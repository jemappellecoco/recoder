# EncoderManagerDialog.py

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QWidget, QMessageBox
)
from encoder_utils import encoder_config  # 全域設定
from utils import log  # 你現有的 log 工具

class EncoderManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙️ 管理 Encoder 裝置")
        self.resize(480, 400)

        self.encoder_data = encoder_config.copy()  # 深複製目前設定
        self.encoder_rows = {}  # 儲存每列元件
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # ➕ 新增區
        add_layout = QHBoxLayout()
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("裝置名稱（例如 Cam3）")
        self.ip_input = QLineEdit()
        self.ip_input.setPlaceholderText("IP 位址")
        self.port_input = QLineEdit()
        self.port_input.setPlaceholderText("Port")

        self.add_button = QPushButton("➕ 新增")
        self.add_button.clicked.connect(self.add_encoder)

        add_layout.addWidget(self.name_input)
        add_layout.addWidget(self.ip_input)
        add_layout.addWidget(self.port_input)
        add_layout.addWidget(self.add_button)
        layout.addLayout(add_layout)

        # 📋 現有 encoder 列表（可刪除）
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll_widget = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_widget)
        self.scroll.setWidget(self.scroll_widget)
        layout.addWidget(self.scroll)

        self.refresh_encoder_list()

        # 💾 儲存按鈕
        button_row = QHBoxLayout()
        save_btn = QPushButton("💾 儲存並關閉")
        save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        button_row.addStretch()
        button_row.addWidget(save_btn)
        button_row.addWidget(cancel_btn)
        layout.addLayout(button_row)

    def refresh_encoder_list(self):
        # 清空舊內容
        for i in reversed(range(self.scroll_layout.count())):
            item = self.scroll_layout.itemAt(i)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        # 逐一建立 encoder 列
        self.encoder_rows = {}
        for name, info in self.encoder_data.items():
            row = QHBoxLayout()
            name_label = QLabel(name)
            ip_label = QLabel(info.get("host", ""))
            port_label = QLabel(str(info.get("port", "")))
            delete_btn = QPushButton("🗑️")
            delete_btn.setFixedWidth(40)
            delete_btn.clicked.connect(lambda _, n=name: self.delete_encoder(n))

            row.addWidget(name_label)
            row.addStretch()
            row.addWidget(ip_label)
            row.addWidget(port_label)
            row.addWidget(delete_btn)

            wrapper = QWidget()
            wrapper.setLayout(row)
            self.scroll_layout.addWidget(wrapper)
            self.encoder_rows[name] = wrapper

    def add_encoder(self):
        name = self.name_input.text().strip()
        ip = self.ip_input.text().strip()
        port_text = self.port_input.text().strip()

        if not name or not ip or not port_text:
            QMessageBox.warning(self, "欄位不完整", "請填寫名稱、IP 與 Port")
            return

        try:
            port = int(port_text)
        except ValueError:
            QMessageBox.warning(self, "Port 格式錯誤", "請輸入數字的 Port")
            return

        if name in self.encoder_data:
            QMessageBox.warning(self, "名稱重複", f"已經有一個叫 {name} 的裝置")
            return

        self.encoder_data[name] = {
            "host": ip,
            "port": port
        }
        self.name_input.clear()
        self.ip_input.clear()
        self.port_input.clear()

        log(f"➕ 已新增 encoder：{name} ➜ {ip}:{port}")
        self.refresh_encoder_list()

    def delete_encoder(self, name):
        reply = QMessageBox.question(
            self,
            "確認刪除",
            f"是否要刪除裝置 {name}？",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.encoder_data.pop(name, None)
            log(f"🗑️ 已刪除 encoder：{name}")
            self.refresh_encoder_list()

    def get_result(self):
        return self.encoder_data
