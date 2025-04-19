import os
import sys
import threading # Import threading
from PyQt5.QtWidgets import QApplication, QMainWindow, QTabWidget

from views.chat_tab import ChatTab
from views.discord_tab import DiscordTab
from views.vtube_tab import VTubeTab
# Removed KG Tab import
# Import settings
from settings_manager import load_settings
# Removed KG handler import
# Import MongoHandler (optional here, might be better scoped in ChatTab)
# from memory.mongo_handler import MongoHandler

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
           self.chat_tab = ChatTab() # ChatTab will now handle memory internally
           self.discord_tab = DiscordTab()
           self.vtube_tab = VTubeTab()
            # Removed KG Tab instantiation

            # Removed KG signal connections

           self.tabs.addTab(self.chat_tab, "Chat")
           self.tabs.addTab(self.discord_tab, "Discord")
           self.tabs.addTab(self.vtube_tab, "Vtube")
           # Removed KG Tab addition

           self.setCentralWidget(self.tabs)
           self.setWindowTitle("Lily III")
           clear_output_folder() # This line seems misplaced, should it be inside __init__? Let's indent it for now.
           self.showMaximized()

            # Removed auto-load KG logic. MongoDB connection is handled by MongoHandler instance.
            # If global handler needed:
            # if self.settings.get('enable_mongo_memory', False):
            #    self.mongo_handler = MongoHandler() # Initialize if enabled

       # Removed auto_load_kg_if_enabled method

       def closeEvent(self, event):
           # Consider closing MongoDB connection here if a global handler was used
           # if hasattr(self, 'mongo_handler') and self.mongo_handler:
           #     self.mongo_handler.close_connection()
           clear_output_folder()
           event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    sys.exit(app.exec_())
