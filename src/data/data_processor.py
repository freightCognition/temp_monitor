import logging
import datetime
import pandas as pd # For easier data manipulation and stats
import os # For checking DB file size in test
import random # For generating varied test data

# Add project root to sys.path to allow imports like src.data.database
import sys
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.data import database
from src.utils.config import config # For default period hours, etc.

logger = logging.getLogger(__name__)

def get_formatted_historical_data(metric, period_hours=None, start_time_dt=None, end_time_dt=None):
    """
    Fetches historical data and formats it, typically for charts.
    Returns a dictionary with 'timestamps' and 'values' lists.
    If data is empty or an error occurs, returns empty lists.

    Args:
        metric (str): The metric to fetch (e.g., 'temperature_c', 'humidity').
        period_hours (int, optional): Duration in hours to fetch data for.
                                     Defaults to config.DEFAULT_HISTORY_PERIOD_HOURS.
        start_time_dt (datetime.datetime, optional): Specific start time.
        end_time_dt (datetime.datetime, optional): Specific end time.
    """
    if period_hours is None and start_time_dt is None:
        period_hours = config.DEFAULT_HISTORY_PERIOD_HOURS
        logger.debug(f"Defaulting to period_hours: {period_hours}h for metric {metric}")

    try:
        # database.get_historical_data expects datetime objects for start/end times
        raw_data = database.get_historical_data(
            metric=metric,
            period_hours=period_hours,
            start_time=start_time_dt,
            end_time=end_time_dt
        ) # Returns list of dicts: [{'timestamp': str_iso, 'value': float}, ...]

        if not raw_data:
            logger.info(f"No historical data found for metric '{metric}' with given parameters.")
            return {"timestamps": [], "values": []}

        # Convert to DataFrame for easier processing if needed, or process directly
        # Timestamps from DB are ISO format strings, e.g., '2023-10-27 10:00:00'
        # For Plotly/Taipy, string timestamps are often fine, but datetime objects can be more robust.
        timestamps = [item['timestamp'] for item in raw_data]
        values = [item['value'] for item in raw_data]

        logger.debug(f"Formatted {len(values)} data points for metric '{metric}'.")
        return {"timestamps": timestamps, "values": values}

    except Exception as e:
        logger.error(f"Error formatting historical data for metric '{metric}': {e}")
        return {"timestamps": [], "values": []}


def calculate_statistics(metric, period_hours=None, start_time_dt=None, end_time_dt=None):
    """
    Calculates min, max, average, and count for a given metric over a period.

    Args:
        metric (str): The metric (e.g., 'temperature_c', 'humidity').
        period_hours (int, optional): Duration in hours. Defaults to config.DEFAULT_HISTORY_PERIOD_HOURS.
        start_time_dt (datetime.datetime, optional): Specific start time.
        end_time_dt (datetime.datetime, optional): Specific end time.

    Returns:
        dict: Contains 'min', 'max', 'avg', 'count', 'metric', 'period_hours'.
              Returns None for values if no data.
    """
    if period_hours is None and start_time_dt is None:
        period_hours = config.DEFAULT_HISTORY_PERIOD_HOURS

    data_points = get_formatted_historical_data(
        metric=metric,
        period_hours=period_hours,
        start_time_dt=start_time_dt,
        end_time_dt=end_time_dt
    )

    values = data_points.get("values", [])

    if not values:
        logger.info(f"No data to calculate statistics for metric '{metric}'.")
        return {
            "metric": metric, "period_hours": period_hours,
            "start_time": start_time_dt.isoformat() if start_time_dt else None,
            "end_time": end_time_dt.isoformat() if end_time_dt else None,
            "min": None, "max": None, "avg": None, "count": 0, "trend": "neutral"
        }

    df = pd.DataFrame(values, columns=['value'])

    stats = {
        "metric": metric,
        "period_hours": period_hours,
        "start_time": start_time_dt.isoformat() if start_time_dt else None,
        "end_time": end_time_dt.isoformat() if end_time_dt else None,
        "min": round(df['value'].min(), 2),
        "max": round(df['value'].max(), 2),
        "avg": round(df['value'].mean(), 2),
        "count": len(df)
    }

    # Basic trend indicator (comparing first half avg vs second half avg)
    if len(df) >= 4: # Need at least a few points to compare
        mid_point = len(df) // 2
        first_half_avg = df['value'].iloc[:mid_point].mean()
        second_half_avg = df['value'].iloc[mid_point:].mean()
        if second_half_avg > first_half_avg * 1.02: # Arbitrary 2% increase
             stats["trend"] = "rising"
        elif second_half_avg < first_half_avg * 0.98: # Arbitrary 2% decrease
             stats["trend"] = "falling"
        else:
             stats["trend"] = "stable"
    else:
        stats["trend"] = "neutral"

    logger.debug(f"Calculated statistics for metric '{metric}': {stats}")
    return stats

