import xml.etree.ElementTree as ET
import requests
import re
import os

# Google GCS 預設的 S3 XML 命名空間
NS = {"s3": "http://doc.s3.amazonaws.com/2006-03-01"}

def fetch_bucket_pairs(bucket_name):
    """
    獲取儲存桶清單並自動將相同編號的 json 與 zip 配對
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

    # 解析 XML 結構
    try:
        root = ET.fromstring(response.content)
    except ET.ParseError:
        print("❌ XML 解析失敗，請確認該儲存桶是否完全公開目錄權限。")
        return None

    contents = root.findall("s3:Contents", NS)
    raw_groups = {}

    # 匹配目標路徑與編號的 正則表達式
    pattern = re.compile(r"Resources/encrypt/Table/(\d+)\.(json|zip)")

    for item in contents:
        key = item.find("s3:Key", NS).text
        size = int(item.find("s3:Size", NS).text)
        last_modified = item.find("s3:LastModified", NS).text

        match = pattern.match(key)
        if match:
            version_id = match.group(1)
            ext = match.group(2)

            if version_id not in raw_groups:
                raw_groups[version_id] = {}

            raw_groups[version_id][ext] = {
                "key": key,
                "size": size,
                "date": last_modified
            }

    # 篩選出同時擁有 json 和 zip 的兩兩成對版本
    matched_pairs = {}
    for version_id, ext_data in raw_groups.items():
        if "json" in ext_data and "zip" in ext_data:
            matched_pairs[version_id] = ext_data

    return matched_pairs

def download_file(bucket_name, file_key, save_path):
    """下載單一檔案的輔助函式（已移除路徑建立，直接存檔）"""
    url = f"https://storage.googleapis.com/{bucket_name}/{file_key}"
    print(f" 📥 正在下載: {file_key} ...")
    res = requests.get(url, stream=True)
    if res.status_code == 200:
        # 直接寫入目前資料夾，不再去切路徑
        with open(save_path, "wb") as f:
            for chunk in res.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    else:
        print(f" ❌ 下載失敗，HTTP 狀態碼: {res.status_code}")
        return False

def main():
    print("=" * 60)
    print("🤖 GCS 資源雙子星自動配對下載器 (純檔名修正版)")
    print("=" * 60)

    bucket_name = input("📌 請輸入 GCS 儲存桶名稱 (預設: perbase-prod-randomdice2): ").strip()
    # perbase-prod-{}
    # luckydefense, luckydefensesolo, cooptd
    if not bucket_name:
        bucket_name = "perbase-prod-randomdice2"

    pairs = fetch_bucket_pairs(bucket_name)

    if not pairs:
        print("❌ 未找到任何成對的資源或無法讀取儲存桶。")
        return

    # 排序編號（最新時間倒序）
    sorted_versions = sorted(pairs.keys(), reverse=True)

    print(f"\n📊 成功篩選出 {len(sorted_versions)} 組完美成對的資源包：")
    print("-" * 75)
    print(f"{'序號':<4} {'版本編號 (Version)':<16} {'JSON 大小':<10} {'ZIP 大小':<10} {'更新時間 (UTC)':<20}")
    print("-" * 75)

    for idx, vid in enumerate(sorted_versions, 1):
        j_size = f"{pairs[vid]['json']['size']} B"
        z_size = f"{pairs[vid]['zip']['size'] / 1024:.1f} KB"
        date_str = pairs[vid]['zip']['date'][:19].replace('T', ' ')
        print(f"[{idx:<2}] {vid:<16} {j_size:<10} {z_size:<10} {date_str:<20}")
    print("-" * 75)

    # 互動式下載循環
    while True:
        user_input = input("\n💾 請輸入你想下載的 [版本編號] 或 [序號] (輸入 q 退出): ").strip().lower()

        if user_input == 'q':
            print("👋 已退出程式。")
            break

        target_version = None

        # 檢查使用者輸入的是序號還是完整的編號
        if user_input.isdigit():
            if len(user_input) <= 3:  # 判定為序號
                idx = int(user_input)
                if 1 <= idx <= len(sorted_versions):
                    target_version = sorted_versions[idx - 1]
                else:
                    print("❌ 序號超出範圍，請重新輸入！")
                    continue
            else:  # 判定為完整編號
                if user_input in pairs:
                    target_version = user_input
                else:
                    print("❌ 找不到該版本編號，請確認輸入是否正確！")
                    continue
        else:
            print("❌ 輸入格式錯誤，請輸入數字序號或完整編號。")
            continue

        # 執行下載
        print(f"\n🚀 準備下載版本: {target_version}")
        json_key = pairs[target_version]["json"]["key"]
        zip_key = pairs[target_version]["zip"]["key"]

        # 設定本地儲存檔名（純檔名，無任何路徑字元）
        local_json = f"{target_version}.json"
        local_zip = f"{target_version}.zip"

        success_j = download_file(bucket_name, json_key, local_json)
        success_z = download_file(bucket_name, zip_key, local_zip)

        if success_j and success_z:
            print(f"✨ [成功] 版本 {target_version} 的 JSON 與 ZIP 已完全下載至本目錄！")
        print("-" * 50)

if __name__ == "__main__":
    main()
