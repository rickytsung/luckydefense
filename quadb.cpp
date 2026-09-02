#include <jni.h>
#include <string>
#include <vector>
#include <android/log.h>
#include <thread>
#include <unistd.h>
#include <link.h>
#include <cstdio>
#include <fcntl.h>
#include <cstring>
#include <sys/stat.h>
#include "shadowhook.h"

#define TAG "Roxy"
#define LOGD(...) __android_log_print(ANDROID_LOG_DEBUG, TAG, __VA_ARGS__)

#define RVA_GET_GLOBAL_DB        0x0a0e116c
#define RVA_GAME_VERSUS_UPDATE   0x0a0bec34
#define RVA_GET_GLOBAL_ASSET     0x0a0e7278  // QuantumUnityDB.GetGlobalAsset(String assetPath)
#define RVA_SERIALIZER_CTOR      0x0a10954c  // QuantumUnityJsonSerializer..ctor
#define RVA_SET_PRETTY_PRINT     0x0a109d00  // QuantumUnityJsonSerializer.set_PrettyPrintEnabled
#define RVA_PRINT_OBJECT         0x0a10b47c  // QuantumUnityJsonSerializer.PrintObject(Object obj)

#define DUMP_OUTPUT_DIR          "/data/data/com.percent.aos.randomdice2/files/Quantum_Pretty_Configs"

static uintptr_t g_base = 0;
static int g_null_fd = -1;
static bool g_dumped = false;

// IL2CPP 基本型別與 API
typedef void* (*il2cpp_domain_get_t)();
typedef void* (*il2cpp_domain_get_assemblies_t)(void* domain, size_t* size);
typedef void* (*il2cpp_assembly_get_image_t)(const void* assembly);
typedef void* (*il2cpp_class_from_name_t)(const void* image, const char* namespaze, const char* name);
typedef void* (*il2cpp_object_new_t)(void* klass);

static il2cpp_domain_get_t            il2cpp_domain_get = nullptr;
static il2cpp_domain_get_assemblies_t il2cpp_domain_get_assemblies = nullptr;
static il2cpp_assembly_get_image_t    il2cpp_assembly_get_image = nullptr;
static il2cpp_class_from_name_t       il2cpp_class_from_name = nullptr;
static il2cpp_object_new_t            il2cpp_object_new = nullptr;

// 官方函式指針定義
typedef void* (*GetGlobalAsset_t)(void* string_path_obj);
typedef void (*Serializer_Ctor_t)(void* self);
typedef void (*Serializer_SetPretty_t)(void* self, bool val);
typedef uintptr_t (*Serializer_PrintObject_t)(void* self, void* obj);

static GetGlobalAsset_t         g_GetGlobalAsset = nullptr;
static Serializer_Ctor_t        g_Serializer_Ctor = nullptr;
static Serializer_SetPretty_t   g_Serializer_SetPretty = nullptr;
static Serializer_PrintObject_t g_Serializer_PrintObject = nullptr;
static void*                    g_Serializer_Klass = nullptr;

bool is_valid_ptr(uintptr_t ptr, size_t size = 8) {
    if (ptr < 0x10000000 || ptr > 0x7fffffffffff) return false;
    if (g_null_fd < 0) g_null_fd = open("/dev/null", O_WRONLY);
    return (write(g_null_fd, (const void*)ptr, size) >= 0);
}

std::string get_clean_string(uintptr_t str_ptr) {
    if (!is_valid_ptr(str_ptr, 0x18)) return "";
    int32_t len = *(int32_t*)(str_ptr + 0x10);
    if (len <= 0 || len > 2000000) return "";
    if (!is_valid_ptr(str_ptr + 0x14, len * 2)) return "";

    char16_t* chars = (char16_t*)(str_ptr + 0x14);
    std::string res = "";
    res.reserve(len * 3);
    for (int i = 0; i < len; i++) {
        char16_t c = chars[i];
        if (c < 0x80) {
            res += (char)c;
        } else if (c < 0x800) {
            res += (char)(0xC0 | (c >> 6));
            res += (char)(0x80 | (c & 0x3F));
        } else {
            res += (char)(0xE0 | (c >> 12));
            res += (char)(0x80 | ((c >> 6) & 0x3F));
            res += (char)(0x80 | (c & 0x3F));
        }
    }
    return res;
}

