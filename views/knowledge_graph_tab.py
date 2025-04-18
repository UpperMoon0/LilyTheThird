# views/knowledge_graph_tab.py
import os
import webbrowser
# Import QMetaObject and pyqtSlot
from PyQt5.QtCore import pyqtSignal, Qt, QMetaObject, pyqtSlot
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel, QHBoxLayout
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

        self.view_button = QPushButton("View Knowledge Graph", self)
        self.view_button.setStyleSheet("width: 200px; height: 40px;")
        self.view_button.clicked.connect(self.view_graph)
        self.view_button.setEnabled(False) # Initially disabled until graph is loaded

        self.status_label = QLabel("Knowledge Graph not loaded", self)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.load_button)
        button_layout.addWidget(self.view_button)
        button_layout.addStretch()

        layout = QVBoxLayout()
        layout.addLayout(button_layout)
        layout.addWidget(self.status_label)
        layout.addStretch()
        self.setLayout(layout)

    def load_graph(self):
        # Prevent multiple load attempts if already loading/loaded
        if not self.load_button.isEnabled():
             print("KG load already in progress or completed.")
             return

        # Update UI immediately before starting thread
        self.status_label.setText("Loading...")
        self.load_button.setEnabled(False)
        self.view_button.setEnabled(False) # Disable view button during load

        def load():
            kg_handler.load_knowledge_graph()
            # Emit signal *after* loading is complete
            # UI updates will be handled by the slot connected to kg_loaded
            self.kg_loaded.emit()

        import threading
        thread = threading.Thread(target=load, daemon=True) # Use daemon thread
        thread.start()

    # Slot to update UI elements once KG is loaded (called via signal)
    @pyqtSlot()
    def update_ui_on_load(self):
        self.status_label.setText("Knowledge Graph loaded successfully")
        self.load_button.setEnabled(False) # Keep load disabled after successful load
        self.view_button.setEnabled(True)  # Enable view button

    def view_graph(self):
        if kg_handler.graph is None:
            self.status_label.setText("Error: Graph not loaded yet.")
            return

        html_file_name = "knowledge_graph.html"
        # Assuming the HTML file should be saved in the project root
        html_file_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', html_file_name))

        try:
            self.status_label.setText("Generating visualization...")
            # Use the visualize_graph function from kg_handler
            # Need to modify visualize_graph to accept a file path
            # For now, let's assume it saves to a fixed location or we modify it later
            # Let's call the existing visualize_graph which saves to "knowledge_graph.html" in the CWD
            # We need the CWD to be the project root for this to work as expected, or modify visualize_graph

            # Temporary workaround: Assume visualize_graph saves to project root relative path
            kg_handler.visualize_graph(kg_handler.graph)

            # Check if the file exists after generation
            if os.path.exists(html_file_path):
                webbrowser.open(f"file:///{html_file_path}")
                self.status_label.setText("Visualization opened.")
            else:
                 # If visualize_graph saves elsewhere (like in kg/ folder), adjust path
                 kg_folder_html_path = os.path.abspath(os.path.join(os.path.dirname(kg_handler.__file__), html_file_name))
                 if os.path.exists(kg_folder_html_path):
                     webbrowser.open(f"file:///{kg_folder_html_path}")
                     self.status_label.setText("Visualization opened.")
                 else:
                    self.status_label.setText(f"Error: Could not find generated HTML file at {html_file_path} or {kg_folder_html_path}")

        except Exception as e:
            self.status_label.setText(f"Error generating/opening visualization: {e}")
            print(f"Error in view_graph: {e}") # Log error for debugging