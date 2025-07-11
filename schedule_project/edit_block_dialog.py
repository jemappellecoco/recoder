# edit_block_dialog.py
from PySide6.QtWidgets import QDialog, QFormLayout, QLineEdit, QDialogButtonBox, QLabel, QTimeEdit, QDoubleSpinBox, QComboBox, QDateEdit, QVBoxLayout
from PySide6.QtCore import QTime, QDate,QDateTime

class EditBlockDialog(QDialog):
    def __init__(self, block_data, encoder_names,readonly=False):
        super().__init__()
        self.setWindowTitle("編輯排程")
        self.block_data = block_data
        self.encoder_names = encoder_names

        self.name_input = QLineEdit(block_data["label"])
        self.time_input = QTimeEdit()
        hour = int(block_data["start_hour"])
        minute = int((block_data["start_hour"] % 1) * 60)
        self.time_input.setTime(QTime(hour, minute))
        self.time_input.setDisplayFormat("HH:mm")
        start_qdate = block_data["qdate"]
        if isinstance(start_qdate, str):
            start_qdate = QDate.fromString(start_qdate, "yyyy-MM-dd")
        start_qtime = QTime(hour, minute)
        start_dt = QDateTime(start_qdate, start_qtime)

        if start_dt <= QDateTime.currentDateTime():
            readonly = True
        self.duration_input = QDoubleSpinBox()
        self.duration_input.setRange(0.25, 24.0)
        self.duration_input.setSingleStep(0.25)
        self.duration_input.setValue(block_data["duration"])

        self.encoder_selector = QComboBox()
        self.encoder_selector.addItems(encoder_names)
        if block_data.get("encoder_name") in encoder_names:
            self.encoder_selector.setCurrentText(block_data["encoder_name"])

        self.date_input = QDateEdit()
        self.date_input.setDate(block_data["qdate"])
        self.date_input.setCalendarPopup(True)

        form = QFormLayout()
        form.addRow("排程日期：", self.date_input)
        form.addRow("節目名稱：", self.name_input)
        form.addRow("開始時間：", self.time_input)
        form.addRow("持續時間（小時）：", self.duration_input)
        form.addRow("錄影設備：", self.encoder_selector)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addLayout(form)
        
        if readonly:
            warning_label = QLabel("⛔ 此排程已開始，僅可修改節目名稱與持續時間（不可早於現在）")
            warning_label.setStyleSheet("color: red; font-weight: bold")
            layout.addWidget(warning_label)

            # ✅ 鎖定不可修改的欄位
            self.date_input.setEnabled(False)
            self.time_input.setEnabled(False)
            self.encoder_selector.setEnabled(False)
        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: red; font-weight: bold")
        layout.addWidget(self.error_label)
        layout.addWidget(buttons)
        self.setLayout(layout)
    def accept(self):
        self.time_input.interpretText()  # 防止手動輸入沒轉換

        name = self.name_input.text().strip()
        if not name:
            self.error_label.setText("❌ 節目名稱不能空白")
            return

        time = self.time_input.time()
        qdate = self.date_input.date()
        duration = self.duration_input.value()
        
        start_dt = QDateTime(qdate, time)
        end_dt = start_dt.addSecs(int(duration * 3600))
        now = QDateTime.currentDateTime()

        if start_dt < now:
            self.error_label.setText("❌ 開始時間不能早於現在")
            return

        if end_dt < now:
            self.error_label.setText("❌ 結束時間不能早於現在")
            return

        super().accept()
    def get_updated_data(self):
        time = self.time_input.time()
        return {
            "qdate": self.date_input.date(),
            "label": self.name_input.text().strip(),
            "start_hour": round(time.hour() + time.minute() / 60, 2),
            "duration": self.duration_input.value(),
            "encoder_name": self.encoder_selector.currentText()
        }
