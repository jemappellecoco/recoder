from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsSimpleTextItem
from PySide6.QtCore import Qt, QTimer, QDate
from PySide6.QtGui import QBrush, QColor, QFont


class TimeBlock(QGraphicsRectItem):
    HANDLE_WIDTH = 6

    def __init__(self, start_date: QDate, track_index, start_hour, duration_hours=4, label="節目名稱"):
        super().__init__(0, 0, duration_hours * 20, 80)
        self.start_date = start_date
        self.track_index = track_index
        self.start_hour = start_hour
        self.duration_hours = duration_hours
        self.label = label
        self.status = "等待中"

        self.setBrush(QBrush(QColor(100, 150, 255, 180)))
        self.setFlag(QGraphicsRectItem.ItemIsMovable, True)
        self.setFlag(QGraphicsRectItem.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)

        self.text = QGraphicsSimpleTextItem("", self)
        self.status_text = QGraphicsSimpleTextItem(self.status, self)
        self.text.setFont(QFont("Arial", 10, QFont.Bold))
        self.status_text.setFont(QFont("Arial", 9))
        self.status_text.setBrush(Qt.black)
        self.status_text.setPos(10, 45)

        QTimer.singleShot(0, self.update_text_position)

        self.left_handle = QGraphicsRectItem(0, 0, self.HANDLE_WIDTH, 80, self)
        self.right_handle = QGraphicsRectItem(self.rect().width() - self.HANDLE_WIDTH, 0, self.HANDLE_WIDTH, 80, self)
        for handle in (self.left_handle, self.right_handle):
            handle.setBrush(QBrush(QColor(80, 80, 80)))
            handle.setCursor(Qt.SizeHorCursor)
            handle.setVisible(False)
        self.dragging_handle = None

    def hoverEnterEvent(self, event):
        self.left_handle.setVisible(True)
        self.right_handle.setVisible(True)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.left_handle.setVisible(False)
        self.right_handle.setVisible(False)
        super().hoverLeaveEvent(event)

    def update_text_position(self):
        try:
            self.text.setText(self.format_text())
            self.text.setPos(4, 2)
            self.status_text.setText(self.status)
        except RuntimeError:
            pass  # 防止物件被刪除時出錯

    def format_text(self):
        def fmt(h): return f"{int(h):02d}:{int((h % 1) * 60):02d}"
        end = self.start_hour + self.duration_hours
        end_fmt = f"{fmt(end % 24)} (+{int(end // 24)})" if end >= 24 else fmt(end)
        return f"{self.label}\n{fmt(self.start_hour)} - {end_fmt}"

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
        scene_width = self.scene().sceneRect().width()

        if self.dragging_handle == 'right':
            new_width = max(20, event.pos().x())
            new_right_x = self.scenePos().x() + new_width
            if new_right_x > scene_width:
                return
            new_duration = round(new_width / 20, 2)
            if not parent_view.is_overlap(self.start_date, self.track_index, self.start_hour, new_duration, exclude_label=self.label):
                self.duration_hours = new_duration
                self.update_geometry(parent_view.base_date)

        elif self.dragging_handle == 'left':
            diff = min(event.pos().x(), self.rect().width() - 20)
            shift = round(diff / 20, 2)
            new_start_hour = self.start_hour + shift
            new_duration = self.duration_hours - shift
            if new_duration >= 1:
                new_x = self.scenePos().x() + shift * 20
                if new_x < 0:
                    return
                if not parent_view.is_overlap(self.start_date, self.track_index, new_start_hour, new_duration, exclude_label=self.label):
                    self.start_hour = new_start_hour
                    self.duration_hours = new_duration
                    self.update_geometry(parent_view.base_date)
        else:
            # 拖曳整個 block：暫時記錄原位置，不直接移動
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.dragging_handle = None
        parent_view = self.scene().parent()
        scene_width = self.scene().sceneRect().width()
        scene_height = self.scene().sceneRect().height()

        new_x, new_y = self.x(), self.y()
        day_width = 24 * 20 + 20
        hour_pixel = max(0, new_x % day_width - 20)
        new_date = parent_view.base_date.addDays(int(new_x // day_width))
        new_hour = round(hour_pixel / 20, 2)
        new_track = int(new_y // 100)
        max_track = len(parent_view.encoder_names)

        # 四向邊界限制
        if new_hour < 0 or new_x < 0 or self.x() + self.rect().width() > scene_width or new_track < 0 or new_track >= max_track:
            print("❌ 拖曳越界，還原")
            self.update_geometry(parent_view.base_date)
            return

        if parent_view.is_overlap(new_date, new_track, new_hour, self.duration_hours, exclude_label=self.label):
            print("❌ 拖曳後重疊，還原")
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
