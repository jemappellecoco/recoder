import sys, traceback

import os
import shutil
import traceback
from PySide6.QtWidgets import QApplication
from ui_main_window import MainWindow
from utils import resource_path, log

# 🧯 全域例外處理（會寫入 error.log，避免 silent crash）
def except_hook(exctype, value, tb):
    tb_text = "".join(traceback.format_exception(exctype, value, tb))
    try:
        with open("error.log", "a", encoding="utf-8") as f:  # ✅ 用附加模式
            f.write("\n==== 未捕捉例外 ====\n")
            f.write(tb_text)
            f.write("\n")
    except Exception as e:
        log(e, "❌ 寫入 error.log 失敗",level="ERROR")

    # ✅ 確保 GUI 也看到
    log(f"❌ 發生例外：\n{tb_text}", level="ERROR")

    # ❌ 先不要強制關閉程式

sys.excepthook = except_hook

if __name__ == "__main__":
    # ✅ 若沒有 schedule.json，自動從 resource 複製
    try:
        if not os.path.exists("schedule.json"):
            shutil.copy(resource_path("schedule.json"), "schedule.json")
            log("📄 已建立預設排程檔案 schedule.json")
    except Exception as e:
        log(f"❌ 建立預設 schedule.json 失敗：{e}",level="ERROR")

    try:
        if not os.path.exists("config.json"):
            shutil.copy(resource_path("config.json"), "config.json")
            log("📄 已建立預設設定檔 config.json")
    except Exception as e:
        log(f"❌ 建立預設 config.json 失敗：{e}",level="ERROR")

    # ✅ 確保 QApplication 建立成功
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
