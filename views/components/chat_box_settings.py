from kivy.uix.boxlayout import BoxLayout
from kivy.properties import BooleanProperty, ListProperty, StringProperty
from kivy.event import EventDispatcher
from kivy.lang import Builder
from kivy.clock import Clock # Added import

# Load the KV file after the class definition
Builder.load_file('views/components/chat_box_settings.kv')

class ChatBoxSettings(BoxLayout, EventDispatcher):
    """
    Component containing TTS checkbox, Clear History button, and LLM Selector.
    Dispatches events: 'on_clear_history', 'on_selected_provider', 'on_selected_model'.
    """
    tts_enabled = BooleanProperty(False)

    # --- LLM Properties (Passed down from parent) ---
    llm_providers = ListProperty([])
    llm_models = ListProperty([])
    selected_provider = StringProperty("")
    selected_model = StringProperty("")

    # Register the event dispatcher
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.register_event_type('on_clear_history')
        # Register NEW event names to bubble up from LLMSelector
        self.register_event_type('on_llm_provider_changed_event')
        self.register_event_type('on_llm_model_changed_event')

    def on_clear_history(self, *args):
        """
        Default handler for the on_clear_history event.
        """
        pass # Implementation is handled by the widget using this component

    # --- Handlers for NEW dispatched events ---
    def on_llm_provider_changed_event(self, provider_name):
        """
        Handler for the 'on_llm_provider_changed_event' dispatched from KV.
        """
        print(f"DEBUG: ChatBoxSettings: Event 'on_llm_provider_changed_event' dispatched with value: {provider_name}")
        # This event is bound by the parent (ChatTab) in chat_tab.kv
        pass

    def on_llm_model_changed_event(self, model_name):
        """
        Handler for the 'on_llm_model_changed_event' dispatched from KV.
        """
        print(f"DEBUG: ChatBoxSettings: Event 'on_llm_model_changed_event' dispatched with value: {model_name}")
        # This event is bound by the parent (ChatTab) in chat_tab.kv
        pass

    # --- Property Observers for Debugging (Kivy's on_<property_name>) ---
    def on_llm_models(self, instance, value):
        """Called by Kivy when self.llm_models changes."""
        print(f"DEBUG: ChatBoxSettings: own llm_models changed to: {value}")
        if hasattr(self, 'ids') and 'llm_selector_in_settings' in self.ids:
            llm_selector_widget = self.ids.llm_selector_in_settings
            # Check if the widget's property matches AFTER Kivy's binding should have updated it
            Clock.schedule_once(lambda dt, w=llm_selector_widget: print(f"DEBUG: ChatBoxSettings: internal LLMSelector's llm_models is: {w.llm_models}"), 0)
        else:
            print(f"DEBUG: ChatBoxSettings: llm_selector_in_settings not found in ids during on_llm_models.")

    def on_selected_provider(self, instance, value): # Kivy property observer
        """Called by Kivy when self.selected_provider KivyProperty changes."""
        print(f"DEBUG: ChatBoxSettings: own selected_provider (property observer) changed to: {value}")
        if hasattr(self, 'ids') and 'llm_selector_in_settings' in self.ids:
            llm_selector_widget = self.ids.llm_selector_in_settings
            Clock.schedule_once(lambda dt, w=llm_selector_widget: print(f"DEBUG: ChatBoxSettings: internal LLMSelector's selected_provider is: {w.selected_provider}"), 0)
        else:
            print(f"DEBUG: ChatBoxSettings: llm_selector_in_settings not found in ids during on_selected_provider (property observer).")

    def on_selected_model(self, instance, value): # Kivy property observer
        """Called by Kivy when self.selected_model KivyProperty changes."""
        print(f"DEBUG: ChatBoxSettings: own selected_model (property observer) changed to: {value}")
        if hasattr(self, 'ids') and 'llm_selector_in_settings' in self.ids:
            llm_selector_widget = self.ids.llm_selector_in_settings
            Clock.schedule_once(lambda dt, w=llm_selector_widget: print(f"DEBUG: ChatBoxSettings: internal LLMSelector's selected_model is: {w.selected_model}"), 0)
        else:
            print(f"DEBUG: ChatBoxSettings: llm_selector_in_settings not found in ids during on_selected_model (property observer).")
