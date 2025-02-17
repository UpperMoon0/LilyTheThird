import os
import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QTabWidget

from tabs.chat_tab import ChatTab
from tabs.discord_tab import DiscordTab
from tabs.vtube_tab import VTubeTab
from tabs.ide_tab import IDETab  

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

        self.tabs = QTabWidget(self)
        self.chat_tab = ChatTab()
        self.discord_tab = DiscordTab()
        self.vtube_tab = VTubeTab()
        self.ide_tab = IDETab() 

        self.tabs.addTab(self.chat_tab, "Chat")
        self.tabs.addTab(self.ide_tab, "IDE")  
        self.tabs.addTab(self.discord_tab, "Discord")
        self.tabs.addTab(self.vtube_tab, "Vtube")

        self.setCentralWidget(self.tabs)
        self.setWindowTitle("Lily III")
        clear_output_folder()
        self.showMaximized()

    def closeEvent(self, event):
        clear_output_folder()
        event.accept()

app = QApplication(sys.argv)
window = MainWindow()
window.show()
sys.exit(app.exec_())