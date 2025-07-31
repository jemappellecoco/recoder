from PySide6.QtCore import QDateTime, QDate, QTime

from utils import log  # 你之前的 log 函數

class CheckScheduleManager:
    def __init__(self, encoder_names, encoder_status_dict, runner, parent_view_getter):
        self.encoder_names = encoder_names
        self.encoder_status = encoder_status_dict
        self.runner = runner  # 可以呼叫 start_encoder / stop_encoder
        self.get_parent_view = parent_view_getter  # 應該是一個 function
        self.schedule_data = []
        self.blocks = []
        self.already_started = set()
        self.already_stopped = set()
        self.last_saved_ts = None

    def find_block_by_id(self, block_id):
        for blk in self.blocks:
            if blk.block_id == block_id:
                return blk
        return None

    def compute_status(self, now, start_dt, end_dt):
        if now < start_dt:
            return "🕒 等待中"
        elif start_dt <= now <= end_dt:
            return "✅ 錄影中"
        else:
            return "⏹️ 已結束"

    def check_schedule(self):
        now = QDateTime.currentDateTime()

        for b in self.schedule_data:
            block_id = b.get("id")
            if block_id in self.already_stopped:
                continue

            qdate = b["qdate"]
            if isinstance(qdate, str):
                qdate = QDate.fromString(qdate, "yyyy-MM-dd")
            end_qdate = b.get("end_qdate", qdate)
            if isinstance(end_qdate, str):
                end_qdate = QDate.fromString(end_qdate, "yyyy-MM-dd")

            start_hour = float(b["start_hour"])
            end_hour = b.get("end_hour", b["start_hour"] + b["duration"])

            start_dt = QDateTime(qdate, QTime(int(start_hour), int((start_hour % 1) * 60)))
            end_dt = QDateTime(end_qdate, QTime(int(end_hour), int((end_hour % 1) * 60)))

            if now > end_dt:
                continue

            track_index = b["track_index"]
            encoder_name = self.encoder_names[track_index]
            status_label = self.encoder_status.get(encoder_name)
            block = self.find_block_by_id(block_id)

            if (start_dt <= now < end_dt and block_id not in self.already_started and (not block or "已結束" not in block.status)):
                log(f"🚀 啟動錄影: {b['label']} ({block_id})")
                self.runner.start_encoder(encoder_name, b["label"], status_label, block_id)
                self.already_started.add(block_id)

            elif now >= end_dt and block_id not in self.already_stopped:
                self.runner.stop_encoder(encoder_name, status_label)
                self.already_stopped.add(block_id)
                if block:
                    block.status = self.compute_status(now, start_dt, end_dt)
                    block.update_text_position()

        # 更新 block 狀態 & 判斷是否需要儲存
        save_needed = False
        block_map = {b["id"]: b for b in self.schedule_data if b.get("id")}
        now = QDateTime.currentDateTime()

        for item in self.blocks:
            b = block_map.get(item.block_id)
            if b:
                qdate = b["qdate"]
                if isinstance(qdate, str):
                    qdate = QDate.fromString(qdate, "yyyy-MM-dd")
                end_qdate = b.get("end_qdate", qdate)
                if isinstance(end_qdate, str):
                    end_qdate = QDate.fromString(end_qdate, "yyyy-MM-dd")
                start_dt = QDateTime(qdate, QTime(int(b["start_hour"]), int((b["start_hour"] % 1) * 60)))
                end_dt = QDateTime(end_qdate, QTime(int(b["end_hour"]), int((b["end_hour"] % 1) * 60)))

                computed_status = self.compute_status(now, start_dt, end_dt)
                if b.get("status", "") != computed_status:
                    b["status"] = computed_status
                    item.status = computed_status
                    item.update_text_position()
                    save_needed = True

        if save_needed and self.blocks:
            parent_view = self.get_parent_view()
            if parent_view:
                now_ts = QDateTime.currentDateTime()
                if self.last_saved_ts is None or self.last_saved_ts.secsTo(now_ts) >= 10:
                    parent_view.save_schedule()
                    self.last_saved_ts = now_ts
