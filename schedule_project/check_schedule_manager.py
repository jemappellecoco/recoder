# check_schedule_manager.py
from PySide6.QtCore import QDateTime, QDate, QTimer, QObject, Signal, QRunnable, QThreadPool
from shiboken6 import isValid
from utils import log, hourf_to_qtime
from encoder_utils import get_encoder_display_name
from encoder_status_manager import EncoderStatusManager
class _ReconSignals(QObject):
    done = Signal(list)  # [{action, block_id, encoder_name, reason, end_now_sec}]
class _ReconWorker(QRunnable):
    """
     每 10 秒跑一次的『狀態一致性』檢查：
    - 在背景批量查詢 Encoder 狀態
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
            # expected_recording = True  # 我們只挑時間命中的；UI若不是錄也要提示
            actions.append({
                "action": "check",
                "block_id": block_id,
                "encoder_name": encoder_name,
                "start_dt": start_dt.toSecsSinceEpoch(),
                "end_dt":   end_dt.toSecsSinceEpoch(),
            })
                # 批量查詢 Encoder 狀態
        stat_mgr = EncoderStatusManager()
        enc_set = {act["encoder_name"] for act in actions}
        enc_stats = stat_mgr.refresh_all(enc_set)
        for act in actions:
            act["status"] = enc_stats.get(act["encoder_name"])
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
            # 設定寬限（避免 tick 漂移）
            GRACE_START_SEC = 10
            GRACE_STOP_SEC  = 10
            # ➤ 自動開始（剛過開始點的短時間內觸發，且現在時間仍在區塊內）
            sec_after_start = start_dt.secsTo(now)
            if (0 <= sec_after_start <= GRACE_START_SEC) and (now <= end_dt) and (block_id not in started):
                actions.append({"action": "start", "block_id": block_id, "encoder_name": encoder_name})
            # ➤ 自動停止（剛過結束點的短時間內觸發）
            sec_after_end = end_dt.secsTo(now)
            if (0 <= sec_after_end <= GRACE_STOP_SEC) and (block_id not in stopped):
                actions.append({"action": "stop", "block_id": block_id, "encoder_name": encoder_name})
            # # ➤ 自動開始
            # delta_start = start_dt.secsTo(now)  # start_dt -> now（到點=0）
            # if 0 <= delta_start <= 1 and block_id not in started:
            #     actions.append({"action": "start", "block_id": block_id, "encoder_name": encoder_name})
            # # ➤ 自動停止
            # delta_end = end_dt.secsTo(now)
            # if 0 <= delta_end <= 1 and block_id not in stopped:
            #     actions.append({"action": "stop", "block_id": block_id, "encoder_name": encoder_name})
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
        # self.encoder_status_manager = EncoderStatusManager()
        self._pool = QThreadPool.globalInstance()
                # ➕ 新增：每 10 秒做一次一致性檢查
        self._recon_timer = QTimer()
        self._recon_timer.setInterval(10_000)
        self._recon_timer.timeout.connect(self.reconcile_async)
        self._recon_timer.start()
        self._mismatch_counts = {}   # {block_id: count}
        self.MISMATCH_THRESHOLD = 3  # 連續 3 次(每 10s 檢查一次 ≈ 30s)才判定異常
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
        依背景查到 Encoder 實況：
        - 未達門檻：僅顯示「⚠️ 不一致 (x/門檻)」+ tooltip，不黃閃、不動 JSON
        - 達門檻(MISMATCH_THRESHOLD)：mark_aborted() + 修 end=now + 回寫 JSON + 短暫黃閃
        """
        if not actions:
            return
        parent_view = self.get_parent_view()
        if not parent_view:
            return

        for act in actions:
            blk_id = act.get("block_id")
            enc    = act.get("encoder_name")
            if not blk_id or not enc:
                continue

            block = self.find_block_by_id(blk_id)
            if not block or not isValid(block) or block.scene() is None:
                continue

            # --- 讀 Encoder 實況（tuple: (text, color)）---
            stat = act.get("status") or ("", "")
            stat_text  = (stat[0] or "").strip()
            stat_color = (stat[1] or "").strip().lower()
            t = stat_text.lower()

            # 是否錄影中
            is_recording = (stat_color == "green") or ("running" in t or "record" in t)

            # 統一理由（給 tooltip）
            if is_recording:
                reason = "編碼器回報：錄影中"
            else:
                if   "error" in t:       reason = "編碼器回報：錯誤"
                elif "disconnect" in t:  reason = "編碼器回報：連線中斷"
                elif "timeout" in t:     reason = "編碼器回報：逾時"
                elif "stopped" in t:     reason = "編碼器回報：已停止"
                elif "paused" in t:      reason = "編碼器回報：暫停"
                elif "idle" in t:        reason = "編碼器回報：待命"
                elif "none" in t:        reason = "編碼器回報：未知"
                elif stat_text:          reason = f"編碼器回報：{stat_text}"
                else:                    reason = "編碼器回報：未知"

            # ===== 守門：僅在「UI 顯示錄影中」且「時間命中」時處理 =====
            try:
                if "錄影中" not in getattr(block, "status", ""):
                    self._mismatch_counts.pop(blk_id, None)
                    # 若不是「錄影中」，也順手清掉殘留提示
                    if getattr(block, "live_status", ""):
                        block.set_live_status("")
                        block.setToolTip("")
                    continue
                start_dt = QDateTime(block.start_date, hourf_to_qtime(block.start_hour))
                end_dt   = block.compute_end_dt()
                now_dt   = QDateTime.currentDateTime()
                if not (start_dt <= now_dt <= end_dt):
                    self._mismatch_counts.pop(blk_id, None)
                    if getattr(block, "live_status", ""):
                        block.set_live_status("")
                        block.setToolTip("")
                    continue
            except RuntimeError:
                continue

            # ===== 錄影狀態處理 =====
            if is_recording:
                # 恢復錄影 → 清除提示與計數
                self._mismatch_counts.pop(blk_id, None)
                try:
                    if getattr(block, "live_status", ""):
                        block.set_live_status("")
                        block.setToolTip("")
                except RuntimeError:
                    pass
                continue

            # 不是錄影中 → 累計一次
            cnt = self._mismatch_counts.get(blk_id, 0) + 1
            self._mismatch_counts[blk_id] = cnt
            threshold = getattr(self, "MISMATCH_THRESHOLD", 3)

            

            # === 達門檻：一次性停住 + 回寫 JSON + 短暫黃閃 ===
            self._mismatch_counts.pop(blk_id, None)
            try:
                # A) 標記異常（停住）
                if hasattr(block, "mark_aborted"):
                    block.mark_aborted("編碼器非錄影狀態")
                elif hasattr(block, "set_state"):
                    block.set_state("WAITING")
                # 給予一次清楚的黃閃提醒（只在達門檻時閃）
                block.flash_warning(800)
                block.update_text_position()
            except RuntimeError:
                continue

            # B) 修正 end=now，回寫 JSON
            try:
                start_dt2 = QDateTime(block.start_date, hourf_to_qtime(block.start_hour))
                new_dur_h = max(0.0, round(start_dt2.secsTo(QDateTime.currentDateTime()) / 3600.0, 3))
                block.duration_hours = new_dur_h
                end_dt2 = block.compute_end_dt()
                end_qdate = end_dt2.date()
                et = end_dt2.time()
                end_hour = round(et.hour() + et.minute()/60 + et.second()/3600, 4)
                block.update_block_data({
                    "duration":  block.duration_hours,
                    "end_hour":  end_hour,
                    "end_qdate": end_qdate,
                    "status":    getattr(block, "status", ""),
                })
            except Exception:
                pass

            # C) 存檔與刷新
            try:
                parent_view.save_schedule()
                parent_view.update()
            except Exception:
                pass

