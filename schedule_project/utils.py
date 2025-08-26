# utils.py
import sys
import os
from PySide6.QtCore import QDateTime, QObject, Signal,Qt,QDate, QTime
from PySide6.QtGui import QTextCursor,QPixmap
from PySide6.QtCore import QTimer
import traceback
_log_box = None
_buffered_logs = []
MAX_LOG_LINES = 500
DEBUG_MODE = True
MIN_LEAD_SECONDS = 90
DAY_MIN = 24 * 60
# 用訊號把任何執行緒的 log 丟回主執行緒處理

class _LogBus(QObject):
    pushed = Signal(str)

_log_bus = None
# ==== HH:MM <-> 分鐘 / QTime / 小時數 工具 ====

DAY_MIN = 24 * 60
def hourf_to_qtime(hourf: float) -> QTime:
    """
    小時(浮點) -> QTime（四捨五入到分鐘，含 24h 取模）
    避免 49.999 分被 int() 截成 49 分。
    """
    total_min = int(round(float(hourf) * 60)) % DAY_MIN
    return QTime(total_min // 60, total_min % 60)
def ceil_to_next_minute(dt: QDateTime) -> QDateTime:
    t = dt.time()
    if t.second() == 0 and t.msec() == 0:
        return dt
    return dt.addSecs(60 - t.second()).addMSecs(-t.msec())
def normalize_hhmm(s: str) -> str:
    try:
        h, m = s.strip().split(":")
        h, m = int(h), int(m)
        if h < 0 or m < 0:  # 負值不合法
            return "00:00"
        total = (h * 60 + m) % DAY_MIN
        return f"{total // 60:02d}:{total % 60:02d}"
    except Exception:
        return "00:00"
def hhmm_to_min(s: str) -> int:
    """
    'HH:MM' -> 整數分鐘（0..1439，超出一律取模）
    """
    try:
        h, m = s.strip().split(":")
        return (int(h) * 60 + int(m)) % DAY_MIN
    except Exception:
        return 0

def min_to_hhmm(mins: int | float) -> str:
    """
    分鐘 -> 'HH:MM'（會做 24h 取模）
    """
    mins = int(round(mins)) % DAY_MIN
    return f"{mins // 60:02d}:{mins % 60:02d}"

def qtime_to_hhmm(t: QTime) -> str:
    """
    QTime -> 'HH:MM'
    """
    if not isinstance(t, QTime) or not t.isValid():
        return "00:00"
    return f"{t.hour():02d}:{t.minute():02d}"

def hhmm_to_qtime(s: str) -> QTime:
    """
    'HH:MM' -> QTime（非法字串回傳 00:00）
    """
    try:
        h, m = s.strip().split(":")
        h, m = int(h), int(m)
        if 0 <= h < 24 and 0 <= m < 60:
            return QTime(h, m)
    except Exception:
        pass
    return QTime(0, 0)

def hours_to_hhmm(hours: float) -> str:
    """
    小時(可含小數) -> 'HH:MM'
    例如 1.5 -> '01:30'
    """
    total_min = int(round(float(hours) * 60))
    return min_to_hhmm(total_min)

def hhmm_to_hours(s: str) -> float:
    """
    'HH:MM' -> 小時(浮點)
    例如 '01:30' -> 1.5
    """
    return hhmm_to_min(s) / 60.0

def add_minutes_wrap(qdate: QDate, qtime: QTime, delta_min: int) -> tuple[QDate, QTime]:
    """
    在 (qdate, qtime) 上加 delta_min 分鐘，回傳(可能跨日)的新 (QDate, QTime)
    """
    if not isinstance(qdate, QDate):
        qdate = QDate.currentDate()
    if not isinstance(qtime, QTime) or not qtime.isValid():
        qtime = QTime(0, 0)

    base_min = qtime.hour() * 60 + qtime.minute()
    total = base_min + int(delta_min)

    # 計算跨日
    days_delta, mins = divmod(total, DAY_MIN)
    if mins < 0:
        mins += DAY_MIN
        days_delta -= 1

    new_date = qdate.addDays(days_delta)
    new_time = QTime(mins // 60, mins % 60)
    return new_date, new_time

def set_log_box(widget):
    """主視窗建立好 QTextEdit 後要第一時間呼叫這個。"""
    global _log_box, _log_bus
    _log_box = widget

    if _log_bus is None:
        _log_bus = _LogBus()
        # 用 QueuedConnection 確保在主執行緒觸發，避免跨執行緒碰 GUI
        _log_bus.pushed.connect(_append_log_safely, Qt.QueuedConnection)

    # 把先前緩存的 log 一次補印
    for text in _buffered_logs:
        _log_bus.pushed.emit(text)
    _buffered_logs.clear()

    try:
        _log_box.moveCursor(QTextCursor.End)
    except Exception:
        pass


def is_frozen():
    return getattr(sys, 'frozen', False)


def _append_log_safely(text: str):
    """只會在主執行緒被呼叫。"""
    if not _log_box:
        return
    # 截斷過長
    lines = _log_box.toPlainText().splitlines()
    lines.append(text)
    if len(lines) > MAX_LOG_LINES:
        lines = lines[-MAX_LOG_LINES:]
        _log_box.setPlainText("\n".join(lines))
    else:
        _log_box.append(text)
    try:
        _log_box.moveCursor(QTextCursor.End)
    except Exception:
        pass

def log(text: str, level: str = "INFO"):
    ts = QDateTime.currentDateTime().toString("HH:mm:ss")
    full = f"[{ts}] [{level}] {text}"

    # 1) Console/檔案：保留你原本行為
    if DEBUG_MODE or level in ("ERROR", "WARNING"):
        try:
            print(full)
        except Exception:
            # 防止編碼問題在 EXE 掛掉
            try:
                print(full.encode("utf-8", "ignore").decode("utf-8", "ignore"))
            except Exception:
                pass
        try:
            with open("log.txt", "a", encoding="utf-8") as f:
                f.write(full + "\n")
        except Exception:
            pass

    # 2) GUI：用訊號丟回主執行緒；未就緒先緩存
    if DEBUG_MODE or level in ("ERROR", "WARNING"):
        if _log_box is None or _log_bus is None:
            _buffered_logs.append(full)
        else:
            _log_bus.pushed.emit(full)


def resource_path(relative_path):
    """讓開發時與 PyInstaller 打包後都能正確抓到資源檔案"""
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.abspath(relative_path)

