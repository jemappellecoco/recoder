# from PySide6.QtWidgets import (
#     QDialog, QVBoxLayout, QFormLayout, QLineEdit, QDialogButtonBox,
#     QLabel, QDoubleSpinBox, QComboBox, QDateEdit,
# )
# import re

# from PySide6.QtCore import QTime, QDate, QDateTime
# from utils import log,ceil_to_next_minute,MIN_LEAD_SECONDS
# from encoder_utils import get_encoder_display_name

# class AddBlockDialog(QDialog):
#     """新增排程：開始/結束時間皆可手動輸入，並與「持續時間」雙向同步。"""
#     def __init__(self, parent=None, encoder_names=None, overlap_checker=None):
#         super().__init__(parent)
#         self.setWindowTitle("新增排程")
#         self.overlap_checker = overlap_checker
#         self.encoder_names = encoder_names or []

#         # 內部旗標：結束時間是否被手動輸入過（避免覆蓋使用者意圖）
#         self._end_manually_set = False

#         # ====== 欄位 ======
#         self.name_input = QLineEdit()

#         # 日期
#         self.date_input = QDateEdit()
#         self.date_input.setDate(QDate.currentDate())
#         self.date_input.setCalendarPopup(True)

#         # 開始與結束時間（皆可手動）
#         self.start_time_input = QLineEdit()
#         self.start_time_input.setPlaceholderText("例如：0930、9:30、198")

#         self.end_time_input = QLineEdit()
#         self.end_time_input.setPlaceholderText("例如：1030、10:30")

#         # 預設：下一個整點開始、持續 0.25h、結束 = 開始 + 持續
#         now = QTime.currentTime()
#         next_hour = (now.hour() + 1) % 24
#         start_qt = QTime(next_hour, 0)
#         self.start_time_input.setText(start_qt.toString("HH:mm"))

#         self.duration_input = QDoubleSpinBox()
#         self.duration_input.setRange(0.25, 24.0)
#         self.duration_input.setSingleStep(0.25)
#         self.duration_input.setValue(0.25)

#         end_qt = start_qt.addSecs(int(self.duration_input.value() * 3600))
#         self.end_time_input.setText(end_qt.toString("HH:mm"))

#         # 錄影設備
#         self.encoder_selector = QComboBox()
#         for name in self.encoder_names:
#             display = get_encoder_display_name(name)
#             self.encoder_selector.addItem(display, userData=name)

#         # 狀態提示
#         self.status_label = QLabel()
#         self.status_label.setStyleSheet("color: red")

#         # 事件連結
#         self.start_time_input.editingFinished.connect(self._on_start_time_finished)
#         self.end_time_input.editingFinished.connect(self._on_end_time_finished)
#         self.duration_input.valueChanged.connect(self._on_duration_changed)
#         self.date_input.dateChanged.connect(self._on_date_changed)

#         # 佈局
#         form = QFormLayout()
#         form.addRow("排程日期：", self.date_input)
#         form.addRow("節目名稱：", self.name_input)
#         form.addRow("開始時間：", self.start_time_input)
#         form.addRow("結束時間：", self.end_time_input)
#         form.addRow("持續時間（小時）：", self.duration_input)
#         form.addRow("錄影設備：", self.encoder_selector)

#         self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
#         self.buttons.accepted.connect(self.accept)
#         self.buttons.rejected.connect(self.reject)

#         layout = QVBoxLayout()
#         layout.addLayout(form)
#         layout.addWidget(self.status_label)
#         layout.addWidget(self.buttons)
#         self.setLayout(layout)

#         self.MIN_LEAD_SECONDS = int(MIN_LEAD_SECONDS)
#         self.parsed_start_time = None
#         self.parsed_end_time = None

#     # ---------- 解析/格式化 ----------
#     def _to_half_width(self, s: str) -> str:
#         return ''.join(
#             chr(ord(c) - 0xFEE0) if 0xFF01 <= ord(c) <= 0xFF5E else c
#             for c in s
#         ).replace('：', ':')

