from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty, ObjectProperty
from kivy.lang import Builder
import os

# Load the corresponding kv file relative to this python file's location
Builder.load_file(os.path.join(os.path.dirname(__file__), 'attachment_chip.kv'))

class AttachmentChip(BoxLayout):
    """
    Kivy equivalent of the AttachmentChip QWidget.
    Displays a filename and a remove button.
    """
    file_path = StringProperty("")
    filename = StringProperty("")
    # Optional: Add a reference to the parent/manager to notify about removal
    manager = ObjectProperty(None)

    def __init__(self, file_path, manager=None, **kwargs):
        super().__init__(**kwargs)
        self.file_path = file_path
        self.filename = os.path.basename(file_path) # Extract filename from path
        self.manager = manager
        # Layout properties like orientation, padding, spacing are set in kv

    def remove_chip(self):
        """
        Handles the click action of the remove button.
        Removes itself from the parent and notifies the manager if available.
        """
        print(f"Remove chip clicked for: {self.file_path}")
        if self.manager and hasattr(self.manager, 'remove_attachment'):
            self.manager.remove_attachment(self.file_path) # Notify manager

        if self.parent:
            self.parent.remove_widget(self) # Remove widget from layout
