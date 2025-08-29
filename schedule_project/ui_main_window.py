from header_view import HeaderView  

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QPushButton, QLabel, QDateEdit, QSlider,QDialog,QFrame,QScrollArea,QSplitter,QTextEdit,
    QVBoxLayout, QHBoxLayout, QLineEdit, QApplication, QSizePolicy, QMessageBox, QMenu, QFileDialog,
     QToolBar, QToolButton, QWidgetAction,

)
from time_block import TimeBlock
from shiboken6 import isValid
from time_block import PreviewImageItem
from PySide6.QtGui import QPixmap,QBrush ,QColor  ,QAction ,QUndoStack, QUndoCommand, QKeySequence
from PySide6.QtCore import QDate, Qt,QDateTime,QTime,QTimer,Qt,QSize
from schedule_view import ScheduleView
from encoder_utils import list_encoders_with_alias
from capture import take_snapshot_by_encoder
from datetime import datetime
import os
import glob
from schedule_runner import ScheduleRunner
import json
from block_manager import BlockManager
from encoder_controller import EncoderController
from add_block_dialog import AddBlockDialog
from path_manager import PathManager
# from utils_conflict import find_conflict_blocks
from capture import take_snapshot_from_block
from check_schedule_manager import CheckScheduleManager
CONFIG_FILE = "config.json"
from uuid import uuid4
from utils import set_log_box ,log
from capture import start_cleanup_timer, stop_cleanup_timer
from snapshot_worker import SnapshotWorker
from EncoderManagerDialog import EncoderManagerDialog
from encoder_utils import save_encoder_config, reload_encoder_config
from encoder_status_manager import EncoderStatusManager
from schedule_view import _TrackLabelWorker
from utils import hours_to_hhmm, hhmm_to_hours
from edit_block_dialog import EditBlockDialog

def _tag_toolbar_buttons_as_primary(tb):
    from PySide6.QtWidgets import QToolButton
    for act in tb.actions():
        w = tb.widgetForAction(act)
        if not isinstance(w, QToolButton):
            continue
        # 排除系統溢出按鈕（通常拿不到，但這行當雙保險）
        if w.objectName() == "qt_toolbar_ext_button":
            continue
        # 打上屬性標籤，讓上面的 QSS 命中
        w.setProperty("kind", "primary")
        # 讓 QSS 立即生效
        w.style().unpolish(w)
        w.style().polish(w)
        w.update()
def find_latest_snapshot_by_prefix(preview_dir, encoder_name):
    pattern = os.path.join(preview_dir,"preview", f"{encoder_name}*.png") 
    log(f"🔍 查找最新快照：{pattern}")
    matched_files = glob.glob(pattern)
    if not matched_files:
        return None
    return max(matched_files, key=os.path.getmtime)
class MainWindow(QMainWindow):
    def __init__(self):
        log("🔧 MainWindow 建立中...")  # ✅ 放在最上面
        super().__init__()
        self.is_closing = False
        # === 基礎設定 ===
        self.path_manager = PathManager()
        self.ensure_valid_paths()
        
         # ✅ 接下來才能安全使用 record_root 與 preview_root
        encoders = list_encoders_with_alias()
        self.encoder_names = [name for name, _ in encoders]
        self.encoder_aliases = {name: alias for name, alias in encoders}
        self.encoder_controller = EncoderController(self.record_root)
        
        if not self.encoder_names:
            log("⚠️ 沒有從 socket 抓到 encoder，使用預設值")
            self.encoder_names = ["encoder1", "encoder2"]
            self.encoder_aliases = {n: n for n in self.encoder_names}
        log(f"✅ Encoder 列表：{self.encoder_names}")

        self.setWindowTitle("錄影時間表")
        self.setGeometry(100, 100, 1600, 900)
        
        main_widget = QWidget(self)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        self.setCentralWidget(main_widget)

        splitter = QSplitter(Qt.Horizontal)  # 先建，稍後加到 main_layout
        
        # # === UI 主體 ===
        # main_widget = QWidget(self)
        # main_layout = QHBoxLayout(main_widget)
        # self.setCentralWidget(main_widget)
        # splitter = QSplitter(Qt.Horizontal)
        # main_layout.addWidget(splitter)

        # === 左側 Encoder Scroll 區塊 ===
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)            # 🔧 取消框線
        scroll_area.setStyleSheet("QScrollArea { border:0;}")
        encoder_scroll_content = QWidget()
        encoder_scroll_layout = QVBoxLayout(encoder_scroll_content)
        encoder_scroll_layout.setAlignment(Qt.AlignTop)
        encoder_scroll_layout.setContentsMargins(0, 100, 0, 0)  # 整體往下推
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
        self.encoder_status_manager = EncoderStatusManager()
        
        os.makedirs(self.preview_root, exist_ok=True)
        self.start_buttons = {}
        self.stop_buttons = {}
        for name in self.encoder_names:
            widget = self.build_encoder_widget(name)
            encoder_layout.addWidget(widget)
        # for name in self.encoder_names:
        #     display = self.encoder_aliases.get(name, name)
        #     encoder_widget = QWidget()
        #     encoder_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        #     encoder_box = QVBoxLayout(encoder_widget)
        #     encoder_box.setContentsMargins(0, 100, 0, 0)
            
        #     preview_label = QLabel(f"🖼️ {display} 預覽載入中...")
        #     preview_label.setScaledContents(False)                      # 我們自己控制縮放
        #     preview_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)  # 不讓 pixmap 影響 sizeHint
        #     preview_label.setAlignment(Qt.AlignCenter)

        #     preview_label.setMinimumHeight(180)
        #     preview_label.setMinimumWidth(0)
        #     preview_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        #     preview_label.setStyleSheet("border: 1px solid gray; background-color: black; color: white;")
        #     preview_label.setAlignment(Qt.AlignCenter)
        #     self.encoder_preview_labels[name] = preview_label
        #     encoder_box.addWidget(preview_label)
            
        #     line = QHBoxLayout()
        #     label = QLabel(display)
        #     entry = QLineEdit()
        #     entry.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        #     entry.setMaximumWidth(80)
        #     start_btn = QPushButton("▶️")
        #     stop_btn = QPushButton("⏹")
        #     # path_btn = QPushButton("📁")
        #     status = QLabel("+++")
        #     status.setAlignment(Qt.AlignVCenter)
            # line.addWidget(label)
            # line.addWidget(entry)
            # line.addWidget(start_btn)
            # line.addWidget(stop_btn)
            # # line.addWidget(path_btn)
            # line.addWidget(status)
            # line.setStretch(0, 1)
            # line.setStretch(1, 5)
            # line.setStretch(2, 1)
            # line.setStretch(3, 1)
            # line.setStretch(4, 1)
            # line.setStretch(5, 2)
        #     encoder_box.addLayout(line)
        #     encoder_layout.addWidget(encoder_widget)

        #     start_btn.clicked.connect(lambda _, n=name, e=entry, s=status: self.encoder_start(n, e, s))
        #     stop_btn.clicked.connect(lambda _, n=name, s=status: self.encoder_stop(n, s))
        #     # path_btn.clicked.connect(lambda _, n=name, e=entry: self.show_file_path(n, e))
        #     self.encoder_entries[name] = entry
        #     self.encoder_status[name] = status
        #     self.start_buttons[name]   = start_btn     # ← 新增
        #     self.stop_buttons[name]    = stop_btn      # ← 新增

        # encoder_scroll_layout.addWidget(encoder_panel)
        encoder_scroll_layout.addWidget(self.encoder_panel)

        # === 右側 排程 Panel ===
        right_panel = QWidget()
        right_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setAlignment(Qt.AlignTop)

        # === 工具列 ===
        toolbar = QToolBar("主工具列", self)
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setIconSize(QSize(16,16))       # 你也可以調 18、20
        toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        # 讓整排在窄時自動出現 ">>" 溢出按鈕
        toolbar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        toolbar.setFixedHeight(40)
        
        # 左側 Zoom 群組（做成一個小 QWidget 打包，放進 QWidgetAction）
        zoom_group = QWidget()
        zlay = QHBoxLayout(zoom_group)
        zlay.setContentsMargins(6, 4, 6, 4)
        zlay.setSpacing(6)
        # 管理 Encoder（QAction）
        self.manage_encoder_button = QAction("⚙️ 管理 Encoder", self)
        self.manage_encoder_button.setObjectName("manageEncoderBtn")  # 指定名稱方便 QSS 定位
        self.manage_encoder_button.triggered.connect(self.open_encoder_manager)
        toolbar.addAction(self.manage_encoder_button)
 
