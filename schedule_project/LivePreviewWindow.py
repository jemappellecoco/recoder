# LivePreviewWindow.py
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QPixmap
import requests
from datetime import datetime

class LivePreviewWindow(QWidget):
    def __init__(self, encoder_name, snapshot_url_func, parent=None):
        super().__init__(parent)
        self.encoder_name = encoder_name
        self.snapshot_url_func = snapshot_url_func

        self.setWindowTitle(f"{encoder_name} 即時預覽")
        self.setMinimumSize(480, 270)

        self.label = QLabel("載入中...", self)
        self.label.setAlignment(Qt.AlignCenter)

        layout = QVBoxLayout()
        layout.addWidget(self.label)
        self.setLayout(layout)

        # 每 60 秒更新一次
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_image)
        self.timer.start(60000)
        self.update_image()

    def update_image(self):
        url = self.snapshot_url_func(self.encoder_name)
        try:
            res = requests.get(url, timeout=5)
            res.raise_for_status()
            pixmap = QPixmap()
            pixmap.loadFromData(res.content)
            self.label.setPixmap(pixmap.scaled(self.label.width(), self.label.height(), Qt.KeepAspectRatio))
        except Exception as e:
            self.label.setText(f"❌ 載入失敗：{e}")
