import os
import json
from kivy.uix.boxlayout import BoxLayout
from kivy.properties import ListProperty, StringProperty, ObjectProperty, DictProperty
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.app import App # To access user_data_dir

# Load the corresponding kv file
Builder.load_file('views/components/vtsanimationlist.kv')

class VTSAnimationListItem(BoxLayout):
    """Widget representing a single VTS animation button with edit/delete."""
    animation_name = StringProperty('')
    animation_data = DictProperty({}) # Store the full loaded data
    # Add reference to the parent list to dispatch events
    list_widget = ObjectProperty(None)

    def trigger_animation(self):
        """Dispatch event to parent to trigger this animation."""
        if self.list_widget:
            self.list_widget.dispatch('on_trigger_animation', self.animation_data)

    def edit_animation(self):
        """Placeholder for edit action."""
        print(f"Edit button pressed for: {self.animation_name}")
        # TODO: Implement edit functionality (e.g., open a popup)

    def delete_animation(self):
        """Placeholder for delete action."""
        print(f"Delete button pressed for: {self.animation_name}")
        # TODO: Implement delete functionality (e.g., confirm and delete file)


class VTSAnimationList(BoxLayout):
    """
    A widget to display a list of VTube Studio animations loaded from JSON files.
    """
    animations = ListProperty([]) # List of loaded animation dictionaries
    vtube_tab = ObjectProperty(None) # Reference to the main VTubeTab for triggering

    # Register events
    __events__ = ('on_trigger_animation', 'on_add_animation')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Schedule loading animations slightly after initialization
        from kivy.clock import Clock # Import Clock locally or at top level
        Clock.schedule_once(self._load_animations_scheduled)

    def _load_animations_scheduled(self, dt=None):
        """Helper method to load animations after a short delay."""
        self.load_animations()

    def get_animations_dir(self):
        """Gets the path to the animations directory in AppData."""
        # Use Kivy's user_data_dir which points to AppData/Roaming/<appname>
        app = App.get_running_app()
        # Construct the specific path within the app's data directory
        # Note: Kivy uses lowercase appname by default for the folder.
        # We might need to adjust this based on how App is named or manually construct.
        # Let's assume a structure like AppData/Roaming/lilythethird/vtube/animations
        # Or use the structure requested: AppData/Roaming/NsTut/LilyTheThird/vtube/animations
        app_data_root = os.getenv('APPDATA') # More reliable for Roaming path
        if not app_data_root:
             print("Error: Could not determine APPDATA directory.")
             return None
        # Use the requested path structure
        animations_path = os.path.join(app_data_root, 'NsTut', 'LilyTheThird', 'vtube', 'animations')

        # Ensure the directory exists
        if not os.path.exists(animations_path):
            try:
                os.makedirs(animations_path)
                print(f"Created animations directory: {animations_path}")
            except OSError as e:
                print(f"Error creating animations directory {animations_path}: {e}")
                return None
        return animations_path

    def load_animations(self):
        """Loads animation data from JSON files in the designated directory."""
        animations_dir = self.get_animations_dir()
        if not animations_dir:
            print("Cannot load animations: Directory path is invalid.")
            self.animations = []
            self.update_animations_display() # Update UI to show empty state
            return

        print(f"Loading animations from: {animations_dir}")
        loaded_animations = []
        try:
            for filename in os.listdir(animations_dir):
                if filename.lower().endswith('.json'):
                    filepath = os.path.join(animations_dir, filename)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            # Basic validation: check for 'name' and 'parameters' keys
                            if isinstance(data, dict) and 'name' in data and 'parameters' in data:
                                # Store the filename without extension for potential use
                                data['_filename'] = os.path.splitext(filename)[0]
                                loaded_animations.append(data)
                                print(f"Loaded animation: {data.get('name', 'Unnamed')}")
                            else:
                                print(f"Warning: Skipping invalid JSON structure in {filename}")
                    except json.JSONDecodeError:
                        print(f"Warning: Skipping invalid JSON file: {filename}")
                    except Exception as e:
                        print(f"Error loading file {filename}: {e}")
        except FileNotFoundError:
            print(f"Animations directory not found: {animations_dir}")
        except Exception as e:
            print(f"Error reading animations directory {animations_dir}: {e}")

        self.animations = loaded_animations
        self.update_animations_display()

    def update_animations_display(self):
        """Clears and repopulates the animation list display."""
        anim_container = self.ids.animations_container
        anim_container.clear_widgets()
        # Set height dynamically (adjust item height as needed)
        item_height = dp(40) # Height for each animation item row
        anim_container.height = len(self.animations) * item_height

        if not self.animations:
            anim_container.height = dp(30) # Height for the 'no animations' label
            anim_container.add_widget(Label(text="No animations found.", size_hint_y=None, height=dp(30)))
        else:
            for anim_data in self.animations:
                item = VTSAnimationListItem(
                    animation_name=anim_data.get('name', 'Unnamed'),
                    animation_data=anim_data,
                    list_widget=self # Pass reference to self
                )
                anim_container.add_widget(item)

    def add_new_animation(self):
        """Placeholder for add action."""
        print("Add New Animation button pressed.")
        self.dispatch('on_add_animation')
        # TODO: Implement add functionality (e.g., open a creation dialog)

    # --- Event Handlers ---
    def on_trigger_animation(self, animation_data):
        """Default handler, bubbles up to VTubeTab."""
        # This method needs to exist for the event to bubble correctly via kv bindings
        # The actual logic is in VTubeTab's handler
        pass

    def on_add_animation(self):
        """Default handler for adding animation."""
        pass
