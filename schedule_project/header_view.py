from PySide6.QtWidgets import QGraphicsView, QGraphicsScene
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QFont

class HeaderView(QGraphicsView):
    def __init__(self, encoder_names, hour_width=20, days=7):
        super().__init__()
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.encoder_names = encoder_names
        self.hour_width = hour_width
        self.days = days
        self.day_width = 24 * hour_width
        self.setFixedHeight(80)  # header 高度拉高顯示日期
        self.setSceneRect(-120, 0, self.days * self.day_width + 150, 110)  # sceneRect 對應拉高

        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.base_date = QDate.currentDate()  # ✅ 一定要先定義
        self.draw_header()

    def draw_header(self):
        self.scene.clear()
        for day in range(self.days):
            x = day * self.day_width

            # 日期列（上方）
            date_label = self.scene.addText(self.base_date.addDays(day).toString("MM/dd (ddd)"))
            date_label.setFont(QFont("Arial", 9, QFont.Bold))
            date_label.setPos(x + 2, 40)  # 微調日期顯示位置

            # 小時刻度
            for hour in range(24):
                xh = day * self.day_width + hour * self.hour_width
                hour_label = self.scene.addText(f"{hour:02d}")
                hour_label.setFont(QFont("Arial", 8))
                hour_label.setPos(xh - hour_label.boundingRect().width() / 2, 25)  # 時間下移對應新高度

    def set_base_date(self, qdate):
        self.base_date = qdate
        self.draw_header()
        self.update() 
    def sync_scroll(self, value):
        self.horizontalScrollBar().setValue(value)