def get_overall_summary_stats():
    """Calculates a summary of statistics for key metrics."""
    # For now, let's use default period (e.g., 24h) for summary.
    # This can be expanded based on requirements.

    temp_stats = calculate_statistics('temperature_c', period_hours=24)
    hum_stats = calculate_statistics('humidity', period_hours=24)

    # Get total record count from the database
    record_count = 0
    try:
        with database.get_db_connection() as conn:
            count_result = conn.execute("SELECT COUNT(id) FROM sensor_readings").fetchone()
            if count_result:
                record_count = count_result[0]
    except Exception as e:
        logger.error(f"Failed to get total record count for summary stats: {e}")

    summary = {
        "temperature_summary_24h": temp_stats,
        "humidity_summary_24h": hum_stats,
        "total_records_in_db": record_count,
        "last_updated": datetime.datetime.now().isoformat()
        # In a real scenario, 'last_updated' might refer to the latest data point's timestamp
    }
    logger.info(f"Generated overall summary stats: {summary}")
    return summary

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    logger.info("Testing Data Processor module...")

    # --- Database Setup for Testing ---
    try:
        # Ensure the database directory exists (config should handle this, but double check for direct script run)
        db_dir = os.path.dirname(database.DATABASE_PATH)
        if not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
            logger.info(f"Main test block: Created database directory {db_dir}")

        print(f"Using database at: {database.DATABASE_PATH}")
        # Ensure tables are created using the already imported database module
        with database.get_db_connection() as conn:
            database.create_tables(conn)
        print("Database tables ensured by data_processor's test setup.")


        # Add varied data for stats testing
        print("Adding/Ensuring varied data for stats testing...")
        now = datetime.datetime.now()
        base_temp, base_hum = 25, 55

        # Clear old test data to make tests somewhat idempotent regarding counts
        cutoff_for_old_test_data = now - datetime.timedelta(hours=48)
        with database.get_db_connection() as conn:
            # Delete data older than 48h to keep test set consistent for count checks
            # but also delete very recent data that might interfere with "last 5 mins" tests
            conn.execute("DELETE FROM sensor_readings WHERE timestamp < ? OR timestamp > ?",
                         (cutoff_for_old_test_data, now - datetime.timedelta(minutes=10)))
            conn.commit()
            print(f"Cleared sensor_readings older than 48h or newer than 10 mins ago to ensure test consistency.")

        for i in range(48): # 48 hours of data, one per hour, ending 1 hour ago
            ts = now - datetime.timedelta(hours=i+1) # Data from 1 hour ago to 48 hours ago
            temp = base_temp + (i % 5) - 2 + random.uniform(-0.5, 0.5)
            hum = base_hum + (i % 10) - 5 + random.uniform(-1, 1)
            cpu_temp = temp + 10 + random.uniform(-1,1)
            raw_temp = temp + random.uniform(-0.2, 0.2)
            with database.get_db_connection() as conn:
                conn.execute("INSERT INTO sensor_readings (timestamp, temperature_c, humidity, cpu_temperature, raw_temperature) VALUES (?, ?, ?, ?, ?)",
                             (ts.strftime('%Y-%m-%d %H:%M:%S'), round(temp,1), round(hum,1), round(cpu_temp,1), round(raw_temp,1)))
                conn.commit()
        print(f"Inserted/Updated 48 hourly records for testing stats (1h ago to 48h ago).")

        # Add a couple of very recent records for "last X minutes" tests
        database.insert_sensor_reading(20.0, 50.0, 30.0, 20.5) # Uses CURRENT_TIMESTAMP
        database.insert_sensor_reading(20.1, 50.1, 30.1, 20.6) # Uses CURRENT_TIMESTAMP
        print("Added 2 very recent sensor readings.")


    except ImportError as e:
        logger.error(f"Could not import for setting up test data: {e}. Ensure PYTHONPATH is correct or run from project root.")
    except Exception as e:
        logger.error(f"Error setting up test data: {e}", exc_info=True)


    print("\n--- Testing get_formatted_historical_data ---")
    temp_data = get_formatted_historical_data('temperature_c', period_hours=48)
    if temp_data['values']:
        print(f"Fetched {len(temp_data['values'])} temperature data points for last 48h.")
        # print(f"First few timestamps: {temp_data['timestamps'][:3]}")
        # print(f"First few values: {temp_data['values'][:3]}")
    else:
        print("No temperature data fetched for last 48h.")

    # Test fetching data for the last 2 hours (should include the 2 very recent + 1 or 2 hourly)
    hum_data = get_formatted_historical_data('humidity', period_hours=2)
    if hum_data['values']:
        print(f"Fetched {len(hum_data['values'])} humidity data points for last 2 hours.")
    else:
        print("No humidity data fetched for last 2 hours.")

    print("\n--- Testing with specific time range (3h to 6h ago) ---")
    start_dt = datetime.datetime.now() - datetime.timedelta(hours=6)
    end_dt = datetime.datetime.now() - datetime.timedelta(hours=3)
    temp_data_range = get_formatted_historical_data('temperature_c', start_time_dt=start_dt, end_time_dt=end_dt)
    if temp_data_range['values']:
        print(f"Fetched {len(temp_data_range['values'])} temperature data points for specific range (3h to 6h ago).")
        # print(f"Timestamps: {temp_data_range['timestamps']}")
    else:
        print(f"No temperature data fetched for range {start_dt} to {end_dt}.")


    print("\n--- Testing calculate_statistics ---")
    temp_stats_24h = calculate_statistics('temperature_c', period_hours=24)
    print(f"Temperature Stats (last 24h): {temp_stats_24h}")

    hum_stats_48h = calculate_statistics('humidity', period_hours=48)
    print(f"Humidity Stats (last 48h): {hum_stats_48h}")

    print("\n--- Testing stats for a very recent period (last 5 minutes) ---")
    start_recent = datetime.datetime.now() - datetime.timedelta(minutes=5)
    end_recent = datetime.datetime.now()
    # Use a metric that has recent data
    recent_temp_stats = calculate_statistics('temperature_c', start_time_dt=start_recent, end_time_dt=end_recent)
    print(f"Temperature Stats (last 5 mins): {recent_temp_stats}")


    print("\n--- Testing get_overall_summary_stats ---")
    summary = get_overall_summary_stats()
    print(f"Overall Summary Stats: {summary}")

    print("\n--- Testing stats for a metric with no data (example: 'non_existent_metric') ---")
    non_existent_metric_stats = calculate_statistics('non_existent_metric', period_hours=24)
    print(f"Stats for non_existent_metric: {non_existent_metric_stats}")


    logger.info("Data Processor module test finished.")
