from sense_hat import SenseHat
from flask import Flask, jsonify, render_template_string, request, abort
import time
import logging
import threading
import statistics
import os
import functools
from dotenv import load_dotenv
from webhook_service import WebhookService, WebhookConfig, AlertThresholds

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

# Global variables to store sensor data
current_temp = 0
current_humidity = 0
last_updated = "Never"
sampling_interval = 60  # seconds between temperature updates

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

# Get bearer token from environment (required)
BEARER_TOKEN = os.getenv('BEARER_TOKEN')
if not BEARER_TOKEN:
    logging.error("BEARER_TOKEN not set in environment. API endpoints will not work.")
    print("ERROR: BEARER_TOKEN environment variable is required.")
    print("Generate a token with: python3 -c \"import secrets; print(secrets.token_hex(32))\"")
    print("Then add it to your .env file: BEARER_TOKEN=<your_token>")
else:
    logging.info("Bearer token loaded from environment")

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
                    Monitoring device: Raspberry Pi Zero 2 W with Sense HAT<br>                                   
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

# Webhook management endpoints
@app.route('/api/webhook/config', methods=['GET'])
@require_token
def get_webhook_config():
    """Get current webhook configuration"""
    if not webhook_service or not webhook_service.webhook_config:
        return jsonify({
            'enabled': False,
            'message': 'Webhook not configured'
        })

    config = webhook_service.webhook_config
    thresholds = webhook_service.alert_thresholds

    return jsonify({
        'webhook': {
            'url': config.url,
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
    })

@app.route('/api/webhook/config', methods=['PUT'])
@require_token
def update_webhook_config():
    """Update webhook configuration"""
    global webhook_service

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    try:
        # Update webhook config if provided
        if 'webhook' in data:
            webhook_data = data['webhook']

            # If webhook service doesn't exist, create it
            if not webhook_service:
                if 'url' not in webhook_data:
                    return jsonify({'error': 'URL required to create webhook config'}), 400

                webhook_service = WebhookService()

            config = WebhookConfig(
                url=webhook_data.get('url', webhook_service.webhook_config.url if webhook_service.webhook_config else ''),
                enabled=webhook_data.get('enabled', True),
                retry_count=webhook_data.get('retry_count', 3),
                retry_delay=webhook_data.get('retry_delay', 5),
                timeout=webhook_data.get('timeout', 10)
            )
            webhook_service.set_webhook_config(config)

        # Update thresholds if provided
        if 'thresholds' in data:
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

        return jsonify({
            'message': 'Webhook configuration updated successfully',
            'config': {
                'webhook': {
                    'url': webhook_service.webhook_config.url if webhook_service.webhook_config else None,
                    'enabled': webhook_service.webhook_config.enabled if webhook_service.webhook_config else False
                },
                'thresholds': {
                    'temp_min_c': webhook_service.alert_thresholds.temp_min_c,
                    'temp_max_c': webhook_service.alert_thresholds.temp_max_c,
                    'humidity_min': webhook_service.alert_thresholds.humidity_min,
                    'humidity_max': webhook_service.alert_thresholds.humidity_max
                }
            }
        })

    except Exception as e:
        logging.error(f"Error updating webhook config: {e}")
        return jsonify({
            'error': 'Failed to update webhook configuration',
            'details': str(e)
        }), 500

@app.route('/api/webhook/test', methods=['POST'])
@require_token
def test_webhook():
    """Send a test webhook message"""
    if not webhook_service or not webhook_service.webhook_config:
        return jsonify({
            'error': 'Webhook not configured'
        }), 400

    try:
        cpu_temp = get_cpu_temperature()
        success = webhook_service.send_status_update(
            current_temp,
            current_humidity,
            cpu_temp,
            last_updated
        )

        if success:
            return jsonify({
                'message': 'Test webhook sent successfully',
                'timestamp': last_updated
            })
        else:
            return jsonify({
                'error': 'Failed to send test webhook'
            }), 500

    except Exception as e:
        logging.error(f"Error sending test webhook: {e}")
        return jsonify({
            'error': 'Failed to send test webhook',
            'details': str(e)
        }), 500

@app.route('/api/webhook/enable', methods=['POST'])
@require_token
def enable_webhook():
    """Enable webhook notifications"""
    if not webhook_service or not webhook_service.webhook_config:
        return jsonify({
            'error': 'Webhook not configured'
        }), 400

    webhook_service.webhook_config.enabled = True
    logging.info("Webhook notifications enabled")

    return jsonify({
        'message': 'Webhook notifications enabled',
        'enabled': True
    })

@app.route('/api/webhook/disable', methods=['POST'])
@require_token
def disable_webhook():
    """Disable webhook notifications"""
    if not webhook_service or not webhook_service.webhook_config:
        return jsonify({
            'error': 'Webhook not configured'
        }), 400

    webhook_service.webhook_config.enabled = False
    logging.info("Webhook notifications disabled")

    return jsonify({
        'message': 'Webhook notifications disabled',
        'enabled': False
    })

if __name__ == '__main__':
    # Start the background thread to update sensor data
    logging.info("Starting temperature monitor service")
    sensor_thread = threading.Thread(target=update_sensor_data, daemon=True)
    sensor_thread.start()
    
    # Give the thread a moment to get initial readings
    time.sleep(2)
    
    # Start the Flask web server
    app.run(host='0.0.0.0', port=8080)
