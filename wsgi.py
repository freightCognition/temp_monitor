"""
WSGI entry point for production deployment on Raspberry Pi 4.

This module provides the Flask application and sensor thread initialization
for use with Waitress or other WSGI servers.

It also wraps the Flask application with WhiteNoise to serve static files
efficiently in a production environment.

Usage:
    waitress-serve --host=0.0.0.0 --port=8080 --threads=1 wsgi:app

Or in docker-compose.yml:
    CMD ["waitress-serve", "--host=0.0.0.0", "--port=8080", "--threads=1", "wsgi:app"]
"""

import logging
import time
from temp_monitor import app as flask_app, start_sensor_thread
from whitenoise import WhiteNoise

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

# Wrap the Flask app with WhiteNoise for static file serving.
# WhiteNoise will automatically find and serve files from the 'static' directory
# configured by the Flask app.
app = WhiteNoise(flask_app)


# Export the wrapped app for Waitress
__all__ = ['app']
