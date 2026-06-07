from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QSpinBox,
    QStyle,
    QStyleOptionComboBox,
    QStylePainter,
)


class NoWheelSpinBox(QSpinBox):
    def wheelEvent(self, event):
        event.ignore()


class NoWheelDoubleSpinBox(QDoubleSpinBox):
    def wheelEvent(self, event):
        event.ignore()


class NoWheelComboBox(QComboBox):
    def wheelEvent(self, event):
        event.ignore()

    def paintEvent(self, event):
        painter = QStylePainter(self)
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        option.subControls = QStyle.SC_All & ~QStyle.SC_ComboBoxArrow
        painter.drawComplexControl(QStyle.CC_ComboBox, option)
        painter.drawControl(QStyle.CE_ComboBoxLabel, option)
