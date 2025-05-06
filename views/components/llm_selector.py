from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty, ListProperty
from kivy.lang import Builder

Builder.load_file('views/components/llm_selector.kv')

class LLMSelector(BoxLayout):
    """
    A reusable Kivy widget for selecting LLM Provider and Model.

    This widget exposes properties that can be bound to by parent widgets
    (like ChatTab or DiscordTab) which handle the actual logic via a mixin
    (e.g., LLMConfigMixin).
    """
    # --- Properties for Binding ---
    # These properties are intended to be bound bidirectionally (using kv notation like `root.parent_property`)
    # by the parent widget that uses this component.
    selected_provider = StringProperty("")
    selected_model = StringProperty("")
    llm_providers = ListProperty([])
    llm_models = ListProperty([])

    # --- Customizable Labels ---
    provider_label_text = StringProperty("LLM Provider:") # Default label text
    model_label_text = StringProperty("LLM Model:")     # Default label text

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Orientation and other layout properties are set in the kv file.
