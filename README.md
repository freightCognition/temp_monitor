# Server Room Temp Monitor


A lightweight environmental monitoring system for server rooms or any space where temperature and humidity tracking is critical. Built on a Raspberry Pi 4 with a Sense HAT.

![image](https://github.com/user-attachments/assets/c96b3e96-c6e6-415d-afc3-7bb13eb406ee)


## Features

- **Real-time Temperature Monitoring**: Measures ambient temperature with hardware compensation for CPU heat
- **Humidity Tracking**: Monitors relative humidity percentage
- **Web Dashboard**: Clean, responsive web interface automatically refreshes every 60 seconds
- **API Endpoints**: JSON data access for integration with other monitoring systems
- **LED Display**: Shows current temperature on the Sense HAT LED matrix
- **Logging**: Records all measurements to a log file

## Hardware Requirements

- Raspberry Pi 4
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

3. Generate a bearer token and add it to `.env`:
   ```bash
   # Generate a secure token
   python3 -c "import secrets; print(secrets.token_hex(32))"

   # Copy the output and add it to your .env file:
   # BEARER_TOKEN=<your_generated_token>
   ```

   **Note:** If `BEARER_TOKEN` is not set in `.env`, the app will:
   1. Log an error
   2. Print instructions for generating a token:
   ```
   ERROR: BEARER_TOKEN environment variable is required.
   Generate a token with: python3 -c "import secrets; print(secrets.token_hex(32))"
   Then add it to your .env file: BEARER_TOKEN=<your_token>
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

### Setting Bearer Token for Docker

Before starting the container, ensure you have a bearer token in your `.env` file:

```bash
# Generate a secure token
python3 -c "import secrets; print(secrets.token_hex(32))"

# Add to .env file:
# BEARER_TOKEN=<your_generated_token>
```

The `.env` file is mounted as a volume, so the token will be available to the container.

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

## Production Deployment

For production deployments on Raspberry Pi 4, the application is optimized with:

- **Waitress WSGI Server**: Production-grade Python web server with single-process, single-thread configuration for resource efficiency
- **Health Check Endpoint**: `/health` endpoint for monitoring and load balancer integration
- **Metrics Endpoint**: `/metrics` for system and application metrics (CPU, memory, uptime, request counts)
- **Memory Monitoring**: Automatic detection and alerting for memory leaks
- **Systemd Integration**: Pre-configured systemd service with memory limits and restart policies
- **Docker Optimizations**: Memory limits, health checks, and resource constraints

### Quick Start - Production Deployment

**Option 1: Docker Compose (Recommended)**
```bash
docker-compose up -d
```

**Option 2: Systemd Service**
```bash
sudo cp deployment/systemd/temp-monitor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable temp-monitor.service
sudo systemctl start temp-monitor.service
```

**Option 3: Direct Startup Script**
```bash
./start_production.sh
```

### Monitoring Production Deployment

Check service health:
```bash
curl http://localhost:8080/health
```

View application and system metrics:
```bash
curl http://localhost:8080/metrics | python -m json.tool
```

Check service status (systemd):
```bash
sudo systemctl status temp-monitor.service
sudo journalctl -u temp-monitor.service -f
```

Check container status (Docker):
```bash
docker-compose ps
docker-compose logs -f temp-monitor
```

### Production Configuration

Memory limits (configurable):
- Process limit: 512MB
- Alert threshold: 400MB
- Auto-restart at limit

Server settings:
- Single worker / single thread
- 50 concurrent connection limit
- 120-second request timeout

For detailed production deployment guide, see [docs/PI4_DEPLOYMENT.md](docs/PI4_DEPLOYMENT.md)

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
- **BEARER_TOKEN**: API authentication token (required, generate with `python3 -c "import secrets; print(secrets.token_hex(32))"`)
- **Static assets**: Images are served from the `static/` directory. Replace `static/My-img8bit-1com-Effect.gif` or `static/f
avicon.ico` if you need custom artwork.

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

**Authentication Required (Bearer Token):**
- `/api/temp` - Get current temperature and humidity data
- `/api/raw` - Get raw temperature data (including CPU temperature)
- `/api/verify-token` - Verify if your token is valid
- `/api/webhook/*` - Webhook management endpoints

**No Authentication Required:**
- `/health` - Health check endpoint for monitoring and load balancers
  ```json
  {
    "status": "healthy",
    "uptime_seconds": 12345,
    "sensor_thread_alive": true,
    "timestamp": 1234567890.123
  }
  ```
- `/metrics` - System and application metrics (CPU, memory, request counts, uptime)
  ```json
  {
    "application": {
      "total_requests": 1234,
      "webhook_alerts_sent": 42,
      "uptime_seconds": 12345,
      "current_temp_c": 23.5,
      "current_humidity_percent": 45.2
    },
    "system": {
      "cpu_percent": 12.5,
      "memory_mb": 120.5,
      "memory_percent": 23.5,
      "threads": 5
    },
    "hardware": {
      "cpu_temp_c": 54.2
    }
  }
  ```
- `/docs` - Swagger API documentation

## Changing the Bearer Token

To change the bearer token, generate a new one and update your `.env` file:

```bash
# Generate a new token
python3 -c "import secrets; print(secrets.token_hex(32))"

# Update .env file with the new token:
# BEARER_TOKEN=<your_new_token>

# Restart the service
sudo systemctl restart temp_monitor  # for systemd
# or
docker-compose restart  # for Docker
```

## Security Notes

- Keep your bearer token secure and don't share it publicly
- The token is stored in the `.env` file, which should be kept private
- Consider regenerating the token periodically for enhanced security 








