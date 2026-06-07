import os
import re
import time
from pathlib import Path
import cv2
import sounddevice as sd
from PySide6.QtCore import QEvent, QEasingCurve, QPropertyAnimation, QRect, QSize, QTimer, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QIcon, QImage, QKeySequence, QPainter, QPalette, QPen, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QMenu,
    QPushButton,
    QPlainTextEdit,
    QProgressBar,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
    QSpinBox,
    QSplitter,
    QStyle,
    QStyledItemDelegate,
    QStylePainter,
    QStyleOptionFrame,
    QToolButton,
    QToolTip,
    QVBoxLayout,
    QWidget,
    QAbstractSpinBox,
    QTextEdit,

)

from app.auth import AuthManager
from app.brand_heading import BrandHeadingLabel
from app.voice_listener import VoiceListener
from app.app_state import AppState
from app.audio_feedback import AudioFeedback
from app.camera_manager import CameraManager
from app.cooldown_manager import CooldownManager
from app.credential_store import CredentialStore
from app.gesture_classifier import GestureClassifier
from app.hand_detector import HandDetector
from app.hover_effects import attach_hover_bounce
from app.config import AppConfig
from app.email_service import EmailDeliveryError, EmailService
from app.otp_service import OTPService
from app.slide_controller import SlideController
from app.device_manager import DeviceManager
from app.login_window import LoginWindow
from app.spin_boxes import NoWheelComboBox, NoWheelDoubleSpinBox, NoWheelSpinBox
from app.window_effects import enable_soft_window_transitions
from app.runtime_paths import resource_path
from app.validators import (
    format_validation_message,
    normalize_username,
    sanitize_camera_index,
    sanitize_control_hold_frames,
    sanitize_jump_hold_seconds,
    sanitize_total_slides,
    sanitize_voice_device_name,
    validate_email,
    validate_confirm_password,
    validate_password,
    validate_username,
)


_QtDialog = QDialog


class AnimatedDialog(_QtDialog):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setProperty("skipFadeInTransition", True)
        enable_soft_window_transitions(self, fade_in_ms=260, fade_out_ms=220)


QDialog = AnimatedDialog


MIC_DEFAULT_BADGE_ROLE = Qt.UserRole + 10


class MicrophoneBadgeDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        painter.save()

        text = str(index.data(Qt.DisplayRole) or "")
        show_default_badge = bool(index.data(MIC_DEFAULT_BADGE_ROLE))

        bg_color = QColor("#ffffff")
        text_color = QColor("#173543")
        badge_bg = QColor("#edf8f1")
        badge_border = QColor("#cbe6d2")
        badge_text = QColor("#1f8f5f")

        if option.state & QStyle.State_Selected:
            bg_color = QColor("#bfe7f8")
            text_color = QColor("#082632")
        elif option.state & QStyle.State_MouseOver:
            bg_color = QColor("#bfe7f8")
            text_color = QColor("#082632")

        painter.setRenderHint(QPainter.Antialiasing, True)
        if option.state & (QStyle.State_Selected | QStyle.State_MouseOver):
            painter.setPen(Qt.NoPen)
            painter.setBrush(bg_color)
            painter.drawRoundedRect(option.rect.adjusted(2, 2, -2, -2), 8, 8)

        content_rect = option.rect.adjusted(12, 0, -12, 0)
        badge_width = 0
        badge_gap = 8
        badge_height = 22

        if show_default_badge:
            badge_label = "Default"
            badge_width = painter.fontMetrics().horizontalAdvance(badge_label) + 18
            badge_rect = QRect(
                content_rect.right() - badge_width,
                content_rect.center().y() - (badge_height // 2),
                badge_width,
                badge_height,
            )
            painter.setPen(QPen(badge_border))
            painter.setBrush(badge_bg)
            painter.drawRoundedRect(badge_rect, 10, 10)
            painter.setPen(badge_text)
            painter.drawText(badge_rect, Qt.AlignCenter, badge_label)

        text_rect = QRect(
            content_rect.left(),
            content_rect.top(),
            max(0, content_rect.width() - badge_width - (badge_gap if show_default_badge else 0)),
            content_rect.height(),
        )
        painter.setPen(text_color)
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, text)
        painter.restore()

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(max(size.height(), 34))
        return size




class AnimatedLabel(QLabel):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._scroll_timer = QTimer(self)
        self._scroll_timer.timeout.connect(self._scroll_step)
        self._scroll_offset = 0
        self._scroll_direction = 1
        self._scroll_active = False
        self.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.setText(text)

    def setText(self, text):
        super().setText(text)
        self._scroll_offset = 0
        self._scroll_direction = 1
        self._update_scroll_state()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_scroll_state()

    def _update_scroll_state(self):
        text_width = self.fontMetrics().horizontalAdvance(self.text())
        available_width = max(0, self.width() - 16)
        if text_width > available_width and available_width > 0:
            self._scroll_active = True
            if not self._scroll_timer.isActive():
                self._scroll_timer.start(70)
        else:
            self._scroll_active = False
            self._scroll_timer.stop()
            self._scroll_offset = 0
            self.update()

    def _scroll_step(self):
        if not self._scroll_active:
            return
        text_width = self.fontMetrics().horizontalAdvance(self.text())
        available_width = max(0, self.width() - 16)
        if available_width <= 0:
            return

        self._scroll_offset += 1
        total_range = text_width + available_width + 40
        if self._scroll_offset > total_range:
            self._scroll_offset = 0
        self.update()

    def paintEvent(self, event):
        painter = QStylePainter(self)
        option = QStyleOptionFrame()
        self.initStyleOption(option)
        painter.drawControl(QStyle.CE_ShapedFrame, option)

        painter.setPen(self.palette().color(QPalette.WindowText))
        painter.setFont(self.font())

        contents = self.contentsRect().adjusted(8, 0, -8, 0)
        if self._scroll_active:
            text = self.text()
            text_width = self.fontMetrics().horizontalAdvance(text)
            x = contents.right() - self._scroll_offset
            painter.drawText(QRect(x, contents.top(), text_width + 4, contents.height()), Qt.AlignVCenter | Qt.AlignLeft, text)
            painter.drawText(QRect(x + text_width + 40, contents.top(), text_width + 4, contents.height()), Qt.AlignVCenter | Qt.AlignLeft, text)
        else:
            painter.drawText(contents, Qt.AlignVCenter | Qt.AlignLeft, self.text())


HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (17, 18), (18, 19), (19, 20),
    (0, 17),
]


class MicrophoneSettingsDialog(QDialog):
    def __init__(self, parent=None, dark_mode=False):
        super().__init__(parent)
        enable_soft_window_transitions(self, fade_in_ms=260, fade_out_ms=220)
        self.dark_mode = bool(dark_mode)
        self.setWindowTitle("Voice Control Settings")
        self.setModal(True)
        self.setWindowModality(Qt.ApplicationModal)
        self.resize(500, 180)

        # Create widgets
        self.voice_device_input = QComboBox()
        self.voice_device_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.voice_device_input.setMinimumHeight(40)
        self.voice_device_input.setMaxVisibleItems(8)
        self.voice_device_input.setObjectName("mic_combo")
        self.voice_device_input.setCursor(Qt.PointingHandCursor)
        self.voice_device_input.view().setCursor(Qt.PointingHandCursor)
        self.voice_device_input.view().viewport().setCursor(Qt.PointingHandCursor)
        self.voice_device_input.setItemDelegate(MicrophoneBadgeDelegate(self.voice_device_input))

        self.voice_refresh_button = QPushButton("Refresh Microphones")
        self.voice_refresh_button.setToolTip("Refresh microphone list")
        self.voice_refresh_button.setObjectName("dialog_button")
        self.voice_refresh_button.setCursor(Qt.PointingHandCursor)

        self.voice_test_button = QPushButton("Test Microphone")
        self.voice_test_button.setObjectName("dialog_button")
        self.voice_test_button.setCursor(Qt.PointingHandCursor)

        self.device_manager = DeviceManager()

        # Layout
        layout = QVBoxLayout()
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # Audio input selection row
        mic_row = QHBoxLayout()
        mic_row.setContentsMargins(0, 0, 0, 0)
        mic_row.setSpacing(10)

        mic_label = QLabel("Audio Input:")
        mic_label.setMinimumWidth(85)
        mic_row.addWidget(mic_label)
        mic_row.addWidget(self.voice_device_input, 1)
        layout.addLayout(mic_row)

        # Buttons row (Test, Refresh, OK - all equal size)
        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(10)

        ok_button = QPushButton("OK")
        ok_button.setObjectName("dialog_button")
        ok_button.setCursor(Qt.PointingHandCursor)
        ok_button.clicked.connect(self.accept)
        attach_hover_bounce(self.voice_refresh_button, y_offset=3, duration=180)
        attach_hover_bounce(self.voice_test_button, y_offset=3, duration=180)
        attach_hover_bounce(ok_button, y_offset=3, duration=180)

        button_row.addWidget(self.voice_refresh_button)
        button_row.addWidget(ok_button)
        button_row.addWidget(self.voice_test_button)
        layout.addLayout(button_row)

        self.setLayout(layout)

        # Connect signals
        self.voice_refresh_button.clicked.connect(self._on_refresh_clicked)
        self.voice_test_button.clicked.connect(self.test_microphone)

        # Unified styling
        if self.dark_mode:
            self.setStyleSheet(
                """
                QDialog { background-color: #0f1a22; }
                QLabel { color: #e7f3f8; font-size: 13px; }

                QComboBox#mic_combo {
                    min-height: 40px;
                    border-radius: 8px;
                    border: 1px solid #42697c;
                    background-color: #16303d;
                    padding: 0px 12px 0px 12px;
                    color: #e7f3f8;
                    font-size: 13px;
                    padding-right: 34px;
                }

                QComboBox#mic_combo:hover {
                    background-color: #214353;
                    border-color: #5c8aa0;
                    color: #ffffff;
                }

                QComboBox#mic_combo:focus {
                    border-color: #5c8aa0;
                    background-color: #16303d;
                }

                QComboBox#mic_combo::drop-down {
                    subcontrol-origin: padding;
                    subcontrol-position: top right;
                    width: 34px;
                    border: none;
                    background: transparent;
                }

                QComboBox#mic_combo::down-arrow {
                    image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 12 8'><polygon points='0,0 12,0 6,8' fill='%23e7f3f8'/></svg>");
                    width: 12px;
                    height: 8px;
                    margin-right: 0px;
                    border: none;
                    background: transparent;
                }

                QComboBox#mic_combo QAbstractItemView {
                    border: 1px solid #42697c;
                    background-color: #132630;
                    color: #e7f3f8;
                    selection-background-color: #24506a;
                    selection-color: #ffffff;
                    outline: 0px;
                }

                QComboBox#mic_combo QAbstractItemView::item {
                    padding: 6px 10px;
                    height: 28px;
                }

                QComboBox#mic_combo QAbstractItemView::item:hover {
                    background-color: #214353;
                    color: #ffffff;
                }

                QComboBox#mic_combo QAbstractItemView::item:selected {
                    background-color: #24506a;
                    color: #ffffff;
                }

                QLabel#feedback_status {
                    border: none;
                    background: transparent;
                    padding: 2px 6px 6px 6px;
                    color: #d8eef6;
                    font-size: 14px;
                    font-weight: 600;
                }

                QLabel#feedback_status[status="error"] {
                    color: #e09090;
                }

                QPushButton#dialog_button {
                    min-height: 40px;
                    min-width: 120px;
                    border-radius: 8px;
                    border: 1px solid #42697c;
                    background-color: #183240;
                    color: #eaf6fb;
                    padding: 6px 14px;
                    font-size: 12px;
                    font-weight: 500;
                }

                QPushButton#dialog_button:hover {
                    background-color: #214353;
                    border-color: #5c8aa0;
                    color: #ffffff;
                }

                QPushButton#dialog_button:pressed {
                    background-color: #122733;
                    border-color: #305465;
                }
                """
            )
        else:
            self.setStyleSheet(
                """
            QDialog { background-color: #f5f9fc; }
            QLabel { color: #173543; font-size: 13px; }

            QComboBox#mic_combo {
                min-height: 40px;
                border-radius: 8px;
                border: 1px solid #cad7e1;
                background-color: #ffffff;
                padding: 0px 12px 0px 12px;
                color: #173543;
                font-size: 13px;
                padding-right: 34px;
            }

            QComboBox#mic_combo:hover {
                background-color: #cfeefb;
                border-color: #3f8196;
            }

            QComboBox#mic_combo:focus {
                border-color: #cad7e1;
                background-color: #ffffff;
            }

            QComboBox#mic_combo::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 34px;
                border: none;
                background: transparent;
            }

            QComboBox#mic_combo::down-arrow {
                image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 12 8'><polygon points='0,0 12,0 6,8' fill='%23173543'/></svg>");
                width: 12px;
                height: 8px;
                margin-right: 0px;
                border: none;
                background: transparent;
            }

            QComboBox#mic_combo QAbstractItemView {
                border: 1px solid #cad7e1;
                background-color: #ffffff;
                color: #173543;
                selection-background-color: #dfeff4;
                selection-color: #173543;
                outline: 0px;
            }

            QComboBox#mic_combo QAbstractItemView::item {
                padding: 6px 10px;
                height: 28px;
            }

            QComboBox#mic_combo QAbstractItemView::item:hover {
                background-color: #bfe7f8;
                color: #082632;
            }

            QComboBox#mic_combo QAbstractItemView::item:selected {
                background-color: #bfe7f8;
                color: #082632;
            }

            QLabel#feedback_status {
                border: none;
                background: transparent;
                padding: 2px 6px 6px 6px;
                color: #0f3946;
                font-size: 14px;
                font-weight: 600;
            }

            QLabel#feedback_status[status="error"] {
                color: #7f2f31;
            }

            QPushButton#dialog_button {
                min-height: 40px;
                min-width: 120px;
                border-radius: 8px;
                border: 1px solid #cad7e1;
                background-color: #ffffff;
                color: #173543;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: 500;
            }

            QPushButton#dialog_button:hover {
                background-color: #cfeefb;
                border-color: #3f8196;
            }

            QPushButton#dialog_button:pressed {
                background-color: #bfe7f8;
                border-color: #3f8196;
            }
            """
            )

        # Initial refresh (no popup)
        self.refresh_microphone_list(show_feedback=False)

    def _selected_voice_device_name(self):
        selected_name = self.voice_device_input.currentData()
        if selected_name:
            return str(selected_name)
        return str(self.voice_device_input.currentText() or "").strip()

    def _on_refresh_clicked(self):
        """Handle refresh button click with feedback popup."""
        self.refresh_microphone_list(show_feedback=True)
        return super().eventFilter(watched, event)

    def refresh_microphone_list(self, show_feedback=False):
        """Refresh the microphone device list."""
        devices = self.device_manager.get_microphone_devices()
        default_name = self.device_manager.get_default_microphone_name()
        current_selection = self._selected_voice_device_name()
        parent_selection = ""
        if self.parent() is not None and hasattr(self.parent(), "config"):
            try:
                parent_selection = str(self.parent().config.get("voice_device_name") or "").strip()
            except Exception:
                parent_selection = ""

        self.voice_device_input.clear()

        for device_name in devices:
            self.voice_device_input.addItem(device_name, device_name)
            item_index = self.voice_device_input.count() - 1
            self.voice_device_input.setItemData(item_index, device_name == default_name, MIC_DEFAULT_BADGE_ROLE)

        preferred_selection = ""
        for candidate in [current_selection, parent_selection, default_name or ""]:
            if not candidate:
                continue
            for index in range(self.voice_device_input.count()):
                if self.voice_device_input.itemData(index) == candidate:
                    preferred_selection = candidate
                    break
            if preferred_selection:
                break

        if not preferred_selection:
            for candidate in [
                "Microphone Array (Realtek HD audio Mic input)",
                "Microphone Array",
                "Realtek",
            ]:
                for index in range(self.voice_device_input.count()):
                    item_name = str(self.voice_device_input.itemData(index) or "")
                    if candidate.lower() in item_name.lower():
                        preferred_selection = item_name
                        break
                if preferred_selection:
                    break

        if preferred_selection:
            for index in range(self.voice_device_input.count()):
                if self.voice_device_input.itemData(index) == preferred_selection:
                    self.voice_device_input.setCurrentIndex(index)
                    break
        elif self.voice_device_input.count() > 0:
            self.voice_device_input.setCurrentIndex(0)

        if show_feedback:
            if devices:
                self._show_feedback_popup(
                    "Microphone Refresh",
                    f"Found {len(devices)} microphone device(s).",
                    success=True,
                )
            else:
                self._show_feedback_popup(
                    "Microphone Refresh",
                    "No microphone devices found. Check your audio settings.",
                    success=False,
                )

    def _show_feedback_popup(self, title: str, message: str, success: bool = True):
        popup = QDialog(self)
        popup.setWindowTitle(title)
        popup.setModal(True)
        popup.setWindowModality(Qt.ApplicationModal)
        popup.setFixedSize(420, 185)

        layout = QVBoxLayout(popup)
        layout.setContentsMargins(22, 22, 22, 18)
        layout.setSpacing(16)

        badge_bg = "#e7f7ef" if success else "#fdf0ef"
        badge_fg = "#217a54" if success else "#b54844"
        badge_symbol = "\u2713" if success else "\u2715"
        inline_message = (
            f"<span style=\"display:inline-block; min-width:24px; max-width:24px; "
            f"min-height:24px; line-height:24px; text-align:center; border-radius:12px; "
            f"background:{badge_bg}; color:{badge_fg}; font-weight:800; font-size:14px;\">"
            f"{badge_symbol}</span>"
            f"&nbsp;&nbsp;{message}"
        )

        feedback_label = QLabel(inline_message)
        feedback_label.setObjectName("feedback_status")
        feedback_label.setProperty("status", "success" if success else "error")
        feedback_label.setWordWrap(True)
        feedback_label.setAlignment(Qt.AlignCenter)
        feedback_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(feedback_label)

        button_row = QHBoxLayout()
        button_row.addStretch(1)

        ok_button = QPushButton("OK")
        ok_button.setObjectName("dialog_button")
        ok_button.setCursor(Qt.PointingHandCursor)
        ok_button.setFixedSize(110, 38)
        ok_button.clicked.connect(popup.accept)
        attach_hover_bounce(ok_button, y_offset=3, duration=180)
        button_row.addWidget(ok_button)

        button_row.addStretch(1)
        layout.addLayout(button_row)

        popup.setStyleSheet(self.styleSheet())
        popup.exec()

    def test_microphone(self):
        """Test the selected microphone"""
        selected_mic = self.voice_device_input.currentText()
        if not selected_mic:
            self._show_feedback_popup(
                "Microphone Test",
                "No microphone selected.",
                success=False,
            )
            return

        # Import here to avoid circular imports
        from app.voice_listener import VoiceListener

        # Create a temporary voice listener for testing
        test_listener = VoiceListener(
            str(resource_path("models", "vosk-model-small-en-us-0.15")),
            selected_mic,
            lambda x: None,
        )

        try:
            success = test_listener.test_input_device()
            if success:
                self._show_feedback_popup(
                    "Microphone Test",
                    f"'{selected_mic}' is working correctly.",
                    success=True,
                )
            else:
                self._show_feedback_popup(
                    "Microphone Test",
                    f"'{selected_mic}' failed the test.",
                    success=False,
                )
        except Exception as e:
            self._show_feedback_popup(
                "Microphone Test",
                f"Error testing microphone: {str(e)}",
                success=False,
            )


class MainWindow(QMainWindow):
    voice_command_received = Signal(str)

    def __init__(self, current_user=None, auth_manager: AuthManager | None = None):
        super().__init__()
        self._startup_reveal_pending = True
        self._startup_reveal_animation: QPropertyAnimation | None = None
        self.assets_dir = resource_path("assets")
        self.auth_manager = auth_manager or AuthManager()
        self.current_user = normalize_username(current_user or "admin")
        self.current_email = self.auth_manager.get_email_for_username(self.current_user) or ""

        self.setWindowTitle("VisionSlide")
        self.setWindowIcon(QIcon(str(self.assets_dir / "visionslide_app_icon.svg")))
        self.resize(1360, 820)
        self.setWindowOpacity(0.0)
        self.setUpdatesEnabled(False)
        self.setStyleSheet(
            """
            QMainWindow {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #dbe8ed, stop:1 #c5dbe4);
            }
            QWidget {
                font-family: "Segoe UI";
                color: #19313d;
            }
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 10px;
                margin: 8px 2px 8px 0;
            }
            QScrollBar::handle:vertical {
                background: #c5d4de;
                border-radius: 5px;
                min-height: 28px;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical,
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {
                background: transparent;
                height: 0;
            }
            QGroupBox {
                font-size: 12px;
                font-weight: 700;
                color: #25414d;
                border: 1px solid #b8ced8;
                border-radius: 18px;
                margin-top: 14px;
                padding: 18px 16px 16px 16px;
                background: #e6f1f5;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 14px;
                padding: 0 8px;
                color: #547180;
                background: #dbe8ed;
            }
            QLabel {
                font-size: 13px;
                color: #2c4653;
            }
            QLabel[stateBadge="true"] {
                background: #f2f7fa;
                border: 1px solid #d9e4eb;
                border-radius: 11px;
                padding: 8px 12px;
                color: #173543;
                font-weight: 600;
            }
            QLabel[emphasis="strong"] {
                font-size: 14px;
                font-weight: 700;
                padding: 10px 12px;
            }
            QLabel[tone="info"] {
                background: #edf6fb;
                border-color: #cae0ee;
                color: #17445c;
            }
            QLabel[tone="success"] {
                background: #edf8f1;
                border-color: #cbe6d2;
                color: #1c5b34;
            }
            QLabel[tone="warning"] {
                background: #fff7ec;
                border-color: #f0dcc0;
                color: #7d551a;
            }
            QLabel[tone="danger"] {
                background: #fff1ef;
                border-color: #efcbc5;
                color: #8b362f;
            }
            QLabel[tone="muted"] {
                background: #f2f7fa;
                border-color: #d9e4eb;
                color: #55717d;
            }
            QPushButton {
                min-height: 42px;
                border-radius: 14px;
                border: 1px solid #ccd8e2;
                background: #ffffff;
                color: #173543;
                padding: 8px 14px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #f9fcff;
                border-color: #8fb6cb;
                color: #102d3a;
            }
            QPushButton:disabled {
                background: #f3f7fa;
                border-color: #d9e3ea;
                color: #95a7b2;
            }
            QPushButton:pressed {
                background: #e7f0f6;
            }
            QPushButton[variant="danger"] {
                background: #fff4f2;
                color: #9b3c30;
                border: 1px solid #efc5bd;
            }
            QPushButton[variant="danger"]:hover {
                background: #ffeae5;
            }
            QPushButton[destructiveAction="true"] {
                background: #fff4f2;
                border-color: #efc5bd;
                color: #973d32;
            }
            QPushButton[destructiveAction="true"]:hover {
                background: #ffe6e0;
                border-color: #d47f71;
                color: #7f2f27;
            }
            QPushButton[modeActive="true"] {
                background: #e9f5fb;
                border: 1px solid #97bfd1;
                color: #12384b;
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
            QPushButton[smallAction="true"] {
                min-height: 34px;
                min-width: 120px;
                padding: 6px 12px;
                font-size: 12px;
            }
            QPushButton[cameraControl="true"] {
                min-height: 34px;
                border-radius: 12px;
                padding: 6px 12px;
            }
            QPushButton[cameraControl="true"]:hover {
                background: #cfe5ee;
                border-color: #3f7c8f;
                color: #143745;
            }
            QPushButton[cameraControl="true"][variant="danger"]:hover {
                background: #f4d9d5;
                border-color: #c97169;
                color: #7b2f2b;
            }
            QComboBox {
                min-height: 36px;
                border-radius: 12px;
                border: 1px solid #cad7e1;
                background: #ffffff;
                padding: 4px 10px;
                color: #173543;
            }
            QComboBox:hover {
                border-color: #4c8ea4;
                background: #c8e7f2;
                color: #103647;
            }
            QComboBox:disabled,
            QSpinBox:disabled,
            QDoubleSpinBox:disabled,
            QCheckBox:disabled {
                color: #95a7b2;
            }
            QComboBox:disabled,
            QSpinBox:disabled,
            QDoubleSpinBox:disabled {
                border-color: #d9e3ea;
                background: #f3f7fa;
            }
            QComboBox#statusModeCombo {
                min-height: 34px;
                border-radius: 11px;
                border: 1px solid #cae0ee;
                background: #edf6fb;
                color: #17445c;
                font-size: 13px;
                font-weight: 600;
                padding: 6px 28px 6px 12px;
            }
            QComboBox#statusModeCombo:hover {
                border-color: #5f9db3;
                background: #dceff8;
                color: #143b4f;
            }
            QComboBox#statusModeCombo::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 28px;
                border: none;
                background: transparent;
            }
            QComboBox#statusModeCombo::down-arrow {
                image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 10 6'><polygon points='0,0 10,0 5,6' fill='%2317445c'/></svg>");
                width: 10px;
                height: 6px;
                margin-right: 8px;
            }
            QComboBox#statusModeCombo QAbstractItemView {
                border: 1px solid #cae0ee;
                border-radius: 10px;
                outline: 0;
                background: #ffffff;
                color: #17445c;
                selection-background-color: #dceff8;
                selection-color: #143b4f;
                padding: 4px;
            }
            QComboBox#statusModeCombo QAbstractItemView::item {
                min-height: 28px;
                padding: 6px 10px;
                border-radius: 8px;
            }
            QComboBox#statusModeCombo QAbstractItemView::item:hover {
                background: #dceff8;
                color: #143b4f;
            }
            QComboBox#statusModeCombo QAbstractItemView::item:selected {
                background: #cfe7f1;
                color: #143b4f;
            }
            QSpinBox:hover,
            QDoubleSpinBox:hover {
                border: 1px solid #4c8ea4;
                background: #c8e7f2;
                color: #103647;
            }
            QComboBox::drop-down {
                width: 24px;
                background: transparent;
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 4px solid #e0e0e0;
                margin-right: 8px;
            }
            QComboBox#mic_combo {
                min-height: 36px;
                border-radius: 12px 0 0 12px;
                border: 1px solid #cad7e1;
                background: #ffffff;
                padding: 0 10px;
                color: #173543;
            }
            QComboBox#mic_combo:hover {
                border-color: #4f8ea1;
                background: #dfeff4;
                color: #15394b;
            }
            QComboBox#mic_combo::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 34px;
                border: none;
                background: transparent;
            }
            QComboBox#mic_combo::down-arrow {
                image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 10 6'><polygon points='0,0 10,0 5,6' fill='%23173543'/></svg>");
                width: 10px;
                height: 6px;
                margin-right: 0px;
            }
            QComboBox#mic_combo::down-arrow:on {
                top: 1px;
            }
            QComboBox#mic_combo QAbstractItemView {
                border: 1px solid #cad7e1;
                outline: 0;
                background: #ffffff;
                selection-background-color: #cfeefb;
                selection-color: #15394b;
            }
            QComboBox#mic_combo::item:hover {
                background: #cfeefb;
                color: #15394b;
            }
            QPushButton#mic_refresh {
                min-width: 38px;
                min-height: 36px;
                border-radius: 0 12px 12px 0;
                border: 1px solid #cad7e1;
                border-left: none;
                background: #ffffff;
                color: #173543;
                padding: 4px;
            }
            QPushButton#mic_refresh:hover {
                background: #dfeff4;
                border-color: #4f8ea1;
                color: #15394b;
            }
            QPushButton#mic_refresh:pressed {
                background: #cfe8f0;
            }
            QCheckBox {
                spacing: 10px;
                color: #274652;
                font-size: 13px;
                font-weight: 500;
            }
            QCheckBox:hover {
                color: #103647;
                background: #c8e7f2;
                border-radius: 10px;
            }
            QCheckBox::indicator {
                width: 15px;
                height: 15px;
            }
            QFrame#cameraCard {
                background: #e3eff4;
                border: 1px solid #b9d0da;
                border-radius: 28px;
            }
            QLabel[sectionNote="true"] {
                background: #f4f8fb;
                border: 1px solid #dbe6ed;
                border-radius: 14px;
                padding: 10px 12px;
                color: #45606c;
                font-size: 12px;
            }
            QLabel[securityValue="true"] {
                background: #f7fbfd;
                border: 1px solid #d7e2e9;
                border-radius: 12px;
                padding: 8px 12px;
                color: #24424f;
                font-weight: 600;
            }
            QLabel[securityMessage="error"] {
                color: #e09090;
                font-size: 11px;
                font-weight: 600;
                padding-left: 4px;
            }
            QLabel[securityMessage="success"] {
                color: #90c090;
                font-size: 11px;
                font-weight: 600;
                padding-left: 4px;
            }
            QLabel[securityMessage="neutral"] {
                color: #aaaaaa;
                font-size: 11px;
                font-weight: 600;
                padding-left: 4px;
            }
            QLabel#cameraSubtext {
                color: #cccccc;
                font-size: 12px;
            }
            QLineEdit {
                min-height: 52px;
                border-radius: 14px;
                border: 1px solid #cad7e1;
                background: #ffffff;
                padding: 6px 12px;
                color: #173543;
                font-size: 13px;
            }
            QLineEdit:focus {
                border-color: #8fb6cb;
                background: #f9fcff;
            }
            QLineEdit[validationState="error"] {
                border: 1px solid #d66f63;
                background: #fff8f6;
            }
            QLineEdit[validationState="success"] {
                border: 1px solid #7cc497;
                background: #f6fcf8;
            }
            QFrame#footerStrip {
                background: #e3eff4;
                border: 1px solid #bad0da;
                border-radius: 16px;
            }
            QLabel[footerLabel="true"] {
                color: #46616f;
                font-size: 12px;
                font-weight: 700;
                background: #dbeaf0;
                border: 1px solid #b7ced8;
                border-radius: 12px;
                padding: 6px 12px;
            }
            QLabel#sidebarInfoLabel {
                color: #2e5568;
                font-size: 11px;
                font-weight: 600;
                background: #e8f2f6;
                border: 1px solid #bfd4de;
                border-radius: 12px;
                padding: 6px 10px;
            }
            QToolTip {
                background: #edf6fb;
                color: #17445c;
                border: 1px solid #cae0ee;
                border-radius: 12px;
                padding: 6px 10px;
                font-size: 11px;
                font-weight: 600;
            }
            QLabel#footerInfoLabel {
                color: #2e5568;
                font-size: 11px;
                font-weight: 600;
                background: #e8f2f6;
                border: 1px solid #bfd4de;
                border-radius: 12px;
                padding: 6px 10px;
            }
            QSplitter::handle {
                background: transparent;
            }
            QSplitter::handle:hover {
                background: #d9e9f0;
            }
            QToolButton[sectionToggle="true"] {
                min-height: 38px;
                border-radius: 14px;
                border: 1px solid #b8ced8;
                background: #e6f1f5;
                color: #173543;
                font-size: 13px;
                font-weight: 700;
                padding: 6px 12px;
                text-align: left;
            }
            QToolButton[sectionToggle="true"]:hover {
                background: #d3e7ef;
                border-color: #7faabd;
                color: #103647;
            }
            QToolButton[utilityMenuButton="true"] {
                min-height: 40px;
                min-width: 40px;
                max-width: 40px;
                border-radius: 12px;
                border: 1px solid #d7e2e9;
                background: #f7fbfd;
                color: #173543;
                font-size: 20px;
                font-weight: 800;
                padding: 0px;
            }
            QToolButton[utilityMenuButton="true"]:hover {
                background: #eef6fa;
                border-color: #8fb6cb;
            }
            QToolButton[utilityMenuButton="true"]:checked {
                background: #e7f2f7;
                border-color: #7fa5b8;
            }
            QToolButton[utilityCloseButton="true"] {
                min-height: 26px;
                min-width: 26px;
                max-width: 26px;
                border-radius: 8px;
                border: 1px solid transparent;
                background: transparent;
                color: #6e808a;
                font-size: 13px;
                font-weight: 800;
                padding: 0px;
            }
            QToolButton[utilityCloseButton="true"]:hover {
                background: #fff1f0;
                border: 1px solid #efb6b1;
                color: #c24a42;
            }
            QToolButton[utilityCloseButton="true"]:pressed {
                background: #f8d7d4;
                border: 1px solid #e39c96;
                color: #b53f37;
            }
            QFrame#utilityMenuPanel {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #fbfdff, stop:1 #f3f8fb);
                border: 1px solid #d7e2e9;
                border-radius: 22px;
            }
            QFrame#utilityMenuPanel[utilityAccent="true"] {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #e2edf2, stop:1 #c8dde6);
                border: 1px solid #b6ccd6;
                border-radius: 22px;
            }
            QFrame#utilityUserCard {
                background: #f5fafc;
                border: none;
                border-radius: 14px;
            }
            QLabel[utilityMenuTitle="true"] {
                color: #173543;
                font-size: 16px;
                font-weight: 700;
            }
            QLabel[utilityHeaderIcon="true"] {
                background: #e8f3f8;
                border: 1px solid #cfe0e8;
                border-radius: 14px;
                color: #204a5d;
                font-size: 14px;
                font-weight: 800;
                min-width: 28px;
                max-width: 28px;
                min-height: 28px;
                max-height: 28px;
                padding: 0px;
            }
            QLabel[utilityUserName="true"] {
                color: #1a3d4d;
                font-size: 12px;
                font-weight: 700;
            }
            QLabel[utilityUserEmail="true"] {
                color: #637a86;
                font-size: 11px;
            }
            QPushButton[utilityItem="true"] {
                min-height: 34px;
                min-width: 0px;
                border-radius: 10px;
                border: 1px solid #d8e4ea;
                background: #fdfefe;
                color: #173543;
                padding: 6px 11px;
                text-align: left;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton[utilityItem="true"][utilityOutlined="true"] {
                border: 1px solid #d8e4ea;
                background: #fdfefe;
                color: #14394c;
            }
            QPushButton[utilityItem="true"]:hover {
                background: #cfeaf4;
                border: 1px solid #4c8ea4;
                color: #103647;
            }
            QPushButton[utilityItem="true"]:pressed {
                background: #c1dfeb;
                border: 1px solid #346b7d;
                color: #103444;
            }
            QPushButton[utilityItem="true"][utilityActive="true"] {
                background: #d7ecf4;
                border: 1px solid #72a2b5;
                color: #12394b;
            }
            QPushButton[utilityItem="true"][utilityTone="danger"][utilityOutlined="true"] {
                border: 1px solid #d8e4ea;
                background: #fdfefe;
                color: #173543;
            }
            QLabel[utilitySection="true"] {
                color: #4f6977;
                font-size: 11px;
                font-weight: 800;
                letter-spacing: 0.4px;
                padding: 0px 4px 0px 4px;
            }
            """
        )

        self.light_stylesheet = self.styleSheet()
        self.dark_mode = False
        self._dialog_theme_filter_installed = False

        self.config = AppConfig()
        self.credential_store = CredentialStore()
        self.email_service = EmailService()
        self.otp_service = OTPService()
        self.device_manager = DeviceManager()
        self.recent_presentations = list(self.config.get("recent_presentations"))
        self.command_history_entries = list(self.config.get("command_history"))
        self.practice_mode_enabled = bool(self.config.get("practice_mode"))
        self.custom_voice_commands = dict(self.config.get("custom_voice_commands"))
        self.custom_gesture_actions = dict(self.config.get("custom_gesture_actions"))
        self.gesture_profile_name = str(self.config.get("gesture_profile"))
        self.voice_feedback_mode = str(self.config.get("voice_feedback_mode"))
        if self.voice_feedback_mode == "silent":
            self.voice_feedback_mode = "unknown_only"
            self.config.set("voice_feedback_mode", self.voice_feedback_mode)
        self.voice_feedback_beep_style = str(self.config.get("voice_feedback_beep_style"))
        self.show_camera_overlays = bool(self.config.get("show_camera_overlays"))
        self.user_preferences = dict(self.config.get("user_preferences"))
        self.admin_activity_entries = list(self.config.get("admin_activity_log"))
        self.auto_lock_minutes = 0
        self.config.set("auto_lock_minutes", 0)
        self.keyboard_shortcuts_enabled = bool(self.config.get("keyboard_shortcuts_enabled"))
        self.current_presentation_path = ""
        self.presentation_timer_running = False
        self.presentation_timer_started_at = 0.0
        self.presentation_timer_elapsed_seconds = 0.0
        self.presentation_timer_tick = QTimer(self)
        self.presentation_timer_tick.setInterval(1000)
        self.presentation_timer_tick.timeout.connect(self._update_presentation_timer_labels)
        self.auto_lock_check_timer = QTimer(self)
        self.auto_lock_check_timer.setInterval(1000)
        self.auto_lock_check_timer.timeout.connect(self._check_auto_lock)
        self.last_activity_at = time.monotonic()
        self.email_change_verified_email = ""
        self.email_change_verified_code = ""
        self.email_change_last_otp_attempt = ""
        self.email_change_failed_code = ""
        self.email_change_resend_available = False
        self.email_change_resend_seconds_remaining = 0
        self.email_change_otp_timer = QTimer(self)
        self.email_change_otp_timer.setInterval(1000)
        self.email_change_otp_timer.timeout.connect(self._tick_email_change_otp_cooldown)
        self.camera_manager = CameraManager()
        self.hand_detector = HandDetector()
        self.gesture_classifier = GestureClassifier()
        self.slide_controller = SlideController()
        self.cooldown_manager = CooldownManager()
        self.audio_feedback = AudioFeedback()
        self.audio_feedback.set_enabled(bool(self.config.get("sound_enabled")))
        self.audio_feedback.set_beep_style(self.voice_feedback_beep_style)
        self.slide_controller.set_auto_focus_enabled(
            self.config.get("auto_focus_presentation")
        )

        # Offline voice listener for presentation commands
        self.voice_command_received.connect(self.handle_voice_command)
        self.voice_listener = VoiceListener(
            model_path=str(resource_path("models", "vosk-model-small-en-us-0.15")),
            device_name=self.config.get("voice_device_name"),
            on_command=lambda text: self.voice_command_received.emit(text),
        )


        self.current_mode = AppState.CONTROL_MODE
        self.last_control_gesture = None
        self.control_gesture_frames = 0
        self.last_jump_count = None
        self.last_jump_seen_at = 0
        self.control_hold_frames = self.config.get("control_hold_frames")
        self.jump_hold_seconds = self.config.get("jump_hold_seconds")


        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)


        central_widget = QWidget()
        self.central_widget = central_widget
        self.setCentralWidget(central_widget)

        root_layout = QVBoxLayout()
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        central_widget.setLayout(root_layout)

        self.main_splitter = QSplitter(Qt.Horizontal)
        self.default_splitter_sizes = [380, 980]

        # Left side: fixed status area + scrollable controls area
        sidebar_widget = QWidget()
        sidebar_widget.setObjectName("sidebarWidget")
        self.sidebar_widget = sidebar_widget
        sidebar_widget.setStyleSheet("QWidget#sidebarWidget { background: #d7e6ed; }")
        sidebar_main_layout = QVBoxLayout()
        sidebar_main_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_main_layout.setSpacing(0)
        sidebar_widget.setLayout(sidebar_main_layout)

        # Scrollable controls area (status area will be added later after info_grid is created)
        sidebar_scroll = QScrollArea()
        sidebar_scroll.setObjectName("sidebarScroll")
        self.sidebar_scroll = sidebar_scroll
        sidebar_scroll.setWidgetResizable(True)
        sidebar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sidebar_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        sidebar_scroll.setFocusPolicy(Qt.NoFocus)
        sidebar_scroll.setMinimumWidth(340)
        sidebar_scroll.setStyleSheet(
            "QScrollArea#sidebarScroll { border: none; background: #d7e6ed; }"
            "QScrollArea#sidebarScroll > QWidget { background: #d7e6ed; }"
        )

        sidebar_container = QWidget()
        sidebar_container.setObjectName("sidebarContainer")
        sidebar_container.setStyleSheet("QWidget#sidebarContainer { background: #d7e6ed; }")
        sidebar_layout = QVBoxLayout()
        sidebar_layout.setContentsMargins(20, 20, 20, 20)
        sidebar_layout.setSpacing(14)
        sidebar_container.setLayout(sidebar_layout)
        sidebar_container.setFocusPolicy(Qt.NoFocus)
        sidebar_scroll.setWidget(sidebar_container)
        self.sidebar_container = sidebar_container

        # Right side: camera area
        camera_area = QWidget()
        camera_layout = QVBoxLayout()
        camera_layout.setContentsMargins(24, 14, 24, 24)
        camera_layout.setSpacing(12)
        camera_area.setLayout(camera_layout)

        camera_card = QFrame()
        camera_card.setObjectName("cameraCard")
        self.camera_card = camera_card
        camera_card_layout = QVBoxLayout()
        camera_card_layout.setContentsMargins(22, 14, 22, 22)
        camera_card_layout.setSpacing(12)
        camera_card.setLayout(camera_card_layout)

        root_layout.addWidget(self.main_splitter)
        self.main_splitter.addWidget(sidebar_widget)
        self.main_splitter.addWidget(camera_area)
        self.main_splitter.setSizes(self.default_splitter_sizes)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.setHandleWidth(10)
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)


        self.header_label = BrandHeadingLabel(
            "VisionSlide",
            "Gesture • Voice • Slides",
            centered=True,
            center_offset_x=-12,
            brand_size=29,
            kicker_size=9,
        )
        self._apply_header_branding()

        self.utility_menu_button = QToolButton()
        self.utility_menu_button.setProperty("utilityMenuButton", "true")
        self.utility_menu_button.setText("\u2630")
        self.utility_menu_button.setToolTip("Open sidebar menu")
        self.utility_menu_open = False
        self.utility_action_active = False

        header_widget = QWidget()
        header_widget.setObjectName("sidebarHeader")
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(20, 20, 20, 20)
        header_layout.setSpacing(12)
        header_widget.setLayout(header_layout)
        header_layout.addWidget(self.utility_menu_button, 0, Qt.AlignVCenter)
        header_layout.addWidget(self.header_label, 1)
        header_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        sidebar_main_layout.addWidget(header_widget)




        self.camera_label = QLabel("Camera preview will appear here")
        self.camera_label.setAlignment(Qt.AlignCenter)
        self.camera_label.setMinimumSize(640, 420)
        self.camera_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.camera_label.setStyleSheet(
            "border: 1px solid #b9d0da; background-color: #dceaf0; color: #1e4a5b; "
            "font-size: 16px; border-radius: 24px; padding: 12px;"
        )

        side_panel = QFrame()
        side_panel.setMinimumWidth(340)
        side_panel.setMaximumWidth(420)
        side_panel.setObjectName("sidePanel")
        self.side_panel = side_panel


        side_panel.setStyleSheet(
            "#sidePanel {"
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #e2edf2, stop:1 #c8dde6);"
            "border: 1px solid #b6ccd6;"
            "border-radius: 28px;"
            "}"
        )




        side_layout = QVBoxLayout()
        side_layout.setContentsMargins(12, 12, 12, 12)
        side_layout.setSpacing(10)
        side_panel.setLayout(side_layout)

        self.mode_value = NoWheelComboBox()
        self.mode_value.setObjectName("statusModeCombo")
        self.mode_value.addItem("Control", AppState.CONTROL_MODE)
        self.mode_value.addItem("Jump", AppState.JUMP_MODE)
        self.mode_value.setCurrentIndex(0)
        self.status_value = QLabel("No hand detected")
        self.gesture_value = QLabel("None")
        self.action_value = QLabel("None")
        self.voice_value = QLabel("None")

        for value_label in [
            self.status_value,
            self.gesture_value,
            self.action_value,
            self.voice_value,
        ]:
            value_label.setProperty("stateBadge", "true")
            value_label.setWordWrap(True)
            value_label.setStyleSheet("font-size: 13px; padding: 8px 12px;")
            value_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            value_label.setFixedHeight(54)
            value_label.setFocusPolicy(Qt.NoFocus)

        self.mode_value.setProperty("stateBadge", "true")
        self.mode_value.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.mode_value.setFixedHeight(34)
        self.mode_value.setFocusPolicy(Qt.NoFocus)
        self.mode_value.setCursor(Qt.PointingHandCursor)
        self.mode_value.view().setCursor(Qt.PointingHandCursor)
        self._apply_mode_value_theme()

        status_heading_labels = []
        for heading_text in ["Mode", "Status", "Gesture", "Action", "Voice"]:
            heading_label = QLabel(heading_text)
            heading_label.setAlignment(Qt.AlignCenter)
            heading_label.setMinimumHeight(28)
            heading_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            status_heading_labels.append(heading_label)
        self.status_heading_labels = status_heading_labels
        self._apply_sidebar_surface_theme()

        info_grid = QGridLayout()
        info_grid.setHorizontalSpacing(8)
        info_grid.setVerticalSpacing(14)
        info_grid.addWidget(status_heading_labels[0], 0, 0)
        info_grid.addWidget(self.mode_value, 0, 1)
        info_grid.addWidget(status_heading_labels[1], 1, 0)
        info_grid.addWidget(self.status_value, 1, 1)
        info_grid.addWidget(status_heading_labels[2], 2, 0)
        info_grid.addWidget(self.gesture_value, 2, 1)
        info_grid.addWidget(status_heading_labels[4], 3, 0)
        info_grid.addWidget(self.voice_value, 3, 1)
        info_grid.addWidget(status_heading_labels[3], 4, 0)
        info_grid.addWidget(self.action_value, 4, 1)

        status_group = QGroupBox("Live Status")
        status_group.setTitle("")
        status_layout = QVBoxLayout()
        status_layout.setContentsMargins(16, 16, 16, 16)
        status_layout.setSpacing(14)
        status_group.setLayout(status_layout)
        status_layout.addLayout(info_grid)

        sidebar_main_layout.addWidget(sidebar_scroll)
        self.start_button = QPushButton("Start Camera")
        self.stop_button = QPushButton("Stop Camera")
        self.start_button.setProperty("cameraControl", "true")
        self.stop_button.setProperty("cameraControl", "true")
        self.lock_security_button = QPushButton("Lock && Security")
        self.manage_users_button = QPushButton("Manage Users")
        self.reset_settings_button = QPushButton("Reset Settings")
        self.open_presentation_button = QPushButton("Open Presentation")
        self.recent_files_button = QPushButton("Recent Files")
        self.practice_mode_button = QPushButton("Practice Mode")
        self.command_history_button = QPushButton("Command History")
        self.custom_voice_commands_button = QPushButton("Custom Voice Commands")
        self.custom_gesture_actions_button = QPushButton("Custom Gesture Actions")
        self.gesture_profiles_button = QPushButton("Gesture Profiles")
        self.voice_feedback_button = QPushButton("Voice Feedback")
        self.presentation_timer_button = QPushButton("Presentation Timer")
        self.camera_overlays_button = QPushButton("Camera Overlays")
        self.export_profile_button = QPushButton("Export Profile")
        self.user_preferences_button = QPushButton("User Preferences")
        self.admin_activity_log_button = QPushButton("Admin Activity Log")
        self.auto_lock_button = QPushButton("Auto Lock")
        self.keyboard_shortcuts_button = QPushButton("Shortcut Keys")
        self.tutorial_button = QPushButton("Tutorial")
        self.voice_settings_button = QPushButton("Microphone Settings")
        self.quick_help_button = QPushButton("Quick Help")
        self.about_button = QPushButton("About VisionSlide")
        self.logout_button = QPushButton("Logout")
        self.start_button.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.stop_button.setIcon(self.style().standardIcon(QStyle.SP_MediaStop))
        self.lock_security_button.setIcon(QIcon(str(self.assets_dir / "lock_security_menu_icon.svg")))
        self.manage_users_button.setIcon(QIcon(str(self.assets_dir / "manage_users_icon.svg")))
        self.reset_settings_button.setIcon(QIcon(str(self.assets_dir / "reset_settings_icon.svg")))
        self.open_presentation_button.setIcon(self.style().standardIcon(QStyle.SP_DialogOpenButton))
        self.recent_files_button.setIcon(self.style().standardIcon(QStyle.SP_FileDialogDetailedView))
        self.practice_mode_button.setIcon(self.style().standardIcon(QStyle.SP_MediaSeekForward))
        self.command_history_button.setIcon(self.style().standardIcon(QStyle.SP_FileDialogContentsView))
        self.custom_voice_commands_button.setIcon(self.style().standardIcon(QStyle.SP_CommandLink))
        self.custom_gesture_actions_button.setIcon(self.style().standardIcon(QStyle.SP_CommandLink))
        self.gesture_profiles_button.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        self.voice_feedback_button.setIcon(self.style().standardIcon(QStyle.SP_MediaVolume))
        self.presentation_timer_button.setIcon(self.style().standardIcon(QStyle.SP_FileDialogInfoView))
        self.camera_overlays_button.setIcon(self.style().standardIcon(QStyle.SP_DesktopIcon))
        self.export_profile_button.setIcon(self.style().standardIcon(QStyle.SP_DialogSaveButton))
        self.user_preferences_button.setIcon(self.style().standardIcon(QStyle.SP_FileDialogListView))
        self.admin_activity_log_button.setIcon(self.style().standardIcon(QStyle.SP_FileDialogContentsView))
        self.auto_lock_button.setIcon(self.style().standardIcon(QStyle.SP_MessageBoxWarning))
        self.keyboard_shortcuts_button.setIcon(self.style().standardIcon(QStyle.SP_ArrowRight))
        self.tutorial_button.setIcon(self.style().standardIcon(QStyle.SP_DialogHelpButton))
        self.voice_settings_button.setIcon(self.style().standardIcon(QStyle.SP_MediaVolume))
        self.quick_help_button.setIcon(QIcon(str(self.assets_dir / "quick_help_icon.svg")))
        self.about_button.setIcon(QIcon(str(self.assets_dir / "about_icon.svg")))
        self.logout_button.setIcon(QIcon(str(self.assets_dir / "logout_icon.svg")))
        self.manage_users_button.hide()

        # Set NoFocus on all buttons to prevent auto-scrolling
        for button in [
            self.start_button,
            self.stop_button,
            self.lock_security_button,
            self.manage_users_button,
            self.reset_settings_button,
            self.open_presentation_button,
            self.recent_files_button,
            self.practice_mode_button,
            self.command_history_button,
            self.custom_voice_commands_button,
            self.custom_gesture_actions_button,
            self.gesture_profiles_button,
            self.voice_feedback_button,
            self.presentation_timer_button,
            self.camera_overlays_button,
            self.export_profile_button,
            self.user_preferences_button,
            self.admin_activity_log_button,
            self.auto_lock_button,
            self.keyboard_shortcuts_button,
            self.tutorial_button,
            self.voice_settings_button,
            self.quick_help_button,
            self.about_button,
            self.logout_button,
            self.utility_menu_button,
        ]:
            button.setFocusPolicy(Qt.NoFocus)
        self.start_button.setCursor(Qt.PointingHandCursor)
        self.stop_button.setCursor(Qt.PointingHandCursor)
        attach_hover_bounce(self.start_button)
        attach_hover_bounce(self.stop_button)

        for utility_button in [
            self.lock_security_button,
            self.manage_users_button,
            self.reset_settings_button,
            self.voice_settings_button,
            self.quick_help_button,
            self.about_button,
            self.logout_button,
        ]:
            if utility_button is not None:
                utility_button.setProperty("utilityItem", "true")
                utility_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                utility_button.setIconSize(QSize(16, 16))
                utility_button.setMouseTracking(True)
                utility_button.setAttribute(Qt.WA_Hover, True)
                utility_button.setCursor(Qt.PointingHandCursor)
                attach_hover_bounce(utility_button, y_offset=0, duration=175)
        self.open_presentation_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._style_tools_button(self.open_presentation_button)
        for tools_button in [
            self.voice_feedback_button,
            self.custom_voice_commands_button,
            self.custom_gesture_actions_button,
            self.practice_mode_button,
            self.recent_files_button,
            self.command_history_button,
            self.admin_activity_log_button,
            self.user_preferences_button,
            self.presentation_timer_button,
            self.gesture_profiles_button,
            self.keyboard_shortcuts_button,
        ]:
            tools_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self._style_tools_button(tools_button)
        # Remove duplicate utility_menu_button creation
        # Settings widgets for the side menu
        self.camera_index_input = QComboBox()
        self.control_hold_input = NoWheelSpinBox()
        self.jump_hold_input = NoWheelDoubleSpinBox()
        self.auto_focus_checkbox = QCheckBox("Auto Focus Presentation")
        self.gesture_checkbox = QCheckBox("Gesture Control Enabled")
        self.voice_checkbox = QCheckBox("Voice Control Enabled")
        self.voice_checkbox.setFocusPolicy(Qt.NoFocus)
        self.theme_checkbox = QCheckBox("Dark Mode Enabled")
        self.theme_checkbox.setFocusPolicy(Qt.NoFocus)
        self.sound_feedback_checkbox = QCheckBox("")
        self.practice_mode_checkbox = QCheckBox("Practice Mode Enabled")
        self.keyboard_shortcuts_checkbox = QCheckBox("")
        self.voice_feedback_link = QPushButton("Sound Settings")
        self.gesture_profiles_link = QPushButton("Gesture Profiles")
        self.keyboard_shortcuts_link = QPushButton("Shortcut Keys")
        self.voice_device_input = QComboBox()
        self.voice_test_button = QPushButton("Test Microphone")
        self.voice_refresh_button = QPushButton("ÃƒÂ°Ã…Â¸Ã¢â‚¬ÂÃ¢â‚¬Å¾")
        self.voice_refresh_button.setToolTip("Refresh microphone list")
        self.voice_refresh_button.setMaximumWidth(40)
        self.voice_device_input.hide()
        self.voice_test_button.hide()
        self.voice_refresh_button.hide()
        self.voice_feedback_link.setProperty("textLink", "true")
        self.gesture_profiles_link.setProperty("textLink", "true")
        self.keyboard_shortcuts_link.setProperty("textLink", "true")
        self.total_slides_input = QSpinBox()
        self.account_username_value = QLabel(self.current_user or "Not available")
        self.account_email_value = QLabel(self.current_email or "Not available")
        self.new_username_input = QLineEdit()
        self.username_current_password_input = QLineEdit()
        self.new_email_input = QLineEdit()
        self.email_current_password_input = QLineEdit()
        self.email_otp_input = QLineEdit()
        self.security_current_password_input = QLineEdit()
        self.security_new_password_input = QLineEdit()
        self.security_confirm_password_input = QLineEdit()
        self.username_feedback_label = QLabel(" ")
        self.username_password_feedback_label = QLabel(" ")
        self.email_feedback_label = QLabel(" ")
        self.email_password_feedback_label = QLabel(" ")
        self.email_otp_feedback_label = QLabel(" ")
        self.password_current_feedback_label = QLabel(" ")
        self.password_new_feedback_label = QLabel(" ")
        self.password_confirm_feedback_label = QLabel(" ")
        self.security_status_label = QLabel(" ")
        self.update_username_button = QPushButton("Update Username")
        self.send_email_otp_button = QPushButton("Send OTP")
        self.resend_email_otp_button = QPushButton("Resend OTP")
        self.update_email_button = QPushButton("Update Email")
        self.update_password_button = QPushButton("Update Password")
        self.send_email_otp_button.setProperty("textLink", "true")
        self.resend_email_otp_button.setProperty("textLink", "true")
        self.update_username_button.setProperty("smallAction", "true")
        self.update_email_button.setProperty("smallAction", "true")
        self.update_password_button.setProperty("smallAction", "true")

        for value_label in [self.account_username_value, self.account_email_value]:
            value_label.setProperty("securityValue", "true")

        for feedback_label in [
            self.username_feedback_label,
            self.username_password_feedback_label,
            self.email_feedback_label,
            self.email_password_feedback_label,
            self.email_otp_feedback_label,
            self.password_current_feedback_label,
            self.password_new_feedback_label,
            self.password_confirm_feedback_label,
            self.security_status_label,
        ]:
            feedback_label.setProperty("securityMessage", "neutral")
            feedback_label.setWordWrap(True)
            feedback_label.setTextFormat(Qt.RichText)

        self.new_username_input.setPlaceholderText("New username")
        self.username_current_password_input.setPlaceholderText("Current password")
        self.new_email_input.setPlaceholderText("New email")
        self.email_current_password_input.setPlaceholderText("Current password")
        self.email_otp_input.setPlaceholderText("Enter OTP code")
        self.security_current_password_input.setPlaceholderText("Current password")
        self.security_new_password_input.setPlaceholderText("New password")
        self.security_confirm_password_input.setPlaceholderText("Confirm new password")
        self.email_otp_input.setEnabled(False)
        self.email_otp_input.setMaxLength(6)
        self.send_email_otp_button.setEnabled(False)
        self.resend_email_otp_button.setEnabled(False)

        for password_input in [
            self.username_current_password_input,
            self.email_current_password_input,
            self.security_current_password_input,
            self.security_new_password_input,
            self.security_confirm_password_input,
        ]:
            password_input.setEchoMode(QLineEdit.Password)
            self._add_password_toggle(password_input)

        self.control_hold_input.setSingleStep(1)
        self.jump_hold_input.setSingleStep(0.1)
        self.total_slides_input.setSingleStep(1)
        self.control_hold_input.lineEdit().setReadOnly(True)
        self.jump_hold_input.lineEdit().setReadOnly(True)
        self.control_hold_input.setButtonSymbols(QAbstractSpinBox.UpDownArrows)
        self.jump_hold_input.setButtonSymbols(QAbstractSpinBox.UpDownArrows)
        self.total_slides_input.setButtonSymbols(QAbstractSpinBox.UpDownArrows)
        self.control_hold_input.setFocusPolicy(Qt.NoFocus)
        self.jump_hold_input.setFocusPolicy(Qt.NoFocus)
        self.total_slides_input.setFocusPolicy(Qt.NoFocus)
        self.camera_index_input.setFocusPolicy(Qt.NoFocus)
        self.auto_focus_checkbox.setFocusPolicy(Qt.NoFocus)
        self.gesture_checkbox.setFocusPolicy(Qt.NoFocus)
        self.sound_feedback_checkbox.setFocusPolicy(Qt.NoFocus)
        self.practice_mode_checkbox.setFocusPolicy(Qt.NoFocus)
        self.practice_mode_checkbox.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.voice_device_input.setFocusPolicy(Qt.NoFocus)
        self.voice_test_button.setFocusPolicy(Qt.NoFocus)
        self.voice_refresh_button.setFocusPolicy(Qt.NoFocus)
        self.keyboard_shortcuts_checkbox.setFocusPolicy(Qt.NoFocus)
        self.voice_feedback_link.setFocusPolicy(Qt.NoFocus)
        self.gesture_profiles_link.setFocusPolicy(Qt.NoFocus)
        self.keyboard_shortcuts_link.setFocusPolicy(Qt.NoFocus)
        self.new_username_input.setFocusPolicy(Qt.NoFocus)
        self.username_current_password_input.setFocusPolicy(Qt.NoFocus)
        self.new_email_input.setFocusPolicy(Qt.NoFocus)
        self.email_current_password_input.setFocusPolicy(Qt.NoFocus)
        self.email_otp_input.setFocusPolicy(Qt.NoFocus)
        self.security_current_password_input.setFocusPolicy(Qt.NoFocus)
        self.security_new_password_input.setFocusPolicy(Qt.NoFocus)
        self.security_confirm_password_input.setFocusPolicy(Qt.NoFocus)
        self.update_username_button.setFocusPolicy(Qt.NoFocus)
        self.send_email_otp_button.setFocusPolicy(Qt.NoFocus)
        self.resend_email_otp_button.setFocusPolicy(Qt.NoFocus)
        self.update_email_button.setFocusPolicy(Qt.NoFocus)
        self.update_password_button.setFocusPolicy(Qt.NoFocus)

        self.camera_footer_label = QLabel("Camera: Stopped")
        self.camera_footer_label.setProperty("footerLabel", "true")
        self.camera_footer_label.setProperty("footerKey", "camera")
        self.camera_state_badge = QLabel("Stopped")
        self.camera_state_badge.setProperty("stateBadge", "true")
        self.camera_state_badge.setMinimumHeight(30)
        self.camera_state_badge.setFocusPolicy(Qt.NoFocus)
        self.camera_state_badge.hide()
        self.voice_footer_label = QLabel("Voice:")
        self.voice_footer_label.setProperty("footerLabel", "true")
        self.voice_footer_label.setProperty("footerKey", "voice")
        self.voice_indicator_label = QLabel("Voice: Off")
        self.voice_indicator_label.setProperty("footerLabel", "true")
        self.voice_indicator_label.setProperty("footerKey", "voice_status")
        self.user_footer_label = QLabel(f"User: {self.current_user}")
        self.user_footer_label.setProperty("footerLabel", "true")
        self.user_footer_label.setProperty("footerKey", "user")
        self.footer_info_label = QLabel(" ")
        self.footer_info_label.setObjectName("footerInfoLabel")
        self.footer_info_label.setWordWrap(True)
        self.footer_info_label.setTextFormat(Qt.RichText)
        self.footer_info_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.footer_info_label.setMaximumWidth(280)
        self.footer_info_label.hide()
        self.sidebar_info_label = QLabel(" ")
        self.sidebar_info_label.setObjectName("sidebarInfoLabel")
        self.sidebar_info_label.setWordWrap(True)
        self.sidebar_info_label.setTextFormat(Qt.RichText)
        self.sidebar_info_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.sidebar_info_label.setMaximumWidth(260)
        self.sidebar_info_label.hide()
        self._setup_info_label_animation(self.sidebar_info_label)
        self.sidebar_info_delay_timer = QTimer(self)
        self.sidebar_info_delay_timer.setSingleShot(True)
        self.sidebar_info_delay_timer.setInterval(700)
        self.sidebar_info_delay_timer.timeout.connect(self._show_pending_sidebar_info)
        self.footer_info_delay_timer = QTimer(self)
        self.footer_info_delay_timer.setSingleShot(True)
        self.footer_info_delay_timer.setInterval(700)
        self.footer_info_delay_timer.timeout.connect(self._show_pending_footer_info)
        self._pending_sidebar_help = None
        self._pending_footer_help = None
        self._refresh_account_security_info()
        self._refresh_voice_listener_commands()
        self._update_keyboard_shortcuts()
        self.auto_lock_check_timer.stop()
        self._clear_security_messages()
        self._refresh_admin_actions_visibility()
        self._set_camera_empty_state("Camera stopped", "Press Start Camera to begin tracking again.")
        self._sync_mode_dropdown()
        self._sync_camera_buttons(False)
        self._set_badge(self.camera_state_badge, "Stopped", "muted")
        self._set_recent_activity("Ready for camera start", "muted")
        self._set_badge(self.gesture_value, "None", "muted")
        self._set_badge(self.action_value, "None", "muted")
        self._set_badge(self.voice_value, "None", "muted")
        self._apply_clickable_cursors(self)
        for control in [
            getattr(self, "control_hold_label", None),
            getattr(self, "jump_hold_label", None),
            getattr(self, "control_hold_input", None),
            getattr(self, "jump_hold_input", None),
        ]:
            if control is not None:
                control.setCursor(Qt.PointingHandCursor)
                control.setAttribute(Qt.WA_Hover, True)
                attach_hover_bounce(control, y_offset=2, duration=175)
        for checkbox in [
            getattr(self, "auto_focus_checkbox", None),
            getattr(self, "gesture_checkbox", None),
            getattr(self, "voice_checkbox", None),
            getattr(self, "theme_checkbox", None),
            getattr(self, "sound_feedback_checkbox", None),
            getattr(self, "practice_mode_checkbox", None),
            getattr(self, "keyboard_shortcuts_checkbox", None),
        ]:
            if checkbox is not None:
                checkbox.setMouseTracking(True)
                checkbox.setAttribute(Qt.WA_Hover, True)
                checkbox.installEventFilter(self)
                self._update_setting_checkbox_cursor(checkbox, None)
                attach_hover_bounce(checkbox, y_offset=2, duration=175)

        for settings_link in [
            getattr(self, "voice_feedback_link", None),
            getattr(self, "gesture_profiles_link", None),
            getattr(self, "keyboard_shortcuts_link", None),
        ]:
            if settings_link is not None:
                settings_link.setCursor(Qt.PointingHandCursor)
                settings_link.setMouseTracking(True)
                settings_link.setAttribute(Qt.WA_Hover, True)
                attach_hover_bounce(settings_link, y_offset=2, duration=175)



        # Do not scan cameras repeatedly; use saved/default camera only
        saved_camera_index = self.config.get("camera_index")
        self.camera_index_input.addItem("Default Camera", saved_camera_index)
        self.camera_index_input.setCurrentIndex(0)
        self.camera_manager.camera_index = saved_camera_index



        # Number of stable frames needed for control gestures
        self.control_hold_input.setRange(1, 10)
        self.control_hold_input.setValue(self.config.get("control_hold_frames"))

        # Hold time for jump mode
        self.jump_hold_input.setRange(0.1, 3.0)
        self.jump_hold_input.setSingleStep(0.1)
        self.jump_hold_input.setValue(self.config.get("jump_hold_seconds"))
        self.total_slides_input.setRange(1, 500)
        self.total_slides_input.setValue(self.config.get("total_slides"))
        # Presentation focus toggle
        self.auto_focus_checkbox.setChecked(
        self.config.get("auto_focus_presentation")
)
        # Gesture and voice toggles
        self.gesture_checkbox.setChecked(self.config.get("gesture_enabled"))
        self.sound_feedback_checkbox.setChecked(bool(self.config.get("sound_enabled")))
        self.practice_mode_checkbox.setChecked(self.practice_mode_enabled)

        # Ensure voice control starts disabled on app open
        self.config.set("voice_enabled", False)
        self.voice_checkbox.setChecked(False)
        self.keyboard_shortcuts_checkbox.setChecked(self.keyboard_shortcuts_enabled)

        self.mode_value.currentIndexChanged.connect(self._change_mode_from_dropdown)
        self.start_button.clicked.connect(
            lambda: self._run_with_busy_button(
                self.start_button,
                "Starting...",
                self.start_camera,
                restore_enabled=False,
            )
        )
        self.stop_button.clicked.connect(
            lambda: self._run_with_busy_button(
                self.stop_button,
                "Stopping...",
                self.stop_camera,
                restore_enabled=False,
            )
        )
        self.lock_security_button.clicked.connect(
            lambda: self._open_utility_action(self.lock_security_button, self.show_lock_security)
        )
        self.manage_users_button.clicked.connect(
            lambda: self._open_utility_action(self.manage_users_button, self.show_manage_users)
        )
        self.reset_settings_button.clicked.connect(
            lambda: self._open_utility_action(self.reset_settings_button, self.show_reset_settings_dialog)
        )
        self.open_presentation_button.clicked.connect(
            self.open_presentation_file
        )
        self.recent_files_button.clicked.connect(self.show_recent_files_dialog)
        self.practice_mode_button.clicked.connect(self.show_practice_mode_dialog)
        self.command_history_button.clicked.connect(self.show_command_history_dialog)
        self.custom_voice_commands_button.clicked.connect(self.show_custom_voice_commands_dialog)
        self.custom_gesture_actions_button.clicked.connect(self.show_custom_gesture_actions_dialog)
        self.gesture_profiles_button.clicked.connect(self.show_gesture_profiles_dialog)
        self.voice_feedback_button.clicked.connect(self.show_voice_feedback_dialog)
        self.presentation_timer_button.clicked.connect(self.show_presentation_timer_dialog)
        self.camera_overlays_button.clicked.connect(self.show_camera_overlays_dialog)
        self.export_profile_button.clicked.connect(self.show_export_profile_dialog)
        self.admin_activity_log_button.clicked.connect(self.show_admin_activity_log_dialog)
        self.auto_lock_button.clicked.connect(self.show_auto_lock_dialog)
        self.keyboard_shortcuts_button.clicked.connect(self.show_keyboard_shortcuts_dialog)
        self.tutorial_button.clicked.connect(self.show_tutorial_dialog)
        self.quick_help_button.clicked.connect(
            lambda: self._open_utility_action(self.quick_help_button, self.show_quick_help)
        )
        self.about_button.clicked.connect(
            lambda: self._open_utility_action(self.about_button, self.show_about_dialog)
        )
        self.voice_settings_button.clicked.connect(
            lambda: self._open_utility_action(self.voice_settings_button, self.open_voice_settings_dialog)
        )
        self.logout_button.clicked.connect(
            lambda: self._open_utility_action(self.logout_button, self.show_account_switcher)
        )
        self.utility_menu_button.clicked.connect(self._toggle_utility_menu)

        self.camera_index_input.currentIndexChanged.connect(self.change_camera_index)

        self.control_hold_input.valueChanged.connect(self.change_control_hold_frames)
        self.jump_hold_input.valueChanged.connect(self.change_jump_hold_seconds)
        self.auto_focus_checkbox.toggled.connect(self.toggle_auto_focus)
        self.gesture_checkbox.toggled.connect(self.toggle_gesture_control)
        self.voice_checkbox.toggled.connect(self.toggle_voice_control)
        self.theme_checkbox.toggled.connect(self.toggle_theme)
        self.sound_feedback_checkbox.toggled.connect(self.toggle_sound_feedback_setting)
        self.practice_mode_checkbox.toggled.connect(self.toggle_practice_mode_setting)
        self.keyboard_shortcuts_checkbox.toggled.connect(self.toggle_keyboard_shortcuts_setting)
        self.voice_feedback_link.clicked.connect(self.show_voice_feedback_dialog)
        self.gesture_profiles_link.clicked.connect(self.show_gesture_profiles_dialog)
        self.keyboard_shortcuts_link.clicked.connect(self.show_keyboard_shortcuts_dialog)
        self.total_slides_input.valueChanged.connect(self.change_total_slides)
        self.new_username_input.textChanged.connect(
            lambda text: self._handle_live_security_username(self.new_username_input, self.username_feedback_label)
        )
        self.username_current_password_input.textChanged.connect(
            lambda text: self._handle_live_current_password(
                text,
                self.username_password_feedback_label,
                self.username_current_password_input,
            )
        )
        self.new_email_input.textChanged.connect(self._handle_live_security_email)
        self.new_email_input.textChanged.connect(self._reset_email_change_verification)
        self.email_current_password_input.textChanged.connect(
            lambda text: self._handle_live_current_password(
                text,
                self.email_password_feedback_label,
                self.email_current_password_input,
            )
        )
        self.email_otp_input.textChanged.connect(self._handle_live_email_change_otp_input)
        self.security_current_password_input.textChanged.connect(
            lambda text: self._handle_live_current_password(
                text,
                self.password_current_feedback_label,
                self.security_current_password_input,
            )
        )
        self.security_new_password_input.textChanged.connect(self._handle_live_security_password)
        self.security_confirm_password_input.textChanged.connect(self._handle_live_security_confirm_password)
        self.update_username_button.clicked.connect(self.update_account_username)
        self.send_email_otp_button.clicked.connect(self.send_email_change_otp)
        self.resend_email_otp_button.clicked.connect(self.resend_email_change_otp)
        self.update_email_button.clicked.connect(self.update_account_email)
        self.update_password_button.clicked.connect(self.update_account_password)


        # Settings grid for gesture timing, jump timing, and core toggles
        settings_grid = QGridLayout()
        settings_grid.setHorizontalSpacing(8)
        settings_grid.setVerticalSpacing(8)

        self.control_hold_label = QLabel("Control Hold:")
        settings_grid.addWidget(self.control_hold_label, 0, 0)
        settings_grid.addWidget(self.control_hold_input, 0, 1)

        self.jump_hold_label = QLabel("Jump Hold (s):")
        settings_grid.addWidget(self.jump_hold_label, 1, 0)
        settings_grid.addWidget(self.jump_hold_input, 1, 1)

        settings_grid.addWidget(self.theme_checkbox, 2, 0, 1, 2)
        settings_grid.addWidget(self.auto_focus_checkbox, 3, 0, 1, 2)
        settings_grid.addWidget(self.practice_mode_checkbox, 4, 0, 1, 2)
        settings_grid.addWidget(self.gesture_checkbox, 5, 0, 1, 2)
        settings_grid.addWidget(self.voice_checkbox, 6, 0, 1, 2)
        voice_feedback_row = QHBoxLayout()
        voice_feedback_row.setContentsMargins(0, 0, 0, 0)
        voice_feedback_row.setSpacing(2)
        voice_feedback_row.addWidget(self.sound_feedback_checkbox, 0, Qt.AlignLeft)
        voice_feedback_row.addWidget(self.voice_feedback_link, 0, Qt.AlignLeft)
        voice_feedback_row.addStretch()
        settings_grid.addLayout(voice_feedback_row, 7, 0, 1, 2)

        keyboard_shortcuts_row = QHBoxLayout()
        keyboard_shortcuts_row.setContentsMargins(0, 0, 0, 0)
        keyboard_shortcuts_row.setSpacing(2)
        keyboard_shortcuts_row.addWidget(self.keyboard_shortcuts_checkbox, 0, Qt.AlignLeft)
        keyboard_shortcuts_row.addWidget(self.keyboard_shortcuts_link, 0, Qt.AlignLeft)
        keyboard_shortcuts_row.addStretch()
        settings_grid.addLayout(keyboard_shortcuts_row, 8, 0, 1, 2)

        account_grid = QGridLayout()
        account_grid.setHorizontalSpacing(8)
        account_grid.setVerticalSpacing(8)
        account_grid.addWidget(QLabel("Username:"), 0, 0)
        account_grid.addWidget(self.account_username_value, 0, 1)
        account_grid.addWidget(QLabel("Email:"), 1, 0)
        account_grid.addWidget(self.account_email_value, 1, 1)

        username_form = QGridLayout()
        username_form.setHorizontalSpacing(8)
        username_form.setVerticalSpacing(10)
        username_form.addWidget(QLabel("New Username <span style='color: red;'>*</span>"), 0, 0, 1, 2)
        username_form.addWidget(self.new_username_input, 1, 0, 1, 2)
        username_form.addWidget(self.username_feedback_label, 2, 0, 1, 2)
        username_form.addWidget(QLabel("Current Password <span style='color: red;'>*</span>"), 3, 0, 1, 2)
        username_form.addWidget(self.username_current_password_input, 4, 0, 1, 2)
        username_form.addWidget(self.username_password_feedback_label, 5, 0, 1, 2)
        username_button_row = QHBoxLayout()
        username_button_row.addStretch()
        username_button_row.addWidget(self.update_username_button)
        username_button_row.addStretch()
        username_form.addLayout(username_button_row, 6, 0, 1, 2)

        email_button_row = QHBoxLayout()
        email_button_row.setSpacing(8)
        email_button_row.addStretch()
        email_button_row.addWidget(self.send_email_otp_button)
        email_button_row.addWidget(self.resend_email_otp_button)

        email_form = QGridLayout()
        email_form.setHorizontalSpacing(8)
        email_form.setVerticalSpacing(10)
        email_form.addWidget(QLabel("New Email <span style='color: red;'>*</span>"), 0, 0, 1, 2)
        email_form.addWidget(self.new_email_input, 1, 0, 1, 2)
        email_form.addWidget(self.email_feedback_label, 2, 0, 1, 2)
        email_form.addWidget(QLabel("Current Password <span style='color: red;'>*</span>"), 3, 0, 1, 2)
        email_form.addWidget(self.email_current_password_input, 4, 0, 1, 2)
        email_form.addWidget(self.email_password_feedback_label, 5, 0, 1, 2)
        email_form.addWidget(QLabel("OTP Code <span style='color: red;'>*</span>"), 6, 0, 1, 2)
        email_form.addWidget(self.email_otp_input, 7, 0, 1, 2)
        email_message_button_row = QHBoxLayout()
        email_message_button_row.setSpacing(8)
        email_message_button_row.addWidget(self.email_otp_feedback_label, 1)
        email_message_button_row.addStretch()
        email_message_button_row.addWidget(self.send_email_otp_button)
        email_message_button_row.addWidget(self.resend_email_otp_button)
        email_form.addLayout(email_message_button_row, 8, 0, 1, 2)
        email_update_row = QHBoxLayout()
        email_update_row.addStretch()
        email_update_row.addWidget(self.update_email_button)
        email_update_row.addStretch()
        email_form.addLayout(email_update_row, 9, 0, 1, 2)

        password_form = QGridLayout()
        password_form.setHorizontalSpacing(8)
        password_form.setVerticalSpacing(10)
        password_form.addWidget(QLabel("Current Password <span style='color: red;'>*</span>"), 0, 0, 1, 2)
        password_form.addWidget(self.security_current_password_input, 1, 0, 1, 2)
        password_form.addWidget(self.password_current_feedback_label, 2, 0, 1, 2)
        password_form.addWidget(QLabel("New Password <span style='color: red;'>*</span>"), 3, 0, 1, 2)
        password_form.addWidget(self.security_new_password_input, 4, 0, 1, 2)
        password_form.addWidget(self.password_new_feedback_label, 5, 0, 1, 2)
        password_form.addWidget(QLabel("Confirm New Password <span style='color: red;'>*</span>"), 6, 0, 1, 2)
        password_form.addWidget(self.security_confirm_password_input, 7, 0, 1, 2)
        password_form.addWidget(self.password_confirm_feedback_label, 8, 0, 1, 2)
        password_button_row = QHBoxLayout()
        password_button_row.addStretch()
        password_button_row.addWidget(self.update_password_button)
        password_button_row.addStretch()
        password_form.addLayout(password_button_row, 9, 0, 1, 2)

        current_account_section = QWidget()
        current_account_layout = QVBoxLayout()
        current_account_layout.setContentsMargins(0, 0, 0, 0)
        current_account_layout.setSpacing(10)
        current_account_section.setLayout(current_account_layout)
        current_account_layout.addLayout(account_grid)

        self.username_section = QWidget()
        username_section_layout = QVBoxLayout()
        username_section_layout.setContentsMargins(0, 0, 0, 0)
        username_section_layout.setSpacing(0)
        self.username_section.setLayout(username_section_layout)
        username_section_layout.addLayout(username_form)

        self.email_section = QWidget()
        email_section_layout = QVBoxLayout()
        email_section_layout.setContentsMargins(0, 0, 0, 0)
        email_section_layout.setSpacing(0)
        self.email_section.setLayout(email_section_layout)
        email_section_layout.addLayout(email_form)

        self.password_section = QWidget()
        password_section_layout = QVBoxLayout()
        password_section_layout.setContentsMargins(0, 0, 0, 0)
        password_section_layout.setSpacing(0)
        self.password_section.setLayout(password_section_layout)
        password_section_layout.addLayout(password_form)

        settings_group = QGroupBox("Settings")
        settings_group.setTitle("")
        settings_layout = QVBoxLayout()
        settings_layout.addLayout(settings_grid)
        settings_group.setLayout(settings_layout)

        tools_group = QGroupBox("Tools")
        tools_group.setTitle("")
        tools_layout = QVBoxLayout()
        tools_layout.setContentsMargins(16, 16, 16, 16)
        tools_layout.setSpacing(10)
        tools_layout.addWidget(self.open_presentation_button)
        tools_layout.addWidget(self.custom_voice_commands_button)
        tools_layout.addWidget(self.custom_gesture_actions_button)
        tools_layout.addWidget(self.recent_files_button)
        tools_layout.addWidget(self.command_history_button)
        tools_layout.addWidget(self.admin_activity_log_button)
        tools_layout.addWidget(self.presentation_timer_button)
        tools_layout.addWidget(self.gesture_profiles_button)
        tools_group.setLayout(tools_layout)

        utility_panel = QFrame()
        utility_panel.setObjectName("utilityMenuPanel")
        utility_panel_layout = QVBoxLayout()
        self.utility_panel_layout = utility_panel_layout
        utility_panel_layout.setContentsMargins(12, 12, 12, 12)
        utility_panel_layout.setSpacing(16)
        utility_panel.setLayout(utility_panel_layout)
        utility_title = QLabel("Utility Menu")
        utility_title.setObjectName("utilityMenuTitle")
        utility_title.setProperty("utilityMenuTitle", "true")
        self.utility_title_label = utility_title
        utility_title.setStyleSheet("font-size: 16px; font-weight: 700;")
        self.utility_menu_close_button = QToolButton()
        self.utility_menu_close_button.setProperty("utilityCloseButton", "true")
        self.utility_menu_close_button.setIcon(
            self.style().standardIcon(QStyle.SP_TitleBarCloseButton)
        )
        self.utility_menu_close_button.setIconSize(QSize(14, 14))
        self.utility_menu_close_button.setToolTip("Close utility menu")
        self.utility_menu_close_button.setCursor(Qt.PointingHandCursor)
        attach_hover_bounce(self.utility_menu_close_button, y_offset=2, duration=170)
        self.utility_menu_close_button.clicked.connect(self._close_utility_menu)
        utility_title_row = QHBoxLayout()
        utility_title_row.setContentsMargins(0, 0, 0, 0)
        utility_title_row.setSpacing(8)
        utility_title_row.addWidget(utility_title)
        utility_title_row.addStretch()
        utility_title_row.addWidget(self.utility_menu_close_button, 0, Qt.AlignTop)
        utility_panel_layout.addLayout(utility_title_row)
        utility_user_card = QFrame()
        utility_user_card.setObjectName("utilityUserCard")
        utility_user_card.setMinimumHeight(52)
        utility_user_layout = QHBoxLayout()
        utility_user_layout.setContentsMargins(10, 10, 10, 10)
        utility_user_layout.setSpacing(10)
        utility_user_card.setLayout(utility_user_layout)
        utility_user_badge = QLabel("\U0001F464")
        utility_user_badge.setProperty("utilityHeaderIcon", "true")
        utility_user_badge.setAlignment(Qt.AlignCenter)
        utility_user_text_layout = QVBoxLayout()
        utility_user_text_layout.setContentsMargins(0, 0, 0, 0)
        utility_user_text_layout.setSpacing(1)
        self.utility_user_name_label = QLabel(self.current_user or "User")
        self.utility_user_name_label.setProperty("utilityUserName", "true")
        self.utility_user_email_label = QLabel(self.current_email or "No email")
        self.utility_user_email_label.setProperty("utilityUserEmail", "true")
        utility_user_text_layout.addWidget(self.utility_user_name_label)
        utility_user_text_layout.addWidget(self.utility_user_email_label)
        utility_user_layout.addWidget(utility_user_badge, 0, Qt.AlignTop)
        utility_user_layout.addLayout(utility_user_text_layout, 1)
        utility_panel_layout.addWidget(utility_user_card)
        security_label = QLabel("Security")
        security_label.setProperty("utilitySection", "true")
        security_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        security_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        security_label.setMaximumHeight(14)
        security_section_layout = QVBoxLayout()
        security_section_layout.setContentsMargins(0, 0, 0, 0)
        security_section_layout.setSpacing(2)
        security_section_layout.addWidget(security_label)
        self.utility_security_options_layout = QVBoxLayout()
        self.utility_security_options_layout.setContentsMargins(0, 4, 0, 0)
        self.utility_security_options_layout.setSpacing(12)
        self.utility_security_options_layout.addWidget(self.lock_security_button)
        self.utility_security_options_layout.addWidget(self.manage_users_button)
        self.utility_security_options_layout.addWidget(self.reset_settings_button)
        security_section_layout.addLayout(self.utility_security_options_layout)
        utility_panel_layout.addLayout(security_section_layout)
        utility_panel_layout.addSpacing(14)

        audio_label = QLabel("Audio")
        audio_label.setProperty("utilitySection", "true")
        audio_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        audio_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        audio_label.setMaximumHeight(14)
        audio_section_layout = QVBoxLayout()
        audio_section_layout.setContentsMargins(0, 0, 0, 0)
        audio_section_layout.setSpacing(2)
        audio_section_layout.addWidget(audio_label)
        self.utility_audio_options_layout = QVBoxLayout()
        self.utility_audio_options_layout.setContentsMargins(0, 4, 0, 0)
        self.utility_audio_options_layout.setSpacing(12)
        self.utility_audio_options_layout.addWidget(self.voice_settings_button)
        audio_section_layout.addLayout(self.utility_audio_options_layout)
        utility_panel_layout.addLayout(audio_section_layout)
        utility_panel_layout.addSpacing(6)

        support_label = QLabel("Support")
        support_label.setProperty("utilitySection", "true")
        support_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        support_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        support_label.setMaximumHeight(14)
        support_section_layout = QVBoxLayout()
        support_section_layout.setContentsMargins(0, 0, 0, 0)
        support_section_layout.setSpacing(2)
        support_section_layout.addWidget(support_label)
        self.utility_support_options_layout = QVBoxLayout()
        self.utility_support_options_layout.setContentsMargins(0, 4, 0, 0)
        self.utility_support_options_layout.setSpacing(12)
        self.utility_support_options_layout.addWidget(self.quick_help_button)
        self.utility_support_options_layout.addWidget(self.about_button)
        support_section_layout.addLayout(self.utility_support_options_layout)
        utility_panel_layout.addLayout(support_section_layout)
        utility_panel_layout.addSpacing(6)

        session_label = QLabel("Session")
        session_label.setProperty("utilitySection", "true")
        session_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        session_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        session_label.setMaximumHeight(14)
        session_section_layout = QVBoxLayout()
        session_section_layout.setContentsMargins(0, 0, 0, 0)
        session_section_layout.setSpacing(2)
        session_section_layout.addWidget(session_label)
        self.utility_session_options_layout = QVBoxLayout()
        self.utility_session_options_layout.setContentsMargins(0, 4, 0, 0)
        self.utility_session_options_layout.setSpacing(0)
        self.utility_session_options_layout.addWidget(self.logout_button)
        session_section_layout.addLayout(self.utility_session_options_layout)
        utility_panel_layout.addLayout(session_section_layout)
        utility_panel_layout.addSpacing(24)
        utility_panel_layout.addStretch()
        self.utility_menu_panel = utility_panel
        self.utility_menu_panel.setParent(sidebar_widget)
        self.utility_menu_panel.hide()
        self.utility_menu_panel.setFixedWidth(266)
        self.utility_menu_panel.setMinimumHeight(0)
        utility_shadow = QGraphicsDropShadowEffect(self)
        utility_shadow.setBlurRadius(28)
        utility_shadow.setOffset(0, 12)
        utility_shadow_color = QColor("#000000")
        utility_shadow_color.setAlpha(28)
        utility_shadow.setColor(utility_shadow_color)
        self.utility_menu_panel.setGraphicsEffect(utility_shadow)
        self.utility_menu_opacity_effect = QGraphicsOpacityEffect(self.utility_menu_panel)
        self.utility_menu_opacity_effect.setOpacity(0.0)
        self.utility_menu_panel.setGraphicsEffect(self.utility_menu_opacity_effect)
        self.utility_menu_animation = QPropertyAnimation(self.utility_menu_panel, b"geometry", self)
        self.utility_menu_animation.setDuration(320)
        self.utility_menu_animation.setEasingCurve(QEasingCurve.OutCubic)
        self.utility_menu_animation.finished.connect(self._handle_utility_menu_animation_finished)
        self.utility_menu_opacity_animation = QPropertyAnimation(self.utility_menu_opacity_effect, b"opacity", self)
        self.utility_menu_opacity_animation.setDuration(280)
        self.utility_menu_opacity_animation.setEasingCurve(QEasingCurve.OutCubic)
        self._refresh_admin_actions_visibility()

        footer_strip = QFrame()
        footer_strip.setObjectName("footerStrip")
        self.footer_strip = footer_strip
        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(14, 10, 14, 10)
        footer_layout.setSpacing(18)
        footer_strip.setLayout(footer_layout)
        self.start_button.setProperty("smallAction", "true")
        self.stop_button.setProperty("smallAction", "true")
        self.start_button.setMinimumWidth(128)
        self.stop_button.setMinimumWidth(128)
        camera_button_row = QHBoxLayout()
        camera_button_row.setContentsMargins(0, 0, 0, 0)
        camera_button_row.setSpacing(8)
        camera_button_row.addWidget(self.start_button)
        camera_button_row.addWidget(self.stop_button)
        camera_button_widget = QWidget()
        camera_button_widget.setLayout(camera_button_row)
        footer_layout.addWidget(camera_button_widget, 0, Qt.AlignLeft)
        footer_layout.addWidget(self.camera_footer_label)
        footer_layout.addWidget(self.voice_indicator_label)
        footer_layout.addWidget(self.user_footer_label)
        footer_layout.addStretch()

        for target, blur, offset_y, alpha in [
            (side_panel, 26, 10, 35),
            (camera_card, 28, 12, 32),
            (footer_strip, 18, 6, 24),
        ]:
            shadow = QGraphicsDropShadowEffect(self)
            shadow.setBlurRadius(blur)
            shadow.setOffset(0, offset_y)
            shadow.setColor(Qt.black if alpha > 0 else Qt.transparent)
            color = shadow.color()
            color.setAlpha(alpha)
            shadow.setColor(color)
            target.setGraphicsEffect(shadow)

        side_layout.addWidget(self._build_collapsible_section("Live Status", status_group))
        side_layout.addWidget(self._build_collapsible_section("Settings", settings_group, expanded=False))
        side_layout.addWidget(self._build_collapsible_section("Tools", tools_group, expanded=False))
        side_layout.addStretch()



         # Sidebar content
        sidebar_layout.addWidget(side_panel)
        self.sidebar_info_label.setParent(self.sidebar_container)
        self.sidebar_info_label.raise_()

        # Camera area content
        camera_card_layout.addWidget(footer_strip)
        camera_card_layout.addWidget(self.camera_label, 1)
        camera_layout.addWidget(camera_card, 1)

        self.central_widget.installEventFilter(self)
        sidebar_scroll.installEventFilter(self)
        sidebar_container.installEventFilter(self)
        side_panel.installEventFilter(self)
        camera_area.installEventFilter(self)
        self.camera_footer_label.installEventFilter(self)
        self.voice_footer_label.installEventFilter(self)
        self.voice_indicator_label.installEventFilter(self)
        self.user_footer_label.installEventFilter(self)
        for hover_widget, help_key in {
            self.mode_value: "status_mode",
            self.status_value: "status_tracking",
            self.gesture_value: "status_gesture",
            self.action_value: "status_action",
            self.voice_value: "status_voice",
            self.start_button: "start_camera",
            self.stop_button: "stop_camera",
            self.camera_index_input: "camera_select",
            self.control_hold_input: "control_hold",
            self.jump_hold_input: "jump_hold",
            self.auto_focus_checkbox: "auto_focus",
            self.gesture_checkbox: "gesture_enabled",
            self.voice_checkbox: "voice_enabled",
            self.sound_feedback_checkbox: "sound_feedback_enabled",
            self.voice_feedback_link: "voice_feedback_choice",
            self.practice_mode_checkbox: "practice_mode",
            self.voice_settings_button: "voice_device",
            self.theme_checkbox: "dark_mode",
            self.keyboard_shortcuts_checkbox: "keyboard_shortcuts",
            self.keyboard_shortcuts_link: "keyboard_shortcuts",
            self.voice_device_input: "voice_device",
            self.total_slides_input: "total_slides",
            self.open_presentation_button: "open_presentation",
            self.recent_files_button: "recent_files",
            self.command_history_button: "command_history",
            self.custom_voice_commands_button: "custom_voice_commands",
            self.custom_gesture_actions_button: "custom_gesture_actions",
            self.presentation_timer_button: "presentation_timer",
            self.camera_overlays_button: "camera_overlays",
            self.export_profile_button: "export_profile",
            self.admin_activity_log_button: "admin_activity_log",
            self.auto_lock_button: "auto_lock",
            self.tutorial_button: "tutorial",
            self.lock_security_button: "lock_security",
            self.manage_users_button: "manage_users",
            self.reset_settings_button: "reset_settings",
            self.quick_help_button: "quick_help",
            self.about_button: "about_app",
            self.voice_settings_button: "voice_device",
            self.logout_button: "saved_accounts",
        }.items():
            hover_widget.setProperty("inlineHelpKey", help_key)
            hover_widget.installEventFilter(self)

        app = QApplication.instance()
        if app is not None and not self._dialog_theme_filter_installed:
            app.installEventFilter(self)
            self._dialog_theme_filter_installed = True


    def showEvent(self, event):
        super().showEvent(event)
        if self._startup_reveal_pending:
            self._startup_reveal_pending = False
            QTimer.singleShot(0, self._finish_startup_reveal)

    def _finish_startup_reveal(self):
        if getattr(self, "main_splitter", None) is not None:
            self.main_splitter.setSizes(self.default_splitter_sizes)
        if self.centralWidget() and self.centralWidget().layout():
            self.centralWidget().layout().activate()
        self.setUpdatesEnabled(True)
        self._startup_reveal_animation = QPropertyAnimation(self, b"windowOpacity", self)
        self._startup_reveal_animation.setDuration(320)
        self._startup_reveal_animation.setEasingCurve(QEasingCurve.OutCubic)
        self._startup_reveal_animation.setStartValue(max(0.0, self.windowOpacity()))
        self._startup_reveal_animation.setEndValue(1.0)
        self._startup_reveal_animation.start()

        # Return a cleaned list of useful microphone device names
    def get_input_device_names(self):
        devices = sd.query_devices()
        names = []

        ignored_words = ["speaker", "stereo mix", "output"]

        for device in devices:
            if device["max_input_channels"] > 0:
                device_name = device["name"]

                # Skip devices that are not useful as microphones
                if any(word in device_name.lower() for word in ignored_words):
                    continue

                names.append(device_name)

        return names


        # Choose the most likely built-in microphone from the available list
    def get_preferred_voice_device_name(self, device_names):
        preferred_keywords = [
            "microphone array",
            "internal microphone",
            "built-in",
            "microphone",
            "mic",
        ]

        for keyword in preferred_keywords:
            for device_name in device_names:
                if keyword in device_name.lower():
                    return device_name

        return device_names[0] if device_names else ""

    def show_quick_help(self):
        help_dialog = QDialog(self)
        help_dialog.setWindowTitle("Quick Help")
        self._apply_standard_dialog_size(help_dialog, "standard")
        help_dialog.resize(help_dialog.width(), max(help_dialog.height(), 660))
        if self._is_dark_theme_active():
            help_dialog.setStyleSheet(
                "QDialog { background: #0f1a22; }"
                "QLabel { color: #e7f3f8; font-size: 13px; background: transparent; }"
                "QFrame[helpCard=\"true\"] { background: #132630; border: 1px solid #355768; border-radius: 18px; }"
                "QPushButton { min-height: 40px; border-radius: 12px; border: 1px solid #42697c; "
                "background: #183240; color: #eaf6fb; font-weight: 700; padding: 8px 12px; }"
                "QPushButton:hover { background: #214353; border-color: #5c8aa0; color: #ffffff; }"
                "QPushButton:pressed { background: #122733; border-color: #305465; }"
            )
        else:
            help_dialog.setStyleSheet(
                "QDialog { background: #f7fbfd; }"
                "QLabel { color: #274652; font-size: 13px; }"
                "QFrame[helpCard=\"true\"] { background: #ffffff; border: 1px solid #d7e2e9; border-radius: 18px; }"
                "QPushButton { min-height: 40px; border-radius: 12px; border: 1px solid #ccd8e2; "
                "background: #ffffff; color: #173543; font-weight: 700; padding: 8px 12px; }"
                "QPushButton:hover { background: #cfe5ee; border-color: #3f7c8f; }"
                "QPushButton:pressed { background: #bddbe6; border-color: #346b7d; }"
            )

        layout = QVBoxLayout()
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)
        help_dialog.setLayout(layout)

        overview_card = QFrame()
        overview_card.setProperty("helpCard", "true")
        overview_layout = QVBoxLayout()
        overview_layout.setContentsMargins(16, 16, 16, 16)
        overview_layout.setSpacing(8)
        overview_card.setLayout(overview_layout)

        overview_title = QLabel("Recommended Flow")
        overview_title.setStyleSheet(
            f"font-size: 14px; font-weight: 700; color: {'#eef8fc' if self._is_dark_theme_active() else '#173543'};"
        )
        overview_text = QLabel(
            "1. Sign in with your email and password.\n"
            "2. Open a presentation from Tools or use your normal presentation app.\n"
            "3. Start the camera and choose Control Mode or Jump Mode.\n"
            "4. Enable Voice Control if you want offline spoken commands.\n"
            "5. Use Settings and Tools to adjust microphones, feedback, shortcuts, custom commands, history, and security."
        )
        overview_text.setWordWrap(True)
        overview_layout.addWidget(overview_title)
        overview_layout.addWidget(overview_text)

        getting_started_button = QPushButton("Getting Started")
        getting_started_button.clicked.connect(self.show_quick_help_getting_started)

        control_button = QPushButton("Control && Jump Mode")
        control_button.clicked.connect(self.show_quick_help_control_mode)

        voice_button = QPushButton("Voice Commands")
        voice_button.clicked.connect(self.show_quick_help_voice_commands)

        tools_button = QPushButton("Settings && Tools")
        tools_button.clicked.connect(self.show_quick_help_settings_tools)

        layout.addSpacing(4)
        layout.addWidget(overview_card)
        layout.addWidget(getting_started_button)
        layout.addWidget(control_button)
        layout.addWidget(voice_button)
        layout.addWidget(tools_button)
        account_button = QPushButton("Account & Security")
        account_button.clicked.connect(self.show_quick_help_account_security)
        layout.addWidget(account_button)
        layout.addStretch()
        close_button = QPushButton("Close")
        close_button.clicked.connect(help_dialog.accept)
        layout.addWidget(close_button)

        self._prepare_simple_dark_dialog(help_dialog)
        self._apply_clickable_cursors(help_dialog)
        help_dialog.exec()

    def show_quick_help_getting_started(self):
        self._show_quick_help_topic(
            "Getting Started",
            "Start from sign-in, then choose the control method that fits your presentation.",
            "VisionSlide opens through a lock screen, so begin by signing in with your "
            "registered email and password. If Remember Me is enabled, that account can "
            "appear again later in saved sign-in suggestions on this device.\n\n"
            "After entering the app, start the camera from the top camera strip. Then use "
            "Control Mode for stable navigation gestures or switch to Jump Mode for direct "
            "slide-number jumps. Voice control can stay enabled at the same time for offline "
            "spoken commands during a presentation.\n\n"
            "Tools can open presentation files, recent files, command history, custom command "
            "editors, the presentation timer, gesture profiles, and admin-only activity logs. "
            "Settings holds the main on/off controls such as Dark Mode, Auto Focus, Voice "
            "Control, Voice Feedback, Practice Mode, Shortcut Keys, and microphone settings.",
        )

    def show_quick_help_control_mode(self):
        self._show_quick_help_topic(
            "Control & Jump Mode",
            "Use Control Mode for gesture navigation and Jump Mode for direct slide-number jumps.",
            "Current control gestures:\n"
            "- Open Palm -> Start slideshow\n"
            "- Fist -> Exit slideshow\n"
            "- Two Fingers -> Next slide\n"
            "- One Finger -> Previous slide\n\n"
            "For best results, keep one hand clearly visible to the camera and hold each "
            "gesture until the configured Control Hold value is reached. That extra hold "
            "time helps prevent accidental slide actions.\n\n"
            "Jump Mode lets you move directly to a slide by holding a visible finger count. "
            "VisionSlide currently supports jump counts from 1 to 10 using one or two hands. "
            "Show the target finger count clearly, keep the hands steady, and hold that count "
            "for the configured Jump Hold duration.\n\n"
            "Jump Mode works best when both hands, if used, stay clearly inside the camera "
            "frame with enough lighting for finger separation to remain visible.",
        )

    def show_quick_help_voice_commands(self):
        self._show_quick_help_topic(
            "Voice Commands",
            "Voice control works offline and supports slideshow navigation plus spoken slide numbers.",
            "VisionSlide uses the local Vosk model, so voice commands can work without an "
            "internet connection. Common supported phrases include:\n"
            "- next / next slide / forward\n"
            "- previous / previous slide / back / go back\n"
            "- start slideshow / begin slideshow\n"
            "- exit slideshow / stop slideshow / end slideshow\n"
            "- first slide / go to first slide\n"
            "- last slide / final slide / go to final slide\n"
            "- spoken slide numbers from one to one hundred, such as twenty or go to slide five\n\n"
            "Custom Voice Commands lets each user add extra phrases for the same core actions. "
            "Voice Feedback controls whether commands beep for all commands, success only, "
            "unknown only, or according to the selected beep style.\n\n"
            "If a presentation window is not available, the app keeps the command inside "
            "VisionSlide and reports that the presentation was not found.",
        )

    def show_quick_help_settings_tools(self):
        self._show_quick_help_topic(
            "Settings & Tools",
            "Settings handle everyday switches, while Tools hold presentation utilities and advanced customization.",
            "Current Settings options include:\n"
            "- Dark Mode Enabled\n"
            "- Auto Focus Presentation\n"
            "- Voice Control Enabled\n"
            "- Voice Feedback on/off and feedback style\n"
            "- Practice Mode Enabled\n"
            "- Shortcut Keys on/off and the shortcut guide\n"
            "- Microphone Settings\n\n"
            "Current Tools options include:\n"
            "- Open Presentation and Recent Files\n"
            "- Custom Voice Commands and Custom Gesture Actions\n"
            "- Command History and Presentation Timer\n"
            "- Gesture Profiles and Keyboard Shortcuts guide\n"
            "- Admin Activity Log for admin accounts only\n\n"
            "Practice Mode is useful before a demo because it lets you test voice and gesture "
            "recognition without sending real slide commands. Shortcut Keys provide keyboard "
            "fallbacks for important app actions when enabled.",
        )

    def show_quick_help_account_security(self):
        self._show_quick_help_topic(
            "Account & Security",
            "VisionSlide includes local sign-in, remembered accounts, and in-app security tools.",
            "Users sign in with email and password. Signup uses email OTP verification, and "
            "forgot-password works through a registered email. Remember Me controls whether "
            "a successful sign-in stays in saved suggestions on this device.\n\n"
            "Inside the app, Lock & Security lets you review the current account, update the "
            "username, change email through OTP verification, and change password. Admin "
            "accounts also receive tools for managing admins, users, passwords, saved sign-ins, "
            "and reviewing the admin activity log.",
        )

    def _show_quick_help_topic(self, title_text, summary_text, detail_text):
        topic_dialog = QDialog(self)
        topic_dialog.setWindowTitle(title_text)
        self._apply_standard_dialog_size(topic_dialog, "standard")
        if self._is_dark_theme_active():
            topic_dialog.setStyleSheet(
                "QDialog { background: #0f1a22; color: #e7f3f8; }"
                "QLabel { color: #e7f3f8; font-size: 13px; background: transparent; }"
                "QFrame[topicCard=\"true\"] { background: #132630; border: 1px solid #355768; border-radius: 18px; }"
                "QLabel[topicSummary=\"true\"] { color: #b5ccd7; font-size: 13px; background: transparent; }"
                "QPushButton { min-height: 36px; border-radius: 12px; border: 1px solid #3c6273; "
                "background: #183240; color: #eaf6fb; font-weight: 700; padding: 6px 12px; }"
                "QPushButton:hover { background: #214353; border-color: #5c8aa0; color: #ffffff; }"
                "QPushButton:pressed { background: #122733; border-color: #305465; }"
            )
        else:
            topic_dialog.setStyleSheet(
                "QDialog { background: #f7fbfd; }"
                "QLabel { color: #274652; font-size: 13px; }"
                "QFrame[topicCard=\"true\"] { background: #ffffff; border: 1px solid #d7e2e9; border-radius: 18px; }"
                "QLabel[topicSummary=\"true\"] { color: #5a7380; font-size: 13px; }"
                "QPushButton { min-height: 36px; border-radius: 12px; border: 1px solid #ccd8e2; "
                "background: #ffffff; color: #173543; font-weight: 700; padding: 6px 12px; }"
                "QPushButton:hover { background: #cfe5ee; border-color: #3f7c8f; }"
                "QPushButton:pressed { background: #bddbe6; border-color: #346b7d; }"
            )

        layout = QVBoxLayout()
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)
        topic_dialog.setLayout(layout)

        title = QLabel(title_text)
        title_color = "#eef8fc" if self._is_dark_theme_active() else "#173543"
        title.setStyleSheet(f"font-size: 20px; font-weight: 700; color: {title_color}; background: transparent;")
        summary = QLabel(summary_text)
        summary.setProperty("topicSummary", "true")
        summary.setWordWrap(True)

        detail_card = QFrame()
        detail_card.setProperty("topicCard", "true")
        detail_layout = QVBoxLayout()
        detail_layout.setContentsMargins(16, 16, 16, 16)
        detail_layout.setSpacing(8)
        detail_card.setLayout(detail_layout)

        detail_label = QLabel(detail_text)
        detail_label.setWordWrap(True)
        detail_layout.addWidget(detail_label)

        close_button = QPushButton("Close")
        close_button.clicked.connect(topic_dialog.accept)

        layout.addWidget(title)
        layout.addWidget(summary)
        layout.addWidget(detail_card)
        layout.addStretch()
        layout.addWidget(close_button)

        self._apply_clickable_cursors(topic_dialog)
        topic_dialog.exec()

    def show_about_dialog(self):
        about_dialog = QDialog(self)
        about_dialog.setWindowTitle("About VisionSlide")
        self._apply_standard_dialog_size(about_dialog, "standard")
        about_dialog.resize(about_dialog.width(), max(about_dialog.height(), 660))
        if self._is_dark_theme_active():
            about_dialog.setStyleSheet(self._dark_dialog_override_stylesheet())
        else:
            about_dialog.setStyleSheet(
                "QDialog { background: #f7fbfd; }"
                "QLabel { color: #274652; font-size: 13px; }"
                "QFrame[aboutCard=\"true\"] { background: #ffffff; border: 1px solid #d7e2e9; border-radius: 18px; }"
                "QLabel[aboutTitle=\"true\"] { font-size: 24px; font-weight: 800; color: #173543; }"
                "QLabel[aboutSub=\"true\"] { font-size: 13px; color: #5a7380; }"
                "QLabel[aboutBadge=\"true\"] { background: #edf5f8; border: 1px solid #d8e6ee; border-radius: 12px; padding: 8px 10px; font-size: 12px; font-weight: 700; color: #2c6275; }"
                "QPushButton { min-height: 38px; border-radius: 12px; border: 1px solid #ccd8e2; "
                "background: #ffffff; color: #173543; font-weight: 700; }"
                "QPushButton:hover { background: #cfe5ee; border-color: #3f7c8f; }"
                "QPushButton:pressed { background: #bddbe6; border-color: #346b7d; }"
            )

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)
        about_dialog.setLayout(layout)

        scroll_area = QScrollArea()
        scroll_area.setObjectName("aboutScrollArea")
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        content.setObjectName("aboutScrollContent")
        content.setAttribute(Qt.WA_StyledBackground, True)
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(14)
        content.setLayout(content_layout)
        scroll_area.setWidget(content)

        title = QLabel("VisionSlide v1.0")
        title.setProperty("aboutTitle", "true")
        subtitle = QLabel(
            "Release v1.0 of the touchless presentation control desktop app with local authentication, presentation tools, gesture input, and offline voice navigation."
        )
        subtitle.setProperty("aboutSub", "true")
        subtitle.setWordWrap(True)

        badge_row = QHBoxLayout()
        badge_row.setContentsMargins(0, 0, 0, 0)
        badge_row.setSpacing(10)
        for badge_text in ["Desktop App", "Gesture Control", "Offline Voice", "Presentation Tools"]:
            badge = QLabel(badge_text)
            badge.setProperty("aboutBadge", "true")
            badge_row.addWidget(badge)
        badge_row.addStretch()

        summary_card = QFrame()
        summary_card.setProperty("aboutCard", "true")
        summary_layout = QVBoxLayout()
        summary_layout.setContentsMargins(16, 16, 16, 16)
        summary_layout.setSpacing(8)
        summary_card.setLayout(summary_layout)
        summary_title = QLabel("Overview")
        summary_title.setStyleSheet("font-size: 14px; font-weight: 700; color: #173543;")
        summary_text = QLabel(
            "VisionSlide is a Windows desktop app for controlling presentation slides without "
            "relying on a keyboard or mouse during delivery. It brings together gesture "
            "recognition, offline voice commands, presentation utilities, remembered sign-ins, "
            "per-user preferences, and in-app security tools in one workflow."
        )
        summary_text.setWordWrap(True)
        summary_layout.addWidget(summary_title)
        summary_layout.addWidget(summary_text)

        feature_card = QFrame()
        feature_card.setProperty("aboutCard", "true")
        feature_layout = QVBoxLayout()
        feature_layout.setContentsMargins(16, 16, 16, 16)
        feature_layout.setSpacing(10)
        feature_card.setLayout(feature_layout)
        feature_title = QLabel("What it includes")
        feature_title.setStyleSheet("font-size: 14px; font-weight: 700; color: #173543;")
        feature_text = QLabel(
            "- Control Mode gestures for start, next, previous, and exit\n"
            "- Jump Mode using finger counts from 1 to 10\n"
            "- Offline voice control including custom phrases and slide numbers from 1 to 100\n"
            "- Presentation file launcher, recent files, timer, and command history\n"
            "- Custom gesture actions, gesture profiles, practice mode, and shortcut keys\n"
            "- Voice feedback choices with selectable professional beep styles\n"
            "- Saved sign-ins, Remember Me, reset settings, and admin-only management tools"
        )
        feature_text.setWordWrap(True)
        feature_layout.addWidget(feature_title)
        feature_layout.addWidget(feature_text)

        purpose_card = QFrame()
        purpose_card.setProperty("aboutCard", "true")
        purpose_layout = QVBoxLayout()
        purpose_layout.setContentsMargins(16, 16, 16, 16)
        purpose_layout.setSpacing(8)
        purpose_card.setLayout(purpose_layout)
        purpose_title = QLabel("Why VisionSlide")
        purpose_title.setStyleSheet("font-size: 14px; font-weight: 700; color: #173543;")
        purpose_text = QLabel(
            "VisionSlide is designed to make slide delivery more natural, independent, and "
            "professional. Instead of depending on constant keyboard or mouse interaction, "
            "it gives presenters a touchless workflow through camera-based gestures and offline "
            "voice commands. Recent files, custom commands, practice mode, shortcut keys, and "
            "voice feedback options make setup smoother for live presentations, academic "
            "demonstrations, and FYP project scenarios."
        )
        purpose_text.setWordWrap(True)
        purpose_layout.addWidget(purpose_title)
        purpose_layout.addWidget(purpose_text)

        stack_card = QFrame()
        stack_card.setProperty("aboutCard", "true")
        stack_layout = QVBoxLayout()
        stack_layout.setContentsMargins(16, 16, 16, 16)
        stack_layout.setSpacing(8)
        stack_card.setLayout(stack_layout)
        stack_title = QLabel("Core Stack")
        stack_title.setStyleSheet("font-size: 14px; font-weight: 700; color: #173543;")
        stack_text = QLabel(
            "VisionSlide is built with PySide6 for the desktop interface, OpenCV and "
            "MediaPipe for hand tracking, Vosk for offline voice recognition, PyAutoGUI "
            "for slideshow control, and SQLite with PBKDF2-based password hashing for "
            "the local account system."
        )
        stack_text.setWordWrap(True)
        stack_layout.addWidget(stack_title)
        stack_layout.addWidget(stack_text)

        security_card = QFrame()
        security_card.setProperty("aboutCard", "true")
        security_layout = QVBoxLayout()
        security_layout.setContentsMargins(16, 16, 16, 16)
        security_layout.setSpacing(8)
        security_card.setLayout(security_layout)
        security_title = QLabel("Security & Account System")
        security_title.setStyleSheet("font-size: 14px; font-weight: 700; color: #173543;")
        security_text = QLabel(
            "The app opens through a local lock screen and supports sign-in with email and "
            "password, OTP-based signup verification, forgot-password by registered email, "
            "Remember Me saved sign-ins, and in-app Lock & Security controls. Admin accounts "
            "also receive tools for managing admins, users, passwords, saved sign-ins, and "
            "admin activity history."
        )
        security_text.setWordWrap(True)
        security_layout.addWidget(security_title)
        security_layout.addWidget(security_text)

        account_card = QFrame()
        account_card.setProperty("aboutCard", "true")
        account_layout = QVBoxLayout()
        account_layout.setContentsMargins(16, 16, 16, 16)
        account_layout.setSpacing(8)
        account_card.setLayout(account_layout)
        account_title = QLabel("Current Account")
        account_title.setStyleSheet("font-size: 14px; font-weight: 700; color: #173543;")
        account_text = QLabel(
            f"Signed in as {self.current_user or 'User'}"
            + (f" - {self.current_email}" if self.current_email else "")
        )
        account_text.setProperty("aboutSub", "true")
        account_text.setWordWrap(True)
        account_layout.addWidget(account_title)
        account_layout.addWidget(account_text)

        support_card = QFrame()
        support_card.setProperty("aboutCard", "true")
        support_layout = QVBoxLayout()
        support_layout.setContentsMargins(16, 16, 16, 16)
        support_layout.setSpacing(8)
        support_card.setLayout(support_layout)
        support_title = QLabel("Support Contact")
        support_title.setStyleSheet("font-size: 14px; font-weight: 700; color: #173543;")
        support_text = QLabel("For project support or account-related help, contact the VisionSlide project administrator.")
        support_text.setWordWrap(True)
        support_layout.addWidget(support_title)
        support_layout.addWidget(support_text)

        close_button = QPushButton("Close")
        close_button.clicked.connect(about_dialog.accept)

        content_layout.addWidget(title)
        content_layout.addWidget(subtitle)
        content_layout.addLayout(badge_row)
        content_layout.addWidget(summary_card)
        content_layout.addWidget(feature_card)
        content_layout.addWidget(purpose_card)
        content_layout.addWidget(stack_card)
        content_layout.addWidget(security_card)
        content_layout.addWidget(account_card)
        content_layout.addWidget(support_card)
        content_layout.addStretch()
        layout.addWidget(scroll_area)
        layout.addWidget(close_button)

        self._apply_clickable_cursors(about_dialog)
        about_dialog.exec()

    def show_lock_security(self):
        lock_security_dialog = QDialog(self)
        lock_security_dialog.setWindowTitle("Lock & Security")
        self._apply_standard_dialog_size(lock_security_dialog, "standard")
        if self._is_dark_theme_active():
            lock_security_dialog.setStyleSheet(
                "QDialog { background: #0f1a22; }"
                "QLabel { color: #e7f3f8; font-size: 13px; background: transparent; }"
                "QPushButton { min-height: 40px; border-radius: 12px; border: 1px solid #42697c; "
                "background: #183240; color: #eaf6fb; font-weight: 700; padding: 8px 12px; }"
                "QPushButton:hover { background: #214353; border-color: #5c8aa0; color: #ffffff; }"
                "QPushButton:pressed { background: #122733; border-color: #305465; }"
            )
        else:
            lock_security_dialog.setStyleSheet(
                "QDialog { background: #f7fbfd; }"
                "QLabel { color: #274652; font-size: 13px; }"
                "QPushButton { min-height: 40px; border-radius: 12px; border: 1px solid #ccd8e2; "
                "background: #ffffff; color: #173543; font-weight: 700; padding: 8px 12px; }"
                "QPushButton:hover { background: #cfe5ee; border-color: #3f7c8f; }"
                "QPushButton:pressed { background: #bddbe6; border-color: #346b7d; }"
            )

        layout = QVBoxLayout()
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)
        lock_security_dialog.setLayout(layout)

        title = QLabel("Lock & Security")
        title.setStyleSheet(
            f"font-size: 20px; font-weight: 700; color: {'#eef8fc' if self._is_dark_theme_active() else '#173543'};"
        )
        subtitle = QLabel("Choose a specific security task to open its own management window.")
        subtitle.setStyleSheet(f"color: {'#b5ccd7' if self._is_dark_theme_active() else '#5a7380'};")
        subtitle.setWordWrap(True)

        current_account_button = QPushButton("Current Account")
        current_account_button.clicked.connect(self.show_current_account_dialog)

        change_username_button = QPushButton("Change Username")
        change_username_button.clicked.connect(self.show_change_username_dialog)

        change_email_button = QPushButton("Change Email")
        change_email_button.clicked.connect(self.show_change_email_dialog)

        change_password_button = QPushButton("Change Password")
        change_password_button.clicked.connect(self.show_change_password_dialog)

        close_button = QPushButton("Close")
        close_button.clicked.connect(lock_security_dialog.accept)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(4)
        layout.addWidget(current_account_button)
        layout.addWidget(change_username_button)
        layout.addWidget(change_email_button)
        layout.addWidget(change_password_button)
        layout.addStretch()
        layout.addWidget(close_button)

        self._prepare_simple_dark_dialog(lock_security_dialog)
        self._apply_clickable_cursors(lock_security_dialog)
        lock_security_dialog.exec()

    def show_current_account_dialog(self):
        account_dialog = QDialog(self)
        account_dialog.setWindowTitle("Current Account")
        self._apply_standard_dialog_size(account_dialog, "standard")
        if self._is_dark_theme_active():
            account_dialog.setStyleSheet(
                "QDialog { background: #0f1a22; color: #e7f3f8; }"
                "QLabel { color: #e7f3f8; font-size: 13px; background: transparent; }"
                "QLabel[accountValue=\"true\"] { background: #17303b; border: 1px solid #355768; border-radius: 14px; padding: 12px 14px; color: #e7f3f8; font-size: 13px; font-weight: 700; }"
                "QPushButton { min-height: 38px; border-radius: 12px; border: 1px solid #3c6273; "
                "background: #183240; color: #eaf6fb; font-weight: 700; }"
                "QPushButton:hover { background: #214353; border-color: #5c8aa0; color: #ffffff; }"
                "QPushButton:pressed { background: #122733; border-color: #305465; }"
            )
        else:
            account_dialog.setStyleSheet(
                "QDialog { background: #f7fbfd; }"
                "QLabel { color: #274652; font-size: 13px; }"
                "QLabel[accountValue=\"true\"] { background: #ffffff; border: 1px solid #d7e2e9; border-radius: 14px; padding: 12px 14px; color: #173543; font-size: 13px; font-weight: 700; }"
                "QPushButton { min-height: 38px; border-radius: 12px; border: 1px solid #ccd8e2; "
                "background: #ffffff; color: #173543; font-weight: 700; }"
                "QPushButton:hover { background: #cfe5ee; border-color: #3f7c8f; }"
                "QPushButton:pressed { background: #bddbe6; border-color: #346b7d; }"
            )

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        account_dialog.setLayout(layout)

        title = QLabel("Current Account")
        title_color = "#eef8fc" if self._is_dark_theme_active() else "#173543"
        title.setStyleSheet(f"font-size: 20px; font-weight: 700; color: {title_color}; background: transparent;")

        subtitle = QLabel("View the account details currently being used in VisionSlide.")
        subtitle_color = "#b5ccd7" if self._is_dark_theme_active() else "#5a7380"
        subtitle.setStyleSheet(f"color: {subtitle_color}; background: transparent;")
        subtitle.setWordWrap(True)

        username_label = QLabel("Username")
        username_value = QLabel(self.current_user or "Not available")
        username_value.setProperty("accountValue", "true")
        username_value.setWordWrap(True)

        email_label = QLabel("Email")
        email_value = QLabel(self.current_email or "Not available")
        email_value.setProperty("accountValue", "true")
        email_value.setWordWrap(True)

        close_button = QPushButton("Close")
        close_button.clicked.connect(account_dialog.accept)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(4)
        layout.addWidget(username_label)
        layout.addWidget(username_value)
        layout.addWidget(email_label)
        layout.addWidget(email_value)
        layout.addStretch()
        layout.addWidget(close_button)

        self._apply_clickable_cursors(account_dialog)
        account_dialog.exec()

    def show_change_username_dialog(self):
        username_dialog = QDialog(self)
        username_dialog.setWindowTitle("Change Username")
        self._apply_standard_dialog_size(username_dialog, "form")
        username_dialog.setStyleSheet(
            "QDialog { background: #f7fbfd; }"
            "QLabel { color: #274652; font-size: 13px; }"
            "QLabel[securityMessage=\"error\"] { color: #b64a3e; font-size: 11px; font-weight: 600; padding-left: 4px; }"
            "QLabel[securityMessage=\"success\"] { color: #2c7a4b; font-size: 11px; font-weight: 600; padding-left: 4px; }"
            "QLabel[securityMessage=\"neutral\"] { color: #6a7f89; font-size: 11px; font-weight: 600; padding-left: 4px; }"
            "QLineEdit { min-height: 52px; border-radius: 14px; border: 1px solid #cad7e1; background: #ffffff; padding: 6px 12px; color: #173543; font-size: 13px; }"
            "QLineEdit:focus { border-color: #8fb6cb; background: #f9fcff; }"
            "QLineEdit[validationState=\"error\"] { border: 1px solid #d66f63; background: #fff8f6; }"
            "QLineEdit[validationState=\"success\"] { border: 1px solid #7cc497; background: #f6fcf8; }"
            "QPushButton { min-height: 38px; border-radius: 12px; border: 1px solid #ccd8e2; "
            "background: #ffffff; color: #173543; font-weight: 700; }"
            "QPushButton:hover { background: #cfe5ee; border-color: #3f7c8f; }"
            "QPushButton:pressed { background: #bddbe6; border-color: #346b7d; }"
            "QPushButton[smallAction=\"true\"] { min-height: 34px; min-width: 120px; padding: 6px 12px; font-size: 12px; }"
        )

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)
        username_dialog.setLayout(layout)

        title = QLabel("Change Username")
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #173543;")

        # Create form widgets
        current_username_input = QLineEdit()
        current_username_input.setPlaceholderText("Current username")
        current_username_input.setFocusPolicy(Qt.StrongFocus)
        new_username_input = QLineEdit()
        new_username_input.setPlaceholderText("New username")
        new_username_input.setFocusPolicy(Qt.StrongFocus)
        username_current_password_input = QLineEdit()
        username_current_password_input.setPlaceholderText("Current password")
        username_current_password_input.setEchoMode(QLineEdit.Password)
        username_current_password_input.setFocusPolicy(Qt.StrongFocus)
        self._add_password_toggle(username_current_password_input)

        current_username_feedback_label = QLabel(" ")
        current_username_feedback_label.setProperty("securityMessage", "neutral")
        current_username_feedback_label.setWordWrap(True)
        current_username_feedback_label.setTextFormat(Qt.RichText)
        username_feedback_label = QLabel(" ")
        username_feedback_label.setProperty("securityMessage", "neutral")
        username_feedback_label.setWordWrap(True)
        username_feedback_label.setTextFormat(Qt.RichText)
        username_password_feedback_label = QLabel(" ")
        username_password_feedback_label.setProperty("securityMessage", "neutral")
        username_password_feedback_label.setWordWrap(True)
        username_password_feedback_label.setTextFormat(Qt.RichText)

        update_username_button = QPushButton("Update Username")
        update_username_button.setDefault(True)
        update_username_button.setFocusPolicy(Qt.NoFocus)

        close_button = QPushButton("Close")
        close_button.clicked.connect(username_dialog.accept)

        # Form layout
        username_form = QGridLayout()
        username_form.setHorizontalSpacing(8)
        username_form.setVerticalSpacing(10)
        username_form.addWidget(QLabel("Current Username <span style='color: red;'>*</span>"), 0, 0, 1, 2)
        username_form.addWidget(current_username_input, 1, 0, 1, 2)
        username_form.addWidget(current_username_feedback_label, 2, 0, 1, 2)
        username_form.addWidget(QLabel("New Username <span style='color: red;'>*</span>"), 3, 0, 1, 2)
        username_form.addWidget(new_username_input, 4, 0, 1, 2)
        username_form.addWidget(username_feedback_label, 5, 0, 1, 2)
        username_form.addWidget(QLabel("Current Password <span style='color: red;'>*</span>"), 6, 0, 1, 2)
        username_form.addWidget(username_current_password_input, 7, 0, 1, 2)
        username_form.addWidget(username_password_feedback_label, 8, 0, 1, 2)
        action_row = self._build_dialog_action_row(update_username_button, close_button)
        username_form.addLayout(action_row, 9, 0, 1, 2)

        # Connect signals
        current_username_input.textChanged.connect(lambda text: self._handle_live_current_username(current_username_input, current_username_feedback_label))
        new_username_input.textChanged.connect(lambda text: self._handle_live_security_username(new_username_input, username_feedback_label))
        username_current_password_input.textChanged.connect(
            lambda text: self._handle_live_current_password(
                text,
                username_password_feedback_label,
                username_current_password_input,
            )
        )
        update_username_button.clicked.connect(lambda: self._run_with_busy_button(
            update_username_button,
            "Updating...",
            lambda: self._update_username_from_dialog(
                current_username_input, new_username_input, username_current_password_input, current_username_feedback_label, username_feedback_label, username_password_feedback_label, username_dialog
            ),
        ))

        layout.addWidget(title)
        layout.addLayout(username_form)
        layout.addStretch()

        username_dialog.setFocus()

        self._apply_clickable_cursors(username_dialog)
        username_dialog.exec()

    def show_change_email_dialog(self):
        email_dialog = QDialog(self)
        email_dialog.setWindowTitle("Change Email")
        self._apply_standard_dialog_size(email_dialog, "form")
        email_dialog.setStyleSheet(
            "QDialog { background: #f7fbfd; }"
            "QLabel { color: #274652; font-size: 13px; }"
            "QLabel[securityMessage=\"error\"] { color: #b64a3e; font-size: 11px; font-weight: 600; padding-left: 4px; }"
            "QLabel[securityMessage=\"success\"] { color: #2c7a4b; font-size: 11px; font-weight: 600; padding-left: 4px; }"
            "QLabel[securityMessage=\"neutral\"] { color: #6a7f89; font-size: 11px; font-weight: 600; padding-left: 4px; }"
            "QLineEdit { min-height: 52px; border-radius: 14px; border: 1px solid #cad7e1; background: #ffffff; padding: 6px 12px; color: #173543; font-size: 13px; }"
            "QLineEdit:focus { border-color: #8fb6cb; background: #f9fcff; }"
            "QLineEdit[validationState=\"error\"] { border: 1px solid #d66f63; background: #fff8f6; }"
            "QLineEdit[validationState=\"success\"] { border: 1px solid #7cc497; background: #f6fcf8; }"
            "QPushButton { min-height: 38px; border-radius: 12px; border: 1px solid #ccd8e2; "
            "background: #ffffff; color: #173543; font-weight: 700; }"
            "QPushButton:hover { background: #cfe5ee; border-color: #3f7c8f; }"
            "QPushButton:pressed { background: #bddbe6; border-color: #346b7d; }"
            "QPushButton[textLink=\"true\"] { min-height: 0px; min-width: 0px; padding: 0px; border: none; background: transparent; color: #2c6e82; font-size: 13px; font-weight: 700; }"
            "QPushButton[textLink=\"true\"]:hover { background: transparent; border: none; color: #1f5c6d; text-decoration: underline; }"
            "QPushButton[textLink=\"true\"]:disabled { background: transparent; border: none; color: #9aaab3; }"
        )

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)
        email_dialog.setLayout(layout)

        title = QLabel("Change Email")
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #173543;")
        new_email_input = QLineEdit()
        new_email_input.setPlaceholderText("New email")
        new_email_input.setFocusPolicy(Qt.StrongFocus)
        email_current_password_input = QLineEdit()
        email_current_password_input.setPlaceholderText("Current password")
        email_current_password_input.setEchoMode(QLineEdit.Password)
        email_current_password_input.setFocusPolicy(Qt.StrongFocus)
        self._add_password_toggle(email_current_password_input)
        email_otp_input = QLineEdit()
        email_otp_input.setPlaceholderText("Enter OTP code")
        email_otp_input.setFocusPolicy(Qt.StrongFocus)
        email_otp_input.setMaxLength(6)
        email_otp_input.setEnabled(False)

        email_feedback_label = QLabel(" ")
        email_feedback_label.setProperty("securityMessage", "neutral")
        email_feedback_label.setWordWrap(True)
        email_feedback_label.setTextFormat(Qt.RichText)
        email_password_feedback_label = QLabel(" ")
        email_password_feedback_label.setProperty("securityMessage", "neutral")
        email_password_feedback_label.setWordWrap(True)
        email_password_feedback_label.setTextFormat(Qt.RichText)
        email_otp_feedback_label = QLabel(" ")
        email_otp_feedback_label.setProperty("securityMessage", "neutral")
        email_otp_feedback_label.setWordWrap(True)
        email_otp_feedback_label.setTextFormat(Qt.RichText)

        send_email_otp_button = QPushButton("Send OTP")
        send_email_otp_button.setProperty("textLink", "true")
        send_email_otp_button.setFocusPolicy(Qt.NoFocus)
        send_email_otp_button.setEnabled(False)
        resend_email_otp_button = QPushButton("Resend OTP")
        resend_email_otp_button.setProperty("textLink", "true")
        resend_email_otp_button.setFocusPolicy(Qt.NoFocus)
        resend_email_otp_button.setEnabled(False)
        update_email_button = QPushButton("Update Email")
        update_email_button.setFocusPolicy(Qt.NoFocus)
        update_email_button.setDefault(True)
        close_button = QPushButton("Close")
        close_button.clicked.connect(email_dialog.accept)

        local_email_verified_email = ""
        local_email_verified_code = ""
        local_email_last_otp_attempt = ""
        local_email_failed_code = ""
        local_email_resend_available = False
        local_email_resend_seconds_remaining = 0
        email_otp_timer = QTimer(email_dialog)
        email_otp_timer.setInterval(1000)

        local_email_verified_email = ""
        local_email_verified_code = ""
        local_email_last_otp_attempt = ""
        local_email_failed_code = ""
        local_email_resend_available = False
        local_email_resend_seconds_remaining = 0
        email_otp_timer = QTimer(email_dialog)
        email_otp_timer.setInterval(1000)

        def set_email_message(label, message, tone="neutral"):
            self._set_security_message(label, message, tone)

        def sync_email_buttons():
            nonlocal local_email_resend_available, local_email_resend_seconds_remaining
            email = new_email_input.text().strip().lower()
            email_ready = bool(email) and not validate_email(email) and email != self.current_email and not self.auth_manager.email_exists(email)
            verified_current_email = bool(email) and local_email_verified_email == email
            if verified_current_email:
                local_email_resend_available = False
            cooldown_active = local_email_resend_seconds_remaining > 0
            send_email_otp_button.setEnabled(
                email_ready and not cooldown_active and not local_email_resend_available and not verified_current_email
            )
            resend_email_otp_button.setEnabled(
                email_ready and (not cooldown_active) and local_email_resend_available and not verified_current_email
            )

        def update_cooldown_buttons():
            nonlocal local_email_resend_seconds_remaining
            if local_email_resend_seconds_remaining <= 0:
                email_otp_timer.stop()
                send_email_otp_button.setText("Send OTP")
                resend_email_otp_button.setText("Resend OTP")
                sync_email_buttons()
                return

            local_email_resend_seconds_remaining -= 1
            send_email_otp_button.setText("Send OTP")
            if local_email_resend_seconds_remaining > 0:
                resend_email_otp_button.setText(f"Resend OTP ({local_email_resend_seconds_remaining}s)")
            else:
                resend_email_otp_button.setText("Resend OTP")
            sync_email_buttons()
            if local_email_resend_seconds_remaining <= 0:
                email_otp_timer.stop()

        email_otp_timer.timeout.connect(update_cooldown_buttons)

        def reset_email_change_verification():
            nonlocal local_email_verified_email, local_email_verified_code, local_email_last_otp_attempt, local_email_failed_code, local_email_resend_available, local_email_resend_seconds_remaining
            local_email_verified_email = ""
            local_email_verified_code = ""
            local_email_last_otp_attempt = ""
            local_email_failed_code = ""
            local_email_resend_available = False
            local_email_resend_seconds_remaining = 0
            email_otp_input.setEnabled(False)
            email_otp_timer.stop()
            send_email_otp_button.setText("Send OTP")
            resend_email_otp_button.setText("Resend OTP")
            set_email_message(email_otp_feedback_label, "")
            sync_email_buttons()

        def handle_send_email_otp(send_mode):
            nonlocal local_email_verified_email, local_email_verified_code, local_email_last_otp_attempt, local_email_failed_code, local_email_resend_available, local_email_resend_seconds_remaining
            email = new_email_input.text().strip().lower()
            set_email_message(email_password_feedback_label, "")
            set_email_message(email_otp_feedback_label, "")

            email_errors = validate_email(email)
            if email_errors:
                set_email_message(email_feedback_label, email_errors[0], "error")
                new_email_input.setFocus()
                return

            if email == self.current_email:
                set_email_message(email_feedback_label, "This is already your current email.", "error")
                new_email_input.setFocus()
                return

            if self.auth_manager.email_exists(email):
                set_email_message(email_feedback_label, "This email is already registered.", "error")
                new_email_input.setFocus()
                return

            try:
                otp_code = self.otp_service.generate_for_email(email)
                self.email_service.send_otp_email(email, otp_code)
            except EmailDeliveryError as error:
                set_email_message(email_feedback_label, str(error), "error")
                return

            local_email_verified_email = ""
            local_email_verified_code = ""
            local_email_last_otp_attempt = ""
            local_email_failed_code = ""
            local_email_resend_available = True
            email_otp_input.setEnabled(True)
            email_otp_input.setFocus()
            if send_mode == "resend":
                set_email_message(email_otp_feedback_label, f"OTP Resend Successfully to {email}", "success")
            else:
                set_email_message(email_otp_feedback_label, f"OTP Send Successfully to {email}", "success")
            local_email_resend_seconds_remaining = 30
            update_cooldown_buttons()
            email_otp_timer.start()

        def handle_otp_input(text):
            nonlocal local_email_verified_email, local_email_verified_code, local_email_last_otp_attempt, local_email_failed_code, local_email_resend_available, local_email_resend_seconds_remaining
            code = (text or "").strip()
            current_email = new_email_input.text().strip().lower()
            if not current_email:
                set_email_message(email_otp_feedback_label, "")
                return

            if code != local_email_last_otp_attempt and code != local_email_verified_code:
                local_email_verified_email = ""
                local_email_verified_code = ""

            if not code:
                set_email_message(email_otp_feedback_label, "")
                return

            if len(code) < 6:
                local_email_last_otp_attempt = ""
                set_email_message(email_otp_feedback_label, "OTP must be 6 digits.", "error")
                return

            if len(code) > 6:
                local_email_last_otp_attempt = ""
                set_email_message(email_otp_feedback_label, "OTP cannot exceed 6 digits.", "error")
                return

            if code == local_email_last_otp_attempt:
                if local_email_verified_email == current_email:
                    set_email_message(email_otp_feedback_label, "OTP verified successfully.", "success")
                return

            local_email_last_otp_attempt = code
            otp_status = self.otp_service.verify_status_for_email(current_email, code)
            if otp_status != "valid":
                local_email_verified_email = ""
                local_email_verified_code = ""
                local_email_failed_code = code
                local_email_resend_available = True
                if otp_status == "expired":
                    set_email_message(email_otp_feedback_label, "OTP has expired.", "error")
                else:
                    set_email_message(email_otp_feedback_label, "OTP is wrong.", "error")
                sync_email_buttons()
                return

            local_email_verified_email = current_email
            local_email_verified_code = code
            local_email_failed_code = ""
            local_email_resend_available = False
            email_otp_input.setEnabled(True)
            set_email_message(email_otp_feedback_label, "OTP verified successfully.", "success")
            sync_email_buttons()

        def update_email():
            new_email = new_email_input.text().strip().lower()
            current_password = email_current_password_input.text()
            set_email_message(email_feedback_label, "")
            set_email_message(email_password_feedback_label, "")
            set_email_message(email_otp_feedback_label, "")

            email_errors = validate_email(new_email)
            if email_errors:
                set_email_message(email_feedback_label, email_errors[0], "error")
                new_email_input.setFocus()
                self._show_security_result_popup("Email Update", email_errors[0], success=False)
                return

            if new_email == self.current_email:
                message = "This is already your current email."
                set_email_message(email_feedback_label, message, "error")
                new_email_input.setFocus()
                self._show_security_result_popup("Email Update", message, success=False)
                return

            if self.auth_manager.email_exists(new_email):
                message = "This email is already registered."
                set_email_message(email_feedback_label, message, "error")
                new_email_input.setFocus()
                self._show_security_result_popup("Email Update", message, success=False)
                return

            if not current_password:
                message = "Current password is required."
                set_email_message(email_password_feedback_label, message, "error")
                email_current_password_input.setFocus()
                self._show_security_result_popup("Email Update", message, success=False)
                return

            if not local_email_verified_email or local_email_verified_email != new_email:
                message = "Verify the OTP for this email before updating."
                set_email_message(email_otp_feedback_label, message, "error")
                email_otp_input.setFocus()
                self._show_security_result_popup("Email Update", message, success=False)
                return

            updated, message = self.auth_manager.update_email(self.current_user, current_password, new_email)
            if not updated:
                set_email_message(email_password_feedback_label, message, "error")
                email_current_password_input.setFocus()
                self._show_security_result_popup("Email Update", message, success=False)
                return

            self.current_email = new_email
            self._refresh_account_security_info()
            self.credential_store.set_password(new_email, current_password)
            reset_email_change_verification()
            set_email_message(email_feedback_label, message, "success")
            set_email_message(email_password_feedback_label, "", "neutral")
            set_email_message(email_otp_feedback_label, "OTP verified successfully.", "success")
            new_email_input.clear()
            email_current_password_input.clear()
            email_otp_input.clear()
            self._show_security_result_popup("Email Update", message, success=True)
        email_form = QGridLayout()
        email_form.setHorizontalSpacing(8)
        email_form.setVerticalSpacing(10)
        email_form.addWidget(QLabel("New Email <span style='color: red;'>*</span>"), 0, 0, 1, 2)
        email_form.addWidget(new_email_input, 1, 0, 1, 2)
        email_form.addWidget(email_feedback_label, 2, 0, 1, 2)
        email_form.addWidget(QLabel("Current Password <span style='color: red;'>*</span>"), 3, 0, 1, 2)
        email_form.addWidget(email_current_password_input, 4, 0, 1, 2)
        email_form.addWidget(email_password_feedback_label, 5, 0, 1, 2)
        email_form.addWidget(QLabel("Verification Code <span style='color: red;'>*</span>"), 6, 0, 1, 2)
        email_form.addWidget(email_otp_input, 7, 0, 1, 2)
        otp_row = QHBoxLayout()
        otp_row.setContentsMargins(0, 0, 0, 0)
        otp_row.setSpacing(12)
        otp_row.addWidget(email_otp_feedback_label, 1)
        otp_row.addStretch()
        otp_row.addWidget(send_email_otp_button)
        otp_row.addWidget(resend_email_otp_button)
        email_form.addLayout(otp_row, 8, 0, 1, 2)
        email_form.addItem(QSpacerItem(0, 8, QSizePolicy.Minimum, QSizePolicy.Fixed), 9, 0, 1, 2)
        email_form.addLayout(self._build_dialog_action_row(update_email_button, close_button), 10, 0, 1, 2)

        new_email_input.textChanged.connect(lambda _: self._handle_live_security_email(new_email_input, email_feedback_label))
        new_email_input.textChanged.connect(lambda: reset_email_change_verification())
        email_current_password_input.textChanged.connect(
            lambda text: self._handle_live_current_password(
                text,
                email_password_feedback_label,
                email_current_password_input,
            )
        )
        email_otp_input.textChanged.connect(lambda text: handle_otp_input(text))
        send_email_otp_button.clicked.connect(
            lambda: self._run_with_busy_button(
                send_email_otp_button,
                "Sending...",
                lambda: handle_send_email_otp("send"),
                restore_enabled=False,
            )
        )
        resend_email_otp_button.clicked.connect(
            lambda: self._run_with_busy_button(
                resend_email_otp_button,
                "Sending...",
                lambda: handle_send_email_otp("resend"),
                restore_enabled=False,
            )
        )
        update_email_button.clicked.connect(
            lambda: self._run_with_busy_button(update_email_button, "Updating...", update_email)
        )

        layout.addWidget(title)
        layout.addLayout(email_form)
        layout.addStretch()

        email_dialog.setFocus()

        self._apply_clickable_cursors(email_dialog)
        email_dialog.exec()

    def show_change_password_dialog(self):
        password_dialog = QDialog(self)
        password_dialog.setWindowTitle("Change Password")
        self._apply_standard_dialog_size(password_dialog, "form")
        password_dialog.move(
            self.x() + (self.width() - password_dialog.width()) // 2,
            max(self.y() + 20, self.y() + (self.height() - password_dialog.height()) // 2 + 10)
        )
        password_dialog.setStyleSheet(
            "QDialog { background: #f7fbfd; }"
            "QLabel { color: #274652; font-size: 13px; }"
            "QLabel[securityMessage=\"error\"] { color: #b64a3e; font-size: 11px; font-weight: 600; padding-left: 4px; }"
            "QLabel[securityMessage=\"success\"] { color: #2c7a4b; font-size: 11px; font-weight: 600; padding-left: 4px; }"
            "QLabel[securityMessage=\"neutral\"] { color: #6a7f89; font-size: 11px; font-weight: 600; padding-left: 4px; }"
            "QLineEdit { min-height: 52px; border-radius: 14px; border: 1px solid #cad7e1; background: #ffffff; padding: 6px 12px; color: #173543; font-size: 13px; }"
            "QLineEdit:focus { border-color: #8fb6cb; background: #f9fcff; }"
            "QLineEdit[validationState=\"error\"] { border: 1px solid #d66f63; background: #fff8f6; }"
            "QLineEdit[validationState=\"success\"] { border: 1px solid #7cc497; background: #f6fcf8; }"
            "QPushButton { min-height: 38px; border-radius: 12px; border: 1px solid #ccd8e2; "
            "background: #ffffff; color: #173543; font-weight: 700; }"
            "QPushButton:hover { background: #cfe5ee; border-color: #3f7c8f; }"
            "QPushButton:pressed { background: #bddbe6; border-color: #346b7d; }"
            "QPushButton[smallAction=\"true\"] { min-height: 34px; min-width: 120px; padding: 6px 12px; font-size: 12px; }"
        )

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)
        password_dialog.setLayout(layout)

        title = QLabel("Change Password")
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #173543;")

        # Create form widgets
        security_current_password_input = QLineEdit()
        security_current_password_input.setPlaceholderText("Current password")
        security_current_password_input.setEchoMode(QLineEdit.Password)
        security_current_password_input.setFocusPolicy(Qt.StrongFocus)
        self._add_password_toggle(security_current_password_input)
        security_new_password_input = QLineEdit()
        security_new_password_input.setPlaceholderText("New password")
        security_new_password_input.setEchoMode(QLineEdit.Password)
        security_new_password_input.setFocusPolicy(Qt.StrongFocus)
        self._add_password_toggle(security_new_password_input)
        security_confirm_password_input = QLineEdit()
        security_confirm_password_input.setPlaceholderText("Confirm new password")
        security_confirm_password_input.setEchoMode(QLineEdit.Password)
        security_confirm_password_input.setFocusPolicy(Qt.StrongFocus)
        self._add_password_toggle(security_confirm_password_input)

        password_current_feedback_label = QLabel(" ")
        password_current_feedback_label.setProperty("securityMessage", "neutral")
        password_current_feedback_label.setWordWrap(True)
        password_current_feedback_label.setTextFormat(Qt.RichText)
        password_new_feedback_label = QLabel(" ")
        password_new_feedback_label.setProperty("securityMessage", "neutral")
        password_new_feedback_label.setWordWrap(True)
        password_new_feedback_label.setTextFormat(Qt.RichText)
        password_confirm_feedback_label = QLabel(" ")
        password_confirm_feedback_label.setProperty("securityMessage", "neutral")
        password_confirm_feedback_label.setWordWrap(True)
        password_confirm_feedback_label.setTextFormat(Qt.RichText)

        update_password_button = QPushButton("Update Password")
        update_password_button.setFocusPolicy(Qt.NoFocus)

        close_button = QPushButton("Close")
        close_button.clicked.connect(password_dialog.accept)

        # Form layout
        password_form = QGridLayout()
        password_form.setHorizontalSpacing(8)
        password_form.setVerticalSpacing(10)
        password_form.addWidget(QLabel("Current Password <span style='color: red;'>*</span>"), 0, 0, 1, 2)
        password_form.addWidget(security_current_password_input, 1, 0, 1, 2)
        password_form.addWidget(password_current_feedback_label, 2, 0, 1, 2)
        password_form.addWidget(QLabel("New Password <span style='color: red;'>*</span>"), 3, 0, 1, 2)
        password_form.addWidget(security_new_password_input, 4, 0, 1, 2)
        password_form.addWidget(password_new_feedback_label, 5, 0, 1, 2)
        password_form.addWidget(QLabel("Confirm New Password <span style='color: red;'>*</span>"), 6, 0, 1, 2)
        password_form.addWidget(security_confirm_password_input, 7, 0, 1, 2)
        password_form.addWidget(password_confirm_feedback_label, 8, 0, 1, 2)
        password_form.addLayout(self._build_dialog_action_row(update_password_button, close_button), 9, 0, 1, 2)
        update_password_button.setDefault(True)

        # Connect signals
        security_current_password_input.textChanged.connect(
            lambda text: self._handle_live_current_password(
                text,
                password_current_feedback_label,
                security_current_password_input,
            )
        )
        security_new_password_input.textChanged.connect(lambda text: self._handle_live_security_password(security_new_password_input, password_new_feedback_label))
        security_confirm_password_input.textChanged.connect(lambda text: self._handle_live_security_confirm_password(security_new_password_input, security_confirm_password_input, password_confirm_feedback_label))
        update_password_button.clicked.connect(lambda: self._run_with_busy_button(
            update_password_button,
            "Updating...",
            lambda: self._update_password_from_dialog(
                security_current_password_input,
                security_new_password_input,
                security_confirm_password_input,
                password_current_feedback_label,
                password_new_feedback_label,
                password_confirm_feedback_label,
                password_dialog,
            ),
        ))

        layout.addWidget(title)
        layout.addLayout(password_form)
        layout.addStretch()

        password_dialog.setFocus()

        self._apply_clickable_cursors(password_dialog)
        password_dialog.exec()

    def show_account_switcher(self):
        switch_dialog = QDialog(self)
        switch_dialog.setWindowTitle("Switch Account")
        self._apply_standard_dialog_size(switch_dialog, "standard")
        if self._is_dark_theme_active():
            switch_dialog.setStyleSheet(self._dark_dialog_override_stylesheet())
        else:
            switch_dialog.setStyleSheet(
                "QDialog { background: #f7fbfd; }"
                "QLabel { color: #274652; font-size: 13px; }"
                "QPushButton { min-height: 38px; border-radius: 12px; border: 1px solid #ccd8e2; "
                "background: #ffffff; color: #173543; font-weight: 700; }"
                "QPushButton:hover { background: #cfe5ee; border-color: #3f7c8f; }"
                "QPushButton:pressed { background: #bddbe6; border-color: #346b7d; }"
                "QListWidget { background: #ffffff; border: 1px solid #d7e2e9; border-radius: 14px; padding: 6px; }"
                "QListWidget::item { padding: 10px 12px; border-radius: 10px; }"
                "QListWidget::item:hover { background: #dfeff4; border: 1px solid #4f8ea1; color: #15394b; }"
                "QListWidget::item:selected { background: #cfe5ee; color: #15394b; }"
                "QListWidget::item:focus { outline: none; }"
            )

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        switch_dialog.setLayout(layout)

        title = QLabel("Saved Accounts")
        title.setStyleSheet(
            f"font-size: 20px; font-weight: 700; color: {'#eef8fc' if self._is_dark_theme_active() else '#173543'};"
        )

        account_list = QListWidget()
        account_list.setMouseTracking(True)
        account_list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        account_list.verticalScrollBar().setSingleStep(12)
        account_list.setSelectionMode(QAbstractItemView.SingleSelection)
        account_list.setFocusPolicy(Qt.NoFocus)
        account_list.setSpacing(6)
        identities = self.credential_store.get_saved_identities()

        def add_account_item(label_text, identity_value="", item_type="account", is_current=False):
            item = QListWidgetItem()
            item.setData(Qt.UserRole, identity_value)
            item.setData(Qt.UserRole + 1, item_type)
            item.setSizeHint(QSize(0, 64))
            if is_current:
                item.setFlags(Qt.NoItemFlags)
            account_list.addItem(item)
            normalized_identity = (identity_value or "").strip().lower()
            is_admin = bool(normalized_identity) and self.auth_manager.is_admin(normalized_identity)

            row_widget = QWidget()
            row_widget.setStyleSheet("background: transparent;")
            row_widget.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            row_layout = QHBoxLayout()
            row_layout.setContentsMargins(12, 10, 12, 10)
            row_layout.setSpacing(8)
            row_widget.setLayout(row_layout)

            user_icon = QLabel("\U0001F464")
            user_icon.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            user_icon.setAlignment(Qt.AlignCenter)
            user_icon.setFixedSize(26, 26)
            icon_bg = "#17303b" if self._is_dark_theme_active() else ("#edf5f8" if is_admin else "#eef5f8")
            icon_border = "#42697c" if self._is_dark_theme_active() else ("#b8d2df" if is_admin else "#d6e2ea")
            icon_color = "#d8eef6" if self._is_dark_theme_active() else "#2d6478"
            user_icon.setStyleSheet(
                f"background: {icon_bg}; "
                f"border: 1px solid {icon_border}; "
                f"border-radius: {'9px' if is_admin else '13px'}; "
                f"color: {icon_color}; font-size: 13px; font-weight: 700;"
            )
            row_layout.addWidget(user_icon, 0, Qt.AlignVCenter)

            text_label = QLabel(label_text)
            text_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            text_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            text_label.setMinimumWidth(0)
            text_color = "#eef8fc" if self._is_dark_theme_active() else "#173543"
            if is_current:
                text_label.setStyleSheet(f"color: {text_color}; font-weight: 700;")
            else:
                text_label.setStyleSheet(f"color: {text_color};")
            row_layout.addWidget(text_label)
            row_layout.addStretch()

            if is_current:
                current_badge = QLabel("Current")
                current_badge.setAttribute(Qt.WA_TransparentForMouseEvents, True)
                current_badge.setStyleSheet(
                    "background: #edf8f1; border: 1px solid #cbe6d2; border-radius: 10px; "
                    "padding: 4px 8px; color: #1f8f5f; font-size: 11px; font-weight: 700;"
                )
                row_layout.addWidget(current_badge, 0, Qt.AlignVCenter)

            if is_admin:
                admin_badge = QLabel("Admin")
                admin_badge.setAttribute(Qt.WA_TransparentForMouseEvents, True)
                admin_badge.setStyleSheet(
                    "background: #edf5f8; border: 1px solid #d8e6ee; border-radius: 10px; "
                    "padding: 4px 8px; color: #2c6275; font-size: 11px; font-weight: 700;"
                )
                row_layout.addWidget(admin_badge, 0, Qt.AlignVCenter)

            account_list.setItemWidget(item, row_widget)
            return item

        current_display = self.current_email or "Current account"
        add_account_item(current_display, self.current_email or "", item_type="current", is_current=True)

        for identity in identities:
            normalized_identity = identity.strip().lower()
            if normalized_identity == (self.current_email or "").strip().lower():
                continue
            add_account_item(identity, identity, item_type="account")

        account_list.clearSelection()
        account_list.setCurrentRow(-1)
        account_list.setCurrentItem(None)

        status_label = QLabel(" ")
        status_label.setProperty("securityMessage", "error")
        status_label.setWordWrap(True)

        add_account_button = QPushButton("+ Add Another Account")
        cancel_button = QPushButton("Cancel")
        button_row = self._build_dialog_action_row(add_account_button, cancel_button)

        def set_dialog_message(message="", tone="error"):
            status_label.setText(message or " ")
            status_label.setProperty("securityMessage", tone)
            status_label.style().unpolish(status_label)
            status_label.style().polish(status_label)
            status_label.update()

        def add_another_account():
            should_add_account = self._show_confirmation_popup(
                "Add Another Account",
                f"Are you sure you want to logout from {current_display} and add another account?",
                confirm_text="Yes",
                cancel_text="No",
            )
            if not should_add_account:
                return

            switch_dialog.accept()
            self.hide()
            login_window = LoginWindow(self.auth_manager)
            login_window.setWindowState(Qt.WindowMaximized)
            login_window.login_succeeded.connect(login_window.accept)
            if login_window.exec() == QDialog.Accepted:
                self.current_user = normalize_username(login_window.authenticated_username or self.current_user)
                self.current_email = self.auth_manager.get_email_for_username(self.current_user) or self.current_email
                self._refresh_account_security_info()
                self._clear_security_messages()
            self.show()
            self.raise_()
            self.activateWindow()

        def switch_selected_account(clicked_item=None):
            current_item = clicked_item
            if current_item is None:
                set_dialog_message("Select a saved account first.", "error")
                return

            item_type = current_item.data(Qt.UserRole + 1) or "account"
            if item_type == "current":
                return

            selected_email = (current_item.data(Qt.UserRole) or "").strip().lower()
            if not selected_email:
                set_dialog_message("Selected account is invalid.", "error")
                return

            target_display = current_item.data(Qt.UserRole) or selected_email
            should_switch = self._show_confirmation_popup(
                "Switch Account",
                f"Are you sure you want to logout from {current_display} and switch to {target_display}?",
                confirm_text="Yes",
                cancel_text="No",
            )
            if not should_switch:
                return

            stored_password = self.credential_store.get_password(selected_email)
            if not stored_password:
                set_dialog_message("No saved password found for this account. Use Add Another Account to sign in manually.", "error")
                return

            if not self.auth_manager.authenticate_email(selected_email, stored_password):
                set_dialog_message("Saved login for this account is no longer valid. Use Add Another Account to sign in again.", "error")
                return

            self.current_email = selected_email
            self.current_user = self.auth_manager.get_username_for_email(selected_email) or self.current_user
            self._refresh_account_security_info()
            self._clear_security_messages()
            set_dialog_message("Account switched successfully.", "success")
            self._set_badge(self.status_value, "Switched to saved account", "success")
            switch_dialog.accept()

        account_list.itemClicked.connect(switch_selected_account)
        add_account_button.clicked.connect(add_another_account)
        cancel_button.clicked.connect(switch_dialog.reject)

        layout.addWidget(title)
        layout.addWidget(account_list)
        layout.addWidget(status_label)
        layout.addLayout(button_row)

        account_list.clearSelection()
        account_list.setCurrentItem(None)
        self._apply_clickable_cursors(switch_dialog)
        switch_dialog.exec()

    def show_manage_users(self):
        if not self._is_admin_user():
            self._show_security_result_popup(
                "Manage Users",
                "Only the admin account can manage saved sign-ins and registered users.",
                success=False,
            )
            return

        manage_dialog = QDialog(self)
        manage_dialog.setWindowTitle("Manage Users")
        self._apply_standard_dialog_size(manage_dialog, "standard")
        if self._is_dark_theme_active():
            manage_dialog.setStyleSheet(
                "QDialog { background: #0f1a22; }"
                "QLabel { color: #e7f3f8; font-size: 13px; background: transparent; }"
                "QPushButton { min-height: 40px; border-radius: 12px; border: 1px solid #42697c; "
                "background: #183240; color: #eaf6fb; font-weight: 700; padding: 8px 12px; }"
                "QPushButton:hover { background: #214353; border-color: #5c8aa0; color: #ffffff; }"
                "QPushButton:pressed { background: #122733; border-color: #305465; }"
            )
        else:
            manage_dialog.setStyleSheet(
                "QDialog { background: #f7fbfd; }"
                "QLabel { color: #274652; font-size: 13px; }"
                "QPushButton { min-height: 40px; border-radius: 12px; border: 1px solid #ccd8e2; "
                "background: #ffffff; color: #173543; font-weight: 700; padding: 8px 12px; }"
                "QPushButton:hover { background: #cfe5ee; border-color: #3f7c8f; }"
                "QPushButton:pressed { background: #bddbe6; border-color: #346b7d; }"
            )

        layout = QVBoxLayout()
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)
        manage_dialog.setLayout(layout)

        title = QLabel("Manage Users")
        title.setStyleSheet(
            f"font-size: 20px; font-weight: 700; color: {'#eef8fc' if self._is_dark_theme_active() else '#173543'};"
        )
        subtitle = QLabel("Choose a specific admin task to open its own management window.")
        subtitle.setStyleSheet(f"color: {'#b5ccd7' if self._is_dark_theme_active() else '#5a7380'};")
        subtitle.setWordWrap(True)

        admin_email_button = QPushButton("Manage Admin")
        admin_email_button.clicked.connect(self.show_admin_email_manager)

        reset_password_button = QPushButton("Reset User Password")
        reset_password_button.clicked.connect(self.show_reset_user_password_manager)

        delete_user_button = QPushButton("Delete User Account")
        delete_user_button.clicked.connect(self.show_delete_user_manager)

        remove_saved_button = QPushButton("Remove Saved Sign-In")
        remove_saved_button.clicked.connect(self.show_remove_saved_signin_manager)

        close_button = QPushButton("Close")
        close_button.clicked.connect(manage_dialog.accept)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(4)
        layout.addWidget(admin_email_button)
        layout.addWidget(reset_password_button)
        layout.addWidget(delete_user_button)
        layout.addWidget(remove_saved_button)
        layout.addStretch()
        layout.addWidget(close_button)

        self._prepare_simple_dark_dialog(manage_dialog)
        self._apply_clickable_cursors(manage_dialog)
        manage_dialog.exec()

    def _add_manage_list_item(
        self,
        list_widget: QListWidget,
        primary_text: str,
        secondary_text: str = "",
        user_data: str = "",
        is_current: bool = False,
        is_admin: bool = False,
        current_badge_tone: str = "green",
        current_badge_first: bool = False,
    ) -> None:
        item = QListWidgetItem()
        item.setData(Qt.UserRole, user_data)
        item.setData(Qt.UserRole + 2, f"{primary_text} {secondary_text}".strip().lower())
        item.setSizeHint(QSize(0, 84))
        list_widget.addItem(item)

        row_widget = QWidget()
        row_widget.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        row_widget.setStyleSheet("background: transparent;")
        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(12, 12, 12, 12)
        row_layout.setSpacing(12)
        row_widget.setLayout(row_layout)

        user_icon = QLabel("\U0001F464")
        user_icon.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        user_icon.setAlignment(Qt.AlignCenter)
        user_icon.setFixedSize(26, 26)
        if getattr(self, "dark_mode", False):
            icon_bg = "#17303b"
            icon_border = "#42697c"
            icon_color = "#d8eef6"
            primary_color = "#eef8fc"
            secondary_color = "#b5ccd7"
        else:
            icon_bg = "#edf5f8" if is_admin else "#eef5f8"
            icon_border = "#b8d2df" if is_admin else "#d6e2ea"
            icon_color = "#2d6478"
            primary_color = "#173543"
            secondary_color = "#6b808b"
        user_icon.setStyleSheet(
            f"background: {icon_bg}; "
            f"border: 1px solid {icon_border}; "
            f"border-radius: {'9px' if is_admin else '13px'}; "
            f"color: {icon_color}; font-size: 13px; font-weight: 700;"
        )
        row_layout.addWidget(user_icon, 0, Qt.AlignVCenter)

        text_label = QLabel()
        text_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        text_label.setWordWrap(True)
        text_label.setTextFormat(Qt.RichText)
        text_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        text_label.setMinimumHeight(34)
        text_label.setStyleSheet(
            f"color: {primary_color}; background: transparent; border: none; padding: 0px; margin: 0px;"
        )
        if secondary_text:
            text_label.setText(
                f"<div style='margin:0; padding:0;'>"
                f"<div style='color:{primary_color}; font-weight:700; margin:0; padding:0;'>{primary_text}</div>"
                f"<div style='color:{secondary_color}; font-size:11px; margin:2px 0 0 0; padding:0;'>{secondary_text}</div>"
                f"</div>"
            )
        else:
            text_label.setText(
                f"<div style='color:{primary_color}; font-weight:700; margin:0; padding:0;'>{primary_text}</div>"
            )
        row_layout.addWidget(text_label, 1)

        current_badge = None
        admin_badge = None

        if is_current:
            current_badge_style = (
                "background: #eef5fd; border: 1px solid #c6dbf6; color: #2a6db4;"
                if current_badge_tone == "blue"
                else "background: #edf8f1; border: 1px solid #cbe6d2; color: #1f8f5f;"
            )
            current_badge = QLabel("Current")
            current_badge.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            current_badge.setStyleSheet(
                f"{current_badge_style} border-radius: 10px; padding: 4px 8px; "
                "font-size: 11px; font-weight: 700;"
            )

        if is_admin:
            admin_badge = QLabel("Admin")
            admin_badge.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            admin_badge.setStyleSheet(
                "background: #edf5f8; border: 1px solid #d8e6ee; border-radius: 10px; "
                "padding: 4px 8px; color: #2c6275; font-size: 11px; font-weight: 700;"
            )

        badge_widgets = []
        if current_badge_first:
            if current_badge is not None:
                badge_widgets.append(current_badge)
            if admin_badge is not None:
                badge_widgets.append(admin_badge)
        else:
            if admin_badge is not None:
                badge_widgets.append(admin_badge)
            if current_badge is not None:
                badge_widgets.append(current_badge)

        for badge in badge_widgets:
            row_layout.addWidget(badge, 0, Qt.AlignVCenter)

        list_widget.setItemWidget(item, row_widget)

    def show_admin_email_manager(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Manage Admin")
        self._apply_standard_dialog_size(dialog, "manager")
        dialog.setStyleSheet(
            "QDialog { background: #f7fbfd; }"
            "QLabel { color: #274652; font-size: 13px; }"
            "QLineEdit { min-height: 38px; border-radius: 12px; border: 1px solid #cad7e1; "
            "background: #ffffff; padding: 6px 12px; color: #173543; font-size: 13px; }"
            "QLineEdit:focus { border-color: #8fb6cb; background: #f9fcff; }"
            "QPushButton { min-height: 38px; border-radius: 12px; border: 1px solid #ccd8e2; "
            "background: #ffffff; color: #173543; font-weight: 700; }"
            "QPushButton:hover { background: #cfe5ee; border-color: #3f7c8f; }"
            "QPushButton:pressed { background: #bddbe6; border-color: #346b7d; }"
            + self._admin_list_stylesheet()
        )

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        dialog.setLayout(layout)

        title = QLabel("Manage Admin")
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #173543;")
        subtitle = QLabel("Add new admin emails or remove an email from the admin list.")
        subtitle.setStyleSheet("color: #5a7380;")
        subtitle.setWordWrap(True)

        search_input = QLineEdit()
        search_input.setPlaceholderText("Search admin emails")

        email_list = QListWidget()
        self._prepare_admin_list_widget(email_list)

        add_button = QPushButton("Add Admin")
        add_button.setDefault(True)
        remove_button = QPushButton("Remove Admin")
        remove_button.setProperty("destructiveAction", "true")
        self._style_destructive_button(remove_button)
        close_button = QPushButton("Close")
        add_button.setMinimumWidth(150)
        close_button.setMinimumWidth(150)
        remove_button.setMinimumWidth(150)
        close_button.clicked.connect(dialog.accept)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(10)
        add_button.setMinimumWidth(140)
        remove_button.setMinimumWidth(140)
        close_button.setMinimumWidth(140)
        add_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        remove_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        close_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        button_row.addWidget(add_button)
        button_row.addStretch()
        button_row.addWidget(remove_button)
        button_row.addStretch()
        button_row.addWidget(close_button)

        def refresh_admin_emails():
            email_list.clear()
            for admin_email in self.auth_manager.get_admin_emails():
                self._add_manage_list_item(
                    email_list,
                    admin_email,
                    "Admin email access",
                    user_data=admin_email,
                    is_current=admin_email == (self.current_email or "").strip().lower(),
                    is_admin=True,
                    current_badge_tone="blue",
                    current_badge_first=True,
                )
            remove_button.setEnabled(email_list.count() > 0)
            self._filter_manage_list_widget(email_list, search_input.text())

        def add_admin_email():
            add_dialog = QDialog(dialog)
            add_dialog.setWindowTitle("Add Admin")
            add_dialog.setModal(True)
            self._apply_standard_dialog_size(add_dialog, "manager")
            add_dialog.setStyleSheet(
                "QDialog { background: #ffffff; }"
                "QLabel { color: #274652; font-size: 13px; }"
                "QPushButton { min-width: 96px; min-height: 36px; border-radius: 10px; border: 1px solid #ccd8e2; "
                "background: #ffffff; color: #173543; font-weight: 700; }"
                "QPushButton:hover { background: #cfe5ee; border-color: #3f7c8f; }"
                "QPushButton:pressed { background: #bddbe6; border-color: #346b7d; }"
                "QListWidget { background: #ffffff; border: 1px solid #d7e2e9; border-radius: 14px; padding: 6px; }"
                "QListWidget::item { padding: 10px 12px; border-radius: 10px; }"
                "QListWidget::item:hover { background: #dfeff4; border: 1px solid #4f8ea1; color: #15394b; }"
                "QListWidget::item:selected { background: #cfe5ee; color: #15394b; }"
            )

            add_layout = QVBoxLayout()
            add_layout.setContentsMargins(18, 18, 18, 16)
            add_layout.setSpacing(12)
            add_dialog.setLayout(add_layout)

            add_title = QLabel("Add Admin")
            add_title.setStyleSheet("font-size: 17px; font-weight: 700; color: #173543;")
            add_note = QLabel("Choose a registered email to add to the admin list.")
            add_note.setStyleSheet("color: #5a7380;")
            add_note.setWordWrap(True)

            candidate_list = QListWidget()
            self._prepare_admin_list_widget(candidate_list)

            existing_admins = set(self.auth_manager.get_admin_emails())
            eligible_records = [
                record for record in self.auth_manager.get_user_records()
                if record["email"] and record["email"] not in existing_admins
            ]

            for record in eligible_records:
                self._add_manage_list_item(
                    candidate_list,
                    record["email"],
                    f"Username: {record['username']}",
                    user_data=record["email"],
                    is_current=record["email"] == (self.current_email or "").strip().lower(),
                    is_admin=False,
                )

            confirm_button = QPushButton("Add")
            cancel_button = QPushButton("Cancel")
            popup_buttons = self._build_dialog_action_row(confirm_button, cancel_button, width=140)

            add_layout.addWidget(add_title)
            add_layout.addWidget(add_note)
            add_layout.addWidget(candidate_list, 1)
            add_layout.addLayout(popup_buttons)

            confirm_button.clicked.connect(add_dialog.accept)
            cancel_button.clicked.connect(add_dialog.reject)

            if not eligible_records:
                confirm_button.setEnabled(True)

            if add_dialog.exec() != QDialog.Accepted:
                return

            if not eligible_records:
                self._show_security_result_popup(
                    "Add Admin Email",
                    "No registered email is available to add as admin.",
                    success=False,
                )
                return

            selected_item = candidate_list.currentItem()
            if selected_item is None:
                self._show_security_result_popup(
                    "Add Admin Email",
                    "Select a registered email first.",
                    success=False,
                )
                return

            email = (selected_item.data(Qt.UserRole) or "").strip().lower()

            added, message = self.auth_manager.add_admin_email(email)
            if not added:
                self._show_security_result_popup("Add Admin", message, success=False)
                return

            refresh_admin_emails()
            self._refresh_admin_actions_visibility()
            self._log_admin_activity("Add Admin", email)
            self._show_security_result_popup("Add Admin", message, success=True)

        def remove_admin_email():
            selected_item = email_list.currentItem()
            if selected_item is None:
                self._show_security_result_popup("Remove Admin", "Select an admin email first.", success=False)
                return

            selected_email = (selected_item.data(Qt.UserRole) or "").strip().lower()
            if selected_email == (self.current_email or "").strip().lower():
                self._show_security_result_popup(
                    "Remove Admin",
                    "You cannot remove the admin email for the account that is currently signed in.",
                    success=False,
                )
                return

            should_remove = self._show_confirmation_popup(
                "Remove Admin",
                f"Are you sure you want to remove {selected_email} from the admin email list?",
                confirm_text="Yes",
                cancel_text="No",
            )
            if not should_remove:
                return

            removed, message = self.auth_manager.remove_admin_email(selected_email)
            if not removed:
                self._show_security_result_popup("Remove Admin", message, success=False)
                return

            refresh_admin_emails()
            self._log_admin_activity("Remove Admin", selected_email)
            self._show_security_result_popup("Remove Admin", message, success=True)

        add_button.clicked.connect(
            lambda: self._run_with_busy_button(add_button, "Adding...", add_admin_email)
        )
        remove_button.clicked.connect(
            lambda: self._run_with_busy_button(remove_button, "Removing...", remove_admin_email)
        )

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self._build_admin_list_panel(search_input, email_list), 1)
        layout.addLayout(button_row)

        search_input.textChanged.connect(lambda text: self._filter_manage_list_widget(email_list, text))
        dialog.setFocusPolicy(Qt.StrongFocus)
        QTimer.singleShot(
            0,
            lambda: (
                search_input.clearFocus(),
                email_list.clearFocus(),
                dialog.setFocus(),
            ),
        )
        refresh_admin_emails()
        self._apply_clickable_cursors(dialog)
        dialog.exec()

    def show_delete_user_manager(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Delete User Account")
        self._apply_standard_dialog_size(dialog, "manager")
        dialog.setStyleSheet(
            "QDialog { background: #f7fbfd; }"
            "QLabel { color: #274652; font-size: 13px; }"
            "QPushButton { min-height: 38px; border-radius: 12px; border: 1px solid #ccd8e2; "
            "background: #ffffff; color: #173543; font-weight: 700; }"
            "QPushButton:hover { background: #cfe5ee; border-color: #3f7c8f; }"
            "QPushButton:pressed { background: #bddbe6; border-color: #346b7d; }"
            "QListWidget { background: #ffffff; border: 1px solid #d7e2e9; border-radius: 14px; padding: 6px; }"
            "QListWidget::item { padding: 10px 12px; border-radius: 10px; }"
            "QListWidget::item:hover { background: #dfeff4; border: 1px solid #4f8ea1; color: #15394b; }"
            "QListWidget::item:selected { background: #cfe5ee; color: #15394b; }"
        )

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        dialog.setLayout(layout)

        title = QLabel("Delete User Account")
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #173543;")
        subtitle = QLabel("Select a registered user account to permanently delete.")
        subtitle.setStyleSheet("color: #5a7380;")
        subtitle.setWordWrap(True)

        search_input = QLineEdit()
        search_input.setPlaceholderText("Search users by username or email")

        user_list = QListWidget()
        self._prepare_admin_list_widget(user_list)

        delete_button = QPushButton("Delete User Account")
        delete_button.setProperty("destructiveAction", "true")
        delete_button.setDefault(True)
        self._style_destructive_button(delete_button)
        close_button = QPushButton("Close")
        close_button.clicked.connect(dialog.accept)
        button_row = self._build_dialog_action_row(delete_button, close_button)

        def refresh_users():
            user_list.clear()
            for record in self.auth_manager.get_user_records():
                username = record["username"]
                email = record["email"]
                if self.auth_manager.is_admin(email) or self.auth_manager.is_admin(username):
                    continue
                self._add_manage_list_item(
                    user_list,
                    username,
                    email,
                    user_data=email,
                    is_current=email == (self.current_email or "").strip().lower(),
                    is_admin=False,
                )
            delete_button.setEnabled(True)
            self._filter_manage_list_widget(user_list, search_input.text())

        def delete_user():
            if user_list.count() == 0:
                self._show_security_result_popup(
                    "Delete User Account",
                    "No account is available to delete.",
                    success=False,
                )
                return

            selected_item = user_list.currentItem()
            if selected_item is None:
                self._show_security_result_popup("Delete User Account", "Select a registered user first.", success=False)
                return

            selected_email = (selected_item.data(Qt.UserRole) or "").strip().lower()
            if selected_email == (self.current_email or "").strip().lower():
                self._show_security_result_popup(
                    "Delete User Account",
                    "You cannot delete the account that is currently signed in.",
                    success=False,
                )
                return

            target_username = self.auth_manager.get_username_for_email(selected_email) or "user"
            if self.auth_manager.is_admin(selected_email) or self.auth_manager.is_admin(target_username):
                self._show_security_result_popup(
                    "Delete User Account",
                    "Admin accounts cannot be deleted from this window.",
                    success=False,
                )
                return

            should_delete = self._show_confirmation_popup(
                "Delete User Account",
                f"Are you sure you want to permanently delete {selected_email}?",
                confirm_text="Delete",
                cancel_text="Cancel",
            )
            if not should_delete:
                return

            deleted, message = self.auth_manager.delete_user_by_email(selected_email)
            if not deleted:
                self._show_security_result_popup("Delete User Account", message, success=False)
                return

            self.credential_store.delete_password(selected_email)
            refresh_users()
            self._log_admin_activity("Delete User", selected_email)
            self._show_security_result_popup("Delete User Account", message, success=True)

        delete_button.clicked.connect(
            lambda: self._run_with_busy_button(delete_button, "Deleting...", delete_user)
        )

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self._build_admin_list_panel(search_input, user_list), 1)
        layout.addLayout(button_row)

        search_input.textChanged.connect(lambda text: self._filter_manage_list_widget(user_list, text))
        dialog.setFocusPolicy(Qt.StrongFocus)
        QTimer.singleShot(
            0,
            lambda: (
                search_input.clearFocus(),
                user_list.clearFocus(),
                dialog.setFocus(),
            ),
        )
        refresh_users()
        self._apply_clickable_cursors(dialog)
        dialog.exec()

    def show_reset_user_password_manager(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Reset User Password")
        self._apply_standard_dialog_size(dialog, "manager")
        dialog.setStyleSheet(
            "QDialog { background: #f7fbfd; }"
            "QLabel { color: #274652; font-size: 13px; }"
            "QLineEdit { min-height: 38px; border-radius: 12px; border: 1px solid #cad7e1; "
            "background: #ffffff; padding: 6px 12px; color: #173543; font-size: 13px; }"
            "QLineEdit:focus { border-color: #8fb6cb; background: #f9fcff; }"
            "QPushButton { min-height: 38px; border-radius: 12px; border: 1px solid #ccd8e2; "
            "background: #ffffff; color: #173543; font-weight: 700; }"
            "QPushButton:hover { background: #cfe5ee; border-color: #3f7c8f; }"
            "QPushButton:pressed { background: #bddbe6; border-color: #346b7d; }"
            "QListWidget { background: #ffffff; border: 1px solid #d7e2e9; border-radius: 14px; padding: 6px; }"
            "QListWidget::item { padding: 10px 12px; border-radius: 10px; }"
            "QListWidget::item:hover { background: #dfeff4; border: 1px solid #4f8ea1; color: #15394b; }"
            "QListWidget::item:selected { background: #cfe5ee; color: #15394b; }"
        )

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        dialog.setLayout(layout)

        title = QLabel("Reset User Password")
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #173543;")
        subtitle = QLabel("Select a registered user and set a new password.")
        subtitle.setStyleSheet("color: #5a7380;")
        subtitle.setWordWrap(True)

        search_input = QLineEdit()
        search_input.setPlaceholderText("Search users by username or email")

        user_list = QListWidget()
        self._prepare_admin_list_widget(user_list)

        password_label = QLabel("New Password <span style='color: red;'>*</span>")
        password_label.setTextFormat(Qt.RichText)
        new_password_input = QLineEdit()
        new_password_input.setPlaceholderText("Enter new password")
        new_password_input.setEchoMode(QLineEdit.Password)
        self._add_password_toggle(new_password_input)

        confirm_label = QLabel("Confirm Password <span style='color: red;'>*</span>")
        confirm_label.setTextFormat(Qt.RichText)
        confirm_password_input = QLineEdit()
        confirm_password_input.setPlaceholderText("Confirm new password")
        confirm_password_input.setEchoMode(QLineEdit.Password)
        self._add_password_toggle(confirm_password_input)

        reset_button = QPushButton("Reset Password")
        reset_button.setDefault(True)
        close_button = QPushButton("Close")
        close_button.clicked.connect(dialog.accept)
        button_row = self._build_dialog_action_row(reset_button, close_button)

        def refresh_users():
            user_list.clear()
            for record in self.auth_manager.get_user_records():
                username = record["username"]
                email = record["email"]
                if self.auth_manager.is_admin(email) or self.auth_manager.is_admin(username):
                    continue
                self._add_manage_list_item(
                    user_list,
                    username,
                    email,
                    user_data=email,
                    is_current=email == (self.current_email or "").strip().lower(),
                    is_admin=False,
                )
            reset_button.setEnabled(True)
            self._filter_manage_list_widget(user_list, search_input.text())

        def reset_user_password():
            if user_list.count() == 0:
                self._show_security_result_popup(
                    "Reset User Password",
                    "No account is available for password reset.",
                    success=False,
                )
                return

            selected_item = user_list.currentItem()
            if selected_item is None:
                self._show_security_result_popup(
                    "Reset User Password",
                    "Select a registered user first.",
                    success=False,
                )
                return

            selected_email = (selected_item.data(Qt.UserRole) or "").strip().lower()
            new_password = new_password_input.text()
            confirm_password = confirm_password_input.text()

            password_errors = validate_password(new_password)
            if password_errors:
                self._show_security_result_popup("Reset User Password", password_errors[0], success=False)
                return

            confirm_errors = validate_confirm_password(new_password, confirm_password)
            if confirm_errors:
                self._show_security_result_popup("Reset User Password", confirm_errors[0], success=False)
                return

            should_reset = self._show_confirmation_popup(
                "Reset User Password",
                f"Are you sure you want to reset the password for {selected_email}?",
                confirm_text="Yes",
                cancel_text="No",
            )
            if not should_reset:
                return

            if not self.auth_manager.reset_password(selected_email, new_password):
                self._show_security_result_popup(
                    "Reset User Password",
                    "User account was not found.",
                    success=False,
                )
                return

            self.credential_store.delete_password(selected_email)
            new_password_input.clear()
            confirm_password_input.clear()
            self._log_admin_activity("Reset Password", selected_email)
            self._show_security_result_popup(
                "Reset User Password",
                "User password reset successfully.",
                success=True,
            )

        reset_button.clicked.connect(
            lambda: self._run_with_busy_button(reset_button, "Resetting...", reset_user_password)
        )

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self._build_admin_list_panel(search_input, user_list), 1)
        layout.addWidget(password_label)
        layout.addWidget(new_password_input)
        layout.addWidget(confirm_label)
        layout.addWidget(confirm_password_input)
        layout.addLayout(button_row)

        dialog.setFocusPolicy(Qt.StrongFocus)
        QTimer.singleShot(
            0,
            lambda: (
                search_input.clearFocus(),
                new_password_input.clearFocus(),
                confirm_password_input.clearFocus(),
                user_list.clearFocus(),
                dialog.setFocus(),
            ),
        )

        search_input.textChanged.connect(lambda text: self._filter_manage_list_widget(user_list, text))
        refresh_users()
        self._apply_clickable_cursors(dialog)
        dialog.exec()

    def show_remove_saved_signin_manager(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Remove Saved Sign-In")
        self._apply_standard_dialog_size(dialog, "manager")
        dialog.setStyleSheet(
            "QDialog { background: #f7fbfd; }"
            "QLabel { color: #274652; font-size: 13px; }"
            "QPushButton { min-height: 38px; border-radius: 12px; border: 1px solid #ccd8e2; "
            "background: #ffffff; color: #173543; font-weight: 700; }"
            "QPushButton:hover { background: #cfe5ee; border-color: #3f7c8f; }"
            "QPushButton:pressed { background: #bddbe6; border-color: #346b7d; }"
            "QListWidget { background: #ffffff; border: 1px solid #d7e2e9; border-radius: 14px; padding: 6px; }"
            "QListWidget::item { padding: 10px 12px; border-radius: 10px; }"
            "QListWidget::item:hover { background: #dfeff4; border: 1px solid #4f8ea1; color: #15394b; }"
            "QListWidget::item:selected { background: #cfe5ee; color: #15394b; }"
        )

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        dialog.setLayout(layout)

        title = QLabel("Remove Saved Sign-In")
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #173543;")
        subtitle = QLabel("Select a saved sign-in from this device to remove it.")
        subtitle.setStyleSheet("color: #5a7380;")
        subtitle.setWordWrap(True)

        search_input = QLineEdit()
        search_input.setPlaceholderText("Search saved sign-ins")

        saved_list = QListWidget()
        self._prepare_admin_list_widget(saved_list)

        remove_button = QPushButton("Remove Saved Sign-In")
        remove_button.setProperty("destructiveAction", "true")
        remove_button.setDefault(True)
        self._style_destructive_button(remove_button)
        close_button = QPushButton("Close")
        close_button.clicked.connect(dialog.accept)
        button_row = self._build_dialog_action_row(remove_button, close_button)

        def refresh_saved_signins():
            saved_list.clear()
            for identity in self.credential_store.get_saved_identities():
                username = self.auth_manager.get_username_for_email(identity) or "Unknown user"
                if self.auth_manager.is_admin(identity) or self.auth_manager.is_admin(username):
                    continue
                self._add_manage_list_item(
                    saved_list,
                    identity,
                    f"Username: {username}",
                    user_data=identity,
                    is_current=identity == (self.current_email or "").strip().lower(),
                    is_admin=False,
                )
            remove_button.setEnabled(True)
            self._filter_manage_list_widget(saved_list, search_input.text())

        def remove_saved_signin():
            if saved_list.count() == 0:
                self._show_security_result_popup(
                    "Remove Saved Sign-In",
                    "No saved account is available to remove from sign-in.",
                    success=False,
                )
                return

            selected_item = saved_list.currentItem()
            if selected_item is None:
                self._show_security_result_popup("Remove Saved Sign-In", "Select a saved sign-in first.", success=False)
                return

            selected_email = (selected_item.data(Qt.UserRole) or "").strip().lower()
            if selected_email == (self.current_email or "").strip().lower():
                self._show_security_result_popup(
                    "Remove Saved Sign-In",
                    "You cannot remove the currently active saved sign-in.",
                    success=False,
                )
                return

            should_remove = self._show_confirmation_popup(
                "Remove Saved Sign-In",
                f"Are you sure you want to remove the saved sign-in for {selected_email} from this device?",
                confirm_text="Yes",
                cancel_text="No",
            )
            if not should_remove:
                return

            self.credential_store.delete_password(selected_email)
            refresh_saved_signins()
            self._log_admin_activity("Remove Saved Sign-In", selected_email)
            self._show_security_result_popup(
                "Remove Saved Sign-In",
                "Saved sign-in removed from this device successfully.",
                success=True,
            )

        remove_button.clicked.connect(
            lambda: self._run_with_busy_button(remove_button, "Removing...", remove_saved_signin)
        )

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self._build_admin_list_panel(search_input, saved_list), 1)
        layout.addLayout(button_row)

        search_input.textChanged.connect(lambda text: self._filter_manage_list_widget(saved_list, text))
        dialog.setFocusPolicy(Qt.StrongFocus)
        QTimer.singleShot(
            0,
            lambda: (
                search_input.clearFocus(),
                saved_list.clearFocus(),
                dialog.setFocus(),
            ),
        )
        refresh_saved_signins()
        self._apply_clickable_cursors(dialog)
        dialog.exec()

    def _build_collapsible_section(self, title, content_widget, expanded=True, click_handler=None):
        section_frame = QFrame()
        section_layout = QVBoxLayout()
        section_layout.setContentsMargins(0, 0, 0, 0)
        section_layout.setSpacing(8 if expanded else 0)
        section_frame.setLayout(section_layout)

        toggle_button = QToolButton()
        toggle_button.setProperty("sectionToggle", "true")
        toggle_button.setText(title)
        toggle_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        toggle_button.setCursor(Qt.PointingHandCursor)
        attach_hover_bounce(toggle_button, y_offset=2, duration=175)
        section_state = {"expanded": expanded}
        content_widget.setMinimumHeight(0)
        content_widget.setMaximumHeight(content_widget.sizeHint().height() if expanded else 0)
        content_animation = QPropertyAnimation(content_widget, b"maximumHeight", section_frame)
        content_animation.setDuration(180)
        content_animation.setEasingCurve(QEasingCurve.OutCubic)

        def sync_visibility():
            if section_state["expanded"]:
                content_widget.setVisible(True)
                content_widget.setMaximumHeight(content_widget.sizeHint().height())
            else:
                content_widget.setVisible(False)
                content_widget.setMaximumHeight(0)

        content_animation.finished.connect(sync_visibility)

        def apply_expanded(is_expanded):
            section_state["expanded"] = is_expanded
            toggle_button.setArrowType(Qt.DownArrow if is_expanded else Qt.RightArrow)
            section_layout.setSpacing(8 if is_expanded else 0)
            content_animation.stop()
            target_height = max(1, content_widget.sizeHint().height())
            current_height = content_widget.maximumHeight()
            if current_height <= 0:
                current_height = target_height

            if is_expanded:
                content_widget.setVisible(True)
                content_animation.setStartValue(max(0, current_height))
                content_animation.setEndValue(target_height)
                content_animation.start()
                return

            if not is_expanded:
                if title == "Change Username":
                    self.new_username_input.clear()
                    self.username_current_password_input.clear()
                    self._set_input_validation_state(self.new_username_input, "")
                    self._set_input_validation_state(self.username_current_password_input, "")
                    self._set_security_message(self.username_feedback_label, "")
                    self._set_security_message(self.username_password_feedback_label, "")
                elif title == "Change Email":
                    self.new_email_input.clear()
                    self.email_current_password_input.clear()
                    self.email_otp_input.clear()
                    self._set_input_validation_state(self.new_email_input, "")
                    self._set_input_validation_state(self.email_current_password_input, "")
                    self._set_security_message(self.email_feedback_label, "")
                    self._set_security_message(self.email_password_feedback_label, "")
                    self._set_security_message(self.email_otp_feedback_label, "")
                    self._reset_email_change_verification()
                elif title == "Change Password":
                    self.security_current_password_input.clear()
                    self.security_new_password_input.clear()
                    self.security_confirm_password_input.clear()
                    self._set_input_validation_state(self.security_current_password_input, "")
                    self._set_input_validation_state(self.security_new_password_input, "")
                    self._set_input_validation_state(self.security_confirm_password_input, "")
                    self._set_security_message(self.password_current_feedback_label, "")
                    self._set_security_message(self.password_new_feedback_label, "")
                    self._set_security_message(self.password_confirm_feedback_label, "")

                content_widget.setVisible(True)
                content_animation.setStartValue(max(0, current_height))
                content_animation.setEndValue(0)
                content_animation.start()

        def on_clicked():
            apply_expanded(not section_state["expanded"])
            if click_handler is not None:
                click_handler()

        apply_expanded(expanded)
        toggle_button.clicked.connect(on_clicked)

        section_layout.addWidget(toggle_button)
        section_layout.addWidget(content_widget)
        return section_frame

    def _build_section_note(self, text):
        note = QLabel(text)
        note.setProperty("sectionNote", "true")
        note.setWordWrap(True)
        return note

    def _admin_list_stylesheet(self):
        if getattr(self, "dark_mode", False):
            return (
                "QListWidget { background: #132630; border: 1px solid #355768; border-radius: 16px; padding: 8px; outline: 0; color: #e7f3f8; }"
                "QListWidget::item { padding: 12px 14px; border-radius: 12px; margin: 2px 0px; color: #e7f3f8; }"
                "QListWidget::item:hover { background: #214353; color: #ffffff; }"
                "QListWidget::item:selected { background: #24506a; color: #ffffff; }"
                "QListWidget::item:focus { outline: none; }"
            )
        return (
            "QListWidget { background: #ffffff; border: 1px solid #d7e2e9; border-radius: 16px; padding: 8px; outline: 0; }"
            "QListWidget::item { padding: 12px 14px; border-radius: 12px; margin: 2px 0px; }"
            "QListWidget::item:hover { background: #dff1f7; color: #15394b; }"
            "QListWidget::item:selected { background: #cfeaf3; color: #15394b; }"
            "QListWidget::item:focus { outline: none; }"
        )

    def _prepare_admin_list_widget(self, list_widget: QListWidget):
        list_widget.setSelectionMode(QAbstractItemView.SingleSelection)
        list_widget.setMouseTracking(True)
        list_widget.setSpacing(6)
        list_widget.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        list_widget.verticalScrollBar().setSingleStep(12)
        list_widget.setFocusPolicy(Qt.NoFocus)

    def _filter_manage_list_widget(self, list_widget: QListWidget, query: str):
        query_text = (query or "").strip().lower()
        for index in range(list_widget.count()):
            item = list_widget.item(index)
            haystack = (item.data(Qt.UserRole + 2) or "").strip().lower()
            item.setHidden(bool(query_text) and query_text not in haystack)

    def _build_admin_list_panel(self, search_input: QLineEdit, list_widget: QListWidget):
        panel = QFrame()
        if getattr(self, "dark_mode", False):
            panel.setStyleSheet(
                "QFrame { background: #132630; border: 1px solid #355768; border-radius: 16px; }"
                "QLineEdit { min-height: 38px; border-radius: 12px; border: 1px solid #3c6273; "
                "background: #16303d; padding: 6px 12px; color: #e7f3f8; font-size: 13px; }"
                "QLineEdit:focus { border-color: #5c8aa0; background: #1e3d4c; color: #ffffff; }"
            )
        else:
            panel.setStyleSheet(
                "QFrame { background: #ffffff; border: 1px solid #d7e2e9; border-radius: 16px; }"
                "QLineEdit { min-height: 38px; border-radius: 12px; border: 1px solid #d7e2e9; "
                "background: #f9fcfe; padding: 6px 12px; color: #173543; font-size: 13px; }"
                "QLineEdit:focus { border-color: #8fb6cb; background: #ffffff; }"
            )
        panel_layout = QVBoxLayout()
        panel_layout.setContentsMargins(8, 8, 8, 8)
        panel_layout.setSpacing(8)
        panel.setLayout(panel_layout)
        if getattr(self, "dark_mode", False):
            list_widget.setStyleSheet(
                "QListWidget { background: transparent; border: none; padding: 0px; outline: 0; color: #e7f3f8; }"
                "QListWidget::item { padding: 12px 14px; border-radius: 12px; margin: 2px 0px; color: #e7f3f8; }"
                "QListWidget::item:hover { background: #214353; color: #ffffff; }"
                "QListWidget::item:selected { background: #24506a; color: #ffffff; }"
                "QListWidget::item:focus { outline: none; }"
            )
        else:
            list_widget.setStyleSheet(
                "QListWidget { background: transparent; border: none; padding: 0px; outline: 0; }"
                "QListWidget::item { padding: 12px 14px; border-radius: 12px; margin: 2px 0px; }"
                "QListWidget::item:hover { background: #dff1f7; color: #15394b; }"
                "QListWidget::item:selected { background: #cfeaf3; color: #15394b; }"
                "QListWidget::item:focus { outline: none; }"
            )
        panel_layout.addWidget(search_input)
        panel_layout.addWidget(list_widget, 1)
        return panel

    def _add_password_toggle(self, line_edit):
        show_icon = QIcon(str(self.assets_dir / "password_eye_windows_off.svg"))
        hide_icon = QIcon(str(self.assets_dir / "password_eye_windows.svg"))
        toggle_action = line_edit.addAction(show_icon, QLineEdit.TrailingPosition)
        toggle_action.setToolTip("Show password")
        toggle_action.setVisible(False)

        def toggle_password_visibility():
            is_hidden = line_edit.echoMode() == QLineEdit.Password
            line_edit.setEchoMode(QLineEdit.Normal if is_hidden else QLineEdit.Password)
            toggle_action.setIcon(hide_icon if is_hidden else show_icon)
            toggle_action.setToolTip("Hide password" if is_hidden else "Show password")

        def sync_toggle_visibility(_text: str):
            has_text = bool(line_edit.text())
            if not has_text:
                line_edit.setEchoMode(QLineEdit.Password)
                toggle_action.setIcon(show_icon)
                toggle_action.setToolTip("Show password")
            toggle_action.setVisible(has_text)

        toggle_action.triggered.connect(toggle_password_visibility)
        line_edit.textChanged.connect(sync_toggle_visibility)

    def _set_security_message(self, label, message="", tone="error"):
        if message:
            display_message = format_validation_message(message)
            icon_color = {
                "error": "#b64a3e",
                "success": "#2c7a4b",
                "neutral": "#6a7f89",
            }.get(tone, "#6a7f89")
            label.setText(
                f'<span style="color:{icon_color}; font-weight:700;">&#128712;</span> {display_message}'
            )
        else:
            label.setText(" ")
        label.setProperty("securityMessage", tone)
        label.style().unpolish(label)
        label.style().polish(label)
        label.update()

    def _set_input_validation_state(self, line_edit, state=""):
        line_edit.setProperty("validationState", state)
        line_edit.style().unpolish(line_edit)
        line_edit.style().polish(line_edit)
        line_edit.update()

    def _show_security_result_popup(self, title, message, success=False):
        popup = QDialog(self)
        popup.setWindowTitle(title)
        popup.setModal(True)
        popup.setMinimumWidth(320)
        if self._is_dark_theme_active():
            popup.setStyleSheet(self._dark_dialog_override_stylesheet())
        else:
            popup.setStyleSheet(
                "QDialog { background: #ffffff; }"
                "QLabel[resultMessage=\"true\"] { color: #173543; font-size: 13px; }"
                "QPushButton { min-width: 84px; min-height: 34px; border-radius: 10px; "
                "border: 1px solid #ccd8e2; background: #ffffff; color: #173543; font-weight: 700; }"
                "QPushButton:hover { background: #cfe5ee; border-color: #3f7c8f; }"
                "QPushButton:pressed { background: #bddbe6; border-color: #346b7d; }"
            )

        layout = QVBoxLayout()
        layout.setContentsMargins(18, 18, 18, 14)
        layout.setSpacing(14)
        popup.setLayout(layout)

        message_row = QHBoxLayout()
        message_row.setContentsMargins(0, 0, 0, 0)
        message_row.setSpacing(10)

        icon_label = QLabel()
        icon_type = QStyle.SP_MessageBoxInformation if success else QStyle.SP_MessageBoxWarning
        icon_label.setPixmap(self.style().standardIcon(icon_type).pixmap(28, 28))
        icon_label.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        message_label = QLabel(message)
        message_label.setProperty("resultMessage", "true")
        message_label.setWordWrap(True)
        message_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)

        message_row.addWidget(icon_label, 0, Qt.AlignTop)
        message_row.addWidget(message_label, 1)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.addStretch()
        ok_button = QPushButton("OK")
        ok_button.setDefault(True)
        ok_button.clicked.connect(popup.accept)
        button_row.addWidget(ok_button)
        button_row.addStretch()

        layout.addLayout(message_row)
        layout.addLayout(button_row)

        self._apply_clickable_cursors(popup)
        popup.exec()

    def _show_confirmation_popup(self, title, message, confirm_text="Yes", cancel_text="No"):
        popup = QDialog(self)
        popup.setWindowTitle(title)
        popup.setModal(True)
        popup.setMinimumWidth(320)
        if self._is_dark_theme_active():
            popup.setStyleSheet(self._dark_dialog_override_stylesheet())
        else:
            popup.setStyleSheet(
                "QDialog { background: #ffffff; }"
                "QLabel[resultMessage=\"true\"] { color: #173543; font-size: 13px; }"
                "QPushButton { min-width: 84px; min-height: 34px; border-radius: 10px; "
                "border: 1px solid #ccd8e2; background: #ffffff; color: #173543; font-weight: 700; }"
                "QPushButton:hover { background: #cfe5ee; border-color: #3f7c8f; }"
                "QPushButton:pressed { background: #bddbe6; border-color: #346b7d; }"
            )

        layout = QVBoxLayout()
        layout.setContentsMargins(18, 18, 18, 14)
        layout.setSpacing(14)
        popup.setLayout(layout)

        message_row = QHBoxLayout()
        message_row.setContentsMargins(0, 0, 0, 0)
        message_row.setSpacing(10)

        icon_label = QLabel()
        icon_label.setPixmap(self.style().standardIcon(QStyle.SP_MessageBoxWarning).pixmap(28, 28))
        icon_label.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        message_label = QLabel(message)
        message_label.setProperty("resultMessage", "true")
        message_label.setWordWrap(True)
        message_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)

        message_row.addWidget(icon_label, 0, Qt.AlignTop)
        message_row.addWidget(message_label, 1)

        confirm_button = QPushButton(confirm_text)
        cancel_button = QPushButton(cancel_text)
        confirm_button.setDefault(True)
        if any(word in confirm_text.lower() for word in ["delete", "remove"]):
            confirm_button.setProperty("destructiveAction", "true")
            self._style_destructive_button(confirm_button)
        confirm_button.clicked.connect(popup.accept)
        cancel_button.clicked.connect(popup.reject)
        button_row = self._build_dialog_action_row(confirm_button, cancel_button, width=120)

        layout.addLayout(message_row)
        layout.addLayout(button_row)

        self._apply_clickable_cursors(popup)
        return popup.exec() == QDialog.Accepted

    def _is_admin_user(self) -> bool:
        return self.auth_manager.is_admin(self.current_email or self.current_user)

    def _rebuild_utility_security_options(self, is_admin: bool) -> None:
        if hasattr(self, "utility_security_options_layout") and self.utility_security_options_layout is not None:
            layout = self.utility_security_options_layout
            for button in [
                self.lock_security_button,
                self.manage_users_button,
                self.reset_settings_button,
            ]:
                if button is not None:
                    layout.removeWidget(button)

            self.lock_security_button.show()
            layout.addWidget(self.lock_security_button)

            if hasattr(self, "manage_users_button") and self.manage_users_button is not None:
                if is_admin:
                    self.manage_users_button.show()
                    layout.addWidget(self.manage_users_button)
                else:
                    self.manage_users_button.hide()

            self.reset_settings_button.show()
            layout.addWidget(self.reset_settings_button)
            layout.setSpacing(22 if is_admin else 12)
            layout.setContentsMargins(0, 0, 0, 4 if is_admin else 2)
            layout.invalidate()
        if hasattr(self, "utility_support_options_layout") and self.utility_support_options_layout is not None:
            self.utility_support_options_layout.setSpacing(12 if is_admin else 12)
            self.utility_support_options_layout.invalidate()

    def _refresh_admin_actions_visibility(self) -> None:
        is_admin = self._is_admin_user()
        self._rebuild_utility_security_options(is_admin)
        if hasattr(self, "admin_activity_log_button") and self.admin_activity_log_button is not None:
            self.admin_activity_log_button.setVisible(is_admin)
        if hasattr(self, "utility_menu_panel") and self.utility_menu_panel is not None:
            self.utility_menu_panel.setProperty("utilityAccent", "true")
            self.utility_menu_panel.style().unpolish(self.utility_menu_panel)
            self.utility_menu_panel.style().polish(self.utility_menu_panel)
            self.utility_menu_panel.update()
        for button in [
            self.lock_security_button,
            self.manage_users_button,
            self.reset_settings_button,
            self.quick_help_button,
            self.about_button,
            self.voice_settings_button,
            self.logout_button,
        ]:
            if button is not None:
                button.setProperty("utilityOutlined", "true")
                attach_hover_bounce(button, y_offset=2, duration=175)
                button.style().unpolish(button)
                button.style().polish(button)
                button.update()
        if hasattr(self, "utility_panel_layout") and self.utility_panel_layout is not None:
            self.utility_panel_layout.invalidate()
            self.utility_panel_layout.activate()
        if hasattr(self, "utility_menu_panel") and self.utility_menu_panel is not None:
            self.utility_menu_panel.setFixedHeight(self._utility_menu_target_height())
            self.utility_menu_panel.updateGeometry()
            self.utility_menu_panel.update()

    def _clear_security_messages(self):
        for label in [
            self.username_feedback_label,
            self.username_password_feedback_label,
            self.email_feedback_label,
            self.email_password_feedback_label,
            self.email_otp_feedback_label,
            self.password_current_feedback_label,
            self.password_new_feedback_label,
            self.password_confirm_feedback_label,
            self.security_status_label,
        ]:
            self._set_security_message(label, "")

    def _refresh_account_security_info(self):
        self.current_email = self.auth_manager.get_email_for_username(self.current_user) or self.current_email
        # Safely update widgets - they should still exist
        if hasattr(self, "account_username_value") and self.account_username_value is not None:
            try:
                self.account_username_value.setText(self.current_user or "Not available")
            except RuntimeError as e:
                print(f"[DEBUG] Error updating username label: {e}")
        if hasattr(self, "account_email_value") and self.account_email_value is not None:
            try:
                self.account_email_value.setText(self.current_email or "Not available")
            except RuntimeError as e:
                print(f"[DEBUG] Error updating email label: {e}")
        if hasattr(self, "utility_user_name_label") and self.utility_user_name_label is not None:
            try:
                self.utility_user_name_label.setText(self.current_user or "User")
            except RuntimeError as e:
                print(f"[DEBUG] Error updating utility user name: {e}")
        if hasattr(self, "utility_user_email_label") and self.utility_user_email_label is not None:
            try:
                self.utility_user_email_label.setText(self.current_email or "No email")
            except RuntimeError as e:
                print(f"[DEBUG] Error updating utility user email: {e}")
        if hasattr(self, "user_footer_label") and self.user_footer_label is not None:
            try:
                self.user_footer_label.setText(f"User: {self.current_user}")
            except RuntimeError as e:
                print(f"[DEBUG] Error updating footer label: {e}")
        try:
            self._refresh_admin_actions_visibility()
        except RuntimeError as e:
            print(f"[DEBUG] Error refreshing admin visibility: {e}")
        try:
            self._load_current_user_preferences()
        except RuntimeError as e:
            print(f"[DEBUG] Error loading user preferences: {e}")

    def _handle_live_security_username(self, input_widget, feedback_label):
        username = normalize_username(input_widget.text())
        if not username:
            self._set_security_message(feedback_label, "")
            self._set_input_validation_state(input_widget, "")
            return

        username_errors = validate_username(username)
        if username_errors:
            self._set_security_message(feedback_label, username_errors[0], "error")
            self._set_input_validation_state(input_widget, "error")
            return

        if username == self.current_user:
            self._set_security_message(feedback_label, "this is already your current username", "error")
            self._set_input_validation_state(input_widget, "error")
            return

        if self.auth_manager.username_exists(username):
            self._set_security_message(feedback_label, "This username is already taken by another user.", "error")
            self._set_input_validation_state(input_widget, "error")
            return

        self._set_security_message(feedback_label, "Username is available.", "success")
        self._set_input_validation_state(input_widget, "success")

    def _handle_live_current_password(self, text, target_label, input_widget=None):
        password = text or ""
        if not password:
            self._set_security_message(target_label, "")
            if input_widget:
                self._set_input_validation_state(input_widget, "")
            elif target_label is self.username_password_feedback_label:
                self._set_input_validation_state(self.username_current_password_input, "")
            elif target_label is self.email_password_feedback_label:
                self._set_input_validation_state(self.email_current_password_input, "")
            elif target_label is self.password_current_feedback_label:
                self._set_input_validation_state(self.security_current_password_input, "")
            return

        if not self.current_email:
            self._set_security_message(target_label, "Current account email is not available.", "error")
            if input_widget:
                self._set_input_validation_state(input_widget, "error")
            return

        if self.auth_manager.authenticate_email(self.current_email, password):
            if input_widget:
                self._set_security_message(target_label, "Current password is correct.", "success")
                self._set_input_validation_state(input_widget, "success")
            elif target_label is self.username_password_feedback_label:
                self._set_security_message(target_label, "Current password is correct.", "success")
                self._set_input_validation_state(self.username_current_password_input, "success")
            elif target_label is self.email_password_feedback_label:
                self._set_security_message(target_label, "Current password is correct.", "success")
                self._set_input_validation_state(self.email_current_password_input, "success")
            elif target_label is self.password_current_feedback_label:
                self._set_security_message(target_label, "Current password is correct.", "success")
                self._set_input_validation_state(self.security_current_password_input, "success")
            else:
                self._set_security_message(target_label, "Current password is correct.", "success")
        else:
            if input_widget:
                self._set_security_message(target_label, "Current password is incorrect.", "error")
                self._set_input_validation_state(input_widget, "error")
            elif target_label is self.username_password_feedback_label:
                self._set_security_message(target_label, "Current password is incorrect.", "error")
                self._set_input_validation_state(self.username_current_password_input, "error")
            elif target_label is self.email_password_feedback_label:
                self._set_security_message(target_label, "Current password is incorrect.", "error")
                self._set_input_validation_state(self.email_current_password_input, "error")
            elif target_label is self.password_current_feedback_label:
                self._set_security_message(target_label, "Current password is incorrect.", "error")
                self._set_input_validation_state(self.security_current_password_input, "error")
            else:
                self._set_security_message(target_label, "Current password is incorrect.", "error")

    def _handle_live_security_email(self, input_widget, feedback_label, send_button=None, resend_button=None):
        email = input_widget.text().strip().lower()
        if not email:
            self._set_security_message(feedback_label, "")
            self._sync_email_change_otp_buttons(input_widget, send_button, resend_button)
            return

        email_errors = validate_email(email)
        if email_errors:
            self._set_security_message(feedback_label, email_errors[0], "error")
            self._sync_email_change_otp_buttons(input_widget, send_button, resend_button)
            return

        if email == self.current_email:
            self._set_security_message(feedback_label, "This is already your current email.", "error")
            self._sync_email_change_otp_buttons(input_widget, send_button, resend_button)
            return

        if self.auth_manager.email_exists(email):
            self._set_security_message(feedback_label, "This email is already registered.", "error")
            self._sync_email_change_otp_buttons(input_widget, send_button, resend_button)
            return

        self._set_security_message(feedback_label, "Email is available for verification.", "success")
        self._sync_email_change_otp_buttons(input_widget, send_button, resend_button)

    def _reset_email_change_verification(self):
        self.email_change_verified_email = ""
        self.email_change_verified_code = ""
        self.email_change_last_otp_attempt = ""
        self.email_change_failed_code = ""
        self.email_change_resend_available = False
        self.email_change_otp_timer.stop()
        self.email_change_resend_seconds_remaining = 0
        self.email_otp_input.clear()
        self.email_otp_input.setEnabled(False)
        self.send_email_otp_button.setText("Send OTP")
        self.resend_email_otp_button.setText("Resend OTP")
        self._set_security_message(self.email_otp_feedback_label, "")
        self._sync_email_change_otp_buttons()

    def _sync_email_change_otp_buttons(self, email_input=None, send_button=None, resend_button=None):
        email_widget = email_input or self.new_email_input
        send_widget = send_button or self.send_email_otp_button
        resend_widget = resend_button or self.resend_email_otp_button

        email = email_widget.text().strip().lower()
        email_ready = bool(email) and not validate_email(email) and email != self.current_email and not self.auth_manager.email_exists(email)
        verified_current_email = bool(email) and self.email_change_verified_email == email
        if verified_current_email:
            self.email_change_resend_available = False
        cooldown_active = self.email_change_resend_seconds_remaining > 0
        send_widget.setEnabled(
            email_ready and not cooldown_active and not self.email_change_resend_available and not verified_current_email
        )
        resend_widget.setEnabled(
            email_ready and (not cooldown_active) and self.email_change_resend_available and not verified_current_email
        )

    def _start_email_change_otp_cooldown(self, seconds=30):
        self.email_change_resend_available = True
        self.email_change_resend_seconds_remaining = seconds
        self._sync_email_change_otp_buttons()
        self.send_email_otp_button.setEnabled(False)
        self.resend_email_otp_button.setEnabled(False)
        self._update_email_change_otp_button_labels()
        self.email_change_otp_timer.start()

    def _tick_email_change_otp_cooldown(self):
        if self.email_change_resend_seconds_remaining <= 0:
            self.email_change_otp_timer.stop()
            self.send_email_otp_button.setText("Send OTP")
            self.resend_email_otp_button.setText("Resend OTP")
            self._sync_email_change_otp_buttons()
            if self.email_change_resend_available:
                self.send_email_otp_button.setEnabled(False)
                self.resend_email_otp_button.setEnabled(True)
            return

        self.email_change_resend_seconds_remaining -= 1
        self._update_email_change_otp_button_labels()
        if self.email_change_resend_seconds_remaining <= 0:
            self.email_change_otp_timer.stop()
            self.send_email_otp_button.setText("Send OTP")
            self.resend_email_otp_button.setText("Resend OTP")
            self._sync_email_change_otp_buttons()
            if self.email_change_resend_available:
                self.send_email_otp_button.setEnabled(False)
                self.resend_email_otp_button.setEnabled(True)

    def _update_email_change_otp_button_labels(self):
        countdown = self.email_change_resend_seconds_remaining
        self.send_email_otp_button.setText("Send OTP")
        self.resend_email_otp_button.setText(f"Resend OTP ({countdown}s)")

    def send_email_change_otp(self):
        self._dispatch_email_change_otp("send")

    def resend_email_change_otp(self):
        self._dispatch_email_change_otp("resend")

    def _dispatch_email_change_otp(self, send_mode):
        email = self.new_email_input.text().strip().lower()
        self._set_security_message(self.email_password_feedback_label, "")
        self._set_security_message(self.email_otp_feedback_label, "")

        email_errors = validate_email(email)
        if email_errors:
            self._set_security_message(self.email_feedback_label, email_errors[0], "error")
            self.new_email_input.setFocus()
            return

        if email == self.current_email:
            self._set_security_message(self.email_feedback_label, "This is already your current email.", "error")
            self.new_email_input.setFocus()
            return

        if self.auth_manager.email_exists(email):
            self._set_security_message(self.email_feedback_label, "This email is already registered.", "error")
            self.new_email_input.setFocus()
            return

        try:
            otp_code = self.otp_service.generate_for_email(email)
            self.email_service.send_otp_email(email, otp_code)
        except EmailDeliveryError as error:
            self._set_security_message(self.email_feedback_label, str(error), "error")
            return

        self.email_change_verified_email = ""
        self.email_change_verified_code = ""
        self.email_change_last_otp_attempt = ""
        self.email_change_failed_code = ""
        self.email_change_resend_available = True
        self.email_otp_input.setEnabled(True)
        self.email_otp_input.setFocus()
        if send_mode == "resend":
            self._set_security_message(self.email_otp_feedback_label, f"OTP Resend Successfully to {email}", "success")
        else:
            self._set_security_message(self.email_otp_feedback_label, f"OTP Send Successfully to {email}", "success")
        self._start_email_change_otp_cooldown()

    def _handle_live_email_change_otp_input(self, text, email_input=None, otp_input=None, otp_feedback_label=None, send_button=None, resend_button=None):
        code = (text or "").strip()
        current_email = (email_input.text().strip().lower() if email_input is not None else self.new_email_input.text().strip().lower())
        target_label = otp_feedback_label or self.email_otp_feedback_label
        if not current_email:
            self._set_security_message(target_label, "")
            return

        if code != self.email_change_last_otp_attempt and code != self.email_change_verified_code:
            self.email_change_verified_email = ""
            self.email_change_verified_code = ""

        if not code:
            self._set_security_message(target_label, "")
            return

        if len(code) < 6:
            self.email_change_last_otp_attempt = ""
            self._set_security_message(target_label, "OTP must be 6 digits.", "error")
            return

        if len(code) > 6:
            self.email_change_last_otp_attempt = ""
            self._set_security_message(target_label, "OTP cannot exceed 6 digits.", "error")
            return

        if code == self.email_change_last_otp_attempt:
            if self.email_change_verified_email == current_email:
                self._set_security_message(target_label, "OTP verified successfully.", "success")
            return

        self.email_change_last_otp_attempt = code
        otp_status = self.otp_service.verify_status_for_email(current_email, code)
        if otp_status != "valid":
            self.email_change_verified_email = ""
            self.email_change_verified_code = ""
            self.email_change_failed_code = code
            self.email_change_resend_available = True
            if otp_status == "expired":
                self._set_security_message(target_label, "OTP has expired.", "error")
            else:
                self._set_security_message(target_label, "OTP is wrong.", "error")
            if otp_input is not None or send_button is not None or resend_button is not None:
                self._sync_email_change_otp_buttons(email_input, send_button, resend_button)
            else:
                self._sync_email_change_otp_buttons()
            return

        self.email_change_verified_email = current_email
        self.email_change_verified_code = code
        self.email_change_failed_code = ""
        self.email_change_resend_available = False
        if otp_input is not None:
            otp_input.setEnabled(True)
            otp_input.setFocus()
        self._sync_email_change_otp_buttons(email_input, send_button, resend_button)
        self._set_security_message(target_label, "OTP verified successfully.", "success")

    def _handle_live_security_password(self, input_widget, feedback_label):
        password = input_widget.text() or ""
        if not password:
            self._set_security_message(feedback_label, "")
            self._set_input_validation_state(input_widget, "")
            return

        password_errors = validate_password(password)
        if password_errors:
            self._set_security_message(feedback_label, password_errors[0], "error")
            self._set_input_validation_state(input_widget, "error")
            return

        self._set_security_message(feedback_label, "Strong password.", "success")
        self._set_input_validation_state(input_widget, "success")

    def _handle_live_security_confirm_password(self, password_input, confirm_input, feedback_label):
        password = password_input.text()
        confirm_password = confirm_input.text()
        if not confirm_password:
            self._set_security_message(feedback_label, "")
            self._set_input_validation_state(confirm_input, "")
            return

        confirm_errors = validate_confirm_password(password, confirm_password)
        if confirm_errors:
            self._set_security_message(feedback_label, confirm_errors[0], "error")
            self._set_input_validation_state(confirm_input, "error")
            return

        self._set_security_message(feedback_label, "Passwords match.", "success")
        self._set_input_validation_state(confirm_input, "success")

    def _handle_live_current_username(self, input_widget, feedback_label):
        current_username = normalize_username(input_widget.text())
        if not current_username:
            self._set_security_message(feedback_label, "")
            self._set_input_validation_state(input_widget, "")
            return

        username_errors = validate_username(current_username)
        if username_errors:
            self._set_security_message(feedback_label, username_errors[0], "error")
            self._set_input_validation_state(input_widget, "error")
            return

        if current_username != self.current_user:
            self._set_security_message(feedback_label, "Current username is incorrect.", "error")
            self._set_input_validation_state(input_widget, "error")
            return

        self._set_security_message(feedback_label, "Current username is correct.", "success")
        self._set_input_validation_state(input_widget, "success")

    def _update_username_from_dialog(self, current_username_input, new_username_input, username_current_password_input, current_username_feedback_label, username_feedback_label, username_password_feedback_label, username_dialog=None):
        current_username = normalize_username(current_username_input.text())
        new_username = normalize_username(new_username_input.text())
        current_password = username_current_password_input.text()
        self._set_security_message(self.security_status_label, "")
        self._set_security_message(current_username_feedback_label, "")
        self._set_security_message(username_password_feedback_label, "")

        if not current_username:
            message = "Current username is required."
            self._set_security_message(current_username_feedback_label, message, "error")
            current_username_input.setFocus()
            self._show_security_result_popup("Username Update", message, success=False)
            return

        current_username_errors = validate_username(current_username)
        if current_username_errors:
            self._set_security_message(current_username_feedback_label, current_username_errors[0], "error")
            current_username_input.setFocus()
            self._show_security_result_popup("Username Update", current_username_errors[0], success=False)
            return

        if current_username != self.current_user:
            message = "Current username is incorrect."
            self._set_security_message(current_username_feedback_label, message, "error")
            current_username_input.setFocus()
            self._show_security_result_popup("Username Update", message, success=False)
            return

        username_errors = validate_username(new_username)
        if username_errors:
            self._set_security_message(username_feedback_label, username_errors[0], "error")
            new_username_input.setFocus()
            self._show_security_result_popup("Username Update", username_errors[0], success=False)
            return

        if new_username == self.current_user:
            message = "this is already your current username"
            self._set_security_message(username_feedback_label, message, "error")
            new_username_input.setFocus()
            self._show_security_result_popup("Username Update", message, success=False)
            return

        if self.auth_manager.username_exists(new_username):
            message = "This username is already taken by another user."
            self._set_security_message(username_feedback_label, message, "error")
            new_username_input.setFocus()
            self._show_security_result_popup("Username Update", message, success=False)
            return

        if not current_password:
            message = "Current password is required."
            self._set_security_message(username_password_feedback_label, message, "error")
            username_current_password_input.setFocus()
            self._show_security_result_popup("Username Update", message, success=False)
            return

        updated, message = self.auth_manager.update_username(self.current_user, current_password, new_username)
        if not updated:
            self._set_security_message(username_password_feedback_label, message, "error")
            username_current_password_input.setFocus()
            self._show_security_result_popup("Username Update", message, success=False)
            return

        self.current_user = new_username
        self._set_security_message(current_username_feedback_label, "Current username is correct.", "success")
        self._set_security_message(username_feedback_label, "Username updated successfully!", "success")
        self._set_security_message(username_password_feedback_label, "Current password is correct.", "success")
        current_username_input.clear()
        new_username_input.clear()
        username_current_password_input.clear()

        # Close dialog
        if username_dialog:
            username_dialog.accept()

        # Use QTimer to refresh UI and show popup AFTER dialog is fully closed
        from PySide6.QtCore import QTimer
        success_message = message  # Capture message for the callback
        def on_dialog_closed():
            print(f"[DEBUG] Dialog closed callback - updating username to {self.current_user}")
            try:
                self._refresh_account_security_info()
                print(f"[DEBUG] Refresh successful")
            except Exception as e:
                print(f"[DEBUG] Refresh error: {e}")
            self._show_security_result_popup("Username Update", success_message, success=True)
        QTimer.singleShot(100, on_dialog_closed)

    def update_account_username(self):
        self.show_change_username_dialog()

    def update_account_email(self):
        new_email = self.new_email_input.text().strip().lower()
        current_password = self.email_current_password_input.text()
        self._set_security_message(self.security_status_label, "")
        self._set_security_message(self.email_password_feedback_label, "")

        email_errors = validate_email(new_email)
        if email_errors:
            self._set_security_message(self.email_feedback_label, email_errors[0], "error")
            self.new_email_input.setFocus()
            self._show_security_result_popup("Email Update", email_errors[0], success=False)
            return

        if new_email == self.current_email:
            message = "This is already your current email."
            self._set_security_message(self.email_feedback_label, message, "error")
            self.new_email_input.setFocus()
            self._show_security_result_popup("Email Update", message, success=False)
            return

        if self.auth_manager.email_exists(new_email):
            message = "This email is already registered."
            self._set_security_message(self.email_feedback_label, message, "error")
            self.new_email_input.setFocus()
            self._show_security_result_popup("Email Update", message, success=False)
            return

        if not current_password:
            message = "Current password is required."
            self._set_security_message(self.email_password_feedback_label, message, "error")
            self.email_current_password_input.setFocus()
            self._show_security_result_popup("Email Update", message, success=False)
            return

        if not self.email_change_verified_email or self.email_change_verified_email != new_email:
            message = "Verify the OTP for this email before updating."
            self._set_security_message(self.email_otp_feedback_label, message, "error")
            self.email_otp_input.setFocus()
            self._show_security_result_popup("Email Update", message, success=False)
            return

        updated, message = self.auth_manager.update_email(self.current_user, current_password, new_email)
        if not updated:
            self._set_security_message(self.email_password_feedback_label, message, "error")
            self.email_current_password_input.setFocus()
            self._show_security_result_popup("Email Update", message, success=False)
            return

        self.current_email = new_email
        self._refresh_account_security_info()
        self.credential_store.set_password(new_email, current_password)
        self.otp_service.clear_for_email(new_email)
        self._reset_email_change_verification()
        self._set_security_message(self.email_feedback_label, message, "success")
        self._set_security_message(self.email_password_feedback_label, "")
        self._set_security_message(self.email_otp_feedback_label, "OTP verified successfully.", "success")
        self.new_email_input.clear()
        self.email_current_password_input.clear()
        self._show_security_result_popup("Email Update", message, success=True)

    def update_account_password(self):
        current_password = self.security_current_password_input.text()
        new_password = self.security_new_password_input.text()
        confirm_password = self.security_confirm_password_input.text()
        self._set_security_message(self.security_status_label, "")
        self._set_security_message(self.password_current_feedback_label, "")

        if not current_password:
            message = "Current password is required."
            self._set_security_message(self.password_current_feedback_label, message, "error")
            self.security_current_password_input.setFocus()
            self._show_security_result_popup("Password Update", message, success=False)
            return

        if current_password == new_password:
            message = "Current password and new password cannot be the same."
            self._set_security_message(self.password_new_feedback_label, message, "error")
            self._set_input_validation_state(self.security_new_password_input, "error")
            self.security_new_password_input.setFocus()
            self._show_security_result_popup("Password Update", message, success=False)
            return

        password_errors = validate_password(new_password)
        if password_errors:
            self._set_security_message(self.password_new_feedback_label, password_errors[0], "error")
            self.security_new_password_input.setFocus()
            self._show_security_result_popup("Password Update", password_errors[0], success=False)
            return

        confirm_errors = validate_confirm_password(new_password, confirm_password)
        if confirm_errors:
            self._set_security_message(self.password_confirm_feedback_label, confirm_errors[0], "error")
            self.security_confirm_password_input.setFocus()
            self._show_security_result_popup("Password Update", confirm_errors[0], success=False)
            return

        updated, message = self.auth_manager.update_password(self.current_email, current_password, new_password)
        if not updated:
            self._set_security_message(self.password_current_feedback_label, message, "error")
            self.security_current_password_input.setFocus()
            self._show_security_result_popup("Password Update", message, success=False)
            return

        self._set_security_message(self.password_current_feedback_label, "Current password is correct.", "success")
        self._set_security_message(self.password_new_feedback_label, "Strong password.", "success")
        self._set_security_message(self.password_confirm_feedback_label, "Passwords match.", "success")
        self.credential_store.set_password(self.current_email, new_password)
        self.security_current_password_input.clear()
        self.security_new_password_input.clear()
        self.security_confirm_password_input.clear()
        self._show_security_result_popup("Password Update", message, success=True)

    def _update_password_from_dialog(
        self,
        current_password_input,
        new_password_input,
        confirm_password_input,
        current_feedback_label,
        new_feedback_label,
        confirm_feedback_label,
        password_dialog=None,
    ):
        current_password = current_password_input.text()
        new_password = new_password_input.text()
        confirm_password = confirm_password_input.text()

        self._set_security_message(current_feedback_label, "")
        self._set_security_message(new_feedback_label, "")
        self._set_security_message(confirm_feedback_label, "")

        if not current_password:
            message = "Current password is required."
            self._set_security_message(current_feedback_label, message, "error")
            current_password_input.setFocus()
            self._show_security_result_popup("Password Update", message, success=False)
            return

        if current_password == new_password:
            message = "Current password and new password cannot be the same."
            self._set_security_message(new_feedback_label, message, "error")
            self._set_input_validation_state(new_password_input, "error")
            new_password_input.setFocus()
            self._show_security_result_popup("Password Update", message, success=False)
            return

        password_errors = validate_password(new_password)
        if password_errors:
            self._set_security_message(new_feedback_label, password_errors[0], "error")
            new_password_input.setFocus()
            self._show_security_result_popup("Password Update", password_errors[0], success=False)
            return

        confirm_errors = validate_confirm_password(new_password, confirm_password)
        if confirm_errors:
            self._set_security_message(confirm_feedback_label, confirm_errors[0], "error")
            confirm_password_input.setFocus()
            self._show_security_result_popup("Password Update", confirm_errors[0], success=False)
            return

        updated, message = self.auth_manager.update_password(self.current_email, current_password, new_password)
        if not updated:
            self._set_security_message(current_feedback_label, message, "error")
            current_password_input.setFocus()
            self._show_security_result_popup("Password Update", message, success=False)
            return

        self._set_security_message(current_feedback_label, "Current password is correct.", "success")
        self._set_security_message(new_feedback_label, "Strong password.", "success")
        self._set_security_message(confirm_feedback_label, "Passwords match.", "success")
        self.credential_store.set_password(self.current_email, new_password)
        current_password_input.clear()
        new_password_input.clear()
        confirm_password_input.clear()
        self._show_security_result_popup("Password Update", message, success=True)

    def _set_badge(self, label, text, tone="muted", **kwargs):
        previous_vertical = None
        previous_horizontal = None
        if hasattr(self, "sidebar_scroll") and self.sidebar_scroll is not None:
            previous_vertical = self.sidebar_scroll.verticalScrollBar().value()
            previous_horizontal = self.sidebar_scroll.horizontalScrollBar().value()

        label.setText(self._format_live_badge_text(label, text))
        label.setProperty("tone", tone)
        if (
            getattr(self, "action_value", None) is label
            and text == "Presentation Not Found!"
        ):
            label.setStyleSheet("font-size: 13px; padding: 8px 12px;")
        else:
            label.setStyleSheet("font-size: 13px; padding: 8px 12px;")
        label.style().unpolish(label)
        label.style().polish(label)
        label.update()

        if getattr(self, "camera_state_badge", None) is label and getattr(self, "camera_footer_label", None) is not None:
            self.camera_footer_label.setText(f"Camera: {text}")
            self.camera_footer_label.style().unpolish(self.camera_footer_label)
            self.camera_footer_label.style().polish(self.camera_footer_label)
            self.camera_footer_label.update()

        if previous_vertical is not None:
            self.sidebar_scroll.verticalScrollBar().setValue(previous_vertical)
        if previous_horizontal is not None:
            self.sidebar_scroll.horizontalScrollBar().setValue(previous_horizontal)

    def _format_live_badge_text(self, label, text):
        if not isinstance(text, str):
            return text

        if label in {
            getattr(self, "gesture_value", None),
            getattr(self, "voice_value", None),
            getattr(self, "status_value", None),
        }:
            words = text.split()
            return " ".join(
                word[:1].upper() + word[1:].lower() if any(ch.isalpha() for ch in word) else word
                for word in words
            )

        return text

    def _set_recent_activity(self, text, tone="info"):
        self._set_badge(self.status_value, text, tone)

    def _sync_camera_buttons(self, running: bool):
        self.start_button.setText("Start Camera")
        self.stop_button.setText("Stop Camera")
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)

    def _run_with_busy_button(self, button, busy_text, callback, restore_enabled: bool = True):
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

    def _apply_standard_dialog_size(self, dialog, variant="standard"):
        size_map = {
            "standard": (500, 460),
            "form": (500, 560),
            "manager": (500, 560),
        }
        width, height = size_map.get(variant, size_map["standard"])
        dialog.setMinimumSize(width, height)
        dialog.resize(width, height)

    def _move_dialog_higher(self, dialog, y_offset=32):
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        available_rect = screen.availableGeometry()
        if self.isVisible():
            anchor_rect = self.frameGeometry()
            target_x = anchor_rect.center().x() - (dialog.width() // 2)
            target_y = anchor_rect.center().y() - (dialog.height() // 2) - y_offset
        else:
            target_x = available_rect.center().x() - (dialog.width() // 2)
            target_y = available_rect.center().y() - (dialog.height() // 2) - y_offset

        min_x = available_rect.left()
        max_x = max(min_x, available_rect.right() - dialog.width() + 1)
        min_y = available_rect.top()
        max_y = max(min_y, available_rect.bottom() - dialog.height() + 1)
        dialog.move(
            max(min_x, min(target_x, max_x)),
            max(min_y, min(target_y, max_y)),
        )

    def _apply_header_branding(self):
        if not hasattr(self, "header_label") or self.header_label is None:
            return
        if isinstance(self.header_label, BrandHeadingLabel):
            self.header_label.setDarkMode(self.dark_mode)

    def _build_dialog_action_row(self, primary_button, secondary_button, width=160):
        primary_button.setMinimumWidth(width)
        secondary_button.setMinimumWidth(width)
        primary_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        secondary_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        row.addWidget(primary_button)
        row.addWidget(secondary_button)
        return row

    def _style_destructive_button(self, button):
        button.setStyleSheet(
            "QPushButton { background: #fff4f2; border: 1px solid #efc5bd; color: #973d32; font-weight: 700; }"
            "QPushButton:hover { background: #ffe6e0; border-color: #d47f71; color: #7f2f27; }"
            "QPushButton:pressed { background: #f5d6cf; border-color: #c96f63; color: #70261f; }"
            "QPushButton:disabled { background: #f7f1f0; border-color: #ead8d5; color: #bda39c; }"
        )

    def _apply_clickable_cursors(self, widget):
        if isinstance(widget, QDialog):
            widget.setProperty("darkDialogStyled", "false")
            widget.setProperty("skipFadeInTransition", True)
            widget.setProperty("dialogOpeningHidden", "true")
            widget.setWindowOpacity(0.0)
            if self._is_dark_theme_active():
                widget.setProperty("darkOpeningHidden", "true")
            self._apply_dark_dialog_overrides(widget, force=True)
            enable_soft_window_transitions(widget, fade_in_ms=190, fade_out_ms=150)

        for child in widget.findChildren(QWidget):
            if isinstance(child, (QPushButton, QToolButton, QComboBox, QAbstractSpinBox)):
                child.setCursor(Qt.PointingHandCursor)
                if isinstance(child, QPushButton) and child.property("textLink") == "true":
                    attach_hover_bounce(child, y_offset=1, duration=170)
                elif isinstance(child, QAbstractSpinBox):
                    attach_hover_bounce(child, y_offset=1, duration=170)
                else:
                    attach_hover_bounce(child)
                if isinstance(child, QComboBox) and child.view() is not None:
                    child.view().setCursor(Qt.PointingHandCursor)
                    child.view().viewport().setCursor(Qt.PointingHandCursor)
            elif isinstance(child, QCheckBox):
                child.setCursor(Qt.PointingHandCursor)
                attach_hover_bounce(child, y_offset=1, duration=170)
            elif isinstance(child, QListWidget):
                child.setCursor(Qt.PointingHandCursor)
            elif isinstance(child, QLabel):
                label_text = child.text() or ""
                if "<a " in label_text.lower():
                    child.setTextInteractionFlags(Qt.TextBrowserInteraction | Qt.TextSelectableByMouse)
                    attach_hover_bounce(child, y_offset=1, duration=170)
                elif label_text.strip():
                    child.setTextInteractionFlags(Qt.TextSelectableByMouse)

    def _set_utility_button_active(self, button, is_active: bool):
        if button is None:
            return
        button.setProperty("utilityActive", "true" if is_active else "false")
        button.style().unpolish(button)
        button.style().polish(button)
        button.update()

    def _open_utility_action(self, button, action):
        self._set_utility_button_active(button, True)
        self.utility_action_active = True
        try:
            action()
        finally:
            self.utility_action_active = False
            self._set_utility_button_active(button, False)

    def _sync_mode_dropdown(self):
        if not hasattr(self, "mode_value") or self.mode_value is None:
            return

        target_index = self.mode_value.findData(self.current_mode)
        if target_index < 0:
            return

        was_blocked = self.mode_value.blockSignals(True)
        self.mode_value.setCurrentIndex(target_index)
        self.mode_value.blockSignals(was_blocked)

    def _change_mode_from_dropdown(self, *_args):
        selected_mode = self.mode_value.currentData()
        if selected_mode == self.current_mode:
            return
        if selected_mode == AppState.JUMP_MODE:
            self.set_jump_mode()
        else:
            self.set_control_mode()

    def _toggle_utility_menu(self):
        self.utility_menu_open = not self.utility_menu_open
        checked = self.utility_menu_open
        if hasattr(self, "utility_menu_button") and self.utility_menu_button is not None:
            self.utility_menu_button.setToolTip("Close utility menu" if checked else "Open utility menu")
        if not hasattr(self, "utility_menu_panel") or self.utility_menu_panel is None:
            return
        if not hasattr(self, "sidebar_container") or self.sidebar_container is None:
            return

        panel_width = self.utility_menu_panel.width() or 266
        panel_height = self._utility_menu_target_height()
        closed_rect = QRect(-(panel_width + 14), 12, panel_width, panel_height)
        open_rect = QRect(14, 12, panel_width, panel_height)
        self.utility_menu_panel.setFixedHeight(panel_height)
        self.utility_menu_panel.raise_()

        if not hasattr(self, "utility_menu_animation") or self.utility_menu_animation is None:
            return
        self.utility_menu_animation.stop()
        if hasattr(self, "utility_menu_opacity_animation") and self.utility_menu_opacity_animation is not None:
            self.utility_menu_opacity_animation.stop()
        if checked:
            self.utility_menu_animation.setDuration(320)
            self.utility_menu_animation.setEasingCurve(QEasingCurve.OutCubic)
            if hasattr(self, "utility_menu_opacity_animation") and self.utility_menu_opacity_animation is not None:
                self.utility_menu_opacity_animation.setDuration(280)
                self.utility_menu_opacity_animation.setEasingCurve(QEasingCurve.OutCubic)
            self.utility_menu_panel.setGeometry(closed_rect)
            if hasattr(self, "utility_menu_opacity_effect") and self.utility_menu_opacity_effect is not None:
                self.utility_menu_opacity_effect.setOpacity(0.0)
            self.utility_menu_panel.show()
            self.utility_menu_animation.setStartValue(closed_rect)
            self.utility_menu_animation.setEndValue(open_rect)
            if hasattr(self, "utility_menu_opacity_animation") and self.utility_menu_opacity_animation is not None:
                self.utility_menu_opacity_animation.setStartValue(0.0)
                self.utility_menu_opacity_animation.setEndValue(1.0)
                self.utility_menu_opacity_animation.start()
        else:
            self.utility_menu_animation.setStartValue(self.utility_menu_panel.geometry())
            self.utility_menu_animation.setEndValue(closed_rect)
            if hasattr(self, "utility_menu_opacity_animation") and self.utility_menu_opacity_animation is not None:
                current_opacity = self.utility_menu_opacity_effect.opacity() if hasattr(self, "utility_menu_opacity_effect") else 1.0
                self.utility_menu_opacity_animation.setStartValue(current_opacity)
                self.utility_menu_opacity_animation.setEndValue(0.0)
                self.utility_menu_opacity_animation.start()
        self.utility_menu_animation.start()

    def _utility_menu_target_height(self):
        return 658 if self._is_admin_user() else 590

    def _close_utility_menu(self):
        if not getattr(self, "utility_menu_open", False):
            return
        self.utility_menu_open = False
        if hasattr(self, "utility_menu_button") and self.utility_menu_button is not None:
            self.utility_menu_button.setToolTip("Open utility menu")
        if not hasattr(self, "utility_menu_panel") or self.utility_menu_panel is None:
            return
        if not hasattr(self, "utility_menu_animation") or self.utility_menu_animation is None:
            self.utility_menu_panel.hide()
            return
        panel_width = self.utility_menu_panel.width() or 266
        panel_height = self._utility_menu_target_height()
        self.utility_menu_panel.setFixedHeight(panel_height)
        closed_rect = QRect(-(panel_width + 14), 12, panel_width, panel_height)
        self.utility_menu_animation.stop()
        self.utility_menu_animation.setDuration(430)
        self.utility_menu_animation.setEasingCurve(QEasingCurve.InOutCubic)
        if hasattr(self, "utility_menu_opacity_animation") and self.utility_menu_opacity_animation is not None:
            self.utility_menu_opacity_animation.stop()
            self.utility_menu_opacity_animation.setDuration(360)
            self.utility_menu_opacity_animation.setEasingCurve(QEasingCurve.OutCubic)
            current_opacity = self.utility_menu_opacity_effect.opacity() if hasattr(self, "utility_menu_opacity_effect") else 1.0
            self.utility_menu_opacity_animation.setStartValue(current_opacity)
            self.utility_menu_opacity_animation.setEndValue(0.0)
            self.utility_menu_opacity_animation.start()
        self.utility_menu_animation.setStartValue(self.utility_menu_panel.geometry())
        self.utility_menu_animation.setEndValue(closed_rect)
        self.utility_menu_animation.start()

    def _handle_utility_menu_animation_finished(self):
        if hasattr(self, "utility_menu_panel") and self.utility_menu_panel is not None:
            if not self.utility_menu_open:
                self.utility_menu_panel.hide()
                if hasattr(self, "utility_menu_opacity_effect") and self.utility_menu_opacity_effect is not None:
                    self.utility_menu_opacity_effect.setOpacity(0.0)

    def _setup_info_label_animation(self, label):
        effect = QGraphicsOpacityEffect(label)
        effect.setOpacity(0.0)
        label.setGraphicsEffect(effect)
        label._info_opacity_effect = effect
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(180)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        label._info_fade_animation = animation
        label._info_hide_callback = None

    def _fade_in_info_label(self, label):
        animation = getattr(label, "_info_fade_animation", None)
        effect = getattr(label, "_info_opacity_effect", None)
        if animation is None or effect is None:
            label.show()
            return
        animation.stop()
        hide_callback = getattr(label, "_info_hide_callback", None)
        if hide_callback is not None:
            try:
                animation.finished.disconnect(hide_callback)
            except Exception:
                pass
            label._info_hide_callback = None
        start_opacity = effect.opacity()
        if start_opacity <= 0.0:
            start_opacity = 0.0
        label.show()
        animation.setStartValue(start_opacity)
        animation.setEndValue(1.0)
        animation.start()

    def _fade_out_info_label(self, label):
        animation = getattr(label, "_info_fade_animation", None)
        effect = getattr(label, "_info_opacity_effect", None)
        if animation is None or effect is None:
            label.hide()
            return
        animation.stop()
        start_opacity = effect.opacity()
        animation.setStartValue(start_opacity)
        animation.setEndValue(0.0)

        def hide_when_done():
            if effect.opacity() <= 0.01:
                label.hide()
                label.setText(" ")
            label._info_hide_callback = None

        old_callback = getattr(label, "_info_hide_callback", None)
        if old_callback is not None:
            try:
                animation.finished.disconnect(old_callback)
            except Exception:
                pass

        label._info_hide_callback = hide_when_done
        animation.finished.connect(hide_when_done)
        animation.start()

    def _update_setting_checkbox_cursor(self, checkbox, event) -> None:
        if checkbox is None:
            return

        hit_width = 15 + 10 + checkbox.fontMetrics().horizontalAdvance(checkbox.text()) + 12
        if event is not None:
            if hasattr(event, "position"):
                x_pos = event.position().x()
            elif hasattr(event, "pos"):
                x_pos = event.pos().x()
            else:
                x_pos = None
        else:
            x_pos = None

        use_hand = x_pos is None or x_pos <= hit_width
        checkbox.setCursor(Qt.PointingHandCursor if use_hand else Qt.ArrowCursor)

    def _is_dark_theme_active(self):
        return bool(
            getattr(self, "dark_mode", False)
            or (
                getattr(self, "theme_checkbox", None) is not None
                and self.theme_checkbox.isChecked()
            )
        )

    def _dark_dialog_override_stylesheet(self):
        return (
            "QDialog { background: #0f1a22; color: #e7f3f8; }"
            "QLabel { color: #d7e9f0; font-size: 13px; }"
            "QLabel[resultMessage=\"true\"], QLabel[accountValue=\"true\"] { "
            "background: #17303b; border: 1px solid #355768; border-radius: 14px; "
            "padding: 10px 12px; color: #e7f3f8; font-weight: 700; }"
            "QLabel[securityMessage=\"error\"] { color: #e09090; font-size: 11px; font-weight: 600; padding-left: 4px; }"
            "QLabel[securityMessage=\"success\"] { color: #90c090; font-size: 11px; font-weight: 600; padding-left: 4px; }"
            "QLabel[securityMessage=\"neutral\"] { color: #b5ccd7; font-size: 11px; font-weight: 600; padding-left: 4px; }"
            "QFrame[helpCard=\"true\"], QFrame[topicCard=\"true\"], QFrame[aboutCard=\"true\"] { "
            "background: #132630; border: 1px solid #355768; border-radius: 18px; }"
            "QFrame#resetItemFrame { background: #132630; border: 1px solid #355768; border-radius: 14px; }"
            "QWidget#aboutScrollContent, QWidget#resetScrollContent, QWidget#resetTextContainer { background: #0f1a22; }"
            "QLabel[aboutTitle=\"true\"] { color: #eef8fc; font-size: 24px; font-weight: 800; background: transparent; }"
            "QLabel[aboutSub=\"true\"], QLabel[topicSummary=\"true\"] { color: #b5ccd7; background: transparent; }"
            "QLabel[sectionTitle=\"true\"] { color: #eef8fc; font-size: 14px; font-weight: 700; background: transparent; }"
            "QLabel[sectionDescription=\"true\"] { color: #b5ccd7; font-size: 12px; background: transparent; }"
            "QLabel[defaultBadge=\"true\"] { "
            "background: #17303b; border: 1px solid #42697c; border-radius: 10px; "
            "color: #d8eef6; font-size: 11px; font-weight: 800; padding: 4px 8px; }"
            "QLabel[aboutBadge=\"true\"] { "
            "background: #17303b; border: 1px solid #42697c; border-radius: 12px; "
            "padding: 8px 10px; font-size: 12px; font-weight: 700; color: #d8eef6; }"
            "QListWidget, QTextEdit, QPlainTextEdit { "
            "background: #132630; border: 1px solid #355768; border-radius: 14px; "
            "color: #e7f3f8; padding: 6px; outline: 0; }"
            "QListWidget::item { color: #e7f3f8; padding: 8px 10px; border-radius: 10px; }"
            "QListWidget::item:hover { background: #214353; color: #ffffff; }"
            "QListWidget::item:selected { background: #24506a; color: #ffffff; }"
            "QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { "
            "min-height: 38px; border-radius: 12px; border: 1px solid #3c6273; "
            "background: #16303d; color: #e7f3f8; padding: 6px 10px; }"
            "QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus { "
            "border-color: #5c8aa0; background: #1e3d4c; color: #ffffff; }"
            "QLineEdit[validationState=\"error\"] { border: 1px solid #e09090; background: #4a2a2a; }"
            "QLineEdit[validationState=\"success\"] { border: 1px solid #90c090; background: #2a4a2a; }"
            "QComboBox QAbstractItemView { "
            "background: #142833; color: #e7f3f8; border: 1px solid #3c6273; "
            "selection-background-color: #24506a; selection-color: #ffffff; }"
            "QCheckBox { color: #deedf4; font-size: 13px; font-weight: 600; spacing: 8px; }"
            "QPushButton { min-height: 38px; border-radius: 12px; border: 1px solid #3c6273; "
            "background: #183240; color: #eaf6fb; font-weight: 700; padding: 6px 12px; }"
            "QPushButton:hover { background: #214353; border-color: #5c8aa0; color: #ffffff; }"
            "QPushButton:pressed { background: #122733; border-color: #305465; }"
            "QPushButton[variant=\"danger\"], QPushButton[destructiveAction=\"true\"] { "
            "background: #4a2a2a; border-color: #6a4a4a; color: #e09090; }"
            "QPushButton[textLink=\"true\"] { background: transparent; border: none; color: #87ceeb; }"
            "QPushButton[textLink=\"true\"]:hover { background: transparent; border: none; color: #add8e6; text-decoration: underline; }"
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea QWidget#qt_scrollarea_viewport { background: #0f1a22; }"
            "QScrollArea > QWidget { background: #0f1a22; }"
            "QScrollBar:vertical { background: #142833; width: 12px; margin: 8px 2px 8px 0; border-radius: 6px; }"
            "QScrollBar::handle:vertical { background: #42697c; border-radius: 6px; min-height: 30px; }"
            "QToolTip { background: #17303b; color: #d8eaf2; border: 1px solid #42697c; border-radius: 12px; }"
        )

    def _apply_dark_dialog_overrides(self, dialog, force=False):
        if not self._is_dark_theme_active():
            return
        if not force and dialog.property("darkDialogStyled") == "true":
            return

        dialog.setProperty("darkDialogStyled", "true")
        dialog.setAttribute(Qt.WA_StyledBackground, True)
        dialog.setAutoFillBackground(True)
        palette = dialog.palette()
        palette.setColor(QPalette.Window, QColor("#0f1a22"))
        palette.setColor(QPalette.Base, QColor("#132630"))
        palette.setColor(QPalette.Text, QColor("#e7f3f8"))
        palette.setColor(QPalette.WindowText, QColor("#e7f3f8"))
        palette.setColor(QPalette.Button, QColor("#183240"))
        palette.setColor(QPalette.ButtonText, QColor("#eaf6fb"))
        dialog.setPalette(palette)

        existing_style = dialog.styleSheet() or ""
        dialog.setStyleSheet(existing_style + self._dark_dialog_override_stylesheet())

        for label in dialog.findChildren(QLabel):
            if label.property("securityMessage") in {"error", "success", "neutral"}:
                continue
            current_style = label.styleSheet() or ""
            if label.property("accountValue") == "true" or label.property("resultMessage") == "true":
                label.setStyleSheet(current_style + " color: #e7f3f8;")
            else:
                label.setStyleSheet(current_style + " color: #e7f3f8; background: transparent;")

        for button in dialog.findChildren(QPushButton):
            if button.property("toolsStyleOverride") == "true":
                continue
            self._style_tools_button(button)

        for list_widget in dialog.findChildren(QListWidget):
            list_widget.setStyleSheet(
                "QListWidget { background: #132630; border: 1px solid #355768; border-radius: 14px; "
                "padding: 6px; color: #e7f3f8; outline: 0; }"
                "QListWidget::item { padding: 8px 10px; border-radius: 10px; color: #e7f3f8; }"
                "QListWidget::item:hover { background: #214353; color: #ffffff; }"
                "QListWidget::item:selected { background: #24506a; color: #ffffff; }"
            )

        for editor in [*dialog.findChildren(QTextEdit), *dialog.findChildren(QPlainTextEdit)]:
            editor.setStyleSheet(
                "background: #132630; border: 1px solid #355768; border-radius: 14px; "
                "color: #e7f3f8; padding: 6px;"
            )

        for scroll_area in dialog.findChildren(QScrollArea):
            scroll_area.setStyleSheet(
                "QScrollArea { background: transparent; border: none; }"
                "QScrollArea QWidget#qt_scrollarea_viewport { background: #0f1a22; }"
            )
            if scroll_area.viewport() is not None:
                scroll_area.viewport().setAutoFillBackground(True)
                viewport_palette = scroll_area.viewport().palette()
                viewport_palette.setColor(QPalette.Window, QColor("#0f1a22"))
                viewport_palette.setColor(QPalette.Base, QColor("#0f1a22"))
                scroll_area.viewport().setPalette(viewport_palette)

    def _reveal_prepared_dialog(self, dialog):
        if dialog.property("dialogOpeningHidden") != "true":
            return

        if self._is_dark_theme_active():
            self._apply_dark_dialog_overrides(dialog)
            dialog.setProperty("darkOpeningHidden", "false")
        dialog.setProperty("dialogOpeningHidden", "false")
        animation = QPropertyAnimation(dialog, b"windowOpacity", dialog)
        animation.setDuration(210)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.finished.connect(lambda: dialog.setWindowOpacity(1.0))
        dialog._dark_open_animation = animation
        animation.start()

    def _prepare_simple_dark_dialog(self, dialog):
        if not self._is_dark_theme_active():
            return

        dialog.setStyleSheet(self._dark_dialog_override_stylesheet())
        dialog.setProperty("darkDialogStyled", "false")
        self._apply_dark_dialog_overrides(dialog, force=True)

    def _tool_combo_stylesheet(self, object_name):
        if self._is_dark_theme_active():
            return (
                f"QComboBox#{object_name} {{"
                "border: 1px solid #42697c;"
                "background: #16303d;"
                "color: #e7f3f8;"
                "border-radius: 12px;"
                "padding: 8px 12px;"
                "font-size: 13px;"
                "font-weight: 600;"
                "}"
                f"QComboBox#{object_name}:hover {{"
                "border-color: #5c8aa0;"
                "background: #214353;"
                "color: #ffffff;"
                "}"
                f"QComboBox#{object_name} QAbstractItemView {{"
                "background: #132630;"
                "border: 1px solid #42697c;"
                "selection-background-color: #24506a;"
                "selection-color: #ffffff;"
                "color: #e7f3f8;"
                "padding: 4px;"
                "outline: 0;"
                "}"
                f"QComboBox#{object_name} QAbstractItemView::item {{ padding: 8px 10px; border-radius: 8px; }}"
                f"QComboBox#{object_name} QAbstractItemView::item:hover {{ background: #214353; color: #ffffff; }}"
                f"QComboBox#{object_name} QAbstractItemView::item:selected {{ background: #24506a; color: #ffffff; }}"
            )
        return (
            f"QComboBox#{object_name} {{"
            "border: 1px solid #cfdde5;"
            "background: #fbfdfe;"
            "color: #173543;"
            "border-radius: 12px;"
            "padding: 8px 12px;"
            "font-size: 13px;"
            "font-weight: 600;"
            "}"
            f"QComboBox#{object_name}:hover {{ border-color: #4c8ea4; background: #cfeaf4; color: #103647; }}"
            f"QComboBox#{object_name} QAbstractItemView {{"
            "background: #ffffff;"
            "border: 1px solid #cfdde5;"
            "selection-background-color: #bddfe9;"
            "selection-color: #103647;"
            "padding: 4px;"
            "outline: 0;"
            "}"
            f"QComboBox#{object_name} QAbstractItemView::item {{ padding: 8px 10px; border-radius: 8px; }}"
            f"QComboBox#{object_name} QAbstractItemView::item:hover {{ background: #cfeaf4; color: #103647; }}"
            f"QComboBox#{object_name} QAbstractItemView::item:selected {{ background: #bddfe9; color: #103647; }}"
        )

    def _tool_list_stylesheet(self):
        if self._is_dark_theme_active():
            return (
                "QListWidget { background: #132630; border: 1px solid #355768; border-radius: 14px; padding: 6px; outline: 0; }"
                "QListWidget::item { background: transparent; border: none; margin: 0px; padding: 0px; color: #e7f3f8; }"
                "QListWidget::item:hover { background: transparent; border: none; }"
                "QListWidget::item:selected { background: transparent; border: none; }"
                "QListWidget::item:focus { outline: none; }"
            )
        return (
            "QListWidget { background: #ffffff; border: 1px solid #d7e2e9; border-radius: 14px; padding: 6px; outline: 0; }"
            "QListWidget::item { background: transparent; border: none; margin: 0px; padding: 0px; }"
            "QListWidget::item:hover { background: transparent; border: none; }"
            "QListWidget::item:selected { background: transparent; border: none; }"
            "QListWidget::item:focus { outline: none; }"
        )

    def _beep_style_list_stylesheet(self):
        if self._is_dark_theme_active():
            return (
                "QListWidget { background: #132630; border: 1px solid #42697c; border-radius: 12px; padding: 6px; outline: 0; }"
                "QListWidget::item { padding: 10px 12px; border-radius: 8px; color: #e7f3f8; font-size: 13px; font-weight: 600; }"
                "QListWidget::item:hover { background: #214353; color: #ffffff; }"
                "QListWidget::item:selected { background: #24506a; color: #ffffff; }"
            )
        return (
            "QListWidget { background: #ffffff; border: 1px solid #cfdde5; border-radius: 12px; padding: 6px; outline: 0; }"
            "QListWidget::item { padding: 10px 12px; border-radius: 8px; color: #173543; font-size: 13px; font-weight: 600; }"
            "QListWidget::item:hover { background: #cfeaf4; color: #103647; }"
            "QListWidget::item:selected { background: #bddfe9; color: #103647; }"
        )

    def _tool_text_button_stylesheet(self, clickable=True):
        if self._is_dark_theme_active():
            hover_bg = "rgba(66,105,124,0.42)" if clickable else "transparent"
            press_bg = "rgba(66,105,124,0.58)" if clickable else "transparent"
            return (
                "QPushButton { background: transparent; border: none; outline: none; border-radius: 8px; "
                "padding: 4px 10px; text-align: left; color: #eef8fc; font-size: 12px; font-weight: 600; }"
                f"QPushButton:hover {{ background: {hover_bg}; color: #ffffff; }}"
                f"QPushButton:pressed {{ background: {press_bg}; color: #ffffff; }}"
            )
        return (
            "QPushButton { background: transparent; border: none; outline: none; border-radius: 8px; "
            "padding: 4px 10px; text-align: left; color: #173543; font-size: 12px; font-weight: 600; }"
            "QPushButton:hover { background: rgba(205,229,240,0.92); }"
            "QPushButton:pressed { background: rgba(191,219,232,0.92); }"
        )

    def _tool_more_button_stylesheet(self):
        if self._is_dark_theme_active():
            return (
                "QToolButton { background: transparent; border: none; border-radius: 12px; color: #d8eef6; "
                "font-size: 18px; font-weight: 700; padding-bottom: 3px; }"
                "QToolButton:hover { background: rgba(66,105,124,0.42); color: #ffffff; }"
                "QToolButton:pressed { background: rgba(66,105,124,0.58); color: #ffffff; }"
            )
        return (
            "QToolButton { background: transparent; border: none; border-radius: 12px; color: #1f5569; "
            "font-size: 18px; font-weight: 700; padding-bottom: 3px; }"
            "QToolButton:hover { background: rgba(205,229,240,0.98); }"
            "QToolButton:pressed { background: rgba(191,219,232,0.98); }"
        )

    def eventFilter(self, watched, event):
        if event.type() in {QEvent.MouseButtonPress, QEvent.MouseMove, QEvent.KeyPress}:
            self.last_activity_at = time.monotonic()

        if event.type() == QEvent.Show and isinstance(watched, QDialog):
            if watched.property("dialogOpeningHidden") == "true":
                QTimer.singleShot(20, lambda dialog=watched: self._reveal_prepared_dialog(dialog))
            else:
                QTimer.singleShot(0, lambda dialog=watched: self._apply_dark_dialog_overrides(dialog, force=True))

        if watched in {
            getattr(self, "auto_focus_checkbox", None),
            getattr(self, "gesture_checkbox", None),
            getattr(self, "voice_checkbox", None),
            getattr(self, "theme_checkbox", None),
            getattr(self, "practice_mode_checkbox", None),
        }:
            if event.type() in {QEvent.Enter, QEvent.MouseMove}:
                self._update_setting_checkbox_cursor(watched, event)
            elif event.type() == QEvent.Leave:
                watched.setCursor(Qt.ArrowCursor)

        if hasattr(watched, "property"):
            help_key = watched.property("inlineHelpKey")
            if help_key:
                if event.type() == QEvent.Enter:
                    self._schedule_sidebar_info(help_key, watched)
                elif event.type() == QEvent.Leave:
                    self._clear_sidebar_info()

        if watched in {
            getattr(self, "camera_footer_label", None),
            getattr(self, "voice_footer_label", None),
            getattr(self, "voice_indicator_label", None),
            getattr(self, "user_footer_label", None),
        }:
            if event.type() == QEvent.Enter:
                footer_key = watched.property("footerKey")
                self._schedule_footer_info(footer_key, watched)
            elif event.type() == QEvent.Leave:
                self._clear_footer_info()

        if (
            getattr(self, "utility_menu_open", False)
            and not getattr(self, "utility_action_active", False)
            and event.type() == QEvent.KeyPress
            and hasattr(event, "key")
            and event.key() == Qt.Key_Escape
        ):
            self._close_utility_menu()
            return True

        if (
            getattr(self, "utility_menu_open", False)
            and not getattr(self, "utility_action_active", False)
            and event.type() == QEvent.MouseButtonPress
            and hasattr(event, "globalPosition")
        ):
            global_pos = event.globalPosition().toPoint()
            panel_rect = self.utility_menu_panel.rect()
            button_rect = self.utility_menu_button.rect()
            panel_global = self.utility_menu_panel.mapToGlobal(panel_rect.topLeft())
            button_global = self.utility_menu_button.mapToGlobal(button_rect.topLeft())
            panel_hit = QRect(panel_global, panel_rect.size()).contains(global_pos)
            button_hit = QRect(button_global, button_rect.size()).contains(global_pos)
            if not panel_hit and not button_hit:
                self._close_utility_menu()
        return super().eventFilter(watched, event)

    def _update_keyboard_shortcuts(self):
        shortcut_specs = [
            ("_shortcut_start_camera", "Ctrl+Shift+S", self.start_camera),
            ("_shortcut_stop_camera", "Ctrl+Shift+X", self.stop_camera),
            ("_shortcut_toggle_voice", "Ctrl+Shift+V", self._toggle_voice_shortcut),
            ("_shortcut_toggle_gesture", "Ctrl+Shift+G", self._toggle_gesture_shortcut),
            ("_shortcut_toggle_practice", "Ctrl+Shift+P", self._toggle_practice_shortcut),
            ("_shortcut_toggle_dark_mode", "Ctrl+Shift+D", self._toggle_dark_mode_shortcut),
            ("_shortcut_toggle_auto_focus", "Ctrl+Shift+A", self._toggle_auto_focus_shortcut),
            ("_shortcut_toggle_sound_feedback", "Ctrl+Shift+B", self._toggle_sound_feedback_shortcut),
            ("_shortcut_open_presentation", "Ctrl+Shift+O", self.open_presentation_file),
            ("_shortcut_open_voice_feedback", "Ctrl+Shift+F", self.show_voice_feedback_dialog),
            ("_shortcut_open_gesture_profiles", "Ctrl+Shift+J", self.show_gesture_profiles_dialog),
            ("_shortcut_open_keyboard_shortcuts", "Ctrl+Shift+K", self.show_keyboard_shortcuts_dialog),
            ("_shortcut_open_microphone_settings", "Ctrl+Shift+M", self.open_voice_settings_dialog),
            ("_shortcut_open_quick_help", "Ctrl+Shift+H", self.show_quick_help),
            ("_shortcut_open_presentation_timer", "Ctrl+Shift+T", self.show_presentation_timer_dialog),
            ("_shortcut_open_utility_menu", "Ctrl+Shift+U", self._toggle_utility_menu),
            ("_shortcut_open_saved_accounts", "Ctrl+Shift+W", self._open_saved_accounts_shortcut),
            ("_shortcut_open_lock_security", "Ctrl+Shift+L", self._open_lock_security_shortcut),
            ("_shortcut_open_manage_users", "Ctrl+Shift+E", self._open_manage_users_shortcut),
            ("_shortcut_open_reset_settings", "Ctrl+Shift+R", self._open_reset_settings_shortcut),
            ("_shortcut_open_about", "Ctrl+Shift+I", self._open_about_shortcut),
            ("_shortcut_minimize_app", "Ctrl+Shift+N", self._minimize_app_shortcut),
            ("_shortcut_close_app", "Ctrl+Shift+Q", self._close_app_shortcut),
        ]

        for attr_name, key_sequence, handler in shortcut_specs:
            shortcut = getattr(self, attr_name, None)
            if shortcut is None:
                shortcut = QShortcut(QKeySequence(key_sequence), self)
                shortcut.activated.connect(handler)
                setattr(self, attr_name, shortcut)
            shortcut.setEnabled(self.keyboard_shortcuts_enabled)

    def _toggle_voice_shortcut(self):
        target_state = not self.voice_checkbox.isChecked()
        self.voice_checkbox.setChecked(target_state)

    def _toggle_gesture_shortcut(self):
        target_state = not self.gesture_checkbox.isChecked()
        self.gesture_checkbox.setChecked(target_state)

    def _toggle_practice_shortcut(self):
        target_state = not self.practice_mode_checkbox.isChecked()
        self.practice_mode_checkbox.setChecked(target_state)

    def _toggle_dark_mode_shortcut(self):
        target_state = not self.theme_checkbox.isChecked()
        self.theme_checkbox.setChecked(target_state)

    def _toggle_auto_focus_shortcut(self):
        target_state = not self.auto_focus_checkbox.isChecked()
        self.auto_focus_checkbox.setChecked(target_state)

    def _toggle_sound_feedback_shortcut(self):
        target_state = not self.sound_feedback_checkbox.isChecked()
        self.sound_feedback_checkbox.setChecked(target_state)

    def _open_saved_accounts_shortcut(self):
        self._open_utility_action(self.logout_button, self.show_account_switcher)

    def _open_lock_security_shortcut(self):
        self._open_utility_action(self.lock_security_button, self.show_lock_security)

    def _open_manage_users_shortcut(self):
        if hasattr(self, "_is_admin_user") and not self._is_admin_user():
            self._set_badge(self.status_value, "Manage users is admin only", "warning")
            return
        self._open_utility_action(self.manage_users_button, self.show_manage_users)

    def _open_reset_settings_shortcut(self):
        self._open_utility_action(self.reset_settings_button, self.show_reset_settings_dialog)

    def _open_about_shortcut(self):
        self._open_utility_action(self.about_button, self.show_about_dialog)

    def _minimize_app_shortcut(self):
        self.showMinimized()

    def _close_app_shortcut(self):
        self.close()

    def _check_auto_lock(self):
        return

    def _schedule_sidebar_info(self, help_key, anchor_widget):
        self._pending_sidebar_help = (help_key, anchor_widget)
        self.sidebar_info_delay_timer.start()

    def _show_pending_sidebar_info(self):
        if not self._pending_sidebar_help:
            return
        help_key, anchor_widget = self._pending_sidebar_help
        self._show_sidebar_info(help_key, anchor_widget)

    def _show_sidebar_info(self, help_key, anchor_widget):
        message = self._get_sidebar_info_message(help_key)
        if message:
            tooltip_pos = anchor_widget.mapToGlobal(anchor_widget.rect().bottomLeft())
            QToolTip.showText(tooltip_pos, f"\u24D8 {message}", anchor_widget)
        else:
            self._clear_sidebar_info()

    def _clear_sidebar_info(self):
        self.sidebar_info_delay_timer.stop()
        self._pending_sidebar_help = None
        QToolTip.hideText()

    def _get_sidebar_info_message(self, help_key):
        if help_key == "status_mode":
            return "Shows whether the app is in Control Mode or Jump Mode."
        if help_key == "status_tracking":
            return "Shows the most recent activity or change inside the app."
        if help_key == "status_gesture":
            return "Shows the current detected hand gesture or jump count."
        if help_key == "status_action":
            return "Shows the last action triggered by gesture or voice."
        if help_key == "status_voice":
            return "Shows the most recent voice command activity."
        if help_key == "start_camera":
            return "Starts the camera feed and begins hand tracking."
        if help_key == "stop_camera":
            return "Stops the camera feed and pauses gesture tracking."
        if help_key == "camera_select":
            return "Choose which camera device VisionSlide should use."
        if help_key == "control_hold":
            return "Sets how many steady frames are needed before a control gesture triggers."
        if help_key == "jump_hold":
            return "Sets how long a jump count must be held before it triggers."
        if help_key == "auto_focus":
            return "Keeps the presentation window focused before sending commands."
        if help_key == "gesture_enabled":
            return "Turns gesture recognition on or off."
        if help_key == "voice_enabled":
            return "Turns voice commands on or off."
        if help_key == "sound_feedback_enabled":
            return "Turns voice feedback beeps on or off while keeping the selected feedback style available."
        if help_key == "dark_mode":
            return "Switches the app between the light and dark visual themes."
        if help_key == "voice_device":
            return "Choose which microphone VisionSlide should listen to."
        if help_key == "total_slides":
            return "Sets the maximum slide number available for jump actions."
        if help_key == "lock_security":
            return "Open account security settings to update username, email, or password."
        if help_key == "manage_users":
            return "Admin-only tool to remove saved sign-ins or permanently delete user accounts."
        if help_key == "reset_settings":
            return "Restore app settings back to their default values."
        if help_key == "open_presentation":
            return "Choose and open a presentation file such as PowerPoint or PDF in its default app."
        if help_key == "recent_files":
            return "Open, remove, or clear recently launched presentation files."
        if help_key == "practice_mode":
            return "Test gestures and voice commands without sending real slide controls."
        if help_key == "command_history":
            return "Review the latest recognized gesture and voice actions."
        if help_key == "custom_voice_commands":
            return "Map alternate spoken phrases for supported slide actions."
        if help_key == "custom_gesture_actions":
            return "Remap the existing camera-detected gestures to different slide actions."
        if help_key == "gesture_profiles":
            return "Switch between Normal, Steady, and Fast gesture sensitivity profiles."
        if help_key == "voice_feedback_choice":
            return "Choose when commands should beep and which short professional beep style should be used."
        if help_key == "presentation_timer":
            return "Track elapsed time during a presentation or demo session."
        if help_key == "user_preferences":
            return "User preferences are saved automatically in the background for each signed-in account."
        if help_key == "admin_activity_log":
            return "Review logged admin actions such as password resets and user changes."
        if help_key == "keyboard_shortcuts":
            return "Enable shortcut keys and view the available keyboard fallback actions."
        if help_key == "quick_help":
            return "Open the current guide for setup, settings, tools, gestures, voice commands, and security."
        if help_key == "about_app":
            return "Open app information, feature highlights, and current account details."
        if help_key == "saved_accounts":
            return "Open the saved accounts list to switch or add another account."
        if help_key == "utility_menu":
            return "Open the sidebar utility menu for account and help actions."
        return ""

    def _schedule_footer_info(self, footer_key, anchor_widget):
        self._pending_footer_help = (footer_key, anchor_widget)
        self.footer_info_delay_timer.start()

    def _show_pending_footer_info(self):
        if not self._pending_footer_help:
            return
        footer_key, anchor_widget = self._pending_footer_help
        self._show_footer_info(footer_key, anchor_widget)
    def _show_footer_info(self, footer_key, anchor_widget):
        message = self._get_footer_info_message(footer_key)
        if message:
            tooltip_pos = anchor_widget.mapToGlobal(anchor_widget.rect().bottomLeft())
            QToolTip.showText(tooltip_pos, f"\u24D8 {message}", anchor_widget)
        else:
            self._clear_footer_info()

    def _clear_footer_info(self):
        self.footer_info_delay_timer.stop()
        self._pending_footer_help = None
        QToolTip.hideText()

    def _get_footer_info_message(self, footer_key):
        if footer_key == "camera":
            camera_text = getattr(self, "camera_state_badge", None).text().lower() if getattr(self, "camera_state_badge", None) is not None else ""
            if "stopped" in camera_text:
                return "Open the camera from controls to begin tracking."
            if "running" in camera_text:
                return "Camera is active and ready to track hand gestures."
            if "unavailable" in camera_text:
                return "Check the selected camera or reconnect the device."
            return "Camera status updates appear here while tracking."

        if footer_key == "voice":
            voice_text = self.voice_footer_label.text().lower()
            if "off" in voice_text:
                return "Enable voice control in settings to use spoken commands."
            if "listening" in voice_text:
                return "Voice control is listening for supported presentation commands."
            if "command received" in voice_text:
                return "A voice command was detected and processed."
            if "mic not found" in voice_text:
                return "Choose an available microphone in settings to use voice control."
            return "Voice command activity appears here."

        if footer_key == "voice_status":
            status_text = self.voice_indicator_label.text().lower()
            if "off" in status_text:
                return "Voice control is off until you enable it in settings."
            if "idle" in status_text:
                return "Voice status is idle until voice control is enabled and listening."
            if "listening" in status_text:
                return "The microphone is active and waiting for a command."
            if "command received" in status_text:
                return "The last spoken command was received successfully."
            if "mic not found" in status_text:
                return "No working microphone is selected for voice control."
            return "This shows the live microphone listening state."

        if footer_key == "user":
            return f"You are signed in as {self.current_user}. Use the menu to switch accounts."

        return ""

    def _set_camera_empty_state(self, title_text, detail_text):
        canvas_width = max(920, self.camera_label.width())
        canvas_height = max(640, self.camera_label.height())
        placeholder_pixmap = self._build_camera_placeholder_pixmap(
            canvas_width,
            canvas_height,
            title_text,
            detail_text,
        )
        self.camera_label.setText("")
        self.camera_label.setPixmap(placeholder_pixmap)

    def _apply_sidebar_surface_theme(self):
        if getattr(self, "dark_mode", False):
            sidebar_bg = "#0f1a22"
            heading_style = (
                "font-size: 12px;"
                "font-weight: 700;"
                "color: #d8eef6;"
                "background: #1a3441;"
                "border: 1px solid #42697c;"
                "border-radius: 10px;"
                "padding: 4px 10px;"
            )
        else:
            sidebar_bg = "#d7e6ed"
            heading_style = (
                "font-size: 12px;"
                "font-weight: 700;"
                "color: #1c5061;"
                "background: #eef7fb;"
                "border: 1px solid #c6dde8;"
                "border-radius: 10px;"
                "padding: 4px 10px;"
            )

        if getattr(self, "sidebar_widget", None) is not None:
            self.sidebar_widget.setStyleSheet(f"QWidget#sidebarWidget {{ background: {sidebar_bg}; }}")
        if getattr(self, "sidebar_scroll", None) is not None:
            self.sidebar_scroll.setStyleSheet(
                f"QScrollArea#sidebarScroll {{ border: none; background: {sidebar_bg}; }}"
                f"QScrollArea#sidebarScroll > QWidget {{ background: {sidebar_bg}; }}"
            )
        if getattr(self, "sidebar_container", None) is not None:
            self.sidebar_container.setStyleSheet(f"QWidget#sidebarContainer {{ background: {sidebar_bg}; }}")

        for heading_label in getattr(self, "status_heading_labels", []):
            heading_label.setStyleSheet(heading_style)

    def _apply_camera_preview_theme(self):
        if getattr(self, "dark_mode", False):
            self.camera_label.setStyleSheet(
                "border: 1px solid #355768; background-color: #132630; color: #d7e9f0; "
                "font-size: 16px; border-radius: 24px; padding: 12px;"
            )
        else:
            self.camera_label.setStyleSheet(
                "border: 1px solid #b9d0da; background-color: #dceaf0; color: #1e4a5b; "
                "font-size: 16px; border-radius: 24px; padding: 12px;"
            )

    def _apply_mode_value_theme(self):
        if getattr(self, "dark_mode", False):
            self.mode_value.setStyleSheet(
                """
                QComboBox {
                    min-height: 39px;
                    max-height: 39px;
                    border-radius: 11px;
                    border: 1px solid #42697c;
                    background: #1a3441;
                    color: #eef8fc;
                    font-size: 13px;
                    font-weight: 600;
                    padding: 0 12px 0 12px;
                }
                QComboBox:hover {
                    border-color: #5e8ea4;
                    background: #224454;
                    color: #ffffff;
                }
                QComboBox::drop-down {
                    width: 0px;
                    border: none;
                    background: transparent;
                    subcontrol-origin: padding;
                    subcontrol-position: top right;
                }
                QComboBox::down-arrow {
                    image: none;
                    width: 0px;
                    height: 0px;
                    margin: 0px;
                }
                QComboBox::indicator {
                    width: 0px;
                    height: 0px;
                }
                QComboBox QAbstractItemView {
                    border: 1px solid #42697c;
                    border-radius: 10px;
                    outline: 0;
                    background: #142833;
                    color: #e7f3f8;
                    selection-background-color: #24506a;
                    selection-color: #ffffff;
                    padding: 4px;
                }
                QComboBox QAbstractItemView::item {
                    min-height: 28px;
                    padding: 6px 10px;
                    border-radius: 8px;
                }
                QComboBox QAbstractItemView::item:hover {
                    background: #24506a;
                    color: #ffffff;
                }
                QComboBox QAbstractItemView::item:selected {
                    background: #24506a;
                    color: #ffffff;
                }
                """
            )
        else:
            self.mode_value.setStyleSheet(
                """
                QComboBox {
                    min-height: 39px;
                    max-height: 39px;
                    border-radius: 11px;
                    border: 1px solid #cae0ee;
                    background: #edf6fb;
                    color: #17445c;
                    font-size: 13px;
                    font-weight: 600;
                    padding: 0 12px 0 12px;
                }
                QComboBox:hover {
                    border-color: #5f9db3;
                    background: #dceff8;
                    color: #143b4f;
                }
                QComboBox::drop-down {
                    width: 0px;
                    border: none;
                    background: transparent;
                    subcontrol-origin: padding;
                    subcontrol-position: top right;
                }
                QComboBox::down-arrow {
                    image: none;
                    width: 0px;
                    height: 0px;
                    margin: 0px;
                }
                QComboBox::indicator {
                    width: 0px;
                    height: 0px;
                }
                QComboBox QAbstractItemView {
                    border: 1px solid #cae0ee;
                    border-radius: 10px;
                    outline: 0;
                    background: #ffffff;
                    color: #17445c;
                    selection-background-color: #dceff8;
                    selection-color: #143b4f;
                    padding: 4px;
                }
                QComboBox QAbstractItemView::item {
                    min-height: 28px;
                    padding: 6px 10px;
                    border-radius: 8px;
                }
                QComboBox QAbstractItemView::item:hover {
                    background: #dceff8;
                    color: #143b4f;
                }
                QComboBox QAbstractItemView::item:selected {
                    background: #cfe7f1;
                    color: #143b4f;
                }
                """
            )

    def _build_camera_placeholder_pixmap(self, width, height, title_text, detail_text):
        pixmap = QPixmap(width, height)
        if getattr(self, "dark_mode", False):
            pixmap.fill(QColor("#132630"))
        else:
            pixmap.fill(QColor("#dceaf0"))

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        mode_text = "Control Mode" if self.current_mode == AppState.CONTROL_MODE else "Jump Mode"
        gesture_text = "Gesture Enabled" if self.gesture_checkbox.isChecked() else "Gesture Disabled"
        voice_text = "Voice Enabled" if self.voice_checkbox.isChecked() else "Voice Disabled"
        hold_text = (
            f"Control Hold: {self.control_hold_frames}"
            if self.current_mode == AppState.CONTROL_MODE
            else f"Jump Hold: {self.jump_hold_seconds:.1f}s"
        )

        # Soft circular backdrop
        painter.setPen(Qt.NoPen)
        icon_size = 140
        icon_x = (width - icon_size) // 2
        icon_y = max(84, (height - icon_size) // 2 - 88)
        painter.setBrush(QColor(255, 255, 255, 80))
        painter.drawEllipse(icon_x - 18, icon_y - 18, icon_size + 36, icon_size + 36)

        # Camera body
        body_rect_x = icon_x + 18
        body_rect_y = icon_y + 42
        body_rect_w = 96
        body_rect_h = 56
        painter.setBrush(QColor("#2f5e72"))
        painter.drawRoundedRect(body_rect_x, body_rect_y, body_rect_w, body_rect_h, 15, 15)

        # Camera top bump
        painter.setBrush(QColor("#2f5e72"))
        bump_x = icon_x + 42
        bump_y = icon_y + 22
        bump_w = 52
        bump_h = 24
        painter.drawRoundedRect(bump_x, bump_y, bump_w, bump_h, 12, 12)

        # Lens outer
        lens_center_x = icon_x + 66
        lens_center_y = icon_y + 70
        lens_radius = 19
        painter.setBrush(QColor("#1f4351"))
        painter.drawEllipse(
            lens_center_x - lens_radius,
            lens_center_y - lens_radius,
            lens_radius * 2,
            lens_radius * 2,
        )

        # Lens inner
        inner_radius = 10
        painter.setBrush(QColor("#79AEC3"))
        painter.drawEllipse(
            lens_center_x - inner_radius,
            lens_center_y - inner_radius,
            inner_radius * 2,
            inner_radius * 2,
        )

        # Small viewfinder side
        painter.setBrush(QColor("#2A4654"))
        side_x = icon_x + 116
        side_y = icon_y + 54
        side_w = 16
        side_h = 28
        painter.drawRoundedRect(side_x, side_y, side_w, side_h, 8, 8)

        # Red blocked circle
        blocked_pen = QPen(QColor("#E14B46"))
        blocked_pen.setWidth(10)
        blocked_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(blocked_pen)
        blocked_circle_size = 42
        blocked_circle_x = lens_center_x - (blocked_circle_size // 2)
        blocked_circle_y = lens_center_y - (blocked_circle_size // 2)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(blocked_circle_x, blocked_circle_y, blocked_circle_size, blocked_circle_size)
        painter.drawLine(
            blocked_circle_x + 8,
            blocked_circle_y + blocked_circle_size - 8,
            blocked_circle_x + blocked_circle_size - 8,
            blocked_circle_y + 8,
        )

        content_width = min(width - 56, 620)
        content_x = (width - content_width) // 2
        title_y = icon_y + icon_size + 40
        detail_rect = QRect(content_x, title_y + 18, content_width, 52)

        painter.setPen(QColor("#173543"))
        title_font = QFont("Segoe UI", 18, QFont.Bold)
        painter.setFont(title_font)
        painter.drawText(QRect(content_x, title_y - 8, content_width, 30), Qt.AlignCenter, title_text)

        painter.setPen(QColor("#55717d"))
        detail_font = QFont("Segoe UI", 10)
        painter.setFont(detail_font)
        painter.drawText(detail_rect, Qt.AlignCenter | Qt.TextWordWrap, detail_text)

        painter.end()
        return pixmap

    def _set_footer_state(self, camera_text=None, voice_text=None, mode_text=None):
        if voice_text is not None:
            self.voice_footer_label.setText(voice_text)
            self.voice_indicator_label.setText(voice_text)




    def set_control_mode(self):
        self.current_mode = AppState.CONTROL_MODE
        self._sync_mode_dropdown()
        self._set_recent_activity("Mode changed to Control", "info")
        self._set_badge(self.gesture_value, "None", "muted")
        self._set_badge(self.action_value, "None", "muted")
        self._set_badge(self.voice_value, "None", "muted")
        self.last_jump_count = None



    def set_jump_mode(self):
        self.current_mode = AppState.JUMP_MODE
        self._sync_mode_dropdown()
        self._set_recent_activity("Mode changed to Jump", "info")
        self._set_badge(self.gesture_value, "None", "muted")
        self._set_badge(self.action_value, "None", "muted")
        self._set_badge(self.voice_value, "None", "muted")
        self.last_jump_count = None


        # Save selected camera from dropdown and update camera manager
    def change_camera_index(self, index):
        camera_value = sanitize_camera_index(self.camera_index_input.currentData(), self.config.get("camera_index"))

        if camera_value is None:
            return

        self.config.set("camera_index", camera_value)
        self.camera_manager.camera_index = camera_value
        self._set_badge(self.status_value, f"Camera set to {self.camera_index_input.currentText()}", "info")
        # Runtime microphone auto-refresh is disabled for stability
    def auto_refresh_microphones(self):
        return



    # Change how many repeated frames are needed for stable control gestures
    def change_control_hold_frames(self, value):
        validated_value = sanitize_control_hold_frames(value, self.control_hold_frames)
        if validated_value != value:
            self.control_hold_input.setValue(validated_value)
            self._set_badge(self.status_value, "Invalid control hold value corrected", "warning")
            return

        self.config.set("control_hold_frames", validated_value)
        self.control_hold_frames = validated_value
        self.gesture_profile_name = "Custom"
        self.config.set("gesture_profile", self.gesture_profile_name)
        self._save_current_user_preferences()
        self._set_badge(self.status_value, f"Control hold set to {validated_value}", "info")

    # Change jump-mode hold time and save it
    def change_jump_hold_seconds(self, value):
        validated_value = sanitize_jump_hold_seconds(value, self.jump_hold_seconds)
        if validated_value != value:
            self.jump_hold_input.setValue(validated_value)
            self._set_badge(self.status_value, "Invalid jump hold value corrected", "warning")
            return

        self.config.set("jump_hold_seconds", validated_value)
        self.jump_hold_seconds = validated_value
        self.gesture_profile_name = "Custom"
        self.config.set("gesture_profile", self.gesture_profile_name)
        self._save_current_user_preferences()
        self._set_badge(self.status_value, f"Jump hold set to {validated_value:.1f}s", "info")

    # Save the total number of slides in the current presentation
    def change_total_slides(self, value):
        validated_value = sanitize_total_slides(value, self.config.get("total_slides"))
        if validated_value != value:
            self.total_slides_input.setValue(validated_value)
            self._set_badge(self.status_value, "Invalid total slides value corrected", "warning")
            return

        self.config.set("total_slides", validated_value)
        self._set_badge(self.status_value, f"Total slides set to {validated_value}", "info")

    # Enable or disable automatic presentation focusing
    def toggle_auto_focus(self, checked):
        self.config.set("auto_focus_presentation", checked)
        self.slide_controller.set_auto_focus_enabled(checked)
        self._save_current_user_preferences()
        self._set_badge(
            self.status_value,
            "Presentation focus enabled" if checked else "Presentation focus disabled",
            "info",
        )



     # Reset all settings back to default values
    def reset_settings(self):
        should_reset = self._show_confirmation_popup(
            "Reset Settings",
            "Are you sure you want to reset settings to default values?",
            confirm_text="Yes",
            cancel_text="No",
        )
        if not should_reset:
            return

        available_devices = [
            self.voice_device_input.itemText(index)
            for index in range(self.voice_device_input.count())
        ]
        default_voice_device = sanitize_voice_device_name(
            "Default System Microphone",
            allowed_devices=available_devices,
            default=available_devices[0] if available_devices else "Default System Microphone",
        )

        self.config.set("camera_index", 0)
        self.config.set("control_hold_frames", 3)
        self.config.set("jump_hold_seconds", 0.1)
        self.config.set("sound_enabled", True)
        self.config.set("auto_focus_presentation", True)
        self.config.set("gesture_enabled", True)
        self.config.set("voice_enabled", False)
        self.config.set("voice_device_name", default_voice_device)
        self.config.set("total_slides", 100)
        self.config.set("practice_mode", False)
        self.config.set("keyboard_shortcuts_enabled", True)
        self.config.set("voice_feedback_mode", "unknown_only")
        self.config.set("voice_feedback_beep_style", "standard")
        self.config.set("gesture_profile", "Normal")
        self.config.set("custom_voice_commands", {})
        self.config.set("custom_gesture_actions", {})

        camera_index = self.camera_index_input.findData(0)
        if camera_index >= 0:
            self.camera_index_input.setCurrentIndex(camera_index)

        self.control_hold_input.setValue(3)
        self.jump_hold_input.setValue(0.1)
        self.sound_feedback_checkbox.setChecked(True)
        self.auto_focus_checkbox.setChecked(True)
        self.gesture_checkbox.setChecked(True)
        self.voice_checkbox.setChecked(False)
        self._set_badge(self.voice_value, "None", "muted")
        self.total_slides_input.setValue(100)
        self.theme_checkbox.setChecked(False)
        self.practice_mode_enabled = False
        self.practice_mode_checkbox.setChecked(False)
        self.keyboard_shortcuts_enabled = True
        self.keyboard_shortcuts_checkbox.setChecked(True)
        self.voice_feedback_mode = "unknown_only"
        self.voice_feedback_beep_style = "standard"
        self.audio_feedback.set_beep_style(self.voice_feedback_beep_style)
        self.gesture_profile_name = "Normal"
        self.custom_voice_commands = {}
        self.custom_gesture_actions = {}
        self._refresh_voice_listener_commands()
        self._update_keyboard_shortcuts()


        voice_device_index = self.voice_device_input.findText(default_voice_device)
        if voice_device_index >= 0:
          self.voice_device_input.setCurrentIndex(voice_device_index)

        self.voice_listener.device_name = default_voice_device


        self.camera_manager.camera_index = 0
        self.control_hold_frames = 3
        self.jump_hold_seconds = 0.1
        self.audio_feedback.set_enabled(True)
        self.slide_controller.set_auto_focus_enabled(True)
        self.voice_listener.stop()
        self.toggle_theme(False)
        self.main_splitter.setSizes(self.default_splitter_sizes)
        self.new_username_input.clear()
        self.username_current_password_input.clear()
        self.new_email_input.clear()
        self.email_current_password_input.clear()
        self.email_otp_input.clear()
        self._reset_email_change_verification()
        self.security_current_password_input.clear()
        self.security_new_password_input.clear()
        self.security_confirm_password_input.clear()
        self._clear_security_messages()
        self._save_current_user_preferences()

        self._set_badge(self.status_value, "Settings reset to default", "info")
        self._show_security_result_popup(
            "Reset Settings",
            "Settings were reset successfully.",
            success=True,
        )

    def show_reset_settings_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Reset Settings")
        dialog.setMinimumSize(540, 620)
        dialog.resize(540, 620)
        dialog.setStyleSheet(
            "QDialog { background: #f7fbfd; }"
            "QLabel { color: #274652; font-size: 13px; }"
            "QPushButton { min-height: 36px; border-radius: 12px; border: 1px solid #ccd8e2; "
            "background: #ffffff; color: #173543; font-weight: 700; padding: 6px 12px; }"
            "QPushButton:hover { background: #cfe5ee; border-color: #3f7c8f; }"
            "QPushButton:pressed { background: #bddbe6; border-color: #346b7d; }"
            "QPushButton[variant=\"danger\"] { background: #fff2ef; border-color: #e5b6ad; color: #9d3f35; }"
            "QPushButton[variant=\"danger\"]:hover { background: #ffe6e0; border-color: #d48f84; }"
            "QFrame#resetItemFrame { background: #ffffff; border: 1px solid #d7e2e9; border-radius: 14px; }"
            "QLabel[sectionTitle=\"true\"] { font-size: 14px; font-weight: 700; color: #173543; }"
            "QLabel[sectionDescription=\"true\"] { color: #5a7380; font-size: 12px; }"
            "QLabel[defaultBadge=\"true\"] { background: #eef7fb; border: 1px solid #c9dde7; "
            "border-radius: 10px; color: #2c6477; font-size: 11px; font-weight: 800; padding: 4px 8px; }"
        )

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)
        dialog.setLayout(layout)

        title = QLabel("Reset Settings")
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #173543;")
        subtitle = QLabel("Reset one setting at a time, or restore the full app setup to its defaults.")
        subtitle.setStyleSheet("color: #5a7380;")
        subtitle.setWordWrap(True)

        scroll_area = QScrollArea()
        scroll_area.setObjectName("resetScrollArea")
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setFrameShape(QFrame.NoFrame)

        scroll_content = QWidget()
        scroll_content.setObjectName("resetScrollContent")
        scroll_content.setAttribute(Qt.WA_StyledBackground, True)
        scroll_layout = QVBoxLayout()
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(12)
        scroll_content.setLayout(scroll_layout)
        scroll_area.setWidget(scroll_content)

        def add_reset_item(label_text, default_text, description_text, callback):
            item_frame = QFrame()
            item_frame.setObjectName("resetItemFrame")
            item_layout = QHBoxLayout()
            item_layout.setContentsMargins(14, 12, 14, 12)
            item_layout.setSpacing(14)
            item_frame.setLayout(item_layout)

            text_container = QWidget()
            text_container.setObjectName("resetTextContainer")
            text_container.setAttribute(Qt.WA_StyledBackground, True)
            text_layout = QVBoxLayout()
            text_layout.setContentsMargins(0, 0, 0, 0)
            text_layout.setSpacing(4)
            text_container.setLayout(text_layout)

            item_title = QLabel(label_text)
            item_title.setProperty("sectionTitle", "true")
            default_badge = QLabel(f"{default_text} (Default)")
            default_badge.setProperty("defaultBadge", "true")
            item_description = QLabel(description_text)
            item_description.setProperty("sectionDescription", "true")
            item_description.setWordWrap(True)
            item_layout.addWidget(text_container, 1)
            title_row = QHBoxLayout()
            title_row.setContentsMargins(0, 0, 0, 0)
            title_row.setSpacing(8)
            title_row.addWidget(item_title)
            title_row.addWidget(default_badge, 0, Qt.AlignLeft)
            title_row.addStretch()
            text_layout.addLayout(title_row)
            text_layout.addWidget(item_description)

            reset_button = QPushButton("Reset")
            reset_button.clicked.connect(lambda checked=False, name=label_text, cb=callback: self._confirm_reset_setting(
                name,
                f"Reset '{name}' to its default value?",
                cb,
                f"{name} has been reset successfully.",
            ))
            item_layout.addWidget(reset_button, 0, Qt.AlignRight | Qt.AlignVCenter)
            scroll_layout.addWidget(item_frame)

        add_reset_item(
            "Camera Selection",
            "Camera 0",
            "Restore the selected camera choice back to the default camera.",
            self._reset_camera_setting,
        )
        add_reset_item(
            "Control Hold",
            "3",
            "Reset the number of frames needed for control gestures to the default value.",
            self._reset_control_hold_setting,
        )
        add_reset_item(
            "Jump Hold (s)",
            "0.1",
            "Restore the jump hold time to the default stability threshold.",
            self._reset_jump_hold_setting,
        )
        add_reset_item(
            "Auto Focus Presentation",
            "Enabled",
            "Return the auto focus presentation setting to its default state.",
            self._reset_auto_focus_setting,
        )
        add_reset_item(
            "Gesture Control Enabled",
            "Enabled",
            "Restore gesture recognition to its default enabled state.",
            self._reset_gesture_setting,
        )
        add_reset_item(
            "Voice Control Enabled",
            "Disabled",
            "Restore voice command enablement to the default disabled state.",
            self._reset_voice_setting,
        )
        add_reset_item(
            "Sound Feedback Enabled",
            "Enabled",
            "Restore feedback beeps to the default enabled state.",
            self._reset_sound_feedback_setting,
        )
        add_reset_item(
            "Voice Feedback",
            "Beep For Unknown Only",
            "Reset the beep behavior and beep style to the default choices.",
            self._reset_voice_feedback_setting,
        )
        add_reset_item(
            "Dark Mode",
            "Light Mode",
            "Reset the theme back to the default light mode.",
            self._reset_theme_setting,
        )
        add_reset_item(
            "Practice Mode Enabled",
            "Disabled",
            "Restore practice mode to its default off state.",
            self._reset_practice_mode_setting,
        )
        add_reset_item(
            "Shortcut Keys",
            "Enabled",
            "Restore keyboard shortcuts to the default enabled state.",
            self._reset_keyboard_shortcuts_setting,
        )
        add_reset_item(
            "Gesture Profiles",
            "Normal",
            "Restore the gesture sensitivity profile to the balanced default.",
            self._reset_gesture_profile_setting,
        )
        add_reset_item(
            "Voice Device",
            "Default System Microphone",
            "Reset the selected microphone back to the default startup device.",
            self._reset_voice_device_setting,
        )
        add_reset_item(
            "Custom Voice Commands",
            "Built-In Phrases",
            "Remove saved custom phrases and keep the built-in voice commands.",
            self._reset_custom_voice_commands_setting,
        )
        add_reset_item(
            "Custom Gesture Actions",
            "Default Mapping",
            "Restore gesture actions to the original VisionSlide mapping.",
            self._reset_custom_gesture_actions_setting,
        )

        reset_all_button = QPushButton("Reset All Settings")
        reset_all_button.setProperty("variant", "danger")
        reset_all_button.clicked.connect(self.reset_settings)

        close_button = QPushButton("Close")
        close_button.clicked.connect(dialog.accept)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(scroll_area)
        layout.addWidget(reset_all_button)
        layout.addWidget(close_button)

        self._apply_clickable_cursors(dialog)
        dialog.exec()

    def _confirm_reset_setting(self, title, message, action, success_message):
        if not self._show_confirmation_popup(title, message, confirm_text="Reset", cancel_text="Cancel"):
            return
        action()
        self._save_current_user_preferences()
        self._show_security_result_popup(title, success_message, success=True)

    def _reset_camera_setting(self):
        self.config.set("camera_index", 0)
        camera_index = self.camera_index_input.findData(0)
        if camera_index >= 0:
            self.camera_index_input.setCurrentIndex(camera_index)
        self.camera_manager.camera_index = 0
        self._set_badge(self.status_value, "Camera selection reset to default", "info")

    def _reset_control_hold_setting(self):
        self.config.set("control_hold_frames", 3)
        self.control_hold_input.setValue(3)
        self.control_hold_frames = 3
        self._set_badge(self.status_value, "Control hold reset to default", "info")

    def _reset_jump_hold_setting(self):
        self.config.set("jump_hold_seconds", 0.1)
        self.jump_hold_input.setValue(0.1)
        self.jump_hold_seconds = 0.1
        self._set_badge(self.status_value, "Jump hold reset to default", "info")

    def _reset_auto_focus_setting(self):
        self.config.set("auto_focus_presentation", True)
        self.auto_focus_checkbox.setChecked(True)
        self.slide_controller.set_auto_focus_enabled(True)
        self._set_badge(self.status_value, "Auto focus reset to default", "info")

    def _reset_gesture_setting(self):
        self.config.set("gesture_enabled", True)
        self.gesture_checkbox.setChecked(True)
        self._set_badge(self.status_value, "Gesture control reset to default", "info")

    def _reset_voice_setting(self):
        self.config.set("voice_enabled", False)
        self.voice_checkbox.setChecked(False)
        self.voice_listener.stop()
        self._set_badge(self.voice_value, "None", "muted")
        self._set_badge(self.status_value, "Voice control reset to default", "info")

    def _reset_sound_feedback_setting(self):
        self.config.set("sound_enabled", True)
        self.sound_feedback_checkbox.setChecked(True)
        self.audio_feedback.set_enabled(True)
        self._set_badge(self.status_value, "Sound feedback reset to default", "info")

    def _reset_voice_feedback_setting(self):
        self.voice_feedback_mode = "unknown_only"
        self.voice_feedback_beep_style = "standard"
        self.config.set("voice_feedback_mode", self.voice_feedback_mode)
        self.config.set("voice_feedback_beep_style", self.voice_feedback_beep_style)
        self.audio_feedback.set_beep_style(self.voice_feedback_beep_style)
        self._set_badge(self.status_value, "Voice feedback reset to default", "info")

    def _reset_theme_setting(self):
        self.config.set("theme", "light")
        self.theme_checkbox.setChecked(False)
        self.toggle_theme(False)
        self._set_badge(self.status_value, "Theme reset to default light mode", "info")

    def _reset_practice_mode_setting(self):
        self.practice_mode_enabled = False
        self.config.set("practice_mode", False)
        self.practice_mode_checkbox.setChecked(False)
        self._set_badge(self.status_value, "Practice mode reset to default", "info")

    def _reset_keyboard_shortcuts_setting(self):
        self.keyboard_shortcuts_enabled = True
        self.config.set("keyboard_shortcuts_enabled", True)
        self.keyboard_shortcuts_checkbox.setChecked(True)
        self._update_keyboard_shortcuts()
        self._set_badge(self.status_value, "Shortcut keys reset to default", "info")

    def _reset_gesture_profile_setting(self):
        self._apply_gesture_profile("Normal")
        self._set_badge(self.status_value, "Gesture profile reset to default", "info")

    def _reset_voice_device_setting(self):
        available_devices = [
            self.voice_device_input.itemText(index)
            for index in range(self.voice_device_input.count())
        ]
        default_voice_device = sanitize_voice_device_name(
            "Default System Microphone",
            allowed_devices=available_devices,
            default=available_devices[0] if available_devices else "Default System Microphone",
        )
        self.config.set("voice_device_name", default_voice_device)
        voice_device_index = self.voice_device_input.findText(default_voice_device)
        if voice_device_index >= 0:
            self.voice_device_input.setCurrentIndex(voice_device_index)
        self.voice_listener.device_name = default_voice_device
        self._set_badge(self.status_value, "Voice device reset to default", "info")

    def _reset_total_slides_setting(self):
        self.config.set("total_slides", 100)
        self.total_slides_input.setValue(100)
        self._set_badge(self.status_value, "Total slides reset to default", "info")

    def _reset_custom_voice_commands_setting(self):
        self.custom_voice_commands = {}
        self.config.set("custom_voice_commands", self.custom_voice_commands)
        self._refresh_voice_listener_commands()
        self._set_badge(self.status_value, "Custom voice commands reset to default", "info")

    def _reset_custom_gesture_actions_setting(self):
        self.custom_gesture_actions = {}
        self.config.set("custom_gesture_actions", self.custom_gesture_actions)
        self._set_badge(self.status_value, "Custom gesture actions reset to default", "info")

    def open_voice_settings_dialog(self):
        dialog = MicrophoneSettingsDialog(self, dark_mode=self._is_dark_theme_active())
        current_device = self.config.get("voice_device_name")
        if current_device:
            current_index = dialog.voice_device_input.findText(current_device, Qt.MatchExactly)
            if current_index >= 0:
                dialog.voice_device_input.setCurrentIndex(current_index)

        dialog.raise_()
        dialog.activateWindow()
        if dialog.exec() == QDialog.Accepted:
            selected_mic = dialog.voice_device_input.currentText()
            if not selected_mic:
                self._set_badge(self.status_value, "No microphone selected", "danger")
                return

            self.change_voice_device_name(selected_mic)
            self.voice_device_input.setCurrentText(self.config.get("voice_device_name"))
            self._set_badge(self.status_value, "Voice device updated", "success")

    def open_presentation_file(self):
        selected_file, _ = QFileDialog.getOpenFileName(
            self,
            "Open Presentation",
            str(Path.home()),
            "Presentation Files (*.ppt *.pptx *.pps *.ppsx *.pdf);;PowerPoint Files (*.ppt *.pptx *.pps *.ppsx);;PDF Files (*.pdf);;All Files (*.*)",
        )
        if not selected_file:
            return

        try:
            os.startfile(selected_file)
        except OSError as error:
            self._set_badge(self.status_value, "Presentation open failed", "danger")
            QMessageBox.warning(
                self,
                "Open Presentation",
                f"Could not open the selected file.\n\n{error}",
            )
            return

        presentation_name = Path(selected_file).name
        self.current_presentation_path = selected_file
        self._add_recent_presentation(selected_file)
        self._set_badge(self.status_value, f"Opened {presentation_name}", "success")

    def _default_custom_voice_commands(self):
        return {
            "next": ["next", "next slide", "go next", "forward", "go forward"],
            "previous": [
                "previous",
                "previous slide",
                "go previous",
                "go back",
                "back",
                "backward",
                "go backward",
                "prevous",
                "prevoius",
                "previus",
                "previos",
                "pervious",
                "previs",
                "prevish",
                "privious",
            ],
            "start": ["start", "begin", "start slideshow", "start slide show", "begin slideshow"],
            "exit": ["exit", "stop", "end", "finish", "finish slideshow", "finish slide show", "exit slideshow", "exit slide show", "stop slideshow", "end slideshow"],
            "first": ["first", "first slide", "go to first slide"],
            "last": ["final slide", "go to final slide", "last slide", "go to last slide"],
            "jump_prefix": ["go to slide", "jump to slide", "slide", "go to", "go slide", "goto", "goto slide", "jump slide"],
        }

    def _default_custom_gesture_actions(self):
        return {
            "Two Fingers": "next",
            "One Finger": "previous",
            "Open Palm": "start",
            "Fist": "exit",
        }

    def _gesture_action_choices(self, gesture_name=None):
        default_mapping = self._default_custom_gesture_actions()
        default_action = default_mapping.get(gesture_name)
        base_choices = [
            ("next", "Next Slide"),
            ("previous", "Previous Slide"),
            ("start", "Start Slideshow"),
            ("exit", "Exit Slideshow"),
            ("first", "First Slide"),
            ("last", "Last Slide"),
            ("none", "Disabled"),
        ]
        choices = []
        for action_key, action_label in base_choices:
            if default_action == action_key:
                choices.append((action_key, f"{action_label} (Default)"))
            else:
                choices.append((action_key, action_label))
        return choices

    def _gesture_action_label(self, action_key):
        choice_map = {key: label for key, label in self._gesture_action_choices()}
        return choice_map.get(action_key, "Disabled")

    def _normalized_custom_gesture_actions(self):
        merged = self._default_custom_gesture_actions()
        allowed_actions = {key for key, _label in self._gesture_action_choices()}
        for gesture_name, action_key in dict(self.custom_gesture_actions or {}).items():
            gesture_text = str(gesture_name or "").strip()
            action_text = str(action_key or "").strip().lower()
            if gesture_text in merged and action_text in allowed_actions:
                merged[gesture_text] = action_text
        return merged

    def _normalize_voice_phrase_text(self, phrase):
        normalized = str(phrase or "").strip().lower().replace("-", " ")
        normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)
        normalized = " ".join(normalized.split())
        if not normalized:
            return ""
        normalized = normalized.replace("slide show", "slideshow")
        normalized = normalized.replace("go to", "goto")
        return normalized

    def _number_to_words_local(self, number):
        ones = {
            0: "zero",
            1: "one",
            2: "two",
            3: "three",
            4: "four",
            5: "five",
            6: "six",
            7: "seven",
            8: "eight",
            9: "nine",
        }
        teens = {
            10: "ten",
            11: "eleven",
            12: "twelve",
            13: "thirteen",
            14: "fourteen",
            15: "fifteen",
            16: "sixteen",
            17: "seventeen",
            18: "eighteen",
            19: "nineteen",
        }
        tens = {
            20: "twenty",
            30: "thirty",
            40: "forty",
            50: "fifty",
            60: "sixty",
            70: "seventy",
            80: "eighty",
            90: "ninety",
        }

        if number < 10:
            return ones[number]
        if 10 <= number < 20:
            return teens[number]
        if number == 100:
            return "one hundred"
        if number in tens:
            return tens[number]
        ten_part = (number // 10) * 10
        one_part = number % 10
        return f"{tens[ten_part]} {ones[one_part]}"

    def _spoken_number_alias_map(self):
        alias_map = {str(number): number for number in range(1, 101)}
        for number in range(1, 101):
            alias_map[self._number_to_words_local(number)] = number

        alias_map.update(
            {
                "won": 1,
                "wun": 1,
                "to": 2,
                "too": 2,
                "tu": 2,
                "tree": 3,
                "for": 4,
                "foor": 4,
                "fiv": 5,
                "sics": 6,
                "sevan": 7,
                "saven": 7,
                "siven": 7,
                "sivin": 7,
                "sivan": 7,
                "sevven": 7,
                "zeven": 7,
                "sven": 7,
                "savin": 7,
                "sevvin": 7,
                "sehven": 7,
                "seben": 7,
                "sevem": 7,
                "sevenn": 7,
                "ate": 8,
                "ait": 8,
                "aight": 8,
                "eit": 8,
                "eyt": 8,
                "eightt": 8,
                "haight": 8,
                "niene": 9,
                "leven": 11,
                "ileven": 11,
                "eliven": 11,
                "elevan": 11,
                "aleven": 11,
                "sleven": 11,
                "tweleve": 12,
                "twelv": 12,
                "twelwe": 12,
                "tuelve": 12,
                "tuelv": 12,
                "twelbe": 12,
                "forteen": 14,
                "fiveteen": 15,
                "seveteen": 17,
                "eighteenn": 18,
                "hundred": 100,
            }
        )
        return alias_map

    def _resolve_spoken_number_value(self, command_text):
        normalized = self._normalize_voice_phrase_text(command_text)
        if not normalized:
            return None

        alias_map = self._spoken_number_alias_map()
        direct_value = alias_map.get(normalized)
        if direct_value is not None:
            return direct_value

        collapsed = normalized.replace(" ", "")
        collapsed_alias_map = {key.replace(" ", ""): value for key, value in alias_map.items()}
        return collapsed_alias_map.get(collapsed)

    def _canonical_voice_display_text(self, command_text, resolved_action=None, resolved_slide_number=None):
        cleaned = str(command_text or "").strip().lower().replace("-", " ")
        cleaned = re.sub(r"[^a-z0-9\s]", " ", cleaned)
        cleaned = " ".join(cleaned.split())
        if not cleaned:
            return "None"
        if resolved_action is not None:
            return cleaned.title()
        if resolved_slide_number is not None:
            return cleaned.title()
        spoken_number_value = self._resolve_spoken_number_value(cleaned)
        if spoken_number_value is not None:
            return self._number_to_words_local(spoken_number_value).title()
        return cleaned.title()

    def _normalized_custom_voice_commands(self):
        merged = self._default_custom_voice_commands()
        for action, phrases in dict(self.custom_voice_commands or {}).items():
            cleaned = list(merged.get(action, []))
            for phrase in phrases or []:
                phrase_text = self._normalize_voice_phrase_text(phrase)
                if phrase_text and phrase_text not in cleaned:
                    cleaned.append(phrase_text)
            if cleaned:
                merged[action] = cleaned
        for action, phrases in list(merged.items()):
            normalized_phrases = []
            for phrase in phrases:
                phrase_text = self._normalize_voice_phrase_text(phrase)
                if action == "jump_prefix" and phrase_text == "go":
                    continue
                if action == "last" and phrase_text in {"last", "final"}:
                    continue
                if phrase_text and phrase_text not in normalized_phrases:
                    normalized_phrases.append(phrase_text)
            merged[action] = normalized_phrases
        return merged

    def _refresh_voice_listener_commands(self):
        command_values = []
        normalized_commands = self._normalized_custom_voice_commands()
        jump_prefixes = list(normalized_commands.get("jump_prefix", []))
        fast_partial_commands = []
        for action_name, phrases in normalized_commands.items():
            if action_name == "jump_prefix":
                continue
            command_values.extend(phrases)
            fast_partial_commands.extend(phrases)

        number_words = [
            "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
            "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen",
            "twenty", "twenty one", "twenty two", "twenty three", "twenty four", "twenty five", "twenty six", "twenty seven", "twenty eight", "twenty nine",
            "thirty", "thirty one", "thirty two", "thirty three", "thirty four", "thirty five", "thirty six", "thirty seven", "thirty eight", "thirty nine",
            "forty", "forty one", "forty two", "forty three", "forty four", "forty five", "forty six", "forty seven", "forty eight", "forty nine",
            "fifty", "fifty one", "fifty two", "fifty three", "fifty four", "fifty five", "fifty six", "fifty seven", "fifty eight", "fifty nine",
            "sixty", "sixty one", "sixty two", "sixty three", "sixty four", "sixty five", "sixty six", "sixty seven", "sixty eight", "sixty nine",
            "seventy", "seventy one", "seventy two", "seventy three", "seventy four", "seventy five", "seventy six", "seventy seven", "seventy eight", "seventy nine",
            "eighty", "eighty one", "eighty two", "eighty three", "eighty four", "eighty five", "eighty six", "eighty seven", "eighty eight", "eighty nine",
            "ninety", "ninety one", "ninety two", "ninety three", "ninety four", "ninety five", "ninety six", "ninety seven", "ninety eight", "ninety nine",
            "one hundred",
        ]
        command_values.extend(number_words)
        command_values.extend(str(number) for number in range(1, 101))
        number_aliases = sorted(
            {
                alias
                for alias, value in self._spoken_number_alias_map().items()
                if alias and value in {1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 14, 15, 17, 18, 100}
            }
        )
        command_values.extend(number_aliases)
        for number in range(1, 101):
            number_words_cmd = self.voice_listener.number_to_words(number)
            number_digit_cmd = str(number)
            for jump_prefix in jump_prefixes:
                prefix_text = str(jump_prefix or "").strip().lower()
                if prefix_text:
                    command_values.append(f"{prefix_text} {number_words_cmd}")
                    command_values.append(f"{prefix_text} {number_digit_cmd}")
            for alias_text, alias_number in self._spoken_number_alias_map().items():
                if alias_number == number:
                    for jump_prefix in jump_prefixes:
                        prefix_text = str(jump_prefix or "").strip().lower()
                        if (
                            prefix_text
                            and alias_text in number_aliases
                            and alias_text != number_words_cmd
                            and alias_text != number_digit_cmd
                        ):
                            command_values.append(f"{prefix_text} {alias_text}")
        self.voice_listener.commands = sorted({command.strip().lower() for command in command_values if command})
        self.voice_listener.fast_partial_commands = sorted(
            {command.strip().lower() for command in fast_partial_commands if command}
        )
        self.voice_listener._refresh_command_cache()
        if getattr(self, "voice_checkbox", None) is not None and self.voice_checkbox.isChecked():
            self.voice_listener.start()

    def _save_feature_lists(self):
        self.config.set("recent_presentations", self.recent_presentations[:10])
        self.config.set("command_history", self.command_history_entries[:80])
        self.config.set("custom_voice_commands", self.custom_voice_commands)
        self.config.set("custom_gesture_actions", self.custom_gesture_actions)
        self.config.set("practice_mode", self.practice_mode_enabled)
        self.config.set("gesture_profile", self.gesture_profile_name)
        self.config.set("voice_feedback_mode", self.voice_feedback_mode)
        self.config.set("show_camera_overlays", self.show_camera_overlays)
        self.config.set("user_preferences", self.user_preferences)
        self.config.set("admin_activity_log", self.admin_activity_entries[:120])
        self.config.set("auto_lock_minutes", 0)
        self.config.set("keyboard_shortcuts_enabled", self.keyboard_shortcuts_enabled)

    def _current_user_pref_key(self):
        return (self.current_email or self.current_user or "").strip().lower()

    def _current_user_preferences_snapshot(self):
        return {
            "theme": bool(self.dark_mode),
            "voice_device_name": self.config.get("voice_device_name"),
            "control_hold_frames": int(self.control_hold_input.value()),
            "control_hold_default_migrated": True,
            "jump_hold_seconds": float(self.jump_hold_input.value()),
            "sound_feedback_enabled": bool(self.sound_feedback_checkbox.isChecked()),
            "voice_feedback_mode": self.voice_feedback_mode,
            "voice_feedback_beep_style": self.voice_feedback_beep_style,
            "gesture_profile": self.gesture_profile_name,
            "practice_mode": self.practice_mode_enabled,
            "show_camera_overlays": self.show_camera_overlays,
            "keyboard_shortcuts_enabled": self.keyboard_shortcuts_enabled,
            "auto_lock_minutes": 0,
            "custom_voice_commands": dict(self.custom_voice_commands),
            "custom_gesture_actions": dict(self.custom_gesture_actions),
        }

    def _save_current_user_preferences(self):
        pref_key = self._current_user_pref_key()
        if not pref_key:
            return
        self.user_preferences[pref_key] = self._current_user_preferences_snapshot()
        self.config.set("user_preferences", self.user_preferences)

    def _load_current_user_preferences(self):
        pref_key = self._current_user_pref_key()
        if not pref_key:
            return
        preferences = dict(self.user_preferences.get(pref_key, {}))
        if not preferences:
            return

        if "control_hold_frames" in preferences:
            control_hold_frames = sanitize_control_hold_frames(preferences["control_hold_frames"], 3)
            if control_hold_frames == 10 and not bool(preferences.get("control_hold_default_migrated", False)):
                control_hold_frames = 3
                preferences["control_hold_frames"] = control_hold_frames
                preferences["control_hold_default_migrated"] = True
                self.user_preferences[pref_key] = preferences
                self.config.set("user_preferences", self.user_preferences)
            self.control_hold_input.setValue(control_hold_frames)
        if "jump_hold_seconds" in preferences:
            self.jump_hold_input.setValue(float(preferences["jump_hold_seconds"]))
        if "voice_device_name" in preferences:
            self.change_voice_device_name(preferences["voice_device_name"])
        sound_feedback_enabled = bool(preferences.get("sound_feedback_enabled", self.config.get("sound_enabled")))
        self.sound_feedback_checkbox.blockSignals(True)
        self.sound_feedback_checkbox.setChecked(sound_feedback_enabled)
        self.sound_feedback_checkbox.blockSignals(False)
        self.config.set("sound_enabled", sound_feedback_enabled)
        self.audio_feedback.set_enabled(sound_feedback_enabled)
        self.voice_feedback_mode = str(preferences.get("voice_feedback_mode", self.voice_feedback_mode))
        if self.voice_feedback_mode == "silent":
            self.voice_feedback_mode = "unknown_only"
        self.voice_feedback_beep_style = str(preferences.get("voice_feedback_beep_style", self.voice_feedback_beep_style))
        self.audio_feedback.set_beep_style(self.voice_feedback_beep_style)
        self.gesture_profile_name = str(preferences.get("gesture_profile", self.gesture_profile_name))
        self.practice_mode_enabled = bool(preferences.get("practice_mode", self.practice_mode_enabled))
        self.show_camera_overlays = bool(preferences.get("show_camera_overlays", self.show_camera_overlays))
        self.keyboard_shortcuts_enabled = bool(preferences.get("keyboard_shortcuts_enabled", self.keyboard_shortcuts_enabled))
        self.auto_lock_minutes = 0
        self.custom_voice_commands = dict(preferences.get("custom_voice_commands", self.custom_voice_commands))
        self.custom_gesture_actions = dict(preferences.get("custom_gesture_actions", self.custom_gesture_actions))
        self.practice_mode_checkbox.blockSignals(True)
        self.practice_mode_checkbox.setChecked(self.practice_mode_enabled)
        self.practice_mode_checkbox.blockSignals(False)
        self.keyboard_shortcuts_checkbox.blockSignals(True)
        self.keyboard_shortcuts_checkbox.setChecked(self.keyboard_shortcuts_enabled)
        self.keyboard_shortcuts_checkbox.blockSignals(False)
        theme_value = bool(preferences.get("theme", self.dark_mode))
        self.theme_checkbox.blockSignals(True)
        self.theme_checkbox.setChecked(theme_value)
        self.theme_checkbox.blockSignals(False)
        self.toggle_theme(theme_value)
        self._refresh_voice_listener_commands()
        self._update_keyboard_shortcuts()
        self.auto_lock_check_timer.stop()

    def _play_command_feedback(self, event_type="success"):
        if self.voice_feedback_mode == "unknown_only":
            if event_type == "unknown":
                self.audio_feedback.play_unrecognized_gesture()
            return
        if self.voice_feedback_mode == "success_only":
            if event_type == "success":
                self.audio_feedback.play_slide_change()
            return
        if event_type == "success":
            self.audio_feedback.play_slide_change()
        elif event_type in {"unknown", "failure"}:
            self.audio_feedback.play_unrecognized_gesture()

    def _record_command_history(self, source, phrase, action, success=True):
        timestamp = time.strftime("%I:%M:%S %p")
        entry = {
            "time": timestamp,
            "source": str(source),
            "phrase": str(phrase or ""),
            "action": str(action or ""),
            "success": bool(success),
        }
        self.command_history_entries.insert(0, entry)
        self.command_history_entries = self.command_history_entries[:80]
        self.config.set("command_history", self.command_history_entries)

    def _log_admin_activity(self, action, detail):
        if not self._is_admin_user():
            return
        entry = {
            "time": time.strftime("%Y-%m-%d %I:%M:%S %p"),
            "admin": self.current_email or self.current_user,
            "action": str(action),
            "detail": str(detail),
        }
        self.admin_activity_entries.insert(0, entry)
        self.admin_activity_entries = self.admin_activity_entries[:120]
        self.config.set("admin_activity_log", self.admin_activity_entries)

    def _add_recent_presentation(self, file_path):
        normalized_path = str(Path(file_path))
        self.recent_presentations = [path for path in self.recent_presentations if path != normalized_path]
        self.recent_presentations.insert(0, normalized_path)
        self.recent_presentations = self.recent_presentations[:10]
        self.config.set("recent_presentations", self.recent_presentations)

    def _resolve_voice_action(self, command_text):
        normalized = self._normalize_voice_phrase_text(command_text)
        for action_name, phrases in self._normalized_custom_voice_commands().items():
            if action_name == "jump_prefix":
                continue
            for phrase in phrases:
                phrase_text = self._normalize_voice_phrase_text(phrase)
                if not phrase_text:
                    continue
                if normalized == phrase_text:
                    return action_name
        return None

    def _is_exact_number_phrase(self, command_text):
        return self._resolve_spoken_number_value(command_text) is not None

    def _resolve_jump_voice_command(self, command_text):
        normalized = self._normalize_voice_phrase_text(command_text)
        if not normalized:
            return None

        if self._is_exact_number_phrase(normalized):
            return self.parse_spoken_slide_number(normalized)

        jump_prefixes = [
            self._normalize_voice_phrase_text(prefix)
            for prefix in self._normalized_custom_voice_commands().get("jump_prefix", [])
            if self._normalize_voice_phrase_text(prefix)
        ]
        for prefix in jump_prefixes:
            prefix_with_space = f"{prefix} "
            if normalized.startswith(prefix_with_space):
                number_part = normalized[len(prefix_with_space):].strip()
                if self._is_exact_number_phrase(number_part):
                    return self.parse_spoken_slide_number(number_part)
        return None

    def _execute_presentation_action(self, action_label, callback, source, phrase="", success_tone="success", failure_tone="danger"):
        if self.practice_mode_enabled:
            self._set_badge(self.action_value, f"Practice: {action_label}", "warning")
            self._record_command_history(source, phrase or action_label, f"Practice: {action_label}", True)
            self._play_command_feedback("success")
            return True

        focused = callback()
        self._set_badge(
            self.action_value,
            action_label if focused else "Presentation Not Found!",
            success_tone if focused else failure_tone,
        )
        self._record_command_history(source, phrase or action_label, action_label if focused else "Presentation Not Found!", focused)
        if focused:
            self._play_command_feedback("success")
        else:
            if self.voice_feedback_mode == "success_only":
                self._play_command_feedback("success")
            else:
                self._play_command_feedback("failure")
        return focused

    def _execute_custom_gesture_action(self, gesture_name):
        action_key = self._normalized_custom_gesture_actions().get(gesture_name, "none")
        if action_key == "none":
            self._set_badge(self.action_value, "None", "muted")
            return True

        action_map = {
            "next": ("Next Slide", self.slide_controller.next_slide, "next_slide", "success"),
            "previous": ("Previous Slide", self.slide_controller.previous_slide, "previous_slide", "success"),
            "start": ("Start Slideshow", self.slide_controller.start_slideshow, "start_slideshow", "success"),
            "exit": ("Exit Slideshow", self.slide_controller.exit_slideshow, "exit_slideshow", "warning"),
            "first": ("First Slide", self.slide_controller.first_slide, "first_slide", "success"),
            "last": ("Last Slide", self.slide_controller.last_slide, "last_slide", "success"),
        }
        action_label, action_callback, cooldown_key, success_tone = action_map.get(
            action_key,
            ("", None, "", "success"),
        )
        if not action_callback or not cooldown_key:
            self._set_badge(self.action_value, "None", "muted")
            return True
        if not self.cooldown_manager.can_trigger(cooldown_key):
            return True
        return self._execute_presentation_action(
            action_label,
            action_callback,
            "Gesture",
            gesture_name,
            success_tone=success_tone,
            failure_tone="danger",
        )

    def _apply_gesture_profile(self, profile_name):
        presets = {
            "Normal": (3, 0.1),
            "Steady": (4, 0.3),
            "Fast": (2, 0.1),
        }
        if profile_name not in presets:
            return
        control_frames, jump_seconds = presets[profile_name]
        self.gesture_profile_name = profile_name
        self.control_hold_input.setValue(control_frames)
        self.jump_hold_input.setValue(jump_seconds)
        self.config.set("gesture_profile", self.gesture_profile_name)
        self._save_current_user_preferences()

    def _format_history_entry_text(self, entry):
        status_text = "Success" if entry.get("success") else "Missed"
        parts = [
            (entry.get("time", "") or "").strip(),
            (entry.get("source", "") or "").strip(),
            (entry.get("phrase", "") or "").strip(),
            (entry.get("action", "") or "").strip(),
            status_text,
        ]
        return "  |  ".join(part for part in parts if part)

    def show_recent_files_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Recent Files")
        self._apply_standard_dialog_size(dialog, "standard")
        self._apply_tools_dialog_style(dialog)
        layout = QVBoxLayout()
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)
        dialog.setLayout(layout)
        title = QLabel("Recent Files")
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #173543;")
        file_list = QListWidget()
        file_list.setSelectionMode(QAbstractItemView.NoSelection)
        file_list.setSpacing(2)
        file_list.setFocusPolicy(Qt.NoFocus)
        file_list.setMouseTracking(True)
        file_list.setStyleSheet(self._tool_list_stylesheet())
        clear_button = QPushButton("Clear All")
        close_button = QPushButton("Close")

        def refresh_recent_list():
            file_list.clear()
            for recent_path in self.recent_presentations:
                item = QListWidgetItem()
                item.setSizeHint(QSize(0, 52))
                file_list.addItem(item)

                row_widget = QWidget()
                row_widget.setStyleSheet("background: transparent;")
                row_layout = QHBoxLayout()
                row_layout.setContentsMargins(8, 4, 8, 4)
                row_layout.setSpacing(6)
                row_widget.setLayout(row_layout)

                more_button = QToolButton()
                more_button.setText("...")
                more_button.setCursor(Qt.PointingHandCursor)
                more_button.setFixedSize(38, 38)
                more_button.setAutoRaise(True)
                more_button.setStyleSheet(self._tool_more_button_stylesheet())
                attach_hover_bounce(more_button, y_offset=3, duration=185)
                more_button.clicked.connect(
                    lambda _=False, button=more_button, path=recent_path: show_recent_actions(button, path)
                )
                row_layout.addWidget(more_button, 0, Qt.AlignVCenter)

                file_button = QPushButton(recent_path)
                file_button.setProperty("toolsStyleOverride", "true")
                file_button.setCursor(Qt.PointingHandCursor)
                file_button.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
                file_button.setMinimumHeight(30)
                file_button.setMaximumHeight(32)
                file_button.setFlat(True)
                file_button.setStyleSheet(self._tool_text_button_stylesheet(clickable=True))
                attach_hover_bounce(file_button, y_offset=3, duration=185)
                file_button.clicked.connect(lambda _=False, path=recent_path: open_recent_path(path))
                row_layout.addWidget(file_button, 0, Qt.AlignVCenter)
                row_layout.addStretch()

                file_list.setItemWidget(item, row_widget)

        def open_recent_path(selected_path):
            if not selected_path or not Path(selected_path).exists():
                self._show_security_result_popup("Recent Files", "The selected file is no longer available.", success=False)
                return
            try:
                os.startfile(selected_path)
                self.current_presentation_path = selected_path
                self._add_recent_presentation(selected_path)
                refresh_recent_list()
                self._set_badge(self.status_value, f"Opened {Path(selected_path).name}", "success")
            except OSError as error:
                self._show_tools_result_popup("Recent Files", f"Could not open the selected file.\n\n{error}", success=False)

        def remove_recent_path(selected_path):
            should_remove = self._show_confirmation_popup(
                "Recent Files",
                f"Are you sure you want to remove {Path(selected_path).name} from recent files?",
                confirm_text="Remove",
                cancel_text="Cancel",
            )
            if not should_remove:
                return
            self.recent_presentations = [path for path in self.recent_presentations if path != selected_path]
            self.config.set("recent_presentations", self.recent_presentations)
            refresh_recent_list()
            self._show_tools_result_popup("Recent Files", "Recent file removed successfully.", success=True)

        def show_recent_actions(button, selected_path):
            menu = QMenu(dialog)
            if self._is_dark_theme_active():
                menu.setStyleSheet(
                    "QMenu { background: #132630; border: 1px solid #42697c; border-radius: 10px; padding: 6px; color: #e7f3f8; }"
                    "QMenu::item { padding: 7px 18px; border-radius: 7px; color: #e7f3f8; }"
                    "QMenu::item:selected { background: #214353; color: #ffffff; }"
                )
            remove_action = menu.addAction("Remove")
            chosen_action = menu.exec(button.mapToGlobal(button.rect().bottomLeft()))
            if chosen_action == remove_action:
                remove_recent_path(selected_path)

        def clear_all_recent():
            if not self.recent_presentations:
                self._show_tools_result_popup("Recent Files", "No recent files are available to clear.", success=False)
                return
            should_clear = self._show_confirmation_popup(
                "Recent Files",
                "Are you sure you want to clear all recent files?",
                confirm_text="Clear",
                cancel_text="Cancel",
            )
            if not should_clear:
                return
            self.recent_presentations = []
            self.config.set("recent_presentations", self.recent_presentations)
            refresh_recent_list()
            self._show_tools_result_popup("Recent Files", "Recent files cleared successfully.", success=True)

        button_row = QHBoxLayout()
        button_row.addWidget(clear_button)
        button_row.addWidget(close_button)
        clear_button.clicked.connect(clear_all_recent)
        close_button.clicked.connect(dialog.accept)

        refresh_recent_list()
        layout.addWidget(title)
        layout.addWidget(file_list)
        layout.addLayout(button_row)
        self._finalize_tools_dialog(dialog)
        self._apply_clickable_cursors(dialog)
        file_list.setCursor(Qt.ArrowCursor)
        file_list.viewport().setCursor(Qt.ArrowCursor)
        dialog.exec()

    def show_command_history_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Command History")
        self._apply_standard_dialog_size(dialog, "form")
        self._apply_tools_dialog_style(dialog)
        layout = QVBoxLayout()
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)
        dialog.setLayout(layout)
        title = QLabel("Command History")
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #173543;")
        history_list = QListWidget()
        history_list.setSelectionMode(QAbstractItemView.NoSelection)
        history_list.setSpacing(2)
        history_list.setFocusPolicy(Qt.NoFocus)
        history_list.setMouseTracking(True)
        history_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        history_list.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        history_list.setWordWrap(False)
        history_list.setStyleSheet(self._tool_list_stylesheet())
        clear_button = QPushButton("Clear History")
        close_button = QPushButton("Close")

        def refresh_history_list():
            history_list.clear()
            for entry in self.command_history_entries:
                item = QListWidgetItem()
                item.setSizeHint(QSize(0, 52))
                history_list.addItem(item)

                row_widget = QWidget()
                row_widget.setStyleSheet("background: transparent;")
                row_widget.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
                row_layout = QHBoxLayout()
                row_layout.setContentsMargins(8, 4, 8, 4)
                row_layout.setSpacing(6)
                row_widget.setLayout(row_layout)

                more_button = QToolButton()
                more_button.setText("...")
                more_button.setCursor(Qt.PointingHandCursor)
                more_button.setFixedSize(38, 38)
                more_button.setAutoRaise(True)
                more_button.setStyleSheet(self._tool_more_button_stylesheet())
                attach_hover_bounce(more_button, y_offset=3, duration=185)
                more_button.clicked.connect(
                    lambda _=False, button=more_button, history_entry=entry: show_history_actions(button, history_entry)
                )
                row_layout.addWidget(more_button, 0, Qt.AlignVCenter)

                history_text = self._format_history_entry_text(entry)
                text_button = QPushButton(history_text)
                text_button.setProperty("toolsStyleOverride", "true")
                text_button.setProperty("historyStaticText", "true")
                text_button.setCursor(Qt.ArrowCursor)
                text_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
                text_button.setMinimumWidth(text_button.fontMetrics().horizontalAdvance(history_text) + 28)
                text_button.setMinimumHeight(30)
                text_button.setMaximumHeight(32)
                text_button.setFlat(True)
                text_button.setStyleSheet(self._tool_text_button_stylesheet(clickable=False))
                row_layout.addWidget(text_button, 0, Qt.AlignVCenter)

                row_width = more_button.width() + text_button.minimumWidth() + 34
                row_widget.setMinimumWidth(row_width)
                item.setSizeHint(QSize(row_width, 52))

                history_list.setItemWidget(item, row_widget)

        def remove_history_entry(history_entry):
            should_remove = self._show_confirmation_popup(
                "Command History",
                "Are you sure you want to remove this command history entry?",
                confirm_text="Remove",
                cancel_text="Cancel",
            )
            if not should_remove:
                return
            try:
                self.command_history_entries.remove(history_entry)
            except ValueError:
                self._show_tools_result_popup("Command History", "The selected history entry could not be found.", success=False)
                return
            self.config.set("command_history", self.command_history_entries)
            refresh_history_list()
            self._show_tools_result_popup("Command History", "Command history entry removed successfully.", success=True)

        def show_history_actions(button, history_entry):
            menu = QMenu(dialog)
            if self._is_dark_theme_active():
                menu.setStyleSheet(
                    "QMenu { background: #132630; border: 1px solid #42697c; border-radius: 10px; padding: 6px; color: #e7f3f8; }"
                    "QMenu::item { padding: 7px 18px; border-radius: 7px; color: #e7f3f8; }"
                    "QMenu::item:selected { background: #214353; color: #ffffff; }"
                )
            remove_action = menu.addAction("Remove")
            chosen_action = menu.exec(button.mapToGlobal(button.rect().bottomLeft()))
            if chosen_action == remove_action:
                remove_history_entry(history_entry)

        def clear_history():
            if not self.command_history_entries:
                self._show_tools_result_popup("Command History", "No command history is available to clear.", success=False)
                return
            should_clear = self._show_confirmation_popup(
                "Command History",
                "Are you sure you want to clear the full command history?",
                confirm_text="Clear",
                cancel_text="Cancel",
            )
            if not should_clear:
                return
            self.command_history_entries.clear()
            self.config.set("command_history", [])
            refresh_history_list()
            self._show_tools_result_popup("Command History", "Command history cleared successfully.", success=True)

        clear_button.clicked.connect(clear_history)
        close_button.clicked.connect(dialog.accept)
        button_row = self._build_dialog_action_row(clear_button, close_button, width=150)
        refresh_history_list()
        layout.addWidget(title)
        layout.addWidget(history_list)
        layout.addLayout(button_row)
        self._finalize_tools_dialog(dialog)
        self._apply_clickable_cursors(dialog)
        for history_button in dialog.findChildren(QPushButton):
            if history_button.property("historyStaticText") == "true":
                history_button.setCursor(Qt.ArrowCursor)
        history_list.setCursor(Qt.ArrowCursor)
        history_list.viewport().setCursor(Qt.ArrowCursor)
        dialog.exec()

    def show_practice_mode_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Practice Mode")
        self._apply_standard_dialog_size(dialog, "standard")
        self._apply_tools_dialog_style(dialog)
        layout = QVBoxLayout()
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)
        dialog.setLayout(layout)
        title = QLabel("Practice Mode")
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #173543;")
        description = QLabel(
            "When Practice Mode is enabled, gestures and voice commands are recognized normally but they do not send real slide controls."
        )
        description.setWordWrap(True)
        details = QLabel(
            "Use the checkbox in Settings to turn Practice Mode on or off. This window is only for understanding what the mode does."
        )
        details.setWordWrap(True)
        status_label = QLabel(f"Current status: {'Enabled' if self.practice_mode_enabled else 'Disabled'}")
        status_label.setWordWrap(True)
        close_button = QPushButton("Close")
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(title)
        layout.addWidget(description)
        layout.addWidget(details)
        layout.addWidget(status_label)
        layout.addStretch()
        layout.addWidget(close_button)
        self._finalize_tools_dialog(dialog)
        self._apply_clickable_cursors(dialog)
        dialog.exec()

    def show_custom_voice_commands_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Custom Voice Commands")
        self._apply_standard_dialog_size(dialog, "form")
        dialog.setMinimumHeight(600)
        dialog.resize(dialog.width(), 600)
        self._apply_tools_dialog_style(dialog)
        layout = QVBoxLayout()
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(10)
        dialog.setLayout(layout)
        title = QLabel("Custom Voice Commands")
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #173543;")
        ordered_keys = [
            ("next", "Next"),
            ("previous", "Previous"),
            ("start", "Start Slideshow"),
            ("exit", "Exit Slideshow"),
            ("first", "First Slide"),
            ("last", "Last Slide"),
            ("jump_prefix", "Jump To Slide Prefixes"),
        ]
        description = QLabel("")
        description.setWordWrap(True)
        actions_layout = QVBoxLayout()
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(10)
        close_button = QPushButton("Close")

        action_buttons = {}

        def save_voice_command_action(action_key, phrases):
            updated_commands = dict(self.custom_voice_commands or {})
            if phrases:
                updated_commands[action_key] = phrases
            else:
                updated_commands.pop(action_key, None)
            self.custom_voice_commands = updated_commands
            self.config.set("custom_voice_commands", self.custom_voice_commands)
            self._refresh_voice_listener_commands()
            self._save_current_user_preferences()
            self._set_badge(self.status_value, "Custom voice commands updated", "success")
            self._show_tools_result_popup("Custom Voice Commands", "Voice command mapping updated successfully.", success=True)
            refresh_action_buttons()

        def refresh_action_buttons():
            merged_commands = self._normalized_custom_voice_commands()
            for action_key, label_text in ordered_keys:
                phrase_count = len(merged_commands.get(action_key, []))
                phrase_label = "phrase" if phrase_count == 1 else "phrases"
                action_buttons[action_key].setText(f"{label_text} ({phrase_count} {phrase_label})")

        def open_action_editor(action_key, label_text):
            editor_dialog = QDialog(dialog)
            editor_dialog.setWindowTitle(label_text)
            self._apply_standard_dialog_size(editor_dialog, "form")
            self._apply_tools_dialog_style(editor_dialog)
            editor_layout = QVBoxLayout()
            editor_layout.setContentsMargins(22, 22, 22, 22)
            editor_layout.setSpacing(12)
            editor_dialog.setLayout(editor_layout)

            editor_title = QLabel(label_text)
            editor_title.setStyleSheet("font-size: 20px; font-weight: 700; color: #173543;")
            editor_layout.addWidget(editor_title)

            hint_text = "Add one custom phrase per line. VisionSlide will match any of them for this action."
            if action_key == "jump_prefix":
                hint_text = "Add one slide-jump prefix per line. These combine with spoken numbers like: go to slide twenty, slide five, or go to seven."
            hint_label = QLabel(hint_text)
            hint_label.setWordWrap(True)
            editor_layout.addWidget(hint_label)

            merged_commands = self._normalized_custom_voice_commands()
            phrases_input = QPlainTextEdit("\n".join(merged_commands.get(action_key, [])))
            if action_key == "jump_prefix":
                phrases_input.setPlaceholderText("go to slide\njump to slide\nslide\ngo to")
            else:
                phrases_input.setPlaceholderText("Add one phrase per line")
            editor_layout.addWidget(phrases_input)

            save_button = QPushButton("Save Phrases")
            close_editor_button = QPushButton("Close")

            def save_action_editor():
                phrases = []
                seen_phrases = set()
                for line in phrases_input.toPlainText().splitlines():
                    phrase_text = str(line or "").strip().lower()
                    if not phrase_text:
                        continue
                    if phrase_text in seen_phrases:
                        self._show_tools_result_popup(
                            label_text,
                            f'The phrase "{phrase_text}" is already added. Please keep each phrase only once.',
                            success=False,
                        )
                        return
                    seen_phrases.add(phrase_text)
                    phrases.append(phrase_text)
                save_voice_command_action(action_key, phrases)
                editor_dialog.accept()

            save_button.clicked.connect(save_action_editor)
            close_editor_button.clicked.connect(editor_dialog.accept)
            editor_button_row = self._build_dialog_action_row(save_button, close_editor_button, width=160)
            editor_layout.addStretch()
            editor_layout.addLayout(editor_button_row)
            self._finalize_tools_dialog(editor_dialog)
            self._apply_clickable_cursors(editor_dialog)
            editor_dialog.exec()

        for action_key, label_text in ordered_keys:
            action_button = QPushButton(label_text)
            action_button.clicked.connect(
                lambda _=False, key=action_key, title_text=label_text: open_action_editor(key, title_text)
            )
            action_buttons[action_key] = action_button
            actions_layout.addWidget(action_button)

        close_button.clicked.connect(dialog.accept)
        refresh_action_buttons()
        layout.addWidget(title)
        layout.addWidget(description)
        layout.addLayout(actions_layout)
        layout.addStretch()
        layout.addWidget(close_button)
        self._finalize_tools_dialog(dialog)
        self._apply_clickable_cursors(dialog)
        dialog.exec()

    def show_gesture_profiles_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Gesture Profiles")
        self._apply_standard_dialog_size(dialog, "standard")
        self._apply_tools_dialog_style(dialog)
        layout = QVBoxLayout()
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)
        dialog.setLayout(layout)
        title = QLabel("Gesture Profiles")
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #173543;")
        profile_input = QComboBox()
        profile_input.setObjectName("gestureProfileCombo")
        profile_input.addItem("Normal (Default)", "Normal")
        profile_input.addItem("Steady", "Steady")
        profile_input.addItem("Fast", "Fast")
        current_profile = self.gesture_profile_name if self.gesture_profile_name in ["Normal", "Steady", "Fast"] else "Normal"
        current_index = max(0, profile_input.findData(current_profile))
        profile_input.setCurrentIndex(current_index)
        profile_input.setMouseTracking(True)
        if profile_input.view() is not None:
            profile_input.view().setMouseTracking(True)
            profile_input.view().viewport().setMouseTracking(True)
        profile_input.setStyleSheet(self._tool_combo_stylesheet("gestureProfileCombo"))
        profile_description = QLabel()
        profile_description.setWordWrap(True)
        profile_description.setStyleSheet(
            "background: #17303b; border: 1px solid #355768; border-radius: 12px; "
            "padding: 12px; color: #d7e9f0; font-size: 12px; font-weight: 600;"
            if self._is_dark_theme_active()
            else
            "background: rgba(232, 243, 249, 0.9); border: 1px solid #d5e5ee; border-radius: 12px; "
            "padding: 12px; color: #173543; font-size: 12px; font-weight: 600;"
        )

        profile_details = {
            "Normal": "Balanced everyday profile. Good default for most users, with moderate hold timing for both control gestures and jump gestures.",
            "Steady": "More stable profile. Best when gestures are triggering too easily or the camera view is a little noisy. Requires steadier holding before actions fire.",
            "Fast": "Quick-response profile. Best when you want faster triggering and already have a clear camera view with confident hand positioning.",
        }

        def refresh_profile_description(profile_name):
            profile_description.setText(profile_details.get(profile_name, profile_details["Normal"]))

        apply_button = QPushButton("Apply Profile")
        close_button = QPushButton("Close")
        def apply_profile():
            selected_profile = str(profile_input.currentData() or "Normal")
            self._apply_gesture_profile(selected_profile)
            self._set_badge(self.status_value, f"{selected_profile} profile applied", "success")
            self._show_tools_result_popup("Gesture Profiles", f"{selected_profile} profile applied successfully.", success=True)
            dialog.accept()
        profile_input.currentIndexChanged.connect(lambda _: refresh_profile_description(str(profile_input.currentData() or "Normal")))
        refresh_profile_description(str(profile_input.currentData() or "Normal"))
        apply_button.clicked.connect(apply_profile)
        close_button.clicked.connect(dialog.accept)
        button_row = self._build_dialog_action_row(apply_button, close_button, width=150)
        layout.addWidget(title)
        layout.addWidget(QLabel("Choose a gesture sensitivity profile."))
        layout.addWidget(profile_input)
        layout.addWidget(profile_description)
        layout.addStretch()
        layout.addLayout(button_row)
        self._finalize_tools_dialog(dialog)
        self._apply_clickable_cursors(dialog)
        dialog.exec()

    def show_custom_gesture_actions_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Custom Gesture Actions")
        self._apply_standard_dialog_size(dialog, "form")
        self._apply_tools_dialog_style(dialog)
        layout = QVBoxLayout()
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)
        dialog.setLayout(layout)

        title = QLabel("Custom Gesture Actions")
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #173543;")
        description = QLabel("Remap the existing camera-recognized gestures to different presentation actions. This changes what each gesture triggers in Control Mode.")
        description.setWordWrap(True)

        controls_grid = QGridLayout()
        controls_grid.setHorizontalSpacing(12)
        controls_grid.setVerticalSpacing(10)

        gesture_inputs = {}
        current_mapping = self._normalized_custom_gesture_actions()
        gesture_rows = ["Open Palm", "Fist", "Two Fingers", "One Finger"]

        for row, gesture_name in enumerate(gesture_rows):
            controls_grid.addWidget(QLabel(gesture_name), row, 0)
            action_input = QComboBox()
            action_input.setObjectName("gestureActionCombo")
            for action_key, action_label in self._gesture_action_choices(gesture_name):
                action_input.addItem(action_label, action_key)
            current_index = action_input.findData(current_mapping.get(gesture_name, "none"))
            action_input.setCurrentIndex(current_index if current_index >= 0 else 0)
            action_input.setStyleSheet(self._tool_combo_stylesheet("gestureActionCombo"))
            gesture_inputs[gesture_name] = action_input
            controls_grid.addWidget(action_input, row, 1)

        save_button = QPushButton("Save Actions")
        close_button = QPushButton("Close")

        def save_gesture_actions():
            updated_mapping = {}
            for gesture_name, action_input in gesture_inputs.items():
                updated_mapping[gesture_name] = str(action_input.currentData() or "none")
            self.custom_gesture_actions = updated_mapping
            self.config.set("custom_gesture_actions", self.custom_gesture_actions)
            self._save_current_user_preferences()
            self._set_badge(self.status_value, "Custom gesture actions updated", "success")
            self._show_tools_result_popup("Custom Gesture Actions", "Gesture action mapping updated successfully.", success=True)
            dialog.accept()

        save_button.clicked.connect(save_gesture_actions)
        close_button.clicked.connect(dialog.accept)
        button_row = self._build_dialog_action_row(save_button, close_button, width=160)

        layout.addWidget(title)
        layout.addWidget(description)
        layout.addLayout(controls_grid)
        layout.addStretch()
        layout.addLayout(button_row)
        self._finalize_tools_dialog(dialog)
        self._apply_clickable_cursors(dialog)
        dialog.exec()

    def show_voice_feedback_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Voice Feedback")
        self._apply_standard_dialog_size(dialog, "standard")
        self._apply_tools_dialog_style(dialog)
        layout = QVBoxLayout()
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)
        dialog.setLayout(layout)
        title = QLabel("Voice Feedback")
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #173543;")
        mode_input = QComboBox()
        mode_input.setObjectName("voiceFeedbackCombo")
        mode_input.addItem("Beep For All Commands", "beep")
        mode_input.addItem("Beep For Unknown Only (Default)", "unknown_only")
        mode_input.addItem("Beep For Success Only", "success_only")
        mode_input.setMouseTracking(True)
        if mode_input.view() is not None:
            mode_input.view().setMouseTracking(True)
            mode_input.view().viewport().setMouseTracking(True)
        mode_input.setStyleSheet(self._tool_combo_stylesheet("voiceFeedbackCombo"))
        beep_style_list = QListWidget()
        beep_style_list.setSelectionMode(QAbstractItemView.SingleSelection)
        beep_style_list.setMouseTracking(True)
        beep_style_list.setCursor(Qt.PointingHandCursor)
        beep_style_list.setStyleSheet(self._beep_style_list_stylesheet())
        beep_style_options = [
            ("standard", "▶ Standard Beep (Default)"),
            ("soft", "▶ Soft Beep"),
            ("crisp", "▶ Crisp Beep"),
            ("chime", "▶ Chime Beep"),
        ]
        beep_style_options.extend(
            [
                ("pulse", "\u25B6 Pulse Beep"),
                ("bright", "\u25B6 Bright Beep"),
                ("mellow", "\u25B6 Mellow Beep"),
            ]
        )
        for style_key, style_label in beep_style_options:
            style_item = QListWidgetItem(style_label)
            style_item.setData(Qt.UserRole, style_key)
            beep_style_list.addItem(style_item)
        current_index = max(0, mode_input.findData(self.voice_feedback_mode))
        mode_input.setCurrentIndex(current_index)
        for index in range(beep_style_list.count()):
            style_item = beep_style_list.item(index)
            if style_item.data(Qt.UserRole) == self.voice_feedback_beep_style:
                beep_style_list.setCurrentItem(style_item)
                break
        apply_button = QPushButton("Apply")
        close_button = QPushButton("Close")

        def play_selected_beep(item):
            if item is None:
                return
            self.audio_feedback.preview_beep(item.data(Qt.UserRole), success=True)

        def apply_voice_feedback():
            self.voice_feedback_mode = mode_input.currentData()
            current_style_item = beep_style_list.currentItem()
            self.voice_feedback_beep_style = (
                current_style_item.data(Qt.UserRole) if current_style_item is not None else "standard"
            )
            self.config.set("voice_feedback_mode", self.voice_feedback_mode)
            self.config.set("voice_feedback_beep_style", self.voice_feedback_beep_style)
            self.audio_feedback.set_beep_style(self.voice_feedback_beep_style)
            self._save_current_user_preferences()
            self._set_badge(self.status_value, "Voice feedback updated", "success")
            self._show_tools_result_popup("Voice Feedback", "Voice feedback updated successfully.", success=True)
            dialog.accept()
        beep_style_list.itemClicked.connect(play_selected_beep)
        apply_button.clicked.connect(apply_voice_feedback)
        close_button.clicked.connect(dialog.accept)
        button_row = self._build_dialog_action_row(apply_button, close_button, width=140)
        layout.addWidget(title)
        layout.addWidget(QLabel("Choose how VisionSlide should confirm gesture and voice command activity."))
        layout.addWidget(mode_input)
        layout.addWidget(QLabel("Choose a beep style and click any item to preview it."))
        layout.addWidget(beep_style_list)
        layout.addStretch()
        layout.addLayout(button_row)
        self._finalize_tools_dialog(dialog)
        self._apply_clickable_cursors(dialog)
        dialog.exec()

    def _presentation_timer_seconds(self):
        if self.presentation_timer_running:
            return self.presentation_timer_elapsed_seconds + (time.monotonic() - self.presentation_timer_started_at)
        return self.presentation_timer_elapsed_seconds

    def _format_seconds(self, seconds):
        total_seconds = max(0, int(seconds))
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        remaining = total_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{remaining:02d}"

    def _update_presentation_timer_labels(self):
        if hasattr(self, "presentation_timer_value_label") and self.presentation_timer_value_label is not None:
            self.presentation_timer_value_label.setText(self._format_seconds(self._presentation_timer_seconds()))

    def show_presentation_timer_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Presentation Timer")
        self._apply_standard_dialog_size(dialog, "standard")
        self._apply_tools_dialog_style(dialog)
        layout = QVBoxLayout()
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)
        dialog.setLayout(layout)
        title = QLabel("Presentation Timer")
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #173543;")
        self.presentation_timer_value_label = QLabel(self._format_seconds(self._presentation_timer_seconds()))
        self.presentation_timer_value_label.setAlignment(Qt.AlignCenter)
        self.presentation_timer_value_label.setStyleSheet("font-size: 28px; font-weight: 800; color: #173543;")
        start_pause_button = QPushButton("Pause" if self.presentation_timer_running else "Start")
        reset_button = QPushButton("Reset")
        close_button = QPushButton("Close")
        def toggle_timer():
            if self.presentation_timer_running:
                self.presentation_timer_elapsed_seconds = self._presentation_timer_seconds()
                self.presentation_timer_running = False
                self.presentation_timer_tick.stop()
                start_pause_button.setText("Start")
                self._show_tools_result_popup("Presentation Timer", "Presentation timer paused successfully.", success=True)
            else:
                self.presentation_timer_started_at = time.monotonic()
                self.presentation_timer_running = True
                self.presentation_timer_tick.start()
                start_pause_button.setText("Pause")
                self._show_tools_result_popup("Presentation Timer", "Presentation timer started successfully.", success=True)
            self._update_presentation_timer_labels()
        def reset_timer():
            self.presentation_timer_running = False
            self.presentation_timer_elapsed_seconds = 0.0
            self.presentation_timer_tick.stop()
            start_pause_button.setText("Start")
            self._update_presentation_timer_labels()
            self._show_tools_result_popup("Presentation Timer", "Presentation timer reset successfully.", success=True)
        start_pause_button.clicked.connect(toggle_timer)
        reset_button.clicked.connect(reset_timer)
        close_button.clicked.connect(dialog.accept)
        button_row = QHBoxLayout()
        button_row.addWidget(start_pause_button)
        button_row.addWidget(reset_button)
        button_row.addWidget(close_button)
        layout.addWidget(title)
        layout.addWidget(self.presentation_timer_value_label)
        layout.addStretch()
        layout.addLayout(button_row)
        self._finalize_tools_dialog(dialog)
        self._apply_clickable_cursors(dialog)
        dialog.exec()

    def show_camera_overlays_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Camera Overlays")
        self._apply_standard_dialog_size(dialog, "standard")
        self._apply_tools_dialog_style(dialog)
        layout = QVBoxLayout()
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)
        dialog.setLayout(layout)
        title = QLabel("Camera Overlays")
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #173543;")
        overlay_checkbox = QCheckBox("Show overlay hints on the camera preview")
        overlay_checkbox.setChecked(self.show_camera_overlays)
        def toggle_overlays(checked):
            setattr(self, "show_camera_overlays", checked)
            self.config.set("show_camera_overlays", checked)
            self._save_current_user_preferences()
            self._show_tools_result_popup("Camera Overlays", "Camera overlays enabled successfully." if checked else "Camera overlays disabled successfully.", success=True)
        overlay_checkbox.toggled.connect(toggle_overlays)
        close_button = QPushButton("Close")
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(title)
        layout.addWidget(overlay_checkbox)
        layout.addStretch()
        layout.addWidget(close_button)
        self._finalize_tools_dialog(dialog)
        self._apply_clickable_cursors(dialog)
        dialog.exec()

    def show_export_profile_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Export Profile")
        self._apply_standard_dialog_size(dialog, "standard")
        self._apply_tools_dialog_style(dialog)
        layout = QVBoxLayout()
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)
        dialog.setLayout(layout)
        title = QLabel("Export Profile")
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #173543;")
        export_button = QPushButton("Export Current Profile")
        import_button = QPushButton("Import Profile")
        close_button = QPushButton("Close")
        def export_profile():
            file_path, _ = QFileDialog.getSaveFileName(self, "Export Profile", str(Path.home() / "visionslide_profile.json"), "JSON Files (*.json)")
            if not file_path:
                return
            profile_data = self._current_user_preferences_snapshot()
            Path(file_path).write_text(__import__("json").dumps(profile_data, indent=4), encoding="utf-8")
            self._set_badge(self.status_value, "Profile exported", "success")
            self._show_tools_result_popup("Export Profile", "Profile exported successfully.", success=True)
        def import_profile():
            file_path, _ = QFileDialog.getOpenFileName(self, "Import Profile", str(Path.home()), "JSON Files (*.json)")
            if not file_path:
                return
            try:
                profile_data = __import__("json").loads(Path(file_path).read_text(encoding="utf-8"))
            except Exception:
                self._show_security_result_popup("Import Profile", "Could not read the selected profile file.", success=False)
                return
            self.user_preferences[self._current_user_pref_key()] = profile_data
            self._load_current_user_preferences()
            self._save_feature_lists()
            self._set_badge(self.status_value, "Profile imported", "success")
            self._show_tools_result_popup("Import Profile", "Profile imported successfully.", success=True)
        export_button.clicked.connect(export_profile)
        import_button.clicked.connect(import_profile)
        close_button.clicked.connect(dialog.accept)
        button_row = QVBoxLayout()
        button_row.addWidget(export_button)
        button_row.addWidget(import_button)
        button_row.addWidget(close_button)
        layout.addWidget(title)
        layout.addWidget(QLabel("Save or load current VisionSlide preferences as a profile file."))
        layout.addLayout(button_row)
        self._finalize_tools_dialog(dialog)
        self._apply_clickable_cursors(dialog)
        dialog.exec()

    def show_user_preferences_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("User Preferences")
        self._apply_standard_dialog_size(dialog, "standard")
        self._apply_tools_dialog_style(dialog)
        layout = QVBoxLayout()
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)
        dialog.setLayout(layout)
        title = QLabel("User Preferences")
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #173543;")
        summary = QTextEdit()
        summary.setReadOnly(True)
        summary.setPlainText(
            f"Current user: {self.current_email or self.current_user}\n"
            f"Theme: {'Dark' if self.dark_mode else 'Light'}\n"
            f"Microphone: {self.config.get('voice_device_name')}\n"
            f"Control Hold: {self.control_hold_input.value()}\n"
            f"Jump Hold: {self.jump_hold_input.value():.1f}\n"
            f"Gesture Profile: {self.gesture_profile_name}\n"
            f"Voice Feedback: {self.voice_feedback_mode}\n"
        )
        save_button = QPushButton("Save Current Preferences")
        reload_button = QPushButton("Reload Saved Preferences")
        reset_button = QPushButton("Reset Saved Preferences")
        close_button = QPushButton("Close")
        def save_preferences():
            self._save_current_user_preferences()
            self._set_badge(self.status_value, "User preferences saved", "success")
            self._show_tools_result_popup("User Preferences", "User preferences saved successfully.", success=True)
        def reload_preferences():
            self._load_current_user_preferences()
            self._set_badge(self.status_value, "User preferences reloaded", "success")
            self._show_tools_result_popup("User Preferences", "User preferences reloaded successfully.", success=True)
        def reset_preferences():
            pref_key = self._current_user_pref_key()
            if pref_key in self.user_preferences:
                should_reset = self._show_confirmation_popup(
                    "User Preferences",
                    "Are you sure you want to reset the saved preferences for this account?",
                    confirm_text="Reset",
                    cancel_text="Cancel",
                )
                if not should_reset:
                    return
                del self.user_preferences[pref_key]
                self.config.set("user_preferences", self.user_preferences)
                self._set_badge(self.status_value, "User preferences cleared", "warning")
                self._show_tools_result_popup("User Preferences", "User preferences reset successfully.", success=True)
            else:
                self._show_tools_result_popup("User Preferences", "No saved preferences were found for this account.", success=False)
        save_button.clicked.connect(save_preferences)
        reload_button.clicked.connect(reload_preferences)
        reset_button.clicked.connect(reset_preferences)
        button_row = QVBoxLayout()
        button_row.addWidget(save_button)
        button_row.addWidget(reload_button)
        button_row.addWidget(reset_button)
        button_row.addWidget(close_button)
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(title)
        layout.addWidget(summary)
        layout.addLayout(button_row)
        self._finalize_tools_dialog(dialog)
        self._apply_clickable_cursors(dialog)
        dialog.exec()

    def show_admin_activity_log_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Admin Activity Log")
        self._apply_standard_dialog_size(dialog, "form")
        self._apply_tools_dialog_style(dialog)
        layout = QVBoxLayout()
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)
        dialog.setLayout(layout)
        title = QLabel("Admin Activity Log")
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #173543;")
        log_list = QListWidget()
        for entry in self.admin_activity_entries:
            log_list.addItem(f"{entry.get('time')} | {entry.get('admin')} | {entry.get('action')} | {entry.get('detail')}")
        clear_button = QPushButton("Clear Log")
        close_button = QPushButton("Close")
        def clear_log():
            if not self.admin_activity_entries:
                self._show_tools_result_popup("Admin Activity Log", "No admin activity log is available to clear.", success=False)
                return
            should_clear = self._show_confirmation_popup(
                "Admin Activity Log",
                "Are you sure you want to clear the admin activity log?",
                confirm_text="Clear",
                cancel_text="Cancel",
            )
            if not should_clear:
                return
            self.admin_activity_entries.clear()
            self.config.set("admin_activity_log", [])
            log_list.clear()
            self._show_tools_result_popup("Admin Activity Log", "Admin activity log cleared successfully.", success=True)
        clear_button.clicked.connect(clear_log)
        close_button.clicked.connect(dialog.accept)
        button_row = self._build_dialog_action_row(clear_button, close_button, width=150)
        layout.addWidget(title)
        layout.addWidget(log_list)
        layout.addLayout(button_row)
        self._finalize_tools_dialog(dialog)
        self._apply_clickable_cursors(dialog)
        dialog.exec()

    def show_auto_lock_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Auto Lock")
        self._apply_standard_dialog_size(dialog, "standard")
        self._apply_tools_dialog_style(dialog)
        layout = QVBoxLayout()
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)
        dialog.setLayout(layout)
        title = QLabel("Auto Lock")
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #173543;")
        minutes_input = QSpinBox()
        minutes_input.setRange(0, 120)
        minutes_input.setValue(self.auto_lock_minutes)
        apply_button = QPushButton("Apply")
        close_button = QPushButton("Close")
        def apply_auto_lock():
            self.auto_lock_minutes = int(minutes_input.value())
            self.config.set("auto_lock_minutes", self.auto_lock_minutes)
            self._save_current_user_preferences()
            if self.auto_lock_minutes > 0:
                self.auto_lock_check_timer.start()
            else:
                self.auto_lock_check_timer.stop()
            self._set_badge(self.status_value, "Auto lock updated", "success")
            self._show_tools_result_popup("Auto Lock", "Auto lock updated successfully.", success=True)
        apply_button.clicked.connect(apply_auto_lock)
        close_button.clicked.connect(dialog.accept)
        button_row = self._build_dialog_action_row(apply_button, close_button, width=140)
        layout.addWidget(title)
        layout.addWidget(QLabel("Set inactivity minutes before the app asks for sign-in again. Use 0 to disable."))
        layout.addWidget(minutes_input)
        layout.addStretch()
        layout.addLayout(button_row)
        self._finalize_tools_dialog(dialog)
        self._apply_clickable_cursors(dialog)
        dialog.exec()

    def show_keyboard_shortcuts_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Shortcut Keys")
        self._apply_standard_dialog_size(dialog, "standard")
        self._apply_tools_dialog_style(dialog)
        layout = QVBoxLayout()
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)
        dialog.setLayout(layout)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_container = QWidget()
        scroll_container.setAttribute(Qt.WA_StyledBackground, True)
        scroll_container.setStyleSheet(
            "background: #0f1a22;" if self._is_dark_theme_active() else "background: #f7fbfd;"
        )
        scroll_layout = QVBoxLayout()
        scroll_layout.setContentsMargins(0, 0, 6, 0)
        scroll_layout.setSpacing(12)
        scroll_container.setLayout(scroll_layout)

        title = QLabel("Shortcut Keys")
        title.setStyleSheet(
            f"font-size: 20px; font-weight: 700; color: {'#eef8fc' if self._is_dark_theme_active() else '#173543'};"
        )
        status_label = QLabel(f"Current status: {'Enabled' if self.keyboard_shortcuts_enabled else 'Disabled'}")
        status_label.setWordWrap(True)
        status_label.setStyleSheet(f"color: {'#d7e9f0' if self._is_dark_theme_active() else '#274652'};")
        info = QLabel(
            "Shortcuts:\n"
            "Ctrl+Shift+S = Start Camera\n"
            "Ctrl+Shift+X = Stop Camera\n"
            "Ctrl+Shift+V = Toggle Voice Control\n"
            "Ctrl+Shift+G = Toggle Gesture Control\n"
            "Ctrl+Shift+P = Toggle Practice Mode\n"
            "Ctrl+Shift+D = Toggle Dark Mode\n"
            "Ctrl+Shift+A = Toggle Auto Focus\n"
            "Ctrl+Shift+B = Toggle Sound Feedback\n"
            "Ctrl+Shift+O = Open Presentation\n"
            "Ctrl+Shift+F = Open Voice Feedback\n"
            "Ctrl+Shift+J = Open Gesture Profiles\n"
            "Ctrl+Shift+K = Open Shortcut Keys\n"
            "Ctrl+Shift+M = Open Microphone Settings\n"
            "Ctrl+Shift+H = Open Quick Help\n"
            "Ctrl+Shift+T = Open Presentation Timer\n"
            "Ctrl+Shift+U = Open Utility Menu\n"
            "Ctrl+Shift+W = Open Saved Sign-In Accounts\n"
            "Ctrl+Shift+L = Open Lock & Security\n"
            "Ctrl+Shift+E = Open Manage Users\n"
            "Ctrl+Shift+R = Open Reset Settings\n"
            "Ctrl+Shift+I = Open About VisionSlide\n"
            "Ctrl+Shift+N = Minimize App\n"
            "Ctrl+Shift+Q = Close App"
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color: {'#e7f3f8' if self._is_dark_theme_active() else '#274652'};")
        close_button = QPushButton("Close")
        close_button.clicked.connect(dialog.accept)
        scroll_layout.addWidget(title)
        scroll_layout.addWidget(status_label)
        scroll_layout.addWidget(info)
        scroll_layout.addStretch()
        scroll_area.setWidget(scroll_container)
        layout.addWidget(scroll_area, 1)
        layout.addWidget(close_button)
        self._finalize_tools_dialog(dialog)
        self._move_dialog_higher(dialog, y_offset=42)
        self._apply_clickable_cursors(dialog)
        dialog.exec()

    def show_tutorial_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Tutorial")
        self._apply_standard_dialog_size(dialog, "form")
        self._apply_tools_dialog_style(dialog)
        layout = QVBoxLayout()
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)
        dialog.setLayout(layout)
        title = QLabel("Tutorial")
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #173543;")
        content = QTextEdit()
        content.setReadOnly(True)
        content.setPlainText(
            "1. Sign in with a registered email and password.\n\n"
            "2. Start the camera to begin gesture tracking.\n\n"
            "3. Use Control or Jump mode depending on the presentation action you want.\n\n"
            "4. Enable Voice Control if you want spoken slide commands.\n\n"
            "5. Use Tools for presentation opening, history, timer, and other advanced features."
        )
        close_button = QPushButton("Close")
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(title)
        layout.addWidget(content)
        layout.addWidget(close_button)
        self._finalize_tools_dialog(dialog)
        self._apply_clickable_cursors(dialog)
        dialog.exec()

    def _show_tools_info_popup(self, title, message):
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        self._apply_standard_dialog_size(dialog, "standard")
        self._apply_tools_dialog_style(dialog)

        layout = QVBoxLayout()
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)
        dialog.setLayout(layout)

        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 20px; font-weight: 700; color: #173543;")
        message_label = QLabel(message)
        message_label.setWordWrap(True)
        message_label.setAlignment(Qt.AlignCenter)
        message_label.setStyleSheet("color: #5a7380; font-size: 13px;")

        ok_button = QPushButton("OK")
        ok_button.clicked.connect(dialog.accept)
        ok_button.setDefault(True)

        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(ok_button)
        button_row.addStretch()

        layout.addWidget(title_label)
        layout.addWidget(message_label)
        layout.addStretch()
        layout.addLayout(button_row)

        self._finalize_tools_dialog(dialog)
        self._apply_clickable_cursors(dialog)
        dialog.exec()

    def _apply_tools_dialog_style(self, dialog):
        dialog.setAttribute(Qt.WA_StyledBackground, True)
        dialog.setAutoFillBackground(True)
        dialog.setAttribute(Qt.WA_TranslucentBackground, False)
        dark_active = self._is_dark_theme_active()
        dialog.setProperty("skipFadeInTransition", dark_active)
        palette = dialog.palette()
        if dark_active:
            palette.setColor(QPalette.Window, QColor("#0f1a22"))
            palette.setColor(QPalette.Base, QColor("#132630"))
            palette.setColor(QPalette.Text, QColor("#e7f3f8"))
            palette.setColor(QPalette.WindowText, QColor("#e7f3f8"))
            palette.setColor(QPalette.Button, QColor("#183240"))
            palette.setColor(QPalette.ButtonText, QColor("#eaf6fb"))
        else:
            palette.setColor(QPalette.Window, QColor("#f7fbfd"))
            palette.setColor(QPalette.Base, QColor("#ffffff"))
            palette.setColor(QPalette.WindowText, QColor("#274652"))
        dialog.setPalette(palette)
        if dark_active:
            dialog.setStyleSheet(self._dark_dialog_override_stylesheet())
        else:
            dialog.setStyleSheet(
                "QDialog { background: #f7fbfd; }"
                "QLabel { color: #274652; font-size: 13px; }"
                "QListWidget, QTextEdit, QPlainTextEdit { "
                "background: #ffffff; border: 1px solid #d8e4ea; border-radius: 14px; "
                "color: #173543; padding: 6px; }"
                "QListWidget::item { padding: 8px 10px; }"
                "QListWidget::item:hover { background: #cfeaf4; color: #103647; border-radius: 10px; }"
                "QListWidget::item:selected { background: #d7ecf4; color: #12394b; border-radius: 10px; }"
                "QLineEdit, QComboBox, QSpinBox { "
                "min-height: 38px; border-radius: 12px; border: 1px solid #d8e4ea; "
                "background: #ffffff; color: #173543; padding: 6px 10px; }"
                "QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border-color: #4c8ea4; }"
                "QComboBox:hover, QSpinBox:hover, QLineEdit:hover { "
                "background: #cfeaf4; border-color: #4c8ea4; color: #103647; }"
                "QComboBox QAbstractItemView { "
                "background: #ffffff; color: #173543; border: 1px solid #d8e4ea; "
                "selection-background-color: #d7ecf4; selection-color: #12394b; }"
                "QCheckBox { color: #173543; font-size: 13px; font-weight: 600; spacing: 8px; }"
            )

    def _style_tools_button(self, button):
        if button is None:
            return
        button.setProperty("toolsItem", "true")
        button.setCursor(Qt.PointingHandCursor)
        button.setMouseTracking(True)
        button.setAttribute(Qt.WA_Hover, True)
        if not button.icon().isNull():
            button.setIconSize(QSize(16, 16))

        if self._is_dark_theme_active():
            button.setStyleSheet(
                "QPushButton {"
                "min-height: 38px;"
                "border-radius: 12px;"
                "border: 1px solid #42697c;"
                "background: rgba(255, 255, 255, 0.08);"
                "color: #eef8fc;"
                "padding: 8px 12px;"
                "text-align: center;"
                "font-size: 13px;"
                "font-weight: 700;"
                "}"
                "QPushButton:hover {"
                "background: rgba(255, 255, 255, 0.16);"
                "border-color: #5e8ea4;"
                "color: #ffffff;"
                "}"
                "QPushButton:pressed {"
                "background: rgba(255, 255, 255, 0.22);"
                "border-color: #74a7bc;"
                "color: #ffffff;"
                "}"
            )
        else:
            button.setStyleSheet(
                "QPushButton {"
                "min-height: 38px;"
                "border-radius: 12px;"
                "border: 1px solid #d8e4ea;"
                "background: #fdfefe;"
                "color: #173543;"
                "padding: 8px 12px;"
                "text-align: center;"
                "font-size: 13px;"
                "font-weight: 700;"
                "}"
                "QPushButton:hover {"
                "background: #cfeaf4;"
                "border-color: #4c8ea4;"
                "color: #103647;"
                "}"
                "QPushButton:pressed {"
                "background: #c1dfeb;"
                "border-color: #346b7d;"
                "color: #103444;"
                "}"
            )
        attach_hover_bounce(button, y_offset=3, duration=185)
        button.update()

    def _finalize_tools_dialog(self, dialog):
        self._apply_tools_dialog_style(dialog)
        for button in dialog.findChildren(QPushButton):
            if button.property("toolsStyleOverride") == "true":
                continue
            self._style_tools_button(button)

    def _show_tools_result_popup(self, title, message, success=True):
        self._show_security_result_popup(title, message, success=success)


        # Enable or disable gesture control
    def toggle_gesture_control(self, checked):
        self.config.set("gesture_enabled", checked)
        self._save_current_user_preferences()
        self._set_badge(
            self.status_value,
            "Gesture control enabled" if checked else "Gesture control disabled",
            "info",
        )

    def toggle_practice_mode_setting(self, checked):
        self.practice_mode_enabled = checked
        self.config.set("practice_mode", checked)
        self._save_current_user_preferences()
        self._set_badge(
            self.status_value,
            "Practice mode enabled" if checked else "Practice mode disabled",
            "info",
        )

    def toggle_keyboard_shortcuts_setting(self, checked):
        self.keyboard_shortcuts_enabled = checked
        self.config.set("keyboard_shortcuts_enabled", checked)
        self._update_keyboard_shortcuts()
        self._save_current_user_preferences()
        self._set_badge(self.status_value, "Keyboard shortcuts updated", "success")

    def toggle_sound_feedback_setting(self, checked):
        self.config.set("sound_enabled", checked)
        self.audio_feedback.set_enabled(bool(checked))
        self._save_current_user_preferences()
        self._set_badge(
            self.status_value,
            "Sound feedback enabled" if checked else "Sound feedback disabled",
            "info",
        )

         # Enable or disable voice control using the already selected startup microphone
    def toggle_voice_control(self, checked):
        if checked:
            self._set_badge(self.status_value, "Voice control enabling...", "info")
            self._set_footer_state(voice_text="Voice: Starting")
            QApplication.processEvents()
            self.refresh_microphone_list(show_status=False)
            selected_mic = self._resolve_runtime_voice_device_name()
            if not selected_mic:
                self.config.set("voice_enabled", False)
                self.voice_checkbox.blockSignals(True)
                self.voice_checkbox.setChecked(False)
                self.voice_checkbox.blockSignals(False)
                self._set_badge(
                    self.status_value,
                    "No microphone device available",
                    "danger",
                )
                self._set_footer_state(voice_text="Voice: Mic not found")
                return

            combo_index = self.voice_device_input.findText(selected_mic, Qt.MatchExactly)
            if combo_index >= 0:
                self.voice_device_input.setCurrentIndex(combo_index)
            self.config.set("voice_device_name", selected_mic)
            self.voice_listener.device_name = selected_mic

            voice_started = self.voice_listener.start()
            if not voice_started and selected_mic == "Default System Microphone":
                real_devices = self._available_voice_device_names()[1:]
                preferred_device = self.get_preferred_voice_device_name(real_devices)
                retry_devices = []
                if preferred_device:
                    retry_devices.append(preferred_device)
                retry_devices.extend(device for device in real_devices if device not in retry_devices)

                for retry_mic in retry_devices:
                    self.voice_listener.device_name = retry_mic
                    if self.voice_listener.start():
                        selected_mic = retry_mic
                        combo_index = self.voice_device_input.findText(selected_mic, Qt.MatchExactly)
                        if combo_index >= 0:
                            self.voice_device_input.setCurrentIndex(combo_index)
                        self.config.set("voice_device_name", selected_mic)
                        voice_started = True
                        break

            if not voice_started:
                self.config.set("voice_enabled", False)
                self.voice_checkbox.blockSignals(True)
                self.voice_checkbox.setChecked(False)
                self.voice_checkbox.blockSignals(False)
                self._set_badge(
                    self.status_value,
                    "Mic open failed",
                    "danger",
                )
                self._set_footer_state(voice_text="Voice: Mic error")
                return
            self._set_badge(self.status_value, "Voice control enabled", "success")
            self._set_footer_state(voice_text="Voice: Listening")
        else:
            self.voice_listener.stop()
            self._set_badge(self.status_value, "Voice control disabled", "muted")
            self._set_footer_state(voice_text="Voice: Off")

        self.config.set("voice_enabled", checked)
        self._save_current_user_preferences()

    def test_microphone(self):
        selected_mic = self._selected_voice_device_name()
        if not selected_mic:
            QMessageBox.warning(
                self,
                "Microphone Test",
                "No microphone selected for testing.",
            )
            return

        self.voice_test_button.setEnabled(False)
        self._set_badge(self.status_value, "Testing microphone...", "info")

        temp_listener = VoiceListener(
            model_path=self.voice_listener.model_path,
            device_name=selected_mic,
            on_command=lambda _: None,
        )
        success = temp_listener.test_input_device()

        self.voice_test_button.setEnabled(True)

        if success:
            self._set_badge(self.status_value, "Microphone test passed", "success")
            QMessageBox.information(
                self,
                "Microphone Test",
                f"ÃƒÂ¢Ã…â€œÃ¢â‚¬Å“ Microphone test passed!\n\nDevice: {selected_mic}\n\nThe microphone is working and ready for voice control.",
            )
        else:
            self._set_badge(self.status_value, "Microphone test failed", "danger")
            QMessageBox.warning(
                self,
                "Microphone Test",
                f"ÃƒÂ¢Ã…â€œÃ¢â‚¬â€ Microphone test failed!\n\nDevice: {selected_mic}\n\nThis microphone could not be opened. Please select a different input device or check your audio settings.",
            )

    def refresh_microphone_list(self, show_status=True):
        """Refresh the microphone device list"""
        current_selection = self.voice_device_input.currentText()
        saved_selection = str(self.config.get("voice_device_name") or "").strip()

        if show_status:
            self._set_badge(self.status_value, "Refreshing microphone list...", "info")

        # Get updated list of microphones
        voice_device_names = ["Default System Microphone"] + self.device_manager.get_microphone_devices()

        # Clear and repopulate the combo box
        self.voice_device_input.clear()
        self.voice_device_input.addItems(voice_device_names)

        # Try to restore the previous selection
        if current_selection and current_selection in voice_device_names:
            self.voice_device_input.setCurrentText(current_selection)
        elif saved_selection and saved_selection in voice_device_names:
            self.voice_device_input.setCurrentText(saved_selection)
        elif voice_device_names:
            # Default to first available if current selection is gone
            self.voice_device_input.setCurrentIndex(0)

        self.voice_test_button.setEnabled(bool(voice_device_names))

        device_count = len(voice_device_names) - 1  # Subtract 1 for "Default System Microphone"
        if not show_status:
            return

        if device_count > 0:
            self._set_badge(self.status_value, f"Found {device_count} microphone(s)", "success")
        else:
            self._set_badge(self.status_value, "No microphones found", "warning")

    def _available_voice_device_names(self):
        return ["Default System Microphone"] + self.device_manager.get_microphone_devices()

    def _resolve_runtime_voice_device_name(self):
        available_devices = self._available_voice_device_names()
        if not available_devices:
            return None

        saved_device = sanitize_voice_device_name(
            self.config.get("voice_device_name"),
            allowed_devices=available_devices,
            default="Default System Microphone",
        )
        if saved_device in available_devices:
            return saved_device

        current_combo_device = str(self.voice_device_input.currentText() or "").strip()
        if current_combo_device in available_devices:
            return current_combo_device

        preferred_device = self.get_preferred_voice_device_name(
            available_devices[1:] if len(available_devices) > 1 else []
        )
        if preferred_device and preferred_device in available_devices:
            return preferred_device

        return "Default System Microphone" if "Default System Microphone" in available_devices else available_devices[0]

    def toggle_theme(self, checked):
        self.dark_mode = checked
        if checked:
            # Professional dark mode stylesheet
            dark_css = """
            QMainWindow {
                background: #0f1a22;
            }
            QWidget {
                font-family: "Segoe UI";
                color: #e7f3f8;
            }
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                background: #2a2a2a;
                width: 12px;
                margin: 8px 2px 8px 0;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background: #555555;
                border-radius: 6px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background: #666666;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical,
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {
                background: transparent;
                height: 0;
            }
            QGroupBox {
                font-size: 12px;
                font-weight: 700;
                color: #deedf4;
                border: 1px solid #385968;
                border-radius: 18px;
                margin-top: 14px;
                padding: 18px 16px 16px 16px;
                background: #142833;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 14px;
                padding: 0 8px;
                color: #9fc5d6;
                background: #1a3240;
            }
            QLabel {
                font-size: 13px;
                color: #d7e9f0;
            }
            QLabel[stateBadge="true"] {
                background: #1a3240;
                border: 1px solid #3b6070;
                border-radius: 11px;
                padding: 8px 12px;
                color: #eef8fc;
                font-weight: 600;
            }
            QLabel[emphasis="strong"] {
                font-size: 14px;
                font-weight: 700;
                padding: 10px 12px;
                color: #ffffff;
            }
            QLabel[tone="info"] {
                background: #2a4a5a;
                border-color: #4a6a7a;
                color: #b0d0e0;
            }
            QLabel[tone="success"] {
                background: #2a4a2a;
                border-color: #4a6a4a;
                color: #90c090;
            }
            QLabel[tone="warning"] {
                background: #4a4a2a;
                border-color: #6a6a4a;
                color: #e0d090;
            }
            QLabel[tone="danger"] {
                background: #4a2a2a;
                border-color: #6a4a4a;
                color: #e09090;
            }
            QLabel[tone="muted"] {
                background: #1a3240;
                border-color: #355868;
                color: #a9c3cf;
            }
            QPushButton {
                min-height: 42px;
                border-radius: 14px;
                border: 1px solid #3c6273;
                background: #183240;
                color: #eaf6fb;
                padding: 8px 14px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #214353;
                border-color: #5c8aa0;
                color: #ffffff;
            }
            QPushButton:pressed {
                background: #122733;
                border-color: #305465;
            }
            QPushButton[variant="danger"] {
                background: #4a2a2a;
                color: #e09090;
                border: 1px solid #6a4a4a;
            }
            QPushButton[variant="danger"]:hover {
                background: #5a3a3a;
                color: #f0a0a0;
            }
            QPushButton[modeActive="true"] {
                background: #2a4a4a;
                border: 1px solid #4a6a6a;
                color: #90c0c0;
            }
            QPushButton[textLink="true"] {
                min-height: 0px;
                min-width: 0px;
                padding: 0px;
                border: none;
                background: transparent;
                color: #87ceeb;
                font-size: 13px;
                font-weight: 700;
            }
            QPushButton[textLink="true"]:hover {
                background: transparent;
                border: none;
                color: #add8e6;
                text-decoration: underline;
            }
            QPushButton[textLink="true"]:disabled {
                background: transparent;
                border: none;
                color: #666666;
            }
            QPushButton[smallAction="true"] {
                min-height: 34px;
                min-width: 120px;
                padding: 6px 12px;
                font-size: 12px;
                background: #183240;
                border: 1px solid #3c6273;
                color: #eaf6fb;
            }
            QPushButton[smallAction="true"][buttonGroupHover="true"],
            QPushButton[smallAction="true"]:hover {
                background: #214353;
                border-color: #5c8aa0;
                color: #ffffff;
            }
            QComboBox {
                min-height: 36px;
                border-radius: 12px;
                border: 1px solid #3c6273;
                background: #16303d;
                padding: 4px 10px;
                color: #e7f3f8;
            }
            QSpinBox,
            QDoubleSpinBox {
                border-radius: 12px;
                border: 1px solid #3c6273;
                background: #16303d;
                padding: 4px 10px;
                color: #e7f3f8;
            }
            QComboBox:hover {
                border-color: #5b8aa0;
                background: #1e3d4c;
                color: #ffffff;
            }
            QSpinBox:hover,
            QDoubleSpinBox:hover {
                border-color: #5b8aa0;
                background: #1e3d4c;
                color: #ffffff;
            }
            QComboBox QAbstractItemView {
                border: 1px solid #3c6273;
                outline: 0;
                background: #142833;
                color: #e7f3f8;
                selection-background-color: #24506a;
                selection-color: #ffffff;
            }
            QComboBox#mic_combo {
                min-height: 36px;
                border-radius: 12px 0 0 12px;
                border: 1px solid #666666;
                background: #3a3a3a;
                padding: 0 10px;
                color: #e0e0e0;
            }
            QComboBox#mic_combo:hover {
                border-color: #777777;
                background: #4a4a4a;
                color: #ffffff;
            }
            QComboBox#mic_combo::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 34px;
                border-left: 1px solid #666666;
                background: transparent;
            }
            QComboBox#mic_combo::down-arrow {
                image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 10 6'><polygon points='0,0 10,0 5,6' fill='%23e0e0e0'/></svg>");
                width: 10px;
                height: 6px;
            }
            QComboBox#mic_combo::down-arrow:on {
                top: 1px;
            }
            QComboBox#mic_combo QAbstractItemView {
                border: 1px solid #666666;
                outline: 0;
                background: #3a3a3a;
                selection-background-color: #4a4a4a;
                selection-color: #ffffff;
            }
            QComboBox#mic_combo::item:hover {
                background: #4a4a4a;
                color: #ffffff;
            }
            QPushButton#mic_refresh {
                min-width: 38px;
                min-height: 36px;
                border-radius: 0 12px 12px 0;
                border: 1px solid #666666;
                border-left: none;
                background: #3a3a3a;
                color: #e0e0e0;
                padding: 4px;
            }
            QPushButton#mic_refresh:hover {
                background: #4a4a4a;
                border-color: #777777;
                color: #ffffff;
            }
            QPushButton#mic_refresh:pressed {
                background: #5a5a5a;
            }
            QPushButton#mic_refresh:hover {
                background: #4a4a4a;
                border-color: #777777;
                color: #ffffff;
            }
            QCheckBox {
                spacing: 10px;
                color: #deedf4;
                font-weight: 500;
            }
            QCheckBox:hover {
                color: #ffffff;
                background: #1f3d4b;
                border-radius: 10px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 1px solid #4b7284;
                background: #16303d;
                border-radius: 3px;
            }
            QCheckBox::indicator:checked {
                background: #24506a;
                image: url(data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTIiIGhlaWdodD0iMTIiIHZpZXdCb3g9IjAgMCAxMiAxMiIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPHBhdGggZD0iTTEwIDNMNCA5IDMgOCIgc3Ryb2tlPSIjZmZmZmZmIiBzdHJva2Utd2lkdGg9IjIiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCIvPgo8L3N2Zz4=);
            }
            QFrame#cameraCard {
                background: #132630;
                border: 1px solid #355768;
                border-radius: 28px;
            }
            QLabel[sectionNote="true"] {
                background: #17303b;
                border: 1px solid #355768;
                border-radius: 14px;
                padding: 10px 12px;
                color: #d2e5ee;
                font-size: 12px;
            }
            QLabel[securityValue="true"] {
                background: #17303b;
                border: 1px solid #355768;
                border-radius: 12px;
                padding: 8px 12px;
                color: #e7f3f8;
                font-weight: 600;
            }
            QLabel[securityMessage="error"] {
                color: #cd5c5c;
                font-size: 11px;
                font-weight: 600;
                padding-left: 4px;
            }
            QLabel[securityMessage="success"] {
                color: #8fbc8f;
                font-size: 11px;
                font-weight: 600;
                padding-left: 4px;
            }
            QLabel[securityMessage="neutral"] {
                color: #aaa;
                font-size: 11px;
                font-weight: 600;
                padding-left: 4px;
            }
            QLabel#cameraSubtext {
                color: #aaa;
                font-size: 12px;
            }
            QLineEdit {
                min-height: 52px;
                border-radius: 14px;
                border: 1px solid #3c6273;
                background: #16303d;
                padding: 6px 12px;
                color: #e7f3f8;
                font-size: 13px;
            }
            QLineEdit:focus {
                border-color: #5c8aa0;
                background: #1e3d4c;
                color: #ffffff;
            }
            QLineEdit[validationState="error"] {
                border: 1px solid #e09090;
                background: #4a2a2a;
            }
            QLineEdit[validationState="success"] {
                border: 1px solid #90c090;
                background: #2a4a2a;
            }
            QFrame#footerStrip {
                background: #17303b;
                border: 1px solid #355768;
                border-radius: 16px;
            }
            QLabel[footerLabel="true"] {
                color: #e7f3f8;
                font-size: 12px;
                font-weight: 700;
                background: #214150;
                border: 1px solid #42697c;
                border-radius: 12px;
                padding: 6px 12px;
            }
            QLabel#footerInfoLabel {
                color: #d8eaf2;
                font-size: 11px;
                font-weight: 600;
                background: #1a3441;
                border: 1px solid #42697c;
                border-radius: 12px;
                padding: 6px 10px;
            }
            QSplitter::handle {
                background: transparent;
                width: 10px;
            }
            QToolButton[sectionToggle="true"] {
                min-height: 38px;
                border-radius: 14px;
                border: 1px solid #42697c;
                background: #1a3441;
                color: #eef8fc;
                font-size: 13px;
                font-weight: 700;
                padding: 6px 12px;
                text-align: left;
            }
            QToolButton[sectionToggle="true"]:hover {
                background: #224454;
                border-color: #5e8ea4;
                color: #ffffff;
            }
            QToolButton[utilityMenuButton="true"] {
                min-height: 40px;
                min-width: 40px;
                background: #17303b;
                border: 1px solid #355768;
                border-radius: 8px;
            }
            QToolButton[utilityMenuButton="true"]:hover {
                background: #214150;
                border-color: #4f7a8d;
            }
            QToolTip {
                background: #17303b;
                color: #d8eaf2;
                border: 1px solid #42697c;
                border-radius: 12px;
                padding: 6px 10px;
                font-size: 11px;
                font-weight: 600;
            }
            QLabel#sidebarInfoLabel {
                color: #d8eaf2;
                font-size: 11px;
                font-weight: 600;
                background: #17303b;
                border: 1px solid #42697c;
                border-radius: 12px;
                padding: 6px 10px;
            }
            QFrame#utilityMenuPanel {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #122631, stop:1 #1a3441);
                border: 1px solid #355768;
                border-radius: 22px;
            }
            QFrame#utilityMenuPanel[utilityAccent="true"] {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #16303d, stop:1 #214150);
                border: 1px solid #42697c;
                border-radius: 22px;
            }
            QFrame#utilityUserCard {
                background: rgba(255, 255, 255, 0.08);
                border: none;
                border-radius: 14px;
            }
            QLabel[utilityMenuTitle="true"] {
                color: #eef8fc;
                font-size: 16px;
                font-weight: 700;
            }
            QLabel[utilityHeaderIcon="true"] {
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid #42697c;
                border-radius: 14px;
                color: #eef8fc;
                font-size: 14px;
                font-weight: 800;
                min-width: 28px;
                max-width: 28px;
                min-height: 28px;
                max-height: 28px;
                padding: 0px;
            }
            QLabel[utilityUserName="true"] {
                color: #eef8fc;
                font-size: 12px;
                font-weight: 700;
            }
            QLabel[utilityUserEmail="true"] {
                color: #b5ccd7;
                font-size: 11px;
            }
            QPushButton[utilityItem="true"] {
                min-height: 34px;
                min-width: 0px;
                border-radius: 10px;
                border: 1px solid #42697c;
                background: rgba(255, 255, 255, 0.08);
                color: #eef8fc;
                padding: 6px 11px;
                text-align: left;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton[utilityItem="true"]:hover {
                background: rgba(255, 255, 255, 0.16);
                border-color: #5e8ea4;
                color: #ffffff;
            }
            """
            self.setStyleSheet(dark_css)
            self.side_panel.setStyleSheet(
                "#sidePanel {"
                "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #132833, stop:1 #1b3643);"
                "border: 1px solid #355768;"
                "border-radius: 28px;"
                "}"
            )
            self._apply_header_branding()
            for spinbox in [self.control_hold_input, self.jump_hold_input]:
                spinbox.setStyleSheet(
                    "QSpinBox, QDoubleSpinBox {"
                    "border: 1px solid #3c6273;"
                    "background: #16303d;"
                    "color: #e7f3f8;"
                    "border-radius: 12px;"
                    "padding: 4px 10px;"
                    "}"
                    "QSpinBox:hover, QDoubleSpinBox:hover {"
                    "border-color: #5b8aa0;"
                    "background: #1e3d4c;"
                    "color: #ffffff;"
                    "}"
                )
        else:
            self.setStyleSheet(self.light_stylesheet)
            self.side_panel.setStyleSheet(
                "#sidePanel {"
                "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #e2edf2, stop:1 #c8dde6);"
                "border: 1px solid #b6ccd6;"
                "border-radius: 28px;"
                "}"
            )
            self._apply_header_branding()
            for spinbox in [self.control_hold_input, self.jump_hold_input]:
                spinbox.setStyleSheet("")
        self._apply_camera_preview_theme()
        self._apply_mode_value_theme()
        self._apply_sidebar_surface_theme()
        if getattr(self.camera_manager, "cap", None) is None or not self.timer.isActive():
            current_camera_text = getattr(self.camera_state_badge, "text", lambda: "Stopped")()
            if "unavailable" in current_camera_text.lower():
                self._set_camera_empty_state("Camera unavailable", "Check your camera connection or selected device.")
            elif "running" not in current_camera_text.lower():
                self._set_camera_empty_state("Camera stopped", "Press Start Camera to begin tracking again.")
        for tools_button in [
            getattr(self, "open_presentation_button", None),
            getattr(self, "voice_feedback_button", None),
            getattr(self, "custom_voice_commands_button", None),
            getattr(self, "custom_gesture_actions_button", None),
            getattr(self, "practice_mode_button", None),
            getattr(self, "recent_files_button", None),
            getattr(self, "command_history_button", None),
            getattr(self, "admin_activity_log_button", None),
            getattr(self, "user_preferences_button", None),
            getattr(self, "presentation_timer_button", None),
            getattr(self, "gesture_profiles_button", None),
            getattr(self, "keyboard_shortcuts_button", None),
        ]:
            if tools_button is not None:
                self._style_tools_button(tools_button)
        self._save_current_user_preferences()
        self._set_badge(self.status_value, "Dark mode enabled" if checked else "Dark mode disabled", "info")



        # Save the selected microphone name only
    def change_voice_device_name(self, device_name):
        self.refresh_microphone_list(show_status=False)
        allowed_devices = self._available_voice_device_names()
        self.voice_device_input.clear()
        self.voice_device_input.addItems(allowed_devices)
        validated_name = sanitize_voice_device_name(
            device_name,
            allowed_devices=allowed_devices,
            default=self._resolve_runtime_voice_device_name() or self.config.get("voice_device_name"),
        )

        if validated_name not in allowed_devices and allowed_devices:
            validated_name = allowed_devices[0]

        if validated_name != device_name:
            restored_index = self.voice_device_input.findText(validated_name)
            if restored_index >= 0:
                self.voice_device_input.setCurrentIndex(restored_index)
            self._set_badge(self.status_value, "Invalid microphone selection blocked", "warning")
            return

        previous_device = self.config.get("voice_device_name")
        self.config.set("voice_device_name", validated_name)
        self.voice_listener.device_name = validated_name
        self._save_current_user_preferences()

        if self.voice_checkbox.isChecked():
            if not self.voice_listener.start():
                self.config.set("voice_device_name", previous_device)
                self.voice_listener.device_name = previous_device
                restore_index = self.voice_device_input.findText(previous_device)
                if restore_index >= 0:
                    self.voice_device_input.setCurrentIndex(restore_index)
                if previous_device:
                    self.voice_listener.start()
                self._set_badge(
                    self.status_value,
                    "Microphone could not be opened; restored previous microphone.",
                    "warning",
                )
    # Convert spoken number words into an integer slide number
    def parse_spoken_slide_number(self, command_text):
        return self._resolve_spoken_number_value(command_text)




        # Handle recognized voice commands and map them to slide actions
    def handle_voice_command(self, command_text):
        print(f"DEBUG: Voice command received: '{command_text}'")
        sidebar_vertical = None
        sidebar_horizontal = None
        if hasattr(self, "sidebar_scroll") and self.sidebar_scroll is not None:
            sidebar_vertical = self.sidebar_scroll.verticalScrollBar().value()
            sidebar_horizontal = self.sidebar_scroll.horizontalScrollBar().value()

        try:
            resolved_action = self._resolve_voice_action(command_text)
            resolved_slide_number = None if resolved_action is not None else self._resolve_jump_voice_command(command_text)

            if resolved_action is None and resolved_slide_number is None:
                print(f"DEBUG: Ignoring unsupported voice phrase: '{command_text}'")
                return

            display_voice_text = self._canonical_voice_display_text(
                command_text,
                resolved_action=resolved_action,
                resolved_slide_number=resolved_slide_number,
            )
            self._set_badge(self.voice_value, display_voice_text, "info")
            self._set_footer_state(voice_text="Voice: Command received")

            if resolved_action == "next":
                print("DEBUG: Executing next slide")
                self._execute_presentation_action(
                    "Next Slide",
                    self.slide_controller.next_slide,
                    "Voice",
                    command_text,
                    success_tone="success",
                    failure_tone="danger",
                )
                return

            if resolved_action == "previous":
                print("DEBUG: Executing previous slide")
                self._execute_presentation_action(
                    "Previous Slide",
                    self.slide_controller.previous_slide,
                    "Voice",
                    command_text,
                    success_tone="success",
                    failure_tone="danger",
                )
                return

            if resolved_action == "start":
                print("DEBUG: Executing start slideshow")
                self._execute_presentation_action(
                    "Start Slideshow",
                    self.slide_controller.start_slideshow,
                    "Voice",
                    command_text,
                    success_tone="success",
                    failure_tone="danger",
                )
                return

            if resolved_action == "exit":
                print("DEBUG: Executing exit slideshow")
                self._execute_presentation_action(
                    "Exit Slideshow",
                    self.slide_controller.exit_slideshow,
                    "Voice",
                    command_text,
                    success_tone="warning",
                    failure_tone="danger",
                )
                return

            if resolved_action == "first":
                print("DEBUG: Executing jump to first slide")
                self._execute_presentation_action(
                    "Jump to First Slide",
                    lambda: self.slide_controller.jump_to_slide(1),
                    "Voice",
                    command_text,
                )
                return

            if resolved_action == "last":
                print("DEBUG: Executing jump to last slide")
                last_slide = self.config.get("total_slides")
                self._execute_presentation_action(
                    "Jump to Last Slide",
                    lambda: self.slide_controller.jump_to_slide(last_slide),
                    "Voice",
                    command_text,
                )
                return

            slide_number = resolved_slide_number
            if slide_number is not None:
                print(f"DEBUG: Executing jump to slide {slide_number}")
                self._execute_presentation_action(
                    f"Jump to Slide {slide_number}",
                    lambda: self.slide_controller.jump_to_slide(slide_number),
                    "Voice",
                    command_text,
                )
                return
            print(f"DEBUG: Unrecognized voice command: '{command_text}'")
        finally:
            if (
                sidebar_vertical is not None
                and sidebar_horizontal is not None
                and hasattr(self, "sidebar_scroll")
                and self.sidebar_scroll is not None
            ):
                self.sidebar_scroll.verticalScrollBar().setValue(sidebar_vertical)
                self.sidebar_scroll.horizontalScrollBar().setValue(sidebar_horizontal)




    def start_camera(self):
        self.camera_manager.start()
        self.timer.start(30)
        self._sync_camera_buttons(True)
        self._set_badge(self.camera_state_badge, "Running", "success")
        self._set_recent_activity("Camera started", "success")
        self._set_camera_empty_state("Starting camera...", "Show your hand clearly in the frame to begin recognition.")
        self._set_footer_state(camera_text="Camera: Running")

    def stop_camera(self):
        self.timer.stop()
        self.camera_manager.stop()
        self._sync_camera_buttons(False)
        self._set_badge(self.camera_state_badge, "Stopped", "warning")
        self._set_camera_empty_state("Camera stopped", "Press Start Camera to begin tracking again.")
        self._set_recent_activity("Camera stopped", "warning")
        self._set_badge(self.gesture_value, "None", "muted")
        self._set_badge(self.action_value, "None", "muted")
        self._set_badge(self.voice_value, "None", "muted")
        self._set_footer_state(camera_text="")


    def update_frame(self):
        frame = self.camera_manager.read_frame()
        if frame is None:
            self._sync_camera_buttons(False)
            self._set_badge(self.camera_state_badge, "Unavailable", "danger")
            self._set_recent_activity("Camera unavailable", "danger")
            self._set_camera_empty_state("Camera unavailable", "Check your camera connection or selected device.")
            self._set_footer_state(camera_text="Camera: Error")
            return

        try:
            processed_frame, result = self.hand_detector.process_frame(
            frame.copy(),
            int(time.monotonic() * 1000),
         )

            hand_landmarks_list = getattr(result, "hand_landmarks", [])

            if hand_landmarks_list:
                for landmarks in hand_landmarks_list:
                    self.draw_landmarks(processed_frame, landmarks)

                if self.config.get("gesture_enabled"):
                    if self.current_mode == AppState.CONTROL_MODE:
                     self.handle_control_mode(hand_landmarks_list)
                    else:
                     self.handle_jump_mode(hand_landmarks_list)
                else:
                  self._set_badge(self.gesture_value, "Gesture control disabled", "warning")

            else:
                self._set_badge(self.gesture_value, "None", "muted")
                self._set_badge(self.action_value, "None", "muted")
                self.last_control_gesture = None
                self.control_gesture_frames = 0
                self.last_jump_count = None


            display_frame = processed_frame

        except Exception as error:
            self._set_recent_activity("Detection error", "danger")
            self._set_badge(self.gesture_value, "Error", "danger")
            self._set_badge(self.action_value, str(error), "danger")
            self._set_footer_state(camera_text="Camera: Detection error")
            display_frame = frame

        if self.show_camera_overlays:
            overlay_lines = [
                f"Mode: {self.current_mode.title()}",
                f"Gesture: {self.gesture_value.text()}",
                f"Action: {self.action_value.text()}",
            ]
            if self.practice_mode_enabled:
                overlay_lines.append("Practice Mode Active")
            for index, overlay_text in enumerate(overlay_lines):
                cv2.putText(
                    display_frame,
                    overlay_text,
                    (20, 30 + (index * 28)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (24, 74, 98),
                    2,
                    cv2.LINE_AA,
                )

        display_frame = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)

        height, width, channel = display_frame.shape
        bytes_per_line = channel * width
        image = QImage(
            display_frame.data,
            width,
            height,
            bytes_per_line,
            QImage.Format_RGB888,
        )

        pixmap = QPixmap.fromImage(image)
        self.camera_label.setPixmap(
            pixmap.scaled(
                self.camera_label.width(),
                self.camera_label.height(),
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation,
            )
        )


    def handle_control_mode(self, hand_landmarks_list):
        landmarks = hand_landmarks_list[0]
        gesture_name = self.gesture_classifier.classify(landmarks)
        self._set_badge(
            self.gesture_value,
            gesture_name,
            "muted" if gesture_name in ["None", "Unknown", "No gesture"] else "info",
        )

        # Count how many frames in a row the same control gesture appears
        if gesture_name == self.last_control_gesture:
            self.control_gesture_frames += 1
        else:
            self.last_control_gesture = gesture_name
            self.control_gesture_frames = 1

        # For valid control gestures, require a small stable hold
        valid_control_gestures = {"Two Fingers", "One Finger", "Open Palm", "Fist"}


        if gesture_name in valid_control_gestures:
            if self.control_gesture_frames < self.control_hold_frames:
                self._set_badge(
                    self.action_value,
                    f"Hold {gesture_name} ({self.control_gesture_frames}/{self.control_hold_frames})",
                    "warning",
                )
                return

        if gesture_name in valid_control_gestures:
            self._execute_custom_gesture_action(gesture_name)
            return

        # Only beep for unknown if it stays unknown for a few frames
        if gesture_name == "Unknown":
            if self.control_gesture_frames >= self.control_hold_frames:
                self._set_badge(self.action_value, "Gesture Not Recognized", "warning")
                self._record_command_history("Gesture", gesture_name, "Gesture Not Recognized", False)
                if self.cooldown_manager.can_trigger("unrecognized_gesture"):
                    self._play_command_feedback("unknown")
            return

        self._set_badge(self.action_value, "None", "muted")





    def handle_jump_mode(self, hand_landmarks_list):
        primary_gesture = self.gesture_classifier.classify(hand_landmarks_list[0])

        total_fingers = 0

        for landmarks in hand_landmarks_list:
            total_fingers += self.count_raised_fingers(landmarks)

        if total_fingers < 1 or total_fingers > 10:
            self._set_badge(self.gesture_value, "Show Fingers Only", "warning")
            self._set_badge(self.action_value, "Gesture Not Recognized", "warning")
            self._record_command_history("Gesture", str(total_fingers), "Gesture Not Recognized", False)
            if self.cooldown_manager.can_trigger("unrecognized_gesture"):
                self._play_command_feedback("unknown")
            self.last_jump_count = None
            return

        gesture_label = self.get_finger_count_label(total_fingers)
        self._set_badge(self.gesture_value, gesture_label, "info")

        now = time.time()

        if self.last_jump_count != total_fingers:
            self.last_jump_count = total_fingers
            self.last_jump_seen_at = now
            self._set_badge(self.action_value, f"Hold for Slide {total_fingers}", "warning")
            return

        if (now - self.last_jump_seen_at) >= self.jump_hold_seconds:
            if self.cooldown_manager.can_trigger(f"jump_{total_fingers}"):
                self._execute_presentation_action(
                    f"Jump to Slide {total_fingers}",
                    lambda: self.slide_controller.jump_to_slide(total_fingers),
                    "Gesture",
                    gesture_label,
                )






    def count_raised_fingers(self, landmarks):
        count = 0

        # Use palm width to make thumb detection relative to hand size
        index_mcp = landmarks[5]
        pinky_mcp = landmarks[17]
        thumb_tip = landmarks[4]

        palm_left = min(index_mcp.x, pinky_mcp.x)
        palm_right = max(index_mcp.x, pinky_mcp.x)
        palm_width = palm_right - palm_left
        thumb_margin = max(0.045, palm_width * 0.50)


        # Count thumb only if it is clearly outside the palm span
        if (
            thumb_tip.x < palm_left - thumb_margin
            or thumb_tip.x > palm_right + thumb_margin
        ):
            count += 1

        # Index finger
        if landmarks[8].y < landmarks[6].y:
            count += 1

        # Middle finger
        if landmarks[12].y < landmarks[10].y:
            count += 1

        # Ring finger
        if landmarks[16].y < landmarks[14].y:
            count += 1

        # Pinky finger
        if landmarks[20].y < landmarks[18].y:
            count += 1

        return count

    def get_finger_count_label(self, total_fingers):
        count_names = {
            1: "One Finger",
            2: "Two Fingers",
            3: "Three Fingers",
            4: "Four Fingers",
            5: "Five Fingers",
            6: "Six Fingers",
            7: "Seven Fingers",
            8: "Eight Fingers",
            9: "Nine Fingers",
            10: "Ten Fingers",
        }

        return count_names.get(total_fingers, f"{total_fingers} Fingers")





    def draw_landmarks(self, frame, landmarks):
        height, width, _ = frame.shape
        points = []

        for landmark in landmarks:
            x = int(landmark.x * width)
            y = int(landmark.y * height)
            points.append((x, y))
            cv2.circle(frame, (x, y), 5, (0, 255, 0), -1)

        for start_idx, end_idx in HAND_CONNECTIONS:
            start_point = points[start_idx]
            end_point = points[end_idx]
            cv2.line(frame, start_point, end_point, (255, 0, 0), 2)

    def closeEvent(self, event):
        self.stop_camera()
        self.hand_detector.close()
        self.voice_listener.stop()
        event.accept()


