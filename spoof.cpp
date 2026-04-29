#include <jni.h>
#include <dlfcn.h>
#include <android/log.h>
#include <shadowhook.h>
#include <unistd.h>
#include <sys/mman.h>
#include <thread>
#include <string>
#include <cstring>
#include <sys/stat.h>
#include <fcntl.h>
#include <sys/time.h>
#include <fstream>
#include <link.h>
#include <errno.h>

#define TAG "Roxy"
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, TAG, __VA_ARGS__)

// ==========================================
// 🎛️ [指揮官中控台]
// ==========================================
// 讓遊戲本體以為自己是這個版本 (透過官方 API 安全建立字串)
#define SPOOF_GAME_STR      "1.8.18"

// 載入資料時請保持 false，需要抓底層網路行為時再開
#define ENABLE_WATCHDOG     false

// ==========================================
// 📍 [核心 RVA 座標]
// ==========================================
#define RVA_LOAD_CSV        0x9f3334c
#define RVA_APP_VERSION     0x5c537e0
#define RVA_UNITY_VERSION   0xb133810
#define RVA_TEXTASSET_VER   0xb2b9120
#define RVA_TMP_SET_VER     0xb0cc5d4

#define HACK_DIR            "/sdcard/Download/Roxy"
uintptr_t g_il2cpp_base = 0;

// 🌟 官方 IL2CPP 字串創建 API (最安全的字串偽裝法)
typedef void* (*il2cpp_string_new_t)(const char* str);
il2cpp_string_new_t il2cpp_string_new = nullptr;

// ==========================================
// 🛡️ 駭客級記憶體探測 (0 FD 消耗)
// ==========================================
int g_null_fd = -1;

bool is_memory_readable(void* ptr, size_t size) {
    if (!ptr || (uintptr_t)ptr < 0x10000) return false;

    if (g_null_fd < 0) {
        g_null_fd = open("/dev/null", O_WRONLY);
        if (g_null_fd < 0) return false;
    }

    bool safe = true;
    if (write(g_null_fd, ptr, 1) < 0) safe = false;
    if (safe && size > 1) {
        uint8_t* tail = (uint8_t*)ptr + size - 1;
        if (write(g_null_fd, tail, 1) < 0) safe = false;
    }
    return safe;
}

// ==========================================
// 🛡️ 防彈安全解碼引擎 (完美支援中日韓文)
// ==========================================
std::string safe_il2cpp_to_utf8(void* obj) {
    if (!obj || (uintptr_t)obj < 0x10000) return "";
    if (!is_memory_readable((uint8_t*)obj + 0x10, 4)) return "";
    int32_t len = *(int32_t*)((uint8_t*)obj + 0x10);
    if (len <= 0 || len > 20000000) return "";
    const uint16_t* utf16 = (const uint16_t*)((uint8_t*)obj + 0x14);
    if (!is_memory_readable((void*)utf16, len * 2)) return "";

    std::string utf8;
    utf8.reserve(len * 3);
    for (int32_t i = 0; i < len; ++i) {
        uint16_t c = utf16[i];
        if (c < 0x0080) { utf8 += (char)c; }
        else if (c < 0x0800) { utf8 += (char)(0xC0 | (c >> 6)); utf8 += (char)(0x80 | (c & 0x3F)); }
        else if (c >= 0xD800 && c < 0xDC00 && (i + 1) < len) {
            uint16_t low = utf16[++i];
            uint32_t code_point = 0x10000 + (((c & 0x3FF) << 10) | (low & 0x3FF));
            utf8 += (char)(0xF0 | (code_point >> 18)); utf8 += (char)(0x80 | ((code_point >> 12) & 0x3F));
            utf8 += (char)(0x80 | ((code_point >> 6) & 0x3F)); utf8 += (char)(0x80 | (code_point & 0x3F));
        } else {
            utf8 += (char)(0xE0 | (c >> 12)); utf8 += (char)(0x80 | ((c >> 6) & 0x3F)); utf8 += (char)(0x80 | (c & 0x3F));
        }
    }
    return utf8;
}

// ==========================================
// 🚀 核心黑科技：官方安全字串替換 (0% 崩潰率)
// ==========================================
void* create_spoofed_il2cpp_string(const char* target_val) {
    if (il2cpp_string_new != nullptr) {
        return il2cpp_string_new(target_val);
    }
    return nullptr;
}

// --- [Hook：版本欺騙] ---
typedef void* (*Func_t)(void* methodInfo);
Func_t orig_AppVer, orig_UnityVer, orig_TextAssetVer, orig_TMPVer = nullptr;

void* hook_AppVer(void* m) { return create_spoofed_il2cpp_string(SPOOF_GAME_STR); }
void* hook_UnityVer(void* m) { return create_spoofed_il2cpp_string(SPOOF_GAME_STR); }
void* hook_TextAssetVer(void* m) { return create_spoofed_il2cpp_string(SPOOF_GAME_STR); }
void* hook_TMPVer(void* m) { return create_spoofed_il2cpp_string(SPOOF_GAME_STR); }

