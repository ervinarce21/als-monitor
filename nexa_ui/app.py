"""
NEXA UI - Main window and entry point

Run with:
    python3 app.py

Sidebar navigation + stacked screens. The Session screen is only reachable
once a session has been opened for a participant.
"""

import sys

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QFrame,
    QPushButton, QStackedWidget, QLabel, QButtonGroup, QMessageBox,
)

import config
import theme
from database import Database
from screens import (
    HomeScreen, ParticipantsScreen, SessionScreen, HistoryScreen,
    SystemCheckScreen,
)


NAV_ITEMS = [
    ("home", "Home"),
    ("participants", "Participants"),
    ("session", "Session"),
    ("history", "History"),
    ("system", "System"),
]


class MainWindow(QMainWindow):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self.setWindowTitle("NEXA")
        self.resize(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # -- sidebar -------------------------------------------------------
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(180)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(0, 20, 0, 12)
        side_layout.setSpacing(0)

        brand = QLabel("  NEXA")
        brand.setObjectName("H2")
        side_layout.addWidget(brand)
        side_layout.addSpacing(20)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons = {}
        for key, label in NAV_ITEMS:
            btn = QPushButton(label)
            btn.setObjectName("NavItem")
            btn.setCheckable(True)
            btn.clicked.connect(lambda _, k=key: self.navigate(k))
            side_layout.addWidget(btn)
            self.nav_group.addButton(btn)
            self.nav_buttons[key] = btn

        side_layout.addStretch()

        quit_btn = QPushButton("Exit")
        quit_btn.setObjectName("NavItem")
        quit_btn.clicked.connect(self.close)
        side_layout.addWidget(quit_btn)

        root.addWidget(sidebar)

        # -- screens -------------------------------------------------------
        self.stack = QStackedWidget()
        self.screens = {}

        self.home = HomeScreen(db)
        self.home.navigate.connect(self.navigate)

        self.participants = ParticipantsScreen(db)
        self.participants.session_started.connect(self._on_session_started)

        self.session = SessionScreen(db)
        self.session.session_ended.connect(self._on_session_ended)

        self.history = HistoryScreen(db)
        self.system = SystemCheckScreen(db)

        for key, screen in (("home", self.home),
                            ("participants", self.participants),
                            ("session", self.session),
                            ("history", self.history),
                            ("system", self.system)):
            self.screens[key] = screen
            self.stack.addWidget(screen)

        root.addWidget(self.stack, 1)

        self.nav_buttons["session"].setEnabled(False)
        self.navigate("home")

    # -- navigation -------------------------------------------------------

    def navigate(self, key):
        screen = self.screens.get(key)
        if screen is None:
            return
        if key == "session" and self.session.session_id is None:
            QMessageBox.information(
                self, "No active session",
                "Start a session from the Participants screen first."
            )
            return
        if hasattr(screen, "refresh"):
            screen.refresh()
        self.stack.setCurrentWidget(screen)
        btn = self.nav_buttons.get(key)
        if btn:
            btn.setChecked(True)

    def _on_session_started(self, session_id):
        self.session.load_session(session_id)
        self.nav_buttons["session"].setEnabled(True)
        self.navigate("session")

    def _on_session_ended(self):
        self.nav_buttons["session"].setEnabled(False)
        self.navigate("history")

    # -- lifecycle -------------------------------------------------------

    def closeEvent(self, event):
        if self.session.session_id is not None:
            reply = QMessageBox.question(
                self, "Session in progress",
                "A session is still open. Exit anyway? The session stays open "
                "and can be ended later from its record.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                event.ignore()
                return
        self.db.close()
        super().closeEvent(event)

    def keyPressEvent(self, event):
        # F11 toggles fullscreen; useful when developing on a desktop.
        if event.key() == Qt.Key_F11:
            if self.isFullScreen():
                self.showNormal()
            else:
                self.showFullScreen()
            return
        super().keyPressEvent(event)


def main():
    config.ensure_dirs()

    app = QApplication(sys.argv)
    app.setStyleSheet(theme.STYLESHEET)
    if config.HIDE_CURSOR:
        app.setOverrideCursor(Qt.BlankCursor)

    try:
        db = Database()
    except Exception as e:
        QMessageBox.critical(None, "Database error",
                             f"Could not open the NEXA database:\n{e}")
        return 1

    window = MainWindow(db)
    if config.FULLSCREEN:
        window.showFullScreen()
    else:
        window.show()

    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())