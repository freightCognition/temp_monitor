# Temperature Monitor

A robust environmental monitoring system for server rooms or any space requiring temperature and humidity tracking. Built for production deployment with Docker support, configurable hardware abstraction, and comprehensive monitoring features.

![Temperature Monitor Dashboard](https://github.com/user-attachments/assets/c96b3e96-c6e6-415d-afc3-7bb13eb406ee)

## Features

### Core Monitoring
- **Real-time Temperature Monitoring**: Measures ambient temperature with configurable CPU heat compensation
- **Humidity Tracking**: Monitors relative humidity percentage
- **Web Dashboard**: Clean, responsive web interface with automatic refresh
- **REST API**: Secured JSON endpoints for integration with monitoring systems
- **Health Checks**: Built-in health monitoring for service status

### Production Ready
- **Docker Support**: Multi-stage containerization with optimized production builds
- **Environment Configuration**: Flexible configuration via environment variables
- **Hardware Abstraction**: Mock sensors for development/testing environments
- **Security Features**: Bearer token authentication, CORS support, security headers
- **Rate Limiting**: Configurable API rate limiting
- **Logging**: Structured logging with configurable levels and formats

### Hardware Integration
- **Raspberry Pi Compatible**: Optimized for Raspberry Pi with Sense HAT
- **LED Display**: Shows current temperature on Sense HAT LED matrix
- **Graceful Fallbacks**: Continues operation without hardware dependencies

## Quick Start with Docker

### Development Environment

```bash
# Clone the repository
git clone <your-repo-url>
cd temp_monitor

# Start development environment
docker-compose -f docker-compose.dev.yml up --build
```

Access the dashboard at `http://localhost:8080`

### Production Deployment

```bash
# Create production environment file
cp .env.example .env
# Edit .env and set BEARER_TOKEN (generate with: python -c "import secrets; print(secrets.token_hex(32))")

# Start production environment
docker-compose up -d --build
```

Access the dashboard at `http://localhost:5000`

## Manual Installation

### Prerequisites

```bash
# Install system packages (Raspberry Pi)
sudo apt-get update
sudo apt-get install -y python3-pip python3-sense-hat python3-venv

# For other systems (mock sensors will be used automatically)
# python3-sense-hat is not required
```

### Setup

1. **Clone and install dependencies:**
   ```bash
   git clone <your-repo-url>
   cd temp_monitor
   
   # Create virtual environment
   python3 -m venv venv
   source venv/bin/activate
   
   # Install dependencies
   pip install -r requirements.txt
   ```

2. **Configure environment:**
   ```bash
   # Copy example configuration
   cp .env.example .env
   
   # Generate secure bearer token
   python generate_token.py
   
   # Edit .env to customize settings (optional)
   nano .env
   ```

3. **Run the application:**
   ```bash
   python temp_monitor.py
   ```

4. **Set up as systemd service (optional):**
   ```bash
   sudo tee /etc/systemd/system/temp-monitor.service > /dev/null <<EOF
   [Unit]
   Description=Temperature Monitor Service
   After=network.target
   
   [Service]
   Type=simple
   User=$USER
   WorkingDirectory=$(pwd)
   Environment=PATH=$(pwd)/venv/bin
   ExecStart=$(pwd)/venv/bin/python temp_monitor.py
   Restart=always
   RestartSec=10
   
   [Install]
   WantedBy=multi-user.target
   EOF
   
   sudo systemctl enable temp-monitor.service
   sudo systemctl start temp-monitor.service
   ```

## Configuration

The application is configured via environment variables. Key settings:

| Variable | Default | Description |
|----------|---------|-------------|
| `ENVIRONMENT` | `development` | Deployment environment |
| `USE_MOCK_SENSORS` | Auto-detect | Force mock sensors for development |
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `5000` | Server port |
| `BEARER_TOKEN` | Generated | API authentication token |
| `SAMPLING_INTERVAL` | `60.0` | Seconds between sensor readings |
| `LOG_LEVEL` | `INFO` | Logging verbosity |
| `ENABLE_CORS` | `false` | Enable CORS for API |
| `RATE_LIMIT_PER_MINUTE` | `60` | API rate limiting |

See `.env.example` for complete configuration options.

## API Usage

All API endpoints require Bearer token authentication:

```bash
export TOKEN="your_bearer_token_here"
curl -H "Authorization: Bearer $TOKEN" http://localhost:5000/api/temp
```

### Endpoints

#### Temperature Data
```bash
GET /api/temp
```
Returns current temperature and humidity:
```json
{
  "temperature_c": 23.5,
  "temperature_f": 74.3,
  "humidity": 45.2,
  "timestamp": "2023-09-19 14:23:45",
  "sensor_type": "real"
}
```

#### Raw Sensor Data
```bash
GET /api/raw
```
Returns detailed sensor information including CPU temperature:
```json
{
  "cpu_temperature": 54.2,
  "raw_temperature": 32.6,
  "compensated_temperature": 23.5,
  "humidity": 45.2,
  "timestamp": "2023-09-19 14:23:45",
  "sensor_type": "real",
  "config": {
    "sampling_interval": 60.0,
    "cpu_temp_factor": 2.0,
    "temperature_samples": 3
  }
}
```

#### Health Check
```bash
GET /health
```
Returns service health status:
```json
{
  "status": "healthy",
  "timestamp": "2023-09-19 14:23:45",
  "sensors": {
    "available": true,
    "type": "real"
  },
  "config": {
    "environment": "production",
    "docker": true
  }
}
```

#### Token Management
```bash
# Verify token
GET /api/verify-token

# Generate new token (requires current valid token)
POST /api/generate-token
```

## Docker Deployment

### Production
```bash
# Standard deployment
docker-compose up -d

# With custom configuration
cp .env.example .env
# Edit .env with your settings
docker-compose up -d
```

### Development
```bash
# Development with hot reload
docker-compose -f docker-compose.dev.yml up

# View logs
docker-compose logs -f temperature-monitor-dev
```

### Building Custom Images
```bash
# Production image
docker build --target production -t temp-monitor:prod .

# Development image
docker build --target development -t temp-monitor:dev .

# Multi-architecture build (for Raspberry Pi)
docker buildx build --platform linux/arm64,linux/amd64 --target production -t temp-monitor:prod .
```

## Hardware Setup

### Raspberry Pi with Sense HAT
1. Install Sense HAT on Raspberry Pi GPIO pins
2. Enable I2C: `sudo raspi-config` → Advanced → I2C → Enable
3. Install system packages: `sudo apt-get install python3-sense-hat`
4. Run with real sensors: `USE_MOCK_SENSORS=false`

### Development/Testing
The application automatically uses mock sensors when:
- Running in Docker containers
- Sense HAT hardware is not available
- `USE_MOCK_SENSORS=true` is set

## Temperature Compensation

CPU heat affects sensor readings. The compensation formula:
```
compensated_temp = raw_temp - ((cpu_temp - raw_temp) / CPU_TEMP_FACTOR)
```

Adjust `CPU_TEMP_FACTOR` (default: 2.0) based on your hardware setup.

## Monitoring and Alerting

### Health Checks
- HTTP endpoint: `/health`
- Docker health checks included
- Kubernetes readiness/liveness probes supported

### Logging
- Structured logging with configurable levels
- JSON format for production environments
- Container-friendly stdout logging in Docker

### Metrics Integration
The API provides detailed sensor data suitable for integration with:
- Prometheus/Grafana
- InfluxDB/Telegraf
- Custom monitoring solutions

## Security

- **Bearer Token Authentication**: Secure API access
- **Security Headers**: OWASP recommended headers in production
- **CORS Configuration**: Configurable cross-origin access
- **Rate Limiting**: Protection against API abuse
- **Non-root Container**: Docker containers run as unprivileged user

## Troubleshooting

### Common Issues

**Sense HAT not detected:**
- Ensure HAT is properly seated on GPIO pins
- Enable I2C: `sudo raspi-config`
- Check kernel modules: `lsmod | grep i2c`

**API authentication failures:**
- Verify bearer token is correct
- Check token format: 64-character hex string
- Regenerate token: `python generate_token.py`

**Container issues:**
- Check logs: `docker-compose logs`
- Verify environment variables
- Ensure volumes are properly mounted

**Web interface not accessible:**
- Check firewall settings
- Verify port mapping in docker-compose
- Check application logs for errors

### Debug Mode

Enable debug logging:
```bash
export DEBUG=true
export LOG_LEVEL=DEBUG
python temp_monitor.py
```

Or in Docker:
```bash
docker-compose -f docker-compose.dev.yml up
```

## Development

### Project Structure
```
├── temp_monitor.py          # Main application
├── config.py                # Configuration management
├── sensor_interface.py      # Hardware abstraction
├── generate_token.py        # Token generation utility
├── requirements.txt         # Python dependencies
├── Dockerfile               # Multi-stage container build
├── docker-compose.yml       # Production compose
├── docker-compose.dev.yml   # Development compose
├── .env.example             # Configuration template
├── assets/                  # Static assets (logo, favicon)
└── README.md               # This file
```

### Contributing

1. Fork the repository
2. Create feature branch
3. Make changes with tests
4. Submit pull request

### Testing

```bash
# Run with mock sensors for testing
export USE_MOCK_SENSORS=true
python temp_monitor.py

# Test API endpoints
export TOKEN="your_token_here"
curl -H "Authorization: Bearer $TOKEN" http://localhost:5000/health
```

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Support

For issues and questions:
1. Check the troubleshooting section above
2. Review logs for error messages
3. Create an issue in the project repository