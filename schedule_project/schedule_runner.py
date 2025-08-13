# schedule_runner.py

from encoder_controller import EncoderController 
from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, QDateTime, QDate, QTime, Signal
from encoder_utils import connect_socket, send_encoder_command, send_persistent_command
from encoder_status_manager import EncoderStatusManager
import os
import logging
import threading
from PySide6.QtWidgets import QApplication
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
        self.refresh_encoder_statuses()
        self._pool = QThreadPool.globalInstance()
    def _refresh_status_async(self):
        log(f"🎯 啟動 StatusWorker：{self.encoder_names}")
        worker = _StatusWorker(self.encoder_names, self.encoder_status_manager)  # ⬅️ 改這個
        worker.signals.done.connect(self._apply_statuses)
        self._pool.start(worker)


    def _apply_statuses(self, statuses: dict):
        for name, (text, color) in statuses.items():
            label = self.encoder_status.get(name)  # ⬅️ 用這個
            if label:
                label.setText(f"狀態：{text}")
                label.setStyleSheet(f"color: {color}")

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
        encoder_index = self.encoder_names.index(encoder_name)

        if ok:
            for block in self.blocks:
                if block.track_index == encoder_index:
                    start_dt = QDateTime(block.start_date, QTime(int(block.start_hour), int((block.start_hour % 1) * 60)))
                    end_dt = start_dt.addSecs(int(block.duration_hours * 3600))
                    if start_dt <= now <= end_dt:
                        block.status = "⏹ 停止中"
                        block.update_text_position()
                        self.already_stopped.add(block.block_id)
                        # ✅ 儲存狀態回 block_data
                        for b in self.schedule_data:
                            if b.get("id") == block.block_id:
                                b["status"] = block.status  # ⬅️ 儲存下來
            safe_set_label(status_label, "狀態：⏹ 停止中", "color: gray")
        else:
            safe_set_label(status_label, "狀態：❌ 停止失敗", "color: red")

   

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
        self.timer.stop()
        self.status_timer.stop()