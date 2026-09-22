from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from ..paths import ensure_data_layout, save_root_pointer
from ..security import AuthStore


class SetupDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Set up eRegistry")
        self.setMinimumWidth(560)
        self.root: Path | None = None
        self.master_key: bytes | None = None
        self.recovery_key = ""
        layout = QVBoxLayout(self)
        title = QLabel("Welcome to eRegistry")
        title.setStyleSheet("font-size: 20pt; font-weight: 700")
        layout.addWidget(title)
        layout.addWidget(
            QLabel("Choose the main data folder and create the single-user application password.")
        )
        form = QFormLayout()
        folder_row = QHBoxLayout()
        self.folder = QLineEdit()
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        folder_row.addWidget(self.folder)
        folder_row.addWidget(browse)
        form.addRow("Main data folder", folder_row)
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.confirm = QLineEdit()
        self.confirm.setEchoMode(QLineEdit.Password)
        form.addRow("Password", self.password)
        form.addRow("Confirm password", self.confirm)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.button(QDialogButtonBox.Ok).setText("Create eRegistry")
        buttons.accepted.connect(self._submit)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose eRegistry data folder")
        if folder:
            self.folder.setText(folder)

    def _submit(self):
        root = Path(self.folder.text()).expanduser()
        if not self.folder.text().strip():
            QMessageBox.warning(self, "Missing folder", "Choose a main data folder.")
            return
        if self.password.text() != self.confirm.text():
            QMessageBox.warning(self, "Password mismatch", "The passwords do not match.")
            return
        try:
            ensure_data_layout(root)
            auth = AuthStore(root / "auth.json")
            self.master_key, self.recovery_key = auth.setup(self.password.text())
            save_root_pointer(root)
            self.root = root
        except Exception as exc:
            QMessageBox.critical(self, "Setup failed", str(exc))
            return
        dlg = RecoveryKeyDialog(self.recovery_key, self)
        if dlg.exec() != QDialog.Accepted:
            QMessageBox.warning(
                self, "Recovery key", "You must confirm that the recovery key has been saved."
            )
            return
        self.accept()


class RecoveryKeyDialog(QDialog):
    def __init__(self, key: str, parent=None):
        super().__init__(parent)
        self.key = key
        self.setWindowTitle("Save your recovery key")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "This key is the only offline way to reset a forgotten password. Save or print it now."
            )
        )
        key_label = QLabel(key)
        key_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        key_label.setStyleSheet(
            "font-family: Consolas; font-size: 14pt; font-weight: 700; padding: 16px; border: 1px solid #888"
        )
        layout.addWidget(key_label)
        save = QPushButton("Save recovery key…")
        save.clicked.connect(self._save)
        layout.addWidget(save)
        self.confirm = QCheckBox("I have safely saved or printed this recovery key")
        layout.addWidget(self.confirm)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        buttons.accepted.connect(self._accept)
        layout.addWidget(buttons)

    def _save(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save recovery key", "eRegistry-Recovery-Key.txt", "Text files (*.txt)"
        )
        if path:
            Path(path).write_text(f"eRegistry recovery key\n\n{self.key}\n", encoding="utf-8")

    def _accept(self):
        if not self.confirm.isChecked():
            QMessageBox.warning(
                self, "Confirmation required", "Confirm that you saved the recovery key."
            )
            return
        self.accept()


class LoginDialog(QDialog):
    def __init__(self, auth: AuthStore, parent=None, lock_mode=False):
        super().__init__(parent)
        self.auth = auth
        self.master_key = None
        self.setWindowTitle("eRegistry locked" if lock_mode else "Sign in to eRegistry")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        title = QLabel("eRegistry")
        title.setStyleSheet("font-size: 24pt; font-weight: 700")
        layout.addWidget(title)
        layout.addWidget(QLabel("Enter the password to continue."))
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.password.returnPressed.connect(self._login)
        layout.addWidget(self.password)
        row = QHBoxLayout()
        login = QPushButton("Unlock" if lock_mode else "Sign in")
        login.clicked.connect(self._login)
        recover = QPushButton("Forgot password?")
        recover.setProperty("secondary", True)
        recover.clicked.connect(self._recover)
        row.addWidget(login)
        row.addWidget(recover)
        layout.addLayout(row)

    def _login(self):
        try:
            self.master_key = self.auth.unlock(self.password.text())
        except Exception as exc:
            QMessageBox.warning(self, "Unable to unlock", str(exc))
            return
        self.accept()

    def _recover(self):
        dialog = PasswordResetDialog(self.auth, self)
        if dialog.exec() == QDialog.Accepted:
            self.master_key = dialog.master_key
            self.accept()


class PasswordResetDialog(QDialog):
    def __init__(self, auth, parent=None):
        super().__init__(parent)
        self.auth = auth
        self.master_key = None
        self.setWindowTitle("Reset password")
        form = QFormLayout(self)
        self.key = QLineEdit()
        self.password = QLineEdit()
        self.confirm = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.confirm.setEchoMode(QLineEdit.Password)
        form.addRow("Recovery key", self.key)
        form.addRow("New password", self.password)
        form.addRow("Confirm", self.confirm)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.accepted.connect(self._submit)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _submit(self):
        if self.password.text() != self.confirm.text():
            QMessageBox.warning(self, "Mismatch", "The passwords do not match.")
            return
        try:
            self.master_key = self.auth.reset_with_recovery(self.key.text(), self.password.text())
        except Exception as exc:
            QMessageBox.warning(self, "Reset failed", str(exc))
            return
        self.accept()


class OrganisationDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create organisation database")
        self.values = None
        form = QFormLayout(self)
        self.name = QLineEdit()
        self.address = QTextEdit()
        self.address.setMaximumHeight(80)
        self.contact = QLineEdit()
        self.phone = QLineEdit()
        self.email = QLineEdit()
        form.addRow("Organisation name*", self.name)
        form.addRow("Address", self.address)
        form.addRow("Contact person", self.contact)
        form.addRow("Phone", self.phone)
        form.addRow("Email", self.email)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.accepted.connect(self._submit)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _submit(self):
        if not self.name.text().strip():
            QMessageBox.warning(self, "Required", "Organisation name is required.")
            return
        self.values = {
            "name": self.name.text(),
            "address": self.address.toPlainText(),
            "contact_person": self.contact.text(),
            "phone": self.phone.text(),
            "email": self.email.text(),
        }
        self.accept()
