# schedule_runner.py
from encoder_controller import EncoderController 
from PySide6.QtCore import QObject, QTimer, QDateTime, QDate, QTime
from encoder_utils import connect_socket, send_encoder_command, send_persistent_command
import os
import logging
from PySide6.QtWidgets import QApplication
# from check_schedule_manager import CheckScheduleManager
from capture import take_snapshot_from_block 
from utils import log   
REFRESH_INTERVAL_MS = 8 * 60 * 1000
class ScheduleRunner(QObject):
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
        self.status_timer.timeout.connect(self.refresh_encoder_statuses)
        
        self.status_timer.start(REFRESH_INTERVAL_MS)  
    def format_remaining_time(self, seconds):
        h = int(seconds) // 3600
        m = (int(seconds) % 3600) // 60
        s = int(seconds) % 60
        return f"{h:02d}:{m:02d}:{s:02d}"
    
    def compute_status(self, now: QDateTime, start_dt: QDateTime, end_dt: QDateTime) -> str:
        if now > end_dt:
            return "狀態：⏹ 已結束"
        elif now < start_dt:
            return "狀態：⏳ 等待中"
        else:
            remaining = end_dt.toSecsSinceEpoch() - now.toSecsSinceEpoch()
            return f"狀態：✅ 錄影中\n剩餘 {self.format_remaining_time(remaining)}"

    # def check_schedule(self):
    #     now = QDateTime.currentDateTime()

    #     for b in self.schedule_data:
    #         block_id = b.get("id")

    #         if block_id in self.already_stopped:
    #             continue  # 🛑 已停止，不再處理

    #         # 解析日期時間資訊
    #         qdate = b["qdate"]
    #         if isinstance(qdate, str):
    #             qdate = QDate.fromString(qdate, "yyyy-MM-dd")

    #         end_qdate = b.get("end_qdate", qdate)
    #         if isinstance(end_qdate, str):
    #             end_qdate = QDate.fromString(end_qdate, "yyyy-MM-dd")

    #         start_hour = float(b["start_hour"])
    #         end_hour = b.get("end_hour", b["start_hour"] + b["duration"])

    #         start_dt = QDateTime(qdate, QTime(int(start_hour), int((start_hour % 1) * 60)))
    #         end_dt = QDateTime(end_qdate, QTime(int(end_hour), int((end_hour % 1) * 60)))

    #         # 若已經完全過期，略過
    #         if now > end_dt:
    #             continue

    #         # Encoder 資訊
    #         track_index = b["track_index"]
    #         encoder_name = self.encoder_names[track_index]
    #         status_label = self.encoder_status.get(encoder_name)
    #         block = self.find_block_by_id(block_id)
    #          # ✅ 若在錄影中區間，啟動錄影（只執行一次）
    #         if start_dt <= now < end_dt and block_id not in self.already_started:
    #             log(f"🚀 啟動錄影: {b['label']} ({block_id})")
    #             self.start_encoder(encoder_name, b["label"], status_label, block_id)
    #             self.already_started.add(block_id)
            
    #         elif now >= end_dt and block_id not in self.already_stopped:
    #             self.stop_encoder(encoder_name, status_label)
    #             self.already_stopped.add(block_id)
    #             if block:
    #                 block.status = self.compute_status(now, start_dt, end_dt)
    #                 block.update_text_position()

    #   # ✅ 統一檢查狀態是否改變 → 再決定要不要存檔
    #     save_needed = False
    #     block_map = {b["id"]: b for b in self.schedule_data if b.get("id")}
    #     now = QDateTime.currentDateTime()

    #     for item in self.blocks:
    #         b = block_map.get(item.block_id)
    #         if b:
    #             # 重新計算狀態
    #             qdate = b["qdate"]
    #             if isinstance(qdate, str):
    #                 qdate = QDate.fromString(qdate, "yyyy-MM-dd")
    #             end_qdate = b.get("end_qdate", qdate)
    #             if isinstance(end_qdate, str):
    #                 end_qdate = QDate.fromString(end_qdate, "yyyy-MM-dd")
    #             start_dt = QDateTime(qdate, QTime(int(b["start_hour"]), int((b["start_hour"] % 1) * 60)))
    #             end_dt = QDateTime(end_qdate, QTime(int(b["end_hour"]), int((b["end_hour"] % 1) * 60)))

    #             computed_status = self.compute_status(now, start_dt, end_dt)
    #             if b.get("status", "") != computed_status:
    #                 b["status"] = computed_status
    #                 item.status = computed_status  # ✅ 順便更新畫面上的 block
    #                 item.update_text_position()
    #                 save_needed = True
    #     if save_needed:
    #         parent_view = self.blocks[0].scene().parent() if self.blocks else None
    #         if parent_view:
    #             now_ts = QDateTime.currentDateTime()
    #             if not hasattr(self, "last_saved_ts"):
    #                 self.last_saved_ts = now_ts.addSecs(-60)  # 初始化
    #             if self.last_saved_ts.secsTo(now_ts) >= 10:
    #                 parent_view.save_schedule()
    #                 self.last_saved_ts = now_ts

    def start_encoder(self, encoder_name, filename, status_label, block_id=None):
        
        now = QDateTime.currentDateTime()
        date_folder = now.toString("MM.dd.yyyy")
        date_prefix = now.toString("MMdd")
        
      
        
        full_path = os.path.abspath(os.path.join(self.record_root, date_folder, f"{date_prefix}_{filename}"))
        rel_path = os.path.relpath(full_path, start=self.record_root)
        
        sock = connect_socket(encoder_name)
        if not sock:
            status_label.setText("❌ 無法連線")
            status_label.setStyleSheet("color: red;")
            return

        res1 = send_encoder_command(encoder_name, f'Setfile "{encoder_name}" 1 {rel_path}')
        res2 = send_encoder_command(encoder_name, f'Start "{encoder_name}" 1')

        if "OK" in res1 and "OK" in res2:
            status_label.setText("✅ 錄影中")
            status_label.setStyleSheet("color: green;")
            block = self.find_block_by_id(block_id) if block_id else None
        # ✅ 只在第一次啟動時拍照，避免 check_schedule 觸發多次
        if block_id and block_id not in self.already_started:
            self.already_started.add(block_id)

        # ✅ 加這一段，安全地避免 UI 關閉後仍觸發 snapshot
            window = QApplication.instance().activeWindow()
            if window and not getattr(window, "is_closing", False):
                take_snapshot_from_block(block, self.encoder_names)
            else:
                log(f"🛑 無視拍照：UI 已關閉或找不到 activeWindow")
        if block:
            img_dir = os.path.join(self.record_root, block.start_date.toString("MM.dd.yyyy"), "img")
            block.load_preview_images(img_dir)     
        else:
            status_label.setText("❌ 錯誤")
            status_label.setStyleSheet("color: red;")

    def stop_encoder(self, encoder_name, status_label):
        status_label.setText("狀態：🔁 停止中...")
        status_label.setStyleSheet("color: blue")
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
            status_label.setText("狀態：⏹ 停止中")
            status_label.setStyleSheet("color: gray")
        else:
            status_label.setText("狀態：❌ 停止失敗")
            status_label.setStyleSheet("color: red")

        self.refresh_encoder_statuses()

    def refresh_encoder_statuses(self):
        for encoder_name in self.encoder_names:
            try:
                res = send_encoder_command(encoder_name,f'EncStatus "{encoder_name}"')
                log(f"⬅️ Response: {res}")
            except Exception as e:
                res = f"FAILED: {e}"

            # 比對是否有改變
            if self.encoder_last_state.get(encoder_name) == res:
                continue  # ❌ 一樣就跳過，不重畫 UI

            self.encoder_last_state[encoder_name] = res  # ✅ 更新快取

            # 解析狀態
            if "Running" in res or "Runned" in res:
                status_text = "✅ 錄影中"
                color = "green"
            elif "Paused" in res:
                status_text = "⏸ 暫停中"
                color = "orange"
            elif "Stopped" in res or "None" in res:
                status_text = "⏹ 停止中"
                color = "gray"
            elif "Prepared" in res or "Preparing" in res:
                status_text = "🟡 準備中"
                color = "blue"
            elif "Error" in res:
                status_text = "❌ 錯誤"
                color = "red"
            else:
                status_text = f"❓未知\n{res}"
                color = "black"

            
            # for block in self.blocks:
            #     if block.track_index < len(self.encoder_names) and self.encoder_names[block.track_index] == encoder_name:
            #         block.status = f"狀態：{status_text}"
            #         block.update_text_position()

            if self.encoder_status.get(encoder_name):
                self.encoder_status[encoder_name].setText(f"狀態：{status_text}")
                self.encoder_status[encoder_name].setStyleSheet(f"color: {color}")
            logging.debug(f"🌀 已更新 {encoder_name} 狀態為 {status_text}")

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