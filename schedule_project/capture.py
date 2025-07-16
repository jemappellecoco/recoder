import os
from encoder_utils import send_encoder_command

import time

def take_snapshot_from_block(block, encoder_names, snapshot_root: str = "E:/"):
    """
    根據錄影區塊資訊（TimeBlock）拍攝快照，並將其儲存至 snapshot_root/日期/img/ 資料夾，檔名為 UUID.png。
    """

    date_str = block.start_date.toString("MM.dd.yyyy")
    block_id = block.block_id
    encoder_name = encoder_names[block.track_index]
    filename = f"{block_id}"

    snapshot_dir = os.path.join(snapshot_root, date_str, "img")
    snapshot_relative = os.path.relpath(os.path.join(date_str, "img", filename))
    snapshot_full = os.path.join(snapshot_dir, f"{filename}.png") 

    os.makedirs(snapshot_dir, exist_ok=True)
     # ✅ 刪除舊縮圖（不管有後綴或空格都刪）
    for f in os.listdir(snapshot_dir):
        if f.startswith(filename):
            try:
                os.remove(os.path.join(snapshot_dir, f))
            except Exception as e:
                print(f"⚠️ 無法刪除舊圖片 {f}：{e}")
    print(f"📸 拍照中 - block: {block.label} / encoder: {encoder_name}")
    print(f"📂 儲存位置: {snapshot_full}")
    # print(f"📂 目錄：{snapshot_dir}")
    # print(f"🖼️ 檔案：{filename}")

    send_encoder_command(encoder_name, f'SetSnapshotFileName "{encoder_name}" "{snapshot_relative}"')
    response = send_encoder_command(encoder_name, f'SnapShot "{encoder_name}"')
    print(f"📡 SnapShot 指令回應: {response}")

    if os.path.exists(snapshot_full):
        print(f"✅ 已儲存：{snapshot_full}")
    else:
        print(f"⚠️ 檔案未生成，請檢查路徑或權限：{snapshot_full}")

    return snapshot_full
def take_snapshot_by_encoder(encoder_name, snapshot_root="E:/"):
    """
    拍攝指定 encoder 的快照，儲存為 snapshot_root/preview/<encoder_name>.png
    """
    subdir = "preview"
    filename = encoder_name.replace(" ", "_")  # 檔名不能有空格
    snapshot_dir = os.path.join(snapshot_root, subdir)
    snapshot_relative = (os.path.join(subdir, filename))
    snapshot_full = os.path.join(snapshot_dir, f"{filename}.png")

    os.makedirs(snapshot_dir, exist_ok=True)
    # ✅ 刪除舊的 snapshot（包含 xxx.png, xxx 0001.png, ...）
    for f in os.listdir(snapshot_dir):
        if f.startswith(filename):  # 不管有沒有空格或編號都刪
            try:
                os.remove(os.path.join(snapshot_dir, f))
            except Exception as e:
                print(f"⚠️ 無法刪除舊圖片 {f}：{e}")
    time.sleep(0.5)
    print(f"📸 為 {encoder_name} 拍照 ➜ {snapshot_full}")
    send_encoder_command(encoder_name, f'SetSnapshotFileName "{encoder_name}" "{snapshot_relative}"')
    res = send_encoder_command(encoder_name, f'SnapShot "{encoder_name}"')
    print("📡 Snapshot 回應：", res)
    print(f"[Debug] encoder_name: {encoder_name}")
    print(f"[Debug] filename: {filename}")
    print(f"[Debug] snapshot_relative: {snapshot_relative}")
    return snapshot_full if os.path.exists(snapshot_full) else None