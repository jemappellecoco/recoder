# schedule_runner.py

from encoder_controller import EncoderController 
from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, QDateTime, QDate, QTime, Signal
from encoder_utils import connect_socket, send_encoder_command, send_persistent_command
from encoder_status_manager import EncoderStatusManager
import os
import logging
import threading
from PySide6.QtWidgets import QApplication,QGraphicsOpacityEffect
from shiboken6 import isValid
# from check_schedule_manager import CheckScheduleManager
from capture import take_snapshot_from_block 
from utils import log   
REFRESH_INTERVAL_MS =10*1000
class _StatusWorkerSignals(QObject):
    done = Signal(dict)  # {name: (text, color)}

class _StatusWorker(QRunnable):
    def __init__(self, names, status_manager):
        super().__init__()
        self.names = names
        self.status_manager = status_manager
        self.signals = _StatusWorkerSignals()
    def run(self):
        from utils import log
        result = {}
        try:
            for name in self.names:
                if not name or not isinstance(name, str):
                    log(f"⚠️ 無效 encoder 名稱: {name}", level="WARNING")
                    continue
                try:
                    stat = self.status_manager.get_status(name)
                    if stat:
                        result[name] = stat
                except Exception as e:
                    log(f"❌ get_status({name}) 發生例外：{e}")
                    result[name] = ("❌ 無法連線", "red")
            # ✅ signals 還活著才 emit
            if self.signals and isValid(self.signals):
                self.signals.done.emit(result)
        except Exception as e:
            log(f"❌ _StatusWorker.run() 整體執行失敗：{e}", level="ERROR")
        
def safe_set_label(label, text, style):
    if not label or not isValid(label):
        return
    label.setText(text)
    label.setStyleSheet(style)
