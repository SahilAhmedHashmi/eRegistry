from __future__ import annotations

import sys

from PySide6.QtCore import QEvent, QObject, QTimer
from PySide6.QtWidgets import QApplication, QDialog

from .app_state import AppContext
from .paths import load_root_pointer
from .security import AuthStore
from .ui.dialogs import LoginDialog, SetupDialog
from .ui.main_window import MainWindow
from .ui.theme import DARK, LIGHT


class IdleLock(QObject):
    def __init__(self, app, auth, context, window):
        super().__init__()
        self.app = app
        self.auth = auth
        self.context = context
        self.window = window
        self.locking = False
        self.timer = QTimer(self)
        self.timer.setInterval(15 * 60 * 1000)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.lock)
        self.timer.start()
        app.installEventFilter(self)

    def eventFilter(self, watched, event):
        if (
            event.type()
            in {QEvent.MouseButtonPress, QEvent.KeyPress, QEvent.Wheel, QEvent.TouchBegin}
            and not self.locking
        ):
            self.timer.start()
        return False

    def lock(self):
        if self.locking:
            return
        self.locking = True
        self.window.hide()
        dialog = LoginDialog(self.auth, lock_mode=True)
        if dialog.exec() == QDialog.Accepted:
            self.context.master_key = dialog.master_key
            self.window.show()
            self.window.raise_()
            self.timer.start()
            self.locking = False
        else:
            self.app.quit()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("eRegistry")
    app.setOrganizationName("eRegistry")
    root = load_root_pointer()
    if not root or not (root / "auth.json").exists():
        setup = SetupDialog()
        if setup.exec() != QDialog.Accepted:
            return 0
        root, master_key = setup.root, setup.master_key
    else:
        auth = AuthStore(root / "auth.json")
        login = LoginDialog(auth)
        if login.exec() != QDialog.Accepted:
            return 0
        master_key = login.master_key
    auth = AuthStore(root / "auth.json")
    context = AppContext(root, master_key)
    window = MainWindow(context)
    theme = window.settings.value("theme", "Light")
    app.setStyleSheet(DARK if theme == "Dark" else LIGHT)
    lock = IdleLock(app, auth, context, window)

    def logout():
        window.hide()
        login = LoginDialog(auth)
        if login.exec() == QDialog.Accepted:
            context.master_key = login.master_key
            if context.organisation:
                context.open_organisation(context.organisation)
            window.show()
            lock.timer.start()
        else:
            app.quit()

    window.logout_requested.connect(logout)
    window.show()
    QTimer.singleShot(1000, window.maybe_weekly_backup_reminder)
    result = app.exec()
    context.close()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
