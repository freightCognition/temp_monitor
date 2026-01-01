from sense_hat import SenseHat
from flask import Flask, jsonify, render_template_string, request, abort
from flask_restx import Api, Resource
import time
import logging
import threading
import statistics
import os
import functools
import signal
from urllib.parse import urlparse
from dotenv import load_dotenv
from webhook_service import WebhookService, WebhookConfig, AlertThresholds
from api_models import (
    webhooks_ns, webhook_config_update, webhook_config_response,
    error_response, success_response, message_response, test_response,
    validate_thresholds, validate_webhook_config
)

try:
    import psutil
except ImportError:
    psutil = None

# Load environment variables from .env file
load_dotenv()

# Configure logging
log_file = os.getenv('LOG_FILE', 'temp_monitor.log')

# Validate and prepare log file path
log_dir = os.path.dirname(log_file)
if log_dir:  # Only validate if directory is specified (not relative path in current dir)
    try:
        os.makedirs(log_dir, exist_ok=True)
    except Exception as e:
        raise RuntimeError(f"Failed to create log directory '{log_dir}': {e}")

try:
    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
except Exception as e:
    raise RuntimeError(f"Failed to configure logging with file '{log_file}': {e}")

# Initialize SenseHat
try:
    sense = SenseHat()
    sense.clear()  # Clear the LED matrix
except Exception as e:
    logging.error(f"Failed to initialize Sense HAT: {e}")
    raise

app = Flask(__name__)

# Initialize Flask-RESTX API with Swagger documentation
api = Api(
    app,
    version='1.0',
    title='Temperature Monitor API',
    description='Server room environmental monitoring API with webhook notifications',
    doc='/docs',
    authorizations={
        'bearer': {
            'type': 'apiKey',
            'in': 'header',
            'name': 'Authorization',
            'description': 'Bearer token authentication. Format: "Bearer <token>"'
        }
    }
    # Note: security='bearer' removed to allow public Swagger UI access at /docs
    # Individual endpoints are protected via @webhooks_ns.doc(security='bearer') decorators
)

# Register the webhooks namespace
api.add_namespace(webhooks_ns, path='/api/webhook')

# Global variables to store sensor data
current_temp = 0
current_humidity = 0
last_updated = "Never"
sampling_interval = 60  # seconds between temperature updates

# Metrics tracking for production deployment
app_start_time = time.time()
request_counter = 0
webhook_alert_counter = 0
sensor_thread = None  # Will be initialized when started

# Periodic status update configuration
status_update_enabled = os.getenv('STATUS_UPDATE_ENABLED', 'false').lower() == 'true'
status_update_interval = int(os.getenv('STATUS_UPDATE_INTERVAL', '3600'))
last_status_update = None  # Track time of last status update

# Validate status update interval (must be >= sampling_interval)
if status_update_enabled and status_update_interval < sampling_interval:
    logging.warning(
        f"STATUS_UPDATE_INTERVAL ({status_update_interval}s) is less than "
        f"sampling_interval ({sampling_interval}s). Using sampling_interval as minimum."
    )
    status_update_interval = sampling_interval

# Initialize webhook service
webhook_service = None
slack_webhook_url = os.getenv('SLACK_WEBHOOK_URL')
if slack_webhook_url:
    webhook_config = WebhookConfig(
        url=slack_webhook_url,
        enabled=os.getenv('WEBHOOK_ENABLED', 'true').lower() == 'true',
        retry_count=int(os.getenv('WEBHOOK_RETRY_COUNT', '3')),
        retry_delay=int(os.getenv('WEBHOOK_RETRY_DELAY', '5')),
        timeout=int(os.getenv('WEBHOOK_TIMEOUT', '10'))
    )

    alert_thresholds = AlertThresholds(
        temp_min_c=float(os.getenv('ALERT_TEMP_MIN_C', '15.0')) if os.getenv('ALERT_TEMP_MIN_C') else None,
        temp_max_c=float(os.getenv('ALERT_TEMP_MAX_C', '27.0')) if os.getenv('ALERT_TEMP_MAX_C') else None,
        humidity_min=float(os.getenv('ALERT_HUMIDITY_MIN', '30.0')) if os.getenv('ALERT_HUMIDITY_MIN') else None,
        humidity_max=float(os.getenv('ALERT_HUMIDITY_MAX', '70.0')) if os.getenv('ALERT_HUMIDITY_MAX') else None
    )

    webhook_service = WebhookService(webhook_config, alert_thresholds)
    logging.info("Webhook service initialized")
