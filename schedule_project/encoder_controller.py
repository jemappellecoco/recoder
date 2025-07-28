# encoder_controller.py

from encoder_utils import connect_socket, send_command,send_encoder_command
import os
from path_manager import PathManager
from datetime import datetime
import base64
from utils import log
class EncoderController:
    def __init__(self, record_root):
        self.record_root = record_root
        self.path_manager = PathManager()

    

    def start_encoder(self, encoder_name, filename):
        full_path = self.path_manager.get_full_path(encoder_name, filename)

        rel_path = os.path.relpath(full_path, start=self.record_root).replace("\\", "/")

        log(f"[debug] Setfile target: encoder_name='{encoder_name}', rel_path='{rel_path}'")


        # 嘗試三參數格式
        res1 = send_encoder_command(encoder_name, f'Setfile "{encoder_name}" 1 "{rel_path}"')
        if "Invalid Parameters" in res1:
            log("⚠️ 三參數格式失敗，改用二參數格式")
            res1 = send_encoder_command(encoder_name, f'Setfile "{encoder_name}" "{rel_path}"')

        res2 = send_encoder_command(encoder_name, f'Start "{encoder_name}" 1')

        return ("OK" in res1 and "OK" in res2), rel_path

    def stop_encoder(self, encoder_name):
        res = send_encoder_command(encoder_name, f'Stop "{encoder_name}" 1')
        return "OK" in res
   