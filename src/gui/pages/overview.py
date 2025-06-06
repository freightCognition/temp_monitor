from taipy.gui import Markdown, State, Gui, notify
import pandas as pd # Taipy charts often work well with pandas DataFrames
import datetime

# Import relevant functions from our project
# Need to ensure PYTHONPATH allows these imports if running Taipy app directly from src/gui
import sys
import os
# Add project root to sys.path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.append(project_root)

from src.utils.config import config
from src.data import sensor_manager # For current readings
from src.data import data_processor # For historical chart data
from src.data import database # For initial data load or direct queries if needed

# --- Taipy Page State Variables ---
# These variables will hold the data displayed on the page
# and will be updated by callback functions.

# For KPI cards
current_temp_c = 20.0
current_humidity = 50.0
last_sensor_update_time = "Never"
cpu_temp_kpi = "N/A"

# For charts - Taipy typically binds to DataFrames or dicts for charts
# Initial empty DataFrame for temperature chart
temp_chart_df = pd.DataFrame({
    "timestamp": pd.to_datetime([]),
    "temperature_c": []
})
# Initial empty DataFrame for humidity chart
humidity_chart_df = pd.DataFrame({
    "timestamp": pd.to_datetime([]),
    "humidity": []
})

# Chart configurations (as per issue description, adapted)
# These are Plotly layout configurations
# Galaxy: #261230, Space: #30173D, Nebula: #CDCBFB, Rock: #78876E, Starlight: #F4F4F1, Comet: #6F5D6F
# Electron: #46EBE1 (temp), Cosmic: #DE5FE9 (humidity)

COMMON_CHART_LAYOUT = {
    "plot_bgcolor": config.CSS_COLORS['galaxy'],  # Galaxy background
    "paper_bgcolor": config.CSS_COLORS['space'], # Space background for the area around plot
    "font": {"color": config.CSS_COLORS['starlight']}, # Starlight text
    "xaxis": {
        "gridcolor": config.CSS_COLORS['comet'],
        "showgrid": True,
        "zeroline": False,
        "linecolor": config.CSS_COLORS['nebula'],
        "titlefont": {"color": config.CSS_COLORS['nebula']},
        "tickfont": {"color": config.CSS_COLORS['nebula']}
    },
    "yaxis": {
        "gridcolor": config.CSS_COLORS['comet'],
        "showgrid": True,
        "zeroline": False,
        "linecolor": config.CSS_COLORS['nebula'],
        "titlefont": {"color": config.CSS_COLORS['nebula']},
        "tickfont": {"color": config.CSS_COLORS['nebula']}
    },
    "legend": {"font": {"color": config.CSS_COLORS['nebula']}},
    "margin": {"l": 60, "r": 30, "t": 50, "b": 70}, # Adjust margins
}

temp_chart_props = {
    "x": "timestamp",
    "y": "temperature_c",
    "type": "scatter",
    "mode": "lines+markers",
    "name": "Temperature",
    "marker": {"color": config.CSS_COLORS['electron'], "size": 5}, # Electron for temp
    "line": {"color": config.CSS_COLORS['electron'], "width": 2}
}

humidity_chart_props = {
    "x": "timestamp",
    "y": "humidity",
    "type": "scatter",
    "mode": "lines+markers",
    "name": "Humidity",
    "marker": {"color": config.CSS_COLORS['cosmic'], "size": 5}, # Cosmic for humidity
    "line": {"color": config.CSS_COLORS['cosmic'], "width": 2}
}


