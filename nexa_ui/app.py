"""
NEXA UI - Main window and entry point

Run with:
    python3 app.py

Sidebar navigation + stacked screens. The Session screen is only reachable
once a session has been opened for a participant.
"""

import sys

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QFrame,
    QPushButton, QStackedWidget, QLabel, QButtonGroup, QMessageBox, QShortcut,
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
        self.ui_scale = config.UI_SCALE_DEFAULT
        self.setWindowTitle("NEXA")
        self.resize(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
        self.setMinimumSize(config.MIN_WINDOW_WIDTH, config.MIN_WINDOW_HEIGHT)

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # -- sidebar -------------------------------------------------------
        self.sidebar = QFrame()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(180)
        side_layout = QVBoxLayout(self.sidebar)
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

        zoom_row = QHBoxLayout()
        zoom_row.setContentsMargins(4, 0, 4, 8)
        zoom_out_btn = QPushButton("-")
        zoom_out_btn.setFixedWidth(32)
        zoom_out_btn.setToolTip("Zoom out (Ctrl+-)")
        zoom_out_btn.clicked.connect(self.zoom_out)
        self.zoom_reset_btn = QPushButton("100%")
        self.zoom_reset_btn.setFixedWidth(50)
        self.zoom_reset_btn.setToolTip("Reset zoom (Ctrl+0)")
        self.zoom_reset_btn.clicked.connect(self.reset_zoom)
        zoom_in_btn = QPushButton("+")
        zoom_in_btn.setFixedWidth(32)
        zoom_in_btn.setToolTip("Zoom in (Ctrl++)")
        zoom_in_btn.clicked.connect(self.zoom_in)
        zoom_row.addWidget(zoom_out_btn)
        zoom_row.addWidget(self.zoom_reset_btn, 1)
        zoom_row.addWidget(zoom_in_btn)
        side_layout.addLayout(zoom_row)

        quit_btn = QPushButton("Exit")
        quit_btn.setObjectName("NavItem")
        quit_btn.clicked.connect(self.close)
        side_layout.addWidget(quit_btn)

        root.addWidget(self.sidebar)

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

        self.zoom_shortcuts = []
        for sequence, handler in (
                ("Ctrl++", self.zoom_in), ("Ctrl+=", self.zoom_in),
                ("Ctrl+-", self.zoom_out), ("Ctrl+0", self.reset_zoom)):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.setContext(Qt.ApplicationShortcut)
            shortcut.activated.connect(handler)
            self.zoom_shortcuts.append(shortcut)

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

    # -- display ----------------------------------------------------------

    def set_zoom(self, scale):
        scale = max(config.UI_SCALE_MIN, min(config.UI_SCALE_MAX, scale))
        self.ui_scale = round(scale, 2)
        QApplication.instance().setStyleSheet(
            theme.scaled_stylesheet(self.ui_scale)
        )
        self.sidebar.setFixedWidth(round(180 * self.ui_scale))
        self.zoom_reset_btn.setText(f"{round(self.ui_scale * 100)}%")

    def zoom_in(self):
        self.set_zoom(self.ui_scale + config.UI_SCALE_STEP)

    def zoom_out(self):
        self.set_zoom(self.ui_scale - config.UI_SCALE_STEP)

    def reset_zoom(self):
        self.set_zoom(config.UI_SCALE_DEFAULT)

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
        if event.modifiers() & Qt.ControlModifier:
            if event.key() in (Qt.Key_Plus, Qt.Key_Equal):
                self.zoom_in()
                return
            if event.key() == Qt.Key_Minus:
                self.zoom_out()
                return
            if event.key() == Qt.Key_0:
                self.reset_zoom()
                return
        super().keyPressEvent(event)


def main():
    config.ensure_dirs()

    app = QApplication(sys.argv)
    app.setStyleSheet(theme.scaled_stylesheet(config.UI_SCALE_DEFAULT))
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