#     def parse_time(self, raw: str) -> QTime | None:
#         raw = self._to_half_width(raw.strip())
#         # 支援：198, 930, 0930, 19:30, 8:5
#         match = re.match(r'^(\d{1,2}):?(\d{1,2})$', raw)
#         if not match:
#             return None
#         hour, minute = int(match.group(1)), int(match.group(2))
#         if not (0 <= hour <= 23) or not (0 <= minute <= 59):
#             return None
#         return QTime(hour, minute)

#     def _normalize_time_field(self, le: QLineEdit) -> QTime | None:
#         qt = self.parse_time(le.text())
#         if not qt:
#             return None
#         le.setText(qt.toString("HH:mm"))
#         return qt

#     # ---------- 同步邏輯 ----------
#     def _on_date_changed(self, *_):
#         # 若是今天，重跑開始時間最小限制（自動補 90s & 進位到整分）
#         self._apply_min_lead_on_start(adjust_end_if_needed=True)

#     def _on_start_time_finished(self):
#         start_qt = self._normalize_time_field(self.start_time_input)
#         if not start_qt:
#             self._error("❌ 時間格式錯誤（開始）例如 0930、9:30、198")
#             self.start_time_input.setFocus()
#             return

#         # 先清除錯誤
#         self._info("")
#         # 最小提前限制（今天）
#         fixed_start_qt = self._apply_min_lead_on_start(adjust_end_if_needed=not self._end_manually_set)
#         if fixed_start_qt:
#             start_qt = fixed_start_qt

#         # 依據是否手動設定結束時間，決定重新計算
#         end_qt = self.parse_time(self.end_time_input.text())
#         if not end_qt:
#             # 沒有有效結束 → 用 duration 推算
#             end_qt = start_qt.addSecs(int(self.duration_input.value() * 3600))
#             self.end_time_input.setText(end_qt.toString("HH:mm"))
#         else:
#             # 有有效結束：
#             if not self._end_manually_set:
#                 # 結束不是手動 → 用 duration 推算結束
#                 end_qt = start_qt.addSecs(int(self.duration_input.value() * 3600))
#                 self.end_time_input.setText(end_qt.toString("HH:mm"))
#             else:
#                 # 結束是手動 → 反算 duration
#                 dur_sec = start_qt.secsTo(end_qt)
#                 if dur_sec <= 0:
#                     self._error("❌ 結束時間必須晚於開始時間")
#                     return
#                 self._set_duration_safely(dur_sec / 3600.0)

#     def _on_end_time_finished(self):
#         end_qt = self._normalize_time_field(self.end_time_input)
#         if not end_qt:
#             self._error("❌ 時間格式錯誤（結束）例如 1030、10:30")
#             self.end_time_input.setFocus()
#             return

#         start_qt = self.parse_time(self.start_time_input.text())
#         if not start_qt:
#             self._error("❌ 先輸入正確的開始時間")
#             self.start_time_input.setFocus()
#             return

#         dur_sec = start_qt.secsTo(end_qt)
#         if dur_sec <= 0:
#             # ✅ 改為依目前 duration 自動調整結束時間
#             fix_end = start_qt.addSecs(int(float(self.duration_input.value()) * 3600))
#             self.end_time_input.blockSignals(True)
#             self.end_time_input.setText(fix_end.toString("HH:mm"))
#             self.end_time_input.blockSignals(False)

#             # 視為「非手動設定結束」，之後改開始時會跟著跑
#             self._end_manually_set = False
#             self._warn(f"⚠️ 結束早於開始，已依持續時間調整為 {fix_end.toString('HH:mm')}")
#             return

#         # 正常路徑：反算 duration
#         self._end_manually_set = True
#         self._info("")
#         self._set_duration_safely(dur_sec / 3600.0)

#     def _on_duration_changed(self, new_hours: float):
#         """當使用者調整『持續時間（小時）』時，強制以開始時間推算並覆寫結束時間。"""
#         start_qt = self.parse_time(self.start_time_input.text())
#         if not start_qt:
#             return

#         # 小時 → 秒 → 推算新的結束時間
#         end_qt = start_qt.addSecs(int(float(new_hours) * 3600))

#         # 這次是由 duration 主導的更新 → 視為「非手動設定結束」狀態
#         # 讓後續若再改『開始時間』時，仍會依目前 duration 自動回推結束時間
#         self._end_manually_set = False

