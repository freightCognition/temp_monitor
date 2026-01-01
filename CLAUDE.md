# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Server Room Temperature Monitor** - A lightweight environmental monitoring system running on a Raspberry Pi 4 with Sense HAT that provides:
- Real-time temperature and humidity monitoring with hardware compensation for CPU heat
- Web dashboard (auto-refreshes every 60 seconds)
- REST API with Bearer token authentication
- Slack webhook notifications for temperature/humidity alerts
- Periodic status updates
- LED matrix display showing current temperature

## Architecture Overview

### Core Layers

**Flask Application (temp_monitor.py)**
- Main entry point that initializes Flask app with Flask-RESTX for API documentation
- Manages sensor reading loop in a background thread (`update_sensor_data()`)
- Implements routes for web dashboard (`/`) and API endpoints (`/api/temp`, `/api/raw`, `/api/verify-token`)
- Bearer token authentication via `@require_token` decorator on protected endpoints

**Webhook Service (webhook_service.py)**
- `WebhookService` class: Handles outbound Slack webhook communication
- `WebhookConfig` dataclass: Configuration for webhook endpoint (URL, retry logic, timeout)
- `AlertThresholds` dataclass: Temperature/humidity thresholds that trigger alerts
- Features: Alert cooldown (5-min between same alert type), exponential backoff retry logic, thread-safe operations with locks
- Methods: `check_and_alert()` (threshold checking), `send_status_update()` (periodic reports), `send_slack_message()` (generic Slack formatting)

**API Models (api_models.py)**
- Flask-RESTX namespace (`webhooks_ns`) defining OpenAPI/Swagger models
- Input models with validation constraints (e.g., retry_count 1-10, timeout 5-120 seconds)
- Output models for responses
- Validation functions: `validate_webhook_config()` and `validate_thresholds()` (cross-field validation)

**Sensor Data Processing**
- `get_compensated_temperature()`: Takes 10 readings (5 from humidity + 5 from pressure sensors), filters outliers, applies CPU heat compensation (factor: 0.7) and -4°F correction
- `get_humidity()`: Takes 3 readings, filters outliers, applies +4% correction
- `get_cpu_temperature()`: Reads from `/sys/class/thermal/thermal_zone0/temp`

### API Endpoints Structure

**Public Routes:**
- `GET /` - Web dashboard (HTML)
- `GET /docs` - Swagger UI

**Protected Routes (require Bearer token):**
- `GET /api/temp` - Current temperature/humidity data
- `GET /api/raw` - Raw sensor readings for debugging
- `GET /api/verify-token` - Token validation check
- `GET /api/webhook/config` - Get webhook configuration
- `PUT /api/webhook/config` - Update webhook config and thresholds (with validation)
- `POST /api/webhook/test` - Send test webhook
- `POST /api/webhook/enable` - Enable webhooks
- `POST /api/webhook/disable` - Disable webhooks

### Configuration

Environment variables (from `.env`):
- `LOG_FILE` - Path to log file (default: `temp_monitor.log`)
- `BEARER_TOKEN` - Required for API access (generated with `python3 -c "import secrets; print(secrets.token_hex(32))"`)
- `SLACK_WEBHOOK_URL` - Slack webhook URL (enables webhook service)
- `WEBHOOK_ENABLED` - Enable/disable webhook notifications (default: true)
- `WEBHOOK_RETRY_COUNT` - Retry attempts (default: 3)
- `WEBHOOK_RETRY_DELAY` - Initial retry delay in seconds (default: 5)
- `WEBHOOK_TIMEOUT` - Request timeout (default: 10)
- `ALERT_TEMP_MIN_C`, `ALERT_TEMP_MAX_C`, `ALERT_HUMIDITY_MIN`, `ALERT_HUMIDITY_MAX` - Thresholds
- `STATUS_UPDATE_ENABLED` - Enable periodic status updates (default: false)
- `STATUS_UPDATE_INTERVAL` - Status update frequency in seconds (default: 3600)
- `STATUS_UPDATE_ON_STARTUP` - Send status update on startup (default: false)

## Key Design Patterns

**Thread Safety**
- Global state (`current_temp`, `current_humidity`) is read-only from thread perspective
- `WebhookService` uses `threading.Lock()` for concurrent access to alert tracking and config
- Background thread runs sensor loop with 60-second sampling interval

**Sensor Data Quality**
- Multiple readings with outlier filtering (removes min/max)
- CPU heat compensation formula to correct for SoC temperature affecting sensor
- Sensor readings are cached and accessed by multiple endpoints

