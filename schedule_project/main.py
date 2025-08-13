import sys
import os
import shutil
import traceback
from PySide6.QtWidgets import QApplication
from ui_main_window import MainWindow
from utils import resource_path, log,log_exception

# 🧯 全域例外處理（會寫入 error.log，避免 silent crash）
def except_hook(exctype, value, tb):
    tb_text = "".join(traceback.format_exception(exctype, value, tb))
    try:
        with open("error.log", "w", encoding="utf-8") as f:
            f.write(tb_text)
    except Exception as e:
        log_exception(e, "❌ 寫入 error.log 失敗")

    log(f"❌ 發生例外：\n{tb_text}", level="ERROR")
    sys.exit(1)

sys.excepthook = except_hook

if __name__ == "__main__":
    # ✅ 若沒有 schedule.json，自動從 resource 複製
    try:
        if not os.path.exists("schedule.json"):
            shutil.copy(resource_path("schedule.json"), "schedule.json")
            log("📄 已建立預設排程檔案 schedule.json")
    except Exception as e:
        log_exception(f"❌ 建立預設 schedule.json 失敗：{e}")

    try:
        if not os.path.exists("config.json"):
            shutil.copy(resource_path("config.json"), "config.json")
            log("📄 已建立預設設定檔 config.json")
    except Exception as e:
        log_exception(f"❌ 建立預設 config.json 失敗：{e}")

    # ✅ 確保 QApplication 建立成功
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
