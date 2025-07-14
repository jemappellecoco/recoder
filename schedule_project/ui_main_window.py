from PySide6.QtWidgets import (
    QMainWindow, QWidget, QPushButton, QLabel, QDateEdit, QInputDialog,QDialog,
    QVBoxLayout, QHBoxLayout, QLineEdit, QApplication, QSizePolicy, QMessageBox, QMenu, QFileDialog
)
from PySide6.QtGui import QPixmap
from PySide6.QtCore import QDate, Qt,QDateTime,QTime,QTimer
from schedule_view import ScheduleView
from encoder_utils import list_encoders, send_command, connect_socket, send_persistent_command
from capture import take_snapshot_by_encoder
from datetime import datetime
import os
from schedule_runner import ScheduleRunner
import json
from block_manager import BlockManager
from encoder_controller import EncoderController
from add_block_dialog import AddBlockDialog
from path_manager import PathManager
from utils_conflict import find_conflict_blocks
CONFIG_FILE = "config.json"
from uuid import uuid4
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
        self.encoder_preview_labels = {}
        preview_dir = os.path.join(self.record_root, "preview")
        os.makedirs(preview_dir, exist_ok=True)
        for name in self.encoder_names:
            encoder_box = QVBoxLayout()
             # 🖼️ 預覽圖
            preview_label = QLabel(f"🖼️ {name} 預覽載入中...")
            preview_label.setFixedSize(480, 270)
            preview_label.setStyleSheet("border: 1px solid gray; background-color: black; color: white;")
            preview_label.setAlignment(Qt.AlignCenter)
            self.encoder_preview_labels[name] = preview_label
            encoder_box.addWidget(preview_label)

            # 🎛️ 控制列
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

            encoder_box.addLayout(line)
            encoder_layout.addLayout(encoder_box)  # 把整組 encoder_box 加進 encoder_layout

            # 📎 功能綁定
            start_btn.clicked.connect(lambda _, n=name, e=entry, s=status: self.encoder_start(n, e, s))
            stop_btn.clicked.connect(lambda _, n=name, s=status: self.encoder_stop(n, s))
            path_btn.clicked.connect(lambda _, n=name, e=entry: self.show_file_path(n, e))

            # 🗂️ 登記
            self.encoder_entries[name] = entry
            self.encoder_status[name] = status
            
        right_panel = QWidget()
        right_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        right_layout = QVBoxLayout(right_panel)

        toolbar = QWidget()
        toolbar_layout = QHBoxLayout(toolbar)
        undo_button = QPushButton("↩️ 復原刪除")
        undo_button.clicked.connect(lambda: (self.block_manager.undo_last_delete(), self.sync_runner_data()))

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
        self.load_button.clicked.connect(lambda: (self.view.load_schedule(), self.sync_runner_data()))
        
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
        self.view.record_root = self.record_root
        self.view.draw_grid()
        self.view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self.show_block_context_menu)
        self.view.path_manager = self.path_manager
        self.update_encoder_status_labels()
        self.encoder_status_timer = QTimer(self)
        self.encoder_status_timer.timeout.connect(self.update_encoder_status_labels)
        self.encoder_status_timer.start(2000)  # 每兩秒更新一次
        # ✅ 一定要在 runner 建立後再指定回去 view
        self.runner = ScheduleRunner(
            schedule_data=self.view.block_data,
            encoder_status=self.encoder_status,
            record_root=self.record_root,
            encoder_names=self.encoder_names,
            blocks=self.view.blocks
        )
        self.view.runner = self.runner
        self.sync_runner_data()  
        right_layout.addWidget(toolbar)
        right_layout.addWidget(self.view)
       

        self.snapshot_timer = QTimer(self)
        self.snapshot_timer.timeout.connect(self.update_all_encoder_snapshots)
        self.snapshot_timer.start(30000)
        
        main_layout.addWidget(encoder_panel)
        main_layout.addWidget(right_panel)
        self.block_manager = BlockManager(self.view)
        self.runner.check_schedule()
        self.runner.refresh_encoder_statuses()
        self.schedule_timer = QTimer(self)
        self.schedule_timer.timeout.connect(self.runner.check_schedule)
        self.schedule_timer.start(1000)  # 每 1000ms (1秒) 檢查一次
    # 🔽 在 encoder 初始化後（ex: encoder_names 取得後）：
        for name in self.encoder_names:
            snapshot_path = take_snapshot_by_encoder(name, snapshot_root=self.record_root)
            print(f"📸 啟動時補拍 {name} ➜ {snapshot_path}")
    def update_encoder_status_labels(self):
        now = QDateTime.currentDateTime()
        for name, status_label in self.encoder_status.items():
            related_blocks = [
                b for b in self.view.block_data if b.get("encoder_name") == name
            ]
            current_status = "無排程"
            for b in related_blocks:
                start_dt = QDateTime(b["qdate"], QTime(int(b["start_hour"]), int((b["start_hour"] % 1) * 60)))
                end_dt = start_dt.addSecs(int(b["duration"] * 3600))
                if now < start_dt:
                    current_status = "等待中"
                elif start_dt <= now <= end_dt:
                    current_status = "錄影中"
                    break
                elif now > end_dt:
                    current_status = "已結束"
            status_label.setText(f"狀態：{current_status}")
    def update_all_encoder_snapshots(self):
        preview_dir = os.path.join(self.record_root, "preview")
        for name, label in self.encoder_preview_labels.items():
            take_snapshot_by_encoder(name, snapshot_root=self.record_root)
            filename = f"{name.replace(' ', '_')}.png"  # 確保一致
            snapshot_full = os.path.join(preview_dir, filename)

            if os.path.exists(snapshot_full):
                pixmap = QPixmap(snapshot_full)
                label.setPixmap(pixmap.scaled(label.width(), label.height(), Qt.KeepAspectRatio))
            else:
                label.setText(f"❌ 無法載入 {name} 圖片")

    def select_record_root(self):
        folder = QFileDialog.getExistingDirectory(self, "選擇儲存根目錄", self.record_root)
        if folder:
            self.record_root = folder
            print(f"📁 使用者設定儲存路徑為：{self.record_root}")
            self.path_manager.save_record_root(folder)

    
    def add_new_block(self):
        def check_overlap(track_index, start_hour, duration, qdate):
            return self.view.is_overlap(qdate, track_index, start_hour, duration, exclude_label=None)

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
            self.sync_runner_data()
            
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
                 # ✅ 禁用已結束 block 的刪除功能
                if hasattr(item, 'has_ended') and item.has_ended:
                    delete_action.setEnabled(False)
                    delete_action.setText("🗑️ 已完成，不可刪")
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

    def encoder_stop(self, encoder_name, status_label):
        status_label.setText("狀態：🔁 停止中...")
        status_label.setStyleSheet("color: blue")
        QApplication.processEvents()

        ok = self.encoder_controller.stop_encoder(encoder_name)

        now = QDateTime.currentDateTime()
        encoder_index = self.encoder_names.index(encoder_name)

        if ok:
            stopped_block_id = None  # 用來記錄有被停止的 block id

            for block in self.view.blocks:
                if block.track_index != encoder_index:
                    continue

                start_dt = QDateTime(block.start_date, QTime(int(block.start_hour), int((block.start_hour % 1) * 60)))
                end_dt = start_dt.addSecs(int(block.duration_hours * 3600))

                if start_dt <= now <= end_dt:
                    block.status = "⏹ 停止中"
                     # ⏱️ 依據停止時間更新長度與畫面
                    new_duration = max(0.0, round(start_dt.secsTo(now) / 3600, 2))
                    block.duration_hours = new_duration
                    block.update_geometry(self.view.base_date)
                    end_hour, end_qdate = block.compute_end_info()
                    block.update_block_data({
                        "duration": block.duration_hours,
                        "end_hour": end_hour,
                        "end_qdate": end_qdate
                    })
                    block.update_text_position()
                    self.view.save_schedule()
                    stopped_block_id = block.block_id
                    break  # ✅ 只處理一個正在錄的 block

            # ✅ 同步 runner 狀態：只加上那一個 block_id
            if stopped_block_id:
                self.runner.already_stopped.add(stopped_block_id)

            status_label.setText("狀態：⏹ 停止中")
            status_label.setStyleSheet("color: gray")
        else:
            status_label.setText("狀態：❌ 停止失敗")
            status_label.setStyleSheet("color: red")
        
        self.runner.refresh_encoder_statuses()
        self.view.draw_grid()
        self.sync_runner_data()
    def encoder_start(self, encoder_name, entry_widget, status_label):
        
        filename = entry_widget.text().strip()
        if not filename:
            status_label.setText("⚠️ 檔名空白")
            status_label.setStyleSheet("color: orange;")
            return

        # ✅ 先計算出錄影時間資訊
        now = datetime.now()
        start_hour = round(now.hour + now.minute / 60, 2)
        duration = 4.0
        track_index = self.encoder_names.index(encoder_name)
        qdate = QDate.currentDate()
        already_exists = any(
            b["label"] == filename and
            b["qdate"] == qdate and
            b["start_hour"] == start_hour and
            b["track_index"] == track_index
            for b in self.view.block_data
        )
     # ✅ 檢查時間衝突（只有在尚未加入 block 才檢查）
        if not already_exists:
            conflicts = find_conflict_blocks(
                "schedule.json", qdate, track_index, start_hour, duration
            )
            if conflicts:
                QMessageBox.warning(
                    self,
                    "❌ 時段衝突",
                    "⚠️ 無法錄影，該時段與以下排程衝突：\n" + "\n".join(conflicts),
                )
                return

        
        # ok, _ = self.encoder_controller.start_encoder(encoder_name, filename)
        # if ok:
            # ✅ 補 block（如沒有）
            if not already_exists:
                block_id = str(uuid4())
                self.block_manager.add_block_with_unique_label(
                    filename,
                    track_index=track_index,
                    start_hour=start_hour,
                    duration=duration,
                    encoder_name=encoder_name,
                    qdate=qdate,
                    block_id=block_id
                )
            else:
                # 🔍 找出現有 block_id（防止重複）
                block_id = next(
                    (b["id"] for b in self.view.block_data if
                    b["label"] == filename and
                    b["qdate"] == qdate and
                    b["start_hour"] == start_hour and
                    b["track_index"] == track_index),
                    None
                )

            # ✅ 記得標記已啟動，防止 check_schedule 重啟
            if block_id:
                self.runner.already_started.add(block_id)
                self.runner.start_encoder(encoder_name, filename, status_label, block_id)
            # ✅ 更新畫面狀態
            now_qt = QDateTime.currentDateTime()
            for block in self.view.blocks:
                if block.track_index == track_index:
                    start_dt = QDateTime(block.start_date, QTime(int(block.start_hour), int((block.start_hour % 1) * 60)))
                    end_dt = start_dt.addSecs(int(block.duration_hours * 3600))
                    if start_dt <= now_qt <= end_dt:
                        block.status = "✅ 錄影中"
                        block.update_text_position()
                        break

            self.runner.refresh_encoder_statuses()
            self.view.draw_grid()
            self.update_encoder_status_labels()
        # else:
        #     status_label.setText("狀態：❌ 錯誤")
        #     status_label.setStyleSheet("color: red")


    def mark_block_stopped(self, encoder_name):
        now = QDateTime.currentDateTime()
        encoder_index = self.encoder_names.index(encoder_name)

        for block in self.view.blocks:
            if block.track_index == encoder_index:
                start_dt = QDateTime(block.start_date, QTime(int(block.start_hour), int((block.start_hour % 1) * 60)))
                end_dt = start_dt.addSecs(int(block.duration_hours * 3600))
                if start_dt <= now <= end_dt:
                    block.status = "⏹ 停止中"
                    block.update_text_position()
                    self.runner.already_stopped.add(block.block_id)

                    # ✅ 同步 block_data 裡的狀態（儲存用）
                    for b in self.view.block_data:
                        if b.get("id") == block.block_id:
                            b["status"] = "⏹ 停止中"
                    break  
    def sync_runner_data(self):
        self.runner.schedule_data = self.view.block_data
        self.runner.blocks = self.view.blocks  # ✅ 這行很重要！
        print(f"🔁 [同步] Runner block 數量：{len(self.runner.blocks)}")

        