from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QEvent, QObject, QPropertyAnimation
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget


class _SoftWindowTransitionFilter(QObject):
    def __init__(self, widget: QWidget, fade_in_ms: int, fade_out_ms: int) -> None:
        super().__init__(widget)
        self.widget = widget
        self.fade_in_ms = fade_in_ms
        self.fade_out_ms = fade_out_ms
        self._opacity_effect: QGraphicsOpacityEffect | None = None
        self._fade_in_animation: QPropertyAnimation | None = None
        self._fade_out_animation: QPropertyAnimation | None = None
        self._allow_close = False
        self._closing = False

    def _ensure_effect(self) -> QGraphicsOpacityEffect:
        if self._opacity_effect is None:
            existing_effect = self.widget.graphicsEffect()
            if isinstance(existing_effect, QGraphicsOpacityEffect):
                self._opacity_effect = existing_effect
            else:
                self._opacity_effect = QGraphicsOpacityEffect(self.widget)
                self._opacity_effect.setOpacity(1.0)
                self.widget.setGraphicsEffect(self._opacity_effect)
        return self._opacity_effect

    def _fade_in(self) -> None:
        effect = self._ensure_effect()
        if self._fade_out_animation is not None:
            self._fade_out_animation.stop()
        self._closing = False
        if bool(self.widget.property("skipFadeInTransition")):
            effect.setOpacity(1.0)
            return
        effect.setOpacity(0.0)
        self._fade_in_animation = QPropertyAnimation(effect, b"opacity", self.widget)
        self._fade_in_animation.setDuration(self.fade_in_ms)
        self._fade_in_animation.setEasingCurve(QEasingCurve.OutCubic)
        self._fade_in_animation.setStartValue(0.0)
        self._fade_in_animation.setEndValue(1.0)
        self._fade_in_animation.start()

    def _fade_out(self) -> None:
        effect = self._ensure_effect()
        if self._fade_in_animation is not None:
            self._fade_in_animation.stop()
        self._closing = True
        self._fade_out_animation = QPropertyAnimation(effect, b"opacity", self.widget)
        self._fade_out_animation.setDuration(self.fade_out_ms)
        self._fade_out_animation.setEasingCurve(QEasingCurve.OutCubic)
        self._fade_out_animation.setStartValue(max(0.0, effect.opacity()))
        self._fade_out_animation.setEndValue(0.0)

        def finish_close() -> None:
            self._allow_close = True
            try:
                self.widget.close()
            finally:
                self._allow_close = False
                self._closing = False
                effect.setOpacity(1.0)

        self._fade_out_animation.finished.connect(finish_close)
        self._fade_out_animation.start()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is not self.widget:
            return False

        if event.type() == QEvent.Show:
            if not self._closing:
                self._fade_in()
            return False

        if event.type() == QEvent.Close:
            if self._allow_close:
                return False
            if self._closing or not self.widget.isVisible():
                return True
            event.ignore()
            self._fade_out()
            return True

        return False


def enable_soft_window_transitions(
    widget: QWidget,
    *,
    fade_in_ms: int = 240,
    fade_out_ms: int = 200,
) -> None:
    if getattr(widget, "_soft_window_transition_enabled", False):
        return

    transition_filter = _SoftWindowTransitionFilter(widget, fade_in_ms, fade_out_ms)
    widget.installEventFilter(transition_filter)
    widget._soft_window_transition_enabled = True
    widget._soft_window_transition_filter = transition_filter