#     def _apply_reconcile_on_main(self, actions: list):
#         """
#         在主執行緒：
#         - 根據背景 worker 已查得的 Encoder 狀態
#         - 如果本該錄影中的 block，Encoder 卻不是「錄影中」，就：
#             1) 先在 block 上顯示 live_status 提示（黃閃）
#             2) 若判定為『停止/未連線/錯誤/暫停』，直接標記為 ABORTED，並把 end 修正為 now（不中斷其它流程）
#         """
#         deadline = getattr(self, "_reconcile_cooldown_until", None)
#         if deadline and QDateTime.currentDateTime() < deadline:
#             return
#         if not actions:
#             return
#         parent_view = self.get_parent_view()
#         if not parent_view:
#             return
#         now = QDateTime.currentDateTime()
#         for act in actions:
#             blk_id = act.get("block_id")
#             enc    = act.get("encoder_name")
#             if not blk_id or not enc:
#                 continue
#             # 先找一次
#             block = self.find_block_by_id(blk_id)
#             if not block:
#                 continue
#             # ✅ 舊物件可能已被 draw_blocks() 重建或刪掉
#             #    確認還有效；不行就再找一次最新的，仍不行就放掉
#             if (not isValid(block)) or (block.scene() is None):
#                 block = self.find_block_by_id(blk_id)
#                 if (not block) or (not isValid(block)) or (block.scene() is None):
#                     continue
#             # 讀 Encoder 狀態（tuple: (text, color)）
#             stat = act.get("status") or ("", "")
#             stat_text = (stat[0] or "").strip()
#             stat_color = (stat[1] or "").strip().lower()
#             # 標準化判斷（用顏色＋英文關鍵字，避免編碼/文案差異）
#             t = stat_text.lower()
#             is_recording = (stat_color == "green") or ("running" in t or "record" in t)
#             not_recording = (stat_color == "red") or any(s in t for s in ["stopped","error","disconnect","timeout","idle","none"])
#             # # 讀 Encoder 實況
#             # # stat = self.encoder_status_manager.get_status(enc)
#             # stat = act.get("status")
#             # stat_text = stat[0] if stat else ""
#             # # 關鍵判斷（依你的文字對應）
#             # not_recording = any(k in stat_text for k in ["未連線", "停止", "錯誤", "暫停"])
#             # is_recording  = ("錄影中" in stat_text)
#             # 不是錄影中：先給即時提示（不寫入 JSON）
#             if not is_recording:
#                 try:
#                     new_text = f"⚠️ 與實況不一致"
#                     changed = getattr(block, "live_status", "") != new_text
#                     if changed:
#                         block.set_live_status(new_text)
#                         # 未知狀態僅更新文字，不觸發閃爍
#                         if not_recording or (stat_text not in ("", "未知")):
#                             block.flash_warning(600)
#                 except RuntimeError:
#                     # 物件在這瞬間被換掉就跳過
#                     continue
# # ========== 兩道守門條件，避免誤標未來/等待中的區塊 ==========
#                 try:
#                     if "錄影中" not in getattr(block, "status", ""):
#                         continue
#                 except RuntimeError:
#                     continue
#                 # 守門 (B)：now 必須在 block 時段內
#                 start_dt_chk = QDateTime(block.start_date, hourf_to_qtime(block.start_hour))
#                 end_dt_chk   = block.compute_end_dt()
#                 now_chk      = QDateTime.currentDateTime()
#                 if not (start_dt_chk <= now_chk <= end_dt_chk):
#                     continue
#                 # =========================================================
#                 if not_recording:
#                     # 標記為異常中斷 + 修 end 為 now，並同步 block_data
#                     try:
#                         if hasattr(block, "mark_aborted"):
#                             block.mark_aborted("編碼器非錄影狀態")
#                         else:
#                             if hasattr(block, "set_state"):
#                                 block.set_state("WAITING")
#                                 block.flash_warning(600)
#                         block.update_text_position()
#                     except RuntimeError:
#                         continue
#                     # 同步回 JSON（把 end 修到 now）
#                     try:
#                         start_dt = QDateTime(block.start_date, hourf_to_qtime(block.start_hour))
#                         new_duration_h = max(0.0, round(start_dt.secsTo(now) / 3600.0, 3))
#                         block.duration_hours = new_duration_h
#                         end_dt = block.compute_end_dt()
#                         end_qdate = end_dt.date()
#                         et = end_dt.time()
#                         end_hour = round(et.hour() + et.minute()/60 + et.second()/3600, 4)
#                         block.update_block_data({
#                             "duration":   block.duration_hours,
#                             "end_hour":   end_hour,
#                             "end_qdate":  end_qdate,
#                             "status":     getattr(block, "status", ""),  # "狀態：❌ 異常中斷"
#                         })
#                     except RuntimeError:
#                         continue
#                     except Exception:
#                         pass
#         # 儲存並刷新畫面（安全包一層）
#         try:
#             parent_view.save_schedule()
#             parent_view.update()
#         except Exception:
#             pass
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