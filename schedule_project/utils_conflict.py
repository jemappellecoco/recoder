# import os 
# from PySide6.QtCore import QDate, QDateTime, QTime
# import json
# from utils import resource_path  ,log
# def find_conflict_blocks(file_path, qdate, track_index, start_hour, duration):
#     new_start_dt = QDateTime(qdate, QTime(int(start_hour), int((start_hour % 1) * 60)))
#     new_end_dt = new_start_dt.addSecs(int(duration * 3600))
    
#     path = resource_path(file_path)
#     if not os.path.exists(path):
#         log(f"⚠️ 無法找到排程檔 {file_path}，視為無衝突")
#         return []

#     try:
#         with open(path, "r", encoding="utf-8") as f:
#             data = json.load(f)
#     except Exception as e:
#         log(f"❌ 無法讀取排程檔 {file_path}：{e}")
#         return []

#     conflicts = []
#     for block in data:
#         if block["track_index"] != track_index:
#             continue
#         b_qdate = QDate.fromString(block["qdate"], "yyyy-MM-dd")
#         if b_qdate != qdate:
#             continue
#         b_start = float(block["start_hour"])
#         b_duration = float(block["duration"])
#         b_start_dt = QDateTime(b_qdate, QTime(int(b_start), int((b_start % 1) * 60)))
#         b_end_dt = b_start_dt.addSecs(int(b_duration * 3600))
#         if new_start_dt < b_end_dt and new_end_dt > b_start_dt:
#             conflicts.append(block["label"])
    
#     return conflicts
# utils_conflict.py（新格式版）
import os
import json
from PySide6.QtCore import QDate, QDateTime, QTime
from utils import resource_path, log, hhmm_to_hours  # ← 取用 HH:MM → 小時

def find_conflict_blocks(file_path, qdate: QDate, track_index: int, start_hour: float, duration: float):
    """
    讀取 schedule.json（新 schema）檢查是否與既有區塊重疊。
    新 schema 欄位：
      - qdate: "yyyy-MM-dd"
      - track_index: int
      - start_time: "HH:MM"
      - duration_time: "HH:MM"
      - end_time: "HH:MM"（可省略，會用 start+duration 推）
      - end_qdate: "yyyy-MM-dd"（可省略，跨日會自動推）
      - label: str
    參數 start_hour/duration 為**內部 float 小時**（維持既有呼叫介面）。
    """
    # ➤ 新增行程的起訖時間（用內部 float 小時換算）
    new_start_dt = QDateTime(qdate, QTime(int(start_hour), int((start_hour % 1) * 60)))
    end_hour = start_hour + duration
    end_qdate = qdate.addDays(1) if end_hour >= 24 else qdate
    new_end_dt = QDateTime(end_qdate, QTime(int(end_hour % 24), int((end_hour % 1) * 60)))

    path = resource_path(file_path)
    if not os.path.exists(path):
        log(f"⚠️ 無法找到排程檔 {file_path}，視為無衝突")
        return []

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        log(f"❌ 無法讀取排程檔 {file_path}：{e}")
        return []

    conflicts = []
    for block in data:
        # 軌道過濾
        try:
            if int(block.get("track_index", -1)) != int(track_index):
                continue
        except Exception:
            continue

        # 解析開始日期（僅檢查「同一天開始」的行程）
        b_qdate = QDate.fromString(str(block.get("qdate", "")), "yyyy-MM-dd")
        if not b_qdate.isValid() or b_qdate != qdate:
            continue

        # 讀取新格式時間欄位
        start_str = block.get("start_time")
        dur_str   = block.get("duration_time")
        end_str   = block.get("end_time")  # 可能缺省
        if not (start_str and dur_str):
            continue  # 少欄位就跳過

        try:
            b_start_h = hhmm_to_hours(start_str)
            b_dur_h   = hhmm_to_hours(dur_str)
            b_end_h   = hhmm_to_hours(end_str) if end_str else (b_start_h + b_dur_h)
        except Exception:
            continue

        # end_qdate 若沒寫，依是否跨 24 小時推
        end_qdate_str = block.get("end_qdate")
        if end_qdate_str:
            b_end_qdate = QDate.fromString(str(end_qdate_str), "yyyy-MM-dd")
            if not b_end_qdate.isValid():
                b_end_qdate = b_qdate.addDays(1) if (b_start_h + b_dur_h) >= 24 else b_qdate
        else:
            b_end_qdate = b_qdate.addDays(1) if (b_start_h + b_dur_h) >= 24 else b_qdate

        # 組成既有區塊的起訖時間
        b_start_dt = QDateTime(b_qdate, QTime(int(b_start_h), int((b_start_h % 1) * 60)))
        b_end_dt   = QDateTime(b_end_qdate, QTime(int(b_end_h % 24), int((b_end_h % 1) * 60)))

        # 半開半閉重疊判斷
        if new_start_dt < b_end_dt and new_end_dt > b_start_dt:
            conflicts.append(block.get("label", "(未命名)"))

    return conflicts

