from sense_hat import SenseHat
from flask import Flask, jsonify, render_template_string, send_file
import time
import logging
import threading
import statistics
import base64
import os

# Configure logging
logging.basicConfig(
    filename='/home/fakebizprez/temp_monitor.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

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

# Try to read and encode the image file
image_base64 = ""
try:
    with open("/home/fakebizprez/My-img8bit-1com-Effect.gif", "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
        image_base64 = f"data:image/gif;base64,{encoded_string}"
        logging.info("Successfully loaded and encoded image")
except Exception as e:
    logging.error(f"Failed to load image: {e}")
    image_base64 = ""  # Keep empty if failed

# Path to favicon file
favicon_path = "/home/fakebizprez/temp-favicon.ico"

def get_cpu_temperature():
    """Get the temperature of the CPU for compensation"""
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            temp = float(f.read()) / 1000.0
        return temp
    except Exception as e:
        logging.error(f"Failed to get CPU temperature: {e}")
        return 0

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
    comp_temp = raw_temp - ((cpu_temp - raw_temp) * factor)
    
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
    
    # Return the average
    return round(statistics.mean(readings), 1)

def update_sensor_data():
    """Background thread function to update sensor data periodically"""
    global current_temp, current_humidity, last_updated
    
    while True:
        try:
            current_temp = get_compensated_temperature()
            current_humidity = get_humidity()
            last_updated = time.strftime("%Y-%m-%d %H:%M:%S")
            
            logging.info(f"Temperature: {current_temp}°C, Humidity: {current_humidity}%, CPU Temp: {get_cpu_temperature()}°C")
            
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
    global image_base64
    
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
        last_updated=last_updated,
        image_data=image_base64
    )

@app.route('/favicon.ico')
def favicon():
    """Serve the favicon"""
    try:
        return send_file(favicon_path, mimetype='image/x-icon')
    except Exception as e:
        logging.error(f"Failed to serve favicon: {e}")
        return "", 404  # Return empty response with 404 status code if favicon not found

@app.route('/api/temp')
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
def api_raw():
    """API endpoint for debugging, showing raw vs compensated temperature"""
    cpu_temp = get_cpu_temperature()
    raw_temp = sense.get_temperature()
    return jsonify({
        'cpu_temperature': round(cpu_temp, 1),
        'raw_temperature': round(raw_temp, 1),
        'compensated_temperature': current_temp,
        'humidity': current_humidity,
        'timestamp': last_updated
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
