import kivy
kivy.require('2.0.0') # Ensure Kivy version compatibility

import kivy
kivy.require('2.0.0') # Ensure Kivy version compatibility

from kivy.app import App
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
# import threading # No longer needed for widget instantiation
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label # Import Label for loading indicator
from kivy.core.window import Window
from kivy.clock import Clock # Import Clock

from views.vtube_tab import VTubeTab
from views.chat_tab import ChatTab
from views.discord_tab import DiscordTab

# Optional: Set a default window size
Window.size = (800, 700)

class MainAppLayout(BoxLayout):
    """Root layout containing the TabbedPanel."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Orientation is vertical by default for BoxLayout

        # Create the TabbedPanel
        # Set do_default_tab=True and ensure default_tab is set after adding the desired tab.
        tab_panel = TabbedPanel(do_default_tab=True, tab_pos='top_mid', tab_width=150) # Default tab enabled, tabs on top

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

        # Add the TabbedPanel to the root layout
        self.add_widget(tab_panel)

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
        print(f"MainAppLayout: Creating content for {tab_item.text}...")
        try:
            # Instantiate the actual content widget (must be on main thread)
            content = content_class()
            print(f"MainAppLayout: Content for {tab_item.text} instantiated.")
            # Add the content directly (already on main thread)
            tab_item.clear_widgets() # Remove the 'Loading...' label
            tab_item.add_widget(content) # Add the actual content widget
            print(f"MainAppLayout: Content added to {tab_item.text}.")
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
        # Set an icon if you have one
        # self.icon = 'assets/icon.png'
        return MainAppLayout()

if __name__ == '__main__':
    LilyKivyApp().run()
