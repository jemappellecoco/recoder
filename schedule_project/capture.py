import os
from encoder_utils import send_persistent_command

import os
from encoder_utils import send_persistent_command

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

    print(f"📸 [Snapshot] 準備為 block '{block.label}' 拍照")
    print(f"📂 目錄：{snapshot_dir}")
    print(f"🖼️ 檔案：{filename}")

    send_persistent_command(f'SetSnapshotFileName "{encoder_name}" "{snapshot_relative}"')
    response = send_persistent_command(f'SnapShot "{encoder_name}"')
    print(f"📡 SnapShot 指令回應: {response}")

    if os.path.exists(snapshot_full):
        print(f"✅ 已儲存：{snapshot_full}")
    else:
        print(f"⚠️ 檔案未生成，請檢查路徑或權限：{snapshot_full}")

    return snapshot_full