# Taipy page definition using Markdown
# Using Taipy's grid layout for better structure
overview_page_md = Markdown("""
<|layout|columns=1 1 1|class_name=kpi_container|
<|card card-bg|
### Temperature
<|{current_temp_c}|text|format=%.1f|class_name=kpi-value|> <|text|class_name=kpi-unit|>°C
|>

<|card card-bg|
### Humidity
<|{current_humidity}|text|format=%.1f|class_name=kpi-value|> <|text|class_name=kpi-unit|>%
|>

<|card card-bg|
### CPU Temp
<|{cpu_temp_kpi}|text|class_name=kpi-value|>
|>
|>

Last updated: <|{last_sensor_update_time}|text|>

<|part|class_name=chart_container|
## Temperature Trend (Last 24 Hours)
<|{temp_chart_df}|chart|properties={temp_chart_props}|layout={COMMON_CHART_LAYOUT}|height=400px|>
|>

<|part|class_name=chart_container|
## Humidity Trend (Last 24 Hours)
<|{humidity_chart_df}|chart|properties={humidity_chart_props}|layout={COMMON_CHART_LAYOUT}|height=400px|>
|>

<br/>
<|Refresh Data|button|on_action=update_all_data|>
""")


# --- Callback Functions ---
def update_live_kpis(state: State):
    """Updates the KPI cards with the latest sensor readings."""
    print("Updating live KPIs...")
    try:
        sensor_data = sensor_manager.get_all_sensor_data()
        state.current_temp_c = sensor_data.get("temperature_c", "N/A")
        state.current_humidity = sensor_data.get("humidity", "N/A")

        cpu_t = sensor_data.get("cpu_temperature")
        state.cpu_temp_kpi = f"{cpu_t}°C" if cpu_t is not None else "N/A"

        state.last_sensor_update_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"KPIs updated: Temp={state.current_temp_c}, Hum={state.current_humidity}")
    except Exception as e:
        print(f"Error updating KPIs: {e}")
        notify(state, "error", f"Failed to update KPIs: {e}")


def update_charts_data(state: State):
    """Updates the data for the temperature and humidity charts."""
    print("Updating charts data...")
    try:
        # Temperature Chart Data (last 24 hours)
        temp_hist_data = data_processor.get_formatted_historical_data(
            metric='temperature_c',
            period_hours=config.DEFAULT_HISTORY_PERIOD_HOURS
        )
        if temp_hist_data["timestamps"]:
            state.temp_chart_df = pd.DataFrame({
                "timestamp": pd.to_datetime(temp_hist_data["timestamps"]),
                "temperature_c": temp_hist_data["values"]
            })
            print(f"Temperature chart updated with {len(temp_hist_data['values'])} points.")
        else:
            print("No new temperature data for chart.")
            # Optionally, clear the chart or keep old data:
            # state.temp_chart_df = pd.DataFrame({"timestamp": [], "temperature_c": []})


        # Humidity Chart Data (last 24 hours)
        hum_hist_data = data_processor.get_formatted_historical_data(
            metric='humidity',
            period_hours=config.DEFAULT_HISTORY_PERIOD_HOURS
        )
        if hum_hist_data["timestamps"]:
            state.humidity_chart_df = pd.DataFrame({
                "timestamp": pd.to_datetime(hum_hist_data["timestamps"]),
                "humidity": hum_hist_data["values"]
            })
            print(f"Humidity chart updated with {len(hum_hist_data['values'])} points.")
        else:
            print("No new humidity data for chart.")
            # state.humidity_chart_df = pd.DataFrame({"timestamp": [], "humidity": []})

    except Exception as e:
        print(f"Error updating chart data: {e}")
        notify(state, "error", f"Failed to update chart data: {e}")

def update_all_data(state: State):
    """Global update function called by button or periodically."""
    print("Executing update_all_data...")
    update_live_kpis(state)
    update_charts_data(state)
    notify(state, "success", "Dashboard data refreshed!")

def on_init(state: State):
    """Called when the GUI is first initialized for a client session."""
    print("Overview page on_init called. Performing initial data load.")
    # Perform an initial update of all data when the page loads
    update_all_data(state)
    print("Initial data load complete for overview page.")

# This 'page' object will be imported by the main Taipy app
page = overview_page_md