#         # 避免觸發 editingFinished / valueChanged 連鎖
#         self.end_time_input.blockSignals(True)
#         self.end_time_input.setText(end_qt.toString("HH:mm"))
#         self.end_time_input.blockSignals(False)

#     def _apply_min_lead_on_start(self, adjust_end_if_needed: bool) -> QTime | None:
#         """若為今天：開始時間 < 現在 + MIN_LEAD_SECONDS（進位到整分）→ 自動調整；必要時連動結束。"""
#         if self.date_input.date() != QDate.currentDate():
#             return None
#         start_qt = self.parse_time(self.start_time_input.text())
#         if not start_qt:
#             return None

#         start_dt = QDateTime(self.date_input.date(), QTime(start_qt.hour(), start_qt.minute(), 0))
#         now_dt = QDateTime.currentDateTime()
#         min_start = ceil_to_next_minute(now_dt.addSecs(self.MIN_LEAD_SECONDS))
#         if start_dt < min_start:
#             fixed_qt = min_start.time()
#             self.start_time_input.setText(fixed_qt.toString("HH:mm"))
#             self._warn(f"⚠️ 開始時間太接近現在，已自動調整為 {fixed_qt.toString('HH:mm')}")
#             if adjust_end_if_needed:
#                 # 以目前 duration 推算新的結束
#                 end_qt = fixed_qt.addSecs(int(self.duration_input.value() * 3600))
#                 self.end_time_input.setText(end_qt.toString("HH:mm"))
#             return fixed_qt
#         return None

#     # ---------- 訊息 ----------
#     def _error(self, msg: str):
#         self.status_label.setText(msg)
#         self.status_label.setStyleSheet("color: red")

#     def _warn(self, msg: str):
#         self.status_label.setText(msg)
#         self.status_label.setStyleSheet("color: orange")

#     def _info(self, msg: str):
#         self.status_label.setText(msg)
#         self.status_label.setStyleSheet("color: green" if msg else "")

#     def _set_duration_safely(self, hours_val: float):
#         """避免 valueChanged 迴圈觸發時造成抖動。"""
#         old = float(self.duration_input.value())
#         if abs(old - hours_val) >= 1e-6:
#             self.duration_input.blockSignals(True)
#             self.duration_input.setValue(max(0.25, min(24.0, hours_val)))
#             self.duration_input.blockSignals(False)

#     # ---------- OK ----------
#     def accept(self):
#         name = self.name_input.text().strip()
#         log(f"🧪 檢查名稱: {name}")
#         if not name:
#             self._error("❌ 節目名稱不能空白")
#             return

#         start_qt = self._normalize_time_field(self.start_time_input)
#         if not start_qt:
#             self._error("❌ 請輸入正確的開始時間")
#             return

#         end_qt = self._normalize_time_field(self.end_time_input)
#         if not end_qt:
#             self._error("❌ 請輸入正確的結束時間")
#             return

#         qdate = self.date_input.date()
#         start_dt = QDateTime(qdate, QTime(start_qt.hour(), start_qt.minute(), 0))
#         end_dt   = QDateTime(qdate, QTime(end_qt.hour(), end_qt.minute(), 0))
#         now_dt   = QDateTime.currentDateTime()

#         # 今日：最小提前
#         if qdate == now_dt.date():
#             min_start = ceil_to_next_minute(now_dt.addSecs(self.MIN_LEAD_SECONDS))
#             if start_dt < min_start:
#                 fixed_str = min_start.time().toString("HH:mm")
#                 self.start_time_input.setText(fixed_str)
#                 self._warn(f"⚠️ 開始時間太接近現在，已自動調整為 {fixed_str}")
#                 start_dt = min_start
#                 start_qt = start_dt.time()
#                 # 若結束不是手動設定過，就用 duration 推算新的結束
#                 if not self._end_manually_set:
#                     end_dt = start_dt.addSecs(int(self.duration_input.value() * 3600))
#                     self.end_time_input.setText(end_dt.time().toString("HH:mm"))

#         # 不可新增到過去
#         if start_dt < now_dt:
#             self._error("❌ 無法新增過去的行程")
#             return

