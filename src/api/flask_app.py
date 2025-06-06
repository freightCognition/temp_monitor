from flask import Flask, jsonify, request, abort, send_from_directory
import logging
import time
import datetime
import os
import random

import sys
# Add project root to sys.path
project_root_for_flask = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root_for_flask not in sys.path:
    sys.path.insert(0, project_root_for_flask)

from src.utils.config import config
from src.api.auth import require_token, setup_auth_routes
from src.data import sensor_manager
from src.data import database # For historical data
# from src.data import data_processor # Will be used for stats; import later when created

logger = logging.getLogger(__name__)

def create_flask_app():
    """Creates and configures the Flask application."""
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'a_very_secret_key_for_flask_sessions')

    # Configure logging for Flask app
    # Basic logging is already configured by the time config.py is imported.
    # You might want to add specific Flask handlers or formatters if needed.
    # Example: app.logger.addHandler(logging.StreamHandler())
    # app.logger.setLevel(logging.INFO)

    logger.info("Flask app created.")
    logger.info(f"Flask BEARER_TOKEN loaded: {'******' if config.BEARER_TOKEN else 'NOT SET'}")


    # --- Serve Favicon ---
    # Assuming temp-favicon.ico is in the project root.
    # The original script had a hardcoded path. Let's make it relative to project root.
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    favicon_path = os.path.join(project_root, "temp-favicon.ico")
    assets_folder = os.path.join(project_root, "assets")


    @app.route('/favicon.ico')
    def favicon():
        if os.path.exists(favicon_path):
            return send_from_directory(project_root, 'temp-favicon.ico', mimetype='image/vnd.microsoft.icon')
        else:
            logger.warning("favicon.ico not found at project root.")
            return "", 404

    @app.route('/assets/<path:filename>')
    def serve_asset(filename):
        return send_from_directory(assets_folder, filename)


    # --- Existing API Endpoints (Refactored) ---
    @app.route('/api/temp')
    @require_token
    def api_temp():
        """API endpoint returning current temperature and humidity data."""
        try:
            data = sensor_manager.get_all_sensor_data() # Uses mock if SenseHAT not available
            current_temp_c = data.get('temperature_c')
            current_humidity_val = data.get('humidity')

            if current_temp_c is None or current_humidity_val is None:
                 logger.error("Sensor data unavailable from sensor_manager")
                 return jsonify({'error': 'Sensor data currently unavailable'}), 503

            fahrenheit = round((current_temp_c * 9/5) + 32, 1)

            return jsonify({
                'temperature_c': current_temp_c,
                'temperature_f': fahrenheit,
                'humidity': current_humidity_val,
                'timestamp': datetime.datetime.now().isoformat() # Current time for live data
            }), 200
        except Exception as e:
            logger.error(f"Error in /api/temp: {e}")
            return jsonify({'error': 'Internal server error reading sensor data'}), 500

    @app.route('/api/raw')
    @require_token
    def api_raw():
        """API endpoint for debugging, showing raw vs compensated temperature."""
        try:
            data = sensor_manager.get_all_sensor_data()
            cpu_temp = data.get('cpu_temperature')
            raw_temp = data.get('raw_temperature_reading') # From our new combined function
            compensated_temp = data.get('temperature_c')
            humidity = data.get('humidity')

            return jsonify({
                'cpu_temperature': cpu_temp,
                'raw_sensor_temperature': raw_temp, # This is the direct sensor reading
                'compensated_temperature': compensated_temp,
                'humidity': humidity,
                'timestamp': datetime.datetime.now().isoformat()
            }), 200
        except Exception as e:
            logger.error(f"Error in /api/raw: {e}")
            return jsonify({'error': 'Internal server error reading raw sensor data'}), 500

    # Register authentication routes (e.g., /api/verify-token)
    setup_auth_routes(app)

    # --- New API Endpoints ---

    # Historical data endpoints
    @app.route('/api/history', methods=['GET'])
    @require_token
    def api_history():
        period_str = request.args.get('period', '24h') # e.g., 24h, 7d
        metric = request.args.get('metric', 'temperature_c') # temperature_c, humidity

        if metric not in ['temperature_c', 'humidity', 'cpu_temperature', 'raw_temperature']:
            return jsonify({'error': 'Invalid metric specified'}), 400

        period_hours = None
        if period_str.endswith('h'):
            try:
                period_hours = int(period_str[:-1])
            except ValueError:
                return jsonify({'error': 'Invalid period format for hours'}), 400
        elif period_str.endswith('d'):
            try:
                period_hours = int(period_str[:-1]) * 24
            except ValueError:
                return jsonify({'error': 'Invalid period format for days'}), 400
        else:
            return jsonify({'error': 'Invalid period suffix. Use "h" for hours or "d" for days.'}), 400

        if period_hours <= 0:
            return jsonify({'error': 'Period must be positive'}), 400

        try:
            # Convert ISO string timestamps from DB to a more friendly format if needed,
            # or ensure Taipy/Plotly can handle ISO strings directly.
            # database.get_historical_data returns list of dicts: {"timestamp": आईएसओ_स्ट्रिंग, "value": संख्या}
            data = database.get_historical_data(metric=metric, period_hours=period_hours)
            return jsonify({
                'metric': metric,
                'period': period_str,
                'data_points': len(data),
                'values': data # data is already a list of {'timestamp': ..., 'value': ...}
            }), 200
        except Exception as e:
            logger.error(f"Error in /api/history (metric: {metric}, period: {period_str}): {e}")
            return jsonify({'error': 'Internal server error fetching historical data'}), 500

    @app.route('/api/export', methods=['GET'])
    @require_token
    def api_export():
        # Placeholder: Actual CSV/JSON generation will be more involved
        # This requires pandas for easy CSV/JSON export from data
        format_type = request.args.get('format', 'csv')
        period_str = request.args.get('period', '30d') # Default to 30 days

        # Similar period parsing as /api/history
        period_hours = None
        if period_str.endswith('h'): period_hours = int(period_str[:-1])
        elif period_str.endswith('d'): period_hours = int(period_str[:-1]) * 24
        else: return jsonify({'error': 'Invalid period. Use "h" or "d".'}), 400

        if period_hours <=0: return jsonify({'error': 'Period must be positive.'}),400

        # Fetch all relevant data for the period
        # For CSV, you'd typically want all metrics together.
        # This is a simplified example. A real export might query all columns.
        try:
            temp_data = database.get_historical_data(metric='temperature_c', period_hours=period_hours)
            hum_data = database.get_historical_data(metric='humidity', period_hours=period_hours)
            # In a real scenario, you'd merge these based on timestamp.
            # For now, just returning temperature data as an example.

            if format_type == 'csv':
                # This part would ideally use pandas: pd.DataFrame(temp_data).to_csv()
                # For now, a very simple CSV string for demonstration:
                if not temp_data:
                    return "timestamp,temperature_c\n", 200, {'Content-Type': 'text/csv'}

                csv_output = "timestamp,temperature_c\n"
                for item in temp_data:
                    csv_output += f"{item['timestamp']},{item['value']}\n"
                return csv_output, 200, {'Content-Type': 'text/csv', 'Content-Disposition': f'attachment; filename="export_{period_str}.csv"'}
            elif format_type == 'json':
                 # Just returning the raw list of dicts for temperature for now
                return jsonify(temp_data), 200
            else:
                return jsonify({'error': 'Unsupported format. Use "csv" or "json".'}), 400
        except Exception as e:
            logger.error(f"Error in /api/export: {e}")
            return jsonify({'error': 'Failed to export data'}), 500


    # Statistics endpoints (Placeholders - require data_processor.py)
    @app.route('/api/stats/<string:metric>', methods=['GET'])
    @require_token
    def api_stats_metric(metric):
        if metric not in ['temperature', 'humidity']: # Simplified
            return jsonify({'error': 'Invalid metric for stats. Use "temperature" or "humidity".'}), 400

        period_str = request.args.get('period', '24h')
        period_hours = None
        if period_str.endswith('h'): period_hours = int(period_str[:-1])
        elif period_str.endswith('d'): period_hours = int(period_str[:-1]) * 24
        else: return jsonify({'error': 'Invalid period. Use "h" or "d".'}), 400

        if period_hours <=0: return jsonify({'error': 'Period must be positive.'}),400

        # Placeholder: Actual calculation will use data_processor and database
        # e.g., stats = data_processor.get_metric_stats(metric, period_hours)
        # For now, returning mock data:
        mock_stats = {
            "metric": metric,
            "period": period_str,
            "min": random.uniform(15, 20) if metric == 'temperature' else random.uniform(40,50),
            "max": random.uniform(25, 30) if metric == 'temperature' else random.uniform(60,70),
            "avg": random.uniform(20, 25) if metric == 'temperature' else random.uniform(50,60),
            "count": random.randint(100,500)
        }
        return jsonify(mock_stats), 200

    @app.route('/api/stats/summary', methods=['GET'])
    @require_token
    def api_stats_summary():
        # Placeholder: Will combine stats for various metrics
        # e.g., summary = data_processor.get_overall_summary()
        mock_summary = {
            "current_temperature_c": sensor_manager.get_compensated_temperature(),
            "current_humidity": sensor_manager.get_humidity(),
            "last_24h_temp_avg": random.uniform(20,25),
            "last_24h_humidity_avg": random.uniform(50,60),
            "records_in_db": random.randint(1000,50000) # This could actually query the DB
        }
        try:
            with database.get_db_connection() as conn:
                count = conn.execute("SELECT COUNT(id) FROM sensor_readings").fetchone()[0]
                mock_summary["records_in_db"] = count
        except Exception as e:
            logger.error(f"Failed to get record count for stats summary: {e}")


        return jsonify(mock_summary), 200

    # System endpoints (Placeholders)
    @app.route('/api/system/health', methods=['GET'])
    @require_token
    def api_system_health():
        # Placeholder: Check DB connection, sensor status, etc.
        db_ok = False
        try:
            with database.get_db_connection() as conn:
                conn.execute("SELECT 1") # Simple query to check connection
            db_ok = True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")

        sensor_ok = sensor_manager.SENSE_HAT_AVAILABLE # Or a more robust check

        return jsonify({
            'status': 'ok' if db_ok and sensor_ok else 'degraded',
            'database_connection': 'ok' if db_ok else 'error',
            'sensor_status': 'ok' if sensor_ok else ('unavailable' if not sensor_manager.SENSE_HAT_AVAILABLE else 'error'),
            'timestamp': datetime.datetime.now().isoformat()
        }), 200

    @app.route('/api/system/uptime', methods=['GET'])
    @require_token
    def api_system_uptime():
        # Placeholder: This is tricky to get application uptime reliably without a global start time.
        # For system uptime, one would use 'uptime' command on Linux.
        # For now, returning a mock string.
        # A simple way is to store start time in the app context, but that resets with workers.
        return jsonify({'application_uptime_status': 'Not implemented yet. System uptime would require OS command.'}), 501

    @app.route('/api/system/storage', methods=['GET'])
    @require_token
    def api_system_storage():
        # Placeholder: Use shutil.disk_usage('/') on Linux
        try:
            if os.name == 'posix': # Check if on a POSIX system (Linux, macOS)
                import shutil
                total, used, free = shutil.disk_usage("/")
                return jsonify({
                    'total_gb': round(total / (2**30), 2),
                    'used_gb': round(used / (2**30), 2),
                    'free_gb': round(free / (2**30), 2),
                    'free_percent': round((free/total) * 100, 2)
                }), 200
            else:
                 return jsonify({'message': 'Disk storage info available on POSIX systems only.'}), 501
        except Exception as e:
            logger.error(f"Error getting disk usage: {e}")
            return jsonify({'error': 'Could not retrieve disk storage information.'}), 500

    logger.info("Flask app configured with all routes.")
    return app

if __name__ == '__main__':
    # This is for direct execution (testing purposes)
    # In production, use a proper WSGI server like Gunicorn or Waitress
    # And the Taipy app will typically run this Flask app as part of its setup.
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')

    # Ensure .env is loaded by creating a config instance if not already done by import
    if not config.BEARER_TOKEN: # A simple check
        logger.warning("BEARER_TOKEN not found during Flask app direct run, API calls might fail auth.")
        # This implies that config from src.utils.config was not fully initialized or .env is missing token
        # For direct run, ensure .env exists in project root with a BEARER_TOKEN

    flask_app = create_flask_app()

    print("Starting Flask development server for API testing...")
    print(f"API Base URL: http://{config.FLASK_HOST}:{config.FLASK_PORT}")
    print(f"Try: curl -H \"Authorization: Bearer YOUR_TOKEN\" http://{config.FLASK_HOST}:{config.FLASK_PORT}/api/temp")
    print(f"Using BEARER_TOKEN: {config.BEARER_TOKEN}") # For testing convenience

    flask_app.run(host=config.FLASK_HOST, port=config.FLASK_PORT, debug=config.FLASK_DEBUG)
