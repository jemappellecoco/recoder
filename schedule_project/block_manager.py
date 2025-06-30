# block_manager.py

class BlockManager:
    def __init__(self, schedule_view):
        self.view = schedule_view

    def add_block_with_unique_label(self, base_label, track_index=0, start_hour=9, duration=4, encoder_name=None):
        label = base_label
        existing_labels = [b["label"] for b in self.view.block_data]
        i = 1
        while label in existing_labels:
            label = f"{base_label}_{i}"
            i += 1

        qdate = self.view.base_date
        block = self.view.add_time_block(qdate, track_index, start_hour, duration, label)

        # 加入 encoder_name 進 block_data，如果有提供
        block_info = {
            "qdate": qdate,
            "track_index": track_index,
            "start_hour": start_hour,
            "duration": duration,
            "label": label
        }
        if encoder_name:
            block_info["encoder_name"] = encoder_name

        self.view.block_data.append(block_info)
        self.view.save_schedule()
        return block