#         # 結束需晚於開始
#         if end_dt <= start_dt:
#             self._error("❌ 結束時間必須晚於開始時間")
#             return

#         # 計算 duration（以開始/結束為準）
#         dur_hours = start_dt.secsTo(end_dt) / 3600.0
#         self._set_duration_safely(dur_hours)

#         # 重疊檢查
#         encoder_name = self.encoder_selector.currentData()
#         try:
#             track_index = self.encoder_names.index(encoder_name) if encoder_name in self.encoder_names else 0
#         except Exception:
#             track_index = 0

#         start_hour_float = (start_qt.hour() * 60 + start_qt.minute()) / 60.0
#         if self.overlap_checker and self.overlap_checker(qdate, track_index, start_hour_float, dur_hours):
#             self._error("⚠️ 時間重疊")
#             return

#         # 透過驗證
#         self.parsed_start_time = start_qt
#         self.parsed_end_time = end_dt.time()
#         super().accept()

#     def get_values(self):
#         """回傳：name, date, start_qtime, duration_hours, encoder_name, end_qtime（可用就拿）"""
#         return (
#             self.name_input.text().strip(),
#             self.date_input.date(),
#             self.parsed_start_time,            # QTime
#             float(self.duration_input.value()),# 小時（與 start/end 同步後的最終值）
#             self.encoder_selector.currentData(),
#             self.parsed_end_time,              # QTime（新增）
#         )


# add_block_dialog.py
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QDialogButtonBox,
    QLabel, QDoubleSpinBox, QComboBox, QDateEdit,
)
import re, math
from PySide6.QtCore import QTime, QDate, QDateTime
from utils import log, ceil_to_next_minute, MIN_LEAD_SECONDS, MIN_DURATION_HOURS
from encoder_utils import get_encoder_display_name


