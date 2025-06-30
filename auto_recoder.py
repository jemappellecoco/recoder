from PySide6.QtWidgets import (
    QMainWindow, QWidget, QPushButton, QLabel, QDateEdit, QInputDialog,
    QVBoxLayout, QHBoxLayout, QLineEdit, QApplication, QSizePolicy, QMessageBox, QMenu, QFileDialog
)
from PySide6.QtCore import QDate, Qt
from schedule_view import ScheduleView
from encoder_utils import list_encoders, send_command, connect_socket
from datetime import datetime
import os

import json

CONFIG_FILE = "config.json"

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.record_root = self.load_record_root()  # 自動載入使用者設定

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

        self.root_button = QPushButton("📁 設定儲存路徑")
        self.root_button.clicked.connect(self.select_record_root)

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
        toolbar_layout.addWidget(self.root_button)
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

    def select_record_root(self):
        folder = QFileDialog.getExistingDirectory(self, "選擇儲存根目錄", self.record_root)
        if folder:
            self.record_root = folder
            print(f"📁 使用者設定儲存路徑為：{self.record_root}")
            self.save_record_root(folder)

    def get_full_path(self, encoder_name, filename):
        date_folder = datetime.today().strftime("%m.%d.%Y")
        date_prefix = datetime.today().strftime("%m%d")
        return os.path.abspath(os.path.join(self.record_root, encoder_name, date_folder, f"{date_prefix}_{filename}"))

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
        full_path = self.get_full_path(encoder_name, filename)
        folder_path = os.path.dirname(full_path)
        if os.path.exists(folder_path):
            os.startfile(folder_path)
        else:
            QMessageBox.information(self, "📁 找不到資料夾", f"{folder_path} 不存在")

    def show_block_context_menu(self, pos):
        scene_pos = self.view.mapToScene(pos)
        for item in self.view.scene.items():
            if hasattr(item, 'label') and item.contains(item.mapFromScene(scene_pos)):
                menu = QMenu(self)
                label = item.label
                encoder_index = int(item.track_index) if hasattr(item, 'track_index') else 0
                encoder_name = self.encoder_names[encoder_index] if encoder_index < len(self.encoder_names) else "unknown"
                path = self.get_full_path(encoder_name, label)

                menu.addAction(f"查看檔案名稱：{label}")
                open_action = menu.addAction("📂 開啟資料夾")
                copy_action = menu.addAction("📋 複製路徑")

                selected = menu.exec(self.view.mapToGlobal(pos))

                if selected == open_action:
                    folder_path = os.path.dirname(path)
                    if os.path.exists(folder_path):
                        os.startfile(folder_path)
                    else:
                        QMessageBox.information(self, "📁 找不到資料夾", f"{folder_path} 不存在")
                elif selected == copy_action:
                    clipboard = QApplication.clipboard()
                    clipboard.setText(path)
                break

    def encoder_start(self, encoder_name, entry_widget, status_label):
        filename = entry_widget.text().strip()
        if filename == "":
            status_label.setText("⚠️ 檔名空白")
            status_label.setStyleSheet("color: orange;")
            return

        full_path = self.get_full_path(encoder_name, filename)
        rel_path = os.path.relpath(full_path, start=self.record_root)

        status_label.setText("🔁 傳送中...")
        status_label.setStyleSheet("color: blue;")
        QApplication.processEvents()

        sock = connect_socket()
        if not sock:
            status_label.setText("❌ 無法連線")
            status_label.setStyleSheet("color: red;")
            return

        res1 = send_command(sock, f'Setfile "{encoder_name}" 1 {rel_path}')
        res2 = send_command(sock, f'Start "{encoder_name}" 1')
        sock.close()

        if "OK" in res1 and "OK" in res2:
            status_label.setText("✅ 錄影中")
            status_label.setStyleSheet("color: green;")
        else:
            status_label.setText("❌ 錯誤")
            status_label.setStyleSheet("color: red;")

    def save_record_root(self, path):
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump({'record_root': path}, f)
        except Exception as e:
            print("❌ 無法儲存 config:", e)

    def load_record_root(self):
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('record_root', 'E:/')
        except Exception as e:
            print("❌ 無法讀取 config:", e)
        return 'E:/'

    def encoder_stop(self, encoder_name, status_label):
        status_label.setText("🔁 停止中...")
        status_label.setStyleSheet("color: blue;")
        QApplication.processEvents()

        sock = connect_socket()
        if not sock:
            status_label.setText("❌ 無法建立連線")
            status_label.setStyleSheet("color: red;")
            return

        res = send_command(sock, f'Stop "{encoder_name}" 1')
        sock.close()

        if "OK" in res:
            status_label.setText("⏹ 已停止")
            status_label.setStyleSheet("color: gray;")
        else:
            status_label.setText("❌ 停止失敗")
            status_label.setStyleSheet("color: red;")
