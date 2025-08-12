from encoder_utils import send_encoder_command
from utils import log

class EncoderStatusManager:
    def __init__(self):
        self.encoder_last_state = {}

    def get_status(self, encoder_name):
        """回傳單一 encoder 狀態 (status_text, color)"""
        try:
            res = send_encoder_command(encoder_name, f'EncStatus "{encoder_name}"')
            log(f"⬅️ Response from {encoder_name}: {res}")
        except Exception as e:
            res = str(e)

        # ⛔ 不再 return None，就算結果一樣也回傳狀態
        self.encoder_last_state[encoder_name] = res

        # 狀態解析
        if "Running" in res or "Runned" in res:
            return "✅ 錄影中", "green"
        elif "Paused" in res:
            return "⏸ 暫停中", "orange"
        elif "Stopped" in res or "None" in res:
            return "⏹ 停止中", "gray"
        elif "Prepared" in res or "Preparing" in res:
            return "🟡 準備中", "blue"
        elif "Error" in res:
            return "❌ 錯誤", "red"
        else:
            return f"❓未知\n{res}", "black"

    def refresh_all(self, encoder_names):
        """回傳所有 encoder 狀態字典 {encoder_name: (status_text, color)}"""
        statuses = {}
        for name in encoder_names:
            result = self.get_status(name)
            if result:  # 一定會有值了
                statuses[name] = result
        return statuses
