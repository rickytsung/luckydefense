import os
import hashlib
from Crypto.Cipher import AES

# 🎯 核心配置
TABLE_KEY = bytes.fromhex("C2D9838123EC7633551FF9AB64EB6BC7FFFE5E96A4D2FFDD5A7F4CC0F8251E38")
VERSION = "20260427084630"
PUB_HASH = "FaX4XJ9OXH1t7qVBKVoNiIe4ApuF6SCibGr2Tm0wNO8="
ENV_KEY = "{94268936-D79E-4345-AA2E-4C49DDE48E5B}"
CATEGORY = "Table"

def is_valid_text(data):
    """
    使用嚴格的 UTF-8 校驗：
    真正的文字 (包含中日韓) 轉碼後不會有大量 \ufffd (亂碼替換符)，
    也不會出現 0-31 之間的底層控制字元。
    """
    if not data: return False
    
    # 預先處理可能的 PKCS7 填充，避免把正常的加密填充當成控制字元
    pad_len = data[-1]
    test_data = data
    if 1 <= pad_len <= 16 and data[-pad_len:] == bytes([pad_len]) * pad_len:
        test_data = data[:-pad_len]
        
    text = test_data.decode('utf-8', errors='replace')
    invalid_utf8 = text.count('\ufffd')
    control_chars = sum(1 for c in text if ord(c) < 32 and ord(c) not in (9, 10, 13))
    
    # 允許最多 2 個斷字(剛好切在區塊邊界)，且不能有底層控制字元
    return invalid_utf8 <= 2 and control_chars <= 1

def roxy_dynamic_resync_fixed(file_path):
    magic = f"{VERSION}.v1.{PUB_HASH}.{ENV_KEY}.{CATEGORY}"
    xor_key = hashlib.sha512(magic.encode()).digest()
    with open(file_path, "rb") as f:
        f.seek(80)
        payload = f.read()
        
    peeled = bytearray(len(payload))
    for i in range(len(payload)):
        peeled[i] = payload[i] ^ xor_key[(i + 19) % 64]

    output_dir = "Table_Resynced_Perfect"
    if not os.path.exists(output_dir): os.makedirs(output_dir)

    chunks = peeled.split(b"PK\x03\x04")
    print(f"⚔️ 啟動 Roxy 動態自適應引擎 (回歸完美版)：修復最後一行與多國語言...")

    for i in range(1, len(chunks)):
        chunk = chunks[i]
        if len(chunk) < 100: continue

        name_len = int.from_bytes(chunk[22:24], "little")
        original_name = chunk[26 : 26 + name_len].decode('ascii', errors='ignore')
        base_name = original_name.split('.')[0] if original_name else f"Table_{i:03d}"
        real_name = "".join(x for x in base_name if x.isalnum() or x == '_')

        final_data = bytearray()
        current_pos = 0
        
        print(f"🕵️ 正在動態掃描: {real_name}.csv")

        while current_pos < len(chunk) - 32:
            found_iv = None
            start_offset = 0
            
            # 🐕 尋找 IV，每次測試 32 Bytes 確保精準度
            for offset in range(current_pos, min(current_pos + 1024, len(chunk) - 32)):
                test_iv = bytes(chunk[offset : offset + 16])
                test_cipher = bytes(chunk[offset + 16 : offset + 48])
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
            
            # 🚜 解密推進
            while p < len(chunk) - 15:
                block = bytes(chunk[p : p + 16])
                decrypted_block = cipher_engine.decrypt(block)
                
                if is_valid_text(decrypted_block):
                    final_data.extend(decrypted_block)
                    consecutive_garbage = 0
                else:
                    final_data.extend(decrypted_block)
                    consecutive_garbage += 1
                
                p += 16
                
                # 🚨 如果連續 2 個 Block 是亂碼，代表撞到斷層，退回並重新獵犬
                if consecutive_garbage >= 2:
                    final_data = final_data[:-32] # 移除這兩塊亂碼
                    current_pos = p - 32 
                    break
            else:
                current_pos = len(chunk)

        if final_data:
            # 🛠️ 物理清洗結尾：不再使用會誤殺的 rfind('\n')
            pad_len = final_data[-1]
            if 1 <= pad_len <= 16 and final_data[-pad_len:] == bytes([pad_len]) * pad_len:
                final_data = final_data[:-pad_len]
            final_data = final_data.rstrip(b'\x00') # 僅移除殘留的空字元
            
            with open(os.path.join(output_dir, f"{real_name}.csv"), "wb") as out:
                out.write(b'\xef\xbb\xbf') # 注入 BOM 讓 Excel 顯示正常韓文
                out.write(final_data)

    print(f"\n🏆 完美版修復完成！這就是你要的最終成果。")

if __name__ == "__main__":
    roxy_dynamic_resync_fixed("20260427084630.zip")
