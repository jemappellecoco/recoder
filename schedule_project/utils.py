# utils.py
import sys
import os
from PySide6.QtCore import QDateTime
from PySide6.QtGui import QTextCursor
from PySide6.QtCore import QTimer
import traceback
_log_box = None
_buffered_logs = []
MAX_LOG_LINES = 500
DEBUG_MODE = True
def log_exception(e, note=""):
    tb = traceback.format_exc()
    if note:
        log(f"❌ {note}\n{tb}", level="ERROR")
    else:
        log(f"❌ Exception:\n{tb}", level="ERROR")
def set_log_box(widget):
    global _log_box
    _log_box = widget

    for text in _buffered_logs:
        _log_box.append(text)
    _buffered_logs.clear()

    try:
        _log_box.moveCursor(QTextCursor.End)
    except Exception as e:
        print(f"[log set_cursor error] {e}")


def is_frozen():
    return getattr(sys, 'frozen', False)

def _append_log_safely(text):
    if _log_box:
        lines = _log_box.toPlainText().splitlines()
        lines.append(text)

        # ✅ 限制最大行數，重新設定文字
        if len(lines) > MAX_LOG_LINES:
            lines = lines[-MAX_LOG_LINES:]
            _log_box.setPlainText("\n".join(lines))
        else:
            _log_box.append(text)

        _log_box.moveCursor(QTextCursor.End)

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
        # ✅ 安全地轉到主執行緒
        QTimer.singleShot(0, lambda: _append_log_safely(full_text))


def resource_path(relative_path):
    """讓開發時與 PyInstaller 打包後都能正確抓到資源檔案"""
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.abspath(relative_path)