class ScheduleRunner(QObject):
    snapshot_result = Signal(str, str)  # block_id, snapshot path

    def __init__(self, schedule_data, encoder_status, record_root, encoder_names, blocks):
        super().__init__()
        self.schedule_data = schedule_data
        self.encoder_status = encoder_status
        self.record_root = record_root
        self.encoder_names = encoder_names
        self.blocks = blocks  # 傳入 TimeBlock 實例列表
        self.encoder_controller = EncoderController(self.record_root)
        self.already_started = set()
        self.already_stopped = set()
        
        self.timer = QTimer(self)
        # self.timer.timeout.connect(self.check_schedule)
        self.timer.start(1000)  # 每秒檢查一次
        self.encoder_last_state = {}
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self._refresh_status_async)

        self.status_timer.start(REFRESH_INTERVAL_MS)

        self.snapshot_result.connect(self._handle_snapshot_result)
        self.encoder_status_manager = EncoderStatusManager()
                # ✅ 自動更新 block 顯示狀態
        self.block_status_timer = QTimer(self)
        self.block_status_timer.timeout.connect(self._refresh_block_statuses)
        self.block_status_timer.start(3000)  # 每秒更新一次
        # ✅ 改為使用 thread pool 異步刷新，避免啟動時卡 UI
        self._pool = QThreadPool.globalInstance()
        self._status_workers = []   # ✅ 持有 worker，避免 signals 被 GC
        self._is_closing = False    # ✅ 關閉旗標
        QTimer.singleShot(0, self._refresh_status_async)
    def _refresh_block_statuses(self):
        self._refresh_status_async()
    def _refresh_status_async(self):
        log(f"🎯 啟動 StatusWorker：{self.encoder_names}")
        if self._is_closing or not getattr(self, "encoder_names", None):
            return
            # ⛑️ 若上一輪尚未回來，就先不再開新的一輪
        if getattr(self, "_status_workers", None) and len(self._status_workers) >= 1:
            return
        worker = _StatusWorker(list(self.encoder_names), self.encoder_status_manager)

        # ✅ 持有，避免 signals 被回收
        self._status_workers.append(worker)

        def _on_done(result, w=worker):
            # 視窗關閉或 runner 被收時，不再碰 UI
            if not hasattr(self, "_is_closing") or self._is_closing:
                pass
            else:
                try:
                    self._apply_statuses(result)
                except Exception as e:
                    log(f"❌ _apply_statuses error: {e}")
            # ✅ 用完釋放引用
            try:
                self._status_workers.remove(w)
            except ValueError:
                pass

        worker.signals.done.connect(_on_done)
        self._pool.start(worker)

    # def _refresh_status_async(self):
    #     log(f"🎯 啟動 StatusWorker：{self.encoder_names}")
    #     if not getattr(self, "encoder_names", None):
    #         return
    #     worker = _StatusWorker(self.encoder_names, self.encoder_status_manager)
    #     worker.signals.done.connect(self._apply_statuses)
    #     self._pool.start(worker)

    def _set_opacity(self, widget, value: float):
        if not widget or not isValid(widget):
            return
        eff = widget.graphicsEffect()
        if not isinstance(eff, QGraphicsOpacityEffect):
            eff = QGraphicsOpacityEffect(widget)
            widget.setGraphicsEffect(eff)
        eff.setOpacity(value)
    def _get_widget(self, mapping: dict, name: str):
        """拿到還活著的 widget；死了就從 mapping 移除並回傳 None。"""
        if not isinstance(mapping, dict):
            return None
        w = mapping.get(name)
        if not w or not isValid(w):
            mapping.pop(name, None)
            return None
        return w
    def _apply_statuses(self, statuses: dict):
        current = set(getattr(self, "encoder_names", []) or [])
        for name, pair in statuses.items():
            # 這台已被刪除 → 清 mapping、跳過
            if name not in current:
                for m in (
                    getattr(self, "encoder_status", None),
                    getattr(self, "start_buttons", None),
                    getattr(self, "stop_buttons", None),
                    getattr(self, "filename_inputs", None),
                ):
                    if isinstance(m, dict):
                        m.pop(name, None)
                continue

            try:
                text, color = pair
            except Exception:
                text, color = ("❓ 未知", "gray")

            # label
            label = self._get_widget(getattr(self, "encoder_status", {}), name)
            if label:
                try:
                    label.setText(f"狀態：{text}")
                    label.setStyleSheet(f"color: {color}")
                except RuntimeError:
                    getattr(self, "encoder_status", {}).pop(name, None)
                    label = None

            is_running = ("錄影中" in text)

            # 控制項
            start_btn  = self._get_widget(getattr(self, "start_buttons", {}), name)
            stop_btn   = self._get_widget(getattr(self, "stop_buttons", {}), name)
            name_input = self._get_widget(getattr(self, "filename_inputs", {}), name)

            try:
                if start_btn:
                    start_btn.setDisabled(is_running)
                    self._set_opacity(start_btn, 0.45 if is_running else 1.0)
            except RuntimeError:
                getattr(self, "start_buttons", {}).pop(name, None)

            try:
                if name_input:
                    name_input.setDisabled(is_running)
                    self._set_opacity(name_input, 0.45 if is_running else 1.0)
            except RuntimeError:
                getattr(self, "filename_inputs", {}).pop(name, None)

            try:
                if stop_btn:
                    stop_btn.setDisabled(not is_running)
                    self._set_opacity(stop_btn, 1.0 if is_running else 0.45)
            except RuntimeError:
                getattr(self, "stop_buttons", {}).pop(name, None)

    def refresh_encoder_statuses(self):
        statuses = self.encoder_status_manager.refresh_all(self.encoder_names)
        for name, (status_text, color) in statuses.items():
            if name in self.encoder_status:
                self.encoder_status[name].setText(f"狀態：{status_text}")
                self.encoder_status[name].setStyleSheet(f"color: {color}")

    def format_remaining_time(self, seconds):
        h = int(seconds) // 3600
        m = (int(seconds) % 3600) // 60
        s = int(seconds) % 60
        return f"{h:02d}:{m:02d}:{s:02d}"
    
   

    def _handle_snapshot_result(self, block_id: str, snapshot_path: str):
        """Update UI when snapshot is finished in background thread."""
        try:
            block = self.find_block_by_id(block_id)
            if block and snapshot_path:
                img_dir = os.path.dirname(snapshot_path)
                block.load_preview_images(img_dir)
            else:
                log(f"⚠️ 拍照失敗或找不到 block：{block_id}")
        except Exception as e:
            log(f"❌ 更新預覽圖錯誤：{e}")

    def start_encoder(self, encoder_name, filename, status_label, block_id=None):
        if status_label and not isValid(status_label):
            log(f"⚠️ QLabel for {encoder_name} no longer exists; skipping label update")
            status_label = None

        # 先拿到 block（之後才用 block.start_date）
        block = self.find_block_by_id(block_id) if block_id else None

        # 用 block 的日期，避免跨日不一致
        base_date = block.start_date if block else QDate.currentDate()
        date_folder = base_date.toString("MM.dd.yyyy")
        date_prefix = base_date.toString("MMdd")

        full_path = os.path.abspath(os.path.join(self.record_root, date_folder, f"{date_prefix}_{filename}"))
        rel_path = os.path.relpath(full_path, start=self.record_root)

        sock = connect_socket(encoder_name)
        if not sock:
            safe_set_label(status_label, "❌ 無法連線", "color: red;")
        else:
            sock.close()
        res1 = send_encoder_command(encoder_name, f'Setfile "{encoder_name}" 1 "{rel_path}"')
        # res1 = send_encoder_command(encoder_name, f'Setfile "{encoder_name}" 1 {rel_path}')
        res2 = send_encoder_command(encoder_name, f'Start "{encoder_name}" 1')

        if "OK" in res1 and "OK" in res2:
            safe_set_label(status_label, "✅ 錄影中", "color: green;")
        else:
            # 啟動失敗就不要拍照，以免誤判
            safe_set_label(status_label, "狀態：❌ 啟動失敗", "color: red;")
            return

        # ✅ 只在第一次啟動時拍照，避免 check_schedule 觸發多次
        if block_id and block_id not in self.already_started:
            self.already_started.add(block_id)
            log(f"📸 update_all_encoder_snapshots triggered at {QDateTime.currentDateTime().toString('HH:mm:ss.zzz')}")
            window = QApplication.instance().activeWindow()
            if window and not getattr(window, "is_closing", False) and block:
                def worker():
                    try:
                        future = take_snapshot_from_block(
                            block, self.encoder_names, snapshot_root=self.record_root
                        )
                        snapshot_path = None
                        if future is not None:
                            try:
                                snapshot_path = future.result(timeout=6)  # _wait_for_file 預設 5 秒
                            except Exception as e:
                                log(f"⚠️ snapshot future error/timeout：{e}")
                                snapshot_path = None
                        self.snapshot_result.emit(block.block_id, snapshot_path)
                    except Exception as e:
                        log(f"❌ snapshot thread error：{e}")
                        self.snapshot_result.emit(block.block_id if block else "", None)
                threading.Thread(target=worker, daemon=True).start()
            else:
                log("🛑 無視拍照：UI 已關閉或找不到 activeWindow")

        
    def stop_encoder(self, encoder_name, status_label):
        if status_label and not isValid(status_label):
            log(f"⚠️ QLabel for {encoder_name} no longer exists; skipping label update")
            status_label = None

        # safe_set_label(status_label, "狀態：🔁 停止中...", "color: blue")
        QApplication.processEvents()

        ok = self.encoder_controller.stop_encoder(encoder_name)
        now = QDateTime.currentDateTime()

        # ⛔ encoder 可能已被刪除：名稱不在清單就不要做 index() 與 block 更新
        if encoder_name not in getattr(self, "encoder_names", []):
            if ok:
                safe_set_label(status_label, "狀態：⏹ 停止中", "color: gray")
            else:
                safe_set_label(status_label, "狀態：❌ 停止失敗", "color: red")
            return

        # 走到這裡代表還在清單中，才安全取 index
        try:
            encoder_index = self.encoder_names.index(encoder_name)
        except ValueError:
            # 雙保險（極少數 race）
            if ok:
                safe_set_label(status_label, "狀態：⏹ 停止中", "color: gray")
            else:
                safe_set_label(status_label, "狀態：❌ 停止失敗", "color: red")
            return

        if ok:
            # 🔒 block 可能已被移除（scene clear 或重建時），任何 UI 操作包 try/except
            for block in list(getattr(self, "blocks", [])):
                try:
                    if getattr(block, "track_index", None) == encoder_index:
                        start_dt = QDateTime(block.start_date, QTime(int(block.start_hour), int((block.start_hour % 1) * 60)))
                        end_dt = start_dt.addSecs(int(block.duration_hours * 3600))
                        if start_dt <= now <= end_dt:
                            block.status = "⏹ 停止中"
                            try:
                                block.update_text_position()
                            except RuntimeError:
                                pass
                            self.already_stopped.add(getattr(block, "block_id", ""))

                            # ✅ 儲存狀態回 block_data（dict，非 Qt 物件，安全）
                            for b in self.schedule_data:
                                if b.get("id") == getattr(block, "block_id", None):
                                    b["status"] = block.status
                except RuntimeError:
                    # block 物件已在 Qt 端被刪除
                    continue

            safe_set_label(status_label, "狀態：⏹ 停止中", "color: gray")
        else:
            safe_set_label(status_label, "狀態：❌ 停止失敗", "color: red")

    # def stop_encoder(self, encoder_name, status_label):
    #     if status_label and not isValid(status_label):
    #         log(f"⚠️ QLabel for {encoder_name} no longer exists; skipping label update")
    #         status_label = None

    #     # safe_set_label(status_label, "狀態：🔁 停止中...", "color: blue")
    #     QApplication.processEvents()

    #     ok = self.encoder_controller.stop_encoder(encoder_name)
    #     now = QDateTime.currentDateTime()
    #     encoder_index = self.encoder_names.index(encoder_name)

    #     if ok:
    #         for block in self.blocks:
    #             if block.track_index == encoder_index:
    #                 start_dt = QDateTime(block.start_date, QTime(int(block.start_hour), int((block.start_hour % 1) * 60)))
    #                 end_dt = start_dt.addSecs(int(block.duration_hours * 3600))
    #                 if start_dt <= now <= end_dt:
    #                     block.status = "⏹ 停止中"
    #                     block.update_text_position()
    #                     self.already_stopped.add(block.block_id)
    #                     # ✅ 儲存狀態回 block_data
    #                     for b in self.schedule_data:
    #                         if b.get("id") == block.block_id:
    #                             b["status"] = block.status  # ⬅️ 儲存下來
    #         safe_set_label(status_label, "狀態：⏹ 停止中", "color: gray")
    #     else:
    #         safe_set_label(status_label, "狀態：❌ 停止失敗", "color: red")

   

    def find_block_by_label(self, label):
        for block in self.blocks:
            if block.label == label:
                return block
        return None
    def find_block_by_id(self, block_id):
        for block in self.blocks:
            if block.block_id == block_id:
                return block
        return None
    
    def stop_timers(self):
        self._is_closing = True   # ✅ 通知不要再啟新 worker/不要更新 UI
        if hasattr(self, "timer"):
            self.timer.stop()
        if hasattr(self, "status_timer"):
            self.status_timer.stop()
        if hasattr(self, "block_status_timer"):
            self.block_status_timer.stop()
        if hasattr(self, "runner"):
            self.runner.stop_timers()
    # def stop_timers(self):
    #     self.timer.stop()
    #     self.status_timer.stop()