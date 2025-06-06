import os
import logging
from dotenv import load_dotenv

# Configure logging for the config module
logger = logging.getLogger(__name__)

class AppConfig:
    """
    Manages application configuration, loading from environment variables and .env file.
    Provides typed access to configuration parameters with defaults.
    """
    def __init__(self, dotenv_path=None):
        """
        Initializes the AppConfig.
        Args:
            dotenv_path (str, optional): Path to the .env file.
                                         Defaults to '.env' in the project root.
        """
        if dotenv_path is None:
            # Assuming the project root is two levels up from src/utils
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            dotenv_path = os.path.join(project_root, '.env')

        logger.info(f"Loading .env file from: {dotenv_path}")
        if not os.path.exists(dotenv_path):
            logger.warning(f".env file not found at {dotenv_path}. Using defaults and environment variables.")
            # Create a default .env file if it doesn't exist for critical values like BEARER_TOKEN
            self._create_default_env_file(dotenv_path)

        load_dotenv(dotenv_path=dotenv_path, override=True) # Override allows env vars to take precedence

        # --- Core Application Settings ---
        self.BEARER_TOKEN = os.getenv('BEARER_TOKEN')
        if not self.BEARER_TOKEN:
            logger.critical("BEARER_TOKEN is not set. This is required for API authentication.")
            # In a real app, you might raise an error or exit if critical configs are missing
            # For now, we'll let it proceed, but API auth will fail.
            # It should have been created by _create_default_env_file if .env was missing.

        self.FLASK_HOST = os.getenv('FLASK_HOST', '0.0.0.0')
        self.FLASK_PORT = self._get_int_env('FLASK_PORT', 8080)
        self.FLASK_DEBUG = self._get_bool_env('FLASK_DEBUG', False)

        self.TAIPY_HOST = os.getenv('TAIPY_HOST', '0.0.0.0')
        self.TAIPY_PORT = self._get_int_env('TAIPY_PORT', 5000)
        self.TAIPY_DEBUG = self._get_bool_env('TAIPY_DEBUG', False)

        # --- Database Settings ---
        default_db_name = "temperature_monitor.db"
        # Place DB in top-level 'database' folder relative to project root
        default_db_path = os.path.join(os.path.dirname(dotenv_path), 'database', default_db_name)
        self.DATABASE_NAME = os.getenv('DATABASE_NAME', default_db_name)
        self.DATABASE_PATH = os.getenv('DATABASE_PATH', default_db_path)
        self.DB_DATA_RETENTION_DAYS = self._get_int_env('DB_DATA_RETENTION_DAYS', 30)

        # --- Sensor and Data Collection Settings ---
        self.SENSOR_SAMPLING_INTERVAL_SECONDS = self._get_int_env('SENSOR_SAMPLING_INTERVAL_SECONDS', 60)
        self.CPU_TEMP_COMPENSATION_FACTOR = self._get_float_env('CPU_TEMP_COMPENSATION_FACTOR', 0.7)

        # --- Charting Settings ---
        self.CHART_REFRESH_RATE_SECONDS = self._get_int_env('CHART_REFRESH_RATE_SECONDS', 5) # For Taipy GUI refresh
        self.DEFAULT_HISTORY_PERIOD_HOURS = self._get_int_env('DEFAULT_HISTORY_PERIOD_HOURS', 24)

        # --- Alerting Settings (Placeholders for now) ---
        self.TEMP_ALERT_HIGH_THRESHOLD = self._get_float_env('TEMP_ALERT_HIGH_THRESHOLD', 30.0)
        self.TEMP_ALERT_LOW_THRESHOLD = self._get_float_env('TEMP_ALERT_LOW_THRESHOLD', 10.0)
        self.HUMIDITY_ALERT_HIGH_THRESHOLD = self._get_float_env('HUMIDITY_ALERT_HIGH_THRESHOLD', 70.0)
        self.HUMIDITY_ALERT_LOW_THRESHOLD = self._get_float_env('HUMIDITY_ALERT_LOW_THRESHOLD', 30.0)
        self.ENABLE_EMAIL_NOTIFICATIONS = self._get_bool_env('ENABLE_EMAIL_NOTIFICATIONS', False)
        self.SMTP_SERVER = os.getenv('SMTP_SERVER')
        self.SMTP_PORT = self._get_int_env('SMTP_PORT', 587)
        self.SMTP_USERNAME = os.getenv('SMTP_USERNAME')
        self.SMTP_PASSWORD = os.getenv('SMTP_PASSWORD') # Store sensitive data like this carefully!
        self.EMAIL_RECIPIENT = os.getenv('EMAIL_RECIPIENT')

        # --- Color Scheme ---
        self.CSS_COLORS = {
            'galaxy': '#261230', 'space': '#30173D', 'nebula': '#CDCBFB',
            'rock': '#78876E', 'crater': '#F0DFDF', 'flare': '#6340AC',
            'electron': '#46EBE1', 'cosmic': '#DE5FE9', 'sandstone': '#E1DF99',
            'comet': '#6F5D6F', 'lunar': '#FBF2FC', 'radiate': '#D7FF64',
            'starlight': '#F4F4F1'
        }
        self._validate_config()

    def _create_default_env_file(self, dotenv_path):
        """Creates a default .env file if one doesn't exist, especially for BEARER_TOKEN."""
        try:
            if not os.path.exists(dotenv_path):
                import secrets
                default_bearer_token = secrets.token_hex(32)
                with open(dotenv_path, 'w') as f:
                    f.write(f"# Default .env file created by application\n")
                    f.write(f"BEARER_TOKEN={default_bearer_token}\n")
                    f.write(f"FLASK_HOST=0.0.0.0\n")
                    f.write(f"FLASK_PORT=8080\n")
                    f.write(f"TAIPY_PORT=5000\n")
                    f.write(f"DATABASE_NAME=temperature_monitor.db\n")
                    f.write(f"SENSOR_SAMPLING_INTERVAL_SECONDS=60\n")
                    f.write(f"DB_DATA_RETENTION_DAYS=30\n")
                logger.info(f"Created a default .env file at {dotenv_path} with a new BEARER_TOKEN.")
                # Set the BEARER_TOKEN for the current session as well
                os.environ['BEARER_TOKEN'] = default_bearer_token
        except Exception as e:
            logger.error(f"Could not create default .env file at {dotenv_path}: {e}")


    def _get_int_env(self, var_name, default):
        val = os.getenv(var_name)
        if val is not None:
            try:
                return int(val)
            except ValueError:
                logger.warning(f"Invalid integer value for {var_name}: '{val}'. Using default: {default}.")
                return default
        return default

    def _get_float_env(self, var_name, default):
        val = os.getenv(var_name)
        if val is not None:
            try:
                return float(val)
            except ValueError:
                logger.warning(f"Invalid float value for {var_name}: '{val}'. Using default: {default}.")
                return default
        return default

    def _get_bool_env(self, var_name, default):
        val = os.getenv(var_name, str(default)).lower()
        if val in ['true', '1', 't', 'y', 'yes']:
            return True
        elif val in ['false', '0', 'f', 'n', 'no']:
            return False
        else:
            logger.warning(f"Invalid boolean value for {var_name}: '{val}'. Using default: {default}.")
            return default

    def _validate_config(self):
        """Performs basic validation of critical configuration values."""
        if not self.BEARER_TOKEN:
            logger.error("CRITICAL: BEARER_TOKEN is not configured. API authentication will fail.")
        if self.SENSOR_SAMPLING_INTERVAL_SECONDS <= 0:
            logger.warning(f"SENSOR_SAMPLING_INTERVAL_SECONDS is {self.SENSOR_SAMPLING_INTERVAL_SECONDS}, which is invalid. Consider setting to a positive integer.")
        if self.DB_DATA_RETENTION_DAYS <= 0:
            logger.warning(f"DB_DATA_RETENTION_DAYS is {self.DB_DATA_RETENTION_DAYS}, which is invalid. Data retention might not work as expected.")

        # Ensure DATABASE_PATH's directory exists
        db_dir = os.path.dirname(self.DATABASE_PATH)
        if not os.path.exists(db_dir):
            try:
                os.makedirs(db_dir, exist_ok=True)
                logger.info(f"Created database directory: {db_dir}")
            except Exception as e:
                logger.error(f"Failed to create database directory {db_dir}: {e}")

        logger.info("Configuration loaded and validated.")

