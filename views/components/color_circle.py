from kivy.uix.widget import Widget
from kivy.properties import ListProperty, NumericProperty
from kivy.lang import Builder
from kivy.utils import get_color_from_hex
from kivy.metrics import dp

Builder.load_file('views/components/color_circle.kv')

class ColorCircle(Widget):
    """
    Kivy equivalent of the ColorCircle QLabel.
    A simple widget displaying a colored circle.
    The color can be updated via the 'circle_color' property.
    """
    # Use ListProperty for color (RGBA format)
    circle_color = ListProperty([1, 0, 0, 1]) # Default to red RGBA

    # Define size properties (can be set in kv or here)
    circle_size = NumericProperty(dp(50)) # Match PyQt fixed size (using dp)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Size is set in the kv file using circle_size property

    def set_color_hex(self, hex_color):
        """Helper method to set color using hex string."""
        self.circle_color = get_color_from_hex(hex_color)

    def set_color_rgb(self, r, g, b, a=1.0):
        """Helper method to set color using RGB values (0-255)."""
        self.circle_color = [r / 255.0, g / 255.0, b / 255.0, a]
