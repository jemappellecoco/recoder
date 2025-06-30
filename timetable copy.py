import sys
import json
import socket
from datetime import datetime
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QGraphicsScene, QGraphicsView,
    QGraphicsRectItem, QGraphicsSimpleTextItem, QPushButton,
    QDateEdit, QLabel, QInputDialog
)
from PySide6.QtCore import Qt, QDate, QTimer
from PySide6.QtGui import QBrush, QColor, QPainter, QFont


class TimeBlock(QGraphicsRectItem):
    HANDLE_WIDTH = 6

    def __init__(self, start_date: QDate, track_index, start_hour, duration_hours=4, label="節目", encoder_name="Bak4-1"):
        super().__init__(0, 0, duration_hours * 20, 80)
        self.start_date = start_date
        self.track_index = track_index
        self.start_hour = start_hour
        self.duration_hours = duration_hours
        self.label = label
        self.encoder_name = encoder_name
        self.status = "等待中"

        self.setBrush(QBrush(QColor(100, 150, 255, 180)))
        self.setFlag(QGraphicsRectItem.ItemIsMovable, True)
        self.setFlag(QGraphicsRectItem.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)

        self.text = QGraphicsSimpleTextItem("", self)
        self.status_text = QGraphicsSimpleTextItem("", self)
        self.text.setFont(QFont("Arial", 10, QFont.Bold))
        self.status_text.setFont(QFont("Arial", 8))
        QTimer.singleShot(0, self.update_text_position)

        self.left_handle = QGraphicsRectItem(0, 0, self.HANDLE_WIDTH, 80, self)
        self.right_handle = QGraphicsRectItem(self.rect().width() - self.HANDLE_WIDTH, 0, self.HANDLE_WIDTH, 80, self)
        for handle in (self.left_handle, self.right_handle):
            handle.setBrush(QBrush(QColor(80, 80, 80)))
            handle.setCursor(Qt.SizeHorCursor)
            handle.setVisible(False)
        self.dragging_handle = None

    def update_text_position(self):
        self.text.setText(self.format_text())
        self.text.setPos(4, 2)
        self.status_text.setText(self.status)
        self.status_text.setBrush(QColor("black"))
        self.status_text.setPos(4, 40)

    def format_text(self):
        def fmt(h): return f"{int(h):02d}:{int((h % 1) * 60):02d}"
        end = self.start_hour + self.duration_hours
        end_fmt = f"{fmt(end % 24)} (+{int(end // 24)})" if end >= 24 else fmt(end)
        return f"{self.label}\n{fmt(self.start_hour)} - {end_fmt}"

    def hoverEnterEvent(self, event):
        self.left_handle.setVisible(True)
        self.right_handle.setVisible(True)
        self.setCursor(Qt.PointingHandCursor)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.left_handle.setVisible(False)
        self.right_handle.setVisible(False)
        self.setCursor(Qt.ArrowCursor)
        super().hoverLeaveEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.pos().x() < 40:
            self.send_start_command()
        elif event.pos().x() > self.rect().width() - 40:
            self.send_stop_command()

    def send_command(self, cmd):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect(("192.168.30.228", 32108))
                s.sendall((cmd + "\r\n").encode("cp950"))
                return s.recv(1024).decode("cp950", errors="replace").strip()
        except Exception as e:
            return f"❌ {e}"

    def send_start_command(self):
        filename = self.label.replace(" ", "_")
        date_folder = self.start_date.toString("MM.dd.yyyy")
        date_prefix = self.start_date.toString("MMdd")
        path = f'{date_folder}\\{date_prefix}_{filename}'

        self.set_status("🔄 傳送中...", "blue")
        res1 = self.send_command(f'Setfile "{self.encoder_name}" 1 {path}')
        res2 = self.send_command(f'Start "{self.encoder_name}" 1')
        if "OK" in res1 and "OK" in res2:
            self.set_status("✅ 錄影中", "green")
        else:
            self.set_status(f"❌ 錯誤", "red")

    def send_stop_command(self):
        self.set_status("🔄 傳送中...", "blue")
        res = self.send_command(f'Stop "{self.encoder_name}" 1')
        if "OK" in res:
            self.set_status("⏹ 已停止", "gray")
        else:
            self.set_status("❌ 停止失敗", "red")

    def set_status(self, text, color="black"):
        self.status = text
        self.status_text.setText(text)
        self.status_text.setBrush(QColor(color))
        QTimer.singleShot(0, self.update_text_position)

    def update_geometry(self, base_date: QDate):
        offset = base_date.daysTo(self.start_date)
        width = self.duration_hours * 20
        self.setRect(0, 0, width, 80)
        self.setPos(offset * (24 * 20 + 20) + 20 + self.start_hour * 20, self.track_index * 100)
        self.right_handle.setRect(width - self.HANDLE_WIDTH, 0, self.HANDLE_WIDTH, 80)
        QTimer.singleShot(0, self.update_text_position)

    def mousePressEvent(self, event):
        if self.left_handle.contains(event.pos()):
            self.dragging_handle = 'left'
        elif self.right_handle.contains(event.pos()):
            self.dragging_handle = 'right'
        else:
            self.dragging_handle = None
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        parent_view = self.scene().parent()
        if self.dragging_handle == 'right':
            new_width = max(20, event.pos().x())
            new_duration = round(new_width / 20, 2)
            if not parent_view.is_overlap(self.start_date, self.track_index, self.start_hour, new_duration, exclude_label=self.label):
                self.duration_hours = new_duration
                self.update_geometry(parent_view.base_date)
        elif self.dragging_handle == 'left':
            diff = min(event.pos().x(), self.rect().width() - 20)
            shift = round(diff / 20, 2)
            new_start = self.start_hour + shift
            new_duration = self.duration_hours - shift
            if new_duration >= 1 and not parent_view.is_overlap(self.start_date, self.track_index, new_start, new_duration, exclude_label=self.label):
                self.start_hour = new_start
                self.duration_hours = new_duration
                self.update_geometry(parent_view.base_date)
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.dragging_handle = None
        new_x, new_y = self.x(), self.y()
        day_width = 24 * 20 + 20
        hour_pixel = max(0, new_x % day_width - 20)
        new_date = self.scene().parent().base_date.addDays(int(new_x // day_width))
        new_hour = round(hour_pixel / 20, 2)
        new_track = int(new_y // 100)
        parent_view = self.scene().parent()
        if parent_view.is_overlap(new_date, new_track, new_hour, self.duration_hours, exclude_label=self.label):
            print("❌ 移動後會重疊，還原原位")
            self.update_geometry(parent_view.base_date)
            return
        self.start_date = new_date
        self.start_hour = new_hour
        self.track_index = new_track
        self.update_geometry(parent_view.base_date)
        for b in parent_view.block_data:
            if b["label"] == self.label:
                b.update({
                    "qdate": self.start_date,
                    "track_index": self.track_index,
                    "start_hour": self.start_hour,
                    "duration": self.duration_hours
                })
                break
        parent_view.save_schedule()
        super().mouseReleaseEvent(event)


class ScheduleView(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.blocks = []
        self.block_data = []
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.days = 7
        self.tracks = 8
        self.hour_width = 20
        self.day_width = 24 * self.hour_width + 20
        self.base_date = QDate.currentDate()
        self.setSceneRect(0, -40, self.days * self.day_width + 100, self.tracks * 100 + 80)
        self.setRenderHint(QPainter.Antialiasing)
        self.draw_grid()
        self.load_schedule()

    def draw_grid(self):
        self.scene.clear()
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
            label = self.scene.addText(f"節目 {track + 1}")
            label.setFont(QFont("Arial", 9))
            label.setPos(-60, y + 30)

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
                    data["start_hour"], data["duration"], data["label"],
                    encoder_name=data.get("encoder", "Bak4-1")
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
                    return True
        return False

    def add_time_block(self, qdate: QDate, track_index, start_hour, duration=4, label="節目", encoder="Bak4-1"):
        self.block_data.append({
            "qdate": qdate,
            "track_index": track_index,
            "start_hour": start_hour,
            "duration": duration,
            "label": label,
            "encoder": encoder
        })
        self.draw_blocks()
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
                        "encoder": b.get("encoder", "Bak4-1")
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
                        "encoder": b.get("encoder", "Bak4-1")
                    } for b in raw
                ]
            self.draw_blocks()
            print("📂 已載入排程 schedule.json")
        except FileNotFoundError:
            print("🕘 無排程檔，略過載入。")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("橫向錄影時間表（支援錄影控制）")
        self.setGeometry(100, 100, 1600, 800)
        self.view = ScheduleView()
        self.setCentralWidget(self.view)

        self.add_button = QPushButton("新增排程", self)
        self.add_button.resize(100, 30)
        self.add_button.move(1480, 740)
        self.add_button.clicked.connect(self.add_new_block)

        self.date_label = QLabel("起始日期：", self)
        self.date_label.move(1280, 744)

        self.date_picker = QDateEdit(QDate.currentDate(), self)
        self.date_picker.setCalendarPopup(True)
        self.date_picker.move(1350, 740)
        self.date_picker.dateChanged.connect(self.update_start_date)

    def add_new_block(self):
        text, ok = QInputDialog.getText(self, "節目名稱", "請輸入節目名稱：")
        if ok and text:
            new_date = self.view.base_date.addDays(1)
            encoder = "Bak4-1" if len(self.view.block_data) % 2 == 0 else "Bak4-2"
            self.view.add_time_block(qdate=new_date, track_index=1, start_hour=9, duration=4, label=text, encoder=encoder)

    def update_start_date(self, qdate):
        self.view.set_start_date(qdate)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
