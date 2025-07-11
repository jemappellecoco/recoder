# schedule_runner.py
from encoder_controller import EncoderController 
from PySide6.QtCore import QObject, QTimer, QDateTime, QDate, QTime
from encoder_utils import connect_socket, send_command,send_persistent_command
import os
import logging
from PySide6.QtWidgets import QApplication
from capture import take_snapshot_from_block 
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
        self.timer.timeout.connect(self.check_schedule)
        self.timer.start(1000)  # 每秒檢查一次
        self.encoder_last_state = {}
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.refresh_encoder_statuses)
        
        self.status_timer.start(REFRESH_INTERVAL_MS)  
        
    def check_schedule(self):
        now = QDateTime.currentDateTime()
        
        for b in self.schedule_data:
            block_id = b.get("id")

            if block_id in self.already_stopped:
                block = self.find_block_by_id(block_id)
                if block:
                    block.status = "⏹ 停止中"
                    block.update_text_position()
                continue

            qdate = b["qdate"]
            if isinstance(qdate, str):
                qdate = QDate.fromString(qdate, "yyyy-MM-dd")

            start_hour = float(b["start_hour"])
            h = int(start_hour)
            m = int((start_hour % 1) * 60)
            s = int(((start_hour * 60) % 1) * 60)  # ➜ 小數轉秒數

            start_dt = QDateTime(qdate, QTime(h, m, s))
            end_hour = b.get("end_hour")
            if end_hour is None:
                end_hour = b["start_hour"] + b["duration"]

            end_h = int(end_hour)
            end_m = int((end_hour % 1) * 60)
            end_s = int(((end_hour * 60) % 1) * 60)
            end_qdate = b.get("end_qdate", None)
            if isinstance(end_qdate, str):
                end_qdate = QDate.fromString(end_qdate, "yyyy-MM-dd")

        end_dt = QDateTime(end_qdate, QTime(end_h, end_m, end_s))

        track_index = b["track_index"]
        encoder_name = self.encoder_names[track_index]
        status_label = self.encoder_status.get(encoder_name)

        if start_dt <= now < end_dt:
            if block_id not in self.already_started:
                print(f"🚀 啟動錄影: {b['label']} ({block_id})")
                self.start_encoder(encoder_name, b["label"], status_label, block_id)
                self.already_started.add(block_id)

        elif now >= end_dt:
            self.stop_encoder(encoder_name, status_label)
            self.already_stopped.add(block_id)




    def start_encoder(self, encoder_name, filename, status_label, block_id=None):
        
        now = QDateTime.currentDateTime()
        date_folder = now.toString("MM.dd.yyyy")
        date_prefix = now.toString("MMdd")
        
      
        
        full_path = os.path.abspath(os.path.join(self.record_root, date_folder, f"{date_prefix}_{filename}"))
        rel_path = os.path.relpath(full_path, start=self.record_root)
        
        sock = connect_socket()
        if not sock:
            status_label.setText("❌ 無法連線")
            status_label.setStyleSheet("color: red;")
            return

        res1 = send_command(sock, f'Setfile "{encoder_name}" 1 {rel_path}')
        res2 = send_command(sock, f'Start "{encoder_name}" 1')
        sock.close()

        if "OK" in res1 and "OK" in res2:
            status_label.setText("✅ 錄影中")
            status_label.setStyleSheet("color: green;")
            block = self.find_block_by_id(block_id) if block_id else None
            take_snapshot_from_block(block, self.encoder_names)
            if block:
                block.load_preview_images(os.path.join(self.record_root, block.start_date.toString("MM.dd.yyyy"), "img"))  # 加這行
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

            status_label.setText("狀態：⏹ 停止中")
            status_label.setStyleSheet("color: gray")
        else:
            status_label.setText("狀態：❌ 停止失敗")
            status_label.setStyleSheet("color: red")

        self.refresh_encoder_statuses()

    def refresh_encoder_statuses(self):
        for encoder_name in self.encoder_names:
            try:
                res = send_persistent_command(f'EncStatus "{encoder_name}"')
                print(f"⬅️ Response: {res}")
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
    def format_remaining_time(self, seconds):
        h = int(seconds) // 3600
        m = (int(seconds) % 3600) // 60
        s = int(seconds) % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

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