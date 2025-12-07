from sense_hat import SenseHat
from flask import Flask, jsonify, render_template_string, request, abort
import time
import logging
import threading
import statistics
import os
import secrets
import functools
import requests
from dotenv import load_dotenv

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

def _persist_bearer_token(token):
    """Save bearer token to .env file while preserving other environment variables"""
    env_path = '.env'
    env_exists = os.path.isfile(env_path)
    env_content = []
    
    if env_exists:
        with open(env_path, 'r') as f:
            env_content = f.readlines()
    
    token_line_found = False
    for i, line in enumerate(env_content):
        if line.startswith('BEARER_TOKEN='):
            env_content[i] = f'BEARER_TOKEN={token}\n'
            token_line_found = True
            break
    
    if not token_line_found:
        env_content.append(f'BEARER_TOKEN={token}\n')
    
    with open(env_path, 'w') as f:
        f.writelines(env_content)

# Get bearer token from environment or generate a new one if not present
BEARER_TOKEN = os.getenv('BEARER_TOKEN')
if not BEARER_TOKEN:
    # Generate a new token if one doesn't exist
    BEARER_TOKEN = secrets.token_hex(32)  # 64 character hex string
    logging.info("Generated new bearer token")
    
    # Save the token to .env file (preserving other env vars)
    try:
        _persist_bearer_token(BEARER_TOKEN)
        logging.info("Saved bearer token to .env file")
        print(f"New bearer token generated and saved to .env file: {BEARER_TOKEN}")
    except Exception as e:
        logging.error(f"Failed to save bearer token to .env file: {e}")
        print(f"WARNING: Generated bearer token but failed to save to .env file: {e}")
        print(f"Please manually add this token to your .env file: BEARER_TOKEN={BEARER_TOKEN}")
else:
    logging.info("Using bearer token from .env file")

# Slack webhook configuration (optional)
SLACK_WEBHOOK_URL = os.getenv('SLACK_WEBHOOK_URL')
SLACK_NOTIFICATION_INTERVAL = int(os.getenv('SLACK_NOTIFICATION_INTERVAL', 3600))

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
            
            # Display temperature on Sense HAT LED matrix
            temp_f = round((current_temp * 9/5) + 32, 1)
            message = f"Temp: {temp_f}F"
            sense.show_message(message)
            
            # Sleep for the specified interval
            time.sleep(sampling_interval)
        except Exception as e:
            logging.error(f"Error updating sensor data: {e}")
            time.sleep(5)  # Short sleep before retry on error

def send_slack_notification():
    """Background thread function to send periodic Slack notifications"""
    global current_temp, current_humidity, last_updated
    
    while True:
        try:
            if SLACK_WEBHOOK_URL:
                temp_f = round((current_temp * 9/5) + 32, 1)
                
                message = {
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": ":thermometer: *Server Room Environmental Update*"
                            }
                        },
                        {
                            "type": "section",
                            "fields": [
                                {
                                    "type": "mrkdwn",
                                    "text": f"*Temperature:*\n{current_temp}\u00b0C ({temp_f}\u00b0F)"
                                },
                                {
                                    "type": "mrkdwn",
                                    "text": f"*Humidity:*\n{current_humidity}%"
                                }
                            ]
                        },
                        {
                            "type": "context",
                            "elements": [
                                {
                                    "type": "mrkdwn",
                                    "text": f"Updated: {last_updated}"
                                }
                            ]
                        }
                    ]
                }
                
                response = requests.post(SLACK_WEBHOOK_URL, json=message, timeout=10)
                response.raise_for_status()
                logging.info(f"Slack notification sent successfully - Temp: {current_temp}\u00b0C, Humidity: {current_humidity}%")
            
            time.sleep(SLACK_NOTIFICATION_INTERVAL)
        except Exception as e:
            logging.error(f"Error in Slack notification: {e}")
            time.sleep(60)

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

# Add a token generation endpoint (protected by existing token)
@app.route('/api/generate-token', methods=['POST'])
@require_token
def generate_new_token():
    """Generate a new bearer token (requires existing token to access)"""
    global BEARER_TOKEN
    
    # Generate new token
    new_token = secrets.token_hex(32)
    
    # Save to .env file (preserving other env vars)
    try:
        _persist_bearer_token(new_token)
        
        # Update the global token
        BEARER_TOKEN = new_token
        logging.info("Generated and saved new bearer token")
        
        return jsonify({
            'message': 'New bearer token generated successfully',
            'token': new_token
        })
    except Exception as e:
        logging.error(f"Failed to save new bearer token: {e}")
        return jsonify({
            'error': 'Failed to save new token',
            'details': str(e)
        }), 500

# Add an endpoint to check if token is valid
@app.route('/api/verify-token', methods=['GET'])
@require_token
def verify_token():
    """Verify if the provided token is valid"""
    return jsonify({
        'valid': True,
        'message': 'Token is valid'
    })

@app.route('/api/notify-slack', methods=['POST'])
@require_token
def manual_slack_notification():
    """Manually trigger a Slack notification"""
    if not SLACK_WEBHOOK_URL:
        return jsonify({'error': 'Slack webhook URL not configured'}), 400
    
    try:
        temp_f = round((current_temp * 9/5) + 32, 1)
        
        message = {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": ":thermometer: *Server Room Environmental Update*"
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Temperature:*\n{current_temp}\u00b0C ({temp_f}\u00b0F)"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Humidity:*\n{current_humidity}%"
                        }
                    ]
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"Updated: {last_updated}"
                        }
                    ]
                }
            ]
        }
        
        response = requests.post(SLACK_WEBHOOK_URL, json=message, timeout=10)
        response.raise_for_status()
        
        logging.info(f"Manual Slack notification sent - Temp: {current_temp}\u00b0C, Humidity: {current_humidity}%")
        
        return jsonify({
            'success': True,
            'message': 'Slack notification sent manually',
            'temperature_c': current_temp,
            'humidity': current_humidity
        })
    except Exception as e:
        logging.error(f"Manual Slack notification failed: {e}")
        return jsonify({'error': f'Failed to send notification: {str(e)}'}), 500

if __name__ == '__main__':
    # Start the background thread to update sensor data
    logging.info("Starting temperature monitor service")
    sensor_thread = threading.Thread(target=update_sensor_data, daemon=True)
    sensor_thread.start()
    
    # Start Slack notification thread if webhook URL is configured
    if SLACK_WEBHOOK_URL:
        slack_thread = threading.Thread(target=send_slack_notification, daemon=True)
        slack_thread.start()
        logging.info("Slack notification thread started")
    else:
        logging.info("Slack webhook URL not configured, skipping notifications")
    
    # Give threads a moment to get initial readings
    time.sleep(2)
    
    # Start the Flask web server
    app.run(host='0.0.0.0', port=8080)
