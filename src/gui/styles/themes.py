# Taipy Theme Configuration
# This file can define one or more theme dictionaries for Taipy.
# These themes can be applied globally or to specific pages.

# We are primarily using custom.css for styling.
# However, a Taipy theme can complement this by setting base values
# that Taipy components use, potentially referencing our CSS variables.

# Import config to access CSS_COLORS if needed, though direct use of CSS vars in custom.css is preferred.
# from src.utils.config import config

# Example of a base theme dictionary.
# Taipy's theme structure allows defining 'palette', 'layout', 'typography', etc.
# Refer to Taipy documentation for the full theme object structure.

# For our project, since custom.css defines variables at :root,
# Taipy components should inherit them if not overridden by Taipy's default theme.
# If Taipy's default theme is too strong, this theme object can be used
# to "reset" or align Taipy's component styling with our CSS variables.

dark_theme_with_css_vars = {
    "palette": {
        "background": {
            # Default background for Taipy components (e.g., dialogs, tooltips)
            "default": "var(--space)",  # Using CSS variable
            "paper": "var(--lunar)"     # Alternative background for elements like cards if not styled by .card-bg
        },
        "text": {
            "primary": "var(--starlight)",
            "secondary": "var(--nebula)",
            "disabled": "var(--comet)"
        },
        "primary": { # Used for primary actions, e.g., some button variants, highlights
            "main": "var(--flare)",
            "contrastText": "var(--starlight)"
        },
        "secondary": { # Used for secondary actions
            "main": "var(--electron)",
            "contrastText": "var(--galaxy)" # Dark text on light accent
        },
        "success": {"main": "var(--radiate)", "contrastText": "var(--galaxy)"},
        "warning": {"main": "var(--cosmic)", "contrastText": "var(--starlight)"},
        "info": {"main": "var(--sandstone)", "contrastText": "var(--galaxy)"},
        "error": {"main": "#B00020", "contrastText": "var(--starlight)"} # Example error color
    },
    # Define other theme aspects like typography, spacing, component overrides if needed.
    # "typography": {
    #     "fontFamily": "var(--taipy-font-family, 'Arial', sans-serif)",
    #     "fontSize": 16
    # },
    # "layout": {
    #     "containerMaxWidth": "lg" # Example: limit max width of page content
    # }
    # Example of overriding a specific Taipy component style (syntax depends on Taipy version)
    # "taipy_button_primary_background_color": "var(--flare)",
    # "taipy_button_primary_text_color": "var(--starlight)",
}

# You can define multiple themes, e.g., a light_theme.
# For this project, we focus on the dark space theme.
default_theme = dark_theme_with_css_vars

if __name__ == '__main__':
    # This allows you to print the theme for inspection if you run this file directly.
    import json
    print("Default Theme Configuration:")
    print(json.dumps(default_theme, indent=4))
