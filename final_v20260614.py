import os
import struct
import hashlib
import zipfile
import io
from Crypto.Cipher import AES

# =============================================================================
# 🎯 Core Factory Constants
# =============================================================================
ENV_KEY = "{94268936-D79E-4345-AA2E-4C49DDE48E5B}"
ARENA_KEY = "EjKQviAHsYocRqieYaFMhdqnlSTm1lEQceqKu7RbuiE="
COOPTD_KEY = "u+u0HHucE8O/bKPECdG8kHyBPriLv/YBRRnqMEgx7G8="

def derive_keys_v44(version_str, json_pub_hash, game_choice):
    """
    Dynamically routes key generation based on the target game selection.
    """
    version_int = int(version_str)
    version_bytes = struct.pack(">q", version_int)
    
    # 1. Outer XOR Candidates Pool (Scans both single/plural paths adaptively)
    xor_candidates = {
        "Tables": hashlib.sha512(f"{version_str}.v1.{json_pub_hash}.{ENV_KEY}.Tables".encode()).digest(),
        "Table":  hashlib.sha512(f"{version_str}.v1.{json_pub_hash}.{ENV_KEY}.Table".encode()).digest()
    }
    
    # 2. 🔐 Inner AES Core Routing
    if game_choice == "arena":
        custom_key = ARENA_KEY
        if len(custom_key) == 43: custom_key += "="
        print(f"   [Game] Arena mode active -> Injecting hardcoded key layout...")
        pwd_material = b"v1" + version_bytes + custom_key.encode() + ENV_KEY.encode()
        
    elif game_choice == "cooptd":
        custom_key = COOPTD_KEY
        if len(custom_key) == 43: custom_key += "="
        print(f"   [Game] CoopTD mode active -> Injecting newly harvested key layout...")
        pwd_material = b"v1" + version_bytes + custom_key.encode() + ENV_KEY.encode()
        
    else:
        # Default / Fallback Mode: Matches classic legacy algorithm logic exactly
        print(f"   [Game] Default mode active -> Applying standard legacy fallback template...")
        pwd_material = b"v1" + version_bytes + ENV_KEY.encode()
    
    # 3. Compute final inner AES-256 key
    salt = hashlib.sha256(pwd_material).digest()
    aes_key = hashlib.pbkdf2_hmac('sha1', pwd_material, salt, 4096, 32)
    
    return xor_candidates, aes_key

def find_xor_offset_v44(payload_body, xor_candidates):
    """
    Adaptive brute-force scanner to crack open outer XOR obfuscation.
    """
    for category_name, xor_key in xor_candidates.items():
        for offset in range(64):
            decrypted_magic = bytearray(4)
            for i in range(4):
                decrypted_magic[i] = payload_body[i] ^ xor_key[(i + offset) % 64]
            
            if decrypted_magic == b"PK\x03\x04":
                return offset, xor_key, category_name
    return None, None, None

def is_valid_content(data):
    """Lax semantic content validation for plaintext formatting."""
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
    """Strips variable-length size prefixes appended by C# BinaryWriter."""
    prefixes = [b'#', b',', b'{', b'[', b'I', b'n']
    for i in range(min(8, len(data))):
        if data[i:i+1] in prefixes or (0x41 <= data[i] <= 0x5A) or (0x61 <= data[i] <= 0x7A):
            return data[i:]
    return data

def run_pipeline():
    print("=" * 60)
    print("🤖 Roxy Game-Adaptive Decryption Engine v4.4")
    print("=" * 60)
    
    # 1. Core Target Selector
    game_choice = input("📌 Game (cooptd / arena / default): ").strip().lower()
    
    print("-" * 60)
    version_str = input("📌 Enter Version (e.g., 20260612095228): ").strip()
    json_pub_hash = input("📌 Enter PublisherToolHash from JSON: ").strip()
    
    if not version_str or not json_pub_hash:
        print("❌ Error: Missing required input parameters!")
        return

    # 2. Path Discovery Array Lookups
    target_file = None
    possible_paths = [
        f"{version_str}.zip",
        f"Tables_{version_str}.zip",
        f"Table_{version_str}.zip"
    ]
    
    print("\n🔍 Scanning directory for matching asset archives...")
    for path in possible_paths:
        if os.path.exists(path):
            target_file = path
            break
            
    if not target_file:
        print(f"❌ Error: Asset file not found. Permutations checked:")
        for path in possible_paths:
            print(f"   - {path}")
        return
        
    print(f"✅ [SUCCESS] Locked target package: {target_file}")
    
    with open(target_file, "rb") as f:
        f.seek(32)  # Strip standard 32-byte header
        payload_body = f.read()

    # 3. Assemble Cryptographic Key Chains
    print("\n⚙️ Forging cryptographic keys...")
    xor_candidates, AES_KEY = derive_keys_v44(version_str, json_pub_hash, game_choice)

    # 4. Break Outer Obfuscation
    print("🔍 Scanning for brute-force XOR offset index...")
    offset, target_xor_key, matched_cat = find_xor_offset_v44(payload_body, xor_candidates)
    
    if offset is None:
        print("❌ Error: Decryption breakdown! Unable to match outer XOR configurations.")
        return
        
    print(f"🎯 [XOR Break] Hit Category: 【{matched_cat}】 | Verified offset index: {offset}")

    # 5. Execute Defusing Loop
    peeled = bytearray(len(payload_body))
    for i in range(len(payload_body)):
        peeled[i] = payload_body[i] ^ target_xor_key[(i + offset) % 64]

    out_dir = f"Decrypted_{version_str}"
    os.makedirs(out_dir, exist_ok=True)
    success = 0

    # 6. Reconstruct Inner Payloads
    try:
        with zipfile.ZipFile(io.BytesIO(peeled)) as z:
            file_list = z.namelist()
            print(f"📦 Archive unpacked successfully! Restoring {len(file_list)} database configurations...\n")

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
                    
                    if (1 <= p_len <= 16 and all(b == p_len for b in dec[-p_len:])) or is_valid_content(test_body):
                        final_plain = test_body
                except: pass
                
                # Secondary Rescue Engine
                if not final_plain and ("localization" in name.lower() or "string" in name.lower()):
                    try:
                        final_plain = AES.new(AES_KEY, AES.MODE_CBC, raw[:16]).decrypt(raw[16:])
                    except: pass

                if final_plain:
                    cleaned = clean_header(final_plain)
                    ext = ".json" if cleaned.strip().startswith(b'{') else ".csv"
                    safe_name = name.replace(".csv", ext) if name.endswith(".csv") else name
                    
                    full_out_path = os.path.join(out_dir, safe_name)
                    os.makedirs(os.path.dirname(full_out_path), exist_ok=True)
                    
                    with open(full_out_path, "wb") as out:
                        if not cleaned.startswith(b'\xef\xbb\xbf'):
                            out.write(b'\xef\xbb\xbf')
                        out.write(cleaned)
                    success += 1
                else:
                    full_failed_path = os.path.join(out_dir, "FAILED_" + name + ".bin")
                    os.makedirs(os.path.dirname(full_failed_path), exist_ok=True)
                    with open(full_failed_path, "wb") as out:
                        out.write(raw)
                        
    except zipfile.BadZipFile:
        print("❌ Error: Obfuscation stripped, but inner zip compression matrix is invalid.")
        return

    print("=" * 60)
    print(f"🏆 Verification Pipeline Concluded!")
    print(f"📈 Harvested Plaintext: {success} / {len(file_list)} datasets")
    print(f"📂 Output Directory: {os.path.abspath(out_dir)}")
    print("=" * 60)

if __name__ == "__main__":
    run_pipeline()
