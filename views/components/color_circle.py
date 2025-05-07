from kivy.uix.widget import Widget
from kivy.properties import ListProperty, NumericProperty, BooleanProperty
from kivy.lang import Builder
from kivy.utils import get_color_from_hex
from kivy.metrics import dp
from kivy.animation import Animation

Builder.load_file('views/components/color_circle.kv')

class ColorCircle(Widget):
    """
    Kivy equivalent of the ColorCircle QLabel.
    A simple widget displaying a colored circle.
    The color can be updated via the 'circle_color' property.
    Can also have an animated pulsating effect.
    """
    # Use ListProperty for color (RGBA format)
    circle_color = ListProperty([1, 0, 0, 1]) # Default to red RGBA
    base_color = ListProperty([1, 0, 0, 1]) # Stores the base color for animation

    # Define size properties (can be set in kv or here)
    circle_size = NumericProperty(dp(50)) # Match PyQt fixed size (using dp)
    is_animating = BooleanProperty(False)

    _animation = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Size is set in the kv file using circle_size property
        self.bind(circle_color=self._update_base_color_if_not_animating)

    def _update_base_color_if_not_animating(self, instance, value):
        if not self.is_animating:
            self.base_color = value[:] # Ensure it's a copy

    def set_color_hex(self, hex_color):
        """Helper method to set color using hex string."""
        new_color = get_color_from_hex(hex_color)
        if self.is_animating:
            self.base_color = new_color
        else:
            self.circle_color = new_color
            self.base_color = new_color[:]

    def set_color_rgb(self, r, g, b, a=1.0):
        """Helper method to set color using RGB values (0-255)."""
        new_color = [r / 255.0, g / 255.0, b / 255.0, a]
        if self.is_animating:
            self.base_color = new_color
        else:
            self.circle_color = new_color
            self.base_color = new_color[:]

    def start_pulsing_animation(self, duration=1.0):
        """Starts a pulsating alpha animation."""
        if not self.is_animating:
            self.is_animating = True
            self.base_color = self.circle_color[:] # Store current color as base
            
            # Ensure base_color has 4 components (RGBA)
            if len(self.base_color) == 3:
                self.base_color.append(1.0)

            anim = Animation(circle_color=[self.base_color[0], self.base_color[1], self.base_color[2], 0.2], duration=duration/2) + \
                   Animation(circle_color=[self.base_color[0], self.base_color[1], self.base_color[2], 1.0], duration=duration/2)
            anim.repeat = True
            self._animation = anim
            anim.start(self)

    def stop_animation(self):
        """Stops any ongoing animation and restores the base color."""
        if self.is_animating:
            if self._animation:
                Animation.cancel_all(self, 'circle_color')
                self._animation = None
            self.circle_color = self.base_color[:] # Restore base color
            self.is_animating = False
