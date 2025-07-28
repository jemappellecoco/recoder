
import os
import time
from datetime import datetime
from encoder_utils import send_encoder_command
from utils import log

def cleanup_old_snapshots(preview_dir, encoder_name, keep_minutes=3):
    now = time.time()
    base_filename = encoder_name.replace(" ", "_")
    for f in os.listdir(preview_dir):
        if f.startswith(base_filename) and f.endswith(".png"):
            full_path = os.path.join(preview_dir, f)
            try:
                if now - os.path.getmtime(full_path) > keep_minutes * 60:
                    os.remove(full_path)
                    log(f"🧹 刪除過期圖片：{full_path}")
            except Exception as e:
                log(f"⚠️ 無法刪除 {full_path}：{e}")

def take_snapshot_from_block(block, encoder_names, snapshot_root: str = "E:/"):
    try:
        if not block.block_id:
            log("❌ 無效 block_id，取消拍照")
            return None

        date_str = block.start_date.toString("MM.dd.yyyy")
        block_id = block.block_id
        encoder_name = encoder_names[block.track_index]

        timestamp = datetime.now().strftime("%H%M%S")
        filename = f"{block_id}_{timestamp}"
        snapshot_dir = os.path.join(snapshot_root, date_str, "img")
        snapshot_relative = os.path.join(date_str, "img", filename)
        snapshot_full = os.path.join(snapshot_dir, f"{filename}.png")

        os.makedirs(snapshot_dir, exist_ok=True)

        log(f"📸 拍照中 - block: {block.label} / encoder: {encoder_name}")
        log(f"📂 儲存位置: {snapshot_full}")

        send_encoder_command(encoder_name, f'SetSnapshotFileName "{encoder_name}" "{snapshot_relative}"')
        response = send_encoder_command(encoder_name, f'SnapShot "{encoder_name}"')
        log(f"📡 SnapShot 指令回應: {response}")

        if os.path.exists(snapshot_full):
            log(f"✅ 已儲存：{snapshot_full}")
            return snapshot_full
        else:
            log(f"⚠️ 檔案未生成，請檢查路徑或權限：{snapshot_full}")
            return None

    except Exception as e:
        log(f"❌ take_snapshot_from_block 錯誤：{e}")
        return None

def take_snapshot_by_encoder(encoder_name, snapshot_root="E:/", keep_minutes=10):
    try:
        subdir = "preview"
        timestamp = datetime.now().strftime("%H%M%S")
        base_filename = encoder_name.replace(" ", "_")
        filename = f"{base_filename}_{timestamp}"
        snapshot_dir = os.path.join(snapshot_root, subdir)
        snapshot_relative = os.path.join(subdir, filename)
        snapshot_full = os.path.join(snapshot_dir, f"{filename}.png")

        os.makedirs(snapshot_dir, exist_ok=True)
        cleanup_old_snapshots(snapshot_dir, encoder_name, keep_minutes)

        time.sleep(0.5)
        log(f"📸 為 {encoder_name} 拍照 ➜ {snapshot_full}")
        send_encoder_command(encoder_name, f'SetSnapshotFileName "{encoder_name}" "{snapshot_relative}"')
        res = send_encoder_command(encoder_name, f'SnapShot "{encoder_name}"')
        log(f"📡 Snapshot 回應：{res}")
        log(f"[Debug] encoder_name: {encoder_name}")
        log(f"[Debug] snapshot_relative: {snapshot_relative}")

        return snapshot_full if os.path.exists(snapshot_full) else None

    except Exception as e:
        log(f"❌ take_snapshot_by_encoder 錯誤：{e}")
        return None
