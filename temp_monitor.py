"""
Temperature Monitor Application
Refactored version with configurable paths, hardware abstraction, and improved error handling.
"""

from flask import Flask, jsonify, render_template_string, send_file, request, abort
import time
import logging
import threading
import statistics
import base64
import os
import secrets
import functools
from pathlib import Path
from dotenv import load_dotenv

from config import config
from sensor_interface import create_sensor_interface

# Production features
try:
    from flask_cors import CORS
except ImportError:
    CORS = None

try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
except ImportError:
    Limiter = None
    get_remote_address = None

# Load environment variables from .env file
load_dotenv()

# Configure logging
def setup_logging():
    """Configure logging based on environment."""
    log_format = config.log_format
    log_level = config.log_level
    
    # Clear any existing handlers
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    
    # Create log directory if needed
    config.create_directories()
    
    if config.is_docker:
        # For Docker, log to stdout/stderr
        logging.basicConfig(
            level=log_level,
            format=log_format,
            handlers=[
                logging.StreamHandler()
            ]
        )
    else:
        # For regular deployment, log to file
        logging.basicConfig(
            filename=config.log_file_path,
            level=log_level,
            format=log_format
        )

setup_logging()

# Validate configuration
config_issues = config.validate()
if config_issues:
    logging.warning(f"Configuration issues detected: {config_issues}")

# Initialize sensor interface
sensor = create_sensor_interface(use_mock=config.use_mock_sensors)
if sensor.is_available():
    logging.info(f"Sensor interface initialized: {'Mock' if config.use_mock_sensors else 'Real'} sensors")
else:
    logging.error("Failed to initialize sensor interface")

app = Flask(__name__)

# Configure production features
if config.enable_cors and CORS:
    CORS(app, origins=config.cors_origins)
    logging.info(f"CORS enabled for origins: {config.cors_origins}")

# Configure rate limiting
limiter = None
if Limiter and get_remote_address:
    limiter = Limiter(
        app,
        key_func=get_remote_address,
        default_limits=[f"{config.rate_limit_per_minute} per minute"],
        storage_uri="memory://"
    )
    logging.info(f"Rate limiting enabled: {config.rate_limit_per_minute} requests per minute")

# Global variables to store sensor data
current_temp = 0
current_humidity = 0
last_updated = "Never"

# Get bearer token from environment or generate a new one if not present
BEARER_TOKEN = config.bearer_token
if not BEARER_TOKEN:
    # Generate a new token if one doesn't exist
    BEARER_TOKEN = secrets.token_hex(32)  # 64 character hex string
    logging.info("Generated new bearer token")
    
    # Save the token to .env file
    try:
        with open('.env', 'a') as env_file:
            env_file.write(f"BEARER_TOKEN={BEARER_TOKEN}\n")
        logging.info("Saved bearer token to .env file")
        print(f"New bearer token generated and saved to .env file: {BEARER_TOKEN}")
    except Exception as e:
        logging.error(f"Failed to save bearer token to .env file: {e}")
        print(f"WARNING: Generated bearer token but failed to save to .env file: {e}")
        print(f"Please manually add this token to your .env file: BEARER_TOKEN={BEARER_TOKEN}")
else:
    logging.info("Using bearer token from configuration")

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

