from kivy.uix.widget import Widget
from kivy.graphics import Color, Rectangle
from kivy.properties import ListProperty, NumericProperty
from kivy.clock import Clock
import colorsys
import math

class RGBStrip(Widget):
    """A thin widget displaying an animated RGB wave gradient strip."""
    strip_color = ListProperty([1, 0, 0, 1]) # Base color, not directly used for drawing now
    hue_offset = NumericProperty(0) # Animated property for the wave effect
    num_segments = NumericProperty(100) # Number of segments for the gradient
    wave_frequency = NumericProperty(2) # How many waves across the strip
    animation_speed = NumericProperty(5) # Duration for one full hue cycle (seconds)

    def __init__(self, **kwargs):
        self._segments = [] # Initialize _segments FIRST
        super().__init__(**kwargs) # Then call parent __init__
        self.size_hint_y = None
        self.height = 3 # Fixed height

        # Create segments on the canvas
        with self.canvas:
            for i in range(self.num_segments):
                # Initial color calculation (can be refined)
                hue = (i / self.num_segments) * self.wave_frequency * 360
                rgb = colorsys.hsv_to_rgb(hue / 360.0, 1, 1)
                color_instruction = Color(rgba=list(rgb) + [1])
                rect_instruction = Rectangle()
                self._segments.append({'color': color_instruction, 'rect': rect_instruction})

        # Bind updates
        self.bind(pos=self._update_rects, size=self._update_rects, hue_offset=self._update_colors)

        # Start the animation using Clock for continuous update
        Clock.schedule_interval(self._animate_hue, 1/60.0) # Update ~60 times per second

    def _update_rects(self, *args):
        """Update rectangle positions and sizes."""
        if not self._segments or self.width == 0:
            return

        segment_width = self.width / self.num_segments
        for i, segment in enumerate(self._segments):
            segment['rect'].pos = (self.x + i * segment_width, self.y)
            segment['rect'].size = (segment_width, self.height)

    def _update_colors(self, *args):
        """Update segment colors based on the current hue_offset."""
        if not self._segments:
            return

        for i, segment in enumerate(self._segments):
            # Calculate hue for this segment based on position and offset
            # Use sine wave for smoother transition
            normalized_pos = i / self.num_segments
            # Map position to angle (0 to 2*pi * frequency)
            angle = normalized_pos * self.wave_frequency * 2 * math.pi
            # Add the animated offset (also converted to radians)
            offset_angle = (self.hue_offset / 360.0) * 2 * math.pi
            # Calculate hue (0-360) based on sine wave + offset
            # Sine ranges from -1 to 1. Map it to 0-1 for hue calculation.
            # We use the offset directly as the base hue shift.
            hue = (self.hue_offset + (math.sin(angle) * 30)) % 360 # Add a sine wave modulation to the base offset
            # Ensure hue is positive
            hue = hue if hue >= 0 else hue + 360

            rgb = colorsys.hsv_to_rgb(hue / 360.0, 1, 1) # Full saturation/value
            segment['color'].rgba = list(rgb) + [1]

    def _animate_hue(self, dt):
        """Update the hue offset over time."""
        # Increment hue offset based on time delta and speed
        # (360 degrees / animation_speed seconds) * dt seconds
        self.hue_offset = (self.hue_offset + (360 / self.animation_speed) * dt) % 360

    # Override property setters to trigger updates if needed, though binding should handle it
    def on_num_segments(self, instance, value):
        # Recreate segments if number changes (complex, avoid for now)
        print("Warning: Changing num_segments dynamically is not fully supported.")
        pass

    def on_size(self, instance, value):
        self._update_rects()

    def on_pos(self, instance, value):
        self._update_rects()
