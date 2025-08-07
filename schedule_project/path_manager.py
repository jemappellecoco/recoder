# path_manager.py
import os
import json
from datetime import datetime
from PySide6.QtCore import QDate
CONFIG_FILE = "config.json"
from utils import resource_path 
from utils import log

class PathManager:
    def __init__(self):
        self.record_root = self.load_record_root()
        self.preview_root = self.load_preview_root()

    
    def get_full_path(self, encoder_name, filename):
        date_folder = datetime.today().strftime("%m.%d.%Y")
        date_prefix = datetime.today().strftime("%m%d")
        return os.path.abspath(os.path.join(self.record_root, date_folder, f"{date_prefix}_{filename}"))
    def _save_config(self, data):
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f)
        except Exception as e:
            log("❌ 無法儲存 config:", e)

    def save_record_root(self, path):
        try:
            data = {}
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            data['record_root'] = path
            data.setdefault('preview_root', self.preview_root)
            self._save_config(data)
        except Exception as e:
            log("❌ 無法儲存 config:", e)

    def save_preview_root(self, path):
        try:
            data = {}
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            data['preview_root'] = path
            data.setdefault('record_root', self.record_root)
            self._save_config(data)
        except Exception as e:
            log("❌ 無法儲存 config:", e)
    def load_record_root(self):
        try:
        # 優先使用外部寫入的 config.json
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('record_root', self.default_record_root())

            # fallback: 使用打包進 exe 的 config.json（只讀）
            path = resource_path(CONFIG_FILE)
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('record_root', self.default_record_root())

        except Exception as e:
            log(f"❌ 無法讀取 config: {e}")
        return self.default_record_root()

    def load_preview_root(self):
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('preview_root', self.default_preview_root())

            path = resource_path(CONFIG_FILE)
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('preview_root', self.default_preview_root())

        except Exception as e:
            log(f"❌ 無法讀取 config: {e}")
        return self.default_preview_root()

    def default_record_root(self):
        return os.path.join(os.getcwd(), "Recordings")

    def default_preview_root(self):
        return os.path.join(self.default_record_root(), "preview")

    @property
    def snapshot_root(self):
        return self.preview_root
    # def load_record_root(self):
    #     try:
    #         path = resource_path(CONFIG_FILE)
    #         if os.path.exists(path):
    #             with open(path, 'r', encoding='utf-8') as f:
    #                 data = json.load(f)
    #                 return data.get('record_root', 'E:/')
    #     except Exception as e:
    #         log("❌ 無法讀取 config:", e)
    #     return 'E:/'
    def get_image_path(self, block_id: str, qdate: QDate):
            
        if not isinstance(block_id, str):
            raise ValueError("block_id 必須是字串（UUID）")
        if not isinstance(qdate, QDate):
            raise ValueError("qdate 必須是 QDate 物件")

        date_folder = qdate.toString("MM.dd.yyyy")
        return os.path.join(self.record_root, date_folder, "img", f"{block_id}.png")
