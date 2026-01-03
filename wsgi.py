"""
WSGI entry point for production deployment on Raspberry Pi 4.

This module provides the Flask application and sensor thread initialization
for use with Waitress or other WSGI servers.

Usage:
    waitress-serve --host=0.0.0.0 --port=8080 --threads=1 wsgi:app

Or in docker-compose.yml:
    CMD ["waitress-serve", "--host=0.0.0.0", "--port=8080", "--threads=1", "wsgi:app"]
"""

import logging
import time
from temp_monitor import app, start_sensor_thread

# Configure logging
logger = logging.getLogger(__name__)

# Start background sensor thread when this module is imported
try:
    logger.info("Initializing sensor thread for production deployment...")
    sensor_thread = start_sensor_thread()

    # Give the thread a moment to get initial readings
    time.sleep(2)

    logger.info("Sensor thread started successfully")
except Exception as e:
    logger.error(f"Failed to start sensor thread: {e}")
    raise

# Export the Flask app for Waitress
__all__ = ['app']
