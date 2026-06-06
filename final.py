import os
import struct
import hashlib
import zipfile
import io
from Crypto.Cipher import AES

# ==========================================
# 🎯 遊戲底層常數
# ==========================================
ENV_KEY = "{94268936-D79E-4345-AA2E-4C49DDE48E5B}"
CATEGORY = "Table"

def derive_keys(version_str, pub_hash):
    """
    計算 XOR 外皮金鑰 與 AES 金鑰
    """
    version_int = int(version_str)
    
    # 1. 算 XOR 外皮金鑰
    magic_str = f"{version_str}.v1.{pub_hash}.{ENV_KEY}.{CATEGORY}"
    xor_key = hashlib.sha512(magic_str.encode()).digest()
    
    # 2. 算 AES 金鑰 (Lucky Defense 專用配方：不含 PubHash)
    pwd_material = b"v1" + struct.pack(">q", version_int) + ENV_KEY.encode()
    salt = hashlib.sha256(pwd_material).digest()
    aes_key = hashlib.pbkdf2_hmac('sha1', pwd_material, salt, 4096, 32)
    
    return xor_key, aes_key

def find_xor_offset(payload_body, xor_key):
    """
    明文碰撞攻擊：爆破尋找正確的 XOR Offset
    利用 ZIP 檔案開頭必為 PK\x03\x04 的特性
    """
    for offset in range(64):
        # 只需要解密前 4 個 Byte 進行比對
        decrypted_magic = bytearray(4)
        for i in range(4):
            decrypted_magic[i] = payload_body[i] ^ xor_key[(i + offset) % 64]
        
        if decrypted_magic == b"PK\x03\x04":
            return offset
    return None

def is_valid_content(data):
    """寬容的語意檢查"""
    if len(data) < 4: return False
    try:
        sample = data[:1024].decode('utf-8', errors='ignore')
        bad_count = sum(1 for c in sample if ord(c) < 32 and ord(c) not in (9, 10, 13))
        if len(sample) > 0 and (bad_count / len(sample)) < 0.05:
            if any(k in sample for k in [",", "{", "[", "#", "string[]", ".int", ".string"]): return True
            if any('\uac00' <= c <= '\ud7a3' for c in sample): return True
    except: pass
    return False

def clean_header(data):
    """自動剔除 C# BinaryWriter 的變長長度標頭"""
    prefixes = [b'#', b',', b'{', b'[', b'I', b'n']
    for i in range(min(8, len(data))):
        if data[i:i+1] in prefixes or (0x41 <= data[i] <= 0x5A) or (0x61 <= data[i] <= 0x7A):
            return data[i:]
    return data

def run_ultimate_pipeline():
    print("=" * 60)
    print("🤖 Roxy 終極自適應破壁者 (本地離線版)")
    print("=" * 60)
    
    # 1. 取得參數
    version_str = input("📌 請輸入版本號 (例如 20260605113820): ").strip()
    pub_hash = input("📌 請輸入 Publish Hash: ").strip()
    
    if not version_str or not pub_hash:
        print("❌ 參數不可為空！")
        return

    # 2. 讀取本地檔案
    file_path = f"{version_str}.zip"
    if not os.path.exists(file_path):
        print(f"❌ 找不到本地檔案: {file_path} (請確認它和本腳本放在同一資料夾)")
        return
        
    print(f"\n📂 讀取本地檔案: {file_path} ...")
    with open(file_path, "rb") as f:
        f.seek(32) # 跳過假標頭
        payload_body = f.read()

    # 3. 計算基礎金鑰
    print("⚙️ 正在根據參數鍛造密鑰...")
    xor_key, AES_KEY = derive_keys(version_str, pub_hash)

    # 4. 自動爆破 XOR 偏移量
    print("🔍 啟動明文碰撞掃描，尋找 XOR 偏移量...")
    offset = find_xor_offset(payload_body, xor_key)
    
    if offset is None:
        print("❌ 碰撞失敗！無法找到 PK 標頭，請確認你的 Version 和 PubHash 真的正確。")
        return
        
    print(f"🎯 [BINGO] 成功鎖定 XOR 偏移量: {offset}")

    # 5. 全面剝離外皮
    print("✂️ 正在進行全檔案 XOR 剝皮處理...")
    peeled = bytearray(len(payload_body))
    for i in range(len(payload_body)):
        peeled[i] = payload_body[i] ^ xor_key[(i + offset) % 64]

    out_dir = f"Decrypted_{version_str}"
    os.makedirs(out_dir, exist_ok=True)
    success = 0

    # 6. 進入 ZIP 解密
    try:
        with zipfile.ZipFile(io.BytesIO(peeled)) as z:
            file_list = z.namelist()
            print(f"📦 成功突破 XOR 外層！準備解密 {len(file_list)} 個檔案...\n")

            for name in file_list:
                raw = z.read(name)
                if len(raw) < 32: continue

                final_plain = None
                
                try:
                    iv = raw[:16]
                    cipher = AES.new(AES_KEY, AES.MODE_CBC, iv)
                    dec = cipher.decrypt(raw[16:])
                    
                    p_len = dec[-1]
                    test_body = dec[:-p_len] if 1 <= p_len <= 16 else dec
                    
                    if is_valid_content(test_body):
                        final_plain = test_body
                except: pass
                
                # 終極救援機制 (針對語系檔)
                if not final_plain and ("localization" in name.lower() or "string" in name.lower()):
                    try:
                        final_plain = AES.new(AES_KEY, AES.MODE_CBC, raw[:16]).decrypt(raw[16:])
                    except: pass

                if final_plain:
                    cleaned = clean_header(final_plain)
                    
                    ext = ".json" if cleaned.strip().startswith(b'{') else ".csv"
                    safe_name = name.replace(".csv", ext) if name.endswith(".csv") else name
                    
                    with open(os.path.join(out_dir, safe_name), "wb") as out:
                        out.write(b'\xef\xbb\xbf') # 寫入 UTF-8 BOM
                        out.write(cleaned)
                    success += 1
                else:
                    # 解不開的暫存為 .bin
                    with open(os.path.join(out_dir, "FAILED_" + name + ".bin"), "wb") as out:
                        out.write(raw)
                        
    except zipfile.BadZipFile:
        print("❌ ZIP 結構損壞！雖然破解了 Offset，但整體結構仍然無效。")
        return

    print("=" * 60)
    print(f"🏆 大一統自適應破壁完成！")
    print(f"📈 成功破譯: {success} / {len(file_list)} 個檔案")
    print(f"📂 輸出目錄: {os.path.abspath(out_dir)}")
    print("=" * 60)

if __name__ == "__main__":
    run_ultimate_pipeline()
