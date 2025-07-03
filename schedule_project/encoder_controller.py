# encoder_controller.py

from encoder_utils import connect_socket, send_command
import os
from datetime import datetime

class EncoderController:
    def __init__(self, record_root):
        self.record_root = record_root

    def get_full_path(self, encoder_name, filename):
        date_folder = datetime.today().strftime("%m.%d.%Y")
        date_prefix = datetime.today().strftime("%m%d")
        return os.path.abspath(os.path.join(self.record_root, date_folder, f"{date_prefix}_{filename}"))

    def start_encoder(self, encoder_name, filename):
        full_path = self.get_full_path(encoder_name, filename)
        rel_path = os.path.relpath(full_path, start=self.record_root).replace("\\", "/")

        print(f"[debug] Setfile target: encoder_name='{encoder_name}', rel_path='{rel_path}'")

        sock = connect_socket()
        if not sock:
            return False, "❌ 無法連線"

        # 嘗試三參數格式
        res1 = send_command(sock, f'Setfile "{encoder_name}" 1 "{rel_path}"')
        if "Invalid Parameters" in res1:
            print("⚠️ 三參數格式失敗，改用二參數格式")
            res1 = send_command(sock, f'Setfile "{encoder_name}" "{rel_path}"')

        res2 = send_command(sock, f'Start "{encoder_name}" 1')
        sock.close()

        return ("OK" in res1 and "OK" in res2), rel_path


    def stop_encoder(self, encoder_name):
        sock = connect_socket()
        if not sock:
            return False
        res = send_command(sock, f'Stop "{encoder_name}" 1')
        sock.close()
        return "OK" in res
