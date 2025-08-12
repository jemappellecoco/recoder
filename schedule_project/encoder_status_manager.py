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
        self._cooldown_ms = cooldown_ms
        self._log_every_s = log_every_s

    def _parse(self, res: str):
        """把回應字串轉成 (text, color)，未知就回 None 讓上層決定是否保留上一個狀態"""
        if not isinstance(res, str):
            return None

        # 正規化：去控制字元、trim、轉小寫
        r = re.sub(r'[\x00-\x1f]+', ' ', res).strip().lower()

        # 常見變體/雜訊的容錯
        # 例：ok\nRunning、ready、idle、timeout、disconnected 等
        if "running" in r or "runned" in r:
            return "✅ 錄影中", "green"
        if "paused" in r:
            return "⏸ 暫停中", "orange"
        if ("stopped" in r) or (" none" in r) or r == "none" or "idle" in r:
            return "⏹ 停止中", "gray"
        if ("prepared" in r) or ("preparing" in r) or ("ready" in r):
            return "🟡 準備中", "blue"
        if ("error" in r) or ("disconnect" in r) or ("timeout" in r):
            return "❌ 錯誤", "red"

    # 其他像是只有 "ok" 但沒狀態字，當未知交給上層處理（不要回「未知」）
        return None

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

        prev = self.encoder_last_state.get(encoder_name)
        changed = (prev != res)
        self.encoder_last_state[encoder_name] = res
        self._last_query_ts[encoder_name] = now_ms
        self._maybe_log(encoder_name, res, changed)

        return self._parse(res)

    def refresh_all(self, encoder_names):
        """回傳 {encoder_name: (status_text, color)}"""
        return {name: self.get_status(name) for name in encoder_names}