else:
    logging.info("Webhook service not configured (no SLACK_WEBHOOK_URL)")

# Initialize status update timer
if status_update_enabled and webhook_service:
    if os.getenv('STATUS_UPDATE_ON_STARTUP', 'false').lower() == 'true':
        last_status_update = None  # Will trigger immediately on first loop
        logging.info("Periodic status updates enabled (will send on startup)")
    else:
        last_status_update = time.time()  # Start timer from now
        logging.info(f"Periodic status updates enabled (interval: {status_update_interval}s)")
elif status_update_enabled and not webhook_service:
    logging.warning("STATUS_UPDATE_ENABLED is true but webhook service not configured")

def generate_error_id():
    """Generate a correlation ID for error tracking in logs and responses"""
    timestamp = int(time.time() * 1000)
import random
    suffix = format(random.randint(0, 65535), '04x')
    return f"{timestamp}_{suffix}"


# Get bearer token from environment (required)
BEARER_TOKEN = os.getenv('BEARER_TOKEN')
if not BEARER_TOKEN:
    logging.critical("BEARER_TOKEN not set in environment. Exiting.")
    print("ERROR: BEARER_TOKEN environment variable is required.")
    print("Generate a token with: python3 -c \"import secrets; print(secrets.token_hex(32))\"")
    print("Then add it to your .env file: BEARER_TOKEN=<your_token>")
    import sys
    sys.exit(1)
else:
    logging.info("Bearer token loaded from environment")

def mask_webhook_url(url):
    """
    Mask webhook URL by returning only scheme and host for security.

    This prevents sensitive path components and tokens from being exposed
    in API responses and logs, while still showing which service is configured.

    Args:
        url: Full webhook URL or None

    Returns:
        Masked URL in format 'scheme://host' or None if input is None/empty
    """
    if not url:
        return None

    try:
        parsed = urlparse(url)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
        else:
            # Malformed URL - return generic placeholder
            return "<invalid-url>"
    except Exception as e:
        logging.warning(f"Error masking webhook URL: {e}")
        return "<invalid-url>"

def require_token(f):
    """Decorator to require bearer token authentication for API endpoints"""
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        
        # Check if Authorization header exists and has the correct format
        if not auth_header or not auth_header.startswith('Bearer '):
            logging.warning(f"API access attempt without valid Authorization header from {request.remote_addr}")
            abort(401, description="Authorization header with Bearer token required")
        
        # Extract and validate the token
        token = auth_header.split(' ')[1]
        if token != BEARER_TOKEN:
            logging.warning(f"API access attempt with invalid token from {request.remote_addr}")
            abort(403, description="Invalid bearer token")
            
        return f(*args, **kwargs)
    return decorated_function

def get_cpu_temperature():
    """Get the temperature of the CPU for compensation"""
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            temp = float(f.read()) / 1000.0
        return temp
    except Exception as e:
        logging.error(f"Failed to get CPU temperature: {e}")
        return None

def get_compensated_temperature():
    """Get temperature from the Sense HAT with CPU compensation"""
    # Get CPU temperature
    cpu_temp = get_cpu_temperature()
    
    # Get raw temperatures from Sense HAT
    raw_temps = []
    for _ in range(5):  # Take multiple readings
        raw_temps.append(sense.get_temperature_from_humidity())
        raw_temps.append(sense.get_temperature_from_pressure())
        time.sleep(0.1)
    
    # Remove outliers and calculate the average raw temperature
    if len(raw_temps) > 2:  # Need at least 3 readings to filter outliers
        raw_temps.sort()
        # Remove highest and lowest reading
        filtered_temps = raw_temps[1:-1]
        raw_temp = statistics.mean(filtered_temps)
    else:
        raw_temp = statistics.mean(raw_temps)
    
    # Apply compensation formula based on calibration
    # This formula assumes the CPU is significantly warmer than the ambient temperature
    # The factor of 0.7 is an approximation that should be calibrated
    factor = 0.7
    if cpu_temp is not None:
        comp_temp = raw_temp - ((cpu_temp - raw_temp) * factor)
    else:
        comp_temp = raw_temp
    
    # Correction: Adjust by -4°F (old -10°F was too aggressive, actual needs -4°F)
    comp_temp = comp_temp - (4 * 5 / 9)

    return round(comp_temp, 1)

