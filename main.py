import os
import sys
import threading # Import threading
from PyQt5.QtWidgets import QApplication, QMainWindow, QTabWidget

from views.chat_tab import ChatTab
from views.discord_tab import DiscordTab
from views.vtube_tab import VTubeTab
from settings_manager import load_settings

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
           self.chat_tab = ChatTab() # ChatTab handles memory internally
           self.discord_tab = DiscordTab()
           self.vtube_tab = VTubeTab()

           self.tabs.addTab(self.chat_tab, "Chat")
           self.tabs.addTab(self.discord_tab, "Discord")
           self.tabs.addTab(self.vtube_tab, "Vtube")

           self.setCentralWidget(self.tabs)
           self.setWindowTitle("Lily III")
           clear_output_folder() # Clear output folder on startup
           self.showMaximized()

       def closeEvent(self, event):
           # No global MongoDB handler to close here
           clear_output_folder()
           event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    sys.exit(app.exec_())