# Create a single instance to be imported by other modules
config = AppConfig()

if __name__ == '__main__':
    # Configure basic logging for direct script execution testing
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')

    print("--- Application Configuration ---")
    print(f"Bearer Token: {'*' * 10 if config.BEARER_TOKEN else 'NOT SET'}") # Avoid printing sensitive token
    print(f"Flask Host: {config.FLASK_HOST}")
    print(f"Flask Port: {config.FLASK_PORT}")
    print(f"Flask Debug: {config.FLASK_DEBUG}")
    print(f"Taipy Host: {config.TAIPY_HOST}")
    print(f"Taipy Port: {config.TAIPY_PORT}")
    print(f"Taipy Debug: {config.TAIPY_DEBUG}")
    print(f"Database Path: {config.DATABASE_PATH}")
    print(f"Database Name: {config.DATABASE_NAME}") # Added for completeness
    print(f"Data Retention (days): {config.DB_DATA_RETENTION_DAYS}")
    print(f"Sensor Sampling Interval (s): {config.SENSOR_SAMPLING_INTERVAL_SECONDS}")
    print(f"CPU Temp Compensation Factor: {config.CPU_TEMP_COMPENSATION_FACTOR}")
    print(f"Chart Refresh Rate (s): {config.CHART_REFRESH_RATE_SECONDS}")
    print(f"Default History Period (hrs): {config.DEFAULT_HISTORY_PERIOD_HOURS}")
    print(f"Temp Alert High: {config.TEMP_ALERT_HIGH_THRESHOLD}°C")
    print(f"Temp Alert Low: {config.TEMP_ALERT_LOW_THRESHOLD}°C")
    print(f"Humidity Alert High: {config.HUMIDITY_ALERT_HIGH_THRESHOLD}%")
    print(f"Humidity Alert Low: {config.HUMIDITY_ALERT_LOW_THRESHOLD}%")
    print(f"Enable Email Notifications: {config.ENABLE_EMAIL_NOTIFICATIONS}")
    print(f"SMTP Server: {config.SMTP_SERVER}")
    print(f"SMTP Port: {config.SMTP_PORT}")
    print(f"SMTP Username: {config.SMTP_USERNAME}")
    print(f"SMTP Password: {'*' * 8 if config.SMTP_PASSWORD else 'NOT SET'}")
    print(f"Email Recipient: {config.EMAIL_RECIPIENT}")

    # Test that .env file is created if it doesn't exist
    project_root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    test_env_path = os.path.join(project_root_dir, '.env.test_config_script')
    if os.path.exists(test_env_path):
        os.remove(test_env_path)

    print(f"\nTesting .env creation at {test_env_path} (if it didn't exist)...")
    test_config = AppConfig(dotenv_path=test_env_path)
    if os.path.exists(test_env_path):
        print(f".env file found or created at {test_env_path}")
        with open(test_env_path, 'r') as f:
            print("Contents of test .env file:")
            print(f.read())
        # Clean up the test .env file
        # os.remove(test_env_path) # Comment out if you want to inspect it after run
    else:
        print(f"Test .env file NOT created at {test_env_path}, which is unexpected if it was missing.")

    # Test DATABASE_PATH directory creation
    print(f"\nEnsuring database directory exists: {os.path.dirname(config.DATABASE_PATH)}")
    # The AppConfig constructor should have already tried to create this.
    # We can double check here.
    if not os.path.exists(os.path.dirname(config.DATABASE_PATH)):
        print(f"ERROR: Database directory {os.path.dirname(config.DATABASE_PATH)} was not created!")
    else:
        print(f"Database directory {os.path.dirname(config.DATABASE_PATH)} exists.")

    print("\nConfig module test finished.")
