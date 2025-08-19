# edit_block_dialog.py
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QDialogButtonBox, QLabel,
    QTimeEdit, QDoubleSpinBox, QComboBox, QDateEdit, QVBoxLayout, QMessageBox
)
from PySide6.QtCore import QTime, QDate, QDateTime
from encoder_utils import get_encoder_display_name
from utils import hhmm_to_qtime, qtime_to_hhmm,hhmm_to_hours,hours_to_hhmm
class EditBlockDialog(QDialog):
    def __init__(self, block_data, encoder_names, readonly=False, overlap_checker=None):
        super().__init__()
        self.setWindowTitle("編輯排程")
        self.block_data = block_data
        self.encoder_names = encoder_names
        self.overlap_checker = overlap_checker    # ← 新增

        self.name_input = QLineEdit(block_data["label"])
        # --- 讀開始時間（相容兩種格式） ---
        start_hour = block_data.get("start_hour")
        if start_hour is None:
            # 新格式：'HH:MM'
            start_str = block_data.get("start_time", "00:00")
            start_hour = hhmm_to_hours(start_str)
        # ---- time/date ----
        hour = int(float(start_hour))
        minute = int(round((float(start_hour) % 1) * 60))
        start_qtime = QTime(hour, minute)
        start_qdate = block_data["qdate"]
        
        start_qdate = block_data.get("qdate")
        if isinstance(start_qdate, str):
            start_qdate = QDate.fromString(start_qdate, "yyyy-MM-dd")
        elif not isinstance(start_qdate, QDate):
            start_qdate = QDate.currentDate()

        self.time_input = QTimeEdit()
        self.time_input.setTime(start_qtime)
        self.time_input.setDisplayFormat("HH:mm")

        self.date_input = QDateEdit()
        self.date_input.setDate(start_qdate)     # ← 用已轉好的 QDate
        self.date_input.setCalendarPopup(True)

        start_dt = QDateTime(start_qdate, start_qtime)
        if start_dt <= QDateTime.currentDateTime():
            readonly = True
        # --- 讀持續時間（相容兩種格式） ---
        duration_hours = block_data.get("duration")
        if duration_hours is None:
            dur_str = block_data.get("duration_time", "00:00")
            duration_hours = hhmm_to_hours(dur_str)
        # ---- duration ----
        self.duration_input = QDoubleSpinBox()
        self.duration_input.setRange(0.25, 24.0)
        self.duration_input.setSingleStep(0.25)
        self.duration_input.setValue(float(duration_hours))
        # ---- encoder ----
        self.encoder_selector = QComboBox()
        for name in encoder_names:
            display = get_encoder_display_name(name)
            self.encoder_selector.addItem(display, userData=name)
        if block_data.get("encoder_name") in encoder_names:
            self.encoder_selector.setCurrentIndex(encoder_names.index(block_data["encoder_name"]))

        # ---- form ----
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
            self.date_input.setEnabled(False)
            self.time_input.setEnabled(False)
            self.encoder_selector.setEnabled(False)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: red; font-weight: bold")
        layout.addWidget(self.error_label)
        layout.addWidget(buttons)
        self.setLayout(layout)
        start_qtime = hhmm_to_qtime(block_data["start_time"])
        self.time_input.setTime(start_qtime)
    def accept(self):
        self.time_input.interpretText()

        name = self.name_input.text().strip()
        if not name:
            self.error_label.setText("❌ 節目名稱不能空白")
            return

        time = self.time_input.time()
        qdate = self.date_input.date()
        duration = float(self.duration_input.value())
        start_dt = QDateTime(qdate, time)
        end_dt = start_dt.addSecs(int(duration * 3600))
        now = QDateTime.currentDateTime()

        # 原始開始時間（用於判斷是否把開始時間往「更早」改）
        old_qdate = self.block_data["qdate"]
        if isinstance(old_qdate, str):
            old_qdate = QDate.fromString(old_qdate, "yyyy-MM-dd")
        old_start_str = self.block_data.get("start_time", "00:00")
        old_qtime = hhmm_to_qtime(old_start_str)
        original_start_dt = QDateTime(old_qdate, old_qtime)

        # 基本檢查
        if end_dt <= start_dt:
            self.error_label.setText("❌ 結束時間必須晚於開始時間")
            return
        if start_dt < now and start_dt != original_start_dt:
            self.error_label.setText("❌ 開始時間不能早於現在")
            return

        # ---- 重疊檢查（重點）----
        if self.overlap_checker is not None:
            encoder_name = self.encoder_selector.currentData()
            try:
                track_index = self.encoder_names.index(encoder_name) if encoder_name in self.encoder_names else 0
            except Exception:
                track_index = 0

            start_hour = round(time.hour() + time.minute() / 60.0, 4)

            # 排除自己：用 label（若你有 block_id，更好改成 exclude_id）
            def overlap(qd, ti, sh, dur):
                return self.overlap_checker(qd, ti, sh, dur)

            if overlap(qdate, track_index, start_hour, duration):
                QMessageBox.warning(self, "❌ 時段衝突", "該時段與現有排程重疊，請調整時間或設備。")
                return

        super().accept()
    def get_updated_data(self):
        t = self.time_input.time()
        duration_h = float(self.duration_input.value())
        return {
            "qdate": self.date_input.date().toString("yyyy-MM-dd"),
            "label": self.name_input.text().strip(),
            "start_time": qtime_to_hhmm(t),
            "duration_time": hours_to_hhmm(duration_h),
            "encoder_name": self.encoder_selector.currentData(),
        }
