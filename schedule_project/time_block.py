from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsSimpleTextItem, QGraphicsPixmapItem, QDialog, QVBoxLayout, QLabel
from PySide6.QtCore import Qt, QTimer, QDate,QDateTime,QTime,QEvent
from PySide6.QtGui import QBrush, QColor, QFont,QPixmap
from edit_block_dialog import EditBlockDialog
import logging
from path_manager import PathManager
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
        start_dt = QDateTime(start_date, QTime(int(start_hour), int((start_hour % 1) * 60)))
        end_dt = start_dt.addSecs(int(duration_hours * 3600))
        now = QDateTime.currentDateTime()
        self.has_ended = now > end_dt  # ✅ 判斷是否已完成

        # 顏色設定
        if self.has_ended:
            self.setBrush(QBrush(QColor(180, 180, 180, 180)))  # 灰色
        else:
            self.setBrush(QBrush(QColor(100, 150, 255, 180)))  # 原藍色
        self.setFlag(QGraphicsRectItem.ItemIsMovable, False)
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
        self.preview_item.setAcceptedMouseButtons(Qt.NoButton)
        self.preview_item.setAcceptHoverEvents(True)
        self.prevent_drag = False
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
        parent_view = self.scene().parent()
        day_offset = base_date.daysTo(self.start_date)
        
        block_x = day_offset * parent_view.day_width + self.start_hour * parent_view.hour_width
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
        self.prevent_drag = False  # 每次按下都先重置
        now = QDateTime.currentDateTime()
        start_dt = QDateTime(self.start_date, QTime(int(self.start_hour), int((self.start_hour % 1) * 60)))
        self.has_started = now >= start_dt  # ⏱️ 判斷是否已開始錄影

        # 清除其他 block 的拖曳狀態
        for item in self.scene().items():
            if isinstance(item, TimeBlock) and item is not self:
                item.dragging_handle = None
                item.prevent_drag = False
        self.setFocus()
        self.drag_start_offset = event.pos()
            # ✅ 雙擊時不觸發拖曳
        if event.type() == QEvent.GraphicsSceneMouseDoubleClick:
            self.prevent_drag = True
            return
         # ✅ 左邊 handle 拖曳
        if self.left_handle.contains(event.pos()):
            if self.has_started:
                print(f"⛔ 已開始：左側不能拖動（{self.label}）")
                self.prevent_drag = True
                return
            self.dragging_handle = 'left'
            return
        # ✅ 右邊 handle 拖曳
        elif self.right_handle.contains(event.pos()):
            self.dragging_handle = 'right'
            return

        # # ✅ 整塊拖曳不允許（即使點擊中間區域）
        # if not self.has_started and self.dragging_handle is None:
        #     self.setFlag(QGraphicsRectItem.ItemIsMovable, True)
        #     self.drag_start_offset = event.pos()

        # ✅ 整塊預備拖曳，延遲啟動（由 mouseMove 決定要不要拖）
        self.dragging_handle = None
        self.setFlag(QGraphicsRectItem.ItemIsMovable, False)  # 先不要啟用拖曳
        # self.dragging_handle = None
        # super().mousePressEvent(event)





    def mouseMoveEvent(self, event):
        if getattr(self, "prevent_drag", False):
            return
        parent_view = self.scene().parent()
        if not self.has_started and self.dragging_handle is None:
            if self.drag_start_offset is not None:
                distance = (event.pos() - self.drag_start_offset).manhattanLength()
                if distance < 4:
                    return  # 不夠遠就不動
                else:
                    self.setFlag(QGraphicsRectItem.ItemIsMovable, True)
                    super().mouseMoveEvent(event)  # ✅ 只在拖超過距離時才觸發
                    return
    # ⛔ 若 block 已開始且不是在拉 handle，就禁止拖曳
        if getattr(self, "has_started", False) and self.dragging_handle is None:
            return

        if self.dragging_handle == 'right':
            delta = event.pos().x()
            new_duration = round(max(1.0, delta / 20), 2)

            new_right_x = self.scenePos().x() + new_duration * 20
            if new_right_x <= self.scenePos().x():
                print(f"⛔ 無法將右邊往前拖（{self.label}）")
                return
            new_end_dt = QDateTime(self.start_date, QTime(int(self.start_hour), int((self.start_hour % 1) * 60)))
            new_end_dt = new_end_dt.addSecs(int(new_duration * 3600))
            now = QDateTime.currentDateTime()
            if new_end_dt < now:
                print(f"⛔ 無法縮到現在時間前結束（{self.label}）")
                self.flash_red()
                return
            if not parent_view.is_overlap(self.start_date, self.track_index, self.start_hour, new_duration, exclude_label=self.block_id):
                self.duration_hours = new_duration
                self.update_geometry(parent_view.base_date)

        elif self.dragging_handle == 'left':
            delta = event.pos().x()
            max_shift = self.rect().width() - 20  # 最小保留 1 小時
            shift_pixels = min(delta, max_shift)
            shift_hours = round(shift_pixels / 20, 2)

            new_start_hour = self.start_hour + shift_hours
            new_duration = self.duration_hours - shift_hours

            new_start_dt = QDateTime(self.start_date, QTime(int(new_start_hour), int((new_start_hour % 1) * 60)))
            now = QDateTime.currentDateTime()

            if new_start_dt < now:
                print(f"⛔ 無法將開始時間拉到過去（{self.label}）")
                self.flash_red()
                return

            if new_duration < 1:
                print(f"⛔ 時間太短（{self.label}）")
                self.flash_red()
                return

            if not parent_view.is_overlap(self.start_date, self.track_index, new_start_hour, new_duration, exclude_label=self.block_id):
                self.start_hour = new_start_hour
                self.duration_hours = new_duration
                self.update_geometry(parent_view.base_date)
            else:
                print(f"❌ 重疊偵測：{self.label} 移動後會與他人重疊")
                self.flash_red()




    def mouseReleaseEvent(self, event):
        self.prevent_drag = False
        parent_view = self.scene().parent()
        scene_width = self.scene().sceneRect().width()

        if self.dragging_handle is not None:
            self.dragging_handle = None
            # ✅ 若是 handle 拖曳，這時 self.start_hour 或 self.duration_hours 已被更新
            for b in parent_view.block_data:
                if b.get("id") == self.block_id:
                    end_hour = round(self.start_hour + self.duration_hours, 4)
                    end_qdate = self.start_date.addDays(1) if end_hour >= 24 else self.start_date
                    b.update({
                        "qdate": self.start_date,
                        "track_index": self.track_index,
                        "start_hour": self.start_hour,
                        "end_hour": end_hour,
                        "end_qdate": end_qdate,
                        "duration": self.duration_hours,
                        "label": self.label,
                        "id": self.block_id,
                        "encoder_name": parent_view.encoder_names[self.track_index]
                    })
                    break
            parent_view.save_schedule()
            return

        if self.drag_start_offset is None:
            self.update_geometry(parent_view.base_date)
            return

        scene_pos = self.scenePos()
        new_x = scene_pos.x()
        new_y = scene_pos.y()

        day_width = 24 * 20 + 20
        hour_pixel = new_x % day_width
        new_date = parent_view.base_date.addDays(int(new_x // day_width))
        new_hour = round(hour_pixel / 20, 2)
        new_track = int(new_y // self.BLOCK_HEIGHT)

        max_track = len(parent_view.encoder_names)

        # ✅ 四向邊界限制
        if new_hour < 0 or new_x < 0 or self.x() + self.rect().width() > scene_width or new_track < 0 or new_track >= max_track:
            print("❌ 拖曳越界，還原")
            self.update_geometry(parent_view.base_date)
            return
        # ✅ 時間不可在過去
        now = QDateTime.currentDateTime()
        start_dt = QDateTime(new_date, QTime(int(new_hour), int((new_hour % 1) * 60)))
        if start_dt < now:
            print(f"⛔ 不可移動到過去（{self.label}）")
            self.flash_red()
            self.update_geometry(parent_view.base_date)
            return
        # ✅ 重疊檢查
        if parent_view.is_overlap(new_date, new_track, new_hour, self.duration_hours, exclude_label=self.block_id):
            print("❌ 拖曳後重疊，還原")
            self.flash_red()
            self.update_geometry(parent_view.base_date)
            return

        # ✅ 更新 block 屬性
        self.start_date = new_date
        self.start_hour = new_hour
        self.track_index = new_track
        self.update_geometry(parent_view.base_date)
        if self.dragging_handle is not None:
            self.dragging_handle = None
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

        
        super().mouseReleaseEvent(event)
        parent_view.save_schedule()
        self.setFlag(QGraphicsRectItem.ItemIsMovable, False)  

    def mouseDoubleClickEvent(self, event):
        event.accept()  # ✅ 優先阻止事件傳遞
        self.setFlag(QGraphicsRectItem.ItemIsMovable, False)
        QTimer.singleShot(0, lambda: self.setFlag(QGraphicsRectItem.ItemIsMovable, False))

        pos = event.pos()
        # ✅ 點擊縮圖 ➜ 顯示大圖
        if self.preview_item and self.preview_item.isVisible():
            if self.preview_item.contains(self.mapToItem(self.preview_item, pos)):
                print(f"🖼️ 點到圖片縮圖：{self.block_id}")
                if hasattr(self, "path_manager"):
                    img_path = self.path_manager.get_image_path(self.block_id, self.start_date)
                    if os.path.exists(img_path):
                        self.show_image_popup(img_path)
                    else:
                        print(f"❌ 找不到圖片：{img_path}")
                else:
                    print("⚠️ 未設定 path_manager")
                return
         # ✅ 檢查是否為過去已結束的 block
        now = QDateTime.currentDateTime()
        start_dt = QDateTime(self.start_date, QTime(int(self.start_hour), int((self.start_hour % 1) * 60)))
        end_dt = start_dt.addSecs(int(self.duration_hours * 3600))
        if now > end_dt:
            print("⛔ 已結束排程不可編輯")
            return

        # ✅ 點到區塊其他地方 → 編輯 Dialog
        print(f"📝 點擊 block：{self.label}")
        parent_view = self.scene().parent()
        block_data = None
        for b in parent_view.block_data:
            if b.get("id") == self.block_id:
                block_data = b
                break

        if not block_data:
            print("⚠️ 找不到對應 block 資料")
            return

        dialog = EditBlockDialog(block_data, self.encoder_names, readonly=(now > end_dt))
        if dialog.exec():
            updated = dialog.get_updated_data()
            self.start_date = updated["qdate"]
            self.label = updated["label"]
            self.start_hour = updated["start_hour"]
            self.duration_hours = updated["duration"]
            self.track_index = parent_view.encoder_names.index(updated["encoder_name"])

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

        event.accept()


    def flash_red(self):
        original_color = self.brush().color()
        flash_color = QColor(255, 0, 0, 180)
        self.setBrush(flash_color)
        QTimer.singleShot(300, lambda: self.setBrush(QBrush(original_color)))

    def load_preview_images(self, image_folder):
        image_path = os.path.join(image_folder, f"{self.block_id}.png")
        pixmap = QPixmap(image_path)

        if pixmap.isNull():
            self.preview_item.setVisible(False)
            print(f"❌ 無法載入圖片：{image_path}")
            return

        # ✅ 縮圖尺寸
        width = 60
        scaled = pixmap.scaledToWidth(width, Qt.SmoothTransformation)
        self.preview_item.setPixmap(scaled)

        # ✅ 放在文字右邊
        text_rect = self.text.boundingRect()
        x_offset = text_rect.width() + 8
        y_offset = self.text.y()
        self.preview_item.setOffset(x_offset, y_offset)

        self.preview_item.setVisible(True)
        self.preview_item.setZValue(10)
        self.preview_item.setAcceptedMouseButtons(Qt.LeftButton)

        # ✅ 強制重繪
        self.update()
        if self.scene():
            self.scene().update()

        print(f"🖼️ 圖片放在右邊：{image_path}")

    def safe_delete(self):
        if self.scene():
            self.scene().removeItem(self)
        
        for item_attr in ["text", "status_text", "preview_item"]:
            item = getattr(self, item_attr, None)
            if item and item.scene():
                item.scene().removeItem(item)
            setattr(self, item_attr, None)  # ✅ 解引用，防止後續被誤用
 
    def show_image_popup(self, image_path):
        dialog = QDialog()
        dialog.setWindowTitle(f"預覽：{self.label}")
        layout = QVBoxLayout(dialog)

        label = QLabel()
        pixmap = QPixmap(image_path)

        if not pixmap.isNull():
            scaled = pixmap.scaled(800, 600, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            label.setPixmap(scaled)

        layout.addWidget(label)
        dialog.setLayout(layout)
        dialog.exec()