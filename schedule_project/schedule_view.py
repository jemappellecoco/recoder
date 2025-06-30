from PySide6.QtWidgets import QGraphicsView, QGraphicsScene
from PySide6.QtCore import Qt, QDate, QTimer
from PySide6.QtGui import QPainter, QFont
from time_block import TimeBlock
import json

class ScheduleView(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.blocks = []
        self.block_data = []
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
        for item in self.scene.items():
            if isinstance(item, TimeBlock):
                self.scene.removeItem(item)
        self.blocks = []
        start_range = self.base_date
        end_range = self.base_date.addDays(self.days)
        for data in self.block_data:
            block_start = data["qdate"]
            block_end = block_start.addDays(int((data["start_hour"] + data["duration"]) // 24))
            if block_start < end_range and block_end >= start_range:
                block = TimeBlock(
                    data["qdate"], data["track_index"],
                    data["start_hour"], data["duration"], data["label"]
                )
                self.scene.addItem(block)
                block.update_geometry(self.base_date)
                self.blocks.append(block)

    def is_overlap(self, qdate, track_index, start_hour, duration, exclude_label=None):
        for block in self.block_data:
            if block["qdate"] == qdate and block["track_index"] == track_index:
                if exclude_label and block["label"] == exclude_label:
                    continue
                exist_start = block["start_hour"]
                exist_end = exist_start + block["duration"]
                new_end = start_hour + duration
                if not (new_end <= exist_start or start_hour >= exist_end):
                    print(f"🔴 重疊：{exclude_label=} 跟 {block['label']} 撞到")
                    return True
        return False


    def add_time_block(self, qdate: QDate, track_index, start_hour, duration=4, label="節目"):
        self.block_data.append({
            "qdate": qdate,
            "track_index": track_index,
            "start_hour": start_hour,
            "duration": duration,
            "label": label
        })
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
                        "label": b["label"]
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
                        "label": b["label"]
                    } for b in raw
                ]
            self.draw_blocks()
            print("📂 已載入節目排程 schedule.json")
        except FileNotFoundError:
            print("🕘 無 schedule.json 檔案，自動跳過載入。")
