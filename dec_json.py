import os
import struct
import hashlib
from Crypto.Cipher import AES

# ==========================================
# 🎯 核心參數
# ==========================================
VERSION_INT = 20260416162326
VERSION_STR = str(VERSION_INT)

PUB_HASH = "1BxaYqbTsOMflyFwHgRKcVtWNV9l8t44qvsJ3un5Z3E="
ENV_KEY = "{94268936-D79E-4345-AA2E-4C49DDE48E5B}"
CATEGORY = "GameData" 

def generate_master_key():
    print("🔑 [Phase 1] 啟動 PBKDF2 密鑰鍛造爐...")
    password = b"v1" + struct.pack(">q", VERSION_INT) + ENV_KEY.encode('utf-8')
    salt = hashlib.sha256(password).digest()
    master_key = hashlib.pbkdf2_hmac('sha1', password, salt, 4096, 32)
    print(f"✔️ 鍛造完成 Master Key: {master_key.hex().upper()}")
    return master_key

def is_valid_text(data):
    """嚴格的 UTF-8 校驗，完美適用於 JSON 格式"""
    if not data: return False
    pad_len = data[-1]
    test_data = data
    if 1 <= pad_len <= 16 and data[-pad_len:] == bytes([pad_len]) * pad_len:
        test_data = data[:-pad_len]
        
    text = test_data.decode('utf-8', errors='replace')
    invalid_utf8 = text.count('\ufffd')
    control_chars = sum(1 for c in text if ord(c) < 32 and ord(c) not in (9, 10, 13))
    return invalid_utf8 <= 2 and control_chars <= 1

def extract_aes_payload(payload_data, TABLE_KEY, output_path):
    """核心獵犬引擎：支援 16KB 斷層與後續明文直接拼接"""
    final_data = bytearray()
    current_pos = 0
    
    while current_pos < len(payload_data) - 32:
        found_iv = None
        start_offset = 0
        
        # 尋找 IV
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
            break # 找不到新的 IV，代表剩下的可能是純明文

        cipher_engine = AES.new(TABLE_KEY, AES.MODE_CBC, found_iv)
        p = start_offset
        consecutive_garbage = 0
        
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
            
            # 如果連續解出亂碼，代表撞到 16KB 物理邊界 (原文明文區)
            if consecutive_garbage >= 2:
                final_data = final_data[:-32] 
                current_pos = p - 32 
                break
        else:
            current_pos = len(payload_data)

    # 🎯 關鍵：如果獵犬引擎中斷了，代表後面全是沒加密的 JSON 原文，直接拼上去！
    if final_data and current_pos < len(payload_data):
        final_data.extend(payload_data[current_pos:])

    if final_data:
        pad_len = final_data[-1]
        if 1 <= pad_len <= 16 and final_data[-pad_len:] == bytes([pad_len]) * pad_len:
            final_data = final_data[:-pad_len]
        final_data = final_data.rstrip(b'\x00')
        
        with open(output_path, "wb") as out:
            out.write(final_data)
        return True
    return False

def decrypt_roxy_data(file_path):
    if not os.path.exists(file_path):
        print(f"❌ 找不到檔案: {file_path}")
        return

    TABLE_KEY = generate_master_key()
    print(f"\n⚔️ [Phase 2] 啟動雙模解密引擎，目標: {file_path}")
    
    magic = f"{VERSION_STR}.v1.{PUB_HASH}.{ENV_KEY}.{CATEGORY}"
    xor_key = hashlib.sha512(magic.encode()).digest()
    
    with open(file_path, "rb") as f:
        f.seek(80) 
        payload = f.read()
        
    peeled = bytearray(len(payload))
    for i in range(len(payload)):
        peeled[i] = payload[i] ^ xor_key[(i + 19) % 64]

    output_dir = "Json_Decrypted_Final"
    if not os.path.exists(output_dir): os.makedirs(output_dir)

    chunks = peeled.split(b"PK\x03\x04")
    
    # ==========================================
    # 模式判斷：ZIP 結構 vs 單一檔案結構
    # ==========================================
    if len(chunks) <= 1:
        print("⚠️ 找不到 ZIP 結構！自動切換至【單一檔案直解模式】...")
        output_path = os.path.join(output_dir, f"{CATEGORY}_{VERSION_STR}.json")
        
        if extract_aes_payload(peeled, TABLE_KEY, output_path):
            print("=" * 60)
            print(f"🏆 單一檔案解析成功！")
            print(f"✔️ 已儲存為: {output_path}")
            print("=" * 60)
        else:
            print("❌ 解析失敗。如果這不是 ZIP，可能是 CATEGORY 猜錯導致 XOR 鑰匙錯誤。")
            
    else:
        print(f"📦 偵測到 ZIP 結構，切換至【批次提取模式】...")
        success_count = 0
        for i in range(1, len(chunks)):
            chunk = chunks[i]
            if len(chunk) < 100: continue

            name_len  = int.from_bytes(chunk[22:24], "little")
            extra_len = int.from_bytes(chunk[24:26], "little")
            data_start = 26 + name_len + extra_len
            
            original_name = chunk[26 : 26 + name_len].decode('ascii', errors='ignore')
            base_name = original_name.split('.')[0] if original_name else f"Data_{i:03d}"
            real_name = "".join(x for x in base_name if x.isalnum() or x == '_')

            comp_size = int.from_bytes(chunk[14:18], "little")
            if comp_size > 0 and data_start + comp_size <= len(chunk):
                payload_data = chunk[data_start : data_start + comp_size]
            else:
                end_idx = len(chunk)
                dd_idx = chunk.find(b"PK\x07\x08", data_start)
                cd_idx = chunk.find(b"PK\x01\x02", data_start)
                if dd_idx != -1: end_idx = min(end_idx, dd_idx)
                if cd_idx != -1: end_idx = min(end_idx, cd_idx)
                payload_data = chunk[data_start : end_idx]

            output_path = os.path.join(output_dir, f"{real_name}.json")
            if extract_aes_payload(payload_data, TABLE_KEY, output_path):
                success_count += 1

        print("=" * 60)
        print(f"🏆 ZIP 批次解析完成！")
        print(f"✔️ 成功解密檔案數 : {success_count} 個")
        print(f"📂 檔案存放於: {os.path.abspath(output_dir)}")
        print("=" * 60)

if __name__ == "__main__":
    decrypt_roxy_data(f"{VERSION_STR}.zip")
