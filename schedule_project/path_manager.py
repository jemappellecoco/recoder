# path_manager.py
import os
import json
from datetime import datetime
from PySide6.QtCore import QDate

from utils import resource_path
from utils import log

CONFIG_FILE = "config.json"


class PathManager:
    def __init__(self):
        self.record_root, self.snapshot_root = self.load_paths()

    def get_full_path(self, encoder_name, filename):
        date_folder = datetime.today().strftime("%m.%d.%Y")
        date_prefix = datetime.today().strftime("%m%d")
        return os.path.abspath(os.path.join(self.record_root, date_folder, f"{date_prefix}_{filename}"))

    def save_record_root(self, path):
        try:
            data = {}
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
            data["record_root"] = path
            data.setdefault("snapshot_root", data.get("record_root", path))
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log("❌ 無法儲存 config:", e)

    def save_snapshot_root(self, path):
        try:
            data = {}
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
            data["snapshot_root"] = path
            data.setdefault("record_root", self.record_root)
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log("❌ 無法儲存 config:", e)

    def load_paths(self):
        record_root = self.default_record_root()
        snapshot_root = record_root
        try:
            data = {}
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
            else:
                path = resource_path(CONFIG_FILE)
                if os.path.exists(path):
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
            record_root = data.get("record_root", record_root)
            snapshot_root = data.get("snapshot_root", record_root)
        except Exception as e:
            log(f"❌ 無法讀取 config: {e}")
        return record_root, snapshot_root

    def default_record_root(self):
        return os.path.join(os.getcwd(), "Recordings")

    def get_image_path(self, block_id: str, qdate: QDate):
        if not isinstance(block_id, str):
            raise ValueError("block_id 必須是字串（UUID）")
        if not isinstance(qdate, QDate):
            raise ValueError("qdate 必須是 QDate 物件")

        date_folder = qdate.toString("MM.dd.yyyy")
        return os.path.join(self.record_root, date_folder, "img", f"{block_id}.png")
