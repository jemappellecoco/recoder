import sys
import os
import shutil
from PySide6.QtWidgets import QApplication
from ui_main_window import MainWindow
from utils import resource_path, log  # ✅ 你已經有的函數

if __name__ == "__main__":
    # ✅ 若沒有 schedule.json，自動從 schedule.json 複製一份
    if not os.path.exists("schedule.json"):
        try:
            shutil.copy(resource_path("schedule.json"), "schedule.json")
            log("📄 已建立預設排程檔案 schedule.json")
        except Exception as e:
            log(f"❌ 建立預設 schedule.json 失敗：{e}")
    if not os.path.exists("config.json"):
        try:
            shutil.copy(resource_path("config.json"), "config.json")
            log("📄 已建立預設設定檔 config.json")
        except Exception as e:
            log(f"❌ 建立預設 config.json 失敗：{e}")
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    # win.showFullScreen()
    sys.exit(app.exec())