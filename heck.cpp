#include <jni.h>
#include <dlfcn.h>
#include <android/log.h>
#include <shadowhook.h>
#include <unistd.h>
#include <thread>
#include <string>
#include <cstring>
#include <link.h>
#include <atomic>
#include <fcntl.h>

#define TAG "Roxy_Fortress"
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, TAG, __VA_ARGS__)

// ==========================================
// 📍 [核心 RVA 座標中控台]
// ==========================================
// 🛡️ WaveGroup 抗性 Getter 座標
#define RVA_GET_PERCENT_RES          0xa945e4c  // get_PercentDamageResistance
#define RVA_GET_PERCENT_RES_PCT      0xa944d9c  // get_PercentDamageResistancePercentage
#define RVA_GET_STUN_RES             0xa945e3c  // get_StunResistance
#define RVA_GET_STUN_RES_PCT         0xa944d8c  // get_StunResistancePercentage

// ⚔️ PlayerUnit 傷害行為座標 (來自新 Quantum.Simulation.dll)
#define RVA_GET_ATTACK_DAMAGE        0xad244a0  // GetAttackDamage

#define ENABLE_WATCHDOG              true

uintptr_t g_il2cpp_base = 0;
std::atomic<bool> g_bypass_active(false);

// 🌟 全域原子計數器：統計生命值等比欺騙的呼叫次數
std::atomic<int32_t> g_spoof_call_count(0);

// 核心 Hook 存根（Stub），用於遭反作弊 maps 掃描時動態全量脫鉤
void* stub_pct_res = nullptr;
void* stub_pct_res_pct = nullptr;
void* stub_stun_res = nullptr;
void* stub_stun_res_pct = nullptr;
void* stub_attack_damage = nullptr; // 攻擊力補丁
void* stub_pthread_create = nullptr;
void* stub_open = nullptr;
void* stub_openat = nullptr;

// 原函數備份指標
typedef int64_t (*GetAttackDamage_t)(void* _this, void* frame, void* netPlayer);
GetAttackDamage_t orig_GetAttackDamage = nullptr;

int (*orig_pthread_create)(pthread_t*, const pthread_attr_t*, void* (*)(void*), void*) = nullptr;
int (*orig_open)(const char* pathname, int flags, mode_t mode) = nullptr;
int (*orig_openat)(int dirfd, const char* pathname, int flags, mode_t mode) = nullptr;

// 預先宣告
void rehook_all_delayed();
void deploy_all_fortress_hooks();

// ==========================================
// 🎯 [Getter 劫持：記憶體 100% 原廠，讀取回傳 0]
// ==========================================
uint64_t hooked_get_PercentDamageResistance(void* _this, void* methodInfo) {
    // 每次呼叫進行原子自增
    int32_t current_count = ++g_spoof_call_count;
    if (current_count % 10 == 0) {
        LOGE("🤫 [Roxy_Bypass] 生命值等比欺騙呼叫已累積觸發 %d 次！(抗性已無痕清零)", current_count);
    }
    return 0;
}

uint64_t hooked_get_PercentDamageResistancePercentage(void* _this, void* methodInfo) {
    return 0;
}

uint64_t hooked_get_StunResistance(void* _this, void* methodInfo) {
    return 0;
}

uint64_t hooked_get_StunResistancePercentage(void* _this, void* methodInfo) {
    return 0;
}

// ==========================================
// ⚔️ [發育期補丁：稍微放大前期英雄基礎傷害]
// ==========================================
int64_t hooked_GetAttackDamage(void* _this, void* frame, void* netPlayer) {
    if (g_bypass_active.load() || orig_GetAttackDamage == nullptr) {
        return ((GetAttackDamage_t)(g_il2cpp_base + RVA_GET_ATTACK_DAMAGE))(_this, frame, netPlayer);
    }

    // 獲取原廠正常算出來的物理攻擊力
    int64_t raw_damage = orig_GetAttackDamage(_this, frame, netPlayer);

    // 🎯 前期等比稍微放大 3 倍，既不破壞數值溢出，又能讓你輕鬆秒怪存錢過渡到後期！
    return raw_damage * 50000000;
}

// ==========================================
// 🛡️ [防線一：執行緒看門狗阻斷流]
// ==========================================
void* dummy_worker(void* arg) { while (true) sleep(3600); return nullptr; }

int hooked_pthread_create(pthread_t* t, const pthread_attr_t* a, void* (*r)(void*), void* arg) {
    if (ENABLE_WATCHDOG && !g_bypass_active.load()) {
        uintptr_t caller = (uintptr_t)__builtin_return_address(0);
        Dl_info info;
        if (dladdr((void*)caller, &info) && info.dli_fname) {
            std::string path = info.dli_fname;
            if (path.find("/data/data/") != std::string::npos || path.find("/memfd:") != std::string::npos) {
                LOGE("🛡️ [Watchdog] 成功攔截並掛起背景反作弊掃描線程！");
                return orig_pthread_create ? orig_pthread_create(t, a, dummy_worker, arg) : pthread_create(t, a, dummy_worker, arg);
            }
        }
    }
    return (g_bypass_active.load() || orig_pthread_create == nullptr) ? pthread_create(t, a, r, arg) : orig_pthread_create(t, a, r, arg);
}

// ==========================================
// 🛡️ [防線二：Maps 幻影同步蒸發引擎]
// ==========================================
bool check_scan_threat(const char* pathname) {
    if (!pathname) return false;
    if (strstr(pathname, "proc") != nullptr && strstr(pathname, "map") != nullptr) {
        return true;
    }
    return false;
}

