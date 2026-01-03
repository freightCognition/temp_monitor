# Raspberry Pi 4 Production Deployment Guide

This guide covers optimized deployment of the Temperature Monitor application on Raspberry Pi 4 for production environments.

## Hardware Requirements

### Raspberry Pi 4 Specifications
- **CPU:** ARM Cortex-A72, 4 cores @ 1.5GHz
- **RAM:** 2GB, 4GB, or 8GB (2GB minimum recommended)
- **Storage:** microSD card 16GB+
- **Power:** 5V/3A USB-C power supply
- **OS:** Raspberry Pi OS Bullseye or later

### Sense HAT Requirements
- Raspberry Pi Sense HAT board
- I2C interface enabled
- GPIO pins accessible

## Baseline Memory Footprint

**To be measured during testing:**
- [ ] Idle application memory (Flask + sensor thread)
- [ ] Memory with active API requests
- [ ] Memory after 24-hour continuous operation
- [ ] Peak memory under load

**Expected baseline (before testing):**
- Flask app + sensor thread: ~50-80 MB
- With Waitress server: ~100-120 MB
- System + app total: ~250-300 MB

## Deployment Options

### Option 1: Docker Deployment (Recommended)

#### Prerequisites
```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker pi
```

#### Deployment
```bash
cd /path/to/temp_monitor
docker compose up -d
```

Optional: set `CLOUDFLARED_TOKEN` in `.env` before starting Docker Compose. In Cloudflare Zero Trust, configure the service as `http://temp-monitor:8080`.

#### Monitoring
```bash
# View logs
docker compose logs -f temp-monitor

# Check health
curl http://localhost:8080/health

# View metrics
curl http://localhost:8080/metrics
```

#### Stop Service
```bash
docker compose down
```

### Option 2: Systemd Service Deployment

#### Prerequisites
```bash
# Create log directory
sudo mkdir -p /var/log/temp-monitor
sudo chown pi:pi /var/log/temp-monitor

# Install dependencies
cd /path/to/temp_monitor
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### Installation
```bash
# Copy service file
sudo cp deployment/systemd/temp-monitor.service /etc/systemd/system/

# Enable service
sudo systemctl daemon-reload
sudo systemctl enable temp-monitor.service
sudo systemctl start temp-monitor.service

# Check status
If you are using Docker Compose, use `deployment/systemd/temp-monitor-compose.service` instead (update the `WorkingDirectory` and `User`).

# Check status
sudo systemctl status temp-monitor.service

# View logs
sudo journalctl -u temp-monitor.service -f
```

#### Useful Commands
```bash
# Start/stop service
sudo systemctl start temp-monitor.service
sudo systemctl stop temp-monitor.service
sudo systemctl restart temp-monitor.service

# View status
sudo systemctl status temp-monitor.service

# View recent logs
sudo journalctl -u temp-monitor.service -n 50

# Follow logs
sudo journalctl -u temp-monitor.service -f
```

### Option 3: Direct Python Deployment

For development and testing only.

```bash
# Setup
cd /path/to/temp_monitor
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run in development mode
python temp_monitor.py

# Or run production mode
./start_production.sh
```

## Configuration

### Environment Variables

Create or update `.env` file in the application directory:

```bash
# Logging
LOG_FILE=/var/log/temp-monitor/temp_monitor.log

# Cloudflare Tunnel (optional, Docker)
# Configure the tunnel in Cloudflare Zero Trust with service http://temp-monitor:8080
CLOUDFLARED_TOKEN=your-cloudflare-tunnel-token

# Webhook Configuration
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
WEBHOOK_ENABLED=true
WEBHOOK_RETRY_COUNT=3
WEBHOOK_RETRY_DELAY=5
WEBHOOK_TIMEOUT=10

# Alert Thresholds
ALERT_TEMP_MIN_C=15.0
ALERT_TEMP_MAX_C=27.0
ALERT_HUMIDITY_MIN=30.0
ALERT_HUMIDITY_MAX=70.0

# Periodic Status Updates (optional)
STATUS_UPDATE_ENABLED=false
STATUS_UPDATE_INTERVAL=3600

# API Security
BEARER_TOKEN=your-secure-token-here
```

### Docker Compose Configuration

The `docker-compose.yml` includes:
- Memory limits: 512MB (hard limit) / 256MB (reservation)
- CPU restrictions: No limit (uses available cores)
- Health checks: Every 30 seconds
- Automatic restart policy

### Systemd Service Configuration

The `deployment/systemd/temp-monitor.service` includes:
- Memory limits: 512MB
- Watchdog timeout: 60 seconds
- Restart policy: Always, with 10-second delays
- Security settings: ProtectSystem, NoNewPrivileges

## Monitoring and Health Checks

### Health Endpoint
```bash
curl http://localhost:8080/health
```

Response:
```json
{
  "status": "healthy",
  "uptime_seconds": 12345,
  "sensor_thread_alive": true,
  "timestamp": 1234567890.123
}
```

### Metrics Endpoint
```bash
curl http://localhost:8080/metrics
```

Response includes:
- Application metrics (request count, alerts sent, uptime)
- Hardware metrics (CPU temperature)
- System metrics (CPU %, memory usage, threads)

### Log Monitoring

#### Docker
```bash
docker compose logs -f temp-monitor
```

#### Systemd
```bash
sudo journalctl -u temp-monitor.service -f

