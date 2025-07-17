from header_view import HeaderView
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QPushButton, QLabel, QDateEdit, QInputDialog,QDialog,QFrame,QScrollArea,QSplitter,
    QVBoxLayout, QHBoxLayout, QLineEdit, QApplication, QSizePolicy, QMessageBox, QMenu, QFileDialog
)
from time_block import PreviewImageItem
import concurrent.futures
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
        # --- 外層主 layout
        main_layout = QHBoxLayout(main_widget)
        self.setCentralWidget(main_widget)
        
        
        # --- 使用 QSplitter 讓左右區塊可拖動
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)
        
        # === 左側：Encoder Scroll 區塊 ===
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        
        encoder_scroll_content = QWidget()
        encoder_scroll_layout = QVBoxLayout(encoder_scroll_content)
        scroll_area.setWidget(encoder_scroll_content)
        
        # Encoder Panel 包裝所有 encoder
        encoder_panel = QWidget()
        encoder_panel.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Preferred)
        encoder_layout = QVBoxLayout(encoder_panel)

        # # 建立 Encoder 區塊
        self.encoder_preview_labels = {}
        self.encoder_pixmaps = {}
        self.encoder_entries = {}
        self.encoder_status = {}
        preview_dir = os.path.join(self.record_root, "preview")
        os.makedirs(preview_dir, exist_ok=True)
      
            
    # 當視窗大小改變時，自動更新所有 encoder 預覽圖

        
        for name in self.encoder_names:
            encoder_widget = QWidget()
            encoder_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            encoder_box = QVBoxLayout(encoder_widget)
            encoder_box.setContentsMargins(0, 0, 0, 0)
            
             # 🖼️ 預覽圖
            preview_label = QLabel(f"🖼️ {name} 預覽載入中...")
            preview_label.setMinimumHeight(180)
            preview_label.setMinimumWidth(0)  # ← 關鍵
            preview_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
            preview_label.setStyleSheet("border: 1px solid gray; background-color: black; color: white;")
            preview_label.setAlignment(Qt.AlignCenter)
           
            self.encoder_preview_labels[name] = preview_label
            encoder_box.addWidget(preview_label)

            # 🎛️ 控制列
            line = QHBoxLayout()
            label = QLabel(name)
            entry = QLineEdit()
            entry.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            entry.setMaximumWidth(80)  # 保護它不會爆版
            start_btn = QPushButton("▶️")
            stop_btn = QPushButton("⏹")
            path_btn = QPushButton("📁")
            status = QLabel("+++")
            status.setAlignment(Qt.AlignVCenter)
           
            line.addWidget(label)       # index 0
            line.addWidget(entry)       # index 1
            line.addWidget(start_btn)   # index 2
            line.addWidget(stop_btn)    # index 3
            line.addWidget(path_btn)    # index 4
            line.addWidget(status)      # index 5

            # 🔧 指定寬度比例（越大越寬）
            line.setStretch(0, 1)  # label
            line.setStretch(1, 5)  # entry
            line.setStretch(2, 1)  # ▶️
            line.setStretch(3, 1)  # ⏹
            line.setStretch(4, 1)  # 📁
            line.setStretch(5, 2)  # 狀態欄（略寬，否則容易被擠）
            
            encoder_box.addLayout(line)
            encoder_layout.addWidget(encoder_widget)
            
            # 📎 功能綁定
            start_btn.clicked.connect(lambda _, n=name, e=entry, s=status: self.encoder_start(n, e, s))
            stop_btn.clicked.connect(lambda _, n=name, s=status: self.encoder_stop(n, s))
            path_btn.clicked.connect(lambda _, n=name, e=entry: self.show_file_path(n, e))

            # 🗂️ 登記
            self.encoder_entries[name] = entry
            self.encoder_status[name] = status
        encoder_scroll_layout.addWidget(encoder_panel)
        # === 右側：你的原本 right_panel（排程區） ===  
        right_panel = QWidget()
        right_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setAlignment(Qt.AlignTop)
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
        self.header = HeaderView(self.encoder_names)  # ➕ 時間軸 header

        self.view = ScheduleView()
        self.view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.view.encoder_names = self.encoder_names
        self.view.encoder_status = self.encoder_status
        self.view.record_root = self.record_root
        self.view.load_schedule()
        self.view.draw_grid()
        
        self.view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self.show_block_context_menu)
        self.view.path_manager = self.path_manager
      
        
        self.block_manager = BlockManager(self.view)
        
        # ✅ 一定要在 runner 建立後再指定回去 view
        self.runner = ScheduleRunner(
            schedule_data=self.view.block_data,
            encoder_status=self.encoder_status,
            record_root=self.record_root,
            encoder_names=self.encoder_names,
            blocks=self.view.blocks
        )
        self.view.runner = self.runner
        # Header 固定高度
        self.header.setFixedHeight(60)
        self.header.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.header.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # ScheduleView 自帶滾動條
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.sync_runner_data() 
        self.view.horizontalScrollBar().valueChanged.connect(self.header.sync_scroll)
 
        self.update_encoder_status_labels()
        
        self.encoder_status_timer = QTimer(self)
        self.encoder_status_timer.timeout.connect(self.update_encoder_status_labels)
        self.encoder_status_timer.start(2000)
        self.view.draw_grid()

        right_layout.addWidget(toolbar)
        # # === Header + Schedule 用 QSplitter 合併
        # schedule_splitter = QSplitter(Qt.Vertical)
        # schedule_splitter.setHandleWidth(0)  # 隱藏分隔線
        # schedule_splitter.setChildrenCollapsible(False)  # 禁止拖動收起
        # schedule_splitter.setSizes([self.header.height(), 9999])
        # # ➕ HeaderView
       
        # schedule_splitter.addWidget(self.header)
        # schedule_splitter.setStretchFactor(0, 0)
        # schedule_splitter.setStretchFactor(1, 1)
        # # ➕ ScheduleView
        # schedule_splitter.addWidget(self.view)

        # # 將 splitter 加入右側 layout
       
        # right_layout.addWidget(schedule_splitter)
        # # right_layout = QVBoxLayout()
        # right_layout.setContentsMargins(0, 0, 0, 0)
        # right_layout.setSpacing(0)
        # right_layout.setAlignment(Qt.AlignTop)
       
        # === Header + Schedule 垂直貼齊（改成用 QVBoxLayout 包裝）===
        header_schedule_wrapper = QWidget()
        wrapper_layout = QVBoxLayout(header_schedule_wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.setSpacing(0)
        wrapper_layout.setAlignment(Qt.AlignTop)

        # ➕ HeaderView（上方時間軸） & ScheduleView（下方時間區塊）
        wrapper_layout.addWidget(self.header)
        wrapper_layout.addWidget(self.view)

        # 將 toolbar 和 header+schedule 一起加入右側 layout
        right_layout.addWidget(toolbar)
        right_layout.addWidget(header_schedule_wrapper)

        
        # right_layout.addWidget(self.header)   # HeaderView 負責畫時間軸
        # right_layout.addWidget(self.view)     # ScheduleView 負責畫節目區
       # === 加入 splitter 讓左右可調整寬度
        splitter.addWidget(scroll_area)
        splitter.addWidget(right_panel)

        self.snapshot_timer = QTimer(self)
        self.snapshot_timer.timeout.connect(self.update_all_encoder_snapshots)
        self.snapshot_timer.start(30000)
        
       
        # ✅ 最後只加 splitter 到 main_layout
       
        self.block_manager = BlockManager(self.view)
        self.runner.check_schedule()
        self.runner.refresh_encoder_statuses()
        self.schedule_timer = QTimer(self)
        self.schedule_timer.timeout.connect(self.runner.check_schedule)
        self.schedule_timer.start(1000) 
        self.update_encoder_status_labels()
        
          # 每兩秒更新一次
        
    # 🔽 在 encoder 初始化後（ex: encoder_names 取得後）：
        for name in self.encoder_names:
            snapshot_path = take_snapshot_by_encoder(name, snapshot_root=self.record_root)
            print(f"📸 啟動時補拍 {name} ➜ {snapshot_path}")
        
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
        entry.setFixedHeight(32)
        start_btn.setFixedHeight(32)
        stop_btn.setFixedHeight(32)
        path_btn.setFixedHeight(32)
        status.setFixedHeight(32)

        label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        entry = QLineEdit()
        entry.setMaximumWidth(100)

        start_btn = QPushButton("▶️")
        stop_btn = QPushButton("⏹")
        path_btn = QPushButton("📁")
        for btn in [start_btn, stop_btn, path_btn]:
            btn.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)
            btn.setMinimumWidth(15)
            btn.setMaximumWidth(60)
            btn.setFixedHeight(28)
        status = QLabel("狀態：+++")
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

        def capture_and_update(name, label):
            take_snapshot_by_encoder(name, snapshot_root=self.record_root)
            filename = f"{name.replace(' ', '_')}.png"
            snapshot_full = os.path.join(preview_dir, filename)

            if os.path.exists(snapshot_full):
                pixmap = QPixmap(snapshot_full)
                self.encoder_pixmaps[name] = pixmap
                self.update_preview_scaled(name)            
            else:
                label.setText(f"❌ 無法載入 {name} 圖片")

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
        for name, label in self.encoder_preview_labels.items():
            executor.submit(capture_and_update, name, label)
    

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
                    print(f"⚠️ get_full_path 錯誤: {e}")
                    path = ""

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
           
            # ✅ 拍照（只針對手動開始）
            block = next((blk for blk in self.view.blocks if blk.block_id == block_id), None)
            if block:
                take_snapshot_from_block(block, self.encoder_names)
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
        
        print(f"🔁 [同步] Runner block 數量：{len(self.runner.blocks)}")

        