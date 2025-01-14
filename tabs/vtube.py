from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout

class VtubeTab(QWidget):
    def __init__(self):
        super().__init__()

        self.label = QLabel("Vtube Tab Content", self)

        layout = QVBoxLayout()
        layout.addWidget(self.label)

        self.setLayout(layout)