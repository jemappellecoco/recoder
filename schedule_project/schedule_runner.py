# schedule_runner.py

from PySide6.QtCore import QObject, QTimer, QDateTime, QDate, QTime
from encoder_utils import connect_socket, send_command
import os

class ScheduleRunner(QObject):
    def __init__(self, schedule_data, encoder_status, record_root, encoder_names, blocks):
        super().__init__()
        self.schedule_data = schedule_data
        self.encoder_status = encoder_status
        self.record_root = record_root
        self.encoder_names = encoder_names
        self.blocks = blocks  # 傳入 TimeBlock 實例列表

        self.already_started = set()
        self.already_stopped = set()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_schedule)
        self.timer.start(1000)  # 每秒檢查一次

    def check_schedule(self):
        now = QDateTime.currentDateTime()
        for b in self.schedule_data:
            label = b["label"]
            qdate = b["qdate"]
            if isinstance(qdate, str):
                qdate = QDate.fromString(qdate, "yyyy-MM-dd")

            start_hour = float(b["start_hour"])
            h = int(start_hour)
            m = int((start_hour - h) * 60)
            start_dt = QDateTime(qdate, QTime(h, m, 0))
            duration_secs = int(b["duration"] * 3600)
            end_dt = start_dt.addSecs(duration_secs)

            track_index = b["track_index"]
            encoder_name = self.encoder_names[track_index]
            status_label = self.encoder_status.get(encoder_name)
            block = self.find_block_by_label(label)

            # 錄影中：已啟動但還沒結束
            if start_dt <= now < end_dt:
                remaining = end_dt.toSecsSinceEpoch() - now.toSecsSinceEpoch()
                time_text = self.format_remaining_time(remaining)

                if block:
                    block.status = f"錄影中\n剩餘 {time_text}"
                    block.update_text_position()

                if label not in self.already_started:
                    self.start_encoder(encoder_name, label, status_label)
                    self.already_started.add(label)

            # 已結束
            elif now >= end_dt and label not in self.already_stopped:
                if block:
                    block.status = "⏹ 已結束"
                    block.update_text_position()

                self.stop_encoder(encoder_name, status_label)
                self.already_stopped.add(label)

            # 等待中：尚未啟動
            elif now < start_dt:
                countdown = start_dt.toSecsSinceEpoch() - now.toSecsSinceEpoch()
                countdown_str = self.format_remaining_time(countdown)
                start_time_str = f"{h:02d}:{m:02d}"
                if block:
                    block.status = f"等待中\n啟動於 {start_time_str}\n倒數 {countdown_str}"
                    block.update_text_position()

    def start_encoder(self, encoder_name, filename, status_label):
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
        else:
            status_label.setText("❌ 錯誤")
            status_label.setStyleSheet("color: red;")

    def stop_encoder(self, encoder_name, status_label):
        sock = connect_socket()
        if not sock:
            status_label.setText("❌ 停止失敗")
            status_label.setStyleSheet("color: red;")
            return

        res = send_command(sock, f'Stop "{encoder_name}" 1')
        sock.close()

        if "OK" in res:
            status_label.setText("⏹ 已停止")
            status_label.setStyleSheet("color: gray;")
        else:
            status_label.setText("❌ 停止失敗")
            status_label.setStyleSheet("color: red;")

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