def get_humidity():
    """Get humidity from the Sense HAT"""
    # Take multiple readings and average them
    readings = []
    for _ in range(3):
        readings.append(sense.get_humidity())
        time.sleep(0.1)
    
    # Remove outliers if possible
    if len(readings) > 2:
        readings.sort()
        readings = readings[1:-1]  # Remove highest and lowest
    
    humidity = statistics.mean(readings)

    # Correction: Adjust by +4% (old +10% was too aggressive, actual needs +4%)
    humidity += 4

    # Ensure humidity doesn't exceed 100%
    if humidity > 100:
        humidity = 100

    # Return the average
    return round(humidity, 1)

def update_sensor_data():
    """Background thread function to update sensor data periodically"""
    global current_temp, current_humidity, last_updated

    while True:
        try:
            current_temp = get_compensated_temperature()
            current_humidity = get_humidity()
            last_updated = time.strftime("%Y-%m-%d %H:%M:%S")

            cpu_temp_val = get_cpu_temperature()
            cpu_temp_display = f"{cpu_temp_val}°C" if cpu_temp_val is not None else "N/A"
            logging.info(
                f"Temperature: {current_temp}°C, Humidity: {current_humidity}%, CPU Temp: {cpu_temp_display}"
            )

            # Check thresholds and send alerts via webhook
            if webhook_service:
                try:
                    alerts_sent = webhook_service.check_and_alert(
                        current_temp, current_humidity, last_updated
                    )
                    if alerts_sent:
                        increment_alert_counter()
                        logging.info(f"Webhook alerts sent: {list(alerts_sent.keys())}")
                except Exception as webhook_error:
                    logging.error(f"Error sending webhook alert: {webhook_error}")

            # Send periodic status updates if enabled
            if status_update_enabled and webhook_service:
                global last_status_update
                current_time = time.time()

                # Check if it's time for a status update
                should_send_update = (
                    last_status_update is None or  # First update or startup update
                    (current_time - last_status_update) >= status_update_interval
                )

                if should_send_update:
                    try:
                        cpu_temp = get_cpu_temperature()
                        success = webhook_service.send_status_update(
                            current_temp, current_humidity, cpu_temp, last_updated
                        )

                        if success:
                            logging.info("Periodic status update sent successfully")
                        else:
                            logging.warning("Periodic status update failed, will retry at next interval")

                    except Exception as update_error:
                        logging.error(f"Error sending periodic status update: {update_error}")
                    finally:
                        # Always update timestamp to prevent retry storms
                        last_status_update = current_time

            # Display temperature on Sense HAT LED matrix
            temp_f = round((current_temp * 9/5) + 32, 1)
            message = f"Temp: {temp_f}F"
            sense.show_message(message)

            # Sleep for the specified interval
            time.sleep(sampling_interval)
        except Exception as e:
            logging.error(f"Error updating sensor data: {e}")
            time.sleep(5)  # Short sleep before retry on error

@app.route('/')
def index():
    """Web interface showing temperature and humidity"""
    
    html_template = """
    <!DOCTYPE html>
    <html>
        <head>
            <title>Server Room Environmental Monitor</title>
            <meta http-equiv="refresh" content="60">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <link rel="shortcut icon" href="{{ url_for('static', filename='favicon.ico') }}">
            <style>
                body { 
                    font-family: Arial, sans-serif; 
                    text-align: center; 
                    margin: 0;
                    padding: 20px;
                    background-color: #f5f5f5;
                }
                .container {
                    max-width: 800px;
                    margin: 0 auto;
                    background-color: white;
                    border-radius: 10px;
                    padding: 20px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                }
                h1 { color: #333; }
                .reading {
                    font-size: 72px;
                    font-weight: bold;
                    margin: 20px 0;
                }
                .temp { color: #e74c3c; }
                .humidity { color: #3498db; }
                .unit { font-size: 30px; }
                .info { 
                    margin-top: 30px;
                    font-size: 14px;
                    color: #777;
                }
                .fahrenheit {
                    font-size: 24px;
                    color: #888;
                    margin-top: -20px;
                    margin-bottom: 30px;
                }
                .logo {
                    max-width: 100%;
                    max-height: 200px;
                    margin-bottom: 20px;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <img src="{{ url_for('static', filename='My-img8bit-1com-Effect.gif') }}" alt="Company Logo" class="logo">
                <h1>Server Room Environmental Monitor</h1>
                
                <h2>Temperature</h2>
                <div class="reading temp">{{ temperature }}<span class="unit">°C</span></div>
                <div class="fahrenheit">({{ fahrenheit }}°F)</div>
                
                <h2>Humidity</h2>
                <div class="reading humidity">{{ humidity }}<span class="unit">%</span></div>
                
                <div class="info">
                    Last updated: {{ last_updated }}<br>
                    Monitoring device: Raspberry Pi 4 with Sense HAT<br>
                </div>
            </div>
        </body>
    </html>
    """
    fahrenheit = round((current_temp * 9/5) + 32, 1)
    return render_template_string(
        html_template, 
        temperature=current_temp, 
        fahrenheit=fahrenheit,
        humidity=current_humidity, 
        last_updated=last_updated
    )

