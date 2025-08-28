# encoder_controller.py

from encoder_utils import connect_socket, send_command,send_encoder_command
import os, re
from path_manager import PathManager
from datetime import datetime
import base64
from utils import log
class EncoderController:
    def __init__(self, record_root):
        self.record_root = record_root
        self.path_manager = PathManager()

    

    # def start_encoder(self, encoder_name, filename):
    #     full_path = self.path_manager.get_full_path(encoder_name, filename)

    #     rel_path = os.path.relpath(full_path, start=self.record_root).replace("\\", "/")

    #     log(f"[debug] Setfile target: encoder_name='{encoder_name}', rel_path='{rel_path}'")


    #     # 嘗試三參數格式
    #     res1 = send_encoder_command(encoder_name, f'Setfile "{encoder_name}" 1 "{rel_path}"')
    #     if "Invalid Parameters" in res1:
    #         log("⚠️ 三參數格式失敗，改用二參數格式")
    #         res1 = send_encoder_command(encoder_name, f'Setfile "{encoder_name}" "{rel_path}"')

    #     res2 = send_encoder_command(encoder_name, f'Start "{encoder_name}" ')

    #     return ("OK" in res1 and "OK" in res2), rel_path
    def start_encoder(self, encoder_name, filename):
        full_path = self.path_manager.get_full_path(encoder_name, filename)
        rel_path  = os.path.relpath(full_path, start=self.record_root).replace("\\", "/")

        log(f"[debug] Setfile target: encoder_name='{encoder_name}', rel_path='{rel_path}'")

        # 先試三參數格式
        res1 = send_encoder_command(encoder_name, f'Setfile "{encoder_name}" 1 "{rel_path}"')
        if "Invalid Parameters" in (res1 or ""):
            log("⚠️ 三參數格式失敗，改用二參數格式")
            res1 = send_encoder_command(encoder_name, f'Setfile "{encoder_name}" "{rel_path}"')

        # 立即印原始回覆（方便對照）
        log(f"↩️ Setfile 回覆：{repr(res1)}")  # NEW

        # NEW: 從 Setfile 回覆直接擷取「實際輸出檔」
        m = re.search(r'OK:\s*New output file:\s*(.+?\.mxf)', (res1 or ""), re.IGNORECASE)
        if m:
            abs_path = os.path.normpath(m.group(1).strip())
            try:
                actual_rel = os.path.relpath(abs_path, start=self.record_root).replace("\\", "/")
            except Exception:
                actual_rel = os.path.basename(abs_path)
            log(f"✅ 實際輸出檔：{actual_rel}")  # 可改成 print 也行
            rel_path = actual_rel  # ← 最小改動：覆蓋回傳用的 rel_path

        # Start（你原本寫法保留）
        res2 = send_encoder_command(encoder_name, f'Start "{encoder_name}" ')
        log(f"↩️ Start  回覆：{repr(res2)}")  # NEW

        ok = ("OK" in (res1 or "")) and ("OK" in (res2 or ""))
        return ok, rel_path  # 型態不變，但已是「實際檔名」

    def stop_encoder(self, encoder_name):
        res = send_encoder_command(encoder_name, f'Stop "{encoder_name}" ')
        return "OK" in res
   