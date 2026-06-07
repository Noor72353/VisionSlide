from __future__ import annotations

import sqlite3
from pathlib import Path

from PySide6.QtCore import QEvent, QEasingCurve, QPropertyAnimation, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QStandardItem,
    QStandardItemModel,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QCompleter,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.auth import AuthManager
from app.brand_heading import BrandHeadingLabel
from app.config import AppConfig
from app.credential_store import CredentialStore
from app.email_service import EmailDeliveryError, EmailService
from app.hover_effects import attach_hover_bounce
from app.otp_service import OTPService
from app.runtime_paths import resource_path
from app.window_effects import enable_soft_window_transitions
from app.validators import (
    format_validation_message,
    get_password_strength_feedback,
    normalize_username,
    validate_confirm_password,
    validate_email,
    validate_password,
    validate_username,
)


class LoginIdentityCompleter(QCompleter):
    def pathFromIndex(self, index) -> str:
        identity = index.data(Qt.UserRole)
        if identity:
            return str(identity)
        return super().pathFromIndex(index)


class LoginIdentityDelegate(QStyledItemDelegate):
    def __init__(self, admin_emails: set[str] | None = None, parent=None):
        super().__init__(parent)
        self.admin_emails = {str(email).strip().lower() for email in (admin_emails or set()) if str(email).strip()}

    def paint(self, painter, option, index) -> None:
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        rect = option.rect.adjusted(2, 2, -2, -2)
        is_selected = bool(option.state & QStyle.State_Selected)
        is_hovered = bool(option.state & QStyle.State_MouseOver)

        if is_selected:
            painter.setBrush(QColor("#bfe0ea"))
            painter.setPen(QPen(QColor("#4f8ea1"), 1))
            painter.drawRoundedRect(rect.adjusted(0, 0, -1, -1), 8, 8)
            text_color = QColor("#15394b")
        elif is_hovered:
            painter.setBrush(QColor("#d3eaf1"))
            painter.setPen(QPen(QColor("#4f8ea1"), 1))
            painter.drawRoundedRect(rect.adjusted(0, 0, -1, -1), 8, 8)
            text_color = QColor("#15394b")
        else:
            painter.setPen(Qt.NoPen)
            text_color = QColor("#173543")

        badge_size = 24
        badge_x = rect.left() + 8
        badge_y = rect.top() + max(0, (rect.height() - badge_size) // 2)
        badge_rect = QRect(badge_x, badge_y, badge_size, badge_size)
        identity_text = str(index.data(Qt.UserRole) or index.data())
        is_admin = identity_text.strip().lower() in self.admin_emails
        painter.setBrush(QColor("#edf5f8" if is_admin else "#eef5f8"))
        painter.setPen(QColor("#b8d2df" if is_admin else "#d6e2ea"))
        if is_admin:
            painter.drawRoundedRect(badge_rect, 8, 8)
        else:
            painter.drawEllipse(badge_rect)

        painter.setPen(QColor("#2d6478"))
        badge_font = painter.font()
        badge_font.setPointSize(10)
        badge_font.setBold(True)
        painter.setFont(badge_font)
        painter.drawText(badge_rect, Qt.AlignCenter, "\U0001F464")

        text_rect = rect.adjusted(40, 0, -8, 0)
        painter.setPen(text_color)
        text_font = painter.font()
        text_font.setPointSize(10)
        text_font.setBold(False)
        painter.setFont(text_font)
        final_text_rect = text_rect.adjusted(0, 0, -74 if is_admin else 0, 0)
        painter.drawText(final_text_rect, Qt.AlignVCenter | Qt.AlignLeft, identity_text)

        if is_admin:
            badge_rect = QRect(rect.right() - 66, rect.top() + max(0, (rect.height() - 22) // 2), 58, 22)
            painter.setBrush(QColor("#edf5f8"))
            painter.setPen(QColor("#d8e6ee"))
            painter.drawRoundedRect(badge_rect, 10, 10)
            badge_font = painter.font()
            badge_font.setPointSize(8)
            badge_font.setBold(True)
            painter.setFont(badge_font)
            painter.setPen(QColor("#2c6275"))
            painter.drawText(badge_rect, Qt.AlignCenter, "Admin")

        painter.restore()


def required_label(text: str) -> QLabel:
    label = QLabel(f'{text} <span style="color:#c65649;">*</span>')
    label.setTextFormat(Qt.RichText)
    label.setIndent(8)
    return label


def centered_form_layout(form: QFormLayout) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.addStretch()
    row.addLayout(form)
    row.addStretch()
    return row


class RoundedAuthPanel(QFrame):
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect().adjusted(1, 1, -2, -2)
        path = QPainterPath()
        path.addRoundedRect(rect, 28, 28)

        painter.fillPath(path, QColor("#fbfdff"))
        painter.setPen(QPen(QColor("#dce7ed"), 1.2))
        painter.drawPath(path)


class RoundedAuthInnerPage(QWidget):
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect().adjusted(0, 0, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(rect, 22, 22)

        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        gradient.setColorAt(0, QColor("#d6edf3"))
        gradient.setColorAt(1, QColor("#b8d7e0"))
        painter.fillPath(path, gradient)


class LoginWindow(QDialog):
    login_succeeded = Signal()

    def __init__(self, auth_manager: AuthManager):
        super().__init__()
        self.auth_manager = auth_manager
        self.config = AppConfig()
        self.credential_store = CredentialStore()
        self.email_service = EmailService()
        self.otp_service = OTPService()
        self.authenticated_username: str | None = None
        self.assets_dir = resource_path("assets")
        self.field_errors: dict[str, QLabel] = {}
        self.field_controls: dict[str, QWidget] = {}
        self.field_inputs: dict[str, QLineEdit] = {}
        self.signup_verified_email = ""
        self.signup_verified_code = ""
        self.signup_failed_code = ""
        self.signup_last_otp_attempt = ""
        self.otp_resend_available = False
        self.otp_resend_seconds_remaining = 0
        self.otp_resend_timer = QTimer(self)
        self.otp_resend_timer.setInterval(1000)
        self.otp_resend_timer.timeout.connect(self._tick_otp_resend_cooldown)
        self.login_suggestion_popup: QWidget | None = None
        self.login_suggestion_close_button: QToolButton | None = None
        self.setWindowTitle("VisionSlide")
        self.setWindowIcon(QIcon(str(self.assets_dir / "visionslide_app_icon.svg")))
        self.setModal(True)
        self.setWindowFlag(Qt.WindowMinimizeButtonHint, True)
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.resize(1360, 820)
        self.setMinimumSize(1200, 760)
        self.setStyleSheet(
            """
            QDialog {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #4f8ea1, stop:1 #c7d1d6);
            }
            QWidget {
                font-family: "Segoe UI";
                color: #173543;
            }
            QFrame#authShell {
                background: transparent;
                border: none;
            }
            QFrame#formPanel {
                background: transparent;
                border: none;
            }
            QWidget[signinPage="true"] {
                background: transparent;
                border: none;
            }
            QStackedWidget {
                background: transparent;
            }
            QLabel[pageTitle="true"] {
                font-size: 30px;
                font-weight: 800;
                color: #173543;
            }
            QLabel[pageSubtitle="true"] {
                font-size: 13px;
                color: #5a7380;
            }
            QLabel[status="true"] {
                background: #fff3f0;
                border: 1px solid #f0cdc5;
                border-radius: 14px;
                padding: 11px 12px;
                color: #8b362f;
                font-size: 13px;
                font-weight: 700;
            }
            QLabel[success="true"] {
                background: #edf8f1;
                border: 1px solid #cbe6d2;
                border-radius: 14px;
                padding: 11px 12px;
                color: #1c5b34;
                font-size: 13px;
                font-weight: 700;
            }
            QLabel[fieldErrorLabel="true"] {
                color: #c65649;
                font-size: 11px;
                font-weight: 600;
                padding-left: 4px;
                margin-top: 2px;
            }
            QLabel[fieldSuccessLabel="true"] {
                color: #2b8a57;
                font-size: 11px;
                font-weight: 600;
                padding-left: 4px;
                margin-top: 2px;
            }
            QLineEdit {
                min-height: 42px;
                border-radius: 14px;
                border: 1px solid #cad7e1;
                background: #ffffff;
                padding: 8px 12px;
                color: #173543;
                font-size: 13px;
            }
            QLineEdit:focus {
                border-color: #8fb6cb;
                background: #fbfeff;
            }
            QFrame[inputShell="true"] {
                background: #ffffff;
                border: 1px solid #cad7e1;
                border-radius: 14px;
            }
            QFrame[inputShell="true"][fieldError="true"] {
                border-color: #d66f63;
                background: #fff8f6;
            }
            QFrame[inputShell="true"][fieldSuccess="true"] {
                border-color: #7cc497;
                background: #f6fcf8;
            }
            QLineEdit[fieldError="true"] {
                border-color: #d66f63;
                background: #fff8f6;
            }
            QLineEdit[fieldSuccess="true"] {
                border-color: #7cc497;
                background: #f6fcf8;
            }
            QPushButton {
                min-height: 42px;
                min-width: 140px;
                border-radius: 14px;
                border: 1px solid #ccd8e2;
                background: #ffffff;
                color: #173543;
                font-size: 13px;
                font-weight: 700;
                padding: 8px 14px;
            }
            QPushButton:hover {
                background: #f8fcff;
                border-color: #8fb6cb;
            }
            QPushButton:disabled {
                background: #f3f7fa;
                border-color: #d9e3ea;
                color: #95a7b2;
            }
            QPushButton[primary="true"] {
                background: #4f8ea1;
                border-color: #3f7c8f;
                color: #ffffff;
            }
            QPushButton[primary="true"]:hover {
                background: #5b9cb0;
                border-color: #4f8ea1;
            }
            QPushButton[secondary="true"] {
                background: #4f8ea1;
                border-color: #3f7c8f;
                color: #ffffff;
            }
            QPushButton[secondary="true"]:hover {
                background: #5b9cb0;
                border-color: #4f8ea1;
            }
            QPushButton[otpSmall="true"] {
                min-height: 34px;
                min-width: 96px;
                padding: 6px 10px;
                font-size: 12px;
            }
            QPushButton[textLink="true"] {
                min-height: 0px;
                min-width: 0px;
                padding: 0px;
                border: none;
                background: transparent;
                color: #2c6e82;
                font-size: 13px;
                font-weight: 700;
            }
            QPushButton[textLink="true"]:hover {
                background: transparent;
                border: none;
                color: #1f5c6d;
                text-decoration: underline;
            }
            QPushButton[textLink="true"]:disabled {
                background: transparent;
                border: none;
                color: #9aaab3;
            }
            QToolButton[passwordToggle="true"] {
                min-width: 30px;
                max-width: 30px;
                min-height: 30px;
                max-height: 30px;
                border: 1px solid transparent;
                background: transparent;
                padding: 0px;
                margin-right: 2px;
            }
            QToolButton[passwordToggle="true"]:hover {
                background: #edf6fa;
                border: 1px solid #cfdfe8;
                border-radius: 6px;
            }
            QToolButton[passwordToggle="true"]:checked {
                background: #e7f2f7;
                border: 1px solid #c7dae5;
                border-radius: 6px;
            }
            QToolTip {
                background: #ffffff;
                color: #173543;
                border: 1px solid #cad7e1;
                border-radius: 8px;
                padding: 4px 8px;
                font-size: 11px;
            }
            """
        )

        root_layout = QVBoxLayout()
        root_layout.setContentsMargins(12, 12, 12, 12)
        self.setLayout(root_layout)

        shell = QFrame()
        shell.setObjectName("authShell")
        shell_layout = QVBoxLayout()
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell.setLayout(shell_layout)
        root_layout.addWidget(shell)

        form_panel = self._build_form_panel()
        shell_layout.addStretch(1)
        center_row = QHBoxLayout()
        center_row.addStretch()
        center_row.addWidget(form_panel)
        center_row.addStretch()
        shell_layout.addLayout(center_row)
        shell_layout.addStretch(1)

        self._switch_page(0)
        self._refresh_login_completer()
        self._apply_clickable_cursors(self)
        QTimer.singleShot(0, self.signin_button.setFocus)

    def _apply_clickable_cursors(self, widget: QWidget) -> None:
        for child in widget.findChildren(QWidget):
            if isinstance(child, (QPushButton, QToolButton)):
                child.setCursor(Qt.PointingHandCursor)
                if isinstance(child, QPushButton) and child.property("textLink") == "true":
                    attach_hover_bounce(child, y_offset=1, duration=170)
                else:
                    attach_hover_bounce(child)
            elif isinstance(child, QCheckBox):
                child.setCursor(Qt.PointingHandCursor)
                attach_hover_bounce(child, y_offset=1, duration=170)
            elif isinstance(child, QAbstractItemView):
                child.setCursor(Qt.PointingHandCursor)
            elif isinstance(child, QLabel):
                label_text = child.text() or ""
                if "<a " in label_text.lower():
                    child.setTextInteractionFlags(Qt.TextBrowserInteraction | Qt.TextSelectableByMouse)
                    attach_hover_bounce(child)
                elif label_text.strip():
                    child.setTextInteractionFlags(Qt.TextSelectableByMouse)

    def _prepare_dialog_open_animation(self, dialog: QDialog) -> None:
        dialog.setProperty("skipFadeInTransition", True)
        dialog.setProperty("dialogOpeningHidden", "true")
        dialog.setWindowOpacity(0.0)
        dialog.installEventFilter(self)
        enable_soft_window_transitions(dialog, fade_in_ms=190, fade_out_ms=150)

    def _reveal_prepared_dialog(self, dialog: QDialog) -> None:
        if dialog.property("dialogOpeningHidden") != "true":
            return

        dialog.setProperty("dialogOpeningHidden", "false")
        animation = QPropertyAnimation(dialog, b"windowOpacity", dialog)
        animation.setDuration(210)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.finished.connect(lambda: dialog.setWindowOpacity(1.0))
        dialog._prepared_open_animation = animation
        animation.start()

    def _run_with_busy_button(self, button: QPushButton, busy_text: str, callback, restore_enabled: bool = True):
        original_text = button.text()
        original_enabled = button.isEnabled()
        button.setEnabled(False)
        button.setText(busy_text)
        QApplication.processEvents()
        try:
            return callback()
        finally:
            if button.text() == busy_text:
                button.setText(original_text)
            if restore_enabled:
                button.setEnabled(original_enabled)

    def _apply_primary_auth_button_style(self, button: QPushButton) -> None:
        button.setProperty("primary", "true")
        button.setStyleSheet(
            "QPushButton {"
            "min-height: 42px;"
            "min-width: 140px;"
            "border-radius: 14px;"
            "border: 1px solid #3f7c8f;"
            "background: #4f8ea1;"
            "color: #ffffff;"
            "font-size: 13px;"
            "font-weight: 700;"
            "padding: 8px 14px;"
            "}"
            "QPushButton:hover {"
            "background: #5b9cb0;"
            "border-color: #4f8ea1;"
            "}"
            "QPushButton:disabled {"
            "background: #f3f7fa;"
            "border-color: #d9e3ea;"
            "color: #95a7b2;"
            "}"
        )
        button.style().unpolish(button)
        button.style().polish(button)
        button.update()

    def _apply_signin_button_style(self) -> None:
        self.signin_button.setStyleSheet(
            "QPushButton {"
            "min-height: 42px;"
            "min-width: 140px;"
            "border-radius: 14px;"
            "border: 1px solid #3f7c8f;"
            "background: #4f8ea1;"
            "color: #ffffff;"
            "font-size: 13px;"
            "font-weight: 700;"
            "padding: 8px 14px;"
            "}"
            "QPushButton:hover {"
            "background: #5b9cb0;"
            "border-color: #4f8ea1;"
            "}"
            "QPushButton:disabled {"
            "background: #f3f7fa;"
            "border-color: #d9e3ea;"
            "color: #95a7b2;"
            "}"
        )
        self.signin_button.style().unpolish(self.signin_button)
        self.signin_button.style().polish(self.signin_button)
        self.signin_button.update()

    def _apply_auth_field_shell_style(self, field_shell: QFrame) -> None:
        field_shell.setStyleSheet(
            "QFrame {"
            "background: #ffffff;"
            "border: 1px solid #cad7e1;"
            "border-radius: 14px;"
            "}"
            "QFrame[fieldError=\"true\"] {"
            "background: #fff8f6;"
            "border-color: #d66f63;"
            "}"
            "QFrame[fieldSuccess=\"true\"] {"
            "background: #f6fcf8;"
            "border-color: #7cc497;"
            "}"
        )

    def _build_form_panel(self) -> QWidget:
        form_panel = RoundedAuthPanel()
        self.form_panel = form_panel
        form_panel.setObjectName("formPanel")
        form_panel.setFixedWidth(620)
        form_panel.setFixedHeight(620)

        layout = QVBoxLayout()
        layout.setContentsMargins(26, 22, 26, 22)
        layout.setSpacing(10)
        form_panel.setLayout(layout)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_sign_in_page())
        self.stack.addWidget(self._wrap_in_scroll(self._build_sign_up_page()))
        self.stack.addWidget(self._wrap_in_scroll(self._build_forgot_page()))

        layout.addWidget(self.stack, 1)
        layout.addSpacing(4)

        return form_panel

    def _build_sign_in_page(self) -> QWidget:
        page = RoundedAuthInnerPage()
        self.signin_page = page
        page.setProperty("signinPage", "true")
        layout = QVBoxLayout()
        layout.setSpacing(16)
        page.setLayout(layout)

        title = BrandHeadingLabel(
            "VisionSlide",
            "Gesture • Voice • Slides",
            centered=True,
            brand_size=32,
            kicker_size=10,
        )
        title.setProperty("pageTitle", "true")

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(4)
        form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)
        form.setRowWrapPolicy(QFormLayout.WrapAllRows)
        form.setLabelAlignment(Qt.AlignLeft)
        form.setFormAlignment(Qt.AlignHCenter)

        self.signin_username_input, signin_username_field, signin_username_error = self._build_text_field(
            "Enter your email",
            clear_button=True,
        )
        self.signin_password_input, signin_password_field, signin_password_error = self._build_password_field(
            "Password"
        )
        self.field_errors["signin_account"] = signin_username_error
        self.field_errors["signin_password"] = signin_password_error
        self.field_controls["signin_account"] = signin_username_field
        self.field_controls["signin_password"] = signin_password_field
        self.field_inputs["signin_account"] = self.signin_username_input
        self.field_inputs["signin_password"] = self.signin_password_input
        self.signin_username_input.installEventFilter(self)
        self.signin_username_input.textChanged.connect(self._handle_live_signin_account_validation)
        self.signin_password_input.textChanged.connect(self._handle_live_signin_password_validation)
        form.addRow(required_label("Email"), signin_username_field)
        form.addRow(required_label("Password"), signin_password_field)

        remember_row = QHBoxLayout()
        remember_row.setContentsMargins(0, 0, 0, 0)
        remember_row.addStretch()
        self.remember_signin_checkbox = QCheckBox("Remember me")
        self.remember_signin_checkbox.setChecked(True)
        self.remember_signin_checkbox.setStyleSheet(
            "QCheckBox { color: #6f8089; font-size: 12px; font-weight: 600; spacing: 8px; }"
            "QCheckBox::indicator { width: 16px; height: 16px; }"
            f"QCheckBox::indicator:checked {{ image: url({(self.assets_dir / 'checkbox_checked_soft.svg').as_posix()}); }}"
        )
        remember_row.addWidget(self.remember_signin_checkbox)
        remember_row.addStretch()

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        button_row.addStretch()
        self.signin_button = QPushButton("Sign In")
        self._apply_primary_auth_button_style(self.signin_button)
        self._apply_signin_button_style()
        self.signin_button.setDefault(True)
        self.signin_button.clicked.connect(
            lambda: self._run_with_busy_button(self.signin_button, "Signing In...", self.attempt_login)
        )
        button_row.addWidget(self.signin_button)
        button_row.addStretch()

        signup_row = QHBoxLayout()
        signup_row.addStretch()
        signup_link = QLabel(
            "New to VisionSlide? "
            "<a href='signup' style='color:#2c6e82; text-decoration:none; font-weight:700;'>Sign up</a>"
        )
        signup_link.setStyleSheet("color: #5a7380; font-size: 13px;")
        signup_link.setTextFormat(Qt.RichText)
        signup_link.setTextInteractionFlags(Qt.TextBrowserInteraction)
        signup_link.setOpenExternalLinks(False)
        signup_link.linkActivated.connect(lambda _link: self._switch_page(1))
        signup_row.addWidget(signup_link)
        signup_row.addStretch()

        forgot_row = QHBoxLayout()
        forgot_row.addStretch()
        forgot_link = QLabel(
            "Forgot Password? "
            "<a href='forgot' style='color:#2c6e82; text-decoration:none; font-weight:700;'>Reset it</a>"
        )
        forgot_link.setStyleSheet("color: #5a7380; font-size: 13px;")
        forgot_link.setTextFormat(Qt.RichText)
        forgot_link.setTextInteractionFlags(Qt.TextBrowserInteraction)
        forgot_link.setOpenExternalLinks(False)
        forgot_link.linkActivated.connect(lambda _link: self._switch_page(2))
        forgot_row.addWidget(forgot_link)
        forgot_row.addStretch()

        help_row = QHBoxLayout()
        help_row.addStretch()
        self.need_help_button = QPushButton("Need Help?")
        self.need_help_button.setProperty("textLink", "true")
        self.need_help_button.clicked.connect(self.show_need_help_dialog)
        help_row.addWidget(self.need_help_button)
        help_row.addStretch()

        layout.addStretch(1)
        layout.addWidget(title)
        layout.addSpacing(4)
        layout.addLayout(centered_form_layout(form))
        layout.addLayout(remember_row)
        layout.addSpacing(6)
        layout.addLayout(button_row)
        layout.addSpacing(4)
        layout.addLayout(signup_row)
        layout.addSpacing(4)
        layout.addLayout(forgot_row)
        layout.addSpacing(2)
        layout.addLayout(help_row)
        layout.addStretch(1)
        layout.addSpacing(10)

        def submit_signin_from_enter():
            if (self.signin_password_input.text() or "").strip():
                self._run_with_busy_button(self.signin_button, "Signing In...", self.attempt_login)
            else:
                self.signin_password_input.setFocus()

        self.signin_password_input.returnPressed.connect(submit_signin_from_enter)
        self.signin_username_input.returnPressed.connect(submit_signin_from_enter)
        self.signin_username_input.editingFinished.connect(self._fill_saved_password_for_identity)

        return page

    def show_need_help_dialog(self) -> None:
        help_dialog = QDialog(self)
        help_dialog.setWindowTitle("Need Help?")
        help_dialog.resize(540, 620)
        help_dialog.setMinimumSize(540, 620)
        help_dialog.setStyleSheet(
            "QDialog { background: #f7fbfd; }"
            "QLabel { color: #274652; font-size: 13px; }"
            "QFrame[helpCard=\"true\"] { background: #ffffff; border: 1px solid #d7e2e9; border-radius: 18px; }"
            "QLabel[helpTitle=\"true\"] { font-size: 22px; font-weight: 800; color: #173543; }"
            "QLabel[helpSub=\"true\"] { color: #5a7380; font-size: 13px; }"
            "QLabel[helpSection=\"true\"] { font-size: 14px; font-weight: 700; color: #173543; }"
            "QPushButton { min-height: 38px; border-radius: 12px; border: 1px solid #ccd8e2; "
            "background: #ffffff; color: #173543; font-weight: 700; padding: 6px 12px; }"
            "QPushButton:hover { background: #cfe5ee; border-color: #3f7c8f; }"
            "QPushButton:pressed { background: #bddbe6; border-color: #346b7d; }"
        )
        self._prepare_dialog_open_animation(help_dialog)

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)
        help_dialog.setLayout(layout)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(14)
        content.setLayout(content_layout)
        scroll_area.setWidget(content)

        title = QLabel("Need Help?")
        title.setProperty("helpTitle", "true")
        subtitle = QLabel(
            "Use this quick guide if you need help signing in, creating an account, verifying OTP, or recovering access."
        )
        subtitle.setProperty("helpSub", "true")
        subtitle.setWordWrap(True)

        def add_help_card(section_title: str, section_text: str) -> QFrame:
            card = QFrame()
            card.setProperty("helpCard", "true")
            card_layout = QVBoxLayout()
            card_layout.setContentsMargins(16, 16, 16, 16)
            card_layout.setSpacing(8)
            card.setLayout(card_layout)

            card_title = QLabel(section_title)
            card_title.setProperty("helpSection", "true")
            card_body = QLabel(section_text)
            card_body.setWordWrap(True)

            card_layout.addWidget(card_title)
            card_layout.addWidget(card_body)
            return card

        content_layout.addWidget(title)
        content_layout.addWidget(subtitle)
        content_layout.addWidget(
            add_help_card(
                "Sign In",
                "Sign in with your registered email and password. If the email format is correct but the account does not exist yet, VisionSlide will tell you to register that email first. If Remember Me stays checked, the account can appear later in saved sign-in suggestions on this device.",
            )
        )
        content_layout.addWidget(
            add_help_card(
                "Create Account",
                "Use Sign up to create a new local VisionSlide account. Enter a username, a valid email, and a strong password, then verify the email with OTP before creating the account. Only registered accounts can sign in or be promoted to admin later.",
            )
        )
        content_layout.addWidget(
            add_help_card(
                "OTP Verification",
                "OTP is used to confirm that you own the email during account creation. Click Send OTP first, wait for the code, and enter it in the OTP field. Resend OTP stays disabled during its cooldown and becomes available again after the timer finishes.",
            )
        )
        content_layout.addWidget(
            add_help_card(
                "Forgot Password",
                "If you already have an account but cannot sign in, open Forgot Password and use your registered email to set a new password. After a successful reset, sign in again with the updated password.",
            )
        )
        content_layout.addWidget(
            add_help_card(
                "Support Contact",
                "If you still need help with account access, OTP verification, or sign-in issues, contact the VisionSlide project administrator.",
            )
        )
        content_layout.addStretch()

        close_button = QPushButton("Close")
        close_button.clicked.connect(help_dialog.accept)

        layout.addWidget(scroll_area)
        layout.addWidget(close_button)

        self._apply_clickable_cursors(help_dialog)
        help_dialog.exec()

    def _build_sign_up_page(self) -> QWidget:
        page = RoundedAuthInnerPage()
        layout = QVBoxLayout()
        layout.setSpacing(18)
        layout.setContentsMargins(0, 10, 0, 10)
        page.setLayout(layout)

        title = BrandHeadingLabel(
            "Create Account",
            "",
            centered=True,
            brand_size=27,
            kicker_size=10,
        )
        title.setProperty("pageTitle", "true")

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(3)
        form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)
        form.setRowWrapPolicy(QFormLayout.WrapAllRows)
        form.setLabelAlignment(Qt.AlignLeft)
        form.setFormAlignment(Qt.AlignHCenter)

        self.signup_username_input, signup_username_field, signup_username_error = self._build_text_field(
            "Choose a username"
        )
        self.signup_email_input, signup_email_field, signup_email_error = self._build_text_field(
            "Enter your email"
        )
        self.signup_password_input, signup_password_field, signup_password_error = self._build_password_field(
            "Create a password"
        )
        self.signup_confirm_password_input, signup_confirm_password_field, signup_confirm_password_error = self._build_password_field(
            "Confirm your password"
        )
        self.signup_otp_input, signup_otp_field, signup_otp_error = self._build_text_field(
            "Enter OTP code"
        )
        self.signup_otp_input.setEnabled(False)
        self.signup_otp_input.setMaxLength(6)
        self.field_errors["signup_username"] = signup_username_error
        self.field_errors["signup_email"] = signup_email_error
        self.field_errors["signup_password"] = signup_password_error
        self.field_errors["signup_confirm_password"] = signup_confirm_password_error
        self.field_errors["signup_otp"] = signup_otp_error
        self.field_controls["signup_username"] = signup_username_field
        self.field_controls["signup_email"] = signup_email_field
        self.field_controls["signup_password"] = signup_password_field
        self.field_controls["signup_confirm_password"] = signup_confirm_password_field
        self.field_controls["signup_otp"] = signup_otp_field
        self.field_inputs["signup_username"] = self.signup_username_input
        self.field_inputs["signup_email"] = self.signup_email_input
        self.field_inputs["signup_password"] = self.signup_password_input
        self.field_inputs["signup_confirm_password"] = self.signup_confirm_password_input
        self.field_inputs["signup_otp"] = self.signup_otp_input
        self._bind_error_reset(self.signup_username_input, "signup_username")
        self._bind_error_reset(self.signup_email_input, "signup_email")
        self._bind_error_reset(self.signup_password_input, "signup_password")
        self._bind_error_reset(self.signup_confirm_password_input, "signup_confirm_password")
        self._bind_error_reset(self.signup_otp_input, "signup_otp")
        self.signup_username_input.textChanged.connect(
            lambda text: self._handle_live_username_validation("signup_username", text)
        )
        self.signup_email_input.textChanged.connect(
            lambda text: self._handle_live_email_validation("signup_email", text)
        )
        self.signup_password_input.textChanged.connect(
            lambda text: self._handle_live_password_validation("signup_password", text)
        )
        self.signup_password_input.textChanged.connect(
            lambda _text: self._handle_live_confirm_password_validation(
                "signup_confirm_password",
                self.signup_password_input.text(),
                self.signup_confirm_password_input.text(),
            )
        )
        self.signup_confirm_password_input.textChanged.connect(
            lambda text: self._handle_live_confirm_password_validation(
                "signup_confirm_password",
                self.signup_password_input.text(),
                text,
            )
        )
        self.signup_email_input.textChanged.connect(self._reset_signup_email_verification)
        self.signup_otp_input.textChanged.connect(self._handle_signup_otp_input_changed)

        otp_actions_row = QHBoxLayout()
        otp_actions_row.setContentsMargins(0, 0, 0, 0)
        otp_actions_row.setSpacing(10)
        self.send_otp_button = QPushButton("Send OTP")
        self.send_otp_button.setProperty("textLink", "true")
        self.send_otp_button.clicked.connect(
            lambda: self._run_with_busy_button(
                self.send_otp_button,
                "Sending...",
                self.send_signup_otp,
                restore_enabled=False,
            )
        )
        self.send_otp_button.setEnabled(False)
        self.send_otp_button.setMinimumHeight(30)
        self.send_otp_button.setMinimumWidth(0)
        self.resend_otp_button = QPushButton("Resend OTP")
        self.resend_otp_button.setProperty("textLink", "true")
        self.resend_otp_button.clicked.connect(
            lambda: self._run_with_busy_button(
                self.resend_otp_button,
                "Sending...",
                self.resend_signup_otp,
                restore_enabled=False,
            )
        )
        self.resend_otp_button.setEnabled(False)
        self.resend_otp_button.setMinimumHeight(30)
        self.resend_otp_button.setMinimumWidth(0)
        signup_otp_error.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        otp_actions_row.addWidget(signup_otp_error, 1)
        otp_actions_row.addWidget(self.send_otp_button)
        otp_actions_row.addWidget(self.resend_otp_button)

        otp_actions = QWidget()
        otp_actions_layout = QVBoxLayout()
        otp_actions_layout.setContentsMargins(0, 0, 0, 0)
        otp_actions_layout.setSpacing(0)
        otp_actions.setLayout(otp_actions_layout)
        otp_actions_layout.addLayout(otp_actions_row)
        signup_otp_field.setFixedHeight(92)
        otp_field_layout = signup_otp_field.layout()
        if otp_field_layout is not None:
            otp_field_layout.removeWidget(signup_otp_error)
            otp_field_layout.addWidget(otp_actions)

        form.addRow(required_label("Username"), signup_username_field)
        form.addRow(required_label("Email"), signup_email_field)
        form.addRow(required_label("Password"), signup_password_field)
        form.addRow(required_label("Confirm Password"), signup_confirm_password_field)
        form.addRow(required_label("OTP Code"), signup_otp_field)

        self.signup_status_label = QLabel("")
        self.signup_status_label.setProperty("status", "true")
        self.signup_status_label.hide()
        self.signup_status_label.setWordWrap(True)

        self.signup_success_label = QLabel("")
        self.signup_success_label.setProperty("success", "true")
        self.signup_success_label.hide()
        self.signup_success_label.setWordWrap(True)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        button_row.addStretch()
        self.signup_button = QPushButton("Create Account")
        self._apply_primary_auth_button_style(self.signup_button)
        self.signup_button.setDefault(True)
        self.signup_button.clicked.connect(
            lambda: self._run_with_busy_button(self.signup_button, "Creating...", self.attempt_signup)
        )
        button_row.addWidget(self.signup_button)
        button_row.addStretch()

        signup_back_row = QHBoxLayout()
        signup_back_row.addStretch()
        signup_back_link = QLabel(
            "Already have an account? "
            "<a href='signin' style='color:#2c6e82; text-decoration:none; font-weight:700;'>Sign in</a>"
        )
        signup_back_link.setStyleSheet("color: #5a7380; font-size: 13px;")
        signup_back_link.setTextFormat(Qt.RichText)
        signup_back_link.setTextInteractionFlags(Qt.TextBrowserInteraction)
        signup_back_link.setOpenExternalLinks(False)
        signup_back_link.linkActivated.connect(lambda _link: self._switch_page(0))
        signup_back_row.addWidget(signup_back_link)
        signup_back_row.addStretch()

        layout.addStretch(0)
        layout.addWidget(title)
        layout.addSpacing(8)
        layout.addLayout(centered_form_layout(form))
        layout.addWidget(self.signup_success_label)
        layout.addSpacing(8)
        layout.addLayout(button_row)
        layout.addSpacing(4)
        layout.addLayout(signup_back_row)
        layout.addStretch(1)

        self.signup_otp_input.returnPressed.connect(
            lambda: self._run_with_busy_button(self.signup_button, "Creating...", self.attempt_signup)
        )

        return page

    def _build_forgot_page(self) -> QWidget:
        page = RoundedAuthInnerPage()
        layout = QVBoxLayout()
        layout.setSpacing(18)
        layout.setContentsMargins(0, 10, 0, 10)
        page.setLayout(layout)

        title = BrandHeadingLabel(
            "Forgot Password",
            "",
            centered=True,
            brand_size=27,
            kicker_size=10,
        )
        title.setProperty("pageTitle", "true")

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(3)
        form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)
        form.setRowWrapPolicy(QFormLayout.WrapAllRows)
        form.setLabelAlignment(Qt.AlignLeft)
        form.setFormAlignment(Qt.AlignHCenter)

        self.reset_email_input, reset_email_field, reset_email_error = self._build_text_field(
            "Registered email"
        )
        self.reset_password_input, reset_password_field, reset_password_error = self._build_password_field(
            "New password"
        )
        self.reset_confirm_password_input, reset_confirm_password_field, reset_confirm_password_error = self._build_password_field(
            "Confirm new password"
        )

        self.field_errors["reset_email"] = reset_email_error
        self.field_errors["reset_password"] = reset_password_error
        self.field_errors["reset_confirm_password"] = reset_confirm_password_error
        self.field_controls["reset_email"] = reset_email_field
        self.field_controls["reset_password"] = reset_password_field
        self.field_controls["reset_confirm_password"] = reset_confirm_password_field
        self.field_inputs["reset_email"] = self.reset_email_input
        self.field_inputs["reset_password"] = self.reset_password_input
        self.field_inputs["reset_confirm_password"] = self.reset_confirm_password_input
        self._bind_error_reset(self.reset_email_input, "reset_email")
        self._bind_error_reset(self.reset_password_input, "reset_password")
        self._bind_error_reset(self.reset_confirm_password_input, "reset_confirm_password")
        self.reset_email_input.textChanged.connect(
            lambda text: self._handle_live_email_validation("reset_email", text)
        )
        self.reset_password_input.textChanged.connect(
            lambda text: self._handle_live_password_validation("reset_password", text)
        )
        self.reset_password_input.textChanged.connect(
            lambda _text: self._handle_live_confirm_password_validation(
                "reset_confirm_password",
                self.reset_password_input.text(),
                self.reset_confirm_password_input.text(),
            )
        )
        self.reset_confirm_password_input.textChanged.connect(
            lambda text: self._handle_live_confirm_password_validation(
                "reset_confirm_password",
                self.reset_password_input.text(),
                text,
            )
        )

        form.addRow(required_label("Email"), reset_email_field)
        form.addRow(required_label("New Password"), reset_password_field)
        form.addRow(required_label("Confirm Password"), reset_confirm_password_field)

        self.reset_status_label = QLabel("")
        self.reset_status_label.setProperty("status", "true")
        self.reset_status_label.hide()
        self.reset_status_label.setWordWrap(True)

        self.reset_success_label = QLabel("")
        self.reset_success_label.setProperty("success", "true")
        self.reset_success_label.hide()
        self.reset_success_label.setWordWrap(True)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        button_row.addStretch()
        self.reset_button = QPushButton("Update Password")
        self._apply_primary_auth_button_style(self.reset_button)
        self.reset_button.setDefault(True)
        self.reset_button.clicked.connect(
            lambda: self._run_with_busy_button(self.reset_button, "Updating...", self.attempt_password_reset)
        )
        button_row.addWidget(self.reset_button)
        button_row.addStretch()

        reset_back_row = QHBoxLayout()
        reset_back_row.addStretch()
        reset_back_link = QLabel(
            "Remembered your password? "
            "<a href='signin' style='color:#2c6e82; text-decoration:none; font-weight:700;'>Sign in</a>"
        )
        reset_back_link.setStyleSheet("color: #5a7380; font-size: 13px;")
        reset_back_link.setTextFormat(Qt.RichText)
        reset_back_link.setTextInteractionFlags(Qt.TextBrowserInteraction)
        reset_back_link.setOpenExternalLinks(False)
        reset_back_link.linkActivated.connect(lambda _link: self._switch_page(0))
        reset_back_row.addWidget(reset_back_link)
        reset_back_row.addStretch()

        layout.addStretch(0)
        layout.addWidget(title)
        layout.addSpacing(8)
        layout.addLayout(centered_form_layout(form))
        layout.addWidget(self.reset_success_label)
        layout.addSpacing(8)
        layout.addLayout(button_row)
        layout.addSpacing(4)
        layout.addLayout(reset_back_row)
        layout.addStretch(1)

        self.reset_confirm_password_input.returnPressed.connect(
            lambda: self._run_with_busy_button(self.reset_button, "Updating...", self.attempt_password_reset)
        )

        return page

    def _switch_page(self, index: int) -> None:
        if index == 0:
            self._clear_signin_fields()
        elif index == 1:
            self._clear_signup_fields()
        elif index == 2:
            self._clear_reset_fields()

        self.stack.setCurrentIndex(index)
        current_page = self.stack.currentWidget()
        if isinstance(current_page, QScrollArea):
            inner_page = current_page.widget()
            if inner_page and inner_page.layout():
                inner_page.layout().activate()
                inner_page.adjustSize()
                inner_page.updateGeometry()
            current_page.widget().updateGeometry() if current_page.widget() else None
            current_page.updateGeometry()
        elif current_page and current_page.layout():
            current_page.layout().activate()
            current_page.adjustSize()
            current_page.updateGeometry()

    def attempt_login(self) -> None:
        account_value = self.signin_username_input.text().strip().lower()
        password = self.signin_password_input.text()
        self._clear_form_errors("signin")

        has_error = False
        if not account_value:
            self._set_field_error("signin_account", "Email is required.")
            has_error = True
        if not password:
            self._set_field_error("signin_password", "Password is required.")
            has_error = True
        if has_error:
            if not account_value:
                self._focus_field("signin_account")
            else:
                self._focus_field("signin_password")
            return

        if "@" not in account_value:
            self._set_field_error("signin_account", "Please enter your email address.")
            self._focus_field("signin_account")
            return

        email_errors = validate_email(account_value)
        if email_errors:
            self._set_field_error("signin_account", email_errors[0])
            self._focus_field("signin_account")
            return

        if not self.auth_manager.authenticate_email(account_value, password):
            self._set_field_error("signin_account", "Invalid email or password.")
            self._focus_field("signin_account")
            return

        self.authenticated_username = self.auth_manager.get_username_for_email(account_value) or account_value
        self.config.set("last_login_identity", account_value)
        if self.remember_signin_checkbox.isChecked():
            self.credential_store.set_password(account_value, password)
        else:
            self.credential_store.delete_password(account_value)
        self.login_succeeded.emit()

    def attempt_signup(self) -> None:
        username = normalize_username(self.signup_username_input.text())
        email = self.signup_email_input.text().strip().lower()
        password = self.signup_password_input.text()
        confirm_password = self.signup_confirm_password_input.text()
        otp_code = self.signup_otp_input.text().strip()
        self._clear_form_errors("signup")

        field_checks = {
            "signup_username": validate_username(username),
            "signup_email": validate_email(email),
            "signup_password": validate_password(password),
            "signup_confirm_password": validate_confirm_password(password, confirm_password),
        }
        has_error = False
        first_error_field = None
        for field_name, errors in field_checks.items():
            if errors:
                self._set_field_error(field_name, errors[0])
                has_error = True
                first_error_field = first_error_field or field_name
        if has_error:
            self.signup_success_label.hide()
            self._focus_field(first_error_field)
            return

        if self.signup_verified_email != email:
            if not self._verify_signup_otp(show_success_popup=False):
                self.signup_success_label.hide()
                return

        if self.auth_manager.username_exists(username):
            self._set_field_error("signup_username", "That username is already in use.")
            self.signup_success_label.hide()
            self._focus_field("signup_username", select_all=True)
            return

        if self.auth_manager.email_exists(email):
            self._set_field_error("signup_email", "That email is already registered.")
            self.signup_success_label.hide()
            self._focus_field("signup_email", select_all=True)
            return

        try:
            self.auth_manager.create_user(username, email, password)
        except sqlite3.IntegrityError:
            self._set_field_error("signup_username", "Username or email already exists.")
            self.signup_success_label.hide()
            self._focus_field("signup_username", select_all=True)
            return

        self.otp_service.clear_for_email(email)
        self.signup_status_label.hide()
        self.signup_success_label.setText("Account created successfully. You can now sign in.")
        self.signup_success_label.show()
        self._refresh_login_completer()
        self._clear_signup_fields()
        self._switch_page(0)

    def attempt_password_reset(self) -> None:
        email = self.reset_email_input.text().strip().lower()
        new_password = self.reset_password_input.text()
        confirm_password = self.reset_confirm_password_input.text()
        self._clear_form_errors("reset")

        field_checks = {
            "reset_email": validate_email(email),
            "reset_password": validate_password(new_password),
            "reset_confirm_password": validate_confirm_password(new_password, confirm_password),
        }
        has_error = False
        first_error_field = None
        for field_name, errors in field_checks.items():
            if errors:
                self._set_field_error(field_name, errors[0])
                has_error = True
                first_error_field = first_error_field or field_name
        if has_error:
            self.reset_success_label.hide()
            self._focus_field(first_error_field)
            return

        if not self.auth_manager.reset_password(email, new_password):
            self._set_field_error("reset_email", "This email is not registered.")
            self.reset_success_label.hide()
            self._focus_field("reset_email", select_all=True)
            return

        self.reset_status_label.hide()
        self.reset_success_label.setText("Password updated successfully. Sign in with your new password.")
        self.reset_success_label.show()
        self.credential_store.set_password(email, new_password)
        self.signin_username_input.setText(email)
        self.signin_password_input.setText(new_password)
        self._clear_reset_fields()
        self._switch_page(0)

    def _show_error(self, label: QLabel, message: str) -> None:
        label.setText(message)
        label.show()

    def _clear_signup_fields(self) -> None:
        self._clear_form_errors("signup")
        self.signup_username_input.clear()
        self.signup_email_input.clear()
        self.signup_password_input.clear()
        self.signup_confirm_password_input.clear()
        self.signup_otp_input.clear()
        self.signup_verified_email = ""
        self.signup_verified_code = ""
        self.signup_failed_code = ""
        self.signup_last_otp_attempt = ""
        self.signup_success_label.hide()
        self.signup_status_label.hide()
        self._reset_otp_ui_state()

    def _clear_reset_fields(self) -> None:
        self._clear_form_errors("reset")
        self.reset_email_input.clear()
        self.reset_password_input.clear()
        self.reset_confirm_password_input.clear()
        self.reset_success_label.hide()
        self.reset_status_label.hide()

    def _clear_signin_fields(self) -> None:
        self._clear_form_errors("signin")
        self.signin_username_input.clear()
        self.signin_password_input.clear()

    def _refresh_login_completer(self) -> None:
        identities = self.credential_store.get_saved_identities()
        admin_emails = set(self.auth_manager.get_admin_emails())
        model = QStandardItemModel(self)
        for identity in identities:
            item = QStandardItem(identity)
            item.setData(identity, Qt.UserRole)
            model.appendRow(item)

        completer = LoginIdentityCompleter(model, self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        completer.setCompletionRole(Qt.DisplayRole)
        completer_popup = completer.popup()
        completer_popup.setAttribute(Qt.WA_StyledBackground, True)
        completer_popup.viewport().setAttribute(Qt.WA_StyledBackground, True)
        completer_popup.setStyleSheet(
            "QListView { background: #ffffff; border: 1px solid #d7e2e9; "
            "border-radius: 12px; padding: 6px; color: #173543; }"
            "QListView::viewport { background: #ffffff; border-radius: 12px; }"
            "QListView::item { padding: 8px 10px; border-radius: 8px; color: #173543; }"
        )
        completer_popup.viewport().setStyleSheet("background: #ffffff;")
        completer_popup.setMouseTracking(True)
        completer_popup.viewport().setMouseTracking(True)
        completer_popup.setCursor(Qt.PointingHandCursor)
        completer_popup.viewport().setCursor(Qt.PointingHandCursor)
        completer_popup.entered.connect(completer_popup.setCurrentIndex)
        completer_popup.setItemDelegate(LoginIdentityDelegate(admin_emails, completer_popup))
        self.login_suggestion_popup = completer_popup
        self.login_suggestion_popup.installEventFilter(self)
        self._apply_clickable_cursors(self.login_suggestion_popup)
        self._fit_login_suggestion_popup_height()
        self._ensure_login_suggestion_close_button()
        self.signin_username_input.setCompleter(completer)
        completer.activated[str].connect(self._apply_selected_login_identity)

    def _apply_selected_login_identity(self, displayed_text: str) -> None:
        identity = displayed_text.replace("\U0001F464", "", 1).strip()
        self.signin_username_input.setText(identity)
        self._fill_saved_password_for_identity()

    def _ensure_login_suggestion_close_button(self) -> None:
        popup = self.login_suggestion_popup
        if popup is None:
            return
        if self.login_suggestion_close_button is None:
            button = QToolButton(popup)
            button.setText("×")
            button.setToolTip("Close suggestions")
            button.setCursor(Qt.PointingHandCursor)
            button.setStyleSheet(
                "QToolButton { background: #ffffff; border: 1px solid #d7e2e9; "
                "border-radius: 9px; color: #6f8089; font-size: 14px; font-weight: 700; }"
                "QToolButton:hover { background: #fff1f0; border-color: #efb6b1; color: #c24a42; }"
            )
            button.setFixedSize(20, 20)
            button.clicked.connect(popup.hide)
            button.hide()
            self.login_suggestion_close_button = button
        self._position_login_suggestion_close_button()

    def _position_login_suggestion_close_button(self) -> None:
        popup = self.login_suggestion_popup
        button = self.login_suggestion_close_button
        if popup is None or button is None:
            return
        button.raise_()
        button.move(max(6, popup.width() - button.width() - 10), 8)

    def _fit_login_suggestion_popup_height(self) -> None:
        popup = self.login_suggestion_popup
        if popup is None or popup.model() is None:
            return

        row_count = popup.model().rowCount()
        if row_count <= 0:
            return

        visible_rows = min(row_count, 8)
        row_height = popup.sizeHintForRow(0)
        if row_height <= 0:
            row_height = 38

        popup.setFixedHeight((row_height * visible_rows) + 18)

    def _fill_saved_password_for_identity(self) -> None:
        identity = self.signin_username_input.text().strip().lower()
        if not identity:
            self.signin_password_input.clear()
            return

        stored_password = self.credential_store.get_password(identity)
        if stored_password:
            self.signin_password_input.setText(stored_password)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Show and isinstance(watched, QDialog):
            if watched.property("dialogOpeningHidden") == "true":
                QTimer.singleShot(20, lambda dialog=watched: self._reveal_prepared_dialog(dialog))

        if watched is self.login_suggestion_popup:
            if event.type() in {QEvent.Show, QEvent.Resize, QEvent.Move}:
                self._fit_login_suggestion_popup_height()
                self._position_login_suggestion_close_button()
                if self.login_suggestion_close_button is not None:
                    self.login_suggestion_close_button.show()
            elif event.type() in {QEvent.Hide, QEvent.Close}:
                if self.login_suggestion_close_button is not None:
                    self.login_suggestion_close_button.hide()

        if (
            watched is getattr(self, "signin_username_input", None)
            and event.type() == QEvent.MouseButtonPress
            and getattr(self, "signin_username_input", None) is not None
            and self.signin_username_input.completer()
            and self.signin_username_input.completer().completionCount() > 0
        ):
            QTimer.singleShot(0, self.signin_username_input.completer().complete)
        return super().eventFilter(watched, event)


    def send_signup_otp(self) -> None:
        self._dispatch_signup_otp(send_mode="send")

    def resend_signup_otp(self) -> None:
        self._dispatch_signup_otp(send_mode="resend")

    def _dispatch_signup_otp(self, send_mode: str) -> None:
        email = self.signup_email_input.text().strip().lower()
        self._clear_field_error("signup_email")
        self._clear_field_error("signup_otp")

        email_errors = validate_email(email)
        if email_errors:
            self._set_field_error("signup_email", email_errors[0])
            self._focus_field("signup_email")
            return

        try:
            otp_code = self.otp_service.generate_for_email(email)
            self.email_service.send_otp_email(email, otp_code)
        except EmailDeliveryError as error:
            self._set_field_error("signup_email", str(error))
            return

        self.signup_verified_email = ""
        self.signup_verified_code = ""
        self.signup_failed_code = ""
        self.signup_last_otp_attempt = ""
        self.otp_resend_available = True
        self.signup_otp_input.setEnabled(True)
        if send_mode == "resend":
            self._set_field_success("signup_otp", f"OTP Resend Successfully to {email}")
        else:
            self._set_field_success("signup_otp", f"OTP Send Successfully to {email}")
        self._start_otp_resend_cooldown()

    def _verify_signup_otp(self, show_success_popup: bool) -> bool:
        email = self.signup_email_input.text().strip().lower()
        code = self.signup_otp_input.text().strip()
        self._clear_field_error("signup_email")
        self._clear_field_error("signup_otp")

        email_errors = validate_email(email)
        if email_errors:
            self._set_field_error("signup_email", email_errors[0])
            self._focus_field("signup_email")
            return False

        if not code:
            self._set_field_error("signup_otp", "OTP code is required.")
            self._focus_field("signup_otp")
            return False

        if len(code) < 6:
            self._set_field_error("signup_otp", "OTP must be 6 digits.")
            self._focus_field("signup_otp")
            return False

        if len(code) > 6:
            self._set_field_error("signup_otp", "OTP cannot exceed 6 digits.")
            self._focus_field("signup_otp")
            return False

        otp_status = self.otp_service.verify_status_for_email(email, code)
        if otp_status != "valid":
            self.signup_verified_email = ""
            self.signup_verified_code = ""
            self.signup_failed_code = code
            self.otp_resend_available = True
            if otp_status == "expired":
                self._set_field_error("signup_otp", "OTP has expired.")
            else:
                self._set_field_error("signup_otp", "OTP is wrong.")
            self._sync_otp_button_states()
            self._focus_field("signup_otp")
            return False

        already_verified = self.signup_verified_email == email and self.signup_verified_code == code
        self.signup_verified_email = email
        self.signup_verified_code = code
        self.signup_failed_code = ""
        self.signup_last_otp_attempt = code
        self.otp_resend_available = False
        self._sync_otp_button_states()
        if show_success_popup and not already_verified:
            self._set_field_success("signup_otp", "OTP verified successfully.")
        return True

    def _build_text_field(
        self,
        placeholder_text: str,
        clear_button: bool = False,
    ) -> tuple[QLineEdit, QWidget, QLabel]:
        line_edit = QLineEdit()
        line_edit.setPlaceholderText(placeholder_text)
        line_edit.setClearButtonEnabled(clear_button)
        line_edit.setStyleSheet("border: none; background: transparent;")
        line_edit.setMinimumHeight(34)

        field_shell = QFrame()
        field_shell.setProperty("inputShell", "true")
        field_shell.setAttribute(Qt.WA_StyledBackground, True)
        self._apply_auth_field_shell_style(field_shell)
        field_shell.setFixedWidth(392)
        field_shell.setMinimumHeight(52)
        field_row = QHBoxLayout()
        field_row.setContentsMargins(12, 4, 8, 4)
        field_row.setSpacing(6)
        field_shell.setLayout(field_row)
        field_row.addWidget(line_edit)

        error_label = QLabel(" ")
        error_label.setProperty("fieldErrorLabel", "true")
        error_label.setWordWrap(True)
        error_label.setTextFormat(Qt.RichText)
        error_label.setFixedHeight(32)

        container = QWidget()
        container.setFixedHeight(92)
        container.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        container_layout = QVBoxLayout()
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(3)
        container.setLayout(container_layout)
        container_layout.addWidget(field_shell)
        container_layout.addWidget(error_label)

        return line_edit, container, error_label

    def _wrap_in_scroll(self, page: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        scroll.viewport().setStyleSheet("background: transparent;")
        scroll.setWidget(page)
        return scroll

    def _build_password_field(self, placeholder_text: str) -> tuple[QLineEdit, QWidget, QLabel]:
        line_edit = QLineEdit()
        line_edit.setPlaceholderText(placeholder_text)
        line_edit.setEchoMode(QLineEdit.Password)
        line_edit.setStyleSheet("border: none; background: transparent;")
        line_edit.setMinimumHeight(34)

        field_shell = QFrame()
        field_shell.setProperty("inputShell", "true")
        field_shell.setAttribute(Qt.WA_StyledBackground, True)
        self._apply_auth_field_shell_style(field_shell)
        field_shell.setFixedWidth(392)
        field_shell.setMinimumHeight(52)
        field_row = QHBoxLayout()
        field_row.setContentsMargins(12, 4, 8, 4)
        field_row.setSpacing(6)
        field_shell.setLayout(field_row)
        field_row.addWidget(line_edit)

        toggle_button = QToolButton()
        toggle_button.setProperty("passwordToggle", "true")
        toggle_button.setIcon(QIcon(str(self.assets_dir / "password_eye_windows.svg")))
        toggle_button.setIconSize(QSize(18, 18))
        toggle_button.setToolTip("Show password")
        toggle_button.setToolTipDuration(2000)
        toggle_button.setCheckable(True)
        toggle_button.hide()

        def toggle_visibility(checked: bool) -> None:
            line_edit.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)
            toggle_button.setIcon(
                QIcon(
                    str(
                        self.assets_dir
                        / ("password_eye_windows.svg" if checked else "password_eye_windows_off.svg")
                    )
                )
            )
            toggle_button.setToolTip("Hide password" if checked else "Show password")

        def sync_toggle_visibility(_text: str) -> None:
            has_text = bool(line_edit.text())
            if not has_text and toggle_button.isChecked():
                toggle_button.blockSignals(True)
                toggle_button.setChecked(False)
                toggle_button.blockSignals(False)
                line_edit.setEchoMode(QLineEdit.Password)
                toggle_button.setIcon(QIcon(str(self.assets_dir / "password_eye_windows.svg")))
                toggle_button.setToolTip("Show password")
            toggle_button.setVisible(has_text)

        toggle_button.toggled.connect(toggle_visibility)
        line_edit.textChanged.connect(sync_toggle_visibility)
        field_row.addWidget(toggle_button)

        error_label = QLabel(" ")
        error_label.setProperty("fieldErrorLabel", "true")
        error_label.setWordWrap(True)
        error_label.setTextFormat(Qt.RichText)
        error_label.setFixedHeight(32)

        container = QWidget()
        container.setFixedHeight(92)
        container.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        container_layout = QVBoxLayout()
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(3)
        container.setLayout(container_layout)
        container_layout.addWidget(field_shell)
        container_layout.addWidget(error_label)

        return line_edit, container, error_label

    def _clear_form_errors(self, prefix: str) -> None:
        for field_name in list(self.field_errors.keys()):
            if field_name.startswith(prefix):
                self._clear_field_error(field_name)

    def _bind_error_reset(self, line_edit: QLineEdit, field_name: str) -> None:
        line_edit.textChanged.connect(lambda _text, name=field_name: self._clear_field_error(name))

    def _focus_field(self, field_name: str | None, select_all: bool = False) -> None:
        if not field_name:
            return

        line_edit = self.field_inputs.get(field_name)
        if not line_edit:
            return

        self.stack.currentWidget().ensureWidgetVisible(line_edit) if isinstance(self.stack.currentWidget(), QScrollArea) else None
        line_edit.setFocus()
        if select_all:
            line_edit.selectAll()

    def _handle_live_username_validation(self, field_name: str, text: str) -> None:
        normalized = normalize_username(text)
        if not normalized:
            self._clear_field_error(field_name)
            return

        errors = validate_username(normalized)
        if errors:
            self._set_field_error(field_name, errors[0])
        elif field_name == "signup_username" and self.auth_manager.username_exists(normalized):
            self._set_field_error(field_name, "This username is already registered.")
        else:
            if field_name == "signup_username":
                self._set_field_success(field_name, "Username is available.")
            else:
                self._clear_field_error(field_name)

    def _handle_live_signin_account_validation(self, text: str) -> None:
        identity = (text or "").strip().lower()
        if not identity:
            self._clear_field_error("signin_account")
            return

        errors = validate_email(identity)
        if errors:
            self._set_field_error("signin_account", errors[0])
            return

        exists = self.auth_manager.email_exists(identity)

        if exists:
            self._set_field_success("signin_account", "Correct email.")
        else:
            self._set_field_error("signin_account", "Register email first, then sign in.")

    def _handle_live_signin_password_validation(self, text: str) -> None:
        password = text or ""
        if not password:
            self._clear_field_error("signin_password")
            return

        if len(password) < 8:
            self._set_field_error("signin_password", "Password must be at least 8 characters.")
            return

        identity = (self.signin_username_input.text() or "").strip().lower()
        if not identity:
            self._clear_field_error("signin_password")
            return

        email_errors = validate_email(identity)
        if email_errors:
            self._clear_field_error("signin_password")
            return

        account_exists = self.auth_manager.email_exists(identity)

        if not account_exists:
            self._clear_field_error("signin_password")
            return

        if self.auth_manager.authenticate_email(identity, password):
            self._set_field_success("signin_password", "Correct password.")
        else:
            self._set_field_error("signin_password", "Wrong password.")

    def _handle_live_email_validation(self, field_name: str, text: str) -> None:
        normalized = (text or "").strip().lower()
        if not normalized:
            self._clear_field_error(field_name)
            return

        errors = validate_email(normalized)
        if errors:
            self._set_field_error(field_name, errors[0])
        elif field_name == "signup_email" and self.auth_manager.email_exists(normalized):
            self._set_field_error(field_name, "This email is already registered.")
        elif field_name == "signup_email":
            self._set_field_success(field_name, "Email is available.")
        elif field_name == "reset_email" and self.auth_manager.email_exists(normalized):
            self._set_field_success(field_name, "Registered email verified.")
        elif field_name == "reset_email":
            self._set_field_error(field_name, "This email is not registered.")
        else:
            self._clear_field_error(field_name)

    def _handle_live_password_validation(self, field_name: str, text: str) -> None:
        password = text or ""
        if not password:
            self._clear_field_error(field_name)
            return

        strength, message = get_password_strength_feedback(password)
        if strength == "weak":
            self._set_field_error(field_name, message)
        elif strength == "strong":
            self._set_field_success(field_name, message)
        else:
            self._clear_field_error(field_name)

    def _handle_live_confirm_password_validation(
        self,
        field_name: str,
        password: str,
        confirm_password: str,
    ) -> None:
        confirm_value = confirm_password or ""
        if not confirm_value:
            self._clear_field_error(field_name)
            return

        errors = validate_confirm_password(password, confirm_password)
        if errors:
            self._set_field_error(field_name, errors[0])
        else:
            self._set_field_success(field_name, "Passwords match.")

    def _reset_signup_email_verification(self) -> None:
        self.signup_verified_email = ""
        self.signup_verified_code = ""
        self.signup_failed_code = ""
        self.signup_last_otp_attempt = ""
        self.otp_resend_available = False
        current_email = self.signup_email_input.text().strip().lower()
        email_ready = bool(current_email) and not validate_email(current_email)
        self.signup_otp_input.setEnabled(email_ready)
        if not email_ready:
            self.signup_otp_input.clear()
        self._clear_field_error("signup_otp")
        self._reset_otp_ui_state()

    def _start_otp_resend_cooldown(self, seconds: int = 30) -> None:
        self.otp_resend_available = True
        self.otp_resend_seconds_remaining = seconds
        self._sync_otp_button_states()
        self.send_otp_button.setEnabled(False)
        self.resend_otp_button.setEnabled(False)
        self._update_otp_button_labels()
        self.otp_resend_timer.start()

    def _tick_otp_resend_cooldown(self) -> None:
        if self.otp_resend_seconds_remaining <= 0:
            self.otp_resend_timer.stop()
            self._sync_otp_button_states()
            self.send_otp_button.setText("Send OTP")
            self.resend_otp_button.setText("Resend OTP")
            if self.otp_resend_available:
                self.send_otp_button.setEnabled(False)
                self.resend_otp_button.setEnabled(True)
            return

        self.otp_resend_seconds_remaining -= 1
        self._update_otp_button_labels()
        if self.otp_resend_seconds_remaining <= 0:
            self.otp_resend_timer.stop()
            self._sync_otp_button_states()
            self.send_otp_button.setText("Send OTP")
            self.resend_otp_button.setText("Resend OTP")
            if self.otp_resend_available:
                self.send_otp_button.setEnabled(False)
                self.resend_otp_button.setEnabled(True)

    def _update_otp_button_labels(self) -> None:
        countdown = self.otp_resend_seconds_remaining
        self.send_otp_button.setText("Send OTP")
        self.resend_otp_button.setText(f"Resend OTP ({countdown}s)")

    def _reset_otp_ui_state(self) -> None:
        self.otp_resend_timer.stop()
        self.otp_resend_seconds_remaining = 0
        self.signup_last_otp_attempt = ""
        self.signup_failed_code = ""
        self.otp_resend_available = False
        self._sync_otp_button_states()
        self.send_otp_button.setText("Send OTP")
        self.resend_otp_button.setText("Resend OTP")

    def _sync_otp_button_states(self) -> None:
        current_email = self.signup_email_input.text().strip().lower()
        email_ready = bool(current_email) and not validate_email(current_email)
        verified_current_email = bool(current_email) and self.signup_verified_email == current_email
        if verified_current_email:
            self._clear_field_error("signup_otp")
            self.otp_resend_available = False
        cooldown_active = self.otp_resend_seconds_remaining > 0
        self.send_otp_button.setEnabled(
            email_ready and not cooldown_active and not self.otp_resend_available and not verified_current_email
        )
        self.resend_otp_button.setEnabled(
            email_ready and (not cooldown_active) and self.otp_resend_available and not verified_current_email
        )

    def _handle_signup_otp_input_changed(self, text: str) -> None:
        code = text.strip()
        if code != self.signup_last_otp_attempt:
            if code != self.signup_verified_code:
                self.signup_verified_email = ""

        if len(code) < 6:
            self.signup_last_otp_attempt = ""
            if code:
                self._set_field_error("signup_otp", "OTP must be 6 digits.")
            return

        if len(code) > 6:
            self.signup_last_otp_attempt = ""
            self._set_field_error("signup_otp", "OTP cannot exceed 6 digits.")
            return

        if code == self.signup_last_otp_attempt:
            current_email = self.signup_email_input.text().strip().lower()
            if self.signup_verified_email and self.signup_verified_email == current_email:
                self._clear_field_error("signup_otp")
            return

        self.signup_last_otp_attempt = code
        self._verify_signup_otp(show_success_popup=True)

    def _clear_field_error(self, field_name: str) -> None:
        error_label = self.field_errors.get(field_name)
        control = self.field_controls.get(field_name)
        visual_control = self._resolve_visual_control(control)
        if error_label:
            error_label.setText(" ")
            error_label.setProperty("fieldErrorLabel", "true")
            error_label.setProperty("fieldSuccessLabel", "false")
        if visual_control:
            visual_control.setProperty("fieldError", "false")
            visual_control.setProperty("fieldSuccess", "false")
            visual_control.style().unpolish(visual_control)
            visual_control.style().polish(visual_control)
        if error_label:
            error_label.style().unpolish(error_label)
            error_label.style().polish(error_label)

    def _set_field_error(self, field_name: str, message: str) -> None:
        error_label = self.field_errors.get(field_name)
        control = self.field_controls.get(field_name)
        visual_control = self._resolve_visual_control(control)
        display_message = format_validation_message(message)
        if error_label:
            error_label.setText(
                f'<span style="color:#b64a3e; font-weight:700;">&#128712;</span> {display_message}'
            )
            error_label.setProperty("fieldErrorLabel", "true")
            error_label.setProperty("fieldSuccessLabel", "false")
            error_label.style().unpolish(error_label)
            error_label.style().polish(error_label)
        if visual_control:
            visual_control.setProperty("fieldError", "true")
            visual_control.setProperty("fieldSuccess", "false")
            visual_control.style().unpolish(visual_control)
            visual_control.style().polish(visual_control)

    def _set_field_success(self, field_name: str, message: str) -> None:
        error_label = self.field_errors.get(field_name)
        control = self.field_controls.get(field_name)
        visual_control = self._resolve_visual_control(control)
        display_message = format_validation_message(message)
        if error_label:
            error_label.setText(
                f'<span style="color:#2c7a4b; font-weight:700;">&#128712;</span> {display_message}'
            )
            error_label.setProperty("fieldErrorLabel", "false")
            error_label.setProperty("fieldSuccessLabel", "true")
            error_label.style().unpolish(error_label)
            error_label.style().polish(error_label)
        if visual_control:
            visual_control.setProperty("fieldError", "false")
            visual_control.setProperty("fieldSuccess", "true")
            visual_control.style().unpolish(visual_control)
            visual_control.style().polish(visual_control)

    def _resolve_visual_control(self, control: QWidget | None) -> QWidget | None:
        if control is None:
            return None
        if isinstance(control, QLineEdit):
            return control.parentWidget() or control
        shell = control.findChild(QFrame)
        return shell or control