@app.route('/api/temp')
@require_token
def api_temp():
    """API endpoint returning temperature data as JSON"""
    fahrenheit = round((current_temp * 9/5) + 32, 1)
    return jsonify({
        'temperature_c': current_temp,
        'temperature_f': fahrenheit,
        'humidity': current_humidity,
        'timestamp': last_updated
    })

@app.route('/api/raw')
@require_token
def api_raw():
    """API endpoint for debugging, showing raw vs compensated temperature"""
    cpu_temp = get_cpu_temperature()
    raw_temp = sense.get_temperature()
    return jsonify({
        'cpu_temperature': round(cpu_temp, 1) if cpu_temp is not None else None,
        'raw_temperature': round(raw_temp, 1),
        'compensated_temperature': current_temp,
        'humidity': current_humidity,
        'timestamp': last_updated
    })

# Add an endpoint to check if token is valid
@app.route('/api/verify-token', methods=['GET'])
@require_token
def verify_token():
    """Verify if the provided token is valid"""
    return jsonify({
        'valid': True,
        'message': 'Token is valid'
    })

# Webhook management endpoints using Flask-RESTX
@webhooks_ns.route('/config')
class WebhookConfigResource(Resource):
    """Webhook configuration management"""

    @webhooks_ns.doc(security='bearer')
    @webhooks_ns.marshal_with(webhook_config_response)
    @webhooks_ns.response(200, 'Success', webhook_config_response)
    @require_token
    def get(self):
        """Get current webhook configuration"""
        if not webhook_service or not webhook_service.webhook_config:
            return {
                'webhook': {
                    'url': None,
                    'enabled': False,
                    'retry_count': 3,
                    'retry_delay': 5,
                    'timeout': 10
                },
                'thresholds': {
                    'temp_min_c': None,
                    'temp_max_c': None,
                    'humidity_min': None,
                    'humidity_max': None
                }
            }

        config = webhook_service.webhook_config
        thresholds = webhook_service.alert_thresholds

        return {
            'webhook': {
                'url': mask_webhook_url(config.url),
                'enabled': config.enabled,
                'retry_count': config.retry_count,
                'retry_delay': config.retry_delay,
                'timeout': config.timeout
            },
            'thresholds': {
                'temp_min_c': thresholds.temp_min_c,
                'temp_max_c': thresholds.temp_max_c,
                'humidity_min': thresholds.humidity_min,
                'humidity_max': thresholds.humidity_max
            }
        }

    @webhooks_ns.doc(security='bearer')
    @webhooks_ns.expect(webhook_config_update)
    @webhooks_ns.marshal_with(success_response)
    @webhooks_ns.response(400, 'Validation Error', error_response)
    @webhooks_ns.response(500, 'Server Error', error_response)
    @require_token
    def put(self):
        """Update webhook configuration with validation"""
        global webhook_service

        data = webhooks_ns.payload

        # Validate webhook config field ranges
        if 'webhook' in data and data['webhook']:
            is_valid, error_msg = validate_webhook_config(data['webhook'])
            if not is_valid:
                webhooks_ns.abort(400, error_msg)

        # Cross-field validation for thresholds
        if 'thresholds' in data and data['thresholds']:
            is_valid, error_msg = validate_thresholds(data['thresholds'])
            if not is_valid:
                webhooks_ns.abort(400, error_msg)

        # Validate URL is provided when no existing URL to fall back to
        if 'webhook' in data and data['webhook']:
            webhook_data = data['webhook']
            has_existing_url = (
                webhook_service and
                webhook_service.webhook_config and
                webhook_service.webhook_config.url
            )
            if not has_existing_url and 'url' not in webhook_data:
                webhooks_ns.abort(400, 'URL required when no existing webhook config')

        try:
            # Update webhook config if provided
            if 'webhook' in data and data['webhook']:
                webhook_data = data['webhook']

                # If webhook service doesn't exist, create it
                if not webhook_service:
                    webhook_service = WebhookService()

                existing_config = webhook_service.webhook_config if webhook_service else None
                config = WebhookConfig(
                    url=webhook_data.get('url', existing_config.url if existing_config else ''),
                    enabled=webhook_data.get('enabled', existing_config.enabled if existing_config else True),
                    retry_count=webhook_data.get('retry_count', existing_config.retry_count if existing_config else 3),
                    retry_delay=webhook_data.get('retry_delay', existing_config.retry_delay if existing_config else 5),
                    timeout=webhook_data.get('timeout', existing_config.timeout if existing_config else 10)
                )
                webhook_service.set_webhook_config(config)

            # Update thresholds if provided
            if 'thresholds' in data and data['thresholds']:
                threshold_data = data['thresholds']
                thresholds = AlertThresholds(
                    temp_min_c=threshold_data.get('temp_min_c'),
                    temp_max_c=threshold_data.get('temp_max_c'),
                    humidity_min=threshold_data.get('humidity_min'),
                    humidity_max=threshold_data.get('humidity_max')
                )

                if not webhook_service:
                    webhook_service = WebhookService(alert_thresholds=thresholds)
                else:
                    webhook_service.set_alert_thresholds(thresholds)

            return {
                'message': 'Webhook configuration updated successfully',
                'config': {
                    'webhook': {
                        'url': mask_webhook_url(webhook_service.webhook_config.url) if webhook_service and webhook_service.webhook_config else None,
                        'enabled': webhook_service.webhook_config.enabled if webhook_service and webhook_service.webhook_config else False,
                        'retry_count': webhook_service.webhook_config.retry_count if webhook_service and webhook_service.webhook_config else 3,
                        'retry_delay': webhook_service.webhook_config.retry_delay if webhook_service and webhook_service.webhook_config else 5,
                        'timeout': webhook_service.webhook_config.timeout if webhook_service and webhook_service.webhook_config else 10
                    },
                    'thresholds': {
                        'temp_min_c': webhook_service.alert_thresholds.temp_min_c if webhook_service else None,
                        'temp_max_c': webhook_service.alert_thresholds.temp_max_c if webhook_service else None,
                        'humidity_min': webhook_service.alert_thresholds.humidity_min if webhook_service else None,
                        'humidity_max': webhook_service.alert_thresholds.humidity_max if webhook_service else None
                    }
                }
            }

        except Exception as e:
            error_id = generate_error_id()
            logging.exception(f"Error updating webhook config [error_id: {error_id}]")
            return {'error': 'Failed to update webhook configuration', 'error_id': error_id}, 500


