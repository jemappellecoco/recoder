from PySide6.QtWidgets import QGraphicsView, QGraphicsScene
from PySide6.QtCore import Qt, QDate, QTimer,QDateTime, QTime,QObject, Signal, QRunnable, QThreadPool
 # 若上面沒 import 到就補上
from PySide6.QtGui import QPainter, QFont,QPen,QColor
from time_block import TimeBlock
import json
from encoder_status_manager import EncoderStatusManager
import os
import uuid
from shiboken6 import isValid
from utils import hours_to_hhmm, hhmm_to_hours ,hourf_to_qtime
# from utils import min_to_hhmm, hours_to_hhmm
from utils import log,hourf_to_qtime
from encoder_utils import get_encoder_display_name
from path_manager import PathManager 
class _TrackLabelWorkerSignals(QObject):
    done = Signal(dict)  # {encoder_name: (status_text, color)}

class _TrackLabelWorker(QRunnable):
    def __init__(self, names, status_manager):
        super().__init__()
        self.names = names
        self.status_manager = status_manager
        self.signals = _TrackLabelWorkerSignals()

    def run(self):
        try:
            result = self.status_manager.refresh_all(self.names)
            # ✅ 發射前確認 signal 來源仍有效
            if self.signals and isValid(self.signals):
                self.signals.done.emit(result)
        except Exception:
            # ✅ 就算失敗也先確保 signal 還活著再 emit
            try:
                if self.signals and isValid(self.signals):
                    self.signals.done.emit({})
            except Exception:
                # signals 已不存在就安靜結束
                pass
