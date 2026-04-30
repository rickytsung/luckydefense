import os
import struct
import hashlib
import zipfile
import io
from Crypto.Cipher import AES

# ==========================================
# 🎯 核心參數 (由你的 Log 實測獲取)
# ==========================================
VERSION_INT = 20260430011816
LOG_KEY_MATERIAL_HEX = "76310000126D3FBBDDA8752B75304848756345384F2F624B5045436447386B4879425072694C762F594252526E714D4567783747383D7B39343236383933362D443739452D343334352D414132452D3443343944444534384535427D"

def derive_final_key(hex_material):
    password = bytes.fromhex(hex_material)
    salt = hashlib.sha256(password).digest()
    return hashlib.pbkdf2_hmac('sha1', password, salt, 4096, 32)

def is_valid_content_v4(data):
    """
    獵犬 4.0 語意檢查：支援多國語言與註記
    """
    if len(data) < 4: return False

    # 1. 嘗試進行 UTF-8 解碼 (這是 Localization 檔的生命線)
    try:
        # 移除前幾個 byte 可能的 BinaryWriter 標頭再嘗試
        test_body = data[1:1024] # 只取前段檢查效能較快
        text = test_body.decode('utf-8', errors='ignore')
        
        # 統計非法控制字元 (0-31 之間，排除換行、Tab)
        bad_chars = sum(1 for c in text if ord(c) < 32 and ord(c) not in (9, 10, 13))
        
        # 如果控制字元比例極低 (小於 1%)，極大機率是正確解密的文字
        if len(text) > 0 and (bad_chars / len(text)) < 0.01:
            # 額外特徵：CSV 的逗號、JSON 的括號、或是 Localization 常見的標頭
            if any(k in text for k in [",", "{", "[", "#", "ID", "Key", "Value"]):
                return True
            # 如果有韓文字元，直接解放
            if any('\uac00' <= c <= '\ud7a3' for c in text):
                return True
    except:
        pass
    return False

def clean_csharp_header(data):
    """
    自動清除 C# BinaryWriter 的字串長度標頭
    """
    # 常見的起始字元 (BOM, {, [, #, ,, 或英文字母)
    for i in range(min(5, len(data))):
        if data[i] in [0xEF, 0x7B, 0x5B, 0x23, 0x2C] or (0x41 <= data[i] <= 0x5A) or (0x61 <= data[i] <= 0x7A):
            return data[i:]
    return data

def harvest_v4():
    print(f"⚔️ 啟動 Roxy 獵犬 4.0 (Localization & 多國語系相容版)...")
    
    CSV_KEY = derive_final_key(LOG_KEY_MATERIAL_HEX)
    JSON_KEY = bytes.fromhex("16D1C9050A0B32E83764A81D801A880773ABEDFD7F8B0B08A1CD87CA0E404F12")
    
    VERSION_STR = str(VERSION_INT)
    PUB_HASH = "SYqEXCmb+MuPsRJdXLnVvw6Gr7Jh8xMluB9L721grqs="
    ENV_KEY = "{94268936-D79E-4345-AA2E-4C49DDE48E5B}"
    magic = f"{VERSION_STR}.v1.{PUB_HASH}.{ENV_KEY}.Table"
    xor_key = hashlib.sha512(magic.encode()).digest()
    
    with open(f"{VERSION_STR}.zip", "rb") as f:
        f.seek(32)
        payload = f.read()
    
    peeled = bytearray(len(payload))
    for i in range(len(payload)):
        peeled[i] = payload[i] ^ xor_key[(i + 53) % 64]

    out_dir = "Table_Harvested_Final"
    os.makedirs(out_dir, exist_ok=True)
    success_count = 0

    with zipfile.ZipFile(io.BytesIO(peeled)) as z:
        all_files = z.namelist()
        print(f"📦 準備處理 {len(all_files)} 個檔案...")

        for file_name in all_files:
            raw_data = z.read(file_name)
            if len(raw_data) < 32: continue

            final_data = None
            
            # 雙金鑰嘗試
            for key in [CSV_KEY, JSON_KEY]:
                iv = raw_data[:16]
                cipher = AES.new(key, AES.MODE_CBC, iv)
                decrypted = cipher.decrypt(raw_data[16:])
                
                # 處理 PKCS7 Padding
                pad_len = decrypted[-1]
                if 1 <= pad_len <= 16:
                    test_data = decrypted[:-pad_len]
                else:
                    test_data = decrypted
                
                if is_valid_content_v4(test_data):
                    final_data = test_data
                    break

            if final_data:
                clean_data = clean_csharp_header(final_data)
                
                with open(os.path.join(out_dir, file_name), "wb") as out:
                    out.write(b'\xef\xbb\xbf') # 加入 UTF-8 BOM 以正確顯示韓文
                    out.write(clean_data)
                success_count += 1
                print(f"✔️ [{success_count:03d}] {file_name} 收割完成")
            else:
                # 最後絕招：如果是 Localization 相關檔案，即便沒通過檢查也強制輸出
                if "localization" in file_name.lower():
                    # 預設使用 CSV_KEY 嘗試輸出
                    iv = raw_data[:16]
                    cipher = AES.new(CSV_KEY, AES.MODE_CBC, iv)
                    decrypted = cipher.decrypt(raw_data[16:])
                    with open(os.path.join(out_dir, "RECOVERED_" + file_name), "wb") as out:
                        out.write(b'\xef\xbb\xbf')
                        out.write(clean_csharp_header(decrypted))
                    print(f"🆘 [強制恢復] {file_name}")

    print("-" * 60)
    print(f"🏆 終極任務報告:")
    print(f"✔️ 成功解密: {success_count} / {len(all_files)}")
    print(f"📂 路徑: {os.path.abspath(out_dir)}")
    print("-" * 60)

if __name__ == "__main__":
    harvest_v4()