def load_image_base64():
    """Load and encode the logo image file"""
    try:
        image_path = Path(config.logo_image_path)
        if image_path.exists():
            with open(image_path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                image_base64 = f"data:image/gif;base64,{encoded_string}"
                logging.info(f"Successfully loaded and encoded image from {image_path}")
                return image_base64
        else:
            logging.warning(f"Logo image not found at {image_path}")
            return ""
    except Exception as e:
        logging.error(f"Failed to load image: {e}")
        return ""

# Load the logo image
image_base64 = load_image_base64()

@app.before_request
def log_request_info():
    """Log request information for monitoring"""
    if request.path.startswith('/api/'):
        logging.info(f"API request: {request.method} {request.path} from {request.remote_addr}")

@app.after_request
def add_security_headers(response):
    """Add security headers to all responses"""
    if config.is_production:
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Content-Security-Policy'] = "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:"
    
    # Add custom headers for monitoring
    response.headers['X-Service-Name'] = 'temperature-monitor'
    response.headers['X-Environment'] = config.environment
    
    return response

def get_cpu_temperature():
    """Get the temperature of the CPU for compensation"""
    try:
        return sensor.get_cpu_temperature()
    except Exception as e:
        logging.error(f"Failed to get CPU temperature: {e}")
        return None

def get_compensated_temperature():
    """Get temperature from sensors with CPU compensation"""
    try:
        # Get CPU temperature
        cpu_temp = get_cpu_temperature()
        
        # Get raw temperatures from sensor
        raw_temps = []
        for _ in range(config.temperature_samples):
            try:
                raw_temps.append(sensor.get_temperature())
                time.sleep(0.1)
            except Exception as e:
                logging.error(f"Error reading temperature sample: {e}")
                continue
        
        if not raw_temps:
            logging.error("No valid temperature readings obtained")
            return 20.0  # Fallback temperature
        
        # Remove outliers and calculate the average raw temperature
        if len(raw_temps) > 2:  # Need at least 3 readings to filter outliers
            raw_temps.sort()
            # Remove highest and lowest reading
            filtered_temps = raw_temps[1:-1]
            raw_temp = statistics.mean(filtered_temps)
        else:
            raw_temp = statistics.mean(raw_temps)
        
        # Apply compensation formula based on CPU temperature
        if cpu_temp is not None and cpu_temp > raw_temp:
            comp_temp = raw_temp - ((cpu_temp - raw_temp) / config.cpu_temp_factor)
        else:
            comp_temp = raw_temp
        
        return round(comp_temp, 1)
    
    except Exception as e:
        logging.error(f"Error in get_compensated_temperature: {e}")
        return 20.0  # Fallback temperature

def get_humidity():
    """Get humidity from sensors"""
    try:
        # Take multiple readings and average them
        readings = []
        for _ in range(config.temperature_samples):
            try:
                readings.append(sensor.get_humidity())
                time.sleep(0.1)
            except Exception as e:
                logging.error(f"Error reading humidity sample: {e}")
                continue
        
        if not readings:
            logging.error("No valid humidity readings obtained")
            return 50.0  # Fallback humidity
        
        # Remove outliers if possible
        if len(readings) > 2:
            readings.sort()
            readings = readings[1:-1]  # Remove highest and lowest
        
        # Return the average
        return round(statistics.mean(readings), 1)
    
    except Exception as e:
        logging.error(f"Error in get_humidity: {e}")
        return 50.0  # Fallback humidity

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
            
            # Display temperature on LED matrix if available
            try:
                temp_f = round((current_temp * 9/5) + 32, 1)
                message = f"Temp: {temp_f}F"
                sensor.show_message(message)
            except Exception as e:
                logging.debug(f"Error displaying message on LED: {e}")
            
            # Sleep for the specified interval
            time.sleep(config.sampling_interval)
        except Exception as e:
            logging.error(f"Error updating sensor data: {e}")
            time.sleep(5)  # Short sleep before retry on error

@app.route('/health')
def health_check():
    """Health check endpoint for monitoring"""
    if not config.health_check_enabled:
        return jsonify({'status': 'disabled'}), 404
    
    health_status = {
        'status': 'healthy',
        'timestamp': time.strftime("%Y-%m-%d %H:%M:%S"),
        'sensors': {
            'available': sensor.is_available(),
            'type': 'mock' if config.use_mock_sensors else 'real'
        },
        'config': {
            'environment': config.environment,
            'docker': config.is_docker,
            'log_path': config.log_file_path
        },
        'data': {
            'last_updated': last_updated,
            'temperature': current_temp,
            'humidity': current_humidity
        }
    }
    
    # Check for any issues
    issues = []
    
    # Check if sensor is available
    if not sensor.is_available():
        issues.append("Sensor interface not available")
        health_status['status'] = 'degraded'
    
    # Check if bearer token is configured
    if not BEARER_TOKEN:
        issues.append("Bearer token not configured")
        health_status['status'] = 'degraded'
    
    # Check if files are accessible
    try:
        Path(config.log_file_path).parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        issues.append("Log directory not accessible")
        health_status['status'] = 'degraded'
    
    if issues:
        health_status['issues'] = issues
    
    status_code = 200 if health_status['status'] == 'healthy' else 503
    return jsonify(health_status), status_code

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
            <link rel="shortcut icon" href="/favicon.ico">
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
                .status {
                    font-size: 12px;
                    color: #999;
                    margin-top: 10px;
                }
            </style>
        </head>
        <body>
            <div class="container">
                {% if image_data %}
                <img src="{{ image_data }}" alt="Company Logo" class="logo">
                {% endif %}
                <h1>Server Room Environmental Monitor</h1>
                
                <h2>Temperature</h2>
                <div class="reading temp">{{ temperature }}<span class="unit">°C</span></div>
                <div class="fahrenheit">({{ fahrenheit }}°F)</div>
                
                <h2>Humidity</h2>
                <div class="reading humidity">{{ humidity }}<span class="unit">%</span></div>
                
                <div class="info">
                    Last updated: {{ last_updated }}<br>
                    Monitoring device: {{ device_info }}<br>
                </div>
                <div class="status">
                    Environment: {{ environment }} | Sensors: {{ sensor_type }}
                </div>
            </div>
        </body>
    </html>
    """
    fahrenheit = round((current_temp * 9/5) + 32, 1)
    device_info = "Raspberry Pi Zero 2 W with Sense HAT" if not config.use_mock_sensors else "Development System with Mock Sensors"
    
    return render_template_string(
        html_template, 
        temperature=current_temp, 
        fahrenheit=fahrenheit,
        humidity=current_humidity, 
        last_updated=last_updated,
        image_data=image_base64,
        environment=config.environment.title(),
        sensor_type="Mock" if config.use_mock_sensors else "Real",
        device_info=device_info
    )

@app.route('/favicon.ico')
def favicon():
    """Serve the favicon"""
    try:
        favicon_path = Path(config.favicon_path)
        if favicon_path.exists():
            return send_file(str(favicon_path), mimetype='image/x-icon')
        else:
            logging.warning(f"Favicon not found at {favicon_path}")
            return "", 404
    except Exception as e:
        logging.error(f"Failed to serve favicon: {e}")
        return "", 404

@app.route('/api/temp')
@require_token
def api_temp():
    """API endpoint returning temperature data as JSON"""
    fahrenheit = round((current_temp * 9/5) + 32, 1)
    return jsonify({
        'temperature_c': current_temp,
        'temperature_f': fahrenheit,
        'humidity': current_humidity,
        'timestamp': last_updated,
        'sensor_type': 'mock' if config.use_mock_sensors else 'real'
    })

@app.route('/api/raw')
@require_token
def api_raw():
    """API endpoint for debugging, showing raw vs compensated temperature"""
    try:
        cpu_temp = get_cpu_temperature()
        raw_temp = sensor.get_temperature()
        return jsonify({
            'cpu_temperature': round(cpu_temp, 1) if cpu_temp is not None else None,
            'raw_temperature': round(raw_temp, 1),
            'compensated_temperature': current_temp,
            'humidity': current_humidity,
            'timestamp': last_updated,
            'sensor_type': 'mock' if config.use_mock_sensors else 'real',
            'config': {
                'sampling_interval': config.sampling_interval,
                'cpu_temp_factor': config.cpu_temp_factor,
                'temperature_samples': config.temperature_samples
            }
        })
    except Exception as e:
        logging.error(f"Error in /api/raw endpoint: {e}")
        return jsonify({
            'error': 'Failed to get raw sensor data',
            'details': str(e)
        }), 500

@app.route('/api/generate-token', methods=['POST'])
@require_token
def generate_new_token():
    """Generate a new bearer token (requires existing token to access)"""
    global BEARER_TOKEN
    
    # Generate new token
    new_token = secrets.token_hex(32)
    
    # Save to .env file
    try:
        env_path = Path('.env')
        if env_path.exists():
            # Read existing .env content
            with open(env_path, 'r') as f:
                lines = f.readlines()
            
            # Update or add BEARER_TOKEN line
            token_found = False
            with open(env_path, 'w') as f:
                for line in lines:
                    if line.startswith('BEARER_TOKEN='):
                        f.write(f"BEARER_TOKEN={new_token}\n")
                        token_found = True
                    else:
                        f.write(line)
                
                if not token_found:
                    f.write(f"BEARER_TOKEN={new_token}\n")
        else:
            # Create new .env file
            with open(env_path, 'w') as f:
                f.write(f"BEARER_TOKEN={new_token}\n")
        
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

@app.route('/api/verify-token', methods=['GET'])
@require_token
def verify_token():
    """Verify if the provided token is valid"""
    return jsonify({
        'valid': True,
        'message': 'Token is valid',
        'environment': config.environment
    })

def main():
    """Main application entry point"""
    # Start the background thread to update sensor data
    logging.info(f"Starting temperature monitor service in {config.environment} mode")
    logging.info(f"Using {'mock' if config.use_mock_sensors else 'real'} sensors")
    logging.info(f"Configuration: Host={config.host}, Port={config.port}, Debug={config.debug}")
    
    sensor_thread = threading.Thread(target=update_sensor_data, daemon=True)
    sensor_thread.start()
    
    # Give the thread a moment to get initial readings
    time.sleep(2)
    
    # Start the Flask web server
    try:
        app.run(
            host=config.host, 
            port=config.port, 
            debug=config.debug
        )
    except Exception as e:
        logging.error(f"Failed to start Flask server: {e}")
        raise

if __name__ == '__main__':
    main()