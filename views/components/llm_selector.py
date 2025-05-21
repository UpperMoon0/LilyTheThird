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
        # Bind internal UI changes to dispatch events or update properties
        # This assumes the Kivy lang file correctly binds spinner/dropdown `text` to these properties.
        # If not, direct bindings to the spinner's on_text event would be needed here.

    # The following methods are examples if direct binding in __init__ is preferred
    # over relying solely on kv lang for property updates from UI to these properties.
    # These would typically be connected to the `on_text` or equivalent event of the UI elements.

    def on_provider_selection_changed(self, new_provider_value):
        """
        Called when the provider selection UI element changes.
        Updates the selected_provider property, which should then propagate
        to the parent via the kv binding.
        """
        if self.selected_provider != new_provider_value:
            self.selected_provider = new_provider_value
            # The parent (e.g., ChatTab) should react to this property change.

    def on_model_selection_changed(self, new_model_value):
        """
        Called when the model selection UI element changes.
        Updates the selected_model property.
        """
        if self.selected_model != new_model_value:
            self.selected_model = new_model_value
            # The parent (e.g., ChatTab) should react to this property change.

# Example of how the kv file for LLMSelector might look (llm_selector.kv)
# This is for illustration; the actual implementation might differ.
"""
<LLMSelector>:
    orientation: 'vertical' # Or 'horizontal' as needed
    spacing: dp(5)
    padding: dp(5)

    Label:
        text: root.provider_label_text
        size_hint_y: None
        height: self.texture_size[1]

    Spinner:
        id: provider_spinner
        text: root.selected_provider if root.selected_provider else (root.llm_providers[0] if root.llm_providers else "")
        values: root.llm_providers
        size_hint_y: None
        height: dp(40)
        on_text: root.on_provider_selection_changed(self.text) # Call method on change

    Label:
        text: root.model_label_text
        size_hint_y: None
        height: self.texture_size[1]
        padding: [0, dp(10), 0, 0] # Add some top padding

    Spinner:
        id: model_spinner
        text: root.selected_model if root.selected_model else (root.llm_models[0] if root.llm_models else "")
        values: root.llm_models
        size_hint_y: None
        height: dp(40)
        disabled: not root.selected_provider # Disable if no provider selected
        on_text: root.on_model_selection_changed(self.text) # Call method on change
"""
