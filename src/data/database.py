import sqlite3
import datetime
import logging
import os

# Configure logging for the database module
logger = logging.getLogger(__name__)

# Determine database path from an environment variable or use a default
DATABASE_NAME = os.environ.get("DATABASE_NAME", "temperature_monitor.db")
DATABASE_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'database', DATABASE_NAME) # Place it in the top-level 'database' folder

# Ensure the database directory exists
os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)

logger.info(f"Database path set to: {DATABASE_PATH}")

def get_db_connection():
    """Establishes a connection to the SQLite database."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row  # Access columns by name
        return conn
    except sqlite3.Error as e:
        logger.error(f"Database connection error: {e}")
        raise

def create_tables(conn):
    """Creates the necessary tables if they don't exist."""
    try:
        cursor = conn.cursor()
        # Sensor Readings Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sensor_readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                temperature_c REAL NOT NULL,
                humidity REAL NOT NULL,
                cpu_temperature REAL,
                raw_temperature REAL
            );
        """)
        # Index for timestamp for faster queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_timestamp ON sensor_readings (timestamp);
        """)
        # System Events Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                event_type TEXT NOT NULL,
                message TEXT,
                severity TEXT DEFAULT 'info' CHECK(severity IN ('info', 'warning', 'error', 'critical'))
            );
        """)
        conn.commit()
        logger.info("Tables 'sensor_readings' and 'system_events' ensured to exist.")
    except sqlite3.Error as e:
        logger.error(f"Error creating tables: {e}")
        conn.rollback() # Rollback changes if table creation fails
        raise

def insert_sensor_reading(temperature_c, humidity, cpu_temperature=None, raw_temperature=None):
    """Inserts a new sensor reading into the database."""
    sql = '''INSERT INTO sensor_readings(temperature_c, humidity, cpu_temperature, raw_temperature)
             VALUES(?,?,?,?)'''
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (temperature_c, humidity, cpu_temperature, raw_temperature))
            conn.commit()
            logger.debug(f"Inserted sensor reading: Temp={temperature_c}, Humidity={humidity}")
            return cursor.lastrowid
    except sqlite3.Error as e:
        logger.error(f"Error inserting sensor reading: {e}")
        return None

def insert_batch_sensor_readings(readings):
    """Inserts multiple sensor readings in a batch.
    'readings' should be a list of tuples:
    [(temp_c, humidity, cpu_temp, raw_temp), ...]
    """
    sql = '''INSERT INTO sensor_readings(temperature_c, humidity, cpu_temperature, raw_temperature)
             VALUES(?,?,?,?)'''
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(sql, readings)
            conn.commit()
            logger.info(f"Batch inserted {len(readings)} sensor readings.")
            return True
    except sqlite3.Error as e:
        logger.error(f"Error batch inserting sensor readings: {e}")
        return False

def get_historical_data(metric, period_hours=24, start_time=None, end_time=None):
    """
    Fetches historical data for a specific metric ('temperature_c', 'humidity', 'cpu_temperature')
    over a given period in hours, or between start_time and end_time.

    Args:
        metric (str): The column name of the metric to fetch.
        period_hours (int, optional): The number of past hours to fetch data for.
                                     Used if start_time and end_time are None.
        start_time (datetime, optional): The start of the time range.
        end_time (datetime, optional): The end of the time range.

    Returns:
        list: A list of tuples (timestamp, value) or empty list on error.
    """
    if metric not in ['temperature_c', 'humidity', 'cpu_temperature', 'raw_temperature']:
        logger.error(f"Invalid metric requested: {metric}")
        return []

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            if start_time and end_time:
                sql = f"SELECT timestamp, {metric} FROM sensor_readings WHERE timestamp BETWEEN ? AND ? ORDER BY timestamp ASC"
                cursor.execute(sql, (start_time, end_time))
            else:
                # Default to period_hours if no specific time range
                calculated_start_time = datetime.datetime.now() - datetime.timedelta(hours=period_hours)
                sql = f"SELECT timestamp, {metric} FROM sensor_readings WHERE timestamp >= ? ORDER BY timestamp ASC"
                cursor.execute(sql, (calculated_start_time,))

            rows = cursor.fetchall()
            logger.debug(f"Fetched {len(rows)} records for metric '{metric}' for period {period_hours}h or specified range.")
            # Convert rows to list of dicts or keep as list of tuples based on preference
            return [{"timestamp": row["timestamp"], "value": row[metric]} for row in rows if row[metric] is not None]
    except sqlite3.Error as e:
        logger.error(f"Error fetching historical data for {metric}: {e}")
        return []

def apply_data_retention(days_to_keep=30):
    """Deletes sensor readings older than the specified number of days."""
    cutoff_date = datetime.datetime.now() - datetime.timedelta(days=days_to_keep)
    sql = "DELETE FROM sensor_readings WHERE timestamp < ?"

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (cutoff_date,))
            conn.commit()
            deleted_rows = cursor.rowcount
            if deleted_rows > 0:
                logger.info(f"Applied data retention: deleted {deleted_rows} rows older than {days_to_keep} days.")
            else:
                logger.debug(f"Data retention check: No rows older than {days_to_keep} days to delete.")
            return deleted_rows
    except sqlite3.Error as e:
        logger.error(f"Error applying data retention: {e}")
        return -1 # Indicate error

def log_system_event(event_type, message, severity='info'):
    """Logs a system event to the system_events table."""
    sql = '''INSERT INTO system_events(event_type, message, severity)
             VALUES(?,?,?)'''
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (event_type, message, severity))
            conn.commit()
            logger.info(f"Logged system event: Type={event_type}, Severity={severity}, Message='{message}'")
            return cursor.lastrowid
    except sqlite3.Error as e:
        logger.error(f"Error logging system event: {e}")
        return None

if __name__ == '__main__':
    # This part is for basic testing of the module functionality
    # It will only run when the script is executed directly
    print(f"Database will be created/used at: {DATABASE_PATH}")

    # Ensure tables are created
    try:
        with get_db_connection() as conn:
            create_tables(conn)
        print("Database tables created/verified successfully.")

        # Test inserting a single reading
        print("Testing single insert...")
        reading_id = insert_sensor_reading(25.5, 60.1, 45.2, 26.0)
        if reading_id:
            print(f"Inserted single sensor reading with ID: {reading_id}")
        else:
            print("Failed to insert single sensor reading.")

        # Test batch inserting readings
        print("\nTesting batch insert...")
        sample_readings = [
            (25.8, 60.5, 45.5, 26.2),
            (26.0, 61.0, 45.8, 26.5),
            (25.7, 60.3, 45.3, 26.1)
        ]
        if insert_batch_sensor_readings(sample_readings):
            print(f"Batch inserted {len(sample_readings)} readings.")
        else:
            print("Failed to batch insert sensor readings.")

        # Test fetching historical data
        print("\nTesting fetching historical temperature data (last 24h)...")
        temp_data = get_historical_data('temperature_c', period_hours=24)
        if temp_data:
            print(f"Fetched {len(temp_data)} temperature readings:")
            for row in temp_data[:5]: # Print first 5
                print(f"  Timestamp: {row['timestamp']}, Temperature: {row['value']}°C")
        else:
            print("No temperature data found or error fetching.")

        # Test logging a system event
        print("\nTesting system event logging...")
        event_id = log_system_event("DB_TEST", "Database module test completed.", "info")
        if event_id:
            print(f"Logged system event with ID: {event_id}")
        else:
            print("Failed to log system event.")

        # Test data retention
        print("\nTesting data retention (simulating old data)...")
        # Insert a record far in the past
        old_timestamp = (datetime.datetime.now() - datetime.timedelta(days=35)).strftime('%Y-%m-%d %H:%M:%S')
        with get_db_connection() as conn:
            conn.execute("INSERT INTO sensor_readings(timestamp, temperature_c, humidity) VALUES (?, ?, ?)",
                         (old_timestamp, 20.0, 50.0))
            conn.commit()
        print("Inserted a mock old record.")
        deleted_count = apply_data_retention(days_to_keep=30)
        print(f"Data retention policy applied. Deleted {deleted_count} old records.")

        # Verify deletion
        temp_data_after_retention = get_historical_data('temperature_c', period_hours=24*40) # Fetch for 40 days
        print(f"Total records after retention (last 40 days): {len(temp_data_after_retention)}")


    except sqlite3.Error as e:
        print(f"An error occurred during database module testing: {e}")
    except Exception as ex:
        print(f"An unexpected error occurred: {ex}")
