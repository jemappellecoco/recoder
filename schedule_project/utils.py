# utils.py
import sys
import os
from PySide6.QtCore import QDateTime
from PySide6.QtGui import QTextCursor
_log_box = None
_buffered_logs = []
MAX_LOG_LINES = 500
DEBUG_MODE = True
def set_log_box(widget):
    global _log_box
    _log_box = widget

    # ✅ 把之前的 log 全部補上
    for text in _buffered_logs:
        _log_box.append(text)
    _buffered_logs.clear()
    _log_box.moveCursor(QTextCursor.End)


def is_frozen():
    return getattr(sys, 'frozen', False)

def log(text: str, level="INFO"):
    timestamp = QDateTime.currentDateTime().toString("HH:mm:ss")
    full_text = f"[{timestamp}] [{level}] {text}"

    if DEBUG_MODE or level in ("ERROR", "WARNING"):
        print(full_text)
        try:
            with open("log.txt", "a", encoding="utf-8") as f:
                f.write(full_text + "\n")
        except:
            pass

    if _log_box and (DEBUG_MODE or level in ("ERROR", "WARNING")):
        _log_box.append(full_text)
        _log_box.moveCursor(QTextCursor.End)
        doc = _log_box.document()
        while doc.blockCount() > MAX_LOG_LINES:
            doc.removeBlock(doc.firstBlock())

def resource_path(relative_path):
    """讓開發時與 PyInstaller 打包後都能正確抓到資源檔案"""
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.abspath(relative_path)
