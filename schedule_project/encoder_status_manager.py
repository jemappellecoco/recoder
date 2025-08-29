# encoder_status_manager.py
from encoder_utils import send_persistent_command  # 👈 改用持久連線
from utils import log
import time
import re
class EncoderStatusManager:
    def __init__(self, cooldown_ms: int = 800, log_every_s: int = 10):
        self.encoder_last_state = {}     # {name: raw_response}
        self._last_query_ts = {}         # {name: epoch_ms}
        self._last_log_ts = {}           # {name: epoch_s}
        self._last_good_parsed = {}      # {name: (text, color)}
        self._cooldown_ms = cooldown_ms
        self._log_every_s = log_every_s

    def _parse(self, res: str):
        """把 EncStatus 回應字串轉成 (text, color)，永遠保底回傳 tuple"""
        if not isinstance(res, str):
            return "❌ 無回應", "red"

        r = re.sub(r'[\x00-\x1f]+', ' ', res).strip().lower()

        # ✅ 錄影中
        if "running" in r or "runned" in r or "splitting" in r or "splitted" in r:
            return "✅ 錄影中", "green"

        # ⏳ 轉態中（不當異常，不累計）
        if "stopping" in r or "pausing" in r:
            return "⏳ 轉態中", "orange"

        # ⏸ / 🟡 可恢復的非錄影（不當異常，不累計）
        if "paused" in r:
            return "⏸ 已暫停", "blue"
        if "preparing" in r:
            return "🟡 準備中", "blue"
        if "prepared" in r:
            return "🟡 已就緒", "blue"

        # ⛔/❌ 硬否定（要列入異常累計）
        if "stopped" in r:
            return "⛔ 已停止", "red"
        if "none" == r or " none" in r:  # disposed
            return "⛔ 已釋放(編碼器已處置)", "red"
        if "no encoder exists" in r:
            return "⛔ 尚未建立編碼器", "red"
        if "error" in r:
            return "❌ 錯誤", "red"

        return "❓ 未知", "gray"


    

    def _maybe_log(self, name: str, res: str, changed: bool):
        now_s = int(time.time())
        last = self._last_log_ts.get(name, 0)
        if changed or (now_s - last) >= self._log_every_s:
            log(f"⬅️ EncStatus {name}: {res}")
            self._last_log_ts[name] = now_s

    def get_status(self, encoder_name: str):
        """
        回傳單一 encoder 狀態 (status_text, color)
        - 800ms 內重複查詢直接回快取，避免頻繁阻塞 I/O
        - 真查詢時使用持久連線，降低卡頓
        """
        now_ms = int(time.time() * 1000)
        last_ms = self._last_query_ts.get(encoder_name, 0)

        # 冷卻時間內直接回快取（仍保證有值）
        if (now_ms - last_ms) < self._cooldown_ms and encoder_name in self.encoder_last_state:
            cached = self.encoder_last_state[encoder_name]
            return self._parse(cached)

        # 真正查一次（持久連線）
        try:
            res = send_persistent_command(f'EncStatus "{encoder_name}"', encoder_name=encoder_name)

        except Exception as e:
            res = str(e)
        prev_raw = self.encoder_last_state.get(encoder_name)
        changed = (prev_raw != res)

        self._last_query_ts[encoder_name] = now_ms
        self.encoder_last_state[encoder_name] = res
        self._maybe_log(encoder_name, res, changed)

        # 若 raw 沒變，直接用先前的「解析後」結果（避免重複波動）
        if not changed and encoder_name in self._last_good_parsed:
            return self._last_good_parsed[encoder_name]

        parsed = self._parse(res)

        # ❗回退策略：
        # - 若是未知/無回應，就回退到「最後一次可用解析」
        # - 否則更新「最後一次可用解析」
        if parsed[0] in ("❓ 未知", "❌ 無回應"):
            if encoder_name in self._last_good_parsed:
                return self._last_good_parsed[encoder_name]
            # 沒有可回退就維持未知
            return parsed
        else:
            self._last_good_parsed[encoder_name] = parsed
            return parsed

        # prev = self.encoder_last_state.get(encoder_name)
        # changed = (prev != res)
        #  # ✏️ 更新查詢時間與狀態快取
        # self._last_query_ts[encoder_name] = now_ms
        # # ✅ 若沒變化，就不重新解析，直接用舊的解析結果
        # if not changed and prev is not None:
        #     return self._parse(prev)
        # self.encoder_last_state[encoder_name] = res
        # # self._last_query_ts[encoder_name] = now_ms
        # self._maybe_log(encoder_name, res, changed)
        # parsed = self._parse(res)
        #     # ✅ 若回傳未知（❓），保留上一個可解析狀態（但仍更新快取）
        # if parsed[0] == "❓ 未知" and prev is not None:
        #     return self._parse(prev)

        # return parsed

    def refresh_all(self, encoder_names):
        """回傳 {encoder_name: (status_text, color)}"""
        return {name: self.get_status(name) for name in encoder_names}
