from PySide6.QtWidgets import QGraphicsView, QGraphicsScene
from PySide6.QtCore import Qt, QDate, QTimer,QDateTime, QTime
from PySide6.QtGui import QPainter, QFont
from time_block import TimeBlock
import json
import os
from path_manager import PathManager 
class ScheduleView(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.blocks = []
        self.block_data = []
        self.path_manager = None
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.days = 7
        self.hour_width = 20
        self.day_width = 24 * self.hour_width + 20
        self.base_date = QDate.currentDate()
        self.encoder_names = []
        self.encoder_status = {}
        self.setSceneRect(-120, -40, self.days * self.day_width + 150, 1000)
        
        self.setRenderHint(QPainter.Antialiasing)
        self.schedule_timer = QTimer()
        self.schedule_timer.start(1000)
        self.load_schedule()
        self.path_manager = PathManager()
    def draw_grid(self):
        print("🎯 draw_grid encoder_names:", self.encoder_names)

        self.scene.clear()
        self.tracks = len(self.encoder_names)

        for day in range(self.days):
            for hour in range(24):
                x = day * self.day_width + hour * self.hour_width
                label = self.scene.addText(f"{hour:02d}")
                label.setFont(QFont("Arial", 8))
                label.setPos(x + 2, -35)
                self.scene.addLine(x, 0, x, self.tracks * 100, Qt.DotLine)

        for day in range(self.days):
            x = day * self.day_width
            self.scene.addRect(x, 0, self.day_width, self.tracks * 100)
            label = self.scene.addText(self.base_date.addDays(day).toString("MM/dd (ddd)"))
            label.setFont(QFont("Arial", 10, QFont.Bold))
            label.setPos(x + 2, -20)

        for track in range(self.tracks):
            y = track * 100
            self.scene.addLine(0, y, self.days * self.day_width, y)

            if track < len(self.encoder_names):
                encoder_name = self.encoder_names[track]
                status_label = self.encoder_status.get(encoder_name)
                status_text = status_label.text() if status_label else "未知"
                full_label = f"{encoder_name}\n狀態：{status_text}"
            else:
                full_label = f"未指定\n--"

            label = self.scene.addText(full_label)
            label.setFont(QFont("Arial", 9))
            label.setPos(-95, y + 15)

        self.draw_blocks()
        
    def draw_blocks(self):
            # 建立舊 block 映射（label → block）以便繼承狀態
        old_block_map = {block.label: block for block in self.blocks}

        # 清除舊的 TimeBlock（但不刪除其他 scene 內容）
        for item in self.scene.items():
            if isinstance(item, TimeBlock):
                item.safe_delete()

        self.blocks = []

        start_range = self.base_date
        end_range = self.base_date.addDays(self.days)

        for data in self.block_data:
            block_start = data["qdate"]
            total_hours = data["start_hour"] + data["duration"]
            extra_days = int(total_hours // 24)
            block_end = block_start.addDays(extra_days)

            if block_end >= start_range and block_start <= end_range:
                block = TimeBlock(
                    data["qdate"],
                    data["track_index"],
                    data["start_hour"],
                    data["duration"],
                    data["label"],
                    block_id=data.get("id")
                )
                block.path_manager = self.path_manager
                # 先加到 scene 才能安全操作 scene() 相關功能
                self.scene.addItem(block)
                block.update_geometry(self.base_date)

                # 從舊 block 繼承狀態與圖片
                old_block = old_block_map.get(data["label"])
                if old_block:
                    block.status = old_block.status
                    if hasattr(old_block, "status_text") and old_block.status_text:
                        block.status_text.setText(old_block.status)
                    if hasattr(old_block, "image_item") and old_block.image_item:
                        block.image_item = old_block.image_item
                        block.image_item.setParentItem(block)

                # 自動載入縮圖
                if block.block_id and hasattr(self, "record_root"):
                    img_folder = os.path.join(self.record_root, block.start_date.toString("MM.dd.yyyy"), "img")
                    block.load_preview_images(img_folder)

                self.blocks.append(block)

        # 更新 ScheduleRunner 的 block 清單
        if hasattr(self, "runner"):
            self.runner.blocks = self.blocks





    def is_overlap(self, qdate, track_index, start_hour, duration, exclude_label=None):
        from PySide6.QtCore import QDateTime, QTime

        new_start_dt = QDateTime(qdate, QTime(int(start_hour), int((start_hour % 1) * 60)))
        new_end_dt = new_start_dt.addSecs(int(duration * 3600))

        for block in self.block_data:
            
            if exclude_label and block["label"] == exclude_label:
                continue

            # 🟡 正確取得 block 起始時間
            b_qdate = block["qdate"]
            if isinstance(b_qdate, str):
                b_qdate = QDate.fromString(b_qdate, "yyyy-MM-dd")

            b_start_hour = float(block["start_hour"])
            b_duration = float(block["duration"])

            b_start_dt = QDateTime(b_qdate, QTime(int(b_start_hour), int((b_start_hour % 1) * 60)))
            b_end_dt = b_start_dt.addSecs(int(b_duration * 3600))

            # 🔴 真正的重疊邏輯（只要有交集就算）
            if new_start_dt < b_end_dt and new_end_dt > b_start_dt:
                print(f"🔴 重疊偵測：{exclude_label=} 撞到 {block['label']}")
                return True

        return False
    

    def add_time_block(self, qdate: QDate, track_index, start_hour, duration=4, label="節目", encoder_name=None, block_id=None):
        if isinstance(qdate, str):
            qdate = QDate.fromString(qdate, "yyyy-MM-dd")

        block = {
            "qdate": qdate,
            "track_index": track_index,
            "start_hour": start_hour,
            "duration": duration,
            "label": label
        }
        # block.path_manager = self.path_manager
        if encoder_name is not None:
            block["encoder_name"] = encoder_name
        if block_id:
            block["id"] = block_id

        self.block_data.append(block)
        self.draw_blocks()
        
    def remove_block_by_label(self, label):
        for item in self.blocks:
            if item.label == label:
                self.scene.removeItem(item)
                self.blocks.remove(item)
                break
        self.block_data = [b for b in self.block_data if b["label"] != label]
        self.save_schedule()
    def set_start_date(self, qdate):
        self.base_date = qdate
        self.draw_grid()

    def save_schedule(self, filename="schedule.json"):
        try:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump([
                    {
                        "qdate": b["qdate"].toString("yyyy-MM-dd"),
                        "track_index": b["track_index"],
                        "start_hour": b["start_hour"],
                        "duration": b["duration"],
                        "label": b["label"],
                        "id": b.get("id"),  # ✅ 儲存 block_id
                        "encoder_name": b.get("encoder_name")  # ✅ 若未來要還原 encoder 名稱
                    } for b in self.block_data
                ], f, ensure_ascii=False, indent=2)
            print("✅ 已儲存節目排程 schedule.json")
        except Exception as e:
            print(f"❌ 儲存失敗: {e}")


    def load_schedule(self, filename="schedule.json"):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                raw = json.load(f)
                self.block_data = [
                    {
                        "qdate": QDate.fromString(b["qdate"], "yyyy-MM-dd"),
                        "track_index": b["track_index"],
                        "start_hour": b["start_hour"],
                        "duration": b["duration"],
                        "label": b["label"],
                        "id": b.get("id"),
                        "encoder_name": b.get("encoder_name")
                    } for b in raw
                ]
            self.draw_blocks()
            print("📂 已載入節目排程 schedule.json")
        except FileNotFoundError:
            print("🕘 無 schedule.json 檔案，自動跳過載入。")