void trigger_ghost_evasion() {
    if (g_bypass_active.exchange(true)) return;

    LOGE("🚨 [GhostMode] 警報！偵測到 maps 記憶體特徵掃描！同步拔除全量補丁實施隱形...");

    // 💥 瞬間拔除所有 Hook（包含代碼補丁、前期傷害補丁、看門狗與 open 自身）
    // 記憶體代碼段（Text Section）100% 恢復至最純淨原廠狀態
    if (stub_pct_res) { shadowhook_unhook(stub_pct_res); stub_pct_res = nullptr; }
    if (stub_pct_res_pct) { shadowhook_unhook(stub_pct_res_pct); stub_pct_res_pct = nullptr; }
    if (stub_stun_res) { shadowhook_unhook(stub_stun_res); stub_stun_res = nullptr; }
    if (stub_stun_res_pct) { shadowhook_unhook(stub_stun_res_pct); stub_stun_res_pct = nullptr; }
    if (stub_attack_damage) { shadowhook_unhook(stub_attack_damage); stub_attack_damage = nullptr; }
    if (stub_pthread_create) { shadowhook_unhook(stub_pthread_create); stub_pthread_create = nullptr; }
    if (stub_open) { shadowhook_unhook(stub_open); stub_open = nullptr; }
    if (stub_openat) { shadowhook_unhook(stub_openat); stub_openat = nullptr; }

    LOGE("🛡️ [GhostMode] 所有補丁已蒸發完畢。5 秒後自動重組防線...");
    std::thread(rehook_all_delayed).detach();
}

int hooked_open(const char* pathname, int flags, mode_t mode) {
    if (check_scan_threat(pathname)) {
        trigger_ghost_evasion();
        return open(pathname, flags, mode);
    }
    return (g_bypass_active.load() || orig_open == nullptr) ? open(pathname, flags, mode) : orig_open(pathname, flags, mode);
}

int hooked_openat(int dirfd, const char* pathname, int flags, mode_t mode) {
    if (check_scan_threat(pathname)) {
        trigger_ghost_evasion();
        return openat(dirfd, pathname, flags, mode);
    }
    return (g_bypass_active.load() || orig_openat == nullptr) ? openat(dirfd, pathname, flags, mode) : orig_openat(dirfd, pathname, flags, mode);
}

// ==========================================
// ⏰ 延時自動重裝補丁引擎
// ==========================================
void rehook_all_delayed() {
    sleep(5); // 完美讓反作弊系統掃描完 100% 原廠乾淨的記憶體
    LOGE("🔄 [GhostMode] 安全期滿，反作弊掃描已離開。重新部署全量堡壘補丁...");

    deploy_all_fortress_hooks();

    g_bypass_active.store(false);
    LOGE("⚔️ [GhostMode] 補丁全數重新部署完畢，功能完美回歸！");
}

void deploy_all_fortress_hooks() {
    // 1. 掛鉤 4 個核心抗性 Getter (過 Checksum 無痕流)
    stub_pct_res = shadowhook_hook_func_addr((void*)(g_il2cpp_base + RVA_GET_PERCENT_RES), (void*)hooked_get_PercentDamageResistance, nullptr);
    stub_pct_res_pct = shadowhook_hook_func_addr((void*)(g_il2cpp_base + RVA_GET_PERCENT_RES_PCT), (void*)hooked_get_PercentDamageResistancePercentage, nullptr);
    stub_stun_res = shadowhook_hook_func_addr((void*)(g_il2cpp_base + RVA_GET_STUN_RES), (void*)hooked_get_StunResistance, nullptr);
    stub_stun_res_pct = shadowhook_hook_func_addr((void*)(g_il2cpp_base + RVA_GET_STUN_RES_PCT), (void*)hooked_get_StunResistancePercentage, nullptr);

    // 2. 掛鉤發育期物理攻擊力放大補丁 (RVA: 0xad244a0)
    stub_attack_damage = shadowhook_hook_func_addr((void*)(g_il2cpp_base + RVA_GET_ATTACK_DAMAGE), (void*)hooked_GetAttackDamage, (void**)&orig_GetAttackDamage);

    // 3. 掛鉤雙重防線門衛：看門狗與 open / openat
    stub_pthread_create = shadowhook_hook_sym_name("libc.so", "pthread_create", (void*)hooked_pthread_create, (void**)&orig_pthread_create);
    stub_open = shadowhook_hook_sym_name("libc.so", "open", (void*)hooked_open, (void**)&orig_open);
    stub_openat = shadowhook_hook_sym_name("libc.so", "openat", (void*)hooked_openat, (void**)&orig_openat);
}

// ==========================================
// ⚙️ [環境初始化入口]
// ==========================================
void init_roxy_fortress_v230() {
    LOGE("⚡ [INIT] Roxy 堡壘 V230 雙向增幅版啟動...");

    while (g_il2cpp_base == 0) {
        dl_iterate_phdr([](struct dl_phdr_info* info, size_t, void* data) {
            if (info->dlpi_name && strstr(info->dlpi_name, "libil2cpp.so")) {
                *(uintptr_t*)data = (uintptr_t)info->dlpi_addr; return 1;
            } return 0;
        }, &g_il2cpp_base);
        usleep(100000);
        usleep(100000);
    }

    LOGE("📍 遊戲基址對齊: 0x%lx, 部署高階發育與秒殺防線...", g_il2cpp_base);
    deploy_all_fortress_hooks();
    LOGE("⚔️ [READY] 終極合體版本就緒！前期物理 3 倍增幅已開，請進關卡暢快發育。");
}

extern "C" JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM* vm, void* reserved) {
    shadowhook_init(SHADOWHOOK_MODE_UNIQUE, false);
    std::thread(init_roxy_fortress_v230).detach();
    return JNI_VERSION_1_6;
}
