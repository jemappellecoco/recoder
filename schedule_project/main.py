from PySide6.QtWidgets import QApplication
import sys
from ui_main_window import MainWindow

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    # win.showFullScreen()
    sys.exit(app.exec())
