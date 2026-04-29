import os
import struct
import hashlib
from Crypto.Cipher import AES

# ==========================================
# 🎯 核心參數 (未來改版只需更新這裡)
# ==========================================
VERSION_INT = 20260427084630
VERSION_STR = str(VERSION_INT)
PUB_HASH = "FaX4XJ9OXH1t7qVBKVoNiIe4ApuF6SCibGr2Tm0wNO8="
ENV_KEY = "{94268936-D79E-4345-AA2E-4C49DDE48E5B}"
CATEGORY = "Table"

def generate_master_key():
    print("🔑 [Phase 1] 啟動 PBKDF2 密鑰鍛造爐...")
    # 完美還原 C# 記憶體底層的造鑰配方
    password = b"v1" + struct.pack(">q", VERSION_INT) + ENV_KEY.encode('utf-8')
    salt = hashlib.sha256(password).digest()
    master_key = hashlib.pbkdf2_hmac('sha1', password, salt, 4096, 32)
    print(f"✔️ 鍛造完成 Master Key: {master_key.hex().upper()}")
    return master_key

def is_valid_text(data):
    """嚴格的 UTF-8 校驗，用來辨識 AES 區塊的斷層與新 IV"""
    if not data: return False
    pad_len = data[-1]
    test_data = data
    if 1 <= pad_len <= 16 and data[-pad_len:] == bytes([pad_len]) * pad_len:
        test_data = data[:-pad_len]
        
    text = test_data.decode('utf-8', errors='replace')
    invalid_utf8 = text.count('\ufffd')
    control_chars = sum(1 for c in text if ord(c) < 32 and ord(c) not in (9, 10, 13))
    
    return invalid_utf8 <= 2 and control_chars <= 1

def decrypt_roxy_data(file_path):
    TABLE_KEY = generate_master_key()
    
    print(f"\n⚔️ [Phase 2] 啟動 Roxy 動態自適應解密引擎，目標: {file_path}")
    
    # XOR 外皮金鑰
    magic = f"{VERSION_STR}.v1.{PUB_HASH}.{ENV_KEY}.{CATEGORY}"
    xor_key = hashlib.sha512(magic.encode()).digest()
    
    with open(file_path, "rb") as f:
        f.seek(80)
        payload = f.read()
        
    peeled = bytearray(len(payload))
    for i in range(len(payload)):
        peeled[i] = payload[i] ^ xor_key[(i + 19) % 64]

    output_dir = "Table_Decrypted_Final"
    if not os.path.exists(output_dir): os.makedirs(output_dir)

    chunks = peeled.split(b"PK\x03\x04")
    success_count = 0

    for i in range(1, len(chunks)):
        chunk = chunks[i]
        if len(chunk) < 100: continue

        name_len  = int.from_bytes(chunk[22:24], "little")
        extra_len = int.from_bytes(chunk[24:26], "little")
        data_start = 26 + name_len + extra_len
        
        original_name = chunk[26 : 26 + name_len].decode('ascii', errors='ignore')
        real_name = "".join(x for x in (original_name.split('.')[0] if original_name else f"Table_{i:03d}") if x.isalnum() or x == '_')

        # 精準擷取 Payload 避開 ZIP 結尾
        comp_size = int.from_bytes(chunk[14:18], "little")
        payload_data = b""
        if comp_size > 0 and data_start + comp_size <= len(chunk):
            payload_data = chunk[data_start : data_start + comp_size]
        else:
            end_idx = len(chunk)
            dd_idx = chunk.find(b"PK\x07\x08", data_start)
            cd_idx = chunk.find(b"PK\x01\x02", data_start)
            if dd_idx != -1: end_idx = min(end_idx, dd_idx)
            if cd_idx != -1: end_idx = min(end_idx, cd_idx)
            payload_data = chunk[data_start : end_idx]

        if len(payload_data) < 32: continue

        # 🎯 獵犬引擎啟動：動態搜尋 IV 與區塊解密
        final_data = bytearray()
        current_pos = 0
        
        while current_pos < len(payload_data) - 32:
            found_iv = None
            start_offset = 0
            
            # 尋找這個區塊專屬的 IV
            for offset in range(current_pos, min(current_pos + 1024, len(payload_data) - 32)):
                test_iv = bytes(payload_data[offset : offset + 16])
                test_cipher = bytes(payload_data[offset + 16 : offset + 48])
                try:
                    pt = AES.new(TABLE_KEY, AES.MODE_CBC, test_iv).decrypt(test_cipher)
                    if is_valid_text(pt):
                        found_iv = test_iv
                        start_offset = offset + 16
                        break
                except: pass

            if not found_iv:
                break

            cipher_engine = AES.new(TABLE_KEY, AES.MODE_CBC, found_iv)
            p = start_offset
            consecutive_garbage = 0
            
            # 推進解密直到撞上下一組 IV (亂碼區)
            while p < len(payload_data) - 15:
                block = bytes(payload_data[p : p + 16])
                decrypted_block = cipher_engine.decrypt(block)
                
                if is_valid_text(decrypted_block):
                    final_data.extend(decrypted_block)
                    consecutive_garbage = 0
                else:
                    final_data.extend(decrypted_block)
                    consecutive_garbage += 1
                
                p += 16
                
                # 如果連續兩塊都是亂碼，代表遇到斷層，退回並讓獵犬重新找 IV
                if consecutive_garbage >= 2:
                    final_data = final_data[:-32] 
                    current_pos = p - 32 
                    break
            else:
                current_pos = len(payload_data)

        if final_data:
            pad_len = final_data[-1]
            if 1 <= pad_len <= 16 and final_data[-pad_len:] == bytes([pad_len]) * pad_len:
                final_data = final_data[:-pad_len]
            final_data = final_data.rstrip(b'\x00')
            
            with open(os.path.join(output_dir, f"{real_name}.csv"), "wb") as out:
                out.write(b'\xef\xbb\xbf') # BOM，完美保留多國語言
                out.write(final_data)
                
            success_count += 1

    print("=" * 60)
    print(f"🏆 大一統完美解析完成！這場戰役我們真的贏了。")
    print(f"✔️ 成功解密無亂碼表格 : {success_count} 個")
    print(f"📂 檔案存放於: {os.path.abspath(output_dir)}")
    print("=" * 60)

if __name__ == "__main__":
    decrypt_roxy_data(f"{VERSION_STR}.zip")
