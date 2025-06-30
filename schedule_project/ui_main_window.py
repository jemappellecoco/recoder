# ui_main_window.py
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QPushButton, QLabel, QDateEdit, QInputDialog,
    QVBoxLayout, QHBoxLayout, QLineEdit, QApplication, QSizePolicy, QMessageBox, QMenu
)
from PySide6.QtCore import QDate, Qt
from schedule_view import ScheduleView
from encoder_utils import list_encoders, init_socket, close_socket, send_persistent_command
from datetime import datetime
import os

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # 初始化持久 socket，模擬 telnet 風格的連線模式
        init_socket()

        # 🄟️ 顯示所有 encoder 名稱
        self.encoder_names = list_encoders()
        if not self.encoder_names:
            print("⚠️ 沒有從 socket 抓到 encoder，使用預設值")
            self.encoder_names = ["encoder1", "encoder2"]
        print("✅ Encoder 列表：", self.encoder_names)

        self.setWindowTitle("橫向錄影時間表（跨日）")
        self.setGeometry(100, 100, 1600, 900)

        main_widget = QWidget(self)
        main_layout = QHBoxLayout(main_widget)
        self.setCentralWidget(main_widget)

        self.encoder_entries = {}
        self.encoder_status = {}

        encoder_panel = QWidget()
        encoder_layout = QVBoxLayout(encoder_panel)
        encoder_layout.setSpacing(10)
        encoder_panel.setFixedWidth(500)

        # 建立每個 encoder 的控制列
        for name in self.encoder_names:
            line = QHBoxLayout()
            label = QLabel(name)
            entry = QLineEdit()
            start_btn = QPushButton("▶️")
            stop_btn = QPushButton("⏹")
            path_btn = QPushButton("📁")
            status = QLabel("等待中")

            entry.setFixedWidth(120)
            status.setFixedWidth(80)
            path_btn.setFixedWidth(30)

            line.addWidget(label)
            line.addWidget(entry)
            line.addWidget(start_btn)
            line.addWidget(stop_btn)
            line.addWidget(path_btn)
            line.addWidget(status)

            encoder_layout.addLayout(line)

            start_btn.clicked.connect(lambda _, n=name, e=entry, s=status: self.encoder_start(n, e, s))
            stop_btn.clicked.connect(lambda _, n=name, s=status: self.encoder_stop(n, s))
            path_btn.clicked.connect(lambda _, n=name, e=entry: self.show_file_path(n, e))

            self.encoder_entries[name] = entry
            self.encoder_status[name] = status

        # 右側畫面顯示區
        right_panel = QWidget()
        right_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        right_layout = QVBoxLayout(right_panel)

        toolbar = QWidget()
        toolbar_layout = QHBoxLayout(toolbar)

        self.date_label = QLabel("起始日期：")
        self.date_picker = QDateEdit(QDate.currentDate())
        self.date_picker.setCalendarPopup(True)
        self.date_picker.dateChanged.connect(self.update_start_date)

        self.add_button = QPushButton("➕ 新增排程")
        self.add_button.clicked.connect(self.add_new_block)

        self.save_button = QPushButton("💾 儲存")
        self.save_button.clicked.connect(lambda: self.view.save_schedule())

        self.load_button = QPushButton("📂 載入")
        self.load_button.clicked.connect(lambda: self.view.load_schedule())

        self.prev_button = QPushButton("⬅️ 前一週")
        self.prev_button.clicked.connect(lambda: self.shift_date(-7))

        self.next_button = QPushButton("➡️ 下一週")
        self.next_button.clicked.connect(lambda: self.shift_date(+7))

        toolbar_layout.addWidget(self.date_label)
        toolbar_layout.addWidget(self.date_picker)
        toolbar_layout.addStretch()
        toolbar_layout.addWidget(self.prev_button)
        toolbar_layout.addWidget(self.next_button)
        toolbar_layout.addWidget(self.add_button)
        toolbar_layout.addWidget(self.save_button)
        toolbar_layout.addWidget(self.load_button)

        self.view = ScheduleView()
        self.view.encoder_names = self.encoder_names
        self.view.encoder_status = self.encoder_status
        self.view.draw_grid()
        self.view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self.show_block_context_menu)

        right_layout.addWidget(toolbar)
        right_layout.addWidget(self.view)

        main_layout.addWidget(encoder_panel)
        main_layout.addWidget(right_panel)

    def closeEvent(self, event):
        # UI 關閉時自動釋放 socket
        close_socket()
        event.accept()

    def add_new_block(self):
        text, ok = QInputDialog.getText(self, "節目名稱", "請輸入節目名稱：")
        if ok and text:
            new_date = self.view.base_date.addDays(1)
            self.view.add_time_block(qdate=new_date, track_index=1, start_hour=9, duration=4, label=text)

    def update_start_date(self, qdate):
        self.view.set_start_date(qdate)

    def shift_date(self, days):
        new_date = self.view.base_date.addDays(days)
        self.view.set_start_date(new_date)
        self.date_picker.setDate(new_date)

    def show_file_path(self, encoder_name, entry_widget):
        filename = entry_widget.text().strip()
        if filename == "":
            QMessageBox.information(self, "檔案路徑", f"{encoder_name} 尚未設定檔名。")
            return
        date_folder = datetime.today().strftime("%m.%d.%Y")
        date_prefix = datetime.today().strftime("%m%d")
        path = f'{date_folder}\\{date_prefix}_{filename}'
        QMessageBox.information(self, "📁 檔案儲存位置", f"{encoder_name} 檔案儲存路徑為：\n\n{path}")

    def show_block_context_menu(self, pos):
        scene_pos = self.view.mapToScene(pos)
        for item in self.view.scene.items():
            if hasattr(item, 'label') and item.contains(item.mapFromScene(scene_pos)):
                menu = QMenu(self)
                label = item.label
                menu.addAction(f"查看檔案名稱：{label}")
                menu.exec(self.view.mapToGlobal(pos))
                break

    def encoder_start(self, encoder_name, entry_widget, status_label):
        filename = entry_widget.text().strip()
        if filename == "":
            status_label.setText("⚠️ 檔名空白")
            status_label.setStyleSheet("color: orange;")
            return

        date_folder = datetime.today().strftime("%m.%d.%Y")
        date_prefix = datetime.today().strftime("%m%d")
        path = f'{date_folder}\\{date_prefix}_{filename}'

        status_label.setText("🔁 傳送中...")
        status_label.setStyleSheet("color: blue;")
        QApplication.processEvents()

        res1 = send_persistent_command(f'Setfile "{encoder_name}" 1 {path}')
        res2 = send_persistent_command(f'Start "{encoder_name}" 1')

        if "OK" in res1 and "OK" in res2:
            status_label.setText("✅ 錄影中")
            status_label.setStyleSheet("color: green;")
        else:
            status_label.setText("❌ 錯誤")
            status_label.setStyleSheet("color: red;")

    def encoder_stop(self, encoder_name, status_label):
        status_label.setText("🔁 停止中...")
        status_label.setStyleSheet("color: blue;")
        QApplication.processEvents()

        res = send_persistent_command(f'Stop "{encoder_name}" 1')

        if "OK" in res:
            status_label.setText("⏹ 已停止")
            status_label.setStyleSheet("color: gray;")
        else:
            status_label.setText("❌ 停止失敗")
            status_label.setStyleSheet("color: red;")
