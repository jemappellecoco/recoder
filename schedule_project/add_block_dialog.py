from PySide6.QtWidgets import (
        QDialog, QVBoxLayout, QFormLayout, QLineEdit, QDialogButtonBox,
    QLabel, QTimeEdit, QDoubleSpinBox, QComboBox, QDateEdit,
)
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
        self.time_input = QTimeEdit()
        self.time_input.setDisplayFormat("HH:mm")
        self.time_input.setTime(QTime(9, 0))

        self.duration_input = QDoubleSpinBox()
        self.duration_input.setRange(0.25, 24.0)
        self.duration_input.setSingleStep(0.25)
        # self.duration_input.setValue(1.0) 
        self.duration_input.setValue(0.25) 

        self.encoder_selector = QComboBox()
        self.date_input = QDateEdit()
        self.date_input.setDate(QDate.currentDate())
        self.date_input.setCalendarPopup(True)

        
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

    def accept(self):
        self.time_input.interpretText()
        name = self.name_input.text().strip()
        log(f"🧪 檢查名稱: {name}")
        if not name:
            self.status_label.setText("❌ 節目名稱不能空白")
            return
        
        time = self.time_input.time()
        start_hour = round(self.time_input.time().hour() + self.time_input.time().minute() / 60, 2)
        duration = self.duration_input.value()
        encoder_name = self.encoder_selector.currentData()
        track_index = self.encoder_names.index(encoder_name)
        qdate = self.date_input.date()
        
        start_dt = QDateTime(qdate, time)
        end_dt = start_dt.addSecs(int(duration * 3600))
        now = QDateTime.currentDateTime()
       # ✅ 開始時間不能早於現在
        if start_dt < now:
            self.status_label.setText("❌ 無法新增過去的行程")
            return

        # ✅ 結束時間也不能早於現在（防止長度過短 + 過期）
        if end_dt < now:
            self.status_label.setText("❌ 結束時間不能早於現在時間")
            return

        # ✅ 檢查時間重疊
        if self.overlap_checker and self.overlap_checker(track_index, start_hour, duration, qdate):
            self.status_label.setText("⚠️ 時間重疊")
            return

        super().accept()

    def get_values(self):
        return (
            self.name_input.text().strip(),
            self.date_input.date(),
            self.time_input.time(),
            self.duration_input.value(),
            self.encoder_selector.currentData(),
        )


