from PySide6.QtWidgets import (
    QMainWindow, QWidget, QPushButton, QLabel, QDateEdit, QInputDialog,QDialog,
    QVBoxLayout, QHBoxLayout, QLineEdit, QApplication, QSizePolicy, QMessageBox, QMenu, QFileDialog
)
from PySide6.QtCore import QDate, Qt
from schedule_view import ScheduleView
from encoder_utils import list_encoders, send_command, connect_socket
from datetime import datetime
import os
from schedule_runner import ScheduleRunner
import json
from block_manager import BlockManager
from encoder_controller import EncoderController
from add_block_dialog import AddBlockDialog
from path_manager import PathManager
CONFIG_FILE = "config.json"

class MainWindow(QMainWindow):
    def __init__(self):
        print("🔧 MainWindow 建立中...")  # ✅ 放在最上面
        super().__init__()
        
        self.path_manager = PathManager()
        self.record_root = self.path_manager.record_root  # 自動載入使用者設定
        self.encoder_names = list_encoders()
        self.encoder_controller = EncoderController(self.record_root) 
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
        undo_button = QPushButton("↩️ 復原刪除")
        undo_button.clicked.connect(lambda: self.block_manager.undo_last_delete())
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
        toolbar_layout.addWidget(undo_button)
        self.view = ScheduleView()
        self.view.encoder_names = self.encoder_names
        self.view.encoder_status = self.encoder_status
        self.view.draw_grid()
        self.view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self.show_block_context_menu)
        self.runner = ScheduleRunner(
            schedule_data=self.view.block_data,
            encoder_status=self.encoder_status,
            record_root=self.record_root,
            encoder_names=self.encoder_names,
            blocks=self.view.blocks
        )
        right_layout.addWidget(toolbar)
        right_layout.addWidget(self.view)

        main_layout.addWidget(encoder_panel)
        main_layout.addWidget(right_panel)
        self.block_manager = BlockManager(self.view)
        self.runner.check_schedule()
        
    def select_record_root(self):
        folder = QFileDialog.getExistingDirectory(self, "選擇儲存根目錄", self.record_root)
        if folder:
            self.record_root = folder
            print(f"📁 使用者設定儲存路徑為：{self.record_root}")
            self.path_manager.save_record_root(folder)

    
    def add_new_block(self):
        def check_overlap(track_index, start_hour, duration):
         return self.view.is_overlap(self.view.base_date, track_index, start_hour, duration)

        dialog = AddBlockDialog(self, 
                encoder_names=self.encoder_names, 
                overlap_checker=check_overlap)
        if dialog.exec() == QDialog.Accepted:
            name, qdate, time_obj, duration, encoder_name = dialog.get_values()
            track_index = self.encoder_names.index(encoder_name)
            start_hour = round(time_obj.hour() + time_obj.minute() / 60, 2)
            self.block_manager.add_block_with_unique_label(
                name, 
                track_index=track_index, 
                start_hour=start_hour, 
                duration=duration, 
                encoder_name=encoder_name,
                qdate=qdate
                )

            
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
        full_path = self.path_manager.get_full_path(encoder_name, filename)
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
                path = self.path_manager.get_full_path("", label)

                menu.addAction(f"查看檔案名稱：{label}")
                open_action = menu.addAction("📂 開啟資料夾")
                copy_action = menu.addAction("📋 複製路徑")
                delete_action = menu.addAction("🗑️ 刪除排程")
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
                elif selected == delete_action:
                    self.block_manager.remove_block_by_id(item.block_id)

                break

    def encoder_start(self, encoder_name, entry_widget, status_label):
        filename = entry_widget.text().strip()
        if not filename:
            status_label.setText("⚠️ 檔名空白")
            status_label.setStyleSheet("color: orange;")
            return

        ok, _ = self.encoder_controller.start_encoder(encoder_name, filename)
        if ok:
            # ❌ 不手動設定狀態，讓 ScheduleRunner 控制

            if not any(b["label"] == filename for b in self.view.block_data):
                now = datetime.now()
                minute = (now.minute + 7) // 15 * 15
                if minute == 60:
                    hour = now.hour + 1
                    minute = 0
                else:
                    hour = now.hour
                start_hour = round(hour + minute / 60, 2)
                track_index = self.encoder_names.index(encoder_name)
                qdate = QDate.currentDate()
                self.block_manager.add_block_with_unique_label(
                    filename,
                    track_index=track_index,
                    start_hour=start_hour,
                    duration=4.0,
                    encoder_name=encoder_name,
                    qdate = qdate
                )

            # ✅ 同步更新 runner 的內部資料再 check
            self.runner.schedule_data = self.view.block_data
            self.runner.blocks = self.view.blocks
            self.runner.check_schedule()

        else:
            status_label.setText("❌ 錯誤")
            status_label.setStyleSheet("color: red")



    

    

    def encoder_stop(self, encoder_name, status_label):
        status_label.setText("🔁 停止中...")
        status_label.setStyleSheet("color: blue")
        QApplication.processEvents()

        ok = self.encoder_controller.stop_encoder(encoder_name)
        if ok:
            # ✅ 不再手動設定狀態
            self.runner.check_schedule()
        else:
            status_label.setText("❌ 停止失敗")
            status_label.setStyleSheet("color: red")