void init_official_pipeline() {
    void* handle = shadowhook_dlopen("libil2cpp.so");
    if (!handle) return;

    il2cpp_domain_get = (il2cpp_domain_get_t)shadowhook_dlsym(handle, "il2cpp_domain_get");
    il2cpp_domain_get_assemblies = (il2cpp_domain_get_assemblies_t)shadowhook_dlsym(handle, "il2cpp_domain_get_assemblies");
    il2cpp_assembly_get_image = (il2cpp_assembly_get_image_t)shadowhook_dlsym(handle, "il2cpp_assembly_get_image");
    il2cpp_class_from_name = (il2cpp_class_from_name_t)shadowhook_dlsym(handle, "il2cpp_class_from_name");
    il2cpp_object_new = (il2cpp_object_new_t)shadowhook_dlsym(handle, "il2cpp_object_new");

    g_GetGlobalAsset = (GetGlobalAsset_t)(g_base + RVA_GET_GLOBAL_ASSET);
    g_Serializer_Ctor = (Serializer_Ctor_t)(g_base + RVA_SERIALIZER_CTOR);
    g_Serializer_SetPretty = (Serializer_SetPretty_t)(g_base + RVA_SET_PRETTY_PRINT);
    g_Serializer_PrintObject = (Serializer_PrintObject_t)(g_base + RVA_PRINT_OBJECT);

    if (il2cpp_domain_get && il2cpp_domain_get_assemblies) {
        void* domain = il2cpp_domain_get();
        size_t size = 0;
        void** assemblies = (void**)il2cpp_domain_get_assemblies(domain, &size);

        for (size_t i = 0; i < size; i++) {
            void* image = il2cpp_assembly_get_image(assemblies[i]);
            void* klass = il2cpp_class_from_name(image, "Quantum", "QuantumUnityJsonSerializer");
            if (klass) {
                g_Serializer_Klass = klass;
                break;
            }
        }
    }

    LOGD("🎯 官方管線綁定完成: GetGlobalAsset=%p, PrintObject=%p, Klass=%p",
         g_GetGlobalAsset, g_Serializer_PrintObject, g_Serializer_Klass);
}

struct OutputItem {
    std::string path;
    std::string json;
};

void background_save(std::vector<OutputItem> list) {
    mkdir(DUMP_OUTPUT_DIR, 0777);
    size_t count = 0;

    for (const auto& item : list) {
        std::string filename = item.path;
        for (char& c : filename) {
            if (!isalnum(c) && c != '_' && c != '-') c = '_';
        }

        std::string path = std::string(DUMP_OUTPUT_DIR) + "/" + filename + ".json";
        FILE* fp = fopen(path.c_str(), "w");
        if (fp) {
            fwrite(item.json.data(), 1, item.json.size(), fp);
            fclose(fp);
            count++;
        }
    }

    LOGD("================================================================================");
    LOGD("🎉 [100%% 官方標準格式導出完成] 成功產出 %zu 筆完整數值 JSON 至:", count);
    LOGD("   %s", DUMP_OUTPUT_DIR);
    LOGD("================================================================================");
}

typedef void (*GameVersusSystem_Update_t)(uintptr_t self, uintptr_t frame);
GameVersusSystem_Update_t orig_GameVersusUpdate = nullptr;

static int s_cursor = 0;
static std::vector<OutputItem> s_results;
static void* s_serializer_instance = nullptr;

