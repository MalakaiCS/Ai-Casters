"""The boot sign-in window shown before the main app.

Accounts are required, so the application gates on authentication: on launch we
try to restore a saved session and, if there isn't one, show this window. It
offers three flows — sign in, create account, and forgot password — over the
:class:`~ai_caster.auth.client.AuthClient`. Network calls run on a worker thread
so the window never freezes; results are marshalled back via Qt signals.

The dialog is *accepted* only once a real session exists, so a build with no
configured account service (the unconfigured backend) simply reports that and
never lets a fake login through.
"""

from __future__ import annotations

import threading

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ai_caster import __brand__, __tagline__
from ai_caster.auth.client import AuthClient
from ai_caster.ui.branding import app_icon, logo_pixmap

_SIGN_IN, _SIGN_UP, _FORGOT = 0, 1, 2


class AuthWindow(QDialog):
    """A modal boot window: sign in, create account, or reset a password."""

    # (accepted, message) — accepted True closes the dialog into the app.
    _result = Signal(bool, str)

    def __init__(self, auth: AuthClient) -> None:
        super().__init__()
        self._auth = auth
        self._busy = False

        self.setWindowTitle(f"{__brand__} — Sign in")
        self.setWindowIcon(app_icon())
        self.setModal(True)
        self.setMinimumWidth(420)

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 28)
        root.setSpacing(12)

        pixmap = logo_pixmap(200)
        if not pixmap.isNull():
            logo = QLabel()
            logo.setPixmap(pixmap)
            logo.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            root.addWidget(logo)

        tagline = QLabel(__tagline__)
        tagline.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        tagline.setStyleSheet("color: #888;")
        root.addWidget(tagline)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_sign_in())
        self._stack.addWidget(self._build_sign_up())
        self._stack.addWidget(self._build_forgot())
        root.addWidget(self._stack)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        root.addWidget(self._status)

        self._result.connect(self._on_result)
        self._show_page(_SIGN_IN)

    # ------------------------------------------------------------------ #
    # Pages
    # ------------------------------------------------------------------ #
    def _build_sign_in(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        self._in_email = QLineEdit()
        self._in_email.setPlaceholderText("email")
        self._in_password = QLineEdit()
        self._in_password.setPlaceholderText("password")
        self._in_password.setEchoMode(QLineEdit.EchoMode.Password)
        self._in_password.returnPressed.connect(self._on_sign_in)
        self._in_button = QPushButton("Sign in")
        self._in_button.setDefault(True)
        self._in_button.clicked.connect(self._on_sign_in)

        create = QPushButton("Create an account")
        create.setFlat(True)
        create.clicked.connect(lambda: self._show_page(_SIGN_UP))
        forgot = QPushButton("Forgot password?")
        forgot.setFlat(True)
        forgot.clicked.connect(lambda: self._show_page(_FORGOT))

        for widget in (self._in_email, self._in_password, self._in_button, create, forgot):
            layout.addWidget(widget)
        return page

    def _build_sign_up(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        self._up_email = QLineEdit()
        self._up_email.setPlaceholderText("email")
        self._up_password = QLineEdit()
        self._up_password.setPlaceholderText("password (at least 8 characters)")
        self._up_password.setEchoMode(QLineEdit.EchoMode.Password)
        self._up_confirm = QLineEdit()
        self._up_confirm.setPlaceholderText("confirm password")
        self._up_confirm.setEchoMode(QLineEdit.EchoMode.Password)
        self._up_confirm.returnPressed.connect(self._on_sign_up)
        self._up_button = QPushButton("Create account")
        self._up_button.clicked.connect(self._on_sign_up)

        back = QPushButton("Back to sign in")
        back.setFlat(True)
        back.clicked.connect(lambda: self._show_page(_SIGN_IN))

        for widget in (
            self._up_email,
            self._up_password,
            self._up_confirm,
            self._up_button,
            back,
        ):
            layout.addWidget(widget)
        return page

    def _build_forgot(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        prompt = QLabel("Enter your email and we'll send a password-reset link.")
        prompt.setWordWrap(True)
        self._fg_email = QLineEdit()
        self._fg_email.setPlaceholderText("email")
        self._fg_email.returnPressed.connect(self._on_forgot)
        self._fg_button = QPushButton("Send reset link")
        self._fg_button.clicked.connect(self._on_forgot)

        back = QPushButton("Back to sign in")
        back.setFlat(True)
        back.clicked.connect(lambda: self._show_page(_SIGN_IN))

        for widget in (prompt, self._fg_email, self._fg_button, back):
            layout.addWidget(widget)
        return page

    # ------------------------------------------------------------------ #
    # Navigation / state
    # ------------------------------------------------------------------ #
    def _show_page(self, index: int) -> None:
        self._status.setText("")
        self._stack.setCurrentIndex(index)

    def _set_busy(self, busy: bool, message: str = "") -> None:
        self._busy = busy
        for button in (self._in_button, self._up_button, self._fg_button):
            button.setEnabled(not busy)
        if message:
            self._status.setStyleSheet("color: #888;")
            self._status.setText(message)

    def _fail(self, message: str) -> None:
        self._status.setStyleSheet("color: #c0392b;")
        self._status.setText(message)

    # ------------------------------------------------------------------ #
    # Actions (network on a worker thread)
    # ------------------------------------------------------------------ #
    def _on_sign_in(self) -> None:
        if self._busy:
            return
        email = self._in_email.text().strip()
        password = self._in_password.text()
        self._set_busy(True, "Signing in…")
        threading.Thread(
            target=self._run_sign_in, args=(email, password), name="auth-signin", daemon=True
        ).start()

    def _run_sign_in(self, email: str, password: str) -> None:
        ok = self._auth.login(email, password)
        if ok:
            self._result.emit(True, "")
        else:
            self._result.emit(False, "Invalid email or password.")

    def _on_sign_up(self) -> None:
        if self._busy:
            return
        email = self._up_email.text().strip()
        password = self._up_password.text()
        if password != self._up_confirm.text():
            self._fail("Passwords don't match.")
            return
        self._set_busy(True, "Creating your account…")
        threading.Thread(
            target=self._run_sign_up, args=(email, password), name="auth-signup", daemon=True
        ).start()

    def _run_sign_up(self, email: str, password: str) -> None:
        result = self._auth.signup(email, password)
        if result.ok and result.session is not None:
            self._result.emit(True, "")
        elif result.ok:
            self._result.emit(False, "Account created — check your email to confirm, then sign in.")
        else:
            self._result.emit(False, result.error or "Sign-up failed.")

    def _on_forgot(self) -> None:
        if self._busy:
            return
        email = self._fg_email.text().strip()
        self._set_busy(True, "Sending…")
        threading.Thread(
            target=self._run_forgot, args=(email,), name="auth-recover", daemon=True
        ).start()

    def _run_forgot(self, email: str) -> None:
        result = self._auth.recover(email)
        if result.ok:
            self._result.emit(False, "If that email has an account, a reset link is on its way.")
        else:
            self._result.emit(False, result.error or "Couldn't send a reset link.")

    # ------------------------------------------------------------------ #
    # Result (Qt thread)
    # ------------------------------------------------------------------ #
    def _on_result(self, accepted: bool, message: str) -> None:
        self._set_busy(False)
        if accepted:
            self.accept()
            return
        # A confirmation/reset message is informational; a real failure is an error.
        if message.startswith(("Account created", "If that email")):
            self._show_page(_SIGN_IN)
            self._status.setStyleSheet("color: #2d7d46;")
            self._status.setText(message)
        else:
            self._fail(message)


def require_sign_in(auth: AuthClient) -> bool:
    """Show the boot sign-in window unless a session was already restored.

    Returns True if the app should proceed (the user is authenticated), or False
    if the window was dismissed without signing in (the app should exit).
    """
    if auth.is_authenticated:
        return True
    window = AuthWindow(auth)
    return window.exec() == QDialog.DialogCode.Accepted
