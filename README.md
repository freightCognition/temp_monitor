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

   # Logo image path (absolute or relative)
   LOGO_PATH=/path/to/My-img8bit-1com-Effect.gif

   # Favicon path (absolute or relative)
   FAVICON_PATH=/path/to/temp-favicon.ico
   ```

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
- **LOGO_PATH**: Path to the logo image for the dashboard (defaults to `My-img8bit-1com-Effect.gif`)
- **FAVICON_PATH**: Path to the favicon file (defaults to `temp-favicon.ico`)
- **BEARER_TOKEN**: API authentication token (auto-generated if not provided)

All paths can be absolute or relative. The application will create the log directory if it doesn't exist.

## Docker Deployment

The application can be run as a Docker container, which simplifies deployment and ensures consistent environments across different systems.

### Prerequisites

- Docker and Docker Compose installed on your Raspberry Pi
- I2C enabled on the Raspberry Pi (use `sudo raspi-config`)

### Building the Docker Image

```bash
docker build -t temp-monitor .
```

### Running with Docker Compose

The easiest way to run the application is using Docker Compose:

```bash
# Create required directories and copy assets
mkdir -p logs assets
cp My-img8bit-1com-Effect.gif assets/logo.gif
cp temp-favicon.ico assets/favicon.ico

# IMPORTANT: Create .env file before starting (required for volume mount)
# If .env doesn't exist or was created as a directory by a failed mount, fix it:
rm -rf .env 2>/dev/null; cp .env.example .env

# Start the container
docker-compose up -d
```

**Note:** The `.env` file must exist as a regular file before running `docker-compose up`. If Docker previously failed to start and created `.env` as a directory, you must remove it first with `rm -rf .env` and then copy from `.env.example`.

The application will be available at `http://[raspberry-pi-ip]:8080`.

### Generating Bearer Token in Container

To generate a new bearer token inside the running container:

```bash
docker-compose exec temp-monitor python generate_token.py
```

### Viewing Logs

```bash
# View container logs
docker-compose logs -f temp-monitor

# View application logs
cat logs/temp_monitor.log
```

### Stopping the Container

```bash
docker-compose down
```

### Important Notes

- **Privileged Mode**: The container runs in privileged mode to access the Sense HAT hardware via I2C. This is required for hardware sensor access.
- **Device Access**: The container needs access to `/dev/i2c-1` for Sense HAT communication and `/sys` (read-only) for CPU temperature readings.
- **ARM Architecture**: This application is designed for Raspberry Pi (ARM architecture). The Docker image will work on armv7l (Pi 3/4) and aarch64 (Pi 4 64-bit) architectures.
- **Volume Mounts**: The `logs/` and `assets/` directories are mounted as volumes to persist data and allow easy customization of the logo and favicon.
- **Environment File**: The `.env` file is mounted into the container to provide the bearer token and other configuration.

### Docker Compose Configuration

The `docker-compose.yml` file configures:
- Port mapping (8080:8080)
- Volume mounts for logs, assets, and environment file
- Device access for I2C hardware
- Read-only access to `/sys` for CPU temperature
- Automatic restart policy

## Troubleshooting

- **Sense HAT not detected**: Ensure the HAT is properly connected and that I2C is enabled (use `sudo raspi-config`)
- **Web interface not accessible**: Check that port 8080 is not blocked by a firewall
- **Inaccurate temperature**: Adjust the compensation factor in the `get_compensated_temperature()` function
- **Favicon not displaying**: Verify the `FAVICON_PATH` points to an existing file
- **Log file creation fails**: Ensure the directory specified in `LOG_FILE` exists or that the user has permission to create it
- **Docker container fails to start**: Ensure I2C is enabled and the Sense HAT is properly connected. Check container logs with `docker-compose logs`.
- **Permission denied errors in Docker**: The container requires privileged mode for hardware access. Ensure `privileged: true` is set in docker-compose.yml.

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








