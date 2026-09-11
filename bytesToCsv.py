# -*- coding: utf-8 -*-
import csv
import struct

# 列舉映射表
GAME_MODE_TYPES = {
    0: "Normal",
    1: "Hard",
    2: "Hell",
    3: "Abyss",
    4: "DeepSea",
    5: "Training",
}
GAME_CONTENTS_TYPES = {
    0: "Multi",
    1: "HumanTower",
    2: "TempleRaid",
    3: "TempleRaid_Extreme",
    4: "BeachBreakout",
    5: "ChristmasGiftBattle",
    6: "GuildDefense",
}
ENEMY_TYPES = {
    0: "Monster",
    1: "LineBoss",
    2: "QuestBoss",
    3: "Hell_SpecialBoss",
    4: "DeepSea_SpecialMonster",
    5: "Giants",
    6: "GiantsBoss",
    7: "Giant_LockTile",
}
MOVEMENT_TYPES = {0: "Ground", 1: "Flying"}


def read_string(data, pos):
  """依據 -(N+1) N 特徵解析字串"""
  tag = struct.unpack("<i", data[pos : pos + 4])[0]
  if tag == 0:
    return "", pos + 4
  length = struct.unpack("<i", data[pos + 4 : pos + 8])[0]
  text = data[pos + 8 : pos + 8 + length].decode("utf-8", errors="replace")
  return text, pos + 8 + length


def convert_bytes_to_csv(
    bytes_path="EnemyStat.bytes", csv_path="EnemyStat_converted.csv"
):
  with open(bytes_path, "rb") as f:
    data = f.read()

  # 略過 UTF-8 BOM
  pos = 3 if data[:3] == b"\xef\xbb\xbf" else 0

  # 略過 9 bytes 標頭 (1 byte 版本 + 4 bytes 總筆數 + 4 bytes 保留)
  pos += 9

  rows = []
  while pos < len(data):
    if pos + 20 > len(data):
      break
    num_cols = data[pos]
    pos += 1

    # 0: Id
    row_id = struct.unpack("<i", data[pos : pos + 4])[0]
    pos += 4

    # 1: GameModeType
    gmt = GAME_MODE_TYPES.get(
        struct.unpack("<i", data[pos : pos + 4])[0], "Normal"
    )
    pos += 4

    # 2: GameContentsType
    gct = GAME_CONTENTS_TYPES.get(
        struct.unpack("<i", data[pos : pos + 4])[0], "Multi"
    )
    pos += 4

    # 3: Level, 4: TargetFloor
    lvl, tf = struct.unpack("<ii", data[pos : pos + 8])
    pos += 8

    # 5: Type
    et = ENEMY_TYPES.get(struct.unpack("<i", data[pos : pos + 4])[0], "Monster")
    pos += 4

    # 6: MovementType
    mt = MOVEMENT_TYPES.get(
        struct.unpack("<i", data[pos : pos + 4])[0], "Ground"
    )
    pos += 4

    # 7: Hp (string)
    hp, pos = read_string(data, pos)

    # 8: HpCount (int)
    hpc = struct.unpack("<i", data[pos : pos + 4])[0]
    pos += 4

    # 9: Shield (string)
    shield, pos = read_string(data, pos)

    # 10: ShieldCount (int)
    sc = struct.unpack("<i", data[pos : pos + 4])[0]
    pos += 4

    # 11: MoveSpeed (16.16 固定點數)
    ms_raw = struct.unpack("<i", data[pos : pos + 4])[0]
    ms = f"{ms_raw / 65536.0:.2f}"
    pos += 4

    # 12: ScalingValue (int)
    sv = struct.unpack("<i", data[pos : pos + 4])[0]
    pos += 4

    # 保留位元組 (4 bytes)
    pos += 4

    # 13: Defence (string)
    defence, pos = read_string(data, pos)

    # 14: BossAddGold, 15: BossAddManaStone
    bag, bams = struct.unpack("<ii", data[pos : pos + 8])
    pos += 8

    # 16: CustomParameter (陣列結構)
    arr_len = struct.unpack("<i", data[pos : pos + 4])[0]
    pos += 4 + arr_len * 8  # 略過陣列元素
    cp_val = "0"

    # 17: Prefab_Path (string)
    prefab, pos = read_string(data, pos)

    # 18: Icon_Path (string)
    icon, pos = read_string(data, pos)

    rows.append([
        row_id,
        gmt,
        gct,
        lvl,
        tf,
        et,
        mt,
        hp,
        hpc,
        shield,
        sc,
        ms,
        sv,
        defence,
        bag,
        bams,
        cp_val,
        prefab,
        icon,
    ])

  # 寫入 CSV (包含表頭註解與型態定義)
  with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
    writer = csv.writer(f)
    writer.writerow([
        "",
        "",
        "",
        "",
        "",
        "",
        "유닛 위치",
        "",
        "",
        "",
        "",
        "",
        "스케일링 수치",
        "",
        "",
        "",
        "",
        "",
        "",
    ])
    writer.writerow([
        "int",
        " EGameModeType",
        "EGameContentsType",
        "int",
        "int",
        "EEnemyType",
        "EUnitMovementType",
        "string",
        "int",
        "string",
        "int",
        "float",
        "int",
        "string",
        "int",
        "int",
        "float[]",
        "string",
        "string",
    ])
    writer.writerow([
        "Id",
        "GameModeType",
        "GameContentsType",
        "Level",
        "TargetFloor",
        "Type",
        "MovementType",
        "Hp",
        "HpCount",
        "Shield",
        "ShieldCount",
        "MoveSpeed",
        "ScalingValue",
        "Defence",
        "BossAddGold",
        "BossAddManaStone",
        "CustomParameter",
        "Prefab_Path",
        "Icon_Path",
    ])
    writer.writerows(rows)

  print(f"轉換成功！已寫入 {len(rows)} 筆資料至 {csv_path}")


if __name__ == "__main__":
  convert_bytes_to_csv("EnemyStat.bytes", "EnemyStat.csv")
