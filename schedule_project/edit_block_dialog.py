# edit_block_dialog.py
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QDialogButtonBox, QLabel,
    QTimeEdit, QDoubleSpinBox, QComboBox, QDateEdit, QVBoxLayout, QMessageBox
)
from PySide6.QtCore import QTime, QDate, QDateTime
from encoder_utils import get_encoder_display_name
from utils import hhmm_to_qtime, qtime_to_hhmm,hhmm_to_hours,hours_to_hhmm,MIN_DURATION_HOURS
import re


class EditBlockDialog(QDialog):
    def __init__(self, block_data, encoder_names, readonly=False, overlap_checker=None):
        super().__init__()
        self.setWindowTitle("編輯排程")
        self.block_data = block_data
        self.encoder_names = encoder_names
        self.overlap_checker = overlap_checker

        # ====== 名稱 ======
        self.name_input = QLineEdit(block_data["label"])

        # ====== 開始日期/時間 ======
        # 讀開始時間（相容 start_hour 或 start_time）
        start_hour = block_data.get("start_hour")
        if start_hour is None:
            start_str = block_data.get("start_time", "00:00")
            start_hour = hhmm_to_hours(start_str)

        start_qdate = block_data.get("qdate")
        if isinstance(start_qdate, str):
            start_qdate = QDate.fromString(start_qdate, "yyyy-MM-dd")
        if not isinstance(start_qdate, QDate) or not start_qdate.isValid():
            start_qdate = QDate.currentDate()

        start_qtime = QTime(int(start_hour), int(round((float(start_hour) % 1) * 60)))

        self.date_input = QDateEdit()
        self.date_input.setCalendarPopup(True)
        self.date_input.setDate(start_qdate)
        self.time_input = QLineEdit()
        self.time_input.setPlaceholderText("例如：0930、9:30、198")
        self.time_input.setText(start_qtime.toString("HH:mm"))
        # self.time_input = QTimeEdit()
        # self.time_input.setDisplayFormat("HH:mm")
        # self.time_input.setTime(start_qtime)
        # ====== 持續時間 ======
        duration_hours = block_data.get("duration")
        if duration_hours is None:
            dur_str = block_data.get("duration_time", "00:00")
            duration_hours = hhmm_to_hours(dur_str)

        self.duration_input = QDoubleSpinBox()
        self.duration_input.setRange(MIN_DURATION_HOURS, 72.0)   # 最長可給到 3 天，看需求調整
        self.duration_input.setSingleStep(MIN_DURATION_HOURS)
        self.duration_input.setValue(float(duration_hours))
        

        # ====== 結束日期/時間（新） ======
        # 若 block_data 內已有 end_hour/end_qdate 就用；否則以 start + duration 推
        end_qdate = block_data.get("end_qdate", start_qdate)
        if isinstance(end_qdate, str):
            end_qdate = QDate.fromString(end_qdate, "yyyy-MM-dd")
        if not isinstance(end_qdate, QDate) or not end_qdate.isValid():
            # 用 start + duration 推
            tmp_end = QDateTime(start_qdate, start_qtime).addSecs(int(float(duration_hours) * 3600))
            end_qdate = tmp_end.date()
            end_qtime = tmp_end.time()
        else:
            eh = float(block_data.get("end_hour", start_hour + float(duration_hours)))
            end_qtime = QTime(int(eh) % 24, int(round((eh % 1) * 60)))

        self.end_date_input = QDateEdit()
        self.end_date_input.setCalendarPopup(True)
        self.end_date_input.setDate(end_qdate)
        
        self.end_time_input = QLineEdit()
        self.end_time_input.setPlaceholderText("例如：1030、10:30")
        self.end_time_input.setText(end_qtime.toString("HH:mm"))
        # self.end_time_input = QTimeEdit()
        # self.end_time_input.setDisplayFormat("HH:mm")
        # self.end_time_input.setTime(end_qtime)
        # self.time_input.editingFinished.connect(self._sync_end_from_duration)
        # self.end_time_input.editingFinished.connect(self._sync_duration_from_end)   
        # ====== Encoder ======
        self.encoder_selector = QComboBox()
        for name in encoder_names:
            display = get_encoder_display_name(name)
            self.encoder_selector.addItem(display, userData=name)
        if block_data.get("encoder_name") in encoder_names:
            self.encoder_selector.setCurrentIndex(encoder_names.index(block_data["encoder_name"]))

        # ====== 只讀判定 ======
        if QDateTime(start_qdate, start_qtime) <= QDateTime.currentDateTime():
            readonly = True

        # ====== 表單 ======
        form = QFormLayout()
        form.addRow("排程日期：", self.date_input)
        form.addRow("節目名稱：", self.name_input)
        form.addRow("開始時間：", self.time_input)
        form.addRow("結束日期：", self.end_date_input)   # ← 新增
        form.addRow("結束時間：", self.end_time_input)   # ← 新增
        form.addRow("持續時間（小時）：", self.duration_input)
        form.addRow("錄影設備：", self.encoder_selector)

        # ====== 事件連動（雙向同步）======
        self.duration_input.valueChanged.connect(self._sync_end_from_duration)
        self.time_input.editingFinished.connect(self._sync_end_from_duration) 
        # self.time_input.timeChanged.connect(self._sync_end_from_duration)
        self.date_input.dateChanged.connect(self._sync_end_from_duration)
        self.end_time_input.editingFinished.connect(self._sync_duration_from_end) 
        # self.end_time_input.timeChanged.connect(self._sync_duration_from_end)
        self.end_date_input.dateChanged.connect(self._sync_duration_from_end)
        # self.time_input.editingFinished.connect(lambda: self._normalize_time_field(self.time_input))
        # self.end_time_input.editingFinished.connect(lambda: self._normalize_time_field(self.end_time_input))
        # 先做一次帶值，避免顯示不一致
        self.time_input.editingFinished.connect(self._on_start_edit_finished)
        self.end_time_input.editingFinished.connect(self._on_end_edit_finished)
        self.end_date_input.dateChanged.connect(self._sync_duration_from_end)
        self._sync_end_from_duration()

        # ====== Buttons ======
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        # ====== Layout ======
        layout = QVBoxLayout()
        layout.addLayout(form)

        if readonly:
            warn = QLabel("⛔ 此排程已開始：不可改日期/開始時間/設備；可調整結束或持續時間（不可早於現在）。")
            warn.setStyleSheet("color: red; font-weight: bold")
            layout.addWidget(warn)
            self.date_input.setEnabled(False)
            self.time_input.setEnabled(False)
            self.encoder_selector.setEnabled(False)
            # 注意：end/duration 保持可編輯

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: red; font-weight: bold")
        layout.addWidget(self.error_label)
        layout.addWidget(buttons)
        self.setLayout(layout)
    def _show_error(self, msg: str):
        self.error_label.setText(msg)

    def _clear_error(self):
        self.error_label.setText("")

    def _on_start_edit_finished(self):
        # 先做格式化（930->09:30 / 9:3->09:03）
        qt = self._normalize_time_field(self.time_input)
        if not qt:
            self._show_error("❌ 開始時間格式錯誤（例如 0930、9:30、198）")
            self.time_input.setFocus()
            return
        self._clear_error()
        # 再做同步：由開始 + duration 推結束
        self._sync_end_from_duration()

    def _on_end_edit_finished(self):
        qt = self._normalize_time_field(self.end_time_input)
        if not qt:
            self._show_error("❌ 結束時間格式錯誤（例如 1030、10:30）")
            self.end_time_input.setFocus()
            return
        self._clear_error()
        # 再回推 duration（含跨日與不得早於現在）
        self._sync_duration_from_end()

    def _to_half_width(self, s: str) -> str:
        return ''.join(
        chr(ord(c) - 0xFEE0) if 0xFF01 <= ord(c) <= 0xFF5E else c
        for c in s
    ).replace('：', ':')

    def parse_time(self, raw: str) -> QTime | None:
        raw = self._to_half_width(raw.strip())
        m = re.match(r'^(\d{1,2}):?(\d{1,2})$', raw)
        if not m:
            return None
        h, mi = int(m.group(1)), int(m.group(2))
        if not (0 <= h <= 23) or not (0 <= mi <= 59):
            return None
        return QTime(h, mi)

    def _normalize_time_field(self, le: QLineEdit) -> QTime | None:
        qt = self.parse_time(le.text())
        if not qt:
            return None
        le.setText(qt.toString("HH:mm"))
        return qt

    # ====== 同步：由開始+duration 推結束 ======
    def _sync_end_from_duration(self):
        start_qt = self.parse_time(self.time_input.text())
        if not start_qt:
            return
        start_dt = QDateTime(self.date_input.date(), start_qt)
        end_dt = start_dt.addSecs(int(float(self.duration_input.value()) * 3600))

        # 避免循環訊號
        self.end_time_input.blockSignals(True)
        self.end_date_input.blockSignals(True)
        self.end_time_input.setText(end_dt.time().toString("HH:mm"))
        self.end_date_input.setDate(end_dt.date())
        self.end_time_input.blockSignals(False)
        self.end_date_input.blockSignals(False)

    # ====== 同步：由結束 推回 duration（允許跨日/多日）======
    def _sync_duration_from_end(self):
        start_qt = self.parse_time(self.time_input.text())
        end_qt = self.parse_time(self.end_time_input.text())
        if not start_qt or not end_qt:
            return

        start_dt = QDateTime(self.date_input.date(), start_qt)
        end_dt = QDateTime(self.end_date_input.date(), end_qt)

        # 允許跨日：若 end <= start 就往後加天
        while end_dt <= start_dt:
            end_dt = end_dt.addDays(1)

        # 不得早於現在：若 end < max(now, start+最短)
        now = QDateTime.currentDateTime()
        min_end_dt = max(now, start_dt.addSecs(int(MIN_DURATION_HOURS * 3600)))
        if end_dt < min_end_dt:
            end_dt = min_end_dt
            self.end_time_input.blockSignals(True)
            self.end_date_input.blockSignals(True)
            self.end_time_input.setText(end_dt.time().toString("HH:mm"))
            self.end_date_input.setDate(end_dt.date())
            self.end_time_input.blockSignals(False)
            self.end_date_input.blockSignals(False)

        dur_h = round(start_dt.secsTo(end_dt) / 3600.0, 3)
        self.duration_input.blockSignals(True)
        self.duration_input.setValue(dur_h)
        self.duration_input.blockSignals(False)



    def accept(self):
        # 正規化輸入
        start_qt = self._normalize_time_field(self.time_input)
        end_qt   = self._normalize_time_field(self.end_time_input)
        if not start_qt:
            self.error_label.setText("❌ 請輸入正確的開始時間")
            return
        if not end_qt:
            self.error_label.setText("❌ 請輸入正確的結束時間")
            return

        name = self.name_input.text().strip()
        if not name:
            self.error_label.setText("❌ 節目名稱不能空白")
            return

        qdate = self.date_input.date()
        end_qdate = self.end_date_input.date()

        start_dt = QDateTime(qdate, start_qt)
        end_dt = QDateTime(end_qdate, end_qt)
        while end_dt <= start_dt:   # 允許隔天凌晨
            end_dt = end_dt.addDays(1)

        now = QDateTime.currentDateTime()

        # 原始開始時間（避免往過去移）
        old_qdate = self.block_data["qdate"]
        if isinstance(old_qdate, str):
            old_qdate = QDate.fromString(old_qdate, "yyyy-MM-dd")
        old_start_str = self.block_data.get("start_time", "00:00")
        original_start_dt = QDateTime(old_qdate, hhmm_to_qtime(old_start_str))

        if end_dt <= start_dt:
            self.error_label.setText("❌ 結束時間必須晚於開始時間")
            return
        if end_dt < now:
            self.error_label.setText("❌ 結束時間不能早於現在")
            return
        if start_dt < now and start_dt != original_start_dt:
            self.error_label.setText("❌ 開始時間不能早於現在")
            return

        # 重新計算 duration 並檢查最短時長
        duration = round(start_dt.secsTo(end_dt) / 3600.0, 3)
        if duration < MIN_DURATION_HOURS:
            self.error_label.setText(f"❌ 持續時間不可小於 {MIN_DURATION_HOURS} 小時")
            return
        self.duration_input.setValue(duration)

        # 重疊檢查
        if self.overlap_checker is not None:
            encoder_name = self.encoder_selector.currentData()
            try:
                track_index = self.encoder_names.index(encoder_name) if encoder_name in self.encoder_names else 0
            except Exception:
                track_index = 0
            start_hour = (start_qt.hour() * 60 + start_qt.minute()) / 60.0
            if self.overlap_checker(qdate, track_index, start_hour, duration):
                QMessageBox.warning(self, "❌ 時段衝突", "該時段與現有排程重疊，請調整時間或設備。")
                return

        super().accept()


    def get_updated_data(self):
        start_qt = self.parse_time(self.time_input.text())
        if not start_qt:
            start_qt = QTime(0, 0)
        duration_h = float(self.duration_input.value())

        return {
            "qdate": self.date_input.date().toString("yyyy-MM-dd"),
            "label": self.name_input.text().strip(),
            "start_time": qtime_to_hhmm(start_qt),
            "duration_time": hours_to_hhmm(duration_h),
            "encoder_name": self.encoder_selector.currentData(),
            # 需要的話也可回填：
            # "end_qdate": self.end_date_input.date().toString("yyyy-MM-dd"),
            # "end_time": self.end_time_input.text(),
        }