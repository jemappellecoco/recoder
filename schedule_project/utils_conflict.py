
from PySide6.QtCore import QDate, QDateTime, QTime
import json

def find_conflict_blocks(file_path, qdate, track_index, start_hour, duration):
    new_start_dt = QDateTime(qdate, QTime(int(start_hour), int((start_hour % 1) * 60)))
    new_end_dt = new_start_dt.addSecs(int(duration * 3600))
    
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    conflicts = []
    for block in data:
        if block["track_index"] != track_index:
            continue
        b_qdate = QDate.fromString(block["qdate"], "yyyy-MM-dd")
        if b_qdate != qdate:
            continue
        b_start = float(block["start_hour"])
        b_duration = float(block["duration"])
        b_start_dt = QDateTime(b_qdate, QTime(int(b_start), int((b_start % 1) * 60)))
        b_end_dt = b_start_dt.addSecs(int(b_duration * 3600))
        if new_start_dt < b_end_dt and new_end_dt > b_start_dt:
            conflicts.append(block["label"])
    
    return conflicts