// ==========================================
// 🚀 終極 LoadCsv 提取 (無 Queue，零死鎖直接寫檔)
// ==========================================
typedef void* (*LoadCsv_t)(void* name, void* filePath, uint8_t isBuiltIn, void* methodInfo);
LoadCsv_t orig_LoadCsv = nullptr;

void* hooked_LoadCsv(void* name, void* filePath, uint8_t isBuiltIn, void* methodInfo) {
    void* result = orig_LoadCsv(name, filePath, isBuiltIn, methodInfo);
    if (g_il2cpp_base != 0 && name && result) {
        std::string c_name = safe_il2cpp_to_utf8(name);
        if (!c_name.empty()) {
            std::string c_content = safe_il2cpp_to_utf8(result);
            if (!c_content.empty()) {
                struct timeval tv;
                gettimeofday(&tv, NULL);
                long long micro_ts = (long long)tv.tv_sec * 1000000 + tv.tv_usec;

                std::string ext = ".bin";
                if (c_content.find("{") == 0 || c_content.find("[") == 0) ext = ".json";
                else if (c_content.find(",") != std::string::npos || c_content.find("\n") != std::string::npos) ext = ".csv";

                std::string versioned_name = c_name + "_" + std::to_string(micro_ts) + ext;
                std::string path = std::string(HACK_DIR) + "/" + versioned_name;

                std::ofstream ofs(path, std::ios::out | std::ios::binary | std::ios::trunc);
                if (ofs.is_open()) {
                    const unsigned char bom[] = {0xEF, 0xBB, 0xBF};
                    if (ext == ".csv") ofs.write((char*)bom, sizeof(bom));
                    ofs.write(c_content.c_str(), c_content.size());
                    ofs.close();
                    LOGE("💾 [SAVED_SYNC] %s", versioned_name.c_str());
                }
            }
        }
    }
    return result;
}

// --- [看門狗防護] ---
void* dummy_worker(void* arg) { while (true) sleep(3600); return nullptr; }
int (*orig_pthread_create)(pthread_t*, const pthread_attr_t*, void* (*)(void*), void*);
int hooked_pthread_create(pthread_t* t, const pthread_attr_t* a, void* (*r)(void*), void* arg) {
    if (ENABLE_WATCHDOG) {
        uintptr_t caller = (uintptr_t)__builtin_return_address(0);
        Dl_info info;
        if (dladdr((void*)caller, &info) && info.dli_fname) {
            std::string path = info.dli_fname;
            if (path.find("/data/data/") != std::string::npos || path.find("/memfd:") != std::string::npos) {
                return orig_pthread_create(t, a, dummy_worker, arg);
            }
        }
    }
    return orig_pthread_create(t, a, r, arg);
}

// --- [初始化] ---
void init_v117() {
    LOGE("⚡ [INIT] Roxy V117 極簡純粹版啟動...");
    mkdir("/sdcard/Download", 0777);
    mkdir(HACK_DIR, 0777);

    shadowhook_hook_sym_name("libc.so", "pthread_create", (void*)hooked_pthread_create, (void**)&orig_pthread_create);

    while (g_il2cpp_base == 0) {
        dl_iterate_phdr([](struct dl_phdr_info* info, size_t, void* data) {
            if (info->dlpi_name && strstr(info->dlpi_name, "libil2cpp.so")) {
                *(uintptr_t*)data = (uintptr_t)info->dlpi_addr; return 1;
            } return 0;
        }, &g_il2cpp_base);
        usleep(100000);
    }

    // 🌟 獲取 IL2CPP 官方字串創造 API
    void* handle = shadowhook_dlopen("libil2cpp.so");
    if (handle) {
        il2cpp_string_new = (il2cpp_string_new_t)shadowhook_dlsym(handle, "il2cpp_string_new");
        if (il2cpp_string_new) LOGE("✅ 成功獲取 il2cpp_string_new API！");
        else LOGE("❌ 警告：無法獲取 il2cpp_string_new！");
    }

    shadowhook_hook_func_addr((void*)(g_il2cpp_base + RVA_LOAD_CSV), (void*)hooked_LoadCsv, (void**)&orig_LoadCsv);
    shadowhook_hook_func_addr((void*)(g_il2cpp_base + RVA_APP_VERSION), (void*)hook_AppVer, (void**)&orig_AppVer);
    shadowhook_hook_func_addr((void*)(g_il2cpp_base + RVA_UNITY_VERSION), (void*)hook_UnityVer, (void**)&orig_UnityVer);
    shadowhook_hook_func_addr((void*)(g_il2cpp_base + RVA_TEXTASSET_VER), (void*)hook_TextAssetVer, (void**)&orig_TextAssetVer);
    shadowhook_hook_func_addr((void*)(g_il2cpp_base + RVA_TMP_SET_VER), (void*)hook_TMPVer, (void**)&orig_TMPVer);

    LOGE("⚔️ [READY] 任務準備就緒，等待遊戲載入文本。");
}

extern "C" JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM* vm, void* reserved) {
    shadowhook_init(SHADOWHOOK_MODE_UNIQUE, false);
    std::thread(init_v117).detach();
    return JNI_VERSION_1_6;
}
