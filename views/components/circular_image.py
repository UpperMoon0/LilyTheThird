from kivy.uix.widget import Widget
from kivy.uix.image import Image
from kivy.properties import StringProperty, ListProperty, ObjectProperty
from kivy.graphics import StencilPush, StencilUse, Ellipse, StencilUnUse, StencilPop, Rectangle, Color
from kivy.lang import Builder
from kivy.metrics import dp

# Using Builder to define canvas instructions is often cleaner
Builder.load_string("""
<CircularImage>:
    canvas.before:
        StencilPush
        Ellipse:
            pos: self.pos  # Use the widget's position
            size: self.size # Use the widget's size for the stencil shape
        StencilUse

    canvas:
        # Draw the image centered and contained within the widget bounds
        # We'll use a Rectangle with the image texture
        Color:
            rgba: 1, 1, 1, 1 # Ensure image is not tinted
        Rectangle:
            texture: self.image_texture
            size: self._image_draw_size # Calculated size to maintain aspect ratio
            pos: self._image_draw_pos   # Calculated position to center the contained image

    canvas.after:
        StencilUnUse
        Ellipse:
            pos: self.pos
            size: self.size
        StencilPop
""")

class CircularImage(Widget):
    """
    A widget that displays an image cropped into a circle.
    It ensures the image content maintains its aspect ratio ('contain')
    and the circular mask adapts correctly on resize.
    """
    source = StringProperty('')
    image_texture = ObjectProperty(None, allownone=True)

    # Internal properties to calculate drawing position and size
    _image_draw_pos = ListProperty([0, 0])
    _image_draw_size = ListProperty([0, 0])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._image = Image() # Internal image to load texture
        self.bind(source=self._update_image_source,
                  pos=self._update_image_draw_params,
                  size=self._update_image_draw_params)

    def _update_image_source(self, instance, value):
        """Load the texture when the source changes."""
        self._image.source = value
        self.image_texture = self._image.texture
        self._update_image_draw_params() # Update drawing params when texture is loaded/changed

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

