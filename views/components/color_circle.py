from PyQt5.QtWidgets import QLabel
from PyQt5.QtGui import QColor
from PyQt5.QtCore import pyqtProperty

class ColorCircle(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._color = QColor(201, 0, 0)  # Start with red
        self.setFixedSize(50, 50)
        self.updateStyleSheet()

    @pyqtProperty(QColor)
    def color(self):
        return self._color

    @color.setter
    def color(self, color):
        self._color = color
        self.updateStyleSheet()

    def updateStyleSheet(self):
        self.setStyleSheet(
            f"background-color: rgba({self._color.red()}, {self._color.green()}, "
            f"{self._color.blue()}, {self._color.alpha() / 255.0}); "
            f"border-radius: 25px;"
        )