class AddBlockDialog(QDialog):
    """
    新增排程（QLineEdit 版）：
    - 開始/結束皆可手動輸入
    - 與「持續時間（小時）」雙向同步
    - 以 MIN_DURATION_HOURS（預設 0.25h=15 分）為粒度自動對齊（ceil/補上去）
    - 今天的開始時間需 ≥ 現在 + MIN_LEAD_SECONDS（並進位到整分）
    - 結束必須晚於開始，且 (結束-開始) 為 MIN_DURATION_HOURS 的整數倍
    """
    def __init__(self, parent=None, encoder_names=None, overlap_checker=None):
        super().__init__(parent)
        self.setWindowTitle("新增排程")
        self.overlap_checker = overlap_checker
        self.encoder_names = encoder_names or []

        # 內部旗標：結束時間是否被手動輸入過（避免覆蓋使用者意圖）
        self._end_manually_set = False

        # ====== 欄位 ======
        self.name_input = QLineEdit()

        # 日期
        self.date_input = QDateEdit()
        self.date_input.setDate(QDate.currentDate())
        self.date_input.setCalendarPopup(True)

        # 開始/結束（QLineEdit，支援 930/09:30/9:3/198）
        self.start_time_input = QLineEdit()
        self.start_time_input.setPlaceholderText("例如：0930、9:30、198")

        self.end_time_input = QLineEdit()
        self.end_time_input.setPlaceholderText("例如：1030、10:30")

        # 預設：下一個整點 + 最短時長
        now = QTime.currentTime()
        next_hour = (now.hour() + 1) % 24
        start_qt = QTime(next_hour, 0)
        self.start_time_input.setText(start_qt.toString("HH:mm"))

        self.duration_input = QDoubleSpinBox()
        self.duration_input.setRange(MIN_DURATION_HOURS, 24.0)
        self.duration_input.setSingleStep(MIN_DURATION_HOURS)
        self.duration_input.setValue(MIN_DURATION_HOURS)  # 預設最短

        end_qt = start_qt.addSecs(int(self.duration_input.value() * 3600))
        self.end_time_input.setText(end_qt.toString("HH:mm"))

        # 錄影設備
        self.encoder_selector = QComboBox()
        for name in self.encoder_names:
            display = get_encoder_display_name(name)
            self.encoder_selector.addItem(display, userData=name)

        # 狀態提示
        self.status_label = QLabel()
        self.status_label.setStyleSheet("color: red")

        # 事件連結
        self.start_time_input.editingFinished.connect(self._on_start_time_finished)
        self.end_time_input.editingFinished.connect(self._on_end_time_finished)
        self.duration_input.valueChanged.connect(self._on_duration_changed)
        self.date_input.dateChanged.connect(self._on_date_changed)

        # 佈局
        form = QFormLayout()
        form.addRow("排程日期：", self.date_input)
        form.addRow("節目名稱：", self.name_input)
        form.addRow("開始時間：", self.start_time_input)
        form.addRow("結束時間：", self.end_time_input)
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
        self.STEP_MIN = int(round(MIN_DURATION_HOURS * 60))  # 例如 0.25h → 15 分
        self.parsed_start_time = None
        self.parsed_end_time = None

    # ---------- 解析/格式化 ----------
    def _to_half_width(self, s: str) -> str:
        return ''.join(
            chr(ord(c) - 0xFEE0) if 0xFF01 <= ord(c) <= 0xFF5E else c
            for c in s
        ).replace('：', ':')

    def parse_time(self, raw: str) -> QTime | None:
        raw = self._to_half_width(raw.strip())
        # 支援：198, 930, 0930, 19:30, 8:5
        m = re.match(r'^(\d{1,2}):?(\d{1,2})$', raw)
        if not m:
            return None
        h, mi = int(m.group(1)), int(m.group(2))
        if not (0 <= h <= 23) or not (0 <= mi <= 59):
            return None
        return QTime(h, mi)

    def _normalize_time_field(self, le: QLineEdit, *, ceil_to_step=False) -> QTime | None:
        """解析 + 正規化為 HH:mm；ceil_to_step=True 會把分鐘進位到 STEP_MIN。"""
        qt = self.parse_time(le.text())
        if not qt:
            return None
        if ceil_to_step:
            qt = self._ceil_time_to_step(qt)
        le.setText(qt.toString("HH:mm"))
        return qt

    def _ceil_time_to_step(self, t: QTime) -> QTime:
        """把時間分鐘數以 STEP_MIN 做『進位』對齊（13:12 → 13:15；13:45 → 14:00）。"""
        total = t.hour() * 60 + t.minute()
        step = self.STEP_MIN
        snapped = int(math.ceil(total / step) * step)
        snapped %= (24 * 60)
        return QTime(snapped // 60, snapped % 60)

    # ---------- 同步邏輯 ----------
    def _on_date_changed(self, *_):
        # 若是今天，重跑開始時間最小限制（自動補 lead 秒 & 進位到整分）
        self._apply_min_lead_on_start(adjust_end_if_needed=True)

    def _on_start_time_finished(self):
        # 開始時間：先解析 → 以 STEP_MIN 進位對齊
        start_qt = self._normalize_time_field(self.start_time_input, ceil_to_step=True)
        if not start_qt:
            self._error("❌ 時間格式錯誤（開始）例如 0930、9:30、198")
            self.start_time_input.setFocus()
            return

        self._info("")

        # 今日：至少 ≥ 現在 + lead（且對齊整分，不改動 STEP 對齊）
        fixed_start_qt = self._apply_min_lead_on_start(adjust_end_if_needed=not self._end_manually_set)
        if fixed_start_qt:
            start_qt = fixed_start_qt

        # 依使用者是否手動設定結束，決定推算方式
        end_qt = self.parse_time(self.end_time_input.text())
        if not end_qt:
            end_qt = start_qt.addSecs(int(self.duration_input.value() * 3600))
            end_qt = self._ceil_time_to_step(end_qt)  # 結束也對齊粒度
            self.end_time_input.setText(end_qt.toString("HH:mm"))
        else:
            if not self._end_manually_set:
                end_qt = start_qt.addSecs(int(self.duration_input.value() * 3600))
                end_qt = self._ceil_time_to_step(end_qt)
                self.end_time_input.setText(end_qt.toString("HH:mm"))
            else:
                # 結束手動過 → 反算 duration，並把 duration 以粒度進位
                dur_min = max(0, start_qt.secsTo(end_qt) // 60)
                if dur_min <= 0:
                    self._error("❌ 結束時間必須晚於開始時間")
                    return
                dur_min = int(math.ceil(dur_min / self.STEP_MIN) * self.STEP_MIN)
                end_qt = start_qt.addSecs(dur_min * 60)
                self.end_time_input.setText(end_qt.toString("HH:mm"))
                self._set_duration_safely(dur_min / 60.0)

    def _on_end_time_finished(self):
        # 結束時間：解析（不直接做步長進位）
        end_qt = self._normalize_time_field(self.end_time_input, ceil_to_step=False)
        if not end_qt:
            self._error("❌ 時間格式錯誤（結束）例如 1030、10:30")
            self.end_time_input.setFocus()
            return

        start_qt = self.parse_time(self.start_time_input.text())
        if not start_qt:
            self._error("❌ 先輸入正確的開始時間")
            self.start_time_input.setFocus()
            return

        # 以 MIN_DURATION_HOURS 粒度「補上去」：確保 end ≥ start + 最短，且為整數倍
        dur_min = max(0, start_qt.secsTo(end_qt) // 60)
        step = self.STEP_MIN
        if dur_min <= 0:
            dur_min = step
        else:
            if dur_min % step != 0:
                dur_min = int(math.ceil(dur_min / step) * step)

        fixed_end = start_qt.addSecs(dur_min * 60)
        if fixed_end != end_qt:
            self.end_time_input.blockSignals(True)
            self.end_time_input.setText(fixed_end.toString("HH:mm"))
            self.end_time_input.blockSignals(False)

        self._end_manually_set = True
        self._info("")
        self._set_duration_safely(dur_min / 60.0)


    def _on_duration_changed(self, new_hours: float):
        """調整『持續時間（小時）』→ 以開始時間推結束，結束對齊粒度。"""
        start_qt = self.parse_time(self.start_time_input.text())
        if not start_qt:
            return

        # 小時 → 秒 → 推算新的結束時間，並以步長對齊
        dur_min = int(round(float(new_hours) * 60))
        # 保底最短 & 對齊步長（向上取整）
        dur_min = max(self.STEP_MIN, int(math.ceil(dur_min / self.STEP_MIN) * self.STEP_MIN))

        end_qt = start_qt.addSecs(dur_min * 60)

        self._end_manually_set = False  # 之後改『開始』會跟著跑
        self.end_time_input.blockSignals(True)
        self.end_time_input.setText(end_qt.toString("HH:mm"))
        self.end_time_input.blockSignals(False)

    def _apply_min_lead_on_start(self, adjust_end_if_needed: bool) -> QTime | None:
        if self.date_input.date() != QDate.currentDate():
            return None
        start_qt = self.parse_time(self.start_time_input.text())
        if not start_qt:
            return None

        start_dt = QDateTime(self.date_input.date(), QTime(start_qt.hour(), start_qt.minute(), 0))
        now_dt = QDateTime.currentDateTime()
        min_start = ceil_to_next_minute(now_dt.addSecs(self.MIN_LEAD_SECONDS))
        if start_dt < min_start:
            fixed_qt = min_start.time()  # ← 僅整分，不做 15 分進位
            self.start_time_input.setText(fixed_qt.toString("HH:mm"))
            self._warn(f"⚠️ 開始時間太接近現在，已自動調整為 {fixed_qt.toString('HH:mm')}")
            if adjust_end_if_needed:
                dur_min = int(round(self.duration_input.value() * 60))
                dur_min = max(self.STEP_MIN, int(math.ceil(dur_min / self.STEP_MIN) * self.STEP_MIN))
                end_qt = fixed_qt.addSecs(dur_min * 60)
                self.end_time_input.setText(end_qt.toString("HH:mm"))
            return fixed_qt
        return None


    # ---------- 訊息 ----------
    def _error(self, msg: str):
        self.status_label.setText(msg)
        self.status_label.setStyleSheet("color: red")

    def _warn(self, msg: str):
        self.status_label.setText(msg)
        self.status_label.setStyleSheet("color: orange")

    def _info(self, msg: str):
        self.status_label.setText(msg)
        self.status_label.setStyleSheet("color: green" if msg else "")

    def _set_duration_safely(self, hours_val: float):
        """避免 valueChanged 迴圈觸發時造成抖動，並強迫對齊步長。"""
        # 對齊步長（向上取整）
        step_h = MIN_DURATION_HOURS
        hours_val = max(step_h, round(math.ceil((hours_val / step_h)) * step_h, 6))
        old = float(self.duration_input.value())
        if abs(old - hours_val) >= 1e-6:
            self.duration_input.blockSignals(True)
            self.duration_input.setValue(min(24.0, hours_val))
            self.duration_input.blockSignals(False)

    # ---------- OK ----------
    def accept(self):
        name = self.name_input.text().strip()
        if not name:
            self._error("❌ 節目名稱不能空白")
            return

        # 解析 + 格式化（不做 15 分進位）
        start_qt = self._normalize_time_field(self.start_time_input, ceil_to_step=False)
        if not start_qt:
            self._error("❌ 請輸入正確的開始時間")
            return

        end_qt = self._normalize_time_field(self.end_time_input, ceil_to_step=False)
        if not end_qt:
            self._error("❌ 請輸入正確的結束時間")
            return

        qdate = self.date_input.date()
        start_dt = QDateTime(qdate, QTime(start_qt.hour(), start_qt.minute(), 0))
        end_dt   = QDateTime(qdate, QTime(end_qt.hour(), end_qt.minute(), 0))
        now_dt   = QDateTime.currentDateTime()

        # 今日：最小提前（只整分）
        if qdate == now_dt.date():
            min_start = ceil_to_next_minute(now_dt.addSecs(self.MIN_LEAD_SECONDS))
            if start_dt < min_start:
                fixed_qt = min_start.time()
                self.start_time_input.setText(fixed_qt.toString("HH:mm"))
                self._warn(f"⚠️ 開始時間太接近現在，已自動調整為 {fixed_qt.toString('HH:mm')}")
                start_dt = QDateTime(qdate, fixed_qt)
                start_qt = fixed_qt
                if not self._end_manually_set:
                    dur_min = int(round(self.duration_input.value() * 60))
                    dur_min = max(self.STEP_MIN, int(math.ceil(dur_min / self.STEP_MIN) * self.STEP_MIN))
                    end_dt = start_dt.addSecs(dur_min * 60)
                    self.end_time_input.setText(end_dt.time().toString("HH:mm"))

        if start_dt < now_dt:
            self._error("❌ 無法新增過去的行程")
            return

        if end_dt <= start_dt:
            end_dt = start_dt.addSecs(self.STEP_MIN * 60)
            self.end_time_input.setText(end_dt.time().toString("HH:mm"))

        # 以步長修正 duration 與 end（確保整數倍）
        dur_min = (start_dt.secsTo(end_dt)) // 60
        if dur_min % self.STEP_MIN != 0:
            dur_min = int(math.ceil(dur_min / self.STEP_MIN) * self.STEP_MIN)
            end_dt = start_dt.addSecs(dur_min * 60)
            self.end_time_input.setText(end_dt.time().toString("HH:mm"))

        dur_hours = dur_min / 60.0
        self._set_duration_safely(dur_hours)

        encoder_name = self.encoder_selector.currentData()
        try:
            track_index = self.encoder_names.index(encoder_name) if encoder_name in self.encoder_names else 0
        except Exception:
            track_index = 0

        start_hour_float = (start_qt.hour() * 60 + start_qt.minute()) / 60.0
        if self.overlap_checker and self.overlap_checker(qdate, track_index, start_hour_float, dur_hours):
            self._error("⚠️ 時間重疊")
            return

        self.parsed_start_time = start_qt
        self.parsed_end_time = end_dt.time()
        super().accept()


    def get_values(self):
        """回傳：name, date, start_qtime, duration_hours, encoder_name, end_qtime"""
        return (
            self.name_input.text().strip(),
            self.date_input.date(),
            self.parsed_start_time,             # QTime
            float(self.duration_input.value()), # 小時（已與步長對齊）
            self.encoder_selector.currentData(),
            self.parsed_end_time,               # QTime
        )
