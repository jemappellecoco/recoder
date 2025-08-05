from PySide6.QtCore import QThread, Signal
from capture import take_snapshot_by_encoder

class SnapshotWorker(QThread):
    finished = Signal(str)

    def __init__(self, encoder_name, snapshot_root):
        super().__init__()
        self.encoder_name = encoder_name
        self.snapshot_root = snapshot_root

    def run(self):
        try:
            take_snapshot_by_encoder(self.encoder_name, snapshot_root=self.snapshot_root)
        finally:
            self.finished.emit(self.encoder_name)
