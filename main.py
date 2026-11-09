"""Teamspeak Heerlen PC entrypoint."""
import sys
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QSplashScreen
from heerlen.ui import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Teamspeak Heerlen PC")
    app.setOrganizationName("Teamspeak Heerlen")
    app.setStyle("Fusion")
    window = MainWindow()

    splash_pix = QPixmap(620, 300)
    splash_pix.fill(Qt.GlobalColor.transparent)
    splash = QSplashScreen(splash_pix)
    splash.setStyleSheet("background:#06182d;color:#16d6ff;border:2px solid #16d6ff")
    splash.showMessage(
        "TEAMSPEAK HEERLEN PC\n\nWINDOWS EDITION\n\nLaden...",
        Qt.AlignmentFlag.AlignCenter,
        Qt.GlobalColor.cyan,
    )
    splash.show()
    app.processEvents()

    def reveal():
        window.show()
        splash.finish(window)

    QTimer.singleShot(1250, reveal)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