@webhooks_ns.route('/test')
class WebhookTestResource(Resource):
    """Test webhook functionality"""

    @webhooks_ns.doc(security='bearer')
    @webhooks_ns.marshal_with(test_response)
    @webhooks_ns.response(400, 'Webhook not configured', error_response)
    @webhooks_ns.response(500, 'Server Error', error_response)
    @require_token
    def post(self):
        """Send a test webhook message"""
        if not webhook_service or not webhook_service.webhook_config:
            webhooks_ns.abort(400, 'Webhook not configured')

        try:
            cpu_temp = get_cpu_temperature()
            success = webhook_service.send_status_update(
                current_temp,
                current_humidity,
                cpu_temp,
                last_updated
            )

            if success:
                return {
                    'message': 'Test webhook sent successfully',
                    'timestamp': last_updated
                }
            else:
                webhooks_ns.abort(500, 'Failed to send test webhook')

        except Exception as e:
            error_id = generate_error_id()
            logging.exception(f"Error sending test webhook [error_id: {error_id}]")
            webhooks_ns.abort(500, 'Failed to send test webhook')


@webhooks_ns.route('/enable')
class WebhookEnableResource(Resource):
    """Enable webhook notifications"""

    @webhooks_ns.doc(security='bearer')
    @webhooks_ns.marshal_with(message_response)
    @webhooks_ns.response(400, 'Webhook not configured', error_response)
    @require_token
    def post(self):
        """Enable webhook notifications"""
        if not webhook_service or not webhook_service.webhook_config:
            webhooks_ns.abort(400, 'Webhook not configured')

        webhook_service.webhook_config.enabled = True
        logging.info("Webhook notifications enabled")

        return {
            'message': 'Webhook notifications enabled',
            'enabled': True
        }


