import os
from PyQt5.QtWidgets import QWidget, QLabel, QPushButton, QHBoxLayout
from PyQt5.QtCore import pyqtSignal

class AttachmentChip(QWidget):
    # Signal to notify when the chip is removed; passes the file path.
    removeClicked = pyqtSignal(str)
    
    def __init__(self, file_path, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.init_ui()
    
    def init_ui(self):
        # Create a horizontal layout with some margins and spacing.
        layout = QHBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        # Label showing the file name.
        self.label = QLabel(self)
        self.label.setText(os.path.basename(self.file_path))
        layout.addWidget(self.label)

        # Remove button ("x" chip).
        self.remove_button = QPushButton("x", self)
        self.remove_button.setFixedSize(20, 20)
        self.remove_button.clicked.connect(self.handle_remove)
        layout.addWidget(self.remove_button)

        self.setLayout(layout)

    def handle_remove(self):
        # Emit a signal indicating that this chip should be removed.
        self.removeClicked.emit(self.file_path)