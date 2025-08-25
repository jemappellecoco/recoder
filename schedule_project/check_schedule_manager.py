# check_schedule_manager.py
from PySide6.QtCore import QDateTime, QDate, QTimer, QObject, Signal, QRunnable, QThreadPool
from shiboken6 import isValid
from utils import log,MIN_LEAD_SECONDS,hourf_to_qtime
from encoder_utils import get_encoder_display_name
from encoder_status_manager import EncoderStatusManager
class _ReconSignals(QObject):
    done = Signal(list)  # [{action, block_id, encoder_name, reason, end_now_sec}]

class _ReconWorker(QRunnable):
    """
    每 10 秒跑一次的『狀態一致性』檢查：
    - 現在在時間範圍內的 block 如果標示「錄影中」，但 Encoder 實況不是錄影，就回報 mismatch/aborted
    """
    def __init__(self, snapshot):
        super().__init__()
        self.snapshot = snapshot
        self.signals = _ReconSignals()

    def run(self):
        now = QDateTime.currentDateTime()
        enc_names = self.snapshot["encoder_names"]
        actions = []

        # 將 today_blocks 以 encoder track 分組，稍後可用
        for b in self.snapshot["today_blocks"]:
            block_id = b["id"]
            if not block_id:
                continue

            start_dt = QDateTime(b["qdate"], hourf_to_qtime(float(b["start_hour"])))
            end_dt   = QDateTime(b["end_qdate"], hourf_to_qtime(float(b["end_hour"])))
            if not (start_dt <= now <= end_dt):
                continue  # 只處理「應該正在錄」的時段

            track_idx = int(b["track_index"])
            if not (0 <= track_idx < len(enc_names)):
                continue
            encoder_name = enc_names[track_idx]

            # 用 status_text 推論是否為「應該在錄」的 UI 狀態（保守以 UI/JSON 為準）
            expected_recording = True  # 我們只挑時間命中的；UI若不是錄也要提示
            actions.append({
                "action": "check",
                "block_id": block_id,
                "encoder_name": encoder_name,
                "start_dt": start_dt.toSecsSinceEpoch(),
                "end_dt":   end_dt.toSecsSinceEpoch(),
            })

        self.signals.done.emit(actions)
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

    # def run(self):
    #     now = QDateTime.currentDateTime()
    #     actions = []

    #     enc_names = self.snapshot["encoder_names"]
    #     started = set(self.snapshot["already_started"])
    #     stopped = set(self.snapshot["already_stopped"])

    #     for b in self.snapshot["today_blocks"]:
    #         block_id = b["id"]
    #         if not block_id:
    #             continue

    #         qdate = b["qdate"]
    #         end_qdate = b.get("end_qdate", qdate)

    #         start_hour = float(b["start_hour"])
    #         end_hour   = float(b.get("end_hour", b["start_hour"] + b["duration"]))

    #         start_dt = QDateTime(qdate,    hourf_to_qtime(float(start_hour)))
    #         end_dt   = QDateTime(end_qdate, hourf_to_qtime(float(end_hour)))
    #         track_idx = b["track_index"]
    #         if not (0 <= track_idx < len(enc_names)):
    #             continue
    #         encoder_name = enc_names[track_idx]

    #         # ➤ 自動開始
    #         delta_start = start_dt.secsTo(now)  # start_dt -> now（到點=0）
    #         if 0 <= delta_start <= 1 and block_id not in started:
    #             actions.append({"action": "start", "block_id": block_id, "encoder_name": encoder_name})

    #         # ➤ 自動停止
    #         delta_end = end_dt.secsTo(now)
    #         if 0 <= delta_end <= 1 and block_id not in stopped:
    #             actions.append({"action": "stop", "block_id": block_id, "encoder_name": encoder_name})

    #     self.signals.done.emit(actions)
        def run(self):
            now = QDateTime.currentDateTime()
            actions = []

            enc_names = self.snapshot["encoder_names"]
            started = set(self.snapshot["already_started"])
            stopped = set(self.snapshot["already_stopped"])

            # 依 encoder 收集操作，之後再排序（0=stop 先、1=start 後）
            per_enc_ops = {name: [] for name in enc_names}
            GRACE_POST_SEC = 5  # 小寬限，避免 tick 漂移；不用到 60 秒

            for b in self.snapshot["today_blocks"]:
                block_id = b["id"]
                if not block_id:
                    continue

                qdate = b["qdate"]
                end_qdate = b.get("end_qdate", qdate)

                start_hour = float(b["start_hour"])
                end_hour   = float(b.get("end_hour", b["start_hour"] + b["duration"]))

                start_dt = QDateTime(qdate,    hourf_to_qtime(start_hour))
                end_dt   = QDateTime(end_qdate, hourf_to_qtime(end_hour))

                ti = b["track_index"]
                if not (0 <= ti < len(enc_names)):
                    continue
                enc = enc_names[ti]

                # ★ 停止：已到或超過結束時間（+小寬限），且尚未停過
                if now >= end_dt.addSecs(-GRACE_POST_SEC) and block_id not in stopped:
                    per_enc_ops[enc].append((0, {"action": "stop",  "block_id": block_id, "encoder_name": enc}))

                # ★ 開始：在區間內且尚未啟動
                if start_dt <= now < end_dt and block_id not in started:
                    per_enc_ops[enc].append((1, {"action": "start", "block_id": block_id, "encoder_name": enc}))

            # ★ 同一台設備：先停再啟，避免邊界同秒互卡
            for enc, ops in per_enc_ops.items():
                ops.sort(key=lambda x: x[0])  # 0=stop, 1=start
                actions.extend(a for _, a in ops)

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

                # ➕ 新增：每 10 秒做一次一致性檢查
        self._recon_timer = QTimer()
        self._recon_timer.setInterval(10_000)
        self._recon_timer.timeout.connect(self.reconcile_async)
        self._recon_timer.start()
    # --- 將必要資料快照化，避免在 worker 內存取 Qt 物件 ---
    def reconcile_async(self):
        try:
            snap = self._make_snapshot()
            worker = _ReconWorker(snap)
            worker.signals.done.connect(self._apply_reconcile_on_main)
            self._pool.start(worker)
        except Exception as e:
            log(f"❌ reconcile_async error: {e}")

    def _apply_reconcile_on_main(self, actions: list):
        """
        在主執行緒：
        - 查 Encoder 實況（使用 encoder_status_manager）
        - 如果本該錄影中的 block，Encoder 卻不是「錄影中」，就：
            1) 在 block 顯示 live_status 提示（黃閃）
            2) 若為『停止/未連線/錯誤/暫停』，標記 ABORTED，並把 end 修正為 now
        - 額外保險：若已超過 end_dt 仍在錄影 → 立即強停
        """
        if not actions:
            return

        parent_view = self.get_parent_view()
        if not parent_view:
            return

        now = QDateTime.currentDateTime()

        # --- (A) 處理 reconcile actions：UI顯示錄影中但實況不是錄影 ---
        for act in actions:
            blk_id = act.get("block_id")
            enc    = act.get("encoder_name")
            if not blk_id or not enc:
                continue

            # 找對應的 TimeBlock（活體檢查）
            block = self.find_block_by_id(blk_id)
            if (not block) or (not isValid(block)) or (block.scene() is None):
                continue

            # 讀 Encoder 實況
            stat = self.encoder_status_manager.get_status(enc)
            stat_text = stat[0] if stat else ""

            not_recording = any(k in stat_text for k in ["未連線", "停止", "錯誤", "暫停"])
            is_recording  = ("錄影中" in stat_text)

            # 非錄影中：先給即時提示（不寫 JSON）
            if not is_recording:
                try:
                    reason = f"{enc} 實況：{stat_text or '未知'}"
                    block.set_live_status(f"⚠️ 與實況不一致：{reason}")
                    block.flash_warning(600)
                except RuntimeError:
                    continue

                # 守門 (A)：UI 必須顯示「錄影中」
                try:
                    if "錄影中" not in getattr(block, "status", ""):
                        continue
                except RuntimeError:
                    continue

                # 守門 (B)：now 必須在 block 時段內
                start_dt_chk = QDateTime(block.start_date, hourf_to_qtime(block.start_hour))
                end_dt_chk   = block.compute_end_dt()
                now_chk      = QDateTime.currentDateTime()
                if not (start_dt_chk <= now_chk <= end_dt_chk):
                    continue

                # 異常：標記 ABORTED + 修正 end 為 now，同步回 JSON
                if not_recording:
                    try:
                        if hasattr(block, "mark_aborted"):
                            block.mark_aborted("編碼器非錄影狀態")
                        else:
                            if hasattr(block, "set_state"):
                                block.set_state("WAITING")
                                block.flash_warning(600)
                        block.update_text_position()
                    except RuntimeError:
                        continue

                    # end=now -> duration 重算
                    try:
                        start_dt = QDateTime(block.start_date, hourf_to_qtime(block.start_hour))
                        new_duration_h = max(0.0, round(start_dt.secsTo(now) / 3600.0, 3))
                        block.duration_hours = new_duration_h

                        end_dt = block.compute_end_dt()
                        end_qdate = end_dt.date()
                        et = end_dt.time()
                        end_hour = round(et.hour() + et.minute()/60 + et.second()/3600, 4)

                        block.update_block_data({
                            "duration":   block.duration_hours,
                            "end_hour":   end_hour,
                            "end_qdate":  end_qdate,
                            "status":     getattr(block, "status", ""),  # "狀態：❌ 異常中斷"
                        })
                    except Exception:
                        pass

        # --- (B) 保險：已過結束時間仍在錄影 → 立即強停 ---
        try:
            now2 = QDateTime.currentDateTime()
            for b in self.schedule_data:
                blk_id = b.get("id")
                if not blk_id or blk_id in self.already_stopped:
                    continue

                qd = b["qdate"]; edqd = b.get("end_qdate", qd)
                if isinstance(qd, str):   qd   = QDate.fromString(qd, "yyyy-MM-dd")
                if isinstance(edqd, str): edqd = QDate.fromString(edqd, "yyyy-MM-dd")

                sh = float(b["start_hour"])
                eh = float(b.get("end_hour", b["start_hour"] + b["duration"]))

                end_dt = QDateTime(edqd, hourf_to_qtime(eh))
                if now2 <= end_dt:
                    continue

                ti = b["track_index"]
                if not (0 <= ti < len(self.encoder_names)):
                    continue
                enc = self.encoder_names[ti]

                stat = self.encoder_status_manager.get_status(enc)
                is_recording = bool(stat and ("錄影中" in stat[0]))

                if is_recording:
                    log(f"🛑 reconcile: {enc} 超過排程仍在錄，強制停止")

                    # label 活體檢查（與 _apply_actions_on_main 一致）
                    status_label = self.encoder_status.get(enc)
                    if status_label and not isValid(status_label):
                        self.encoder_status.pop(enc, None)
                        status_label = None

                    # 真正下停機
                    self.runner.stop_encoder(enc, status_label)
                    self.already_stopped.add(blk_id)

                    # UX：若場上 block 還在，立刻轉成 FINISHED（避免使用者等下一輪）
                    blk_obj = self.find_block_by_id(blk_id)
                    if blk_obj and isValid(blk_obj) and blk_obj.scene() is not None:
                        try:
                            if hasattr(blk_obj, "set_state"):
                                blk_obj.set_state("FINISHED", force=True)
                                blk_obj.update_text_position()
                        except RuntimeError:
                            pass
        except Exception:
            pass

        # --- 存檔 + 重繪（一次就好） ---
        if parent_view:
            try:
                parent_view.save_schedule()
                parent_view.update()
            except Exception:
                pass


        # 儲存並刷新
        parent_view = self.get_parent_view()
        if parent_view:
            parent_view.save_schedule()
            parent_view.update()
        # 儲存並刷新畫面（安全包一層）
        try:
            parent_view.save_schedule()
            parent_view.update()
        except Exception:
            pass
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
        pv = self.get_parent_view()
        if not pv:
            return None
        for blk in getattr(pv, "blocks", []):
            if getattr(blk, "block_id", None) == block_id:
                # 活體檢查，避免剛好重建中
                try:
                    if isValid(blk) and blk.scene() is not None:
                        return blk
                except RuntimeError:
                    return None
        return None
