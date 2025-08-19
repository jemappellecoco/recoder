from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QDialogButtonBox,
    QLabel, QDoubleSpinBox, QComboBox, QDateEdit,
)
import re

from PySide6.QtCore import QTime, QDate, QDateTime
from utils import log,ceil_to_next_minute,MIN_LEAD_SECONDS
from encoder_utils import get_encoder_display_name

class AddBlockDialog(QDialog):
     # 至少比現在晚 1 分 30 秒

    def __init__(self, parent=None, encoder_names=None, overlap_checker=None):
        super().__init__(parent)
        self.setWindowTitle("新增排程")
        self.overlap_checker = overlap_checker
        self.encoder_names = encoder_names or []

        self.name_input = QLineEdit()
        self.time_input = QLineEdit()
        self.time_input.setPlaceholderText("例如：0930、9:30")

        # ➤ 預設：下一個整點
        now = QTime.currentTime()
        next_hour = (now.hour() + 1) % 24
        self.time_input.setText(QTime(next_hour, 0).toString("HH:mm"))

        self.duration_input = QDoubleSpinBox()
        self.duration_input.setRange(0.25, 24.0)
        self.duration_input.setSingleStep(0.25)
        self.duration_input.setValue(0.25)

        self.encoder_selector = QComboBox()
        self.date_input = QDateEdit()
        self.date_input.setDate(QDate.currentDate())
        self.date_input.setCalendarPopup(True)

        # ✨ 失焦即自動格式化＋必要時自動修正＋顯示警告
        self.time_input.editingFinished.connect(self.format_time_input)

        for name in self.encoder_names:
            display = get_encoder_display_name(name)
            self.encoder_selector.addItem(display, userData=name)

        self.status_label = QLabel()
        self.status_label.setStyleSheet("color: red")

        form = QFormLayout()
        form.addRow("排程日期：", self.date_input)
        form.addRow("節目名稱：", self.name_input)
        form.addRow("開始時間：", self.time_input)
        form.addRow("持續時間（小時）：", self.duration_input)
        form.addRow("錄影設備：", self.encoder_selector)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(self.status_label)
        layout.addWidget(self.buttons)
        self.setLayout(layout)
        self.MIN_LEAD_SECONDS = int(MIN_LEAD_SECONDS)  
    # ---------- helpers ----------
    # def _ceil_to_next_minute(self, dt: QDateTime) -> QDateTime:
    #     """把時間對齊到下一個整分（清掉秒/毫秒；若有秒/毫秒則進位到下一分）。"""
    #     t = dt.time()
    #     if t.second() == 0 and t.msec() == 0:
    #         return dt
    #     return dt.addSecs(60 - t.second()).addMSecs(-t.msec())

    def parse_time(self, raw):
        def to_half_width(s):
            return ''.join(
                chr(ord(c) - 0xFEE0) if 0xFF01 <= ord(c) <= 0xFF5E else c
                for c in s
            ).replace('：', ':')
        raw = to_half_width(raw.strip())

        # 支援：198, 930, 0930, 19:30, 8:5
        match = re.match(r'^(\d{1,2}):?(\d{1,2})$', raw)
        if not match:
            return None
        hour, minute = int(match.group(1)), int(match.group(2))
        if not (0 <= hour <= 23) or not (0 <= minute <= 59):
            return None
        return QTime(hour, minute)

    # ---------- events ----------
    def format_time_input(self):
        """離開時間欄位：格式化；若是今天且時間 < 現在+90 秒 → 自動修正並顯示警告（橘色）。"""
        time = self.parse_time(self.time_input.text())
        if not time:
            self.status_label.setText("❌ 時間格式錯誤，例如 0930、9:30、198")
            self.status_label.setStyleSheet("color: red")
            self.time_input.setFocus()
            return

        # 正規化 HH:mm
        self.time_input.setText(time.toString("HH:mm"))
        self.status_label.setText("")  # 先清空提示

        # 只對「今天」做 +90 秒限制
        if self.date_input.date() == QDate.currentDate():
            start_dt = QDateTime(self.date_input.date(), QTime(time.hour(), time.minute(), 0))
            min_start = ceil_to_next_minute(QDateTime.currentDateTime().addSecs(self.MIN_LEAD_SECONDS))
            if start_dt < min_start:
                fixed = min_start.time().toString("HH:mm")
                self.time_input.setText(fixed)
                self.status_label.setText(f"⚠️ 開始時間太接近現在，已自動調整為 {fixed}")
                self.status_label.setStyleSheet("color: orange")

    def accept(self):
        """按下 OK：再次保險檢查，若需要同樣自動修正並以警告呈現，不擋住流程。"""
        name = self.name_input.text().strip()
        log(f"🧪 檢查名稱: {name}")
        if not name:
            self.status_label.setText("❌ 節目名稱不能空白")
            self.status_label.setStyleSheet("color: red")
            return

        time = self.parse_time(self.time_input.text())
        if not time:
            self.status_label.setText("❌ 請輸入正確的時間格式，例如 0930、9:30")
            self.status_label.setStyleSheet("color: red")
            return

        qdate = self.date_input.date()
        start_dt = QDateTime(qdate, QTime(time.hour(), time.minute(), 0))
        now_dt = QDateTime.currentDateTime()

        # 今日：至少「現在 + 90 秒」（對齊整分）
        if qdate == now_dt.date():
            min_start = ceil_to_next_minute(now_dt.addSecs(self.MIN_LEAD_SECONDS))
            if start_dt < min_start:
                fixed_str = min_start.time().toString("HH:mm")
                self.time_input.setText(fixed_str)
                self.status_label.setText(f"⚠️ 開始時間太接近現在，已自動調整為 {fixed_str}")
                self.status_label.setStyleSheet("color: orange")
                start_dt = min_start
                time = start_dt.time()

        # 基本時間檢查（這裡多半會通過，除非使用者設的是過去日期）
        if start_dt < now_dt:
            self.status_label.setText("❌ 無法新增過去的行程")
            self.status_label.setStyleSheet("color: red")
            return

        duration = float(self.duration_input.value())  # 小時
        end_dt = start_dt.addSecs(int(duration * 3600))
        if end_dt <= start_dt:
            self.status_label.setText("❌ 結束時間必須晚於開始時間")
            self.status_label.setStyleSheet("color: red")
            return

        # 軌道/重疊檢查
        encoder_name = self.encoder_selector.currentData()
        try:
            track_index = self.encoder_names.index(encoder_name) if encoder_name in self.encoder_names else 0
        except Exception:
            track_index = 0

        # 若 overlap_checker 仍吃 float 小時，維持這行；（之後你改成 HH:MM/分鐘也能替換）
        start_hour = round(time.hour() + time.minute() / 60.0, 4)
        if self.overlap_checker and self.overlap_checker(qdate, track_index, start_hour, duration):
            self.status_label.setText("⚠️ 時間重疊")
            self.status_label.setStyleSheet("color: red")
            return

        # 通過驗證
        self.parsed_time = time
        super().accept()

    def get_values(self):
        return (
            self.name_input.text().strip(),
            self.date_input.date(),
            self.parsed_time,               # 已可能被自動修正過的 QTime
            self.duration_input.value(),
            self.encoder_selector.currentData(),
        )
