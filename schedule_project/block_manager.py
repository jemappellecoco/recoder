import uuid
from PySide6.QtWidgets import QMessageBox
class BlockManager:
    def __init__(self, schedule_view):
        self.view = schedule_view
        self.recently_deleted = None
    def add_block_with_unique_label(self, base_label, track_index=0, start_hour=9, duration=4, encoder_name=None, qdate=None):
        label = base_label
        existing_labels = [b["label"] for b in self.view.block_data]
        i = 1
        while label in existing_labels:
            label = f"{base_label}_{i}"
            i += 1

        if qdate is None:
            qdate = self.view.base_date

        block_id = str(uuid.uuid4())  # ✅ 唯一識別碼

        self.view.add_time_block(
            qdate=qdate,
            track_index=track_index,
            start_hour=start_hour,
            duration=duration,
            label=label,
            encoder_name=encoder_name,
            block_id=block_id
        )
        self.view.save_schedule()

    def get_block_by_id(self, block_id):
        for b in self.view.block_data:
            if b.get("id") == block_id:
                return b
        return None

    def remove_block_by_id(self, block_id):
        # ✅ 從畫面上移除 block
        for item in list(self.view.blocks):  # 避免迭代時刪除錯誤
            if hasattr(item, "block_id") and item.block_id == block_id:
                self.view.scene.removeItem(item)
                self.view.blocks.remove(item)
                break

        # ✅ 從 block_data 移除
        self.view.block_data = [b for b in self.view.block_data if b.get("id") != block_id]
        self.view.save_schedule()
    def remove_block_by_id(self, block_id):
        for item in list(self.view.blocks):
            if hasattr(item, "block_id") and item.block_id == block_id:
                self.view.scene.removeItem(item)
                self.view.blocks.remove(item)
                break

        for b in self.view.block_data:
            if b.get("id") == block_id:
                self.recently_deleted = b  # 👈 儲存起來方便復原
                break

        self.view.block_data = [b for b in self.view.block_data if b.get("id") != block_id]
        self.view.save_schedule()
        print(f"🗑️ 已刪除 block：{block_id}")
    def undo_last_delete(self):
        if not self.recently_deleted:
            print("⚠️ 沒有可復原的刪除記錄")
            QMessageBox.information(None, "⚠️ 無法復原", "目前沒有可以復原的排程。")
            return

        b = self.recently_deleted
        self.view.add_time_block(
            qdate=b["qdate"],
            track_index=b["track_index"],
            start_hour=b["start_hour"],
            duration=b["duration"],
            label=b["label"],
            encoder_name=b.get("encoder_name"),
            block_id=b.get("id")
        )
        self.view.save_schedule()
        print(f"↩️ 已復原刪除的 block：{b['label']}")
        QMessageBox.information(None, "✅ 復原成功", f"已復原節目：{b['label']}")  # ✅ 這行放在這裡剛剛好！
        self.recently_deleted = None