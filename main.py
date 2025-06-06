import threading
import logging
import time
import sys
import os
import datetime # Added for background_sensor_collector logic

# Ensure src is in PYTHONPATH for imports when running main.py from project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from src.utils.config import config # Loads .env
from src.api.flask_app import create_flask_app
from src.gui.main import get_taipy_app # This function returns the configured Taipy GUI object

# --- Background Data Collection and DB Update Task ---
# This task will periodically read from sensors and store in DB.
# Taipy GUI can then read from DB for its charts.
# Taipy Core can also be used for this for more robust pipeline management.
# For now, a simple threading approach similar to original, but using new modules.

from src.data import sensor_manager
from src.data import database

def background_sensor_collector():
    """Periodically collects sensor data and stores it in the database."""
    logger = logging.getLogger("SensorCollectorThread")
    logger.info(f"Background sensor collector started. Interval: {config.SENSOR_SAMPLING_INTERVAL_SECONDS}s")

    # Initial delay before first run, e.g. if sensors need time to stabilize
    time.sleep(5)

    while True:
        try:
            logger.debug("Collecting sensor data...")
            data = sensor_manager.get_all_sensor_data()

            # Store in database
            # database.insert_sensor_reading expects individual values
            reading_id = database.insert_sensor_reading(
                temperature_c=data.get('temperature_c'),
                humidity=data.get('humidity'),
                cpu_temperature=data.get('cpu_temperature'),
                raw_temperature=data.get('raw_temperature_reading') # Renamed for clarity in db schema/sensor_manager
            )
            if reading_id:
                logger.info(f"Stored sensor reading ID {reading_id}: Temp={data.get('temperature_c')}°C, Hum={data.get('humidity')}%")
            else:
                logger.warning("Failed to store sensor reading.")

            # Apply data retention policy periodically (e.g., once per hour or day)
            # For simplicity, doing it every time for now, but this is inefficient.
            # A better way is to do this less frequently.
            # Example: Check current time, run retention once after midnight.
            if datetime.datetime.now().minute == 0: # Run at the start of every hour
                 deleted_count = database.apply_data_retention(days_to_keep=config.DB_DATA_RETENTION_DAYS)
                 if deleted_count > 0:
                     logger.info(f"Data retention policy applied, {deleted_count} old records deleted.")


        except Exception as e:
            logger.error(f"Error in background sensor collector: {e}", exc_info=True)

        time.sleep(config.SENSOR_SAMPLING_INTERVAL_SECONDS)


def start_flask_api_server():
    """Starts the Flask API server."""
    logger = logging.getLogger("FlaskThread")
    try:
        flask_api_app = create_flask_app()
        logger.info(f"Starting Flask API server on http://{config.FLASK_HOST}:{config.FLASK_PORT}")
        flask_api_app.run(host=config.FLASK_HOST, port=config.FLASK_PORT, debug=config.FLASK_DEBUG, use_reloader=False)
    except Exception as e:
        logger.critical(f"Failed to start Flask API server: {e}", exc_info=True)
        # Exit if Flask can't start, as Taipy might depend on it or it's a critical failure
        os._exit(1)


def start_taipy_gui_server():
    """Starts the Taipy GUI server."""
    logger = logging.getLogger("TaipyGUIThread")
    try:
        gui = get_taipy_app() # Get the configured Gui instance
        logger.info(f"Starting Taipy GUI server on http://{config.TAIPY_HOST}:{config.TAIPY_PORT}")
        # Note: Taipy's run server is blocking.
        # The 'run_server=True' is default. 'debug=True' enables reloader.
        # 'use_reloader=False' is important if Flask is also using a reloader or if in threads.
        gui.run(host=config.TAIPY_HOST, port=config.TAIPY_PORT, title="Temperature Monitor",
                  debug=config.TAIPY_DEBUG, use_reloader=False,
                  stylekit=True) # stylekit=True for better default Taipy styling
                  # css_file="src/gui/styles/custom.css" # Add when CSS file is created
    except Exception as e:
        logger.critical(f"Failed to start Taipy GUI server: {e}", exc_info=True)
        os._exit(1)


if __name__ == '__main__':
    # Configure basic logging for the main application
    # This should ideally be more sophisticated (e.g., rotating file handlers)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(name)s - [%(threadName)s] - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout) # Log to console
            # Add FileHandler here if needed: logging.FileHandler("app.log")
        ]
    )
    main_logger = logging.getLogger("MainApp")
    main_logger.info("Application starting...")
    main_logger.info(f"Loaded configuration. BEARER_TOKEN set: {bool(config.BEARER_TOKEN)}")
    main_logger.info(f"Database path: {config.DATABASE_PATH}")

    # Initialize database tables if they don't exist
    try:
        with database.get_db_connection() as conn:
            database.create_tables(conn)
        main_logger.info("Database tables ensured to exist.")
    except Exception as e:
        main_logger.critical(f"Failed to initialize database: {e}. Exiting.")
        sys.exit(1)

    # Start the background sensor collector thread
    collector_thread = threading.Thread(target=background_sensor_collector, name="SensorCollectorThread", daemon=True)
    collector_thread.start()
    main_logger.info("Background sensor collector thread started.")

    # Start Flask API server in a separate thread
    # Flask's dev server is not recommended for production but okay for this setup.
    # If using Gunicorn for Flask, the integration method would change.
    flask_thread = threading.Thread(target=start_flask_api_server, name="FlaskThread", daemon=True)
    flask_thread.start()
    main_logger.info("Flask API server thread started.")

    # Give Flask a moment to start up before Taipy, in case Taipy needs to access Flask APIs during init (not typical)
    time.sleep(2)

    # Start Taipy GUI server (this will block the main thread)
    # Taipy GUI should be run in the main thread as per Taipy recommendations for stability with some backends.
    main_logger.info("Starting Taipy GUI server in the main thread...")
    start_taipy_gui_server() # This is blocking

    main_logger.info("Application shutdown.") # This line might not be reached if Taipy blocks indefinitely