# Filter by level
sudo journalctl -u temp-monitor.service -p err -f
```

#### File-based (if using LOG_FILE)
```bash
tail -f /var/log/temp-monitor/temp_monitor.log
```

## Performance Tuning

### Single-Process Configuration
The application is configured for single-process deployment:
- **Workers:** 1
- **Threads per worker:** 1
- **Connection limit:** 50 concurrent connections
- **Request timeout:** 120 seconds

This configuration is optimized for Pi 4's limited resources while maintaining reliability.

### Memory Management

#### Monitoring Memory Usage
```bash
# Check current memory
curl http://localhost:8080/metrics | python -m json.tool | grep -A 10 '"system"'

# Monitor over time
watch -n 5 'curl -s http://localhost:8080/metrics | python -m json.tool | grep memory'
```

#### Memory Limits
- **Container/Process limit:** 512MB
- **Alert threshold:** 400MB
- **Restart threshold:** 512MB (enforced by systemd/Docker)

#### Detecting Memory Leaks
Monitor the `/metrics` endpoint over a 24-hour period. If `memory_mb` shows continuous growth, investigate:
1. Check sensor thread logs for errors
2. Review webhook service for stuck connections
3. Check Flask request handling for unfinished requests

### I2C Performance
The application communicates with Sense HAT via I2C. Performance factors:
- I2C clock speed: 100kHz (standard)
- Sampling interval: 60 seconds (configurable)
- Temperature compensation: Calculated locally

## Troubleshooting

### Service Won't Start

**Check logs:**
```bash
# Docker
docker compose logs temp-monitor

# Systemd
sudo journalctl -u temp-monitor.service -n 50
```

**Common issues:**
1. Permission denied on `/dev/i2c-1`
   - Solution: `sudo usermod -a -G i2c pi` (then logout/login)
2. Port 8080 already in use
   - Solution: Change port in config or stop conflicting service
3. Sense HAT not detected
   - Solution: Check I2C enabled (`sudo raspi-config`) and Sense HAT connected

### High Memory Usage

**Investigation steps:**
1. Check current memory: `curl http://localhost:8080/metrics`
2. Look for memory leak pattern in metrics over time
3. Check logs for repeated errors
4. Monitor webhook service for hung connections

**Solutions:**
1. Restart service: `sudo systemctl restart temp-monitor.service`
2. Increase memory threshold in code
3. Check webhook URL is responding

### Health Check Failing

**Quick test:**
```bash
curl -v http://localhost:8080/health
```

**If returns 500:**
1. Check logs for errors
2. Verify sensor thread is running
3. Check available disk space for logs

### Webhook Delivery Issues

**Test webhook endpoint:**
```bash
curl -X POST http://localhost:8080/api/webhook/test \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://your-webhook-url", "enabled": true}'
```

**Check webhook configuration:**
```bash
curl http://localhost:8080/api/webhook/config \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## Backup and Recovery

### Backup Configuration
```bash
# Backup .env file
sudo cp /home/pi/temp_monitor/.env /home/pi/temp_monitor/.env.backup

# Backup logs
sudo tar -czf temp-monitor-logs-$(date +%Y%m%d).tar.gz /var/log/temp-monitor/
```

### Restore Configuration
```bash
sudo cp /home/pi/temp_monitor/.env.backup /home/pi/temp_monitor/.env
sudo systemctl restart temp-monitor.service
```

## Updates and Maintenance

### Update Application Code
```bash
cd /path/to/temp_monitor
git pull origin main
source venv/bin/activate
pip install -r requirements.txt

# Restart service
sudo systemctl restart temp-monitor.service
```

### Log Rotation (Systemd)

Logs are automatically managed by journald. View retention:
```bash
sudo journalctl --vacuum-time=30d  # Keep 30 days
```

### Log Rotation (File-based)

Create `/etc/logrotate.d/temp-monitor`:
```
/var/log/temp-monitor/*.log {
    daily
    rotate 7
    compress
    delaycompress
    notifempty
    create 0644 pi pi
    sharedscripts
}
```

## Performance Testing Results

**To be completed after deployment:**

| Metric | Target | Actual |
|--------|--------|--------|
| Idle memory | <150MB | --- |
| Peak memory | <400MB | --- |
| API response time | <100ms | --- |
| Sensor update latency | <1s | --- |
| Uptime without restart | 7 days | --- |

## Additional Resources

- [Raspberry Pi 4 Documentation](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html)
- [Sense HAT Documentation](https://github.com/RPi-Distro/Adafruit-Raspberry-Pi-Python-Code)
- [Waitress Documentation](https://docs.pylonsproject.org/projects/waitress/)
- [Flask Documentation](https://flask.palletsprojects.com/)
- [Docker for Raspberry Pi](https://docs.docker.com/engine/install/raspberry-pi-os/)

## Support

For issues or questions:
1. Check logs first: `sudo journalctl -u temp-monitor.service -f`
2. Review this guide's troubleshooting section
3. Check `/health` and `/metrics` endpoints
4. Review application logs at `LOG_FILE` location
