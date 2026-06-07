from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QEvent, QObject, Property, QPropertyAnimation, QRect, QTimer, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget


class HoverTintOverlay(QWidget):
    def __init__(self, parent: QWidget, color: QColor | None = None):
        super().__init__(parent)
        self._opacity = 0.0
        self._color = color or QColor(220, 239, 248)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.hide()

    def _get_opacity(self) -> float:
        return self._opacity

    def _set_opacity(self, value: float) -> None:
        self._opacity = max(0.0, min(1.0, float(value)))
        if self._opacity <= 0.0:
            self.hide()
        else:
            self.show()
        self.update()

    opacity = Property(float, _get_opacity, _set_opacity)

    def sync_geometry(self) -> None:
        self.setGeometry(self.parentWidget().rect())
        self.raise_()

    def paintEvent(self, event):
        from PySide6.QtGui import QPainter

        if self._opacity <= 0.0:
            return
        painter = QPainter(self)
        color = QColor(self._color)
        color.setAlphaF(min(1.0, 0.18 * self._opacity))
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 10, 10)


class HoverLiftFilter(QObject):
    def __init__(self, target: QWidget, y_offset: int = 3, duration: int = 180):
        super().__init__(target)
        self._target = target
        self._y_offset = y_offset
        self._duration = duration
        self._hovered = False
        self._rest_geometry = QRect(target.geometry())
        self._hover_geometry = QRect(self._rest_geometry)
        self._hover_geometry.translate(0, -self._y_offset)

        self._animation = QPropertyAnimation(target, b"geometry", self)
        self._animation.setDuration(duration)
        self._animation.setEasingCurve(QEasingCurve.OutCubic)
        self._animation.finished.connect(self._finalize_geometry)

        self._overlay = HoverTintOverlay(target)
        self._overlay_animation = QPropertyAnimation(self._overlay, b"opacity", self)
        self._overlay_animation.setDuration(duration)
        self._overlay_animation.setEasingCurve(QEasingCurve.OutCubic)

    def _sync_rest_geometry(self) -> None:
        self._rest_geometry = QRect(self._target.geometry())
        self._hover_geometry = QRect(self._rest_geometry)
        self._hover_geometry.translate(0, -self._y_offset)

    def _animate_to(self, geometry: QRect) -> None:
        if not self._target.isVisible():
            return
        self._animation.stop()
        self._animation.setDuration(self._duration)
        self._animation.setStartValue(self._target.geometry())
        self._animation.setEndValue(geometry)
        self._animation.start()

    def _animate_overlay_to(self, opacity: float) -> None:
        self._overlay.sync_geometry()
        self._overlay_animation.stop()
        self._overlay_animation.setStartValue(self._overlay.opacity)
        self._overlay_animation.setEndValue(opacity)
        self._overlay_animation.start()

    def _finalize_geometry(self) -> None:
        if not self._hovered:
            self._target.setGeometry(self._rest_geometry)
            self._restore_parent_layout()

    def _reset_immediately(self) -> None:
        self._hovered = False
        self._animation.stop()
        self._target.setGeometry(self._rest_geometry)
        self._overlay_animation.stop()
        self._overlay.opacity = 0.0
        self._restore_parent_layout()

    def _animate_back_to_rest(self) -> None:
        self._hovered = False
        if not self._target.isVisible():
            return
        self._animation.stop()
        self._animation.setDuration(self._duration)
        self._animation.setStartValue(self._target.geometry())
        self._animation.setEndValue(self._rest_geometry)
        self._animation.start()
        self._animate_overlay_to(0.0)

    def _restore_parent_layout(self) -> None:
        parent = self._target.parentWidget()
        if parent is None:
            return

        def _apply_restore() -> None:
            if parent.layout() is not None:
                parent.layout().activate()
            self._target.updateGeometry()
            parent.updateGeometry()
            parent.update()

        QTimer.singleShot(0, _apply_restore)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is not self._target:
            return False

        event_type = event.type()
        if event_type in {QEvent.Show, QEvent.Resize, QEvent.Move} and not self._hovered:
            self._sync_rest_geometry()
            self._overlay.sync_geometry()
        elif event_type == QEvent.Enter:
            if not self._target.isEnabled():
                return False
            self._sync_rest_geometry()
            self._hovered = True
            self._animate_to(self._hover_geometry)
            self._animate_overlay_to(1.0)
        elif event_type == QEvent.Leave:
            self._animate_back_to_rest()
        elif event_type == QEvent.MouseButtonPress:
            if self._hovered:
                pressed_geometry = QRect(self._rest_geometry)
                pressed_geometry.translate(0, -1)
                self._animate_to(pressed_geometry)
                self._animate_overlay_to(0.7)
        elif event_type == QEvent.MouseButtonRelease:
            if self._hovered:
                self._animate_to(self._hover_geometry)
                self._animate_overlay_to(1.0)
            else:
                self._animate_to(self._rest_geometry)
                self._animate_overlay_to(0.0)
        elif event_type == QEvent.EnabledChange and not self._target.isEnabled():
            self._reset_immediately()
        return False


def attach_hover_bounce(widget: QWidget, y_offset: int = 3, duration: int = 180) -> None:
    if widget is None:
        return
    existing_filter = getattr(widget, "_hover_lift_filter", None)
    if existing_filter is not None:
        existing_filter._y_offset = y_offset
        existing_filter._duration = duration
        existing_filter._sync_rest_geometry()
        return
    widget.setAttribute(Qt.WA_Hover, True)
    widget.setMouseTracking(True)
    widget._hover_lift_filter = HoverLiftFilter(widget, y_offset=y_offset, duration=duration)
    widget.installEventFilter(widget._hover_lift_filter)
