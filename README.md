# Server Room Environmental Monitor

A lightweight environmental monitoring system for server rooms or any space where temperature and humidity tracking is critical. Built on a Raspberry Pi Zero 2 W with a Sense HAT.

![image](https://github.com/user-attachments/assets/c96b3e96-c6e6-415d-afc3-7bb13eb406ee)


## Features

- **Real-time Temperature Monitoring**: Measures ambient temperature with hardware compensation for CPU heat
- **Humidity Tracking**: Monitors relative humidity percentage
- **Web Dashboard**: Clean, responsive web interface automatically refreshes every 60 seconds
- **API Endpoints**: JSON data access for integration with other monitoring systems
- **LED Display**: Shows current temperature on the Sense HAT LED matrix
- **Logging**: Records all measurements to a log file

## Hardware Requirements

- Raspberry Pi (Zero 2 W or other model)
- Sense HAT add-on board
- Power supply
- (Optional) Case for the Raspberry Pi

## Installation

### Prerequisites

```bash
# Install required system packages
sudo apt-get update
sudo apt-get install -y python3-pip python3-sense-hat

# Create a virtual environment (optional but recommended)
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install flask
```

### Setup

1. Clone this repository:
   ```bash
   git clone https://github.com/yourusername/temp_monitor.git
   cd temp_monitor
   ```

2. Configure log file location:
   Edit the `temp_monitor.py` file to update the log file path if needed:
   ```python
   logging.basicConfig(
       filename='/home/yourusername/temp_monitor.log',
       level=logging.INFO,
       format='%(asctime)s - %(levelname)s - %(message)s'
   )
   ```

3. (Optional) Add a custom logo:
   Place your image file at the location specified in the code:
   ```python
   with open("/home/yourusername/logo.gif", "rb") as image_file:
   ```

4. Set up as a service (for automatic startup):
   Create a systemd service file:
   ```bash
   sudo nano /etc/systemd/system/temp_monitor.service
   ```
   
   Add the following content:
   ```
   [Unit]
   Description=Temperature Monitor Service
   After=network.target

   [Service]
   User=yourusername
   WorkingDirectory=/home/yourusername/temp_monitor
   ExecStart=/home/yourusername/temp_monitor/venv/bin/python3 temp_monitor.py
   Restart=always
   RestartSec=10

   [Install]
   WantedBy=multi-user.target
   ```

   Enable and start the service:
   ```bash
   sudo systemctl enable temp_monitor.service
   sudo systemctl start temp_monitor.service
   ```

## Usage

### Web Dashboard

Access the web dashboard by navigating to:
```
http://[raspberry-pi-ip-address]:8080
```

The dashboard will automatically refresh every 60 seconds.

### API Endpoints

#### Temperature and Humidity Data
```
GET http://[raspberry-pi-ip-address]:8080/api/temp
```

Returns:
```json
{
  "temperature_c": 23.5,
  "temperature_f": 74.3,
  "humidity": 45.2,
  "timestamp": "2023-09-19 14:23:45"
}
```

#### Raw Sensor Data (for debugging)
```
GET http://[raspberry-pi-ip-address]:8080/api/raw
```

Returns:
```json
{
  "cpu_temperature": 54.2,
  "raw_temperature": 32.6,
  "compensated_temperature": 23.5,
  "humidity": 45.2,
  "timestamp": "2023-09-19 14:23:45"
}
```

## Temperature Compensation

The system compensates for the effect of CPU heat on temperature readings using a formula:
```
compensated_temp = raw_temp - ((cpu_temp - raw_temp) * factor)
```
Where `factor` is a calibration value (default 0.7) that may need adjustment based on your specific hardware configuration and enclosure.

## Customization

### Sampling Interval

To change how often temperature readings are updated, modify the `sampling_interval` variable (in seconds):

```python
sampling_interval = 60  # seconds between temperature updates
```

### Web Interface

The web interface uses an embedded HTML template with CSS. You can customize the appearance by modifying the HTML template in the `index()` function.

## Troubleshooting

- **Sense HAT not detected**: Ensure the HAT is properly connected and that I2C is enabled (use `sudo raspi-config`)
- **Web interface not accessible**: Check that port 8080 is not blocked by a firewall
- **Inaccurate temperature**: Adjust the compensation factor in the `get_compensated_temperature()` function

## License

[MIT License](LICENSE)

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request. 