# 取得對應的 QToolButton，設定 objectName
        btn = toolbar.widgetForAction(self.manage_encoder_button)
        if btn is not None:
            btn.setObjectName("manageEncoderBtn")

        # 再設定樣式（可放在建好 toolbar 的最後）
        toolbar.setStyleSheet("""
    QToolBar QToolButton[kind="primary"] {
        padding: 2px 8px;
        margin-right: 4px;       /* 按鈕間距 */
        border: 1px solid #aaa;
        border-radius: 4px;
        background: #f2f2f2;     /* 灰色背景 */
        font-weight: 500;
    }
    QToolBar QToolButton[kind="primary"]:hover {
        background: #e0e0e0;
    }
    QToolBar QToolButton[kind="primary"]:pressed {
        background: #d6d6d6;
    }
        """)
        zoom_label = QLabel("Zoom：")
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(10, 200)
        self.zoom_slider.setValue((10 + 200) // 2)
        self.zoom_slider.valueChanged.connect(self.update_zoom)
        self.zoom_slider.setFixedWidth(220)
        self.zoom_slider.setFixedHeight(20)

        zlay.addWidget(zoom_label)
        zlay.addWidget(self.zoom_slider)

        zoom_act = QWidgetAction(self)
        zoom_act.setDefaultWidget(zoom_group)
        toolbar.addAction(zoom_act)

        # 加一個彈性空白，把右邊推到右側
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        spacer_act = QWidgetAction(self)
        spacer_act.setDefaultWidget(spacer)
        toolbar.addAction(spacer_act)

        # 右側一串按鈕：用 QAction（或需要複雜內容時用 QWidgetAction）
        def _mk_action(text, handler):
            act = QAction(text, self)
            act.triggered.connect(handler)
            return act



        # 起始日期（需要小控件 → QWidgetAction）
        date_wrap = QWidget()
        dl = QHBoxLayout(date_wrap); dl.setContentsMargins(0,0,0,0); dl.setSpacing(6)
        self.date_label = QLabel("起始日期：")
        self.date_picker = QDateEdit(QDate.currentDate())
        self.date_picker.setCalendarPopup(True)
        self.date_picker.setFixedWidth(130)
        self.date_picker.dateChanged.connect(self.update_start_date)
        dl.addWidget(self.date_label); dl.addWidget(self.date_picker)
        date_act = QWidgetAction(self); date_act.setDefaultWidget(date_wrap)
        toolbar.addAction(date_act)
        # 加一個小空白
        gap = QWidget()
        gap.setFixedWidth(10)   # 你要幾 px 就設幾 px
        gap_act = QWidgetAction(self)
        gap_act.setDefaultWidget(gap)
        toolbar.addAction(gap_act)

        # 其他按鈕（純 QAction）
        toolbar.addAction(_mk_action("📅 今天", self.jump_to_today))
        toolbar.addAction(_mk_action("➕ 新增排程", self.add_new_block))
       
        toolbar.addAction(_mk_action("⬅️ 前一週", lambda: self.shift_date(-7)))
        toolbar.addAction(_mk_action("➡️ 下一週", lambda: self.shift_date(+7)))
        
        toolbar.addAction(_mk_action("💾 儲存", lambda: self.view.save_schedule()))
        toolbar.addAction(_mk_action("📂 載入", lambda: (self.view.load_schedule(), self.sync_runner_data())))
        toolbar.addAction(_mk_action("📁 設定影片儲存路徑", self.select_record_root))
        toolbar.addAction(_mk_action("📁 設定預覽儲存路徑", self.select_preview_root))
        toolbar.addAction(_mk_action("📄 選擇排程檔", self.select_schedule_json))
        undo_act = QAction("↩️ 復原刪除", self)
        undo_act.triggered.connect(lambda: (self.block_manager.undo_last_delete(), self.sync_runner_data()))
        toolbar.addAction(undo_act)
        _tag_toolbar_buttons_as_primary(toolbar)
        # 把 QToolBar 放進你的 right_layout（取代原本的 toolbar widget）
        # right_layout.addWidget(toolbar)
        # main_layout.addWidget(toolbar)



        # # --- Log box ---
        # self.log_box = QTextEdit()
        # self.log_box.setReadOnly(True)
        # self.log_box.setLineWrapMode(QTextEdit.NoWrap)
        # self.log_box.setFixedHeight(150)
        # self.log_box.setStyleSheet("""
        #     QTextEdit {
        #         background-color: #111;
        #         color: #00FF00;
        #         font-family: Consolas, Courier, monospace;
        #         font-size: 12px;
        #         border: 1px solid #333;
        #     }
        # """)

        # set_log_box(self.log_box)

        # --- Header & ScheduleView ---
        self.header = HeaderView(self.encoder_names)
        self.view = ScheduleView()
        self.view.encoder_status_manager = self.encoder_status_manager  # ✅ 傳入狀態管理器

        self.view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.view.encoder_names = self.encoder_names
        self.view.encoder_status = self.encoder_status
        self.view.record_root = self.record_root
        self.view.load_schedule()
        # self.view.draw_grid()
        # self.track_status_timer = QTimer()
        # self.track_status_timer.timeout.connect(self.view.refresh_track_labels)
        # self.track_status_timer.start(10000)
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
        preview_dir = os.path.join(self.path_manager.snapshot_root, "preview")
        start_cleanup_timer(preview_dir, check_period=300, max_age=300, run_immediately=False)
        self.block_manager = BlockManager(self.view)
        self.runner = ScheduleRunner(
            schedule_data=self.view.block_data,
            encoder_status=self.encoder_status,
            record_root=self.record_root,
            encoder_names=self.encoder_names,
            blocks=self.view.blocks
        )# ✅ 加這裡！建立 schedule_manager
                # ✅ 建立完 runner 後，再把控制權交給 runner（移到這裡）
        self.runner.start_buttons   = self.start_buttons
        self.runner.stop_buttons    = self.stop_buttons
        self.runner.filename_inputs = self.encoder_entries
        self.schedule_manager = CheckScheduleManager(
            encoder_names=self.encoder_names,
            encoder_status_dict=self.encoder_status,
            runner=self.runner,
            parent_view_getter=lambda: self.view
        )
        self.mismatch_timer = QTimer(self)
        self.mismatch_timer.timeout.connect(self.schedule_manager.reconcile_async)
        self.mismatch_timer.start(10_000)
        self.schedule_manager.schedule_data = self.view.block_data
        self.schedule_manager.blocks = self.view.blocks
        # self.check_timer = QTimer(self)
        # self.check_timer.timeout.connect(self.safe_check_schedule)
        # self.check_timer.start(1000)
        self.schedule_manager._reconcile_cooldown_until = QDateTime.currentDateTime().addSecs(15)
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
        main_layout.addWidget(toolbar)
        # right_layout.addWidget(toolbar)
        right_layout.addWidget(header_schedule_wrapper)
        # right_layout.addWidget(self.log_box)
        # === 加入 splitter ===
        main_layout.addWidget(splitter)
        splitter.addWidget(scroll_area)
        splitter.addWidget(right_panel)
        
        # 讓右側吃伸展；左側不主動搶寬
        splitter.setStretchFactor(0, 0)   # 左：scroll_area
        splitter.setStretchFactor(1, 1)   # 右：right_panel

        # 給個合理初始寬度分配（可調）
        splitter.setSizes([260, 1200])

        # 確保右側可被壓到很窄，不會卡住 splitter
        right_panel.setMinimumWidth(1)
        self.header.setMinimumWidth(1)
        self.view.setMinimumWidth(1)

        # 左側別主動搶寬（但保留你 preview_label 的 Preferred）
        scroll_area.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Expanding)
        scroll_area.setMinimumWidth(1)
    
        
        self.snapshot_timer = QTimer(self)
        self.snapshot_timer.timeout.connect(self.update_all_encoder_snapshots)
        self.snapshot_timer.start(30000)

      

        self.sync_runner_data()
        self.view.horizontalScrollBar().valueChanged.connect(self.header.sync_scroll)
        # self.update_encoder_status_labels()
        # QTimer.singleShot(2000, self.update_encoder_status_labels)
        self.view.draw_grid()
        self.check_timer = QTimer(self)
        self.check_timer.timeout.connect(self.safe_check_schedule)
        self.check_timer.start(1000)
        self.copied_block_template = None
        self.track_height = TimeBlock.BLOCK_HEIGHT
        QTimer.singleShot(3000, self.update_all_encoder_snapshots)
  
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
        
    def update_zoom(self, value):
        self.view.hour_width = value
        self.view.day_width = 24 * value
        self.header.hour_width = value
        self.header.day_width = 24 * value

        self.view.draw_grid()
        self.header.draw_header()

        # 重新定位所有 block
        for block in self.view.blocks:
            block.update_geometry(self.view.base_date)
            block.update_text_position()
        self.view.center_on_now()
    def ensure_valid_paths(self):
        self.record_root = self.path_manager.record_root
        self.preview_root = self.path_manager.preview_root

        invalid_record = not os.path.isdir(self.record_root)
        invalid_preview = not os.path.isdir(self.preview_root)

        if not invalid_record and not invalid_preview:
            return

        msg = "⚠️ 以下路徑無效，請重新設定：\n"
        if invalid_record:
            msg += f"\n📁 錄影儲存路徑：{self.record_root}"
        if invalid_preview:
            msg += f"\n🖼️ 預覽儲存路徑：{self.preview_root}"
        msg += "\n\n請按「確定」後依序設定"

        QMessageBox.critical(self, "❌ 路徑錯誤", msg)

        if invalid_record:
            self.select_record_root()
        if invalid_preview:
            self.select_preview_root()

    # def ensure_valid_record_root(self):
    #     self.record_root = self.path_manager.record_root
    #     if not os.path.isdir(self.record_root):
    #         log(f"❌ 無效的錄影儲存路徑：{self.record_root}")
    #         QMessageBox.critical(
    #             self,
    #             "❌ 錄影儲存路徑無效",
    #             f"⚠️ 找不到錄影儲存路徑：\n{self.record_root}\n\n請重新選擇一個有效的資料夾。"
    #         )
    #         self.select_record_root()  # 嘗試讓使用者重新選擇
    #         self.path_manager = PathManager()
    #         self.record_root = self.path_manager.record_root  # 更新路徑
    #     os.makedirs(self.record_root, exist_ok=True)


    # def ensure_valid_preview_root(self):
    #     self.preview_root = self.path_manager.preview_root
    #     if not os.path.isdir(self.preview_root):
    #         log(f"❌ 無效的預覽儲存路徑：{self.preview_root}")
    #         QMessageBox.critical(
    #             self,
    #             "❌ 預覽儲存路徑無效",
    #             f"⚠️ 找不到預覽儲存路徑：\n{self.preview_root}\n\n請重新選擇一個有效的資料夾。"
    #         )
    #         self.select_preview_root()
    #         self.path_manager = PathManager()
    #         self.preview_root = self.path_manager.preview_root
    #     # os.makedirs(self.preview_root, exist_ok=True)

    def open_encoder_manager(self):
        reload_encoder_config()
        dialog = EncoderManagerDialog(self)
        if dialog.exec():  # 如果點了儲存
            new_config = dialog.get_result()
            save_encoder_config(new_config)
            reload_encoder_config()
            self.reload_encoder_list()
            
    def reload_encoder_list(self):
            log("🔄 重新載入 Encoder 列表")

        # 1) 讀新清單
            encoders = list_encoders_with_alias()
            self.encoder_names   = [name for name, _ in encoders]
            self.encoder_aliases = {name: alias for name, alias in encoders}

            # 2) 清空所有映射（含 start/stop）
            self.encoder_status.clear()
            self.encoder_entries = {}
            self.encoder_preview_labels = {}
            self.start_buttons = {}
            self.stop_buttons  = {}

            # 3) 更新 runner/schedule_manager 的名稱
            self.runner.encoder_names = self.encoder_names
            self.schedule_manager.encoder_names = self.encoder_names

            # 4) 清空左側 encoder_panel，改用「一開始那套」現場組 UI
            encoder_panel = self.findChild(QWidget, "encoder_panel")
            if encoder_panel:
                layout = encoder_panel.layout()
                if layout:
                    while layout.count():
                        item = layout.takeAt(0)
                        w = item.widget()
                        if w:
                            w.setParent(None)

                    for name in self.encoder_names:
                        widget = self.build_encoder_widget(name)
                        layout.addWidget(widget)

            # 5) 把最新的 mapping 回填給 runner（🔑 讓開始鍵能自動變灰）
            self.runner.encoder_status   = self.encoder_status
            self.runner.start_buttons    = self.start_buttons
            self.runner.stop_buttons     = self.stop_buttons
            self.runner.filename_inputs  = self.encoder_entries

            # 6) 右側視圖同步 & 重畫
            self.view.encoder_names  = self.encoder_names
            self.view.encoder_status = self.encoder_status
            self.header.set_encoder_names(self.encoder_names)

            self.view.restore_orphan_blocks()
            self.view.remap_block_tracks()
            self.view.rebuild_tracks()
            # self.view.draw_grid()

            orphan_count = len(self.view.orphan_blocks)
            if orphan_count:
                log(f"⚠️ {orphan_count} 個節目沒有對應的 encoder")

            # 7) 立即刷新一次狀態（讓開始鍵立刻依狀態變灰）
            self.sync_runner_data()
            QTimer.singleShot(0, self.update_encoder_status_labels)
            QTimer.singleShot(0, getattr(self.runner, "_refresh_status_async"))

    def jump_to_today(self):
        today = QDate.currentDate()
        self.view.set_start_date(today)
        self.header.set_base_date(today)
        self.date_picker.setDate(today)
        self.view.center_on_now()  
    def safe_check_schedule(self):
        log("🕒 檢查排程中...")
        try:
            # 改成非同步：丟給 worker，避免卡住
            self.schedule_manager.tick_async()
        except Exception as e:
            log(f"❌ [Timer] check_schedule 錯誤：{e}",level="ERROR")
        
    def build_encoder_widget(self, name):
        display = self.encoder_aliases.get(name, name)
        encoder_widget = QWidget()
        encoder_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        encoder_box = QVBoxLayout(encoder_widget)
        encoder_box.setContentsMargins(0, 0, 0, 0) 
        encoder_box.setSpacing(2) 
        # encoder_box.setContentsMargins(0, 100, 0, 0)

        # 🖼️ 預覽圖
        preview_label = QLabel(f"🖼️ {display} 預覽載入中...")
        preview_label.setMinimumHeight(160)
        preview_label.setStyleSheet("border: 1px solid gray; background-color: black; color: white;")
        preview_label.setAlignment(Qt.AlignCenter)
        self.encoder_preview_labels[name] = preview_label
        encoder_box.addWidget(preview_label)

        # 📏 控制列（整排）
        control_row = QHBoxLayout()
        control_row.setContentsMargins(0, 0, 0, 0)  
        control_row.setSpacing(2)
        label = QLabel(display)
        label.setFixedWidth(60)
        label.setMinimumHeight(32)
        label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        
        entry = QLineEdit()
        entry.setFixedHeight(32)
        entry.setMaximumWidth(100)
        

        start_btn = QPushButton("▶️")
        stop_btn = QPushButton("⏹")
        # path_btn = QPushButton("📁")
        status = QLabel("狀態：")
        for btn in [start_btn, stop_btn]:
        # for btn in [start_btn, stop_btn, path_btn]:
            btn.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)
            btn.setMinimumWidth(40)
            btn.setMaximumWidth(80)
            btn.setFixedHeight(28)
        
        status.setFixedWidth(100)
        status.setAlignment(Qt.AlignVCenter)

        control_row.addWidget(label)
        control_row.addWidget(entry)
        control_row.addWidget(start_btn)
        control_row.addWidget(stop_btn)
        # control_row.addWidget(path_btn)
        control_row.addWidget(status)

        encoder_box.addLayout(control_row)

        # 📎 綁定與註冊
        start_btn.clicked.connect(lambda _, n=name, e=entry, s=status: self.encoder_start(n, e, s))
        stop_btn.clicked.connect(lambda _, n=name, s=status: self.encoder_stop(n, s))
        # path_btn.clicked.connect(lambda _, n=name, e=entry: self.show_file_path(n, e))

        self.encoder_entries[name] = entry
        self.encoder_status[name] = status
        self.start_buttons[name]   = start_btn   # ← 新增
        self.stop_buttons[name]    = stop_btn  
        status.setText(f"狀態：{self.get_encoder_status(name)}")
        return encoder_widget
    # def update_preview_scaled(self, name):
    #     label = self.encoder_preview_labels.get(name)
    #     pixmap = self.encoder_pixmaps.get(name)
    #     if label and pixmap:
    #         scaled = pixmap.scaled(label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
    #         label.setPixmap(scaled)
   

    def update_preview_scaled(self, name: str):
        label = self.encoder_preview_labels.get(name)
        pm = self.encoder_pixmaps.get(name)
        if not label or not pm or pm.isNull():
            return

        # 只用可用內容區域，不用 label.size() / sizeHint()
        target_size = label.contentsRect().size()
        if not target_size.isValid() or target_size.isEmpty():
            return

        # 只有在目標大小跟現有顯示不一樣時才重算，避免頻繁 setPixmap 觸發重排
        cur = label.pixmap()
        if cur and cur.size() == target_size:
            return

        scaled = pm.scaled(target_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        label.setPixmap(scaled)

    def resizeEvent(self, event):
        for name in self.encoder_names:
            self.update_preview_scaled(name)
        super().resizeEvent(event)
    def get_encoder_status(self, name):
        result = self.encoder_status_manager.get_status(name)
        log(f"🧪 get_status({name}) 回傳：{result}")
        
        if result:
            status_text, _ = result
            return status_text
        else:
            # ❗❗❗ Fallback：如果解析失敗（None），保留舊狀態以避免 UI 閃跳
            last = self.runner.encoder_last_state.get(name, "")
            if "Running" in last or "Runned" in last:
                return "✅ 錄影中"
            elif "Paused" in last:
                return "⏸ 暫停中"
            elif "Stopped" in last or "None" in last:
                return "⏹ 停止中"
            elif "Prepared" in last or "Preparing" in last:
                return "🟡 準備中"
            elif "Error" in last or "disconnect" in last:
                return "❌ 錯誤"
            elif not last:
                return "❌ 未連線"
            else:
                # 可選：log unknown 狀態但不顯示到 UI
                log(f"⚠️ 無法解析狀態 fallback: {last}")
                return ""



    def update_encoder_status_labels(self):
        try:
            for name, status_label in self.encoder_status.items():
                # 用同一份狀態來源 ➜ 兩邊一致
                result = self.encoder_status_manager.get_status(name)
                # get_status 回傳 (status_text, color)
                if not result:
                    continue
                status_text, color = result

                # 左側控制面板（既有）
                status_label.setText(f"狀態：{status_text}")
                status_label.setStyleSheet(f"color: {color}")

                # 右側時間表左邊的標題（新）
                self.view.set_track_label_status(name, status_text, color)
        except Exception as e:
            log(f"❌ [Timer] update_encoder_status_labels 發生錯誤：{e}",level="ERROR")
            
            
    def update_all_encoder_snapshots(self):
        if getattr(self, "is_closing", False):
            log("🛑 UI 正在關閉，取消 snapshot 拍攝")
            if hasattr(self, "snapshot_futures"):
                for fut in self.snapshot_futures.values():
                    if hasattr(fut, "cancel_event"):
                        fut.cancel_event.set()
            return

        def on_finished(name, old_label):
            def load_image():
                try:
                    # ⛑️ 重新取得目前還活著的 label，避免閉包抓舊物件
                    cur_label = self.encoder_preview_labels.get(name)
                    if not cur_label or not isValid(cur_label):
                        # 舊 label 已失效 / 已被替換：拔掉殘留 mapping（可選）
                        self.encoder_preview_labels.pop(name, None)
                        return

                    latest_path = find_latest_snapshot_by_prefix(self.preview_root, name)
                    if latest_path and os.path.exists(latest_path):
                        pm = QPixmap(latest_path)
                        if pm.isNull():
                            log(f"⚠️ {name} 載入圖片為空，略過更新")
                            return
                        self.encoder_pixmaps[name] = pm
                        # ⛑️ 再次確認 label 還在
                        if isValid(cur_label):
                            self.update_preview_scaled(name)
                    else:
                        # ⛑️ 只在 label 還活著時才 setText
                        if isValid(cur_label):
                            cur_label.setText(f"❌ 無法載入 {name} 圖片")
                except Exception as e:
                    log(f"❌ [Timer] 快照更新錯誤（{name}）：{e}",level="ERROR")

            QTimer.singleShot(300, load_image)

        if not hasattr(self, "snapshot_workers"):
            self.snapshot_workers = []
        try:
            for name, label in self.encoder_preview_labels.items():
                worker = SnapshotWorker(name, self.preview_root)
                worker.finished.connect(lambda n, l=label: on_finished(n, l))

                # ✅ 用獨立函式安全清理
                def _cleanup(_, w=worker):
                    try:
                        if w in self.snapshot_workers:
                            self.snapshot_workers.remove(w)
                    except Exception:
                        pass
                worker.finished.connect(_cleanup)

                worker.finished.connect(worker.deleteLater)
                self.snapshot_workers.append(worker)
                worker.start()
        except Exception as e:
            log(f"❌ [Timer] update_all_encoder_snapshots 整體錯誤：{e}",level="ERROR")

    
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
            self.path_manager.record_root = folder
            self.path_manager.save_record_root(folder)

            # ✅ 更新給 runner、view、path_manager（若存在）
            if hasattr(self, "runner"):
                self.runner.record_root = folder
            if hasattr(self, "view"):
                self.view.record_root = folder
                if hasattr(self.view, "path_manager"):
                    self.view.path_manager.record_root = folder
            log(f"📁 使用者設定儲存路徑為：{folder}")

    def select_preview_root(self):
        folder = QFileDialog.getExistingDirectory(self, "選擇預覽儲存路徑", self.preview_root)
        if folder:
            self.preview_root = folder
            os.makedirs(self.preview_root, exist_ok=True)
            self.path_manager.preview_root = folder
            self.path_manager.save_preview_root(folder)

            # ✅ 更新 path_manager 給 view（若存在）
            if hasattr(self, "view") and hasattr(self.view, "path_manager"):
                self.view.path_manager.preview_root = folder

            log(f"📁 設定預覽資料夾：{folder}")


    
    def add_new_block(self):
        def check_overlap(qdate, track_index, start_hour, duration):
            return self.view.is_overlap(qdate, track_index, start_hour, duration, exclude_label=None)

        dialog = AddBlockDialog(self, 
                encoder_names=self.encoder_names, 
                overlap_checker=check_overlap)
        if dialog.exec() == QDialog.Accepted:
            vals = dialog.get_values()

            # 相容：5 值（舊版）或 6 值（新版，多回傳 end_qtime）
            if len(vals) == 6:
                name, qdate, time_obj, duration, encoder_name, end_qtime = vals
            else:
                name, qdate, time_obj, duration, encoder_name = vals
                end_qtime = None

            track_index = self.encoder_names.index(encoder_name)

            # start_hour 以 HH:mm 轉 float 小時
            start_hour = hhmm_to_hours(time_obj.toString("HH:mm"))

            # duration 可能已是 float；若是字串（理論上新版不是），也支援
            duration_hours = hhmm_to_hours(duration) if isinstance(duration, str) else float(duration)

            self.block_manager.add_block_with_unique_label(
                name,
                track_index=track_index,
                start_hour=start_hour,
                duration=duration_hours,
                encoder_name=encoder_name,
                qdate=qdate
            )

            # 如果你之後要儲存 end_hour，可在這裡計算（選擇性）
            # if end_qtime is not None:
            #     end_hour = hhmm_to_hours(end_qtime.toString("HH:mm"))
            #     # TODO: 視你的資料結構決定如何保存 end_hour

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
# 放在 MainWindow 類別裡（例如 show_block_context_menu 的上方或下方都可）
    def _edit_block_via_dialog(self, item):
        # item 是 time_block.TimeBlock 的實例
        from PySide6.QtCore import QDateTime, QTime
        from utils import hours_to_hhmm, hhmm_to_hours

        parent_view = self.view
        now = QDateTime.currentDateTime()
        start_dt = QDateTime(item.start_date, QTime(int(item.start_hour), int((item.start_hour % 1) * 60)))
        # end_dt = start_dt.addSecs(int(item.duration_hours * 3600))
        end_dt = start_dt.addSecs(int(round(item.duration_hours * 60)) * 60)
        # 已結束就不讓編輯（跟 TimeBlock.double click 一樣）
        if now > end_dt:
            log("⛔ 已結束排程不可編輯")
            return

        # 目前這個 block 的初始值
        block_dict = {
            "qdate": item.start_date,
            "label": item.label,
            "start_time": hours_to_hhmm(item.start_hour),
            "duration_time": hours_to_hhmm(item.duration_hours),
            "encoder_name": parent_view.encoder_names[item.track_index] if 0 <= item.track_index < len(parent_view.encoder_names) else None,
            "id": item.block_id,
        }

        # 是否唯讀（已開始的情況）
        readonly = start_dt <= now

        # 排除自己做重疊檢查
        def overlap_checker(qdate, track_index, start_hour, duration):
            return parent_view.is_overlap(qdate, track_index, start_hour, duration, exclude_label=item.block_id)

        dlg = EditBlockDialog(block_dict, parent_view.encoder_names, readonly=readonly, overlap_checker=overlap_checker)
        if not dlg.exec():
            return

        updated = dlg.get_updated_data()

        # 轉換時間
        qdate_q = updated["qdate"]
        new_start_hour = hhmm_to_hours(updated["start_time"])
        new_duration   = hhmm_to_hours(updated["duration_time"])

        # 回寫到 TimeBlock 本體
        item.start_date = qdate_q
        item.label = updated["label"]
        item.start_hour = new_start_hour
        item.duration_hours = new_duration
        if updated.get("encoder_name") in parent_view.encoder_names:
            item.track_index = parent_view.encoder_names.index(updated["encoder_name"])

        # 更新幾何 & 顯示
        item.update_geometry(parent_view.base_date)
        item.update_text_position()

        # 計算跨日的 end_hour / end_qdate
        end_hour, end_qdate = item.compute_end_dt()

        # 回寫到 block_data
        for b in parent_view.block_data:
            if b.get("id") == item.block_id:
                b.update({
                    "qdate": item.start_date,
                    "start_hour": item.start_hour,
                    "duration": item.duration_hours,
                    "end_hour": end_hour,
                    "end_qdate": end_qdate,
                    "label": item.label,
                    "encoder_name": updated["encoder_name"],
                    "start_time": hours_to_hhmm(item.start_hour),
                    "duration_time": hours_to_hhmm(item.duration_hours),
                    "track_index": item.track_index,
                    "id": item.block_id,
                })
                break

        # 存檔 + 同步 runner
        parent_view.save_schedule()
        self.sync_runner_data()
    def show_block_context_menu(self, pos):
        from time_block import PreviewImageItem  # 避免頂端循環匯入
        from PySide6.QtCore import QDateTime, QTime

        scene_pos = self.view.mapToScene(pos)

        # 先找滑鼠下是否命中某個 block（跳過預覽圖片）
        hit_item = None
        for item in self.view.scene.items():
            if isinstance(item, PreviewImageItem):
                continue
            if hasattr(item, "label") and item.contains(item.mapFromScene(scene_pos)):
                hit_item = item
                break

        # ========== 命中 block：顯示原本的右鍵選單 ==========
        if hit_item:
            # 右鍵彈出前，僅就地刷新這一個 block 的時間狀態（不重畫整個畫面）
            try:
                if hasattr(hit_item, "update_status_by_time"):
                    changed = hit_item.update_status_by_time()
                    if changed and hasattr(self.view, "save_schedule"):
                        self.view.save_schedule()
            except Exception:
                pass

            # 即時計算現在是否已開始/已結束（不要只靠 has_ended / 文字）
            now = QDateTime.currentDateTime()
            start_dt = QDateTime(
                hit_item.start_date,
                QTime(int(hit_item.start_hour) % 24, int((hit_item.start_hour % 1) * 60)),
            )
            try:
                end_dt = hit_item.compute_end_dt()
            except Exception:
                end_dt = start_dt.addSecs(int(hit_item.duration_hours * 3600))

            already_started = now >= start_dt
            already_ended = now > end_dt

            menu = QMenu(self)
            label = hit_item.label

            # 嘗試取得檔案路徑（防呆）
            try:
                path = self.path_manager.get_full_path("", label)
            except Exception as e:
                log(f"⚠️ get_full_path 錯誤: {e}", level="ERROR")
                path = ""

            menu.addAction(f"查看檔案名稱：{label}")
            open_action = menu.addAction("📂 開啟資料夾")
            copy_action = menu.addAction("📋 複製排程")
            delete_action = menu.addAction("🗑️ 刪除排程")
            edit_action = menu.addAction("✏️ 編輯排程…")

            # 已開始或已完成的排程不可刪
            if already_started or already_ended:
                delete_action.setEnabled(False)
                delete_action.setText("🗑️ 已開始或完成，不可刪")
                        # ✅ 已結束：編輯選項灰掉，避免誤會
            if already_ended:
                edit_action.setEnabled(False)
                edit_action.setText("✏️ 已結束（不可編輯）")
            selected = menu.exec(self.view.mapToGlobal(pos))

            if selected == open_action:
                folder_path = os.path.dirname(path)
                if os.path.exists(folder_path):
                    try:
                        os.startfile(folder_path)  # Windows
                    except Exception:
                        import subprocess, sys
                        if sys.platform.startswith("darwin"):
                            subprocess.call(["open", folder_path])
                        else:
                            subprocess.call(["xdg-open", folder_path])
                else:
                    QMessageBox.information(self, "📁 找不到資料夾", f"{folder_path} 不存在")

            elif selected == copy_action:
                # 從 block_data 找到此 block 的完整資料當範本
                src = next(
                    (b for b in self.view.block_data if b.get("id") == getattr(hit_item, "block_id", None)),
                    None,
                )
                if src is None:
                    log("⚠️ 找不到來源 block，無法複製")
                    return

                # 只保留貼上會用到的欄位
                self.copied_block_template = {
                    "label": src.get("label", ""),
                    "duration": float(src.get("duration", src.get("duration_hours", 4.0))),
                }
                log(f"✅ 已複製行程：{self.copied_block_template['label']}（{self.copied_block_template['duration']}h）")

            elif selected == edit_action:
                self._edit_block_via_dialog(hit_item)

            elif selected == delete_action:
                now2 = QDateTime.currentDateTime()
                if now2 >= start_dt or now2 > end_dt:
                    QMessageBox.information(self, "無法刪除", "此排程已開始或已結束。")
                    return
                self.block_manager.remove_block_by_id(hit_item.block_id)

            return  # 已處理，直接收工

        # ========== 沒有命中任何 block：顯示「貼上」背景選單 ==========
        bg_menu = QMenu(self)
        paste_action = bg_menu.addAction("📋 貼上行程")
        if not self.copied_block_template:
            paste_action.setEnabled(False)
            paste_action.setText("📋（尚未複製）")

        selected = bg_menu.exec(self.view.mapToGlobal(pos))
        if selected == paste_action:
            self._paste_block_at_scene_pos(scene_pos)

    def _paste_block_at_scene_pos(self, scene_pos):
        # tpl = self.copied_block_template
        tpl = self.copied_block_template.copy()
        tpl.pop("status", None)      # 不複製舊狀態
        tpl.pop("live_status", None) # 也不要帶即時提示
        # 另外別忘了換新的 id
        tpl["id"] = str(uuid4())
        
        if not tpl:
            return

        # === 1) 由座標換算 slot（日期、時段、track） ===
        view = self.view
        hour_width = getattr(view, "hour_width", 20)
        day_width  = 24 * hour_width
        offset_y   = getattr(view, "grid_top_offset", 0)

        x = scene_pos.x()
        y = scene_pos.y()

        # 日期
        day_idx   = int(max(0, min(6, x // day_width)))  # 週視圖 0..6
        qdate     = view.base_date.addDays(day_idx)

        # 小時（對齊 5 分鐘 = 1/12 小時；你也可以改成 0.25 小時）
        hour_px   = x % day_width
        raw_hour  = hour_px / hour_width
        step      = 1/12  # 5 分鐘
        start_hour = round(round(raw_hour / step) * step, 4)

        # 軌道（encoder）
        track_index = int((y - offset_y) //self.track_height)
        # track_index = int((y - offset_y) // getattr(view, "BLOCK_HEIGHT", 100))
        if track_index < 0 or track_index >= len(self.encoder_names):
            log("⚠️ 貼上超出軌道範圍，取消")
            return

        duration = float(tpl.get("duration", 4.0))
        label    = tpl.get("label", "").strip() or "複製的行程"
        encoder_name = self.encoder_names[track_index]

        # === 2) 基本檢查：不可在過去、不可重疊 ===
        start_dt = QDateTime(qdate, QTime(int(start_hour), int((start_hour % 1) * 60)))
        if start_dt < QDateTime.currentDateTime():
            QMessageBox.warning(self, "❌ 無法貼上", "⚠️ 不能貼到過去的時間。")
            return

        if self.view.is_overlap(qdate, track_index, start_hour, duration, exclude_label=None):
            QMessageBox.warning(self, "❌ 無法貼上", "⚠️ 與既有行程重疊。")
            return

        # === 3) 建立新 block（自動處理重名） ===
        self.block_manager.add_block_with_unique_label(
            label,
            track_index=track_index,
            start_hour=start_hour,
            duration=duration,
            encoder_name=encoder_name,
            qdate=qdate
        )
        new_bd = next((
            b for b in self.view.block_data
            if b.get("label") == label
            and b.get("qdate") == qdate
            and b.get("track_index") == track_index
            and abs(float(b.get("start_hour", -999)) - start_hour) < 1e-6
        ), None)

        if new_bd is not None:
            new_bd["status"] = ""  # JSON 清空
            # 重畫並把活體物件也設回等待中
            self.view.draw_grid()
            self.view.draw_blocks()
            blk = next((x for x in self.view.blocks if getattr(x, "block_id", None) == new_bd.get("id")), None)
            if blk:
                blk.set_state("WAITING")
        self.sync_runner_data()
        log(f"📌 已貼上：{label} ➜ {qdate.toString('yyyy-MM-dd')} {start_hour:.2f}h @ {encoder_name}")
    def encoder_stop(self, encoder_name, status_label):
        QApplication.processEvents()

        ok = self.encoder_controller.stop_encoder(encoder_name)
        now = QDateTime.currentDateTime()
        encoder_index = self.encoder_names.index(encoder_name)

        if ok:
            stopped_block_id = None

            for block in self.view.blocks:
                if block.track_index != encoder_index:
                    continue

                start_dt = QDateTime(block.start_date, QTime(int(block.start_hour), int((block.start_hour % 1) * 60)))
                end_dt   = start_dt.addSecs(int(block.duration_hours * 3600))

                if start_dt <= now <= end_dt:
                    # ⏱ 根據實際停止時間修正時長
                    new_duration = max(0.0, round(start_dt.secsTo(now) / 3600.0, 3))
                    block.duration_hours = new_duration

                    # ✅ 統一用 set_state，顏色/文字一次到位（取代手動 status/setBrush）
                    block.set_state("FINISHED")

                    # 重新排版、幾何
                    block.update_geometry(self.view.base_date)
                    block.update_text_position()

                    # 📌 回寫 block_data（務必把 status 一起寫回）
                    try:
                        end_hour, end_qdate = block.compute_end_dt()
                    except Exception:
                        # 若沒有 compute_end_info()，就自己算：
                        end_dt_now = start_dt.addSecs(int(new_duration * 3600))
                        end_hour   = end_dt_now.time().hour() + end_dt_now.time().minute() / 60.0
                        end_qdate  = end_dt_now.date()

                    block.update_block_data({
                        "duration":   block.duration_hours,
                        "end_hour":   end_hour,
                        "end_qdate":  end_qdate,
                        "status":     block.status,   # ⬅️ 關鍵：把 set_state 後的字串寫回
                    })

                    # 💾 立刻存檔（你的 save_schedule 已會把 block_data.status 寫進 JSON）
                    self.view.save_schedule()

                    stopped_block_id = block.block_id
                    break  # 只處理一個正在錄的 block

            # ✅ 同步 runner 狀態
            if stopped_block_id:
                self.runner.already_stopped.add(stopped_block_id)

            status_label.setText("狀態：✅ 已結束")
            status_label.setStyleSheet("color: gray")
        else:
            status_label.setText("狀態：❌ 停止失敗")
            status_label.setStyleSheet("color: red")

        self.runner.refresh_encoder_statuses()

        # 建議：如果剛剛已 save 並且 draw_grid 會重建 blocks，可視需求保留或拿掉
        # 保留的話，JSON 裡已經有 status，就不怕狀態遺失
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
            if self.view.is_overlap(qdate, track_index, start_hour, duration, exclude_label=None):
                QMessageBox.warning(
                self,
                "❌ 時段衝突",
                "⚠️ 無法錄影，該時段與現有排程重疊。",
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
            self.schedule_manager.already_started.add(block_id)
            self.sync_runner_data()
            for b in self.view.block_data:
                if b.get("id") == block_id:
                    b["status"] = "✅ 錄影中"
                    break
            self.view.save_schedule()  # ✅ 立即儲存
        block = next((blk for blk in self.view.blocks if blk.block_id == block_id), None)
        if block:
            try:
                future = take_snapshot_from_block(block, self.encoder_names, snapshot_root=self.record_root)

                def on_done(fut):
                    snapshot_path = fut.result()

                    def update_ui():
                        if snapshot_path and os.path.exists(snapshot_path):
                            encoder_name = self.encoder_names[block.track_index]
                            self.encoder_pixmaps[encoder_name] = QPixmap(snapshot_path)
                            self.update_preview_scaled(encoder_name)
                            log(f"📸 手動啟動拍照成功 ➜ {snapshot_path}")
                        else:
                            log(f"⚠️ 手動啟動拍照失敗 ➜ {snapshot_path}")

                    QTimer.singleShot(0, update_ui)

                future.add_done_callback(on_done)
            except Exception as e:
                log(f"❌ 手動啟動拍照錯誤：{e}",level="ERROR")
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

        if hasattr(self, "cleanup_timer") and self.cleanup_timer:
            self.cleanup_timer.cancel()
        stop_cleanup_timer()

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
        if hasattr(self, "snapshot_futures"):
            for fut in self.snapshot_futures.values():
                if hasattr(fut, "cancel_event"):
                    fut.cancel_event.set()
            self.snapshot_futures.clear()

        log("👋 MainWindow 已關閉")
        super().closeEvent(event)
        os._exit(0)
        QApplication.quit()