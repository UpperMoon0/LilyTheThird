import kivy
kivy.require('2.0.0') # Ensure Kivy version compatibility

from kivy.app import App
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.uix.boxlayout import BoxLayout
from kivy.lang import Builder
from kivy.core.window import Window

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

        # --- Create and add Chat Tab (First Tab) ---
        chat_tab_item = TabbedPanelItem(text='Chat')
        chat_tab_content = ChatTab() # Instantiate the ChatTab widget
        chat_tab_item.add_widget(chat_tab_content)
        tab_panel.add_widget(chat_tab_item)
        # Set Chat Tab as the default selected tab
        tab_panel.default_tab = chat_tab_item # Set this AFTER adding the chat tab

        # --- Create and add Discord Tab (Second Tab) ---
        discord_tab_item = TabbedPanelItem(text='Discord')
        discord_tab_content = DiscordTab() # Instantiate the DiscordTab widget
        discord_tab_item.add_widget(discord_tab_content)
        tab_panel.add_widget(discord_tab_item)

        # --- Create and add VTube Tab (Third Tab) ---
        vtube_tab_item = TabbedPanelItem(text='VTube')
        vtube_tab_content = VTubeTab() # Instantiate the VTubeTab widget
        vtube_tab_item.add_widget(vtube_tab_content)
        tab_panel.add_widget(vtube_tab_item)

        # Add the TabbedPanel to the root layout
        self.add_widget(tab_panel)


class LilyKivyApp(App):
    """Main Kivy Application Class."""
    def build(self):
        self.title = "Lily AI - Kivy Interface"
        # Set an icon if you have one
        # self.icon = 'assets/icon.png'
        return MainAppLayout()

if __name__ == '__main__':
    LilyKivyApp().run()
