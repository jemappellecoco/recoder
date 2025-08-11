from PySide6.QtWidgets import (
        QDialog, QVBoxLayout, QFormLayout, QLineEdit, QDialogButtonBox,
    QLabel, QDoubleSpinBox, QComboBox, QDateEdit,
)
import re
from PySide6.QtCore import QTime,QDate,QDateTime
from utils import log
from encoder_utils import get_encoder_display_name
class AddBlockDialog(QDialog):
    def __init__(self, parent=None, encoder_names=None, overlap_checker=None):
        super().__init__(parent)
        self.setWindowTitle("新增排程")
        self.overlap_checker = overlap_checker
        self.encoder_names = encoder_names or []

        self.name_input = QLineEdit()
        self.time_input = QLineEdit()
        self.time_input.setPlaceholderText("例如：0930、9:30")
        # ➤ 計算下一個整點時間
        now = QTime.currentTime()
        next_hour = (now.hour() + 1) % 24  # 若是23點，變成00點
        self.time_input.setText(QTime(next_hour, 0).toString("HH:mm"))
        self.duration_input = QDoubleSpinBox()
        self.duration_input.setRange(0.25, 24.0)
        self.duration_input.setSingleStep(0.25)
        # self.duration_input.setValue(1.0) 
        self.duration_input.setValue(0.25) 

        self.encoder_selector = QComboBox()
        self.date_input = QDateEdit()
        self.date_input.setDate(QDate.currentDate())
        self.date_input.setCalendarPopup(True)
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
    def format_time_input(self):
        time = self.parse_time(self.time_input.text())
        if time:
            self.time_input.setText(time.toString("HH:mm"))
            self.status_label.setText("")  # ✅ 清除錯誤訊息
        else:
            self.status_label.setText("❌ 時間格式錯誤，例如 0930、9:30、198")
            self.time_input.setFocus()
            
    def parse_time(self, raw):
        def to_half_width(s):
            return ''.join(
                chr(ord(c) - 0xFEE0) if 0xFF01 <= ord(c) <= 0xFF5E else c
                for c in s
            ).replace('：', ':')

        raw = to_half_width(raw.strip())

        # ➤ 自動補零：如 198 → 19:08
        # 支援格式：198, 930, 0930, 19:30, 8:5 等
        match = re.match(r'^(\d{1,2}):?(\d{1,2})$', raw)
        if not match:
            return None

        hour, minute = int(match.group(1)), int(match.group(2))

        if not (0 <= hour <= 23):
            return None
        if not (0 <= minute <= 59):
            return None

        return QTime(hour, minute)

    def accept(self):
        name = self.name_input.text().strip()
        log(f"🧪 檢查名稱: {name}")
        if not name:
            self.status_label.setText("❌ 節目名稱不能空白")
            return

        # ✅ 使用自己寫的 parse_time 處理 QLineEdit 輸入的字串
        time = self.parse_time(self.time_input.text())
        if not time:
            self.status_label.setText("❌ 請輸入正確的時間格式，例如 0930、9:30")
            return

        start_hour = round(time.hour() + time.minute() / 60, 2)
        duration = self.duration_input.value()
        encoder_name = self.encoder_selector.currentData()
        track_index = self.encoder_names.index(encoder_name)
        qdate = self.date_input.date()

        start_dt = QDateTime(qdate, time)
        end_dt = start_dt.addSecs(int(duration * 3600))
        now = QDateTime.currentDateTime()

        if start_dt < now:
            self.status_label.setText("❌ 無法新增過去的行程")
            return

        if end_dt < now:
            self.status_label.setText("❌ 結束時間不能早於現在時間")
            return

        if self.overlap_checker and self.overlap_checker(track_index, start_hour, duration, qdate):
            self.status_label.setText("⚠️ 時間重疊")
            return

        self.parsed_time = time  # ✅ 儲存起來，供 get_values() 使用
        super().accept()

    def get_values(self):
        return (
        self.name_input.text().strip(),
        self.date_input.date(),
        self.parsed_time,  # ✅ 使用剛剛解析好的 QTime
        self.duration_input.value(),
        self.encoder_selector.currentData(),
    )


