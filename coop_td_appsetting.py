import os
import base64
import requests
import random
import struct
import hashlib
import io
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from Crypto.Cipher import AES  # 依賴 pycryptodome

# =============================================================================
# 🚀 CONFIGURATION & CONSTANTS
# =============================================================================
SERVER_PUBLIC_KEY_HEX = "ba3b4a451c79d3cc01ebcb3f107b555a26d17c6fed7251dff776cc3f159b446a"
TARGET_URL = "https://prod-appsetting-953759719189.asia-northeast3.run.app/api/v1/appsetting/refresh?version=1.6.1"
ECIES_SALT = b"perbase-ecies-v1"

# 🏛️ 38 位元組固定環境常數 (長度剛好是 38!)
ENV_KEY = "{94268936-D79E-4345-AA2E-4C49DDE48E5B}"

# =============================================================================
# 🎲 .NET CORE SYSTEM.RANDOM 狀態機實現
# =============================================================================
class NetRandom:
    def __init__(self, seed):
        self.seed_array = [0] * 56
        ii = abs(self.int32(seed))
        mj = 161803398 - ii
        self.seed_array[55] = mj
        mk = 1
        for i in range(1, 55):
            index = (21 * i) % 55
            self.seed_array[index] = mk
            mk = self.int32(mj - mk)
            if mk < 0: mk = self.int32(mk + 2147483647)
            mj = self.seed_array[index]
        for k in range(1, 5):
            for i in range(1, 56):
                self.seed_array[i] = self.int32(self.seed_array[i] - self.seed_array[1 + (i + 30) % 55])
                if self.seed_array[i] < 0: self.seed_array[i] = self.int32(self.seed_array[i] + 2147483647)
        self.inext = 0
        self.inextp = 21

    @staticmethod
    def int32(val):
        return (val + 2**31) % 2**32 - 2**31

    def next_bytes(self, length):
        buffer = bytearray(length)
        for i in range(length):
            self.inext += 1
            if self.inext >= 56: self.inext = 1
            self.inextp += 1
            if self.inextp >= 56: self.inextp = 1
            ret_val = self.int32(self.seed_array[self.inext] - self.seed_array[self.inextp])
            if ret_val < 0: ret_val = self.int32(ret_val + 2147483647)
            self.seed_array[self.inext] = ret_val
            buffer[i] = int(ret_val) % 256
        return bytes(buffer)

def generate_pb_encode_type(plain_data: bytes) -> str:
    server_public_key = x25519.X25519PublicKey.from_public_bytes(bytes.fromhex(SERVER_PUBLIC_KEY_HEX))
    ephemeral_private_key = x25519.X25519PrivateKey.generate()
    ephemeral_public_bytes = ephemeral_private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    )
    shared_secret = ephemeral_private_key.exchange(server_public_key)
    hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=ECIES_SALT, info=ephemeral_public_bytes)
    chacha20_key = hkdf.derive(shared_secret)
    nonce = os.urandom(12)
    ciphertext_with_tag = ChaCha20Poly1305(chacha20_key).encrypt(nonce, plain_data, None)
    return base64.b64encode(ephemeral_public_bytes + nonce + ciphertext_with_tag).decode('utf-8')