class ScheduleView(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.encoder_labels = {}
        self.blocks = []
        self.block_data = []
        self.orphan_blocks = []
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
        self.encoder_status_manager = EncoderStatusManager()
        self._pool = QThreadPool.globalInstance()
        
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self.refresh_track_labels)  # 只丟 worker，不做 I/O
        self._status_timer.start(2000)  # 每 2 秒觸發一次背景刷新
        
        self.block_status_timer = QTimer(self)
        self.block_status_timer.timeout.connect(self.update_all_blocks)  # 見下方新函式
        self.block_status_timer.start(1000)  # 每秒更新一次（可改 2000/5000）
        self._pool = QThreadPool.globalInstance()
        self._bg_workers = []      # ✅ 保存背景任務，避免被 GC
        
    def get_now_x(self) -> int | None:
        now = QDateTime.currentDateTime()
        days = self.base_date.daysTo(now.date())
        if not (0 <= days < self.days):
            return None
        t = now.time()
        hours = t.hour() + t.minute() / 60 + t.second() / 3600
        return int(days * self.day_width + hours * self.hour_width)

    def center_on_x(self, x: int):
        sb = self.horizontalScrollBar()
        target = int(x - self.viewport().width() / 2)
        sb.setValue(max(sb.minimum(), min(sb.maximum(), target)))

    def center_on_now(self):
        x = self.get_now_x()
        if x is not None:
            self.center_on_x(x)
    def set_track_label_status(self, encoder_name: str, status_text: str | None, color: str = "black"):
        """供外部（MainWindow）呼叫：把某台 encoder 的狀態顯示在左側標題行。"""
        item = self.encoder_labels.get(encoder_name)
        if not item:
            return
        alias = get_encoder_display_name(encoder_name)
        # 你若真的要完全「不顯示狀態」，就把下一行改成：text = alias
        text = alias if not status_text else f"{alias}\n狀態：{status_text}"
        item.setPlainText(text)
        item.setDefaultTextColor(QColor(color))
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
        
    # def update_all_blocks(self):
    #         # 只更新畫面內的 block，省資源
    #     visible_scene_rect = self.mapToScene(self.viewport().rect()).boundingRect()
    #     for item in self.scene.items(visible_scene_rect):
    #         if isinstance(item, TimeBlock):
    #             item.update_status_by_time()
    def update_all_blocks(self):
        visible_scene_rect = self.mapToScene(self.viewport().rect()).boundingRect()
        any_changed = False
        for item in self.scene.items(visible_scene_rect):
            if isinstance(item, TimeBlock):
                changed = item.update_status_by_time()
                any_changed = any_changed or bool(changed)

        # 節流（例如 10 秒內只存一次）
        if any_changed:
            now = QDateTime.currentDateTime()
            if not hasattr(self, "_last_auto_save") or self._last_auto_save.msecsTo(now) > 10_000:
                self.save_schedule()
                self._last_auto_save = now   # ← 修正這行
    def refresh_track_labels(self):
        # 啟動背景 worker 查詢所有 encoder 狀態
        worker = _TrackLabelWorker(list(self.encoder_names), self.encoder_status_manager)

        # ✅ 持有 worker，避免 signals 被回收
        self._bg_workers.append(worker)

        def _on_done(result, w=worker):
            # 視圖已關閉或正在關閉就跳過
            if getattr(self, "_is_closing", False) or not isValid(self):
                pass
            else:
                self._apply_track_label_statuses(result)
            # ✅ 用完就移除引用
            try:
                self._bg_workers.remove(w)
            except ValueError:
                pass

        worker.signals.done.connect(_on_done)
        self._pool.start(worker)
    def _apply_track_label_statuses(self, statuses: dict):
        for name, pair in statuses.items():
            if not isinstance(pair, (tuple, list)) or len(pair) < 2:
                continue
            status_text, color = pair
            label_item = self.encoder_labels.get(name)
            if not (label_item and isValid(label_item)):
                # 物件已失效就拔掉 mapping，避免下次再碰
                self.encoder_labels.pop(name, None)
                continue
            alias = get_encoder_display_name(name)
            full_label = f"{alias}\n狀態：{status_text}"
            label_item.setPlainText(full_label)
            label_item.setDefaultTextColor(QColor(color))

    def draw_grid(self):
        log(f"🎯 draw_grid encoder_names:{self.encoder_names}")

        offset = self.grid_top_offset
        self.scene.clear()
        self.tracks = len(self.encoder_names)
        self.update_scene_rect()
        self.verticalScrollBar().setValue(0)

        # 仍保留原本用 item 畫格線（先不動），只是先解決同步查詢卡頓
        for day in range(self.days):
            for hour in range(24):
                x = day * self.day_width + hour * self.hour_width
                self.scene.addLine(x, offset, x, offset + self.tracks * 100, Qt.DotLine)

        for day in range(self.days):
            x = day * self.day_width
            self.scene.addRect(x, offset, self.day_width, self.tracks * 100)

        # 🔄 每個 track 標籤（改成占位，不同步查 EncStatus）
        self.encoder_labels.clear()  # 先清一次，避免殘留舊 mapping
        for track in range(self.tracks):
            y = offset + track * 100
            self.scene.addLine(0, y, self.days * self.day_width, y)

            if track < len(self.encoder_names):
                encoder_name = self.encoder_names[track]
                alias = get_encoder_display_name(encoder_name)
                full_label = f"{alias}"   # ⬅️ 占位
                color = "black"
            else:
                full_label = "未指定\n--"
                color = "black"
                encoder_name = None

            label_item = self.scene.addText(full_label)
            label_item.setFont(QFont("Arial", 9))
            label_item.setDefaultTextColor(QColor(color))
            label_item.setPos(-95, y)

            if encoder_name is not None:
                self.encoder_labels[encoder_name] = label_item  # 之後 refresh 用
        
        self.draw_blocks()
        for blk in getattr(self, "blocks", []):
            bd = next((b for b in self.block_data if b.get("id") == blk.block_id), None)
            if not bd:
                continue
            s = str(bd.get("status", "") or "")
            if s.startswith("狀態：❌"):
                blk.set_state("ABORTED", force=True)
                blk.update_text_position()
            elif s == blk.STATUS_TEXT["FINISHED"]:
                blk.set_state("FINISHED", force=True)
                blk.update_text_position()
        self.update_now_line()
        self.verticalScrollBar().setValue(self.verticalScrollBar().minimum())

        # ✅ 用背景 worker 批次刷新真實狀態（不阻塞 UI）
        # self.refresh_track_labels()
        
  

    def update_scene_rect(self):
        self.tracks = len(self.encoder_names)
        # scene_height = self.tracks * 100 + 40
        scene_height = self.tracks * 100 + self.grid_top_offset
        scene_width = self.days * self.day_width + 150
        self.setSceneRect(-120, 0, scene_width, scene_height)
    def draw_blocks(self):
            # 建立舊 block 映射（label → block）以便繼承狀態
        # old_block_map = {block.label: block for block in self.blocks}
        old_block_map = {}
        for block in self.blocks:
            key = getattr(block, "block_id", None) or block.label
            old_block_map[key] = block
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
                # block.status = data.get("status") or "狀態：⏳ 等待中"
                # ⬇️ 這裡插入
                stored = data.get("status")
                if stored:
                    block.status = stored
                    # block.update_text_position()
                    # block.update_status_by_time()
                else:
                    block.update_status_by_time()
                block.update_text_position()
                # # ✅ 立刻依現在時間套狀態（等待中／已結束）
                # block.update_status_by_time()
                # 從舊 block 繼承狀態與圖片
                # old_block = old_block_map.get(data["label"])
                old_block = old_block_map.get(data.get("id")) or old_block_map.get(data["label"])
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
        # 允許傳進來的是 str / QDate
        if isinstance(qdate, str):
            qdate = QDate.fromString(qdate, "yyyy-MM-dd")

        # 新區間：用 QDateTime + addSecs(round(...))，精確又可自動跨日
        new_start_dt = QDateTime(qdate, hourf_to_qtime(float(start_hour)))
        new_end_dt   = new_start_dt.addSecs(int(round(float(duration) * 3600)))

        for block in self.block_data:
            if block["track_index"] != track_index:
                continue

            # 若 exclude_label 是 block id，就跳過自己
            if exclude_label and block.get("id") == exclude_label:
                continue

            b_qdate = block["qdate"]
            if isinstance(b_qdate, str):
                b_qdate = QDate.fromString(b_qdate, "yyyy-MM-dd")

            b_start_hour = float(block["start_hour"])
            b_duration   = float(block["duration"])

            b_start_dt = QDateTime(b_qdate, hourf_to_qtime(b_start_hour))
            b_end_dt   = b_start_dt.addSecs(int(round(b_duration * 3600)))

            # 區間交集： [new_start_dt, new_end_dt) 與 [b_start_dt, b_end_dt)
            if new_start_dt < b_end_dt and new_end_dt > b_start_dt:
                log(f"🔴 重疊偵測：與 {block['label']} 發生重疊")
                return True

        return False
    # def is_overlap(self, qdate, track_index, start_hour, duration, exclude_label=None):
    #     new_start_dt = QDateTime(qdate, QTime(int(start_hour), int((start_hour % 1) * 60)))
    #     end_hour = start_hour + duration
    #     end_qdate = qdate.addDays(1) if end_hour >= 24 else qdate
    #     new_end_dt = QDateTime(end_qdate, QTime(int(end_hour % 24), int(((end_hour % 1) * 60))))

    #     for block in self.block_data:
    #         if block["track_index"] != track_index:
    #             continue

    #         # ✅ 用 exclude_label 當作 exclude_id（只要確定你傳的是 block["id"]）
    #         if exclude_label and block.get("id") == exclude_label:
    #             continue  

    #         b_start_hour = float(block["start_hour"])
    #         b_end_hour = float(block.get("end_hour", b_start_hour + block["duration"]))
    #         b_qdate = block["qdate"]
    #         if isinstance(b_qdate, str):
    #             b_qdate = QDate.fromString(b_qdate, "yyyy-MM-dd")
    #         b_end_qdate = block.get("end_qdate", b_qdate.addDays(1) if b_end_hour >= 24 else b_qdate)

    #         b_start_dt = QDateTime(b_qdate, QTime(int(b_start_hour), int((b_start_hour % 1) * 60)))
    #         b_end_dt = QDateTime(b_end_qdate, QTime(int(b_end_hour % 24), int((b_end_hour % 1) * 60)))

    #         if new_start_dt < b_end_dt and new_end_dt > b_start_dt:
    #             log(f"🔴 重疊偵測：與 {block['label']} 發生重疊")
    #             return True

    #     return False
    

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
        start_dt = QDateTime(block["qdate"], hourf_to_qtime(float(block["start_hour"])))
        return start_dt >= now
    # def can_delete_block(self, block):
    #     now = QDateTime.currentDateTime()
    #     start_dt = QDateTime(block["qdate"], QTime(int(block["start_hour"]), int((block["start_hour"] % 1) * 60)))
    #     return start_dt >= now    
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
            # now = QDateTime.currentDateTime()
            for item in self.scene.items():
                if isinstance(item, TimeBlock) and item.block_id in block_map:
                    # 以畫面上 TimeBlock 的狀態為準，無條件回寫
                    block_map[item.block_id]["status"] = item.status
            
            with open(filename, "w", encoding="utf-8") as f:
                
                json.dump([{
                    "qdate": b["qdate"].toString("yyyy-MM-dd"),
                    "track_index": b["track_index"],
                    "start_time": hours_to_hhmm(b["start_hour"]),     # HH:MM
                    "duration_time": hours_to_hhmm(b["duration"]),    # HH:MM
                    "end_time": hours_to_hhmm(b["end_hour"]),         # HH:MM
                    "end_qdate": (
                        b["end_qdate"].toString("yyyy-MM-dd")
                        if isinstance(b["end_qdate"], QDate) else str(b["end_qdate"])
                    ),
                    "label": b["label"],
                    "id": b.get("id"),
                    "encoder_name": b.get("encoder_name"),
                    "snapshot_path": b.get("snapshot_path",""),
                    "status": b.get("status","")
                } for b in self.block_data], f, ensure_ascii=False, indent=2)
            log(f"✅ 已儲存節目排程：{filename}")
        except Exception as e:
            log(f"❌ 儲存失敗: {e}",level="ERROR")


    def load_schedule(self, filename=None):
        if filename is None:
            # 嘗試從 config.json 讀取使用者設定的 schedule 檔案路徑
            if os.path.exists("config.json"):
                try:
                    with open("config.json", "r", encoding="utf-8") as f:
                        config = json.load(f)
                        filename = config.get("schedule_file", "schedule.json")
                except Exception as e:
                    log(f"⚠️ 無法從 config.json 取得 schedule 檔：{e}", level="ERROR")
                    filename = "schedule.json"
            else:
                filename = "schedule.json"

        try:
            with open(filename, "r", encoding="utf-8") as f:
                raw = json.load(f)

            new_data = []
            for b in raw:
                # 1) 讀日期
                qdate = QDate.fromString(b["qdate"], "yyyy-MM-dd")
                end_qdate = QDate.fromString(b.get("end_qdate") or b["qdate"], "yyyy-MM-dd")

                # 2) HH:MM 轉回內部浮點小時
                start_hour = hhmm_to_hours(b["start_time"])
                duration   = hhmm_to_hours(b["duration_time"])
                end_hour   = hhmm_to_hours(b["end_time"]) if b.get("end_time") else (start_hour + duration)

                # 3) 其他欄位容錯
                label = b.get("label", "")
                try:
                    track_idx = int(b.get("track_index", 0))
                except Exception:
                    track_idx = 0

                new_data.append({
                    "qdate": qdate,
                    "track_index": track_idx,
                    "start_hour": start_hour,    # ✅ 內部一律用 float 小時
                    "duration": duration,
                    "end_hour": end_hour,
                    "end_qdate": end_qdate,
                    "label": label,
                    "id": b.get("id"),
                    "encoder_name": b.get("encoder_name"),
                    "snapshot_path": b.get("snapshot_path", ""),
                    "status": b.get("status", "")
                })

            self.block_data = new_data
            self.remap_block_tracks()
            self.draw_grid()
            log(f"📂 已載入節目排程 {filename}")
        except FileNotFoundError:
            log(f"🕘 無 {filename} 檔案，自動跳過載入。")
        except Exception as e:
            log(f"❌ 載入失敗：{e}", level="ERROR")

    # def stop_timers(self):
    #         if hasattr(self, "now_timer"):
    #             self.now_timer.stop()
    #         if hasattr(self, "global_timer"):
    #             self.global_timer.stop()
    def stop_timers(self):
        if hasattr(self, "now_timer"):
            self.now_timer.stop()
        if hasattr(self, "global_timer"):
            self.global_timer.stop()
        if hasattr(self, "_status_timer"):
            self._status_timer.stop()
        if hasattr(self, "block_status_timer"):
            self.block_status_timer.stop()
        self._is_closing = True  # ✅ 告知背景回來時別再碰 UI
    def set_encoder_names(self, names):
        self.encoder_names = names
        self.update()
    def rebuild_tracks(self):
        """Rebuild grid and blocks after encoder list is updated."""
        self.tracks = len(self.encoder_names)
        self.update_scene_rect()
        self.draw_grid()
    def remap_block_tracks(self):
        """Remap block track indices and collect blocks without encoder."""
        valid_blocks = []
        orphans = list(self.orphan_blocks)

        for block in self.block_data:
            name = block.get("encoder_name")
            track = block.get("track_index")

            if name:  # ➤ 若有 encoder_name
                if name in self.encoder_names:
                    # ✅ encoder_name 合法，依名稱設定 track_index
                    block["track_index"] = self.encoder_names.index(name)
                    valid_blocks.append(block)
                else:
                    # ⚠️ 名稱不存在於 encoder 名單
                    log(f"⚠️ 無效的 encoder_name: {name}，暫存為孤兒")
                    orphans.append(block)
            else:  # ➤ 無 encoder_name
                if isinstance(track, int) and 0 <= track < len(self.encoder_names):
                    # ✅ 根據 track_index 回填 encoder_name
                    block["encoder_name"] = self.encoder_names[track]
                    valid_blocks.append(block)
                else:
                    # ⚠️ 無效資訊，忽略此區塊
                    log(f"⚠️ 無效的 track_index: {track}，已忽略")

        self.block_data = valid_blocks
        self.orphan_blocks = orphans
    def restore_orphan_blocks(self):
        """Try to reattach orphan blocks to block_data when encoder returns."""
        if not self.orphan_blocks:
            return
        remaining = []
        for block in self.orphan_blocks:
            name = block.get("encoder_name")
            if name in self.encoder_names:
                block["track_index"] = self.encoder_names.index(name)
                self.block_data.append(block)
                log(f"🔄 恢復孤兒節目：{block['label']}")
            else:
                remaining.append(block)
        self.orphan_blocks = remaining

    def purge_orphan_blocks(self):
        """Permanently delete all orphan blocks."""
        count = len(self.orphan_blocks)
        self.orphan_blocks = []
        log(f"🗑️ 已清除 {count} 個孤兒節目")