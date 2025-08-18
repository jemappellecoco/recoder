# utils.py
import sys
import os
from PySide6.QtCore import QDateTime, QObject, Signal,Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtCore import QTimer
import traceback
_log_box = None
_buffered_logs = []
MAX_LOG_LINES = 500
DEBUG_MODE = True
# 用訊號把任何執行緒的 log 丟回主執行緒處理
class _LogBus(QObject):
    pushed = Signal(str)

_log_bus = None

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
