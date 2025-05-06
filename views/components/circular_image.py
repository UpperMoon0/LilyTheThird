import os
import time
from kivy.app import App
from kivy.uix.widget import Widget
from kivy.uix.image import Image as KivyImage
from kivy.properties import StringProperty, ListProperty, ObjectProperty, BooleanProperty
from kivy.lang import Builder
from kivy.uix.filechooser import FileChooserIconView
from kivy.uix.popup import Popup
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.label import Label
from kivy.metrics import dp
from kivy.core.window import Window
from kivy.clock import Clock # Added import

try:
    from PIL import Image as PILImage
    from PIL import ImageOps
except ImportError:
    PILImage = None
    ImageOps = None
    # Consider raising an error or logging if PIL is critical
    print("PIL (Pillow) library not found. Image resizing and saving will not work.")


Builder.load_file('views/components/circular_image.kv')

from utils.file_utils import get_nstut_lilythethird_app_data_dir # Import the new utility

# AVATAR_FILENAME can remain a module-level constant or become a class attribute
AVATAR_FILENAME = "avatar.png"

class CircularImage(Widget):
    """
    A widget that displays an image cropped into a circle.
    It allows users to click to select a new avatar, which is then
    resized and saved.
    """
    source = StringProperty('')
    image_texture = ObjectProperty(None, allownone=True)

    # Internal properties to calculate drawing position and size
    _image_draw_pos = ListProperty([0, 0])
    _image_draw_size = ListProperty([0, 0])
    # _default_avatar_path will be an instance variable, not a Kivy property
    hovered = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._image = KivyImage() # Internal Kivy image to load texture
        self._popup = None
        self._current_filechooser_path_input = None
        self._current_filechooser = None

        # --- Path Definitions using helper ---
        app_instance = App.get_running_app() # Still useful for app_root for assets

        base_app_data_dir = get_nstut_lilythethird_app_data_dir() # Use imported function
        self.avatar_dir = os.path.join(base_app_data_dir, 'chat')
        self.full_avatar_path = os.path.join(self.avatar_dir, AVATAR_FILENAME)

        # Define self._default_avatar_path (logic for app_root remains the same)
        if app_instance and app_instance.directory:
            app_root = app_instance.directory
        else:
            # Fallback if app_instance or its directory is not available
            app_root = os.getcwd() 
        self._default_avatar_path = os.path.join(app_root, 'assets', 'avatar.png')
        # --- End Path Definitions ---

        # Ensure avatar directory exists
        if not os.path.exists(self.avatar_dir):
            try:
                os.makedirs(self.avatar_dir)
                print(f"Created avatar directory: {self.avatar_dir}")
            except OSError as e:
                print(f"Error creating avatar directory {self.avatar_dir}: {e}")
        
        Clock.schedule_once(lambda dt: self.load_avatar()) # Changed to schedule_once

        self.bind(source=self._update_image_source,
                  pos=self._update_image_draw_params,
                  size=self._update_image_draw_params)
        Window.bind(mouse_pos=self.on_mouse_pos)

    def on_mouse_pos(self, window, pos):
        """Handles mouse position changes to update hover state."""
        # Check if the widget is currently part of the window's widget tree
        if not self.get_root_window():
            if self.hovered:
                self.hovered = False
            return
        
        inside = self.collide_point(*pos)
        if self.hovered != inside:
            self.hovered = inside

    def load_avatar(self):
        """Loads the saved avatar or the default if not found."""
        path_to_load = self._default_avatar_path # Start with default

        print(f"CircularImage INFO: --- Avatar Loading ---")
        print(f"CircularImage INFO: Default avatar path: {self._default_avatar_path}")
        print(f"CircularImage INFO: Attempting to load saved avatar from: {self.full_avatar_path}")

        saved_avatar_exists = False
        try:
            saved_avatar_exists = os.path.exists(self.full_avatar_path)
            print(f"CircularImage INFO: os.path.exists('{self.full_avatar_path}') returned: {saved_avatar_exists}")
        except Exception as e:
            print(f"CircularImage ERROR: Exception during os.path.exists('{self.full_avatar_path}'): {e}")


        if saved_avatar_exists:
            path_to_load = self.full_avatar_path
            print(f"CircularImage INFO: Saved avatar found. Using: {path_to_load}")
        else:
            print(f"CircularImage INFO: Saved avatar NOT found or error checking. Using default: {path_to_load}")
        
        # Add timestamp for cache busting to the widget's source property
        self.source = f"{path_to_load}?_={time.time()}" 
        print(f"CircularImage INFO: Final source set to: '{self.source}' (based on path: '{path_to_load}')")
        print(f"CircularImage INFO: --- End Avatar Loading ---")

    def _update_image_source(self, instance, value):
        """Load the texture when the source changes."""
        # Value might contain a cache-busting query string. Strip it for local file loading.
        clean_path = value.split('?')[0]
        
        if self._image.source == clean_path and self._image.texture:
            # If the clean path is the same and texture exists, force a reload
            # This handles the case where the file content changed but path is the same.
            print(f"CircularImage: Reloading image from {clean_path}")
            self._image.reload()
        else:
            # If path is different or no texture, set source and Kivy handles loading
            print(f"CircularImage: Setting internal KivyImage source to {clean_path}")
            self._image.source = clean_path
            # Kivy's Image widget reloads automatically when its source property changes.
            # If issues persist, self._image.reload() can be called here too.

        self.image_texture = self._image.texture
        # self._update_image_draw_params() # This is called by on_image_texture

    def on_image_texture(self, instance, value):
        """Callback when the texture is loaded."""
        self._update_image_draw_params()

    def _update_image_draw_params(self, *args):
        """Calculate the position and size to draw the image texture."""
        if not self.image_texture or self.width <= 0 or self.height <= 0:
            self._image_draw_size = [0, 0]
            self._image_draw_pos = self.pos
            return

        tex_w, tex_h = self.image_texture.size
        if tex_h == 0: # Avoid division by zero if texture height is 0
            self._image_draw_size = [0, 0]
            self._image_draw_pos = self.pos
            return
        aspect_ratio = tex_w / float(tex_h)

        # Calculate 'contain' size
        widget_aspect = self.width / float(self.height)
        if widget_aspect > aspect_ratio:
            # Widget is wider than image aspect ratio, height is the limiting factor
            draw_h = self.height
            draw_w = draw_h * aspect_ratio
        else:
            # Widget is taller or equal aspect ratio, width is the limiting factor
            draw_w = self.width
            draw_h = draw_w / aspect_ratio

        # Calculate centered position
        draw_x = self.x + (self.width - draw_w) / 2.0
        draw_y = self.y + (self.height - draw_h) / 2.0

        self._image_draw_size = [draw_w, draw_h]
        self._image_draw_pos = [draw_x, draw_y]

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            if touch.is_double_tap: # Or single tap, depending on desired UX
                 self.open_file_chooser()
                 return True # Consume the touch
        return super().on_touch_down(touch)

    def open_file_chooser(self):
        if not PILImage:
            print("CircularImage: PIL (Pillow) not installed. Cannot open file chooser.")
            # Optionally show a Kivy popup to inform the user
            error_popup = Popup(title='Error',
                                content=Button(text='Image library (Pillow) not found.\nPlease install it to change avatar.'),
                                size_hint=(0.6, 0.2))
            error_popup.content.bind(on_press=error_popup.dismiss)
            error_popup.open()
            return

        content = BoxLayout(orientation='vertical', spacing=dp(5), padding=dp(5))
        
        # Path Bar
        path_bar_layout = BoxLayout(size_hint_y=None, height=dp(30), spacing=dp(5))
        path_label = Label(text="Path:", size_hint_x=None, width=dp(40))
        self._current_filechooser_path_input = TextInput(
            multiline=False,
            size_hint_x=1
        )
        path_bar_layout.add_widget(path_label)
        path_bar_layout.add_widget(self._current_filechooser_path_input)
        content.add_widget(path_bar_layout)

        # Use user's home directory or a sensible default if possible
        home_dir = os.path.expanduser('~')
        if not os.path.isdir(home_dir): # Fallback if home_dir is not accessible/valid
            home_dir = App.get_running_app().user_data_dir

        self._current_filechooser = FileChooserIconView(
            path=home_dir,
            filters=['*.png', '*.jpg', '*.jpeg', '*.bmp', '*.gif'],
            dirselect=False,
            size_hint_y=1 # Takes remaining space
        )
        self._current_filechooser_path_input.text = self._current_filechooser.path # Initialize path input

        # Bindings for path bar
        self._current_filechooser.bind(path=self._on_filechooser_path_changed)
        self._current_filechooser_path_input.bind(on_text_validate=self._on_path_input_submit)

        content.add_widget(self._current_filechooser)

        btn_layout = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(5))
        select_btn = Button(text='Select')
        cancel_btn = Button(text='Cancel')
        btn_layout.add_widget(select_btn)
        btn_layout.add_widget(cancel_btn)
        content.add_widget(btn_layout)

        self._popup = Popup(title="Choose an Avatar Image",
                            content=content,
                            size_hint=(0.9, 0.9),
                            auto_dismiss=False)
        
        self._popup.bind(on_dismiss=self._clear_filechooser_refs) # Clear refs on dismiss

        select_btn.bind(on_press=lambda x: self.save_avatar_from_selection(self._current_filechooser.selection))
        cancel_btn.bind(on_press=self._popup.dismiss) # This will trigger _clear_filechooser_refs
        self._popup.open()

    def _clear_filechooser_refs(self, instance=None):
        """Clear references to filechooser components when popup is dismissed."""
        if self._current_filechooser:
            self._current_filechooser.unbind(path=self._on_filechooser_path_changed)
        if self._current_filechooser_path_input:
            self._current_filechooser_path_input.unbind(on_text_validate=self._on_path_input_submit)
        
        self._current_filechooser_path_input = None
        self._current_filechooser = None
        self._popup = None # Ensure popup ref is also cleared

    def _on_filechooser_path_changed(self, instance, path):
        if self._current_filechooser_path_input:
            self._current_filechooser_path_input.text = path

    def _on_path_input_submit(self, instance_text_input):
        new_path = instance_text_input.text.strip()
        if self._current_filechooser and os.path.isdir(new_path):
            self._current_filechooser.path = new_path
        elif self._current_filechooser_path_input: # Revert if path invalid
            # Simple feedback: revert to current filechooser path
            self._current_filechooser_path_input.text = self._current_filechooser.path
            # More advanced: show a small error label or change background briefly

    def save_avatar_from_selection(self, selection):
        # Popup dismissal and ref clearing is now handled by _clear_filechooser_refs via on_dismiss
        if self._popup and self._popup.content: # Check if popup still exists
             self._popup.dismiss() # This will also call _clear_filechooser_refs

        if not selection:
            return

        selected_path = selection[0]
        if not PILImage or not ImageOps:
            print("CircularImage: PIL (Pillow) not available for image processing.")
            return

        try:
            img = PILImage.open(selected_path)
            
            # Ensure image is in RGB or RGBA mode before saving as PNG
            if img.mode not in ('RGB', 'RGBA'):
                img = img.convert('RGBA')

            # Resize while maintaining aspect ratio, then crop to square
            # This is a common way to get a 1000x1000 image without distortion
            # Option 1: Fit within 1000x1000 then pad (if you want to keep all content)
            # img.thumbnail((1000, 1000), PILImage.Resampling.LANCZOS)
            # new_img = PILImage.new("RGBA", (1000, 1000), (0,0,0,0)) # Transparent background
            # new_img.paste(img, ((1000 - img.width) // 2, (1000 - img.height) // 2))
            # img = new_img

            # Option 2: Crop to square from center (more common for avatars)
            # Resize the smallest dimension to 1000, then crop center
            img = ImageOps.fit(img, (1000, 1000), PILImage.Resampling.LANCZOS)

            img.save(self.full_avatar_path, 'PNG') # Save as PNG to support transparency
            print(f"CircularImage: Saved new avatar to {self.full_avatar_path}")
            self.load_avatar() # Reload the avatar to display the new one
        except Exception as e:
            print(f"CircularImage: Error processing or saving image: {e}")
            # Optionally show an error popup to the user
            error_popup = Popup(title='Image Error',
                                content=Button(text=f'Could not process image:\n{e}'),
                                size_hint=(0.8, 0.3))
            error_popup.content.bind(on_press=error_popup.dismiss)
            error_popup.open()
