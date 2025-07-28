
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QPixmap
import os
from path_manager import PathManager

class LivePreviewWindow(QWidget):
    def __init__(self, encoder_name, parent=None):
        super().__init__(parent)
        self.encoder_name = encoder_name

        self.path_manager = PathManager()
        self.snapshot_root = os.path.join(self.path_manager.record_root, "preview")

        self.setWindowTitle(f"{encoder_name} 即時預覽")
        self.setMinimumSize(480, 270)

        self.label = QLabel("載入中...", self)
        self.label.setAlignment(Qt.AlignCenter)

        layout = QVBoxLayout()
        layout.addWidget(self.label)
        self.setLayout(layout)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_image)
        self.timer.start(60000)
        self.update_image()

    def update_image(self):
        path = self.get_latest_snapshot_path()
        if not path or not os.path.exists(path):
            self.label.setText("❌ 找不到圖片")
            return

        try:
            pixmap = QPixmap(path)
            self.label.setPixmap(pixmap.scaled(self.label.width(), self.label.height(), Qt.KeepAspectRatio))
        except Exception as e:
            self.label.setText(f"❌ 載入失敗：{e}")

    def get_latest_snapshot_path(self):
        base_filename = self.encoder_name.replace(" ", "_")
        try:
            files = [
                f for f in os.listdir(self.snapshot_root)
                if f.startswith(base_filename) and f.endswith(".png")
            ]
            if not files:
                return None
            files.sort(key=lambda x: os.path.getmtime(os.path.join(self.snapshot_root, x)), reverse=True)
            return os.path.join(self.snapshot_root, files[0])
        except Exception as e:
            print(f"⚠️ 錯誤：無法取得圖片：{e}")
            return None
