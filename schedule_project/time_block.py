from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsSimpleTextItem,QGraphicsPixmapItem
from PySide6.QtCore import Qt, QTimer, QDate,QDateTime,QTime
from PySide6.QtGui import QBrush, QColor, QFont,QPixmap
from edit_block_dialog import EditBlockDialog
import logging
import os
logging.basicConfig(level=logging.INFO)
class TimeBlock(QGraphicsRectItem):
    HANDLE_WIDTH = 6
    BLOCK_HEIGHT = 100
    def __init__(self, start_date: QDate, track_index, start_hour, duration_hours=4, label="節目名稱", block_id=None):
    
        super().__init__(0, 0, duration_hours * 20, self.BLOCK_HEIGHT)
        self.block_id = block_id
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
        self.text.setFont(QFont("Arial", 9, QFont.Bold))
        self.status_text.setFont(QFont("Arial", 9))
        self.status_text.setBrush(Qt.black)
        # self.status_text.setPos(10, 45)
        self.status_text.setFont(QFont("Arial", 8)) 
        self.status_text.setPos(4, self.rect().height() - 18)
        QTimer.singleShot(0, self.update_text_position)

        self.left_handle = QGraphicsRectItem(0, 0, self.HANDLE_WIDTH, self.BLOCK_HEIGHT, self)
        self.right_handle = QGraphicsRectItem(self.rect().width() - self.HANDLE_WIDTH, 0, self.HANDLE_WIDTH, self.BLOCK_HEIGHT, self)
        self.drag_start_offset = None
        self.setAcceptedMouseButtons(Qt.LeftButton)
        self.setFlag(QGraphicsRectItem.ItemIsFocusable, True)

        self.preview_item = QGraphicsPixmapItem(self)
        self.preview_item.setZValue(5)
        self.preview_item.setOffset(4, self.status_text.y() + self.status_text.boundingRect().height() + 6)
        self.preview_item.setVisible(False)
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
        # ✅ 檢查主文字是否存在且仍屬於場景中
            if self.text is None or self.text.scene() is None:
                return

            # ✅ 更新上方主文字（節目名稱＋時間）
            self.text.setText(self.format_text())
            self.text.setPos(4, 2)

            # ✅ 檢查狀態文字是否存在且仍屬於場景中
            if self.status_text is None or self.status_text.scene() is None:
                return  # 避免已被刪除後仍嘗試操作造成 RuntimeError

            # ✅ 根據狀態更新下方狀態文字內容
            if self.status.startswith("狀態：⏳ 等待中"):
                self.status_text.setText(self.status)
            else:
                if self.status_text.text() != self.status:
                    self.status_text.setText(self.status)

            # ✅ 動態調整狀態文字的位置（在主文字下方）
            text_rect = self.text.boundingRect()
            self.status_text.setPos(4, text_rect.height() + 6)

        except RuntimeError as e:
           pass



    def format_text(self):
        

        start_dt = QDateTime(self.start_date, QTime(int(self.start_hour), int((self.start_hour % 1) * 60)))
        end_dt = start_dt.addSecs(int(self.duration_hours * 3600))

        start_str = start_dt.toString("MM/dd HH:mm")
        end_str = end_dt.toString("MM/dd HH:mm")

        # 📐 格式設計（清楚排版）
        return (
            f"{self.label}\n"           # 節目名稱
            f"開始 ➤ {start_str}\n"     # 起始時間
            f"結束 ➤ {end_str}"         # 結束時間
        )

    def update_geometry(self, base_date: QDate):
        day_offset = base_date.daysTo(self.start_date)
        block_x = day_offset * (24 * 20 + 20) + 20 + self.start_hour * 20
        block_width = self.duration_hours * 20

        # 計算畫布可視範圍
        min_x = 0
        max_x = 7 * (24 * 20 + 20)  # 7 天的寬度

        # 限制左邊：若 block 在左邊界外，裁掉左邊
        if block_x < min_x:
            overflow_left = min_x - block_x
            block_x = min_x
            block_width -= overflow_left

        # 限制右邊：若 block 超過右邊界，裁掉右邊
        if block_x + block_width > max_x:
            block_width = max(min(block_width, max_x - block_x), 20)

        self.setRect(0, 0, block_width, self.BLOCK_HEIGHT)
        self.setPos(block_x, self.track_index * self.BLOCK_HEIGHT)
        self.right_handle.setRect(block_width - self.HANDLE_WIDTH, 0, self.HANDLE_WIDTH, self.BLOCK_HEIGHT)

        QTimer.singleShot(0, self.update_text_position)
        

    def mousePressEvent(self, event):
        now = QDateTime.currentDateTime()
        start_dt = QDateTime(self.start_date, QTime(int(self.start_hour), int((self.start_hour % 1) * 60)))
        self.has_started = now >= start_dt  # ⏱️ 存成屬性，後面 mouseMove 也可用

        # 清除其他 block 的拖曳狀態
        for item in self.scene().items():
            if isinstance(item, TimeBlock) and item is not self:
                item.dragging_handle = None

        self.setFocus()
        self.drag_start_offset = event.pos()

        if self.left_handle.contains(event.pos()):
            if self.has_started:
                print(f"⛔ 已開始：左側不能拖動（{self.label}）")
                return
            self.dragging_handle = 'left'
            return

        elif self.right_handle.contains(event.pos()):
            self.dragging_handle = 'right'
            return

        # 整塊拖曳
        if self.has_started:
            print(f"⛔ 已開始：整塊不能移動（{self.label}）")
            return

        self.dragging_handle = None
        super().mousePressEvent(event)




    def mouseMoveEvent(self, event):
        parent_view = self.scene().parent()

        if self.dragging_handle == 'right':
            delta = event.pos().x()
            new_duration = round(max(1.0, delta / 20), 2)

            new_right_x = self.scenePos().x() + new_duration * 20
            if new_right_x <= self.scenePos().x():  # ⛔ 不可縮短（即使未開始）
                print(f"⛔ 無法將右邊往前拖（{self.label}）")
                return

            if not parent_view.is_overlap(self.start_date, self.track_index, self.start_hour, new_duration, exclude_label=self.label):
                self.duration_hours = new_duration
                self.update_geometry(parent_view.base_date)

        elif self.dragging_handle == 'left':
            if getattr(self, "has_started", False):
                return

            delta = event.pos().x()
            max_shift = self.rect().width() - 20
            shift_pixels = min(delta, max_shift)
            shift_hours = round(shift_pixels / 20, 2)

            new_start_hour = self.start_hour + shift_hours
            new_duration = self.duration_hours - shift_hours

            if new_duration >= 1:
                if not parent_view.is_overlap(self.start_date, self.track_index, new_start_hour, new_duration, exclude_label=self.label):
                    self.start_hour = new_start_hour
                    self.duration_hours = new_duration
                    self.update_geometry(parent_view.base_date)

        else:
            if getattr(self, "has_started", False):
                return
            super().mouseMoveEvent(event)



    def mouseReleaseEvent(self, event):
        if self.dragging_handle is not None:
            self.dragging_handle = None
            return  # 不處理整塊移動邏輯

        parent_view = self.scene().parent()
        scene_width = self.scene().sceneRect().width()

        if self.drag_start_offset is None:
            self.update_geometry(parent_view.base_date)
            return

        scene_pos = self.scenePos() + self.drag_start_offset
        new_x = scene_pos.x()
        new_y = scene_pos.y()

        day_width = 24 * 20 + 20
        hour_pixel = max(0, new_x % day_width - 20)
        new_date = parent_view.base_date.addDays(int(new_x // day_width))
        new_hour = round(hour_pixel / 20, 2)
        new_track = int(new_y // self.BLOCK_HEIGHT)

        max_track = len(parent_view.encoder_names)

        # ✅ 四向邊界限制
        if new_hour < 0 or new_x < 0 or self.x() + self.rect().width() > scene_width or new_track < 0 or new_track >= max_track:
            print("❌ 拖曳越界，還原")
            self.update_geometry(parent_view.base_date)
            return

        if parent_view.is_overlap(new_date, new_track, new_hour, self.duration_hours, exclude_label=self.label):
            print("❌ 拖曳後重疊，還原")
            self.flash_red()
            self.update_geometry(parent_view.base_date)
            return

        # ✅ 更新 block 屬性
        self.start_date = new_date
        self.start_hour = new_hour
        self.track_index = new_track
        self.update_geometry(parent_view.base_date)

        for b in parent_view.block_data:
            if b.get("id") == self.block_id:
                b.update({
                    "qdate": self.start_date,
                    "track_index": self.track_index,
                    "start_hour": self.start_hour,
                    "duration": self.duration_hours,
                    "label": self.label,
                    "id": self.block_id,
                    "encoder_name": parent_view.encoder_names[self.track_index]  # 對應 encoder
                })
                break

        parent_view.save_schedule()
        super().mouseReleaseEvent(event)
        parent_view.save_schedule()
    def mouseDoubleClickEvent(self, event):
        parent_view = self.scene().parent()
        block_data = None
        for b in parent_view.block_data:
            if b.get("id") == self.block_id:
                block_data = b
                break
        if not block_data:
            print("⚠️ 找不到對應 block 資料，無法編輯")
            return

        dialog = EditBlockDialog(block_data, parent_view.encoder_names)
        if dialog.exec():
            updated = dialog.get_updated_data()
            # 更新 block 資料
            self.start_date = updated["qdate"]
            self.label = updated["label"]
            self.start_hour = updated["start_hour"]
            self.duration_hours = updated["duration"]
            self.track_index = parent_view.encoder_names.index(updated["encoder_name"])

            # 更新畫面與資料
            self.update_geometry(parent_view.base_date)
            self.update_text_position()

            block_data.update({
                "qdate": self.start_date,
                "start_hour": self.start_hour,
                "duration": self.duration_hours,
                "label": self.label,
                "encoder_name": updated["encoder_name"]
            })

            parent_view.save_schedule()
    def flash_red(self):
        original_color = self.brush().color()
        flash_color = QColor(255, 0, 0, 180)
        self.setBrush(flash_color)
        QTimer.singleShot(300, lambda: self.setBrush(QBrush(original_color)))

    def load_preview_images(self, image_folder):
        image_path = os.path.join(image_folder, f"{self.block_id}.png")
        if os.path.exists(image_path):
            pixmap = QPixmap(image_path).scaledToWidth(60)
            self.preview_item.setPixmap(pixmap)
            self.preview_item.setVisible(True)
            self.update()
            self.scene().update()
            print(f"🖼️ 已載入縮圖：{image_path}")
        else:
            self.preview_item.setVisible(False)
            print(f"⚠️ 找不到縮圖：{image_path}")
    def safe_delete(self):
        if self.scene():
            self.scene().removeItem(self)
        
        for item_attr in ["text", "status_text", "preview_item"]:
            item = getattr(self, item_attr, None)
            if item and item.scene():
                item.scene().removeItem(item)
            setattr(self, item_attr, None)  # ✅ 解引用，防止後續被誤用
