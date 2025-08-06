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
def take_snapshot_from_block(block, encoder_names, snapshot_root: str | None = None):
    if snapshot_root is None:
        snapshot_root = PathManager().snapshot_root
    try:
        if not block.block_id:
            log("❌ 無效 block_id，取消拍照")
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
            log(f"❌ 讀取 snapshot_dir 錯誤：{e}")
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
        log(f"❌ take_snapshot_from_block 錯誤：{e}")
        return None
def take_snapshot_by_encoder(encoder_name, snapshot_root: str | None = None):
    try:
        if snapshot_root is None:
            snapshot_root = PathManager().snapshot_root
        subdir = "preview"
        filename = encoder_name.replace(" ", "_")
        snapshot_dir = os.path.join(snapshot_root, subdir)
        snapshot_relative = os.path.join(subdir, filename)
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
            log(f"❌ 無法讀取 {snapshot_dir}：{e}")
            return None

        log(f"📸 為 {encoder_name} 拍照 ➜ {snapshot_full}")
        send_encoder_command(encoder_name, f'SetSnapshotFileName "{encoder_name}" "{snapshot_relative}"')
        res = send_encoder_command(encoder_name, f'SnapShot "{encoder_name}"')
        log(f"📡 Snapshot 回應：{res}")
        log(f"📸 拍照指令傳送 by encoder")

        cancel_event = threading.Event()

        def check_file():
            return _wait_for_file(snapshot_full, cancel_event)

        future = _snapshot_executor.submit(check_file)
        future.cancel_event = cancel_event
        return future

    except Exception as e:
        log(f"❌ take_snapshot_by_encoder 錯誤：{e}")
        return None
# capture.py
def start_cleanup_timer(snapshot_root, interval=300):
    """啟動自動清理 preview 圖片的計時器並回傳 Timer 參考。"""
    global cleanup_timer, cleanup_running
    cleanup_running = True

    def cleanup():
        """實際執行清理，並根據旗標決定是否排程下一次。"""
        global cleanup_timer
        if not cleanup_running:
            return

        preview_dir = os.path.join(snapshot_root, "preview")
        now = time.time()
        deleted = 0
        try:
            if os.path.exists(preview_dir):
                for f in os.listdir(preview_dir):
                    if f.endswith(".png"):
                        fpath = os.path.join(preview_dir, f)
                        if os.path.isfile(fpath) and now - os.path.getmtime(fpath) > interval:
                            os.remove(fpath)
                            deleted += 1
            log(f"🧹 自動清理 preview，已刪除 {deleted} 張舊圖片")
        except Exception as e:
            log(f"❌ 清理 preview 圖片失敗：{e}")
        finally:
            if cleanup_running:
                cleanup_timer = threading.Timer(interval, cleanup)
                cleanup_timer.daemon = True
                cleanup_timer.start()

    cleanup()  # 立即清理並排程下一次
    return cleanup_timer


def stop_cleanup_timer():
    """停止自動清理計時器。"""
    global cleanup_running, cleanup_timer
    cleanup_running = False
    if cleanup_timer:
        cleanup_timer.cancel()
        cleanup_timer = None
