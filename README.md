# Server Room Temp Monitor


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

2. Configure environment variables:
   Copy `.env.example` to `.env` and customize paths as needed:
   ```bash
   cp .env.example .env
   ```

   Edit `.env` to set your paths:
   ```
   # Log file path (absolute or relative)
   LOG_FILE=/home/yourusername/temp_monitor.log
   ```

   Static assets (logo and favicon) are served from the repository's `static/` directory by default. Replace the files there if you want to customize the images.

3. Generate a bearer token:
   ```bash
   python generate_token.py
   ```
   This will create a secure token and save it to `.env`.

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

## Docker Deployment

The application can be deployed as a Docker container, making it easier to manage dependencies and deployment.

### Prerequisites

- Docker and Docker Compose installed on your Raspberry Pi
- Raspberry Pi with ARM architecture (armv7l or aarch64)
- Sense HAT hardware properly connected

### Preparing for Docker Deployment

1. **Create a logs directory:**
   ```bash
   mkdir -p logs
   ```

2. **(Optional) Replace static assets:**
   The container serves images from the built-in `static/` directory. If you want to override them, replace the files in `stat
ic/` before building the image or mount your own `static/` directory at runtime.

3. **Create a .env file:**
   ```bash
   cp .env.example .env
   ```

   The bearer token will be auto-generated on first run, or you can generate it manually (see below).

### Building and Running with Docker Compose

1. **Build the Docker image:**
   ```bash
   docker-compose build
   ```

2. **Start the container:**
   ```bash
   docker-compose up -d
   ```

3. **View logs:**
   ```bash
   docker-compose logs -f
   ```

4. **Stop the container:**
   ```bash
   docker-compose down
   ```

### Generating Bearer Token in Container

To generate or regenerate the bearer token inside the container:

```bash
docker-compose exec temp-monitor python generate_token.py
```

The token will be saved to the `.env` file in your project directory (which is mounted as a volume).

### Building Docker Image Manually

If you prefer to build and run without docker-compose:

```bash
# Build the image
docker build -t temp-monitor .

# Run the container
docker run -d \
  --name temp-monitor \
  --privileged \
  -p 8080:8080 \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/static:/app/static:ro \
  -v $(pwd)/.env:/app/.env \
  -v /sys:/sys:ro \
  --device /dev/i2c-1:/dev/i2c-1 \
  -e LOG_FILE=/app/logs/temp_monitor.log \
  temp-monitor
```

### Important Docker Notes

- **Privileged Mode:** The container requires privileged mode to access the I2C interface and hardware sensors on the Sense HAT
- **ARM Architecture:** This application is designed for ARM-based Raspberry Pi. The Python base image will automatically use the appropriate ARM variant
- **Device Access:** The container needs access to `/dev/i2c-1` for Sense HAT communication and `/sys` (read-only) for CPU temperature readings
- **Persistent Data:** Logs and the `.env` file are stored in mounted volumes, so they persist across container restarts
- **Auto-restart:** The docker-compose configuration includes `restart: unless-stopped` to automatically restart the container if it crashes or after system reboot

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

## Configuration

The application uses environment variables for configuration. Create a `.env` file (copy from `.env.example`) with these settings:

- **LOG_FILE**: Path to the log file (defaults to `temp_monitor.log`)
- **BEARER_TOKEN**: API authentication token (auto-generated if not provided)
- **SLACK_WEBHOOK_URL**: The unique URL provided by Slack for the incoming webhook
- **SLACK_NOTIFICATION_INTERVAL**: Frequency of notifications in seconds (defaults to 300)
- **Static assets**: Images are served from the `static/` directory. Replace `static/My-img8bit-1com-Effect.gif` or `static/f
avicon.ico` if you need custom artwork.

**Important:** When updating the `.env` file, ensure you **append** new values rather than overwriting the file, to preserve existing configurations like your bearer token.

Example using `cat` to append:
```bash
cat >> .env << EOF
# Slack Integration Settings
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
SLACK_NOTIFICATION_INTERVAL=300
EOF
```

All paths can be absolute or relative. The application will create the log directory if it doesn't exist.

## Troubleshooting

- **Sense HAT not detected**: Ensure the HAT is properly connected and that I2C is enabled (use `sudo raspi-config`)
- **Web interface not accessible**: Check that port 8080 is not blocked by a firewall
- **Inaccurate temperature**: Adjust the compensation factor in the `get_compensated_temperature()` function
- **Favicon not displaying**: Verify `static/favicon.ico` exists and is being served
- **Log file creation fails**: Ensure the directory specified in `LOG_FILE` exists or that the user has permission to create it

## License

[MIT License](LICENSE)

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

# Temperature Monitor API with Bearer Token Authentication

This application monitors temperature and humidity using a Raspberry Pi with Sense HAT and provides a web interface and API endpoints to access the data.

## API Security

The API endpoints are protected with Bearer Token authentication. You need to include a valid token in the `Authorization` header to access the API.

## Getting Started

1. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Configure your environment (see Setup section above for details)

3. Start the application:
   ```bash
   python temp_monitor.py
   ```

## Using the API

To access the API endpoints, include the bearer token in the `Authorization` header:

```bash
curl -H "Authorization: Bearer YOUR_TOKEN_HERE" http://your-server:8080/api/temp
```

### Available Endpoints

- `/api/temp` - Get current temperature and humidity data
- `/api/raw` - Get raw temperature data (including CPU temperature)
- `/api/verify-token` - Verify if your token is valid
- `/api/generate-token` - Generate a new token (requires existing valid token)

## Regenerating Tokens

You can regenerate the token in two ways:

1. Using the script:
   ```
   python generate_token.py
   ```

2. Using the API (requires existing valid token):
   ```
   curl -X POST -H "Authorization: Bearer YOUR_CURRENT_TOKEN" http://your-server:8080/api/generate-token
   ```

## Security Notes

- Keep your bearer token secure and don't share it publicly
- The token is stored in the `.env` file, which should be kept private
- Consider regenerating the token periodically for enhanced security 








