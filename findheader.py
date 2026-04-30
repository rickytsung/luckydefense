import hashlib
import os

# ==========================================
# 🎯 核心參數
# ==========================================
VERSION_STR = "20260430011816"
PUB_HASH = "SYqEXCmb+MuPsRJdXLnVvw6Gr7Jh8xMluB9L721grqs="
ENV_KEY = "{94268936-D79E-4345-AA2E-4C49DDE48E5B}"
FILE_NAME = f"{VERSION_STR}.zip"

# 猜測清單
CATEGORIES = ["Table", "Tables", "GameData", "Data", "Config", "CSV", "Asset", "TextAsset", "MasterData"]
VERSIONS = ["v1", "v2", "v3", "v1.0", "v2.0"]
MAX_HEADER_LEN = 2048  # 假標頭長度通常不會超過 2KB

def brute_force_xor():
    if not os.path.exists(FILE_NAME):
        print(f"❌ 找不到檔案 {FILE_NAME}")
        return
        
    # 只讀取前面 2KB 就夠我們碰撞出 ZIP 檔頭了
    with open(FILE_NAME, "rb") as f:
        raw_data = f.read(MAX_HEADER_LEN + 10)
        
    print("🕵️ 啟動 Roxy 破壁者：已知明文爆破掃描...")
    
    # 這是 ZIP 檔案永遠不變的開頭 4 Bytes (PK..)
    target_magic = b"PK\x03\x04"
    
    for cat in CATEGORIES:
        for v in VERSIONS:
            # 組合可能的外皮字串
            magic_str = f"{VERSION_STR}.{v}.{PUB_HASH}.{ENV_KEY}.{cat}"
            xor_key = hashlib.sha512(magic_str.encode()).digest()
            
            # 窮舉假標頭長度 (0 ~ 2048)
            for header_len in range(MAX_HEADER_LEN):
                # 窮舉 XOR 起始偏移量 (0 ~ 63)
                for key_offset in range(64):
                    # 檢查這連續 4 個 bytes 經過 XOR 能不能還原成 PK\x03\x04
                    match = True
                    for i in range(4):
                        if (raw_data[header_len + i] ^ xor_key[(key_offset + i) % 64]) != target_magic[i]:
                            match = False
                            break
                            
                    if match:
                        print("==================================================")
                        print("🏆 [BINGO] 物理碰撞成功！找到正確的解密組合！")
                        print("==================================================")
                        print(f"✔️ 正確的 Category : {cat}")
                        print(f"✔️ 正確的 Version標籤 : {v}")
                        print(f"✔️ 假標頭長度 (Seek)  : {header_len}")
                        print(f"✔️ XOR 起始偏移量     : {key_offset}")
                        print("==================================================")
                        print("💡 請將你的主腳本修改為以下設定：")
                        print(f"   1. CATEGORY = \"{cat}\"")
                        print(f"   2. magic = f\"{{VERSION_STR}}.{v}.{{PUB_HASH}}.{{ENV_KEY}}.{{CATEGORY}}\"")
                        print(f"   3. f.seek({header_len})")
                        print(f"   4. peeled[i] = payload[i] ^ xor_key[(i + {key_offset}) % 64]")
                        return
                        
    print("⚠️ 掃描結束。如果沒有找到：")
    print("   1. 可能 PUB_HASH 有錯。")
    print("   2. 裡面根本不是 ZIP 檔 (請嘗試把 target_magic 換成 b'{\"' 來搜尋 JSON)。")
    print("   3. 他們把外皮加密法從 SHA-512 XOR 換掉了。")

if __name__ == "__main__":
    brute_force_xor()
