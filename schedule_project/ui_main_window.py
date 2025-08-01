from header_view import HeaderView
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QPushButton, QLabel, QDateEdit, QInputDialog,QDialog,QFrame,QScrollArea,QSplitter,QTextEdit,
    QVBoxLayout, QHBoxLayout, QLineEdit, QApplication, QSizePolicy, QMessageBox, QMenu, QFileDialog
)
from time_block import PreviewImageItem
from PySide6.QtGui import QPixmap,QBrush ,QColor    
from PySide6.QtCore import QDate, Qt,QDateTime,QTime,QTimer
from schedule_view import ScheduleView
from encoder_utils import list_encoders,send_encoder_command
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
from capture import take_snapshot_from_block
from check_schedule_manager import CheckScheduleManager
CONFIG_FILE = "config.json"
from uuid import uuid4
from utils import set_log_box ,log
import glob
from capture import start_cleanup_timer
import time
from EncoderManagerDialog import EncoderManagerDialog
from encoder_utils import save_encoder_config, reload_encoder_config
def find_latest_snapshot_by_prefix(preview_dir, encoder_name):
    pattern = os.path.join(preview_dir, f"{encoder_name}*.png")
    matched_files = glob.glob(pattern)
    if not matched_files:
        return None
    return max(matched_files, key=os.path.getmtime)  # 找出修改時間最新的

