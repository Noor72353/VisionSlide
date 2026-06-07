from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath
from PySide6.QtWidgets import QLabel, QSizePolicy


class BrandHeadingLabel(QLabel):
    def __init__(
        self,
        brand_text: str = "VisionSlide",
        kicker_text: str = "Gesture \u2022 Voice \u2022 Slides",
        *,
        centered: bool = False,
        center_offset_x: int = 0,
        brand_size: int = 34,
        kicker_size: int = 11,
        parent=None,
    ):
        super().__init__(parent)
        self.brand_text = brand_text
        self.kicker_text = kicker_text
        self.centered = centered
        self.center_offset_x = center_offset_x
        self.brand_size = brand_size
        self.kicker_size = kicker_size
        self.dark_mode = False
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(self.sizeHint().height())

    def setDarkMode(self, dark_mode: bool) -> None:
        self.dark_mode = bool(dark_mode)
        self.update()

    def setCentered(self, centered: bool) -> None:
        self.centered = bool(centered)
        self.update()

    def setCenterOffsetX(self, offset: int) -> None:
        self.center_offset_x = int(offset)
        self.update()

    def sizeHint(self) -> QSize:
        has_kicker = bool(self.kicker_text.strip())
        kicker_height = max(18, int(self.kicker_size * 1.7)) if has_kicker else 0
        brand_height = max(42, int(self.brand_size * 1.55))
        total_height = brand_height + kicker_height + (6 if has_kicker else 2)
        return QSize(340, total_height)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        full_rect = self.rect()
        align = Qt.AlignCenter if self.centered else Qt.AlignLeft
        has_kicker = bool(self.kicker_text.strip())
        kicker_height = max(18, int(self.kicker_size * 1.7)) if has_kicker else 0
        spacing = 2 if has_kicker else 0
        brand_rect = full_rect.adjusted(0, 0, 0, -(kicker_height + spacing))
        kicker_rect = full_rect.adjusted(0, brand_rect.bottom() - full_rect.top() + spacing, 0, 0)

        kicker_font = QFont("Segoe UI", self.kicker_size)
        kicker_font.setWeight(QFont.ExtraBold)
        kicker_font.setLetterSpacing(QFont.AbsoluteSpacing, 0.8)

        brand_font = QFont("Segoe UI", self.brand_size)
        brand_font.setWeight(QFont.ExtraBold)
        brand_font.setLetterSpacing(QFont.AbsoluteSpacing, 1.0)
        painter.setFont(brand_font)
        brand_metrics = painter.fontMetrics()

        gradient = QLinearGradient(0, brand_rect.top(), 0, brand_rect.bottom())
        if self.dark_mode:
            gradient.setColorAt(0.0, QColor("#e2f8ff"))
            gradient.setColorAt(1.0, QColor("#66adc1"))
        else:
            gradient.setColorAt(0.0, QColor("#98deef"))
            gradient.setColorAt(1.0, QColor("#5c92a3"))

        path = QPainterPath()
        baseline_y = brand_rect.top() + brand_metrics.ascent() + 2
        if self.centered:
            x_pos = brand_rect.center().x() - (brand_metrics.horizontalAdvance(self.brand_text) / 2) + self.center_offset_x
        else:
            x_pos = brand_rect.left()
        path.addText(x_pos, baseline_y, brand_font, self.brand_text)
        shadow_path = QPainterPath(path)
        shadow_path.translate(0, 3)
        shadow_color = QColor("#183640" if self.dark_mode else "#7ea0ac")
        shadow_color.setAlpha(105 if self.dark_mode else 88)
        painter.fillPath(shadow_path, shadow_color)
        painter.fillPath(path, gradient)

        if has_kicker:
            painter.setFont(kicker_font)
            kicker_color = QColor("#b7d7e4" if self.dark_mode else "#6f95a4")
            painter.setPen(kicker_color)
            if self.centered and self.center_offset_x:
                shifted_kicker_rect = kicker_rect.adjusted(self.center_offset_x, 0, self.center_offset_x, 0)
                painter.drawText(shifted_kicker_rect, align | Qt.AlignTop, self.kicker_text)
            else:
                painter.drawText(kicker_rect, align | Qt.AlignTop, self.kicker_text)