void proxy_GameVersusUpdate(uintptr_t self, uintptr_t frame) {
    orig_GameVersusUpdate(self, frame);

    if (g_dumped || g_base == 0) return;

    if (!g_GetGlobalAsset || !g_Serializer_Klass) {
        init_official_pipeline();
        if (!g_GetGlobalAsset || !g_Serializer_Klass) return;
    }

    typedef uintptr_t (*get_Global_t)();
    get_Global_t get_global_db = (get_Global_t)(g_base + RVA_GET_GLOBAL_DB);
    uintptr_t db = get_global_db();
    if (!db || !is_valid_ptr(db, 0x40)) return;

    uintptr_t entries_list = *(uintptr_t*)(db + 0x20);
    if (!is_valid_ptr(entries_list, 0x20)) return;

    uintptr_t items_array = *(uintptr_t*)(entries_list + 0x10);
    int32_t count = *(int32_t*)(entries_list + 0x18);
    if (count <= 0 || !is_valid_ptr(items_array, 0x20)) return;

    // 建立官方序列化器
    if (!s_serializer_instance) {
        s_serializer_instance = il2cpp_object_new(g_Serializer_Klass);
        if (!s_serializer_instance) return;
        g_Serializer_Ctor(s_serializer_instance);
        g_Serializer_SetPretty(s_serializer_instance, true);
    }

    // 分幀批次載入（每幀 15 筆，確保主執行緒載入資源無任何卡頓）
    int batch_size = 15;
    int end = (s_cursor + batch_size < count) ? (s_cursor + batch_size) : count;

    for (int i = s_cursor; i < end; i++) {
        uintptr_t entry_addr = items_array + 0x20 + i * sizeof(void*);
        if (!is_valid_ptr(entry_addr)) continue;
        uintptr_t entry_ptr = *(uintptr_t*)entry_addr;
        if (!is_valid_ptr(entry_ptr, 0x38)) continue;

        void* path_str_obj = *(void**)(entry_ptr + 0x10);
        if (!is_valid_ptr((uintptr_t)path_str_obj, 0x18)) {
            path_str_obj = *(void**)(entry_ptr + 0x18);
        }
        if (!is_valid_ptr((uintptr_t)path_str_obj, 0x18)) continue;

        std::string path = get_clean_string((uintptr_t)path_str_obj);
        if (path.empty()) continue;

        // 核心調用：透過官方 API 將 ResourcePath 解析成純 C# AssetObject
        void* asset_obj = g_GetGlobalAsset(path_str_obj);
        if (!asset_obj || !is_valid_ptr((uintptr_t)asset_obj, 0x10)) continue;

        // 調用官方序列化器輸出 JSON
        uintptr_t json_str_ptr = g_Serializer_PrintObject(s_serializer_instance, asset_obj);
        std::string official_json = get_clean_string(json_str_ptr);

        if (official_json.size() > 10 && official_json.find("QuantumAssetObjectSourceResource") == std::string::npos) {
            s_results.push_back({path, official_json});
        }
    }

    s_cursor = end;

    if (s_cursor >= count) {
        g_dumped = true;
        LOGD("🚀 官方 API 讀取完畢，捕獲 %zu 筆完整設定檔，交由背景寫檔 ...", s_results.size());
        std::thread(background_save, std::move(s_results)).detach();
    }
}

struct DLData { const char* n; uintptr_t b; };

extern "C" JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM* vm, void* reserved) {
    shadowhook_init(SHADOWHOOK_MODE_UNIQUE, false);

    std::thread([]() {
        DLData mi = {"libil2cpp.so", 0};
        while (mi.b == 0) {
            dl_iterate_phdr([](struct dl_phdr_info* info, size_t, void* data) {
                auto m = (DLData*)data;
                if (info->dlpi_name && strstr(info->dlpi_name, m->n)) {
                    m->b = (uintptr_t)info->dlpi_addr;
                    return 1;
                }
                return 0;
            }, &mi);
            if (mi.b == 0) usleep(100000);
        }

        g_base = mi.b;
        LOGD("✅ libil2cpp.so 鎖定: 0x%lx", g_base);

        shadowhook_hook_func_addr(
                (void*)(g_base + RVA_GAME_VERSUS_UPDATE),
                (void*)proxy_GameVersusUpdate,
                (void**)&orig_GameVersusUpdate
        );
    }).detach();

    return JNI_VERSION_1_6;
}
