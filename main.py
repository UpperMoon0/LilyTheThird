import os
import sys
import threading # Import threading
from PyQt5.QtWidgets import QApplication, QMainWindow, QTabWidget

from views.chat_tab import ChatTab
from views.discord_tab import DiscordTab
from views.vtube_tab import VTubeTab
from views.knowledge_graph_tab import KnowledgeGraphTab
# Import settings and kg_handler
from settings_manager import load_settings
from kg import kg_handler

def clear_output_folder():
    output_folder = "outputs"
    if os.path.exists(output_folder):
        for filename in os.listdir(output_folder):
            if filename.startswith("audio"):
                file_path = os.path.join(output_folder, filename)
                try:
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                        print(f"Deleted {file_path}")
                except Exception as e:
                    pass

class MainWindow(QMainWindow):
       def __init__(self):
           super(MainWindow, self).__init__()

           # Load settings early
           self.settings = load_settings()

           self.tabs = QTabWidget(self)
           # Pass settings to ChatTab if it needs them directly (already handled via import)
           self.chat_tab = ChatTab()
           self.discord_tab = DiscordTab()
           self.vtube_tab = VTubeTab()
           self.kg_tab = KnowledgeGraphTab()  # KG tab instance

           # Connect the knowledge graph loaded signal to chat_tab update
           # This connection remains important for both manual and auto-load
           self.kg_tab.kg_loaded.connect(self.chat_tab.enable_kg_features)
           # Also connect to KG tab's own update method
           self.kg_tab.kg_loaded.connect(self.kg_tab.update_ui_on_load)

           self.tabs.addTab(self.chat_tab, "Chat")
           self.tabs.addTab(self.discord_tab, "Discord")
           self.tabs.addTab(self.vtube_tab, "Vtube")
           self.tabs.addTab(self.kg_tab, "Knowledge Graph")

           self.setCentralWidget(self.tabs)
           self.setWindowTitle("Lily III")
           clear_output_folder()
           self.showMaximized()

           # Auto-load KG if setting is enabled
           self.auto_load_kg_if_enabled()

       def auto_load_kg_if_enabled(self):
           if self.settings.get('enable_kg_memory', False):
               print("KG Memory enabled in settings. Auto-loading Knowledge Graph...")
               # Use the KG tab's load method, which handles threading and signals
               self.kg_tab.load_graph()
           else:
               print("KG Memory not enabled in settings. Skipping auto-load.")

       def closeEvent(self, event):
           clear_output_folder()
           event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    sys.exit(app.exec_())
