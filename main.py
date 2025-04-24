from kivy.config import Config
Config.remove_option('input', 'wm_pen') # Disable problematic touch provider
Config.remove_option('input', 'wm_touch') # Disable problematic touch provider

import kivy
kivy.require('2.0.0') # Ensure Kivy version compatibility

from kivy.app import App
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label # Import Label for loading indicator
from kivy.core.window import Window # Import Window
from kivy.clock import Clock # Import Clock

# Import Views and Components
from views.vtube_tab import VTubeTab
from views.chat_tab import ChatTab
from views.discord_tab import DiscordTab

class MainAppLayout(BoxLayout):
    """Root layout containing the TabbedPanel."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Orientation is vertical by default for BoxLayout

        # Create the TabbedPanel
        # Set do_default_tab=True and ensure default_tab is set after adding the desired tab.
        tab_panel = TabbedPanel(do_default_tab=True, tab_pos='top_left') # Default tab enabled, tabs on top_left, removed fixed width

        # --- Create Chat Tab Item (Placeholder) ---
        chat_tab_item = TabbedPanelItem(text='Chat')
        chat_tab_item.add_widget(Label(text='Loading Chat...')) # Placeholder
        tab_panel.add_widget(chat_tab_item)
        # Set Chat Tab as the default selected tab
        tab_panel.default_tab = chat_tab_item # Set this AFTER adding the chat tab
        self.chat_tab_item = chat_tab_item # Store reference

        # --- Create Discord Tab Item (Placeholder) ---
        discord_tab_item = TabbedPanelItem(text='Discord')
        discord_tab_item.add_widget(Label(text='Loading Discord...')) # Placeholder
        tab_panel.add_widget(discord_tab_item)
        self.discord_tab_item = discord_tab_item # Store reference

        # --- Create VTube Tab Item (Placeholder) ---
        vtube_tab_item = TabbedPanelItem(text='VTube')
        vtube_tab_item.add_widget(Label(text='Loading VTube...')) # Placeholder
        tab_panel.add_widget(vtube_tab_item)
        self.vtube_tab_item = vtube_tab_item # Store reference

        # Store the tab_panel as an instance attribute
        self.tab_panel = tab_panel
        # --- RGB Strip removed from here ---

        # Add the TabbedPanel to the root layout
        self.add_widget(self.tab_panel)

        # Schedule the creation of tab contents on the main thread after the layout is built
        Clock.schedule_once(self._create_tabs)

    def _create_tabs(self, dt):
        """Creates and adds the content for each tab on the main thread."""
        print("MainAppLayout: Creating tab content on main thread.")
        self._create_tab_content(self.chat_tab_item, ChatTab)
        self._create_tab_content(self.discord_tab_item, DiscordTab)
        self._create_tab_content(self.vtube_tab_item, VTubeTab)

    def _create_tab_content(self, tab_item, content_class):
        """Instantiates and adds the content widget to the tab item."""
        try:
            # Instantiate the actual content widget (must be on main thread)
            content = content_class()
            print(f"MainAppLayout: Content for {tab_item.text} instantiated.")
            tab_item.clear_widgets() 
            tab_item.add_widget(content) 
        except Exception as e:
            print(f"MainAppLayout: Error creating content for {tab_item.text}: {e}")
            # Display error message in the tab
            error_message = f"Error loading {tab_item.text}:\n{e}"
            tab_item.clear_widgets()
            tab_item.add_widget(Label(text=error_message, halign='center', valign='middle'))


class LilyKivyApp(App):
    """Main Kivy Application Class."""
    def build(self):
        self.title = "Lily AI - Kivy Interface"
        Clock.schedule_once(self.maximize_window, 0)
        return MainAppLayout()

    def maximize_window(self, dt):
        """Maximizes the application window."""
        Window.maximize()

if __name__ == '__main__':
    LilyKivyApp().run()