# =============================================================================
# 🎬 MAIN EXECUTIVE PIPELINE
# =============================================================================
def main():
    print("======================================================================")
    print("🤖 Roxy Game-Adaptive Decryption Engine v6.0 [True Key Alignment]")
    print("======================================================================")
    
    # 1. 狀態隨機流與明文生成
    chosen_seed = random.randint(-2147483648, 2147483647)
    prng_stream = NetRandom(chosen_seed)
    plain_data = prng_stream.next_bytes(32)
    
    # 2. 🎯【 終局修正 】：70 碼素材 = 本輪 32B 明文 + 38B 硬編碼 ENV_KEY
    decrypt_key_material = plain_data + ENV_KEY.encode()
    
    pb_encode_type_header = generate_pb_encode_type(plain_data)
    
    headers = {
        "Connection": "keep-alive",
        "Host": "prod-appsetting-953759719189.asia-northeast3.run.app",
        "User-Agent": "UnityPlayer/2021.3.15f1c1 (UnityWebRequest/1.0, libcurl/7.84.0-DEV)",
        "PB-EncodeType": pb_encode_type_header
    }
    
    print("📡 [Step 1] 正在向官方 Cloud Run 發射動態同調握手...")
    try:
        response = requests.get(TARGET_URL, headers=headers, timeout=10)
        print(f"   📥 伺服器響應狀態碼 : {response.status_code}")
        print(f"   📦 成功下載加密配置包 : {len(response.content)} bytes")
        
        if response.status_code != 200 or len(response.content) == 0:
            print("❌ 錯誤：伺服器拒絕放行！")
            return
            
        raw_payload = response.content

        # 組合一：伺服器回傳排布可能（帶 32B 標頭，或是不帶標頭直接進 IV）
        payload_candidates = {
            "Raw Payload 直接切前 16B 當 IV": raw_payload,
            "Stripped 32B 外殼後，切前 16B 當 IV": raw_payload[32:]
        }
        
        # 組合二：Salt 鹽類選用可能
        #（A：70碼明文的 SHA256，B：純 ENV_KEY 的 SHA256，C：標準對齊）
        salt_candidates = {
            "SHA256 of 70-Byte Material": hashlib.sha256(decrypt_key_material).digest(),
            "SHA256 of ENV_KEY Directly": hashlib.sha256(ENV_KEY.encode()).digest()
        }

        print("\n⚡ [Step 2] 正在記憶體實施全自動多維度密鑰矩陣解鎖...")
        print("-" * 70)
        
        match_found = False

        for p_name, p_bytes in payload_candidates.items():
            if len(p_bytes) < 32: continue
            
            # 💡 回應你的問題：前 16 bytes 作為 CBC 模式的初始化向量 IV
            iv = p_bytes[:16]
            encrypted_body = p_bytes[16:]
            
            for salt_name, salt_bytes in salt_candidates.items():
                
                # 呼叫標準 PBKDF2-SHA1 衍生 32 位元組 AES 工作金鑰
                derived_key = hashlib.pbkdf2_hmac('sha1', decrypt_key_material, salt_bytes, 4096, 32)
                
                try:
                    cipher = AES.new(derived_key, AES.MODE_CBC, iv)
                    decrypted_body = cipher.decrypt(encrypted_body)
                    
                    # 🎯 聖杯特徵字元校驗：看開頭是否為標準 JSON '{'
                    if decrypted_body.strip().startswith(b'{'):
                        print(f"🎯 【 終極密鑰鏈完美咬合成功！！！ 】")
                        print(f"   📂 物理分頁結構 : {p_name}")
                        print(f"   🧂 衍生鹽類(Salt): {salt_name}\n")
                        print("=" * 70)
                        
                        # 清洗剪裁 PKCS7 填充
                        padding_len = decrypted_body[-1]
                        if 1 <= padding_len <= 16 and all(b == padding_len for b in decrypted_body[-padding_len:]):
                            decrypted_body = decrypted_body[:-padding_len]
                            
                        json_text = decrypted_body.decode('utf-8', errors='ignore').strip()
                        print(json_text)
                        print("=" * 70)
                        
                        # 成果落盤保存
                        with open("appsetting.json", "w", encoding="utf-8") as out_f:
                            out_f.write(json_text)
                        print(f"📂 成果檔案已成功落盤 : appsetting.json")
                        match_found = True
                        return
                except:
                    pass
                    
        if not match_found:
            print("❌ 解密失敗。密鑰素材已對齊，請確認 Salt 是否有加上額外的位元組編碼。")

    except Exception as e:
        print(f"❌ 網路發射或執行中途潰散: {e}")
    print("=" * 70)

if __name__ == "__main__":
    main()