**API Security**
- Bearer token required for all non-public endpoints
- Token format validation: `Authorization: Bearer <token>`
- 401 (missing header) vs 403 (invalid token) distinction
- Swagger UI accessible without auth for API documentation

**Webhook Reliability**
- Alert cooldown prevents spam (5 minutes between same alert type)
- Exponential backoff: delay = initial_delay × 2^(attempt_number)
- Configurable retry count (1-10) and timeout (5-120 seconds)
- Thread-safe alert tracking via locks

## Development Commands

### Running the Application

```bash
# Install dependencies
pip install -r requirements.txt

# Set up environment (copy example)
cp .env.example .env
# Edit .env to add BEARER_TOKEN and other settings

# Run directly (requires Sense HAT hardware or mock)
python temp_monitor.py

# Run with Docker Compose (includes ARM build support)
docker-compose build
docker-compose up -d
```

### Testing

```bash
# Run API endpoint tests
python test_webhook_api.py

# Run webhook service tests
python test_webhook.py

# Run periodic update tests
python test_periodic_updates.py
```

### Docker Deployment

```bash
# Build image
docker build -t temp-monitor .

# Run container with hardware access
docker run -d \
  --name temp-monitor \
  --privileged \
  -p 8080:8080 \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/.env:/app/.env \
  -v /sys:/sys:ro \
  --device /dev/i2c-1:/dev/i2c-1 \
  temp-monitor
```

### Systemd Service Setup

Create `/etc/systemd/system/temp_monitor.service`:
```ini
[Unit]
Description=Temperature Monitor Service
After=network.target

[Service]
User=yourusername
WorkingDirectory=/path/to/temp_monitor
ExecStart=/path/to/venv/bin/python3 temp_monitor.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then enable: `sudo systemctl enable temp_monitor.service && sudo systemctl start temp_monitor.service`

## Testing Strategy

Tests use `unittest.mock` to mock the `sense_hat` module (unavailable on non-RPi systems). Key test patterns:

```python
# Mock sense_hat before importing temp_monitor
sys.modules['sense_hat'] = MagicMock()
from temp_monitor import app, webhook_service

# Use test client with Bearer token
self.client.get('/api/temp', headers={'Authorization': f'Bearer {token}'})
```

Critical areas to test:
1. Webhook config creation when `webhook_service` is `None` (AttributeError bug fix)
2. Threshold validation (cross-field min/max relationships)
3. Alert cooldown preventing duplicate alerts
4. Exponential backoff retry logic

## Common Issues & Solutions

**Sense HAT Detection**
- Ensure I2C is enabled: `sudo raspi-config` → Interface Options → I2C
- Verify with: `i2cdetect -y 1`

**Temperature Calibration**
- Adjust `factor` in `get_compensated_temperature()` (line 191) based on actual readings
- CPU heat affects accuracy; hardware compensation attempts to correct this

**Webhook Failures**
- Check Slack webhook URL format: `https://hooks.slack.com/services/...`
- Verify network connectivity: `curl -X POST <webhook_url>`
- Monitor logs for retry attempts and final failures

**API Authentication**
- Generate token: `python3 -c "import secrets; print(secrets.token_hex(32))"`
- Always include `Authorization: Bearer <token>` header
- Bearer token is case-sensitive

## Dependencies

- **Flask 2.3.3** - Web framework
- **Flask-RESTX 1.3.0+** - REST API with OpenAPI/Swagger documentation
- **sense-hat 2.6.0** - Sense HAT hardware library
- **python-dotenv 1.0.0** - Environment variable management
- **requests 2.31.0** - HTTP client for webhooks

## File Structure

- `temp_monitor.py` - Main application (25KB, ~640 lines)
- `webhook_service.py` - Webhook/alert logic (~390 lines)
- `api_models.py` - Flask-RESTX models and validation (~170 lines)
- `sense_hat.py` - Mock/compatibility layer for Sense HAT
- `test_webhook_api.py` - Integration tests for API endpoints
- `test_webhook.py` - Unit tests for webhook service
- `test_periodic_updates.py` - Tests for periodic status updates
- `Dockerfile` - ARM-compatible build (Python 3.9)
- `docker-compose.yml` - Production-ready compose configuration
- `requirements.txt` - Python dependencies
- `.env.example` - Environment template
- `static/` - Web assets (favicon, logo)
