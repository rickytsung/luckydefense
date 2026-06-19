#include <jni.h>
#include <string>
#include <android/log.h>
#include <thread>
#include <unistd.h>
#include <link.h>
#include "shadowhook.h"

#define TAG "TD_HOOK"
#define LOGD(...) __android_log_print(ANDROID_LOG_DEBUG, TAG, __VA_ARGS__)

// 🎯 目標：負責封裝 PB-EncodeType 的核心大砲
#define RVA_ENCODE_LAUNCHER   0x96923d4  

// Dll : Perbase.V2.Core.dll
// Namespace: Perbase.V2.Core.Crypto
internal static class EciesCrypto
{
	// Fields
	private const Int32 _pubKeySize; // 0x0
	private const Int32 _priKeySize; // 0x0
	private const Int32 _nonceSize; // 0x0
	private const Int32 _headerSize; // 0x0
	private const Int32 _poly1305tagSize; // 0x0
	private const Int32 _chaCha20keySize; // 0x0
	private const Int32 _sharedSecretSize; // 0x0
	private static readonly Byte[] _hkdfSalt; // 0x0

	// Properties

	// Methods
	// RVA: 0x969225c VA: 0x785f946ba25c
	public static Void GenerateKeyPair(out Byte[] publicKey, out Byte[] privateKey) { }
	// RVA: 0x96923d4 VA: 0x785f946ba3d4
	public static Byte[] Encrypt(Byte[] plainData, Byte[] publicKey) { }
	// RVA: 0x9692ab8 VA: 0x785f946baab8
	public static Byte[] Decrypt(Byte[] encryptedData, Byte[] privateKey) { }
	// RVA: 0x9693198 VA: 0x785f946bb198
	private static Void .cctor() { }
}

// ✨ 神級工具：直接扒光 C# Byte[] 陣列的底層二進位數據
void dump_il2cpp_byte_array(const char* array_name, void* array_ptr) {
    if (!array_ptr) {
        LOGD("   📦 [%s] 為 空指標 (Null)", array_name);
        return;
    }
    
    // 1. 提取陣列長度 (位於偏移量 24 處的 int32_t)
    int32_t length = *(int32_t*)((uintptr_t)array_ptr + 24);
    // 2. 定位資料起點 (位於偏移量 32 處)
    uint8_t* data_ptr = (uint8_t*)((uintptr_t)array_ptr + 32);
    
    LOGD("   📦 [%s] 陣列長度為: %d bytes", array_name, length);
    
    if (length <= 0 || length > 4096) return; // 安全保護
    
    std::string hex_str = "";
    std::string ascii_str = "";
    
    for (int i = 0; i < length; i++) {
        char buf[3];
        sprintf(buf, "%02x", data_ptr[i]);
        hex_str += buf;
        ascii_str += (data_ptr[i] >= 32 && data_ptr[i] <= 126) ? (char)data_ptr[i] : '.';
    }
    
    LOGD("      🎯 [%s] Hex  : %s", array_name, hex_str.c_str());
    LOGD("      📝 [%s] ASCII: %s", array_name, ascii_str.c_str());
}

// =============================================================================
// 🔓 封裝大砲穩健攔截器
// =============================================================================
typedef uintptr_t (*EncodeLauncher_t)(uintptr_t x0, uintptr_t x1, uintptr_t x2, uintptr_t x3, uintptr_t x4, uintptr_t x5, uintptr_t x6, uintptr_t x7);
EncodeLauncher_t orig_EncodeLauncher = nullptr;

uintptr_t proxy_EncodeLauncher(uintptr_t x0, uintptr_t x1, uintptr_t x2, uintptr_t x3, uintptr_t x4, uintptr_t x5, uintptr_t x6, uintptr_t x7) {
    LOGD("=======================================================================");
    LOGD("🚀 [封裝大砲 0x96923d4 通電] 正在對齊明文素材與金鑰矩陣...");
    LOGD("=======================================================================");
    
    // 🔥 直接把 X0 (待加密數據) 和 X1 (加密金鑰) 的二進位內文倒出來！
    dump_il2cpp_byte_array("X0_明文數據陣列", (void*)x0);
    dump_il2cpp_byte_array("X1_加密金鑰陣列", (void*)x1);
    LOGD("   👉 參數 X2 控制標記: 0x%lx", x2);
    LOGD("=======================================================================\n");

    return orig_EncodeLauncher(x0, x1, x2, x3, x4, x5, x6, x7);
}

extern "C" JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM* vm, void* reserved) {
    shadowhook_init(SHADOWHOOK_MODE_UNIQUE, false);

    std::thread([]() {
        uintptr_t base = 0;
        while (base == 0) {
            struct { const char* n; uintptr_t b; } mi = {"libil2cpp.so", 0};
            dl_iterate_phdr([](struct dl_phdr_info* info, size_t, void* data) {
                auto m = (decltype(mi)*)data;
                if (info->dlpi_name && strstr(info->dlpi_name, m->n)) {
                    m->b = (uintptr_t)info->dlpi_addr; return 1;
                }
                return 0;
            }, &mi);
            base = mi.b;
            if (base == 0) usleep(100000);
        }

        LOGD("✅ libil2cpp.so 基址鎖定成功: 0x%lx", base);
        sleep(5);

        // 穩健掛鉤標準函數起點
        shadowhook_hook_func_addr(
            (void*)(base + RVA_ENCODE_LAUNCHER), 
            (void*)proxy_EncodeLauncher, 
            (void**)&orig_EncodeLauncher
        );
        LOGD("🏆 陣列二進位深度收割矩陣已就位！");
    }).detach();

    return JNI_VERSION_1_6;
}