class MainWindow(QMainWindow):
    def __init__(self):
        log("🔧 MainWindow 建立中...")  # ✅ 放在最上面
        super().__init__()
        self.is_closing = False
        # === 基礎設定 ===
        self.path_manager = PathManager()
        self.record_root = self.path_manager.record_root
        self.encoder_names = list_encoders()
        self.encoder_controller = EncoderController(self.record_root)
        if not self.encoder_names:
            log("⚠️ 沒有從 socket 抓到 encoder，使用預設值")
            self.encoder_names = ["encoder1", "encoder2"]
        log(f"✅ Encoder 列表：{self.encoder_names}")

        self.setWindowTitle("錄影時間表")
        self.setGeometry(100, 100, 1600, 900)

        # === UI 主體 ===
        main_widget = QWidget(self)
        main_layout = QHBoxLayout(main_widget)
        self.setCentralWidget(main_widget)
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)

        # === 左側 Encoder Scroll 區塊 ===
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        encoder_scroll_content = QWidget()
        encoder_scroll_layout = QVBoxLayout(encoder_scroll_content)
        scroll_area.setWidget(encoder_scroll_content)
        self.encoder_panel = QWidget()
        self.encoder_panel.setObjectName("encoder_panel")
        encoder_layout = QVBoxLayout(self.encoder_panel)
        # encoder_panel = QWidget()
        # encoder_panel.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Preferred)
        # encoder_layout = QVBoxLayout(encoder_panel)

        self.encoder_preview_labels = {}
        self.encoder_pixmaps = {}
        self.encoder_entries = {}
        self.encoder_status = {}
        preview_dir = os.path.join(self.record_root, "preview")
        os.makedirs(preview_dir, exist_ok=True)

        for name in self.encoder_names:
            encoder_widget = QWidget()
            encoder_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            encoder_box = QVBoxLayout(encoder_widget)
            encoder_box.setContentsMargins(0, 0, 0, 0)

            preview_label = QLabel(f"🖼️ {name} 預覽載入中...")
            preview_label.setMinimumHeight(180)
            preview_label.setMinimumWidth(0)
            preview_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
            preview_label.setStyleSheet("border: 1px solid gray; background-color: black; color: white;")
            preview_label.setAlignment(Qt.AlignCenter)
            self.encoder_preview_labels[name] = preview_label
            encoder_box.addWidget(preview_label)

            line = QHBoxLayout()
            label = QLabel(name)
            entry = QLineEdit()
            entry.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            entry.setMaximumWidth(80)
            start_btn = QPushButton("▶️")
            stop_btn = QPushButton("⏹")
            path_btn = QPushButton("📁")
            status = QLabel("+++")
            status.setAlignment(Qt.AlignVCenter)
            line.addWidget(label)
            line.addWidget(entry)
            line.addWidget(start_btn)
            line.addWidget(stop_btn)
            line.addWidget(path_btn)
            line.addWidget(status)
            line.setStretch(0, 1)
            line.setStretch(1, 5)
            line.setStretch(2, 1)
            line.setStretch(3, 1)
            line.setStretch(4, 1)
            line.setStretch(5, 2)
            encoder_box.addLayout(line)
            encoder_layout.addWidget(encoder_widget)

            start_btn.clicked.connect(lambda _, n=name, e=entry, s=status: self.encoder_start(n, e, s))
            stop_btn.clicked.connect(lambda _, n=name, s=status: self.encoder_stop(n, s))
            path_btn.clicked.connect(lambda _, n=name, e=entry: self.show_file_path(n, e))
            self.encoder_entries[name] = entry
            self.encoder_status[name] = status

        # encoder_scroll_layout.addWidget(encoder_panel)
        encoder_scroll_layout.addWidget(self.encoder_panel)

        # === 右側 排程 Panel ===
        right_panel = QWidget()
        right_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setAlignment(Qt.AlignTop)

        # --- Toolbar ---
        toolbar = QWidget()
        toolbar_layout = QHBoxLayout(toolbar)
        undo_button = QPushButton("↩️ 復原刪除")
        undo_button.clicked.connect(lambda: (self.block_manager.undo_last_delete(), self.sync_runner_data()))
        self.date_label = QLabel("起始日期：")
        self.date_picker = QDateEdit(QDate.currentDate())
        self.date_picker.setCalendarPopup(True)
        self.date_picker.dateChanged.connect(self.update_start_date)
        self.select_schedule_button = QPushButton("📄 選擇排程檔")
        self.select_schedule_button.clicked.connect(self.select_schedule_json)
        self.add_button = QPushButton("➕ 新增排程")
        self.add_button.clicked.connect(self.add_new_block)
        self.root_button = QPushButton("📁 設定影片儲存路徑")
        self.root_button.clicked.connect(self.select_record_root)
        self.save_button = QPushButton("💾 儲存")
        self.save_button.clicked.connect(lambda: self.view.save_schedule())
        self.load_button = QPushButton("📂 載入")
        self.load_button.clicked.connect(lambda: (self.view.load_schedule(), self.sync_runner_data()))
        self.prev_button = QPushButton("⬅️ 前一週")
        self.prev_button.clicked.connect(lambda: self.shift_date(-7))
        self.next_button = QPushButton("➡️ 下一週")
        self.next_button.clicked.connect(lambda: self.shift_date(+7))
        self.today_button = QPushButton("📅 今天")
        self.today_button.clicked.connect(self.jump_to_today)
        self.manage_encoder_button = QPushButton("⚙️ 管理 Encoder")
        self.manage_encoder_button.clicked.connect(self.open_encoder_manager)
        toolbar_layout.addWidget(self.manage_encoder_button)

        toolbar_layout.addWidget(self.date_label)
        toolbar_layout.addWidget(self.date_picker)
        toolbar_layout.addStretch()
        toolbar_layout.addWidget(self.today_button)
        toolbar_layout.addWidget(self.select_schedule_button)
        toolbar_layout.addWidget(self.root_button)
        toolbar_layout.addWidget(self.prev_button)
        toolbar_layout.addWidget(self.next_button)
        toolbar_layout.addWidget(self.add_button)
        toolbar_layout.addWidget(self.save_button)
        toolbar_layout.addWidget(self.load_button)
        toolbar_layout.addWidget(undo_button)

        # --- Log box ---
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setLineWrapMode(QTextEdit.NoWrap)
        self.log_box.setFixedHeight(150)
        self.log_box.setStyleSheet("""
            QTextEdit {
                background-color: #111;
                color: #00FF00;
                font-family: Consolas, Courier, monospace;
                font-size: 11px;
                border: 1px solid #333;
            }
        """)
        set_log_box(self.log_box)

        # --- Header & ScheduleView ---
        self.header = HeaderView(self.encoder_names)
        self.view = ScheduleView()
        self.view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.view.encoder_names = self.encoder_names
        self.view.encoder_status = self.encoder_status
        self.view.record_root = self.record_root
        self.view.load_schedule()
        self.view.draw_grid()
        # 自動對齊畫面到「現在時間」
        now = QDateTime.currentDateTime()
        self.base_date = QDate.currentDate()
        self.view.set_start_date(self.base_date)
        self.header.set_base_date(self.base_date)
        self.date_picker.setDate(self.base_date)  # ➤ UI 同步更新日期選擇器
        days_from_base = self.base_date.daysTo(now.date())

        if 0 <= days_from_base < self.view.days:
            total_hours = now.time().hour() + now.time().minute() / 60
            x_pos = int(days_from_base * self.view.day_width + total_hours * self.view.hour_width)
            self.view.horizontalScrollBar().setValue(x_pos)
            log(f"🧭 自動捲動畫面至今天時間：X = {x_pos}")
        self.view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self.show_block_context_menu)
        self.view.path_manager = self.path_manager

        self.block_manager = BlockManager(self.view)
        self.runner = ScheduleRunner(
            schedule_data=self.view.block_data,
            encoder_status=self.encoder_status,
            record_root=self.record_root,
            encoder_names=self.encoder_names,
            blocks=self.view.blocks
        )# ✅ 加這裡！建立 schedule_manager
        self.schedule_manager = CheckScheduleManager(
            encoder_names=self.encoder_names,
            encoder_status_dict=self.encoder_status,
            runner=self.runner,
            parent_view_getter=lambda: self.view
        )
        self.schedule_manager.schedule_data = self.view.block_data
        self.schedule_manager.blocks = self.view.blocks
        self.check_timer = QTimer(self)
        self.check_timer.timeout.connect(self.safe_check_schedule)
        self.check_timer.start(1000)
        self.schedule_manager.schedule_data = self.view.block_data
        self.schedule_manager.blocks = self.view.blocks
        self.view.runner = self.runner

        # --- Header + View Layout ---
        header_schedule_wrapper = QWidget()
        wrapper_layout = QVBoxLayout(header_schedule_wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.setSpacing(0)
        wrapper_layout.setAlignment(Qt.AlignTop)
        wrapper_layout.addWidget(self.header)
        wrapper_layout.addWidget(self.view)

        right_layout.addWidget(toolbar)
        right_layout.addWidget(header_schedule_wrapper)
        right_layout.addWidget(self.log_box)
        # === 加入 splitter ===
        splitter.addWidget(scroll_area)
        splitter.addWidget(right_panel)

        # === 啟動時間器 ===
        self.encoder_status_timer = QTimer(self)
        self.encoder_status_timer.timeout.connect(self.update_encoder_status_labels)
        self.encoder_status_timer.start(2000)

        self.snapshot_timer = QTimer(self)
        self.snapshot_timer.timeout.connect(self.update_all_encoder_snapshots)
        self.snapshot_timer.start(30000)

      

        self.sync_runner_data()
        self.view.horizontalScrollBar().valueChanged.connect(self.header.sync_scroll)
        self.update_encoder_status_labels()
        self.view.draw_grid()
        start_cleanup_timer(self.record_root)
        QTimer.singleShot(3000, self.update_all_encoder_snapshots)
        # === 初始復原狀態 ===
        # for name in self.encoder_names:
        #     snapshot_path = take_snapshot_by_encoder(name, snapshot_root=self.record_root)
        #     log(f"📸 啟動時補拍 {name} ➔ {snapshot_path}")

        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    schedule_file = config.get("schedule_file")
                    if schedule_file and os.path.exists(schedule_file):
                        self.view.schedule_file = schedule_file
                        self.view.load_schedule(filename=schedule_file)
                        log(f"📂 自動載入之前選的檔案：{schedule_file}")
        except Exception as e:
            log(f"⚠️ config.json 載入失敗：{e}")
    def open_encoder_manager(self):
        dialog = EncoderManagerDialog(self)
        if dialog.exec():  # 如果點了儲存
            new_config = dialog.get_result()
            save_encoder_config(new_config)
            reload_encoder_config()
            self.reload_encoder_list()
    def reload_encoder_list(self):
        log("🔄 重新載入 Encoder 列表")
        self.encoder_names = list_encoders()
        self.encoder_status = {}
        self.encoder_entries = {}
        self.encoder_preview_labels = {}

        # ✅ 清空 encoder_panel UI 區塊
        encoder_panel = self.findChild(QWidget, "encoder_panel")
        if encoder_panel:
            layout = encoder_panel.layout()
            if layout:
                while layout.count():
                    item = layout.takeAt(0)
                    widget = item.widget()
                    if widget:
                        widget.setParent(None)

                for name in self.encoder_names:
                    widget = self.build_encoder_widget(name)
                    layout.addWidget(widget)

        # ✅ 更新 Header & View 需要的 encoder info
        self.view.encoder_names = self.encoder_names
        self.view.encoder_status = self.encoder_status
        self.header.set_encoder_names(self.encoder_names)

        # ✅ 修正 block 對應 encoder track
        self.view.remap_block_tracks()
        self.view.rebuild_tracks()
        self.view.draw_grid()  # ←❗別漏這個
        self.view.save_schedule()
        self.sync_runner_data()
        self.update_encoder_status_labels()

    def jump_to_today(self):
        today = QDate.currentDate()
        self.view.set_start_date(today)
        self.header.set_base_date(today)
        self.date_picker.setDate(today)
    def safe_check_schedule(self):
        try:
            self.schedule_manager.check_schedule()
        except Exception as e:
            log(f"❌ [Timer] check_schedule 錯誤：{e}")
        
    def build_encoder_widget(self, name):
        encoder_widget = QWidget()
        encoder_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        encoder_box = QVBoxLayout(encoder_widget)
        encoder_box.setContentsMargins(0, 0, 0, 0)

        # 🖼️ 預覽圖
        preview_label = QLabel(f"🖼️ {name} 預覽載入中...")
        preview_label.setMinimumHeight(160)
        preview_label.setStyleSheet("border: 1px solid gray; background-color: black; color: white;")
        preview_label.setAlignment(Qt.AlignCenter)
        self.encoder_preview_labels[name] = preview_label
        encoder_box.addWidget(preview_label)

        # 📏 控制列（整排）
        control_row = QHBoxLayout()

        label = QLabel(name)
        label.setFixedWidth(60)
        label.setMinimumHeight(32)
        label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        
        entry = QLineEdit()
        entry.setFixedHeight(32)
        entry.setMaximumWidth(100)
        
        # stop_btn.setFixedHeight(32)
        # path_btn.setFixedHeight(32)
        # status.setFixedHeight(32)

        

        

        start_btn = QPushButton("▶️")
        stop_btn = QPushButton("⏹")
        path_btn = QPushButton("📁")
        status = QLabel("狀態：+++")
        for btn in [start_btn, stop_btn, path_btn]:
            btn.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)
            btn.setMinimumWidth(15)
            btn.setMaximumWidth(60)
            btn.setFixedHeight(28)
        
        status.setFixedWidth(100)
        status.setAlignment(Qt.AlignVCenter)

        control_row.addWidget(label)
        control_row.addWidget(entry)
        control_row.addWidget(start_btn)
        control_row.addWidget(stop_btn)
        control_row.addWidget(path_btn)
        control_row.addWidget(status)

        encoder_box.addLayout(control_row)

        # 📎 綁定與註冊
        start_btn.clicked.connect(lambda _, n=name, e=entry, s=status: self.encoder_start(n, e, s))
        stop_btn.clicked.connect(lambda _, n=name, s=status: self.encoder_stop(n, s))
        path_btn.clicked.connect(lambda _, n=name, e=entry: self.show_file_path(n, e))

        self.encoder_entries[name] = entry
        self.encoder_status[name] = status

        return encoder_widget
    def update_preview_scaled(self, name):
        label = self.encoder_preview_labels.get(name)
        pixmap = self.encoder_pixmaps.get(name)
        if label and pixmap:
            scaled = pixmap.scaled(label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            label.setPixmap(scaled)

    def resizeEvent(self, event):
        for name in self.encoder_names:
            self.update_preview_scaled(name)
        super().resizeEvent(event)
    def update_encoder_status_labels(self):
        try:
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
        except Exception as e:
            log(f"❌ [Timer] update_encoder_status_labels 發生錯誤：{e}")
            
            
    def update_all_encoder_snapshots(self):
        if getattr(self, "is_closing", False):
            log("🛑 UI 正在關閉，取消 snapshot 拍攝")
            return
        preview_dir = os.path.join(self.record_root, "preview")
        def capture_and_update(name, label):
            try:
                take_snapshot_by_encoder(name, snapshot_root=self.record_root)
                preview_dir = os.path.join(self.record_root, "preview")
                latest_path = find_latest_snapshot_by_prefix(preview_dir, name)
                time.sleep(0.3)
                if latest_path and os.path.exists(latest_path):
                    pixmap = QPixmap(latest_path)
                    self.encoder_pixmaps[name] = pixmap
                    self.update_preview_scaled(name)
                else:
                    label.setText(f"❌ 無法載入 {name} 圖片")
            except Exception as e:
                log(f"❌ [Timer] 快照更新錯誤（{name}）：{e}")

        # def capture_and_update(name, label):
        #     try:
        #         take_snapshot_by_encoder(name, snapshot_root=self.record_root)
        #         filename = f"{name.replace(' ', '_')}.png"
        #         snapshot_full = os.path.join(preview_dir, filename)
            
        #         if os.path.exists(snapshot_full):
        #             pixmap = QPixmap(snapshot_full)
        #             self.encoder_pixmaps[name] = pixmap
        #             self.update_preview_scaled(name)
        #         else:
        #             label.setText(f"❌ 無法載入 {name} 圖片")
        #     except Exception as e:
        #         log(f"❌ [Timer] 快照更新錯誤（{name}）：{e}")

        # try:
        #      with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        #         for name, label in self.encoder_preview_labels.items():
        #             executor.submit(capture_and_update, name, label)
        # except Exception as e:
        #     log(f"❌ [Timer] update_all_encoder_snapshots 整體錯誤：{e}")
        try:
            names = list(self.encoder_preview_labels.keys())

            for i, name in enumerate(names):
                label = self.encoder_preview_labels[name]
                QTimer.singleShot(i * 700, lambda n=name, l=label: capture_and_update(n, l))
        except Exception as e:
            log(f"❌ [Timer] update_all_encoder_snapshots 整體錯誤：{e}")

    
    def select_schedule_json(self):
        path, _ = QFileDialog.getSaveFileName(self, "選擇排程檔案", self.record_root, "JSON 檔 (*.json)")
        if path:
            self.view.schedule_file = path
            self.view.load_schedule(filename=path)
            log(f"📂 使用者選擇排程檔案：{path}")
            config = {}
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    config = json.load(f)
            config["schedule_file"] = path
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
    def select_record_root(self):
        folder = QFileDialog.getExistingDirectory(self, "選擇儲存根目錄", self.record_root)
        if folder:
            self.record_root = folder
            log(f"📁 使用者設定儲存路徑為：{self.record_root}")
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
        self.header.set_base_date(qdate)  
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
            if isinstance(item, PreviewImageItem):
                continue  # ✅ 避免圖片觸發右鍵選單
            if hasattr(item, 'label') and item.contains(item.mapFromScene(scene_pos)):
                menu = QMenu(self)
                label = item.label
                 # ➤ 嘗試取得檔案路徑（防止例外）
                try:
                    path = self.path_manager.get_full_path("", label)
                except Exception as e:
                    log(f"⚠️ get_full_path 錯誤: {e}")
                    path = ""

                menu.addAction(f"查看檔案名稱：{label}")
                open_action = menu.addAction("📂 開啟資料夾")
                copy_action = menu.addAction("📋 複製路徑")
                delete_action = menu.addAction("🗑️ 刪除排程")
                 # ✅ 禁用已結束 block 的刪除功能
                if getattr(item, 'has_ended', False) or item.status.strip() in ["✅ 錄影中", "⏹ 停止中"]:
                    delete_action.setEnabled(False)
                    delete_action.setText("🗑️ 已開始或完成，不可刪")
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
                        "end_qdate": end_qdate,
                         "status": "狀態：✅ 已結束"
                        
                    })
                    block.status = "狀態：✅ 已結束"
                    block.setBrush(QBrush(QColor(180, 180, 180, 180)))  # 灰色背景
                    block.update_geometry(self.view.base_date)
                    block.update_text_position()
                    self.view.save_schedule()
                    stopped_block_id = block.block_id
                    break  # ✅ 只處理一個正在錄的 block

            # ✅ 同步 runner 狀態：只加上那一個 block_id
            if stopped_block_id:
                self.runner.already_stopped.add(stopped_block_id)

            status_label.setText("狀態： 已結束")
            status_label.setStyleSheet("color: gray")
        else:
            status_label.setText("狀態：❌ 停止失敗")
            status_label.setStyleSheet("color: red")
        
        self.runner.refresh_encoder_statuses()
        self.view.draw_grid()
        self.sync_runner_data()
        
        QApplication.processEvents()
        self.view.update()
    def encoder_start(self, encoder_name, entry_widget, status_label):
        filename = entry_widget.text().strip()
        if not filename:
            status_label.setText("⚠️ 檔名空白")
            status_label.setStyleSheet("color: orange;")
            return

        now = datetime.now()
        start_hour = round(now.hour + now.minute / 60, 2)
        track_index = self.encoder_names.index(encoder_name)
        qdate = QDate.currentDate()

        # 🔍 嘗試找出最接近的下一個 block
        future_blocks = [
            b for b in self.view.block_data
            if b["track_index"] == track_index and
               b["qdate"] == qdate and
               b["start_hour"] > start_hour
        ]
        future_blocks.sort(key=lambda b: b["start_hour"])
        default_duration = 4.0
        if future_blocks:
            next_start = future_blocks[0]["start_hour"]
            max_duration = round(next_start - start_hour, 2)
            if max_duration <= 0:
                QMessageBox.warning(self, "❌ 時段衝突", "⚠️ 後面已有排程，無法手動錄影")
                return
            duration = min(default_duration, max_duration)
        else:
            duration = default_duration

        already_exists = any(
            b["label"] == filename and
            b["qdate"] == qdate and
            b["start_hour"] == start_hour and
            b["track_index"] == track_index
            for b in self.view.block_data
        )

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
            block_id = next(
                (b["id"] for b in self.view.block_data if
                 b["label"] == filename and
                 b["qdate"] == qdate and
                 b["start_hour"] == start_hour and
                 b["track_index"] == track_index),
                None
            )

        if block_id:
            self.runner.already_started.add(block_id)
            self.runner.start_encoder(encoder_name, filename, status_label, block_id)
            for b in self.view.block_data:
                if b.get("id") == block_id:
                    b["status"] = "✅ 錄影中"
                    break
            self.view.save_schedule()  # ✅ 立即儲存
        block = next((blk for blk in self.view.blocks if blk.block_id == block_id), None)
        if block:
            try:
                snapshot_path = take_snapshot_from_block(block, self.encoder_names)
                if snapshot_path and os.path.exists(snapshot_path):
                    encoder_name = self.encoder_names[block.track_index]
                    self.encoder_pixmaps[encoder_name] = QPixmap(snapshot_path)
                    self.update_preview_scaled(encoder_name)
                    log(f"📸 手動啟動拍照成功 ➜ {snapshot_path}")
                else:
                    log(f"⚠️ 手動啟動拍照失敗 ➜ {snapshot_path}")
            except Exception as e:
                log(f"❌ 手動啟動拍照錯誤：{e}")
        # if block:
        #     take_snapshot_from_block(block, self.encoder_names)

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

        
    def sync_runner_data(self):
        self.runner.schedule_data = self.view.block_data
        self.runner.blocks = self.view.blocks  # ✅ 這行很重要！
        self.schedule_manager.schedule_data = self.view.block_data
        self.schedule_manager.blocks = self.view.blocks
        log(f"🔁 [同步] Runner block 數量：{len(self.runner.blocks)}")

    def closeEvent(self, event):
        self.is_closing = True

        import capture
        capture.cleanup_running = False  # ✅ 停止清理 timer

        if hasattr(self, "encoder_status_timer"):
            self.encoder_status_timer.stop()
        if hasattr(self, "snapshot_timer"):
            self.snapshot_timer.stop()
        if hasattr(self, "check_timer"):
            self.check_timer.stop()
        if hasattr(self, "runner"):
            self.runner.stop_timers()
        if hasattr(self, "view"):
            self.view.stop_timers()

        log("👋 MainWindow 已關閉")
        super().closeEvent(event)
        os._exit(0)