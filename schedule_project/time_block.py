from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsSimpleTextItem, QGraphicsPixmapItem, QDialog, QVBoxLayout, QLabel
from PySide6.QtCore import Qt, QTimer, QDate,QDateTime,QTime,QEvent
from PySide6.QtGui import QBrush, QColor, QFont,QPixmap
from edit_block_dialog import EditBlockDialog
import logging
from path_manager import PathManager
import os
from utils import log
logging.basicConfig(level=logging.INFO)
def _safe_pixmap_from_file(path: str) -> QPixmap | None:
    try:
        if not path or not os.path.isfile(path):
            return None
        # 檔案存在但為 0 bytes 的情況也略過
        try:
            if os.path.getsize(path) <= 0:
                return None
        except Exception:
            # 有些網路磁碟在 getsize 會噴例外，直接忽略大小檢查
            pass

        pm = QPixmap(path)
        if pm.isNull():
            return None
        return pm
    except Exception:
        return None
class PreviewImageItem(QGraphicsPixmapItem):
    def __init__(self, block_id, start_date, path_manager, label):
        super().__init__()
        self.block_id = block_id
        self.start_date = start_date
        self.path_manager = path_manager
        self.label = label

    def mouseDoubleClickEvent(self, event):
        try:
            img_path = self.path_manager.get_image_path(self.block_id, self.start_date)
        except Exception:
            return

        pm = _safe_pixmap_from_file(img_path)
        if pm is None:
            # 沒圖或壞圖就不開窗
            log(f"ℹ️ 預覽圖不存在或無法讀取：{img_path}")
            return

        dialog = QDialog()
        dialog.setWindowTitle(f"預覽：{self.label}")
        layout = QVBoxLayout(dialog)

        label = QLabel()
        scaled = pm.scaled(800, 600, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        label.setPixmap(scaled)

        layout.addWidget(label)
        dialog.setLayout(layout)
        dialog.exec()

class TimeBlock(QGraphicsRectItem):
    HANDLE_WIDTH = 6
    BLOCK_HEIGHT = 100
    MIN_DURATION_HOURS = 0.1   
    def __init__(self, start_date: QDate, track_index, start_hour, duration_hours=4, label="節目名稱", block_id=None):
    
        super().__init__(0, 0, duration_hours * 20, self.BLOCK_HEIGHT)
        self.has_moved = False

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
        self.status = "狀態：等待中"  # 這個從 JSON 來，可儲存
        self.live_status = ""        # 這個只顯示，不儲存
        self.preview_item = None
        
        for handle in (self.left_handle, self.right_handle):
            handle.setBrush(QBrush(QColor(80, 80, 80)))
            handle.setCursor(Qt.SizeHorCursor)
            handle.setVisible(False)
        self.dragging_handle = None
       
        self.prevent_drag = False
    def hoverEnterEvent(self, event):
        self.left_handle.setVisible(True)
        self.right_handle.setVisible(True)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.left_handle.setVisible(False)
        self.right_handle.setVisible(False)
        super().hoverLeaveEvent(event)
    def set_live_status(self, text: str):
        if self.live_status != text:
            self.live_status = text
            self.update_text_position()
    def update_text_position(self):
        try:
            if self.text is None or self.text.scene() is None:
                return
            if self.status_text is None or self.status_text.scene() is None:
                return

            # ✅ 主文字：節目名稱 + 時間
            self.text.setText(self.format_text())
            self.text.setPos(4, 2)

            # ✅ 狀態文字：status + live_status（不寫入 JSON）
            combined_status = self.status
            if getattr(self, "live_status", ""):
                combined_status += "\n" + self.live_status

            if self.status_text.text() != combined_status:
                self.status_text.setText(combined_status)

            # ✅ 位置調整
            text_rect = self.text.boundingRect()
            self.status_text.setPos(4, text_rect.height() + 6)

        except RuntimeError:
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
        hour_width = getattr(parent_view, 'hour_width', 20)
        day_width = 24 * hour_width

        # 計算 block 的 x 位置與寬度
        day_offset = base_date.daysTo(self.start_date)
        block_x = day_offset * day_width + self.start_hour * hour_width
        block_width = self.duration_hours * hour_width

        # 畫布限制
        min_x = 0
        max_x = 7 * day_width

        # 左右裁切（保險）
        if block_x < min_x:
            overflow_left = min_x - block_x
            block_x = min_x
            block_width -= overflow_left
        if block_x + block_width > max_x:
            block_width = max(min(block_width, max_x - block_x), hour_width)

        # 更新圖形與位置
        self.setRect(0, 0, block_width, self.BLOCK_HEIGHT)
        self.setPos(block_x, self.track_index * self.BLOCK_HEIGHT + parent_view.grid_top_offset)

        # 移動右側 handle
        self.right_handle.setRect(block_width - self.HANDLE_WIDTH, 0, self.HANDLE_WIDTH, self.BLOCK_HEIGHT)

        QTimer.singleShot(0, self.update_text_position)

        

    def mousePressEvent(self, event):
        if "已結束" in self.status:
            log(f"⛔ 已結束 block 不可拖動（{self.label}）")
            self.prevent_drag = True
            return
        self.has_moved = False
        self.drag_start_offset = event.scenePos()
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
        
            # ✅ 雙擊時不觸發拖曳
        if event.type() == QEvent.GraphicsSceneMouseDoubleClick:
            self.prevent_drag = True
            return
         # ✅ 轉換成本地座標做準確偵測
        local_pos = self.mapFromScene(event.scenePos())

         # ✅ 左邊 handle 拖曳
        if self.left_handle.contains(local_pos):
            if self.has_started:
                log(f"⛔ 已開始：左側不能拖動（{self.label}）")
                self.prevent_drag = True
                return
            self.dragging_handle = 'left'
            return
        # ✅ 右邊 handle 拖曳
        elif self.right_handle.contains(local_pos):
            self.dragging_handle = 'right'
            return


        # ✅ 整塊預備拖曳，延遲啟動（由 mouseMove 決定要不要拖）
        self.dragging_handle = None
        self.setFlag(QGraphicsRectItem.ItemIsMovable, False)  # 先不要啟用拖曳
      

    def update_block_data(self, updates: dict):
            parent_view = self.scene().parent()
            for b in parent_view.block_data:
                if b.get("id") == self.block_id:
                    has_changed = False
                    for k, v in updates.items():
                        if b.get(k) != v:
                            b[k] = v
                            has_changed = True
                    if has_changed:
                        parent_view.save_schedule()
                    break

    def mouseMoveEvent(self, event):
        if getattr(self, "prevent_drag", False):
            return
        parent_view = self.scene().parent()

        if not self.has_started and self.dragging_handle is None:
            if self.drag_start_offset is not None:
                distance = (event.scenePos() - self.drag_start_offset).manhattanLength()
                if distance < 10:
                    return
                else:
                    self.has_moved = True
                    self.setFlag(QGraphicsRectItem.ItemIsMovable, True)
                    super().mouseMoveEvent(event)
                    return

        if getattr(self, "has_started", False) and self.dragging_handle is None:
            return

        now = QDateTime.currentDateTime()

        if self.dragging_handle == 'right':
            delta = event.pos().x()
            # new_duration = round(max(1.0, delta / 20), 2)
            hour_width = getattr(parent_view, 'hour_width', 20)
            new_duration = round(max(self.MIN_DURATION_HOURS, delta / hour_width), 2)
            new_end_dt = QDateTime(self.start_date, QTime(int(self.start_hour), int((self.start_hour % 1) * 60)))
            new_end_dt = new_end_dt.addSecs(int(new_duration * 3600))

            if new_end_dt < now:
                log(f"⛔ 無法縮到現在時間前結束（{self.label}）")
                self.flash_red()
                return

            if not parent_view.is_overlap(self.start_date, self.track_index, self.start_hour, new_duration, exclude_label=self.block_id):
                self.duration_hours = new_duration
                self.update_geometry(parent_view.base_date)
                end_hour, end_qdate = self.compute_end_info()
                self.update_block_data({
                    "duration": self.duration_hours,
                    "end_hour": end_hour,
                    "end_qdate": end_qdate
                })
                parent_view.save_schedule()

        elif self.dragging_handle == 'left':
            delta = event.pos().x()
            hour_width = getattr(self.scene().parent(), 'hour_width', 20)

            # ✅ 允許的最短時長（沒有類別常數就用 0.25 小時）
            min_dur = getattr(self, "MIN_DURATION_HOURS", 0.25)

            # ✅ 最多能往右推的像素：保證剩餘長度 >= 最短時長
            max_shift_px = self.rect().width() - (min_dur * hour_width)

            # clamp：不可小於 0，也不可超過 max_shift_px
            shift_pixels = min(max(0, delta), max_shift_px)

            shift_hours = round(shift_pixels / hour_width, 2)
            new_start_hour = self.start_hour + shift_hours
            new_duration = round(self.duration_hours - shift_hours, 2)

            new_start_dt = QDateTime(
                self.start_date, QTime(int(new_start_hour), int((new_start_hour % 1) * 60))
            )

           
            # ⚠️ 不再檢查 new_duration < 1，因為上面已經用 clamp 確保不會低於最短時長
            if not parent_view.is_overlap(self.start_date, self.track_index, new_start_hour, new_duration, exclude_label=self.block_id):
                self.start_hour = new_start_hour
                self.duration_hours = new_duration
                self.update_geometry(parent_view.base_date)
                end_hour, end_qdate = self.compute_end_info()
                self.update_block_data({
                    "start_hour": self.start_hour,
                    "duration": self.duration_hours,
                    "end_hour": end_hour,
                    "end_qdate": end_qdate
                })
                parent_view.save_schedule()
            else:
                log(f"❌ 重疊偵測：{self.label} 移動後會與他人重疊")
                self.flash_red()


    def compute_end_info(self):
        total_hour = round(self.start_hour + self.duration_hours, 4)
        if total_hour >= 24:
            return round(total_hour - 24, 4), self.start_date.addDays(1)
        else:
            return total_hour, self.start_date



    def mouseReleaseEvent(self, event):
        self.setFlag(QGraphicsRectItem.ItemIsMovable, False)
        self.prevent_drag = False
        parent_view = self.scene().parent()
        
        if not self.has_moved:
            self.setFlag(QGraphicsRectItem.ItemIsMovable, False)
            self.update_geometry(parent_view.base_date)
            return  
        scene_width = self.scene().sceneRect().width()

        if self.dragging_handle is not None:
            self.dragging_handle = None
            # ✅ 若是 handle 拖曳，這時 self.start_hour 或 self.duration_hours 已被更新
            for b in parent_view.block_data:
                if b.get("id") == self.block_id:
                    
                    end_hour, end_qdate = self.compute_end_info()
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
            self.setFlag(QGraphicsRectItem.ItemIsMovable, False)
            return

        if self.drag_start_offset is None:
            self.update_geometry(parent_view.base_date)
            return

        scene_pos = self.scenePos()
        new_x = scene_pos.x()
        new_y = scene_pos.y()
        hour_width = parent_view.hour_width  
       
        day_width = 24 * hour_width 
        hour_pixel = new_x % day_width
        new_hour = round(hour_pixel / hour_width, 2)
        new_date = parent_view.base_date.addDays(int(new_x // day_width))
        # new_hour = round(hour_pixel / 20, 2)
        new_track = int(new_y // self.BLOCK_HEIGHT)

        max_track = len(parent_view.encoder_names)

        # ✅ 四向邊界限制
        if new_hour < 0 or new_x < 0 or self.x() + self.rect().width() > scene_width or new_track < 0 or new_track >= max_track:
            log("❌ 拖曳越界，還原")
            self.update_geometry(parent_view.base_date)
            return
        # ✅ 時間不可在過去
        now = QDateTime.currentDateTime()
        start_dt = QDateTime(new_date, QTime(int(new_hour), int((new_hour % 1) * 60)))
        if start_dt < now:
            log(f"⛔ 不可移動到過去（{self.label}）")
            self.flash_red()
            self.update_geometry(parent_view.base_date)
            return
        if self.is_start_or_end_in_past(new_date, new_hour, self.duration_hours):
            log(f"⛔ 不可移動到過去（{self.label}）")
            self.flash_red()
            self.update_geometry(parent_view.base_date)
            parent_view.save_schedule()
            return
        # ✅ 重疊檢查

        if parent_view.is_overlap(new_date, new_track, new_hour, self.duration_hours, exclude_label=self.block_id):
            log("❌ 拖曳後重疊，還原")
            self.flash_red()
            self.update_geometry(parent_view.base_date)
            return

        # ✅ 更新 block 屬性
        self.start_date = new_date
        self.start_hour = new_hour
        self.track_index = new_track
        # self.duration_hours = round(self.rect().width() / 20, 2)
        self.duration_hours = round(self.rect().width() / hour_width, 2)
        self.update_geometry(parent_view.base_date)
         # 🔁 加這段：處理 end_hour 與 end_qdate
       
        end_hour, end_qdate = self.compute_end_info()
        if self.dragging_handle is not None:
            self.dragging_handle = None
        for b in parent_view.block_data:
            if b.get("id") == self.block_id:
                b.update({
                    "qdate": self.start_date,
                    "track_index": self.track_index,
                    "start_hour": self.start_hour,
                    "duration": self.duration_hours,
                    "end_hour": end_hour,           # ✅ 補這行
                    "end_qdate": end_qdate,         # ✅ 補這行
                    "label": self.label,
                    "id": self.block_id,
                    "encoder_name": parent_view.encoder_names[self.track_index]  # 對應 encoder
                })
                break

        
        super().mouseReleaseEvent(event)
        parent_view.save_schedule()
        self.setFlag(QGraphicsRectItem.ItemIsMovable, False)  
    def update_status_by_time(self):
        now = QDateTime.currentDateTime()
        start_dt = QDateTime(self.start_date, QTime(int(self.start_hour), int((self.start_hour % 1) * 60)))
        end_dt = start_dt.addSecs(int(self.duration_hours * 3600))

        # ✅ 若已經結束，統一標記為「已結束」，不再讓硬體狀態蓋掉
        if now > end_dt:
            if self.status != "狀態：✅ 已結束":
                self.status = "狀態：✅ 已結束"
                self.setBrush(QBrush(QColor(180, 180, 180, 180)))  # 灰色
                self.update_text_position()
            return  # ❗重要：已結束就 return，不再讓後續邏輯處理

        # ✅ 還沒開始
        if now < start_dt:
            if self.status != "狀態：⌛ 等待中":
                self.status = "狀態：⌛ 等待中"
                self.setBrush(QBrush(QColor(200, 200, 255, 180)))  # 藍色
                self.update_text_position()
            return

        # ✅ 進行中：此時 UI 狀態應該依照硬體回報更新（例如 ScheduleRunner 寫入的狀態）
        # ⚠️ 請勿在這裡修改成「錄影中 / 停止中」，由外部控制元件設定
        pass
    def mouseDoubleClickEvent(self, event):
       
        event.accept()  # ✅ 優先阻止事件傳遞
        self.setFlag(QGraphicsRectItem.ItemIsMovable, False)
        QTimer.singleShot(0, lambda: self.setFlag(QGraphicsRectItem.ItemIsMovable, False))
        # ✅ 如果點到的是圖片，讓圖片自己處理（不要打開 block dialog）
        items_at_click = self.scene().items(event.scenePos())
        for item in items_at_click:
            if isinstance(item, PreviewImageItem) and item.block_id == self.block_id:
                # ✅ 圖片自己處理 popup，所以這邊什麼都不用做
                return
        
         # ✅ 檢查是否為過去已結束的 block
        now = QDateTime.currentDateTime()
        start_dt = QDateTime(self.start_date, QTime(int(self.start_hour), int((self.start_hour % 1) * 60)))
        end_dt = start_dt.addSecs(int(self.duration_hours * 3600))
        if now > end_dt:
            log("⛔ 已結束排程不可編輯")
            return

        # ✅ 點到區塊其他地方 → 編輯 Dialog
        log(f"📝 點擊 block：{self.label}")
        parent_view = self.scene().parent()
        block_data = None
        for b in parent_view.block_data:
            if b.get("id") == self.block_id:
                block_data = b
                break

        if not block_data:
            log("⚠️ 找不到對應 block 資料")
            return
        
        dialog = EditBlockDialog(block_data, self.encoder_names, readonly=(now > end_dt))
        if dialog.exec():
            updated = dialog.get_updated_data()
               # ✅ 加這段防呆檢查「是否會落在過去」
            start_dt = QDateTime(updated["qdate"], QTime(int(updated["start_hour"]), int((updated["start_hour"] % 1) * 60)))
            end_hour = updated["start_hour"] + updated["duration"]
            end_qdate = updated["qdate"].addDays(1) if end_hour >= 24 else updated["qdate"]
            end_dt = QDateTime(end_qdate, QTime(int(end_hour % 24), int((end_hour % 1) * 60)))
            now = QDateTime.currentDateTime()

            if start_dt < now or end_dt < now:
               
                self.flash_red()
                return
            self.start_date = updated["qdate"]
            self.label = updated["label"]
            self.start_hour = updated["start_hour"]
            self.duration_hours = updated["duration"]
            self.track_index = parent_view.encoder_names.index(updated["encoder_name"])

            self.update_geometry(parent_view.base_date)
            self.update_text_position()
            end_hour, end_qdate = self.compute_end_info()
            block_data.update({
                "qdate": self.start_date,
                "start_hour": self.start_hour,
                "duration": self.duration_hours,
                "end_hour": end_hour,
                "end_qdate": end_qdate,
                "label": self.label,
                "encoder_name": updated["encoder_name"]
            })
            parent_view.save_schedule()

        # event.accept()


    def flash_red(self):
        original_color = self.brush().color()
        flash_color = QColor(255, 0, 0, 180)
        self.setBrush(flash_color)
        QTimer.singleShot(300, lambda: self.setBrush(QBrush(original_color)))

    def load_preview_images(self, image_folder):
        """安全載入 block 的縮圖；檔案不存在/壞掉就略過且隱藏舊縮圖。"""
        try:
            # 優先用呼叫端給的資料夾；若沒給，改用 PathManager 求精確路徑
            image_path = None

            if image_folder:
                candidate = os.path.join(image_folder, f"{self.block_id}.png")
                if os.path.isfile(candidate):
                    image_path = candidate
            if not image_path:
                # fallback：用 path_manager 直接算路徑
                pm = getattr(self, "path_manager", None)
                if pm is None:
                    # 從 parent view 拿
                    parent_view = self.scene().parent() if self.scene() else None
                    pm = getattr(parent_view, "path_manager", None)
                if pm:
                    try:
                        candidate = pm.get_image_path(self.block_id, self.start_date)
                        if os.path.isfile(candidate):
                            image_path = candidate
                    except Exception:
                        image_path = None

            pmx = _safe_pixmap_from_file(image_path) if image_path else None
            if pmx is None:
                # 找不到圖或讀不到 → 把舊的縮圖藏起來（避免殘影），不崩不報錯
                if getattr(self, "preview_item", None):
                    self.preview_item.setVisible(False)
                # log(f"ℹ️ 找不到縮圖或無法讀取：block_id={self.block_id}")
                return

            # 生成縮圖
            width = 60
            scaled = pmx.scaledToWidth(width, Qt.SmoothTransformation)

            scene = self.scene()
            if not scene:
                log("⚠️ 無法取得 scene，取消縮圖建立")
                return

            # 建立或更新 preview_item
            if not getattr(self, "preview_item", None):
                # 取得 path_manager
                pm = getattr(self, "path_manager", None)
                if pm is None:
                    parent_view = scene.parent()
                    pm = getattr(parent_view, "path_manager", None)

                self.preview_item = PreviewImageItem(self.block_id, self.start_date, pm, self.label)
                self.preview_item.setZValue(10)
                self.preview_item.setAcceptedMouseButtons(Qt.LeftButton)
                self.preview_item.setFlag(QGraphicsPixmapItem.ItemIsMovable, True)
                scene.addItem(self.preview_item)

            self.preview_item.setPixmap(scaled)
            self.preview_item.setVisible(True)

            # 放在文字右側
            block_pos = self.scenePos()
            text_rect = self.text.boundingRect() if self.text else None
            x_offset = block_pos.x() + (text_rect.width() + 8 if text_rect else 8)
            y_offset = block_pos.y() + 2
            self.preview_item.setPos(x_offset, y_offset)

            # 標記 block_id
            self.preview_item.block_id = self.block_id

            # log(f"🖼️ 縮圖就緒：{image_path}")
        except Exception as e:
            log(f"❌ load_preview_images 例外：{e}")
            # 任何錯誤都吞掉，不讓 UI 崩


    def safe_delete(self):
        if self.scene():
            self.scene().removeItem(self)
        
        for item_attr in ["text", "status_text", "preview_item"]:
            item = getattr(self, item_attr, None)
            if item and item.scene():
                item.scene().removeItem(item)
            setattr(self, item_attr, None)  # ✅ 解引用，防止後續被誤用
 
    
    def show_image_popup(self, image_path):
        """安全版本的圖片預覽（保留介面相容）。"""
        pm = _safe_pixmap_from_file(image_path)
        if pm is None:
            log(f"ℹ️ 預覽圖不存在或無法讀取：{image_path}")
            return

        dialog = QDialog()
        dialog.setWindowTitle(f"預覽：{self.label}")
        layout = QVBoxLayout(dialog)

        label = QLabel()
        scaled = pm.scaled(800, 600, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        label.setPixmap(scaled)

        layout.addWidget(label)
        dialog.setLayout(layout)
        dialog.exec()
    def is_start_or_end_in_past(self, qdate, start_hour, duration):
        now = QDateTime.currentDateTime()
        start_dt = QDateTime(qdate, QTime(int(start_hour), int((start_hour % 1) * 60)))
        end_hour = start_hour + duration
        end_qdate = qdate.addDays(1) if end_hour >= 24 else qdate
        end_dt = QDateTime(end_qdate, QTime(int(end_hour % 24), int((end_hour % 1) * 60)))
        return start_dt < now or end_dt < now