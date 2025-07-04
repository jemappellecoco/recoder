# path_manager.py
import os
import json
from datetime import datetime
from PySide6.QtCore import QDate
CONFIG_FILE = "config.json"

class PathManager:
    def __init__(self):
        self.record_root = self.load_record_root()

    
    def get_full_path(self, encoder_name, filename):
        date_folder = datetime.today().strftime("%m.%d.%Y")
        date_prefix = datetime.today().strftime("%m%d")
        return os.path.abspath(os.path.join(self.record_root, date_folder, f"{date_prefix}_{filename}"))
    def save_record_root(self, path):
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump({'record_root': path}, f)
        except Exception as e:
            print("❌ 無法儲存 config:", e)

    def load_record_root(self):
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('record_root', 'E:/')
        except Exception as e:
            print("❌ 無法讀取 config:", e)
        return 'E:/'
    def get_image_path(self, block_id: str, qdate: QDate):
            
        if not isinstance(block_id, str):
            raise ValueError("block_id 必須是字串（UUID）")
        if not isinstance(qdate, QDate):
            raise ValueError("qdate 必須是 QDate 物件")

        date_folder = qdate.toString("MM.dd.yyyy")
        return os.path.join(self.record_root, date_folder, "img", f"{block_id}.png")