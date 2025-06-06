from taipy.gui import Markdown, State, Gui, notify
import pandas as pd
import datetime

# Ensure project root is in sys.path for imports
import sys
import os
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.append(project_root)

from src.utils.config import config
from src.data import data_processor
from src.gui.pages.overview import COMMON_CHART_LAYOUT # Reuse common layout

# --- Page State Variables ---
# Time range selection for historical data
# Lov: List of values for selector. First element is default.
time_range_selector = ["Last 7 Days", "Last 24 Hours", "Last 30 Days"]
selected_time_range = "Last 7 Days" # Default selection

# DataFrames for charts
historical_temp_df = pd.DataFrame({"timestamp": [], "temperature_c": []})
historical_humidity_df = pd.DataFrame({"timestamp": [], "humidity": []})
correlation_df = pd.DataFrame({"temperature_c": [], "humidity": [], "timestamp": []}) # For scatter plot

# Chart Properties (reusing some from overview)
hist_temp_chart_props = {
    "x": "timestamp", "y": "temperature_c", "type": "scatter", "mode": "lines+markers", "name": "Temperature",
    "marker": {"color": config.CSS_COLORS['electron'], "size": 4},
    "line": {"color": config.CSS_COLORS['electron'], "width": 1.5}
}

hist_humidity_chart_props = {
    "x": "timestamp", "y": "humidity", "type": "scatter", "mode": "lines+markers", "name": "Humidity",
    "marker": {"color": config.CSS_COLORS['cosmic'], "size": 4},
    "line": {"color": config.CSS_COLORS['cosmic'], "width": 1.5}
}

correlation_chart_props = {
    "x": "temperature_c",
    "y": "humidity",
    "type": "scatter",
    "mode": "markers",
    "name": "Temp vs Humidity",
    "text": "timestamp", # Show timestamp on hover
    "marker": {
        "color": config.CSS_COLORS['flare'], "size": 6,
        "opacity": 0.7,
        "line": {"width": 0.5, "color": config.CSS_COLORS['nebula']}
    }
}
correlation_layout_specific = {
    **COMMON_CHART_LAYOUT, # Inherit common settings
    "xaxis": {**COMMON_CHART_LAYOUT["xaxis"], "title": "Temperature (°C)"},
    "yaxis": {**COMMON_CHART_LAYOUT["yaxis"], "title": "Humidity (%)"}
}


# --- Helper function to parse time range string ---
def parse_time_range_to_hours(time_range_str):
    if "24 Hours" in time_range_str:
        return 24
    elif "7 Days" in time_range_str:
        return 24 * 7
    elif "30 Days" in time_range_str:
        return 24 * 30
    return 24 # Default

# --- Callback Functions ---
def update_analytics_charts(state: State):
    """Updates all charts on the analytics page based on the selected time range."""
    print(f"Analytics page: Updating charts for time range '{state.selected_time_range}'")
    period_hours = parse_time_range_to_hours(state.selected_time_range)

    try:
        # Temperature History
        temp_data = data_processor.get_formatted_historical_data('temperature_c', period_hours=period_hours)
        if temp_data["timestamps"]:
            state.historical_temp_df = pd.DataFrame({
                "timestamp": pd.to_datetime(temp_data["timestamps"]),
                "temperature_c": temp_data["values"]
            })
            print(f"Analytics: Temp chart updated with {len(temp_data['values'])} points.")
        else:
            state.historical_temp_df = pd.DataFrame({"timestamp": [], "temperature_c": []})
            print("Analytics: No temperature data for selected range.")

        # Humidity History
        hum_data = data_processor.get_formatted_historical_data('humidity', period_hours=period_hours)
        if hum_data["timestamps"]:
            state.historical_humidity_df = pd.DataFrame({
                "timestamp": pd.to_datetime(hum_data["timestamps"]),
                "humidity": hum_data["values"]
            })
            print(f"Analytics: Humidity chart updated with {len(hum_data['values'])} points.")
        else:
            state.historical_humidity_df = pd.DataFrame({"timestamp": [], "humidity": []})
            print("Analytics: No humidity data for selected range.")

        # Correlation Data: Need both temp and humidity for the same timestamps
        # This requires a bit more sophisticated data fetching, e.g., joining or aligning.
        # For simplicity, data_processor could offer a function for this.
        # Or, we fetch separately and merge.
        if temp_data["timestamps"] and hum_data["timestamps"]:
            # A simple merge/alignment strategy:
            # Create DataFrames and merge on timestamp. This handles missing data in one metric.
            df_temp = pd.DataFrame({'timestamp': pd.to_datetime(temp_data["timestamps"]), 'temperature_c': temp_data["values"]})
            df_hum = pd.DataFrame({'timestamp': pd.to_datetime(hum_data["timestamps"]), 'humidity': hum_data["values"]})

            # Merge on timestamp; how='inner' ensures we only get points where both exist
            merged_df = pd.merge(df_temp, df_hum, on="timestamp", how="inner")

            # For scatter plot, we want to show the timestamp on hover.
            # Plotly can take a 'text' field in its data for hover info.
            # Ensure timestamp is string for hover text if needed.
            merged_df['timestamp_str'] = merged_df['timestamp'].dt.strftime('%Y-%m-%d %H:%M')

            state.correlation_df = pd.DataFrame({
                "temperature_c": merged_df["temperature_c"],
                "humidity": merged_df["humidity"],
                "timestamp": merged_df["timestamp_str"] # Use string version for hover
            })
            print(f"Analytics: Correlation plot updated with {len(state.correlation_df)} points.")
        else:
            state.correlation_df = pd.DataFrame({"temperature_c": [], "humidity": [], "timestamp": []})
            print("Analytics: Not enough data for correlation plot.")

        notify(state, "info", f"Analytics charts updated for {state.selected_time_range}.")

    except Exception as e:
        print(f"Error updating analytics charts: {e}")
        notify(state, "error", f"Failed to update analytics charts: {e}")


def on_analytics_change(state: State, var_name: str, value: any):
    """Called when a state variable changes on the analytics page."""
    if var_name == "selected_time_range":
        print(f"Analytics: Time range changed to {value}. Triggering chart update.")
        update_analytics_charts(state)

def on_analytics_init(state: State):
    """Called when the analytics page is first initialized for a client session."""
    print("Analytics page on_init called. Performing initial chart data load.")
    # Set default time range if not already set (it should be by variable definition)
    # state.selected_time_range = time_range_selector[0]
    update_analytics_charts(state) # Load data for the default time range
    print("Initial data load complete for analytics page.")


# --- Page Definition ---
analytics_page_md = Markdown("""
# Analytics Dashboard

Select Time Range: <|{selected_time_range}|selector|lov={time_range_selector}|dropdown=True|on_change=on_analytics_change|>
<br/>

<|part|class_name=chart_container|
## Historical Temperature Trend
<|{historical_temp_df}|chart|properties={hist_temp_chart_props}|layout={COMMON_CHART_LAYOUT}|height=450px|>
|>

<|part|class_name=chart_container|
## Historical Humidity Trend
<|{historical_humidity_df}|chart|properties={hist_humidity_chart_props}|layout={COMMON_CHART_LAYOUT}|height=450px|>
|>

<|part|class_name=chart_container|
## Temperature vs. Humidity Correlation
<|{correlation_df}|chart|properties={correlation_chart_props}|layout={correlation_layout_specific}|height=500px|>
|>
""")

page = analytics_page_md
