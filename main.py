import os
import sys

from PyQt5.QtWidgets import QApplication, QMainWindow, QTabWidget

from tabs.chat import ChatTab
from tabs.discord import DiscordTab


def clear_output_folder():
    output_folder = "outputs"  # Adjust this path as needed

    # Check if the outputs folder exists
    if os.path.exists(output_folder):
        # Delete files that start with 'audio' in the outputs folder
        for filename in os.listdir(output_folder):
            if filename.startswith("audio"):
                file_path = os.path.join(output_folder, filename)
                try:
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                        print(f"Deleted {file_path}")
                except Exception as e:
                    print(f"Error deleting {file_path}: {e}")


class MainWindow(QMainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()

        self.tabs = QTabWidget(self)
        self.chat_tab = ChatTab()
        self.discord_tab = DiscordTab()

        self.tabs.addTab(self.chat_tab, "Chat")
        self.tabs.addTab(self.discord_tab, "Discord")

        self.setCentralWidget(self.tabs)

        # Set the window title to "Lily III"
        self.setWindowTitle("Lily III")

        # Clear the outputs folder when the app starts
        clear_output_folder()

        # Set the window to full screen on start
        self.showMaximized()

    def closeEvent(self, event):
        # Clear the outputs folder before the application closes
        clear_output_folder()
        event.accept()  # Accept the close event to allow the window to close


app = QApplication(sys.argv)
window = MainWindow()
window.show()
sys.exit(app.exec_())
