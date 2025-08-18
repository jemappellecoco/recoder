import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor

from encoder_utils import send_encoder_command
from utils import log
from path_manager import PathManager
cleanup_running = True

_snapshot_executor = ThreadPoolExecutor(max_workers=4)


def _wait_for_file(path, cancel_event, timeout=5):
    start = time.time()
    while time.time() - start < timeout:
        if cancel_event.is_set():
            log("🛑 拍照已取消")
            return None
        if os.path.exists(path):
            log(f"✅ 已儲存：{path}")
            return path
        time.sleep(0.1)
    log(f"⚠️ 檔案未生成，請檢查路徑或權限：{path}")
    return None
def take_snapshot_from_block(block, encoder_names, snapshot_root: str = None):
    try:
        # 守門：record_root 必須存在
        if not snapshot_root or not os.path.isdir(snapshot_root):
            log(f"ℹ️ 略過快照：snapshot_root 無效或不存在 -> {snapshot_root}")
            return None
        if not block or not block.block_id:
            log("ℹ️ 略過快照：無效的 block/block_id")
            return None

        date_str = block.start_date.toString("MM.dd.yyyy")
        block_id = block.block_id
        encoder_name = encoder_names[block.track_index]
        filename = f"{block_id}"
        snapshot_dir = os.path.join(snapshot_root, date_str, "img")
        snapshot_relative = os.path.relpath(os.path.join(date_str, "img", filename))
        snapshot_full = os.path.join(snapshot_dir, f"{filename}.png")

        os.makedirs(snapshot_dir, exist_ok=True)

        try:
            for f in os.listdir(snapshot_dir):
                if f.startswith(filename):
                    try:
                        os.remove(os.path.join(snapshot_dir, f))
                    except Exception as e:
                        log(f"⚠️ 無法刪除舊圖片 {f}：{e}")
        except Exception as e:
            log(e, "讀取 snapshot_dir 錯誤")
            return None

        log(f"📸 拍照中 - block: {block.label} / encoder: {encoder_name}")
        log(f"📂 儲存位置: {snapshot_full}")

        send_encoder_command(encoder_name, f'SetSnapshotFileName "{encoder_name}" "{snapshot_relative}"')
        response = send_encoder_command(encoder_name, f'SnapShot "{encoder_name}"')
        log(f"📡 SnapShot 指令回應: {response}")

        cancel_event = threading.Event()

        def check_file():
            return _wait_for_file(snapshot_full, cancel_event)

        future = _snapshot_executor.submit(check_file)
        future.cancel_event = cancel_event
        return future

    except Exception as e:
        log(f"❌ take_snapshot_from_block 錯誤：{e}",level="ERROR")
        return None
def take_snapshot_by_encoder(encoder_name, preview_root: str | None = None):
    try:
        if preview_root is None:
            preview_root = PathManager().snapshot_root  # 通常是 "Z:/"

        filename = encoder_name.replace(" ", "_")

        # ✅ 傳給 encoder 的相對路徑（沒有副檔名）
        snapshot_relative = os.path.join("preview", filename).replace("\\", "/")

        # ✅ 本機實際要等的圖片檔案（Z:/preview/Bak4-1.png）
        snapshot_dir = os.path.join(preview_root, "preview")
        snapshot_full_path = os.path.join(snapshot_dir, f"{filename}.png")

        os.makedirs(snapshot_dir, exist_ok=True)

        # 🔄 清除舊圖
        # try:
        #     for f in os.listdir(snapshot_dir):
        #         if f.startswith(filename):
        #             try:
        #                 os.remove(os.path.join(snapshot_dir, f))
        #             except Exception as e:
        #                 log(f"⚠️ 無法刪除舊圖片 {f}：{e}")
        # except Exception as e:
        #     log(f"❌ 無法讀取 snapshot_dir：{e}")
        #     return None

        log(f"📸 為 {encoder_name} 拍照 ➜ 儲存預期路徑：{snapshot_full_path}")
        log(f"🛰️ 傳給 encoder 的路徑（不含副檔名）：{snapshot_relative}")

        send_encoder_command(encoder_name, f'SetSnapshotFileName "{encoder_name}" "{snapshot_relative}"')
        res = send_encoder_command(encoder_name, f'SnapShot "{encoder_name}"')
        log(f"📡 Snapshot 回應：{res}")

        cancel_event = threading.Event()

        def check_file():
            return _wait_for_file(snapshot_full_path, cancel_event)

        future = _snapshot_executor.submit(check_file)
        future.cancel_event = cancel_event
        return future

    except Exception as e:
        log(f"❌ take_snapshot_by_encoder 錯誤：{e}",level="ERROR")
        return None

# capture.py
def start_cleanup_timer(preview_root, check_period=600, max_age=300, run_immediately=False):
    """每 check_period 秒執行一次清理；只刪除修改時間超過 max_age 秒的檔案。"""
    global cleanup_timer, cleanup_running
    cleanup_running = True

    def cleanup():
        global cleanup_timer
        if not cleanup_running:
            return
        now = time.time()
        deleted = 0
        try:
            if os.path.exists(preview_root):
                for f in os.listdir(preview_root):
                    if f.endswith(".png"):
                        fpath = os.path.join(preview_root, f)
                        if os.path.isfile(fpath) and now - os.path.getmtime(fpath) > max_age:
                            os.remove(fpath)
                            deleted += 1
            log(f"🧹 自動清理 preview，已刪除 {deleted} 張舊圖片")
        except Exception as e:
            log(f"❌ 清理 preview 圖片失敗：{e}",level="ERROR")
        finally:
            if cleanup_running:
                cleanup_timer = threading.Timer(check_period, cleanup)
                cleanup_timer.daemon = True
                cleanup_timer.start()

    if run_immediately:
        cleanup()                         # 立刻跑一次（可選）
    else:
        cleanup_timer = threading.Timer(check_period, cleanup)  # 延後第一次，避免一開就黑屏
        cleanup_timer.daemon = True
        cleanup_timer.start()

    return cleanup_timer



def stop_cleanup_timer():
    """停止自動清理計時器。"""
    global cleanup_running, cleanup_timer
    cleanup_running = False
    if cleanup_timer:
        cleanup_timer.cancel()
        cleanup_timer = None
