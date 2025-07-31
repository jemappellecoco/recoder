from PySide6.QtWidgets import QGraphicsView, QGraphicsScene
from PySide6.QtCore import Qt, QDate, QTimer,QDateTime, QTime
from PySide6.QtGui import QPainter, QFont,QPen
from time_block import TimeBlock
import json
import os
import uuid
from utils import log
from path_manager import PathManager 
class ScheduleView(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.encoder_labels = {}
        self.blocks = []
        self.block_data = []
        self.path_manager = None
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.days = 7
        self.hour_width = 20
        self.day_width = 24 * self.hour_width
        self.base_date = QDate.currentDate()
        self.encoder_names = []
        self.encoder_status = {}
        self.tracks = len(self.encoder_names)  # 加這行初始化軌道數
        # self.setSceneRect(-120, 0, self.days * self.day_width + 150, self.tracks * 100 + 40)
        # self.setSceneRect(-120, 0, self.days * self.day_width + 150, 1000)
        
        self.setRenderHint(QPainter.Antialiasing)
        # self.schedule_timer = QTimer()
        # self.schedule_timer.start(1000)
        # self.load_schedule()
        self.path_manager = PathManager()
        self.record_root = self.path_manager.record_root  

        self.now_timer = QTimer(self)
        self.now_timer.timeout.connect(self.update_now_line)
        self.now_timer.start(1000)  # 每秒更新
        self.now_line_item = None
        self.now_time_label = None
        self.global_timer = QTimer(self)
        self.global_timer.timeout.connect(self.update_visible_blocks_only)
        self.global_timer.start(30000)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
       
        self.grid_top_offset = 30
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)
    def update_visible_blocks_only(self):
        visible_rect = self.viewport().rect()
        visible_scene_rect = self.mapToScene(visible_rect).boundingRect()
        
        for item in self.scene.items(visible_scene_rect):  # ✅ 限定畫面內
            if isinstance(item, TimeBlock):
                
                #  ✅ 圖片 lazy load：只載一次
                if not getattr(item, "preview_item", None):  # 尚未載入過
                    if hasattr(self, "record_root"):
                        img_folder = os.path.join(self.record_root, item.start_date.toString("MM.dd.yyyy"), "img")
                        item.load_preview_images(img_folder)
   
    def update_now_line(self):
        now = QDateTime.currentDateTime()
        days_from_base = self.base_date.daysTo(now.date())

        # 不在可視範圍內時，移除現在時間線
        if not (0 <= days_from_base < self.days):
            try:
                if self.now_line_item and self.now_line_item.scene():
                    self.scene.removeItem(self.now_line_item)
            except RuntimeError:
                pass
            self.now_line_item = None

            try:
                if self.now_time_label and self.now_time_label.scene():
                    self.scene.removeItem(self.now_time_label)
            except RuntimeError:
                pass
            self.now_time_label = None
            return

        # ➤ 計算目前時間對應的 X 座標
        time = now.time()
        total_hours = time.hour() + time.minute() / 60 + time.second() / 3600
        x = days_from_base * self.day_width + total_hours * self.hour_width

        offset = self.grid_top_offset  # 🔴 新增：向下偏移

        # ✅ 安全地移除舊紅線
        try:
            if self.now_line_item and self.now_line_item.scene():
                self.scene.removeItem(self.now_line_item)
        except RuntimeError:
            self.now_line_item = None

        self.now_line_item = self.scene.addLine(
            x, offset, x, offset + self.tracks * 100, QPen(Qt.red, 2)
        )
        self.now_line_item.setZValue(1000)

        # ✅ 安全地移除舊時間文字
        try:
            if self.now_time_label and self.now_time_label.scene():
                self.scene.removeItem(self.now_time_label)
        except RuntimeError:
            self.now_time_label = None

        # ➤ 新增現在時間文字
        time_str = now.time().toString("HH:mm:ss")
        self.now_time_label = self.scene.addText(f"TIME {time_str}")
        self.now_time_label.setFont(QFont("Arial", 8, QFont.Bold))
        self.now_time_label.setDefaultTextColor(Qt.red)
        self.now_time_label.setPos(x - 10, offset - 18)  # 🔴 新位置跟著 offset
        self.now_time_label.setZValue(1000)

    def update_all_blocks(self):
        for item in self.scene.items():
            if isinstance(item, TimeBlock):
                item.update_status_by_time()
    
    def draw_grid(self):
        log(f"🎯 draw_grid encoder_names:{self.encoder_names}" )

        offset = self.grid_top_offset  # ✅ 統一使用偏移量
        self.scene.clear()
        self.tracks = len(self.encoder_names)
        self.update_scene_rect()
        self.verticalScrollBar().setValue(0)

        for day in range(self.days):
            for hour in range(24):
                x = day * self.day_width + hour * self.hour_width
                self.scene.addLine(x, offset, x, offset + self.tracks * 100, Qt.DotLine)

        for day in range(self.days):
            x = day * self.day_width
            self.scene.addRect(x, offset, self.day_width, self.tracks * 100)

        for track in range(self.tracks):
            y = offset + track * 100  # ✅ 把每條橫線往下移 offset
            self.scene.addLine(0, y, self.days * self.day_width, y)

            if track < len(self.encoder_names):
                encoder_name = self.encoder_names[track]
                status_label = self.encoder_status.get(encoder_name)
                status_text = status_label.text() if status_label else "未知"
                full_label = f"{encoder_name}\n{status_text}"
            else:
                full_label = f"未指定\n--"

            label = self.scene.addText(full_label)
            label.setFont(QFont("Arial", 9))
            label.setPos(-95, y)  # ✅ y 已經包含 offset

        self.draw_blocks()
        self.update_now_line()
        self.verticalScrollBar().setValue(self.verticalScrollBar().minimum())

  

    def update_scene_rect(self):
        self.tracks = len(self.encoder_names)
        # scene_height = self.tracks * 100 + 40
        scene_height = self.tracks * 100 + self.grid_top_offset
        scene_width = self.days * self.day_width + 150
        self.setSceneRect(-120, 0, scene_width, scene_height)
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
                block.encoder_names = self.encoder_names
                block.status = data.get("status") or "狀態：⏳ 等待中"

                block.update_text_position()
                # 從舊 block 繼承狀態與圖片
                old_block = old_block_map.get(data["label"])
                if old_block:
                    block.status = old_block.status
                    if hasattr(old_block, "status_text") and old_block.status_text:
                        block.status_text.setText(old_block.status)
                if block.block_id and hasattr(self, "record_root"):
                    img_folder = os.path.join(self.record_root, block.start_date.toString("MM.dd.yyyy"), "img")
                    block.load_preview_images(img_folder)

            

                self.blocks.append(block)

        # 更新 ScheduleRunner 的 block 清單
        if hasattr(self, "runner"):
            self.runner.schedule_data = self.block_data
            self.runner.blocks = self.blocks
            




    def is_overlap(self, qdate, track_index, start_hour, duration, exclude_label=None):
        new_start_dt = QDateTime(qdate, QTime(int(start_hour), int((start_hour % 1) * 60)))
        end_hour = start_hour + duration
        end_qdate = qdate.addDays(1) if end_hour >= 24 else qdate
        new_end_dt = QDateTime(end_qdate, QTime(int(end_hour % 24), int(((end_hour % 1) * 60))))

        for block in self.block_data:
            if block["track_index"] != track_index:
                continue

            # ✅ 用 exclude_label 當作 exclude_id（只要確定你傳的是 block["id"]）
            if exclude_label and block.get("id") == exclude_label:
                continue  

            b_start_hour = float(block["start_hour"])
            b_end_hour = float(block.get("end_hour", b_start_hour + block["duration"]))
            b_qdate = block["qdate"]
            if isinstance(b_qdate, str):
                b_qdate = QDate.fromString(b_qdate, "yyyy-MM-dd")
            b_end_qdate = block.get("end_qdate", b_qdate.addDays(1) if b_end_hour >= 24 else b_qdate)

            b_start_dt = QDateTime(b_qdate, QTime(int(b_start_hour), int((b_start_hour % 1) * 60)))
            b_end_dt = QDateTime(b_end_qdate, QTime(int(b_end_hour % 24), int((b_end_hour % 1) * 60)))

            if new_start_dt < b_end_dt and new_end_dt > b_start_dt:
                log(f"🔴 重疊偵測：與 {block['label']} 發生重疊")
                return True

        return False
    

    def add_time_block(self, qdate: QDate, track_index, start_hour, duration=4, label="節目", encoder_name=None, block_id=None):
        if isinstance(qdate, str):
            qdate = QDate.fromString(qdate, "yyyy-MM-dd")

        end_hour = round(start_hour + duration, 4)
        end_qdate = qdate.addDays(1) if end_hour >= 24 else qdate

        block = {
            "qdate": qdate,
            "track_index": track_index,
            "start_hour": start_hour,
            "duration": duration,
            "end_hour": end_hour,
            "end_qdate": end_qdate,
            "label": label,
            "encoder_name": encoder_name,
            "id": block_id or str(uuid.uuid4()),
            "snapshot_path": ""
        }

       
        # block.path_manager = self.path_manager
        if encoder_name is not None:
            block["encoder_name"] = encoder_name
        if block_id:
            block["id"] = block_id

        self.block_data.append(block)
        self.draw_blocks()
    def can_delete_block(self, block):
        now = QDateTime.currentDateTime()
        start_dt = QDateTime(block["qdate"], QTime(int(block["start_hour"]), int((block["start_hour"] % 1) * 60)))
        return start_dt >= now    
    def remove_block_by_label(self, label):
        # 🔍 找出對應的 block 資料（從 block_data 查）
        block_to_remove = next((b for b in self.block_data if b["label"] == label), None)

        if not block_to_remove:
            log(f"⚠️ 找不到節目：{label}")
            return

        # ⛔ 判斷是否在過去
        if not self.can_delete_block(block_to_remove):
            log(f"⛔ 節目 {label} 已在過去，不可刪除")
            return

        # ✅ 找出場景中的 block item 並刪除
        for item in self.blocks:
            if item.label == label:
                self.scene.removeItem(item)
                self.blocks.remove(item)
                break

        # ✅ 從 block_data 移除
        self.block_data = [b for b in self.block_data if b["label"] != label]
        self.save_schedule()

    def set_start_date(self, qdate):
        self.base_date = qdate
        self.draw_grid()
    # def save_schedule(self, filename="schedule.json"):
    #     try:
    #     # ✅ 用 dict 快速對應 block_id → block_data
    #         block_map = {b["id"]: b for b in self.block_data if b.get("id")}

    #         now = QDateTime.currentDateTime()

    #         # ✅ 同步畫面上的 TimeBlock 狀態
    #         for item in self.scene.items():
    #             if isinstance(item, TimeBlock) and item.block_id in block_map:
    #                 start_dt = QDateTime(item.start_date, QTime(int(item.start_hour), int((item.start_hour % 1) * 60)))
    #                 if start_dt >= now:
    #                     block_map[item.block_id]["status"] = item.status  # ✅ 寫入最新狀態

    #         # ✅ 寫入 JSON 檔
    #         with open(filename, "w", encoding="utf-8") as f:
    #             json.dump([
    #                 {
    #                     "qdate": b["qdate"].toString("yyyy-MM-dd"),
    #                     "track_index": b["track_index"],
    #                     "start_hour": b["start_hour"],
    #                     "duration": b["duration"],
    #                     "end_hour": b["end_hour"],
    #                     "end_qdate": (
    #                         b["end_qdate"].toString("yyyy-MM-dd") if isinstance(b["end_qdate"], QDate)
    #                         else b["end_qdate"]
    #                     ),
    #                     "label": b["label"],
    #                     "id": b.get("id"),
    #                     "encoder_name": b.get("encoder_name"),
    #                     "snapshot_path": b.get("snapshot_path", ""),
    #                     "status": b.get("status", "")  # ✅ 最終會寫入最新的狀態（等待中、已結束等）
    #                 } for b in self.block_data
    #             ], f, ensure_ascii=False, indent=2)
    #         log("✅ 已儲存節目排程 schedule.json")
    #     except Exception as e:
    #         log(f"❌ 儲存失敗: {e}")

    
    def save_schedule(self, filename=None):
        try:
            # ✅ 如果使用者選過排程檔，優先使用該路徑
            if filename is None and hasattr(self, "schedule_file"):
                filename = self.schedule_file

            # ✅ fallback：使用 Documents 預設儲存路徑
            if filename is None:
                documents_dir = os.path.join(os.path.expanduser("~"), "Documents", "schedule_saved")
                os.makedirs(documents_dir, exist_ok=True)
                filename = os.path.join(documents_dir, "schedule.json")

            block_map = {b["id"]: b for b in self.block_data if b.get("id")}
            now = QDateTime.currentDateTime()

            for item in self.scene.items():
                if isinstance(item, TimeBlock) and item.block_id in block_map:
                    start_dt = QDateTime(item.start_date, QTime(int(item.start_hour), int((item.start_hour % 1) * 60)))
                    if start_dt >= now:
                        block_map[item.block_id]["status"] = item.status

            with open(filename, "w", encoding="utf-8") as f:
                json.dump([
                    {
                        "qdate": b["qdate"].toString("yyyy-MM-dd"),
                        "track_index": b["track_index"],
                        "start_hour": b["start_hour"],
                        "duration": b["duration"],
                        "end_hour": b["end_hour"],
                        "end_qdate": (
                            b["end_qdate"].toString("yyyy-MM-dd") if isinstance(b["end_qdate"], QDate)
                            else b["end_qdate"]
                        ),
                        "label": b["label"],
                        "id": b.get("id"),
                        "encoder_name": b.get("encoder_name"),
                        "snapshot_path": b.get("snapshot_path", ""),
                        "status": b.get("status", "")
                    } for b in self.block_data
                ], f, ensure_ascii=False, indent=2)

            log(f"✅ 已儲存節目排程：{filename}")
        except Exception as e:
            log(f"❌ 儲存失敗: {e}")



    def load_schedule(self, filename=None):
        if filename is None:
            # 嘗試從 config.json 讀取使用者設定的 schedule 檔案路徑
            if os.path.exists("config.json"):
                try:
                    with open("config.json", "r", encoding="utf-8") as f:
                        config = json.load(f)
                        filename = config.get("schedule_file", "schedule.json")
                except Exception as e:
                    log(f"⚠️ 無法從 config.json 取得 schedule 檔：{e}")
                    filename = "schedule.json"
            else:
                filename = "schedule.json"

        try:
            with open(filename, "r", encoding="utf-8") as f:
                raw = json.load(f)
                self.block_data = [
                    {
                        "qdate": QDate.fromString(b["qdate"], "yyyy-MM-dd"),
                        "track_index": b["track_index"],
                        "start_hour": b["start_hour"],
                        "duration": b["duration"],
                        "end_hour": b.get("end_hour", b["start_hour"] + b["duration"]),
                        "end_qdate": QDate.fromString(b.get("end_qdate"), "yyyy-MM-dd") if b.get("end_qdate") else None,
                        "label": b["label"],
                        "id": b.get("id"),
                        "encoder_name": b.get("encoder_name"),
                        # "snapshot_path": b.get("snapshot_path", ""),
                        "status": b.get("status", "")
                    } for b in raw
                ]
            self.draw_grid()
            log(f"📂 已載入節目排程 {filename}")
        except FileNotFoundError:
            log(f"🕘 無 {filename} 檔案，自動跳過載入。")


    def stop_timers(self):
            if hasattr(self, "now_timer"):
                self.now_timer.stop()
            if hasattr(self, "global_timer"):
                self.global_timer.stop()