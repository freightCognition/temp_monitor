# Server Room Temperature Monitor

A lightweight environmental monitoring system for server rooms built on Raspberry Pi 4 with Sense HAT. Features real-time monitoring, REST API, Slack webhook alerts, and production-ready deployment options.

![image](https://github.com/user-attachments/assets/c96b3e96-c6e6-415d-afc3-7bb13eb406ee)

## Table of Contents

- [Features](#features)
- [Hardware Requirements](#hardware-requirements)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [API Reference](#api-reference)
- [Webhook Notifications](#webhook-notifications)
- [Deployment](#deployment)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)

## Features

- **Real-time Monitoring**: Temperature with CPU heat compensation, humidity tracking
- **Web Dashboard**: Auto-refreshing interface at port 8080
- **REST API**: JSON endpoints with Bearer token authentication
- **Swagger Documentation**: Interactive API docs at `/docs`
- **Slack Webhooks**: Threshold-based alerts with configurable cooldowns
- **Periodic Status Updates**: Scheduled status reports via webhook
- **LED Display**: Current temperature on Sense HAT matrix
- **Production Ready**: Waitress WSGI server, health checks, metrics endpoint
- **Docker Support**: Pre-configured docker-compose for easy deployment

## Hardware Requirements

- Raspberry Pi 4 (2GB+ RAM recommended)
- Sense HAT add-on board
- 5V/3A USB-C power supply
- (Optional) Case for the Raspberry Pi

## Quick Start

### 1. Clone and Install

```bash
git clone https://github.com/yourusername/temp_monitor.git
cd temp_monitor
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env

# Generate a bearer token (required)
python3 -c "import secrets; print(secrets.token_hex(32))"
# Add the output to .env as BEARER_TOKEN=<token>
```

### 3. Run

```bash
# Development
python temp_monitor.py

# Production (with Waitress)
./start_production.sh

# Docker
docker-compose up -d
```

Access the dashboard at `http://[raspberry-pi-ip]:8080`

## Configuration

All configuration is done via environment variables in `.env`. Copy `.env.example` to get started.

### Core Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `BEARER_TOKEN` | (required) | API authentication token |
| `LOG_FILE` | `temp_monitor.log` | Log file path |

### Webhook Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `SLACK_WEBHOOK_URL` | (none) | Slack incoming webhook URL |
| `WEBHOOK_ENABLED` | `true` | Enable/disable notifications |
| `WEBHOOK_RETRY_COUNT` | `3` | Retry attempts (1-10) |
| `WEBHOOK_RETRY_DELAY` | `5` | Initial retry delay in seconds |
| `WEBHOOK_TIMEOUT` | `10` | Request timeout in seconds |

### Alert Thresholds

| Variable | Default | Description |
|----------|---------|-------------|
| `ALERT_TEMP_MIN_C` | `15.0` | Low temperature alert (Celsius) |
| `ALERT_TEMP_MAX_C` | `27.0` | High temperature alert (Celsius) |
| `ALERT_HUMIDITY_MIN` | `30.0` | Low humidity alert (%) |
| `ALERT_HUMIDITY_MAX` | `70.0` | High humidity alert (%) |

### Periodic Status Updates

| Variable | Default | Description |
|----------|---------|-------------|
| `STATUS_UPDATE_ENABLED` | `false` | Enable periodic status reports |
| `STATUS_UPDATE_INTERVAL` | `3600` | Interval in seconds (min: 60) |
| `STATUS_UPDATE_ON_STARTUP` | `false` | Send status on startup |

## API Reference

### Public Endpoints (No Authentication)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Web dashboard |
| `/docs` | GET | Swagger UI documentation |
| `/health` | GET | Health check for load balancers |
| `/metrics` | GET | Application and system metrics |

### Protected Endpoints (Bearer Token Required)

Include header: `Authorization: Bearer YOUR_TOKEN`

#### Sensor Data

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/temp` | GET | Current temperature and humidity |
| `/api/raw` | GET | Raw sensor data for debugging |
| `/api/verify-token` | GET | Validate authentication token |

#### Webhook Management

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/webhook/config` | GET | Get current webhook configuration |
| `/api/webhook/config` | PUT | Update webhook config and thresholds |
| `/api/webhook/test` | POST | Send a test webhook message |
| `/api/webhook/enable` | POST | Enable webhook notifications |
| `/api/webhook/disable` | POST | Disable webhook notifications |

### Example Requests

```bash
# Get temperature data
curl -H "Authorization: Bearer YOUR_TOKEN" http://localhost:8080/api/temp

# Response:
{
  "temperature_c": 23.5,
  "temperature_f": 74.3,
  "humidity": 45.2,
  "timestamp": "2024-01-15 14:23:45"
}

# Health check (no auth needed)
curl http://localhost:8080/health

# Response:
{
  "status": "healthy",
  "uptime_seconds": 12345,
  "sensor_thread_alive": true,
  "timestamp": 1705329825.123
}

# Update webhook thresholds
curl -X PUT http://localhost:8080/api/webhook/config \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "thresholds": {
      "temp_min_c": 18.0,
      "temp_max_c": 25.0
    }
  }'
```

## Webhook Notifications

When configured with a Slack webhook URL, the system sends alerts when readings exceed thresholds.

### Alert Types

- **Temperature High**: Triggered when temp > `ALERT_TEMP_MAX_C`
- **Temperature Low**: Triggered when temp < `ALERT_TEMP_MIN_C`
- **Humidity High**: Triggered when humidity > `ALERT_HUMIDITY_MAX`
- **Humidity Low**: Triggered when humidity < `ALERT_HUMIDITY_MIN`

### Features

- **Alert Cooldown**: 5-minute cooldown between same alert type (prevents spam)
- **Exponential Backoff**: Retries with increasing delays on failure
- **URL Masking**: Webhook URLs are masked in API responses and logs for security

### Getting a Slack Webhook URL

1. Go to [Slack API](https://api.slack.com/messaging/webhooks)
2. Create a new app or use an existing one
3. Enable Incoming Webhooks
4. Create a webhook for your channel
5. Copy the URL to `SLACK_WEBHOOK_URL` in `.env`

## Deployment

### Docker (Recommended)

```bash
# Create logs directory and configure
mkdir -p logs
cp .env.example .env
# Edit .env with your settings

# Build and run
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

**Note**: Requires privileged mode for I2C/hardware access.

### Systemd Service

```bash
sudo cp deployment/systemd/temp-monitor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable temp-monitor.service
sudo systemctl start temp-monitor.service
```

### Production Configuration

- **Memory Limit**: 512MB (configurable)
- **Server**: Waitress WSGI, single worker/thread
- **Health Checks**: Every 30 seconds via `/health`
- **Auto-restart**: On failure with 10-second delay

For detailed production deployment, see [docs/PI4_DEPLOYMENT.md](docs/PI4_DEPLOYMENT.md).

## Temperature Compensation

The Sense HAT is affected by CPU heat. The system compensates using:

```
compensated_temp = raw_temp - ((cpu_temp - raw_temp) * factor)
```

The default factor is `0.7`. Adjust in `temp_monitor.py` if readings seem inaccurate.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Sense HAT not detected | Enable I2C via `sudo raspi-config`, check connection |
| Port 8080 blocked | Check firewall: `sudo ufw allow 8080` |
| Inaccurate temperature | Adjust compensation factor in code |
| Webhook failures | Check URL, network connectivity, view logs |
| API returns 401/403 | Verify Bearer token in request header |
| Service won't start | Check logs: `journalctl -u temp-monitor -f` |

## Dependencies

| Package | Version | Description |
|---------|---------|-------------|
| Flask | 2.3.3 | Web framework |
| Flask-RESTX | 1.3.0+ | REST API with Swagger |
| sense-hat | 2.6.0 | Sense HAT library |
| python-dotenv | 1.0.0 | Environment management |
| requests | 2.31.0 | HTTP client for webhooks |
| waitress | 2.1.2+ | Production WSGI server |
| psutil | 5.9.0+ | System metrics (optional) |

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

[MIT License](LICENSE)
