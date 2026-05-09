import sys

from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QDialog

from .dialogs import LoginDialog
from .shop_window import ShopWindow


def run() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("ShopManager")
    app.setFont(QFont("Tahoma", 9))

    login = LoginDialog()
    if login.exec() != QDialog.DialogCode.Accepted:
        return 0

    window = ShopWindow(login.connection, login.game_directory or "")
    window.show()
    return app.exec()
