import uuid
from PySide6.QtWidgets import QMessageBox
from collections import deque
from uuid import uuid4
from utils import log
class BlockManager:
    def __init__(self, schedule_view):
        self.view = schedule_view
        self.deleted_stack = deque()
    def add_block_with_unique_label(self, base_label, track_index=0, start_hour=9, duration=4, encoder_name=None, qdate=None, block_id=None):
        label = base_label
        # existing_labels = [b["label"] for b in self.view.block_data]
        # i = 1
        # while label in existing_labels:
        #     label = f"{base_label}_{i}"
        #     i += 1

        if qdate is None:
            qdate = self.view.base_date

        if block_id is None:
            block_id = str(uuid4()) 
        # end_hour = round(start_hour + duration, 4)
        # end_qdate = qdate.addDays(1) if end_hour >= 24 else qdate
        log("✅ 呼叫 add_time_block")
        self.view.add_time_block(
            qdate=qdate,
            track_index=track_index,
            start_hour=start_hour,
            duration=duration,
            label=label,
            encoder_name=encoder_name,
            block_id=block_id 
        )
        log(f"✅ 已加入 block: {label}")    
        
        # self.view.draw_blocks()
        self.view.save_schedule()

    def get_block_by_id(self, block_id):
        for b in self.view.block_data:
            if b.get("id") == block_id:
                return b
        return None

    def remove_block_by_id(self, block_id):
        # 從畫面上移除
        for item in list(self.view.blocks):
            if hasattr(item, "block_id") and item.block_id == block_id:
                self.view.scene.removeItem(item)
                self.view.blocks.remove(item)
                break
         # ✅ 從 scene 中額外刪除可能殘留的圖片（萬一之前沒 bind）
        for item in list(self.view.scene.items()):
            if hasattr(item, "block_id") and item.block_id == block_id:
                self.view.scene.removeItem(item)
        # 找出要刪除的 block 資料
        deleted_block = None
        for b in self.view.block_data:
            if b.get("id") == block_id:
                deleted_block = b
                break

        # 如果有找到就推進 stack
        if deleted_block:
            self.deleted_stack.append(deleted_block)

        # 從 block_data 移除
        self.view.block_data = [b for b in self.view.block_data if b.get("id") != block_id]
        self.view.save_schedule()
        log(f"🗑️ 已刪除 block：{block_id}")

    def undo_last_delete(self):
        if not self.deleted_stack:
            log("⚠️ 沒有可復原的排程")
            QMessageBox.information(None, "⚠️ 無法復原", "目前沒有可以復原的排程。")
            return

        b = self.deleted_stack.pop()
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
        log(f"↩️ 已復原 block：{b['label']}")
        QMessageBox.information(None, "✅ 復原成功", f"已復原節目：{b['label']}")