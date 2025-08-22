# check_schedule_manager.py
from PySide6.QtCore import QDateTime, QDate, QTime, QObject, Signal, QRunnable, QThreadPool
from shiboken6 import isValid
from utils import log,MIN_LEAD_SECONDS,hourf_to_qtime
from encoder_utils import get_encoder_display_name
from encoder_status_manager import EncoderStatusManager

# ---------------- Worker ----------------
class _CheckWorkerSignals(QObject):
    done = Signal(list)   # [{'action': 'start'|'stop', 'block_id': str, 'encoder_name': str}]


class _CheckWorker(QRunnable):
    """
    真正做「排程計算」的背景工作：
    - 不觸碰 UI 物件
    - 不直接呼叫 runner（避免跨執行緒）
    - 只回傳要做的動作清單，由主線程套用
    """
    def __init__(self, snapshot):
        super().__init__()
        self.snapshot = snapshot
        self.signals = _CheckWorkerSignals()

    def run(self):
        now = QDateTime.currentDateTime()
        actions = []

        enc_names = self.snapshot["encoder_names"]
        started = set(self.snapshot["already_started"])
        stopped = set(self.snapshot["already_stopped"])

        for b in self.snapshot["today_blocks"]:
            block_id = b["id"]
            if not block_id:
                continue

            qdate = b["qdate"]
            end_qdate = b.get("end_qdate", qdate)

            start_hour = float(b["start_hour"])
            end_hour   = float(b.get("end_hour", b["start_hour"] + b["duration"]))

            start_dt = QDateTime(qdate,    hourf_to_qtime(float(start_hour)))
            end_dt   = QDateTime(end_qdate, hourf_to_qtime(float(end_hour)))
            track_idx = b["track_index"]
            if not (0 <= track_idx < len(enc_names)):
                continue
            encoder_name = enc_names[track_idx]

            # ➤ 自動開始
            delta_start = start_dt.secsTo(now)  # start_dt -> now（到點=0）
            if 0 <= delta_start <= 1 and block_id not in started:
                actions.append({"action": "start", "block_id": block_id, "encoder_name": encoder_name})

            # ➤ 自動停止
            delta_end = end_dt.secsTo(now)
            if 0 <= delta_end <= 1 and block_id not in stopped:
                actions.append({"action": "stop", "block_id": block_id, "encoder_name": encoder_name})

        self.signals.done.emit(actions)


# ---------------- Manager ----------------
class CheckScheduleManager(QObject):
    """
    管理『排程檢查』，把重工作業丟到背景，主線程只負責套用結果。
    """
    def __init__(self, encoder_names, encoder_status_dict, runner, parent_view_getter):
        super().__init__()
        self.encoder_names = encoder_names
        self.encoder_status = encoder_status_dict
        self.runner = runner
        self.get_parent_view = parent_view_getter
        self.schedule_data = []
        self.blocks = []
        self.already_started = set()
        self.already_stopped = set()
        self.last_saved_ts = None
        self.encoder_status_manager = EncoderStatusManager()
        self._pool = QThreadPool.globalInstance()

    # --- 將必要資料快照化，避免在 worker 內存取 Qt 物件 ---
    def _make_snapshot(self):
        today = QDate.currentDate()
        today_blocks = []
        for b in self.schedule_data:
            block_id = b.get("id")
            if not block_id:
                continue

            qdate = b["qdate"]
            if isinstance(qdate, str):
                qdate = QDate.fromString(qdate, "yyyy-MM-dd")

            # 只處理今天
            if qdate != today:
                continue

            end_qdate = b.get("end_qdate", qdate)
            if isinstance(end_qdate, str):
                end_qdate = QDate.fromString(end_qdate, "yyyy-MM-dd")

            today_blocks.append({
                "id": block_id,
                "qdate": qdate,
                "end_qdate": end_qdate,
                "track_index": b["track_index"],
                "start_hour": float(b["start_hour"]),
                "duration": float(b["duration"]),
                "end_hour": float(b.get("end_hour", b["start_hour"] + b["duration"])),
                "label": b["label"]
            })

        return {
            "encoder_names": list(self.encoder_names),
            "already_started": list(self.already_started),
            "already_stopped": list(self.already_stopped),
            "today_blocks": today_blocks,
        }

    # 主線程呼叫：把檢查丟到背景
    def tick_async(self):
        try:
            snap = self._make_snapshot()
            worker = _CheckWorker(snap)
            worker.signals.done.connect(self._apply_actions_on_main)
            self._pool.start(worker)
        except Exception as e:
            log(f"❌ tick_async error: {e}")

    # 主線程 slot：依 worker 結果套用動作（這裡才觸碰 UI / runner）
    def _apply_actions_on_main(self, actions: list):
        if not actions:
            return

        for act in actions:
            action = act["action"]
            enc = act["encoder_name"]
            block_id = act["block_id"]

            status_label = self.encoder_status.get(enc)
            if status_label and not isValid(status_label):
                alias = get_encoder_display_name(enc)
                log(f"⚠️ status label for {alias} 已失效，略過 UI 更新")
                self.encoder_status.pop(enc, None)
                status_label = None

            # 找 block（為了 label / 日期等）
            block = self.find_block_by_id(block_id)
            label = block.label if block else next((b["label"] for b in self.schedule_data if b.get("id") == block_id), "")

            if action == "start" and block_id not in self.already_started:
                log(f"🚀 [主線程] 啟動錄影：{label} ({block_id}) on {enc}")
                self.runner.start_encoder(enc, label, status_label, block_id)
                self.already_started.add(block_id)

            elif action == "stop" and block_id not in self.already_stopped:
                log(f"🛑 [主線程] 停止錄影：{label} ({block_id}) on {enc}")
                self.runner.stop_encoder(enc, status_label)
                self.already_stopped.add(block_id)

        # 套用後更新畫面 / 儲存
        parent_view = self.get_parent_view()
        if parent_view:
            parent_view.save_schedule()
            parent_view.update()

    def find_block_by_id(self, block_id):
        for blk in self.blocks:
            if blk.block_id == block_id:
                return blk
        return None
