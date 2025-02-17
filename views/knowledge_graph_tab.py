# views/knowledge_graph_tab.py
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel
from kg import kg_handler

class KnowledgeGraphTab(QWidget):
    kg_loaded = pyqtSignal()  # Custom signal to notify when the KG has loaded

    def __init__(self):
        super().__init__()
        self.init_ui()
    
    def init_ui(self):
        self.load_button = QPushButton("Load Knowledge Graph", self)
        self.load_button.setStyleSheet("width: 200px; height: 40px;")
        self.load_button.clicked.connect(self.load_graph)
        
        self.status_label = QLabel("Knowledge Graph not loaded", self)
        
        layout = QVBoxLayout()
        layout.addWidget(self.load_button)
        layout.addWidget(self.status_label)
        layout.addStretch()
        self.setLayout(layout)
    
    def load_graph(self):
        self.status_label.setText("Loading...")
        self.load_button.setEnabled(False)
        
        def load():
            kg_handler.load_knowledge_graph()
            # When done, update the UI (in the main thread)
            self.status_label.setText("Knowledge Graph loaded successfully")
            self.kg_loaded.emit()  # Emit the signal once the KG is loaded
        
        import threading
        thread = threading.Thread(target=load)
        thread.start()