@webhooks_ns.route('/disable')
class WebhookDisableResource(Resource):
    """Disable webhook notifications"""

    @webhooks_ns.doc(security='bearer')
    @webhooks_ns.marshal_with(message_response)
    @webhooks_ns.response(400, 'Webhook not configured', error_response)
    @require_token
    def post(self):
        """Disable webhook notifications"""
        if not webhook_service or not webhook_service.webhook_config:
            webhooks_ns.abort(400, 'Webhook not configured')

        webhook_service.webhook_config.enabled = False
        logging.info("Webhook notifications disabled")

        return {
            'message': 'Webhook notifications disabled',
            'enabled': False
        }


# Production Deployment Endpoints
# ============================================================================

@app.route('/health')
def health():
    """Health check endpoint for monitoring and load balancers"""
    try:
        sensor_alive = sensor_thread is not None and sensor_thread.is_alive()
        return jsonify({
            'status': 'healthy',
            'uptime_seconds': time.time() - app_start_time,
            'sensor_thread_alive': sensor_alive,
            'timestamp': time.time()
        }), 200
    except Exception as e:
        error_id = generate_error_id()
        logging.exception(f"Health check error [error_id: {error_id}]")
        return jsonify({'status': 'error', 'error_id': error_id}), 500


@app.route('/metrics')
def metrics():
    """System and application metrics for Pi 4 monitoring"""
    try:
        metrics_data = {
            'application': {
                'total_requests': request_counter,
                'webhook_alerts_sent': webhook_alert_counter,
                'uptime_seconds': time.time() - app_start_time,
                'last_sensor_update': last_updated,
                'current_temp_c': current_temp,
                'current_humidity_percent': current_humidity,
                'sensor_thread_alive': sensor_thread is not None and sensor_thread.is_alive()
            },
            'hardware': {
                'cpu_temp_c': get_cpu_temperature()
            }
        }

        # Add system metrics if psutil is available
        if psutil:
            try:
                process = psutil.Process()
                metrics_data['system'] = {
                    'cpu_percent': psutil.cpu_percent(interval=0.1),
                    'memory_mb': process.memory_info().rss / 1024 / 1024,
                    'memory_percent': process.memory_percent(),
                    'threads': process.num_threads(),
                    'file_descriptors': process.num_fds() if hasattr(process, 'num_fds') else 'N/A'
                }
            except Exception as psutil_error:
                logging.exception("Error collecting system metrics")
                metrics_data['system'] = {'error': 'Unable to collect system metrics'}
        else:
            metrics_data['system'] = {'error': 'psutil not available'}

        return jsonify(metrics_data), 200
    except Exception as e:
        error_id = generate_error_id()
        logging.exception(f"Metrics endpoint error [error_id: {error_id}]")
        return jsonify({'error': 'Unable to retrieve metrics', 'error_id': error_id}), 500


def start_sensor_thread():
    """
    Start the background sensor thread.

    Returns:
        threading.Thread: The started sensor thread

    Raises:
        RuntimeError: If sensor thread fails to start
    """
    global sensor_thread

    if sensor_thread is not None and sensor_thread.is_alive():
        logging.warning("Sensor thread is already running, skipping restart")
        return sensor_thread

    logging.info("Starting temperature monitor sensor thread")
    sensor_thread = threading.Thread(target=update_sensor_data, daemon=True)
    sensor_thread.start()

    # Give the thread a moment to get initial readings
    time.sleep(2)

    if not sensor_thread.is_alive():
        raise RuntimeError("Sensor thread failed to start")

    logging.info("Sensor thread started successfully")
    return sensor_thread


def increment_request_counter():
    """Middleware-like function to track requests"""
    global request_counter
    with threading.Lock():
        request_counter += 1


def increment_alert_counter():
    """Increment webhook alert counter"""
    global webhook_alert_counter
    with threading.Lock():
        webhook_alert_counter += 1


# Add request counter tracking
@app.before_request
def before_request():
    """Track incoming requests for metrics"""
    increment_request_counter()


if __name__ == '__main__':
    try:
        # Start the background sensor thread
        start_sensor_thread()

        # Start the Flask web server in development mode
        logging.info("Starting Flask development server on 0.0.0.0:8080")
        app.run(host='0.0.0.0', port=8080)
    except Exception as e:
        logging.error(f"Failed to start service: {e}")
        raise
