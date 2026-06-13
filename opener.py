import xml.etree.ElementTree as ET
import requests
import re
import os

# Google GCS 預設的 S3 XML 命名空間
NS = {"s3": "http://doc.s3.amazonaws.com/2006-03-01"}

def fetch_bucket_pairs(bucket_name):
    """
    獲取儲存桶清單，自動識別動態資料夾名稱，並將相同編號的 json 與 zip 配對
    """
    url = f"https://storage.googleapis.com/{bucket_name}"
    print(f"📡 正在連線至儲存桶: {url} ...")

    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            print(f"❌ 無法存取儲存桶，錯誤碼: {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ 網路連線失敗: {e}")
        return None

    try:
        root = ET.fromstring(response.content)
    except ET.ParseError:
        print("❌ XML 解析失敗，請確認該儲存桶是否完全公開目錄權限。")
        return None

    contents = root.findall("s3:Contents", NS)
    raw_groups = {}

    # ✨ 修正：將 Table 改為 ([^/]+) 允許動態匹配任何資料夾名稱 (如 Table, Voice_ko 等)
    pattern = re.compile(r"Resources/encrypt/([^/]+)/(\d+)\.(json|zip)")

    for item in contents:
        key = item.find("s3:Key", NS).text
        size = int(item.find("s3:Size", NS).text)
        last_modified = item.find("s3:LastModified", NS).text

        match = pattern.match(key)
        if match:
            category = match.group(1)   # 例如: Table 或 Voice_ko
            version_id = match.group(2) # 例如: 20260611073355
            ext = match.group(3)        # json 或 zip

            # 使用 "資料夾/編號" 作為唯一的配對識別碼
            pair_id = f"{category}/{version_id}"

            if pair_id not in raw_groups:
                raw_groups[pair_id] = {
                    "category": category,
                    "version": version_id
                }

            raw_groups[pair_id][ext] = {
                "key": key,
                "size": size,
                "date": last_modified
            }

    # 篩選出同時擁有 json 和 zip 的兩兩成對版本
    matched_pairs = {}
    for pair_id, ext_data in raw_groups.items():
        if "json" in ext_data and "zip" in ext_data:
            matched_pairs[pair_id] = ext_data

    return matched_pairs

def download_file(bucket_name, file_key, save_path):
    """下載單一檔案，直接存放在當前目錄下"""
    url = f"https://storage.googleapis.com/{bucket_name}/{file_key}"
    print(f" 📥 正在下載: {file_key} ...")
    res = requests.get(url, stream=True)
    if res.status_code == 200:
        with open(save_path, "wb") as f:
            for chunk in res.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    else:
        print(f" ❌ 下載失敗，HTTP 狀態碼: {res.status_code}")
        return False

def main():
    print("=" * 60)
    print("🤖 GCS 資源雙子星自動配對下載器 (全環境自適應版)")
    print("=" * 60)

    bucket_name = input("📌 請輸入 GCS 儲存桶名稱 (例如 perbase-prod-arenago2): ").strip()
    if not bucket_name:
        bucket_name = "perbase-prod-randomdice2"

    pairs = fetch_bucket_pairs(bucket_name)

    if not pairs:
        print("❌ 未找到任何成對的資源或無法讀取儲存桶。")
        return

    # 依照時間排序（最新時間倒序）
    sorted_pair_ids = sorted(pairs.keys(), key=lambda x: pairs[x]['version'], reverse=True)

    print(f"\n📊 成功篩選出 {len(sorted_pair_ids)} 組完美成對的資源包：")
    print("-" * 85)
    print(f"{'序號':<4} {'類別 (Category)':<15} {'版本編號 (Version)':<16} {'JSON 大小':<10} {'ZIP 大小':<10}")
    print("-" * 85)

    for idx, pid in enumerate(sorted_pair_ids, 1):
        category = pairs[pid]['category']
        vid = pairs[pid]['version']
        j_size = f"{pairs[pid]['json']['size']} B"
        z_size = f"{pairs[pid]['zip']['size'] / 1024 / 1024:.2f} MB" if pairs[pid]['zip']['size'] > 1024*1024 else f"{pairs[pid]['zip']['size'] / 1024:.1f} KB"
        print(f"[{idx:<2}] {category:<15} {vid:<16} {j_size:<10} {z_size:<10}")
    print("-" * 85)

    # 互動式下載循環
    while True:
        user_input = input("\n💾 請輸入你想下載的 [序號] 或完整的 [類別/版本號] (輸入 q 退出): ").strip()

        if user_input.lower() == 'q':
            print("👋 已退出程式。")
            break

        target_pid = None

        # 判定使用者輸入
        if user_input.isdigit() and len(user_input) <= 3:  # 輸入的是短序號
            idx = int(user_input)
            if 1 <= idx <= len(sorted_pair_ids):
                target_pid = sorted_pair_ids[idx - 1]
            else:
                print("❌ 序號超出範圍，請重新輸入！")
                continue
        else:  # 輸入的是完整的 pair_id (例如 Voice_ko/20260410151510)
            if user_input in pairs:
                target_pid = user_input
            else:
                print("❌ 找不到該資源識別碼，請輸入畫面上精確的 [序號] 或 [類別/版本號]！")
                continue

        # 執行下載
        category = pairs[target_pid]["category"]
        version_id = pairs[target_pid]["version"]
        
        print(f"\n🚀 準備下載: 類別 [{category}] 版本 [{version_id}]")
        json_key = pairs[target_pid]["json"]["key"]
        zip_key = pairs[target_pid]["zip"]["key"]

        # ✨ 修正檔名命名規則，移除路徑斜線，用底線代替，直接存在當前目錄
        local_json = f"{category}_{version_id}.json"
        local_zip = f"{category}_{version_id}.zip"

        success_j = download_file(bucket_name, json_key, local_json)
        success_z = download_file(bucket_name, zip_key, local_zip)

        if success_j and success_z:
            print(f"✨ [成功] 檔案 {local_json} 與 {local_zip} 已完全下載至當前目錄！")
        print("-" * 50)

if __name__ == "__main__":
    main()
