from taipy.gui import Gui, State
import sys
import os

# Add project root to sys.path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.append(project_root)

# Import pages
from src.gui.pages import overview
from src.gui.pages import analytics
# from src.gui.pages import diagnostics # Will be added later
# from src.gui.pages import config_page # Renamed from config.py to avoid conflict with utils.config

from src.utils.config import AppConfig # Import AppConfig
from src.gui.styles.themes import default_theme as app_theme # To access CSS colors for themes, etc.

# Initialize our AppConfig to load .env and make CSS colors available
# This instance will be separate from the one used by Flask if Flask runs in a diff process,
# but for CSS color vars it's fine.
app_config_for_gui = AppConfig()


# Define pages for the Taipy GUI
# The structure is: {'route': PageObject}
pages = {
    "/": "<|navbar|>", # Root will show the navbar, which lists other pages
    "overview": overview.page,
    "analytics": analytics.page,
    # "diagnostics": diagnostics.page, # Uncomment when diagnostics page is created
    # "settings": config_page.page # Uncomment when config page is created
}

# Basic CSS for cards and KPIs, to be moved to custom.css later
# Using Taipy's stylekit and also allowing for custom CSS.
# The color variables will be defined in custom.css as per the plan.
# For now, we can pass some basic style, but ideally this is all in CSS files.
# gui_style string removed, styles now in custom.css

# Taipy GUI application instance
# The run_server=False is important when embedding in another framework or managing server start manually
# However, for the hybrid model, Taipy often runs its own server.
# The issue description implies Taipy GUI runs on port 5000 and Flask on 8080.
# We will start Taipy GUI's server.
taipy_gui = Gui(pages=pages)

# We need to define the `on_init` for the overview page at the Gui level if it's the root,
# or ensure it's called per-session. Taipy's `on_init` on a page object is usually for single-page apps.
# For multi-page, global state or specific page `on_init` via `Gui(on_init=...)` might be needed
# or using `State.assign` in the page module.
# The `overview.on_init` should be picked up by Taipy when the `overview` page is loaded.

def initialize_global_state(state: State):
    """
    Initialize any global state variables if needed when the application starts.
    This is called once per application instance.
    """
    print("Taipy GUI application on_init: Initializing global state (if any).")
    # Example: state.global_app_start_time = datetime.datetime.now()
    pass


def on_gui_change(state: State, fn_name: str, payload: dict):
    """
    Global callback for GUI interactions. Can be used for logging or global actions.
    """
    print(f"GUI change: Function '{fn_name}' triggered.")
    # Example: if fn_name == "update_all_data": state.last_manual_refresh = datetime.datetime.now()
    pass


# Configure Taipy GUI
# title, favicon, dark_mode, stylekit etc.
# taipy_gui.title = "Temperature Monitor Dashboard"
# taipy_gui.favicon = "/path/to/favicon.png" # Will use Flask to serve if from assets
# taipy_gui.stylekit = True # Use Taipy's default styling improvements
# taipy_gui.css_file = ["/path/to/custom.css"] # Later step


def get_taipy_app():
    """Returns the configured Taipy Gui object for the main application runner."""

    # Configure app properties
    taipy_gui.title = "TempMon Dashboard"
    # Assuming favicon is served by Flask from root or assets
    # Taipy can also take a file path for favicon. For now, let's assume browser looks for /favicon.ico
    # We can also specify a theme or CSS files here.
    # taipy_gui.add_shared_variable("app_config_for_gui", app_config_for_gui)
    # This makes app_config_for_gui accessible as {app_config_for_gui.CSS_COLORS.galaxy} in Markdown,
    # but it's generally better to use CSS variables defined in a CSS file.

    # Register global callbacks
    # taipy_gui.on_init = initialize_global_state # This is for app-level init, not page
    taipy_gui.on_change = on_gui_change

    # Set up a stylekit theme (optional, for better default styling)
    # Using a dictionary for theme to apply our custom colors
    # This is a basic way; a full themes.py as planned is more robust.
    theme_config = {
        "palette": {
            "background": {
                "default": app_config_for_gui.CSS_COLORS['galaxy'], # Main background
                "paper": app_config_for_gui.CSS_COLORS['space']    # Card/paper background
            },
            "text": {
                "primary": app_config_for_gui.CSS_COLORS['starlight'],
                "secondary": app_config_for_gui.CSS_COLORS['nebula']
            },
            "primary": {"main": app_config_for_gui.CSS_COLORS['flare']}, # Accent for buttons etc.
            "secondary": {"main": app_config_for_gui.CSS_COLORS['electron']},
            # Add more palette colors as needed by Taipy's theme structure
        },
        # Define overrides for specific components if necessary
    }

    # Add custom CSS file path (will be created in a later step)
    # For now, the basic style is embedded in gui_style string.
    # When custom.css is ready:
    # print(f"Attempting to load CSS from: {custom_css_path}")


    # Apply custom theme and CSS
    taipy_gui.theme = app_theme
    custom_css_path = os.path.join(project_root, "src", "gui", "styles", "custom.css")
    taipy_gui.css_file = custom_css_path
    print(f"Loading custom CSS from: {custom_css_path}")
    print(f"Applying custom theme.")
    return taipy_gui
