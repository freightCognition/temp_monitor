# Webhook Integration Guide

## Overview

The Temperature Monitor includes robust webhook integration for sending real-time alerts and status updates to Slack. This feature monitors temperature and humidity thresholds and automatically sends notifications when readings are out of range.

## Features

- **Threshold-based alerts**: Automatic notifications when temperature or humidity exceeds configured limits
- **Slack integration**: Formatted messages with color-coded alerts
- **Retry logic**: Automatic retry with exponential backoff for failed deliveries
- **Rate limiting**: Built-in cooldown period (5 minutes) to prevent alert spam
- **API management**: Dynamic configuration via REST API endpoints
- **Thread-safe**: Safe concurrent access to webhook configuration

---

## Quick Start

### 1. Get a Slack Webhook URL

1. Go to https://api.slack.com/messaging/webhooks
2. Click "Create your Slack app"
3. Choose "From scratch" and name your app (e.g., "Temperature Monitor")
4. Select the workspace where you want to receive notifications
5. Under "Incoming Webhooks", toggle "Activate Incoming Webhooks" to **On**
6. Click "Add New Webhook to Workspace"
7. Choose the channel for notifications (e.g., #server-room-alerts)
8. Copy the webhook URL (format: `https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXX`)

### 2. Configure the Application

Add your webhook URL to `.env`:

```bash
# Slack webhook URL
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL

# Enable webhooks (optional, default: true)
WEBHOOK_ENABLED=true

# Alert thresholds (optional, defaults shown)
ALERT_TEMP_MIN_C=15.0   # 59°F
ALERT_TEMP_MAX_C=27.0   # 80.6°F
ALERT_HUMIDITY_MIN=30.0
ALERT_HUMIDITY_MAX=70.0
```

### 3. Restart the Application

```bash
# If running directly
python temp_monitor.py

# If running with Docker
docker-compose restart
```

### 4. Test the Integration

```bash
# Get your bearer token
TOKEN=$(grep BEARER_TOKEN .env | cut -d= -f2)

# Send a test message
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  http://localhost:8080/api/webhook/test
```

You should see a status update message in your Slack channel!

---

## Configuration

### Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `SLACK_WEBHOOK_URL` | Slack incoming webhook URL | None | Yes |
| `WEBHOOK_ENABLED` | Enable/disable webhooks | `true` | No |
| `WEBHOOK_RETRY_COUNT` | Number of retry attempts | `3` | No |
| `WEBHOOK_RETRY_DELAY` | Base retry delay in seconds | `5` | No |
| `WEBHOOK_TIMEOUT` | HTTP request timeout in seconds | `10` | No |
| `ALERT_TEMP_MIN_C` | Minimum temperature threshold (°C) | `15.0` | No |
| `ALERT_TEMP_MAX_C` | Maximum temperature threshold (°C) | `27.0` | No |
| `ALERT_HUMIDITY_MIN` | Minimum humidity threshold (%) | `30.0` | No |
| `ALERT_HUMIDITY_MAX` | Maximum humidity threshold (%) | `70.0` | No |

### Alert Thresholds

**Temperature Defaults:**
- Minimum: 15°C (59°F)
- Maximum: 27°C (80.6°F)

**Humidity Defaults:**
- Minimum: 30%
- Maximum: 70%

**Disabling Specific Alerts:**

To disable a specific threshold, set it to an empty value in `.env`:

```bash
# Disable low temperature alerts
ALERT_TEMP_MIN_C=

# Disable high humidity alerts
ALERT_HUMIDITY_MAX=
```

### Periodic Status Updates

In addition to threshold-based alerts, the monitor can send **scheduled periodic status updates** at regular intervals.

**Configuration:**

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `STATUS_UPDATE_ENABLED` | Enable periodic status updates | `false` | No |
| `STATUS_UPDATE_INTERVAL` | Interval in seconds | `3600` (1 hour) | No |
| `STATUS_UPDATE_ON_STARTUP` | Send update immediately on startup | `false` | No |

**Common Intervals:**
- Every 30 minutes: `1800`
- Every hour (recommended): `3600`
- Every 2 hours: `7200`
- Every 4 hours: `14400`
- Daily: `86400`

**Example Configuration:**

```bash
# Enable hourly status updates
STATUS_UPDATE_ENABLED=true
STATUS_UPDATE_INTERVAL=3600

# Optionally send update on startup
STATUS_UPDATE_ON_STARTUP=true
```

**How It Works:**
- Independent of threshold alerts (sends even when all readings are normal)
- Provides regular confirmation that monitoring is working
- Useful for creating a historical record in Slack
- Minimum interval is 60 seconds (the sensor sampling rate)
- If webhook delivery fails, update is skipped and rescheduled for next interval

**Benefits:**
- ✅ Confirms service is running and healthy
- ✅ Regular check-ins without manually opening dashboard
- ✅ Historical record if Slack messages are archived
- ✅ Combines with alerts for complete monitoring

---

## API Endpoints

All webhook endpoints require bearer token authentication via the `Authorization: Bearer <token>` header.

### GET /api/webhook/config

Get current webhook configuration.

**Example Request:**
```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8080/api/webhook/config
```

**Example Response:**
```json
{
  "webhook": {
    "url": "https://hooks.slack.com/services/...",
    "enabled": true,
    "retry_count": 3,
    "retry_delay": 5,
    "timeout": 10
  },
  "thresholds": {
    "temp_min_c": 15.0,
    "temp_max_c": 27.0,
    "humidity_min": 30.0,
    "humidity_max": 70.0
  }
}
```

### PUT /api/webhook/config

Update webhook configuration dynamically.

**Example Request:**
```bash
curl -X PUT \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "webhook": {
      "url": "https://hooks.slack.com/services/NEW/URL",
      "enabled": true,
      "retry_count": 5
    },
    "thresholds": {
      "temp_min_c": 18.0,
      "temp_max_c": 25.0,
      "humidity_min": 35.0,
      "humidity_max": 65.0
    }
  }' \
  http://localhost:8080/api/webhook/config
```

**Example Response:**
```json
{
  "message": "Webhook configuration updated successfully",
  "config": {
    "webhook": {
      "url": "https://hooks.slack.com/services/NEW/URL",
      "enabled": true
    },
    "thresholds": {
      "temp_min_c": 18.0,
      "temp_max_c": 25.0,
      "humidity_min": 35.0,
      "humidity_max": 65.0
    }
  }
}
```

### POST /api/webhook/test

Send a test webhook with current sensor readings.

**Example Request:**
```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  http://localhost:8080/api/webhook/test
```

**Example Response:**
```json
{
  "message": "Test webhook sent successfully",
  "timestamp": "2025-12-30 14:23:45"
}
```

### POST /api/webhook/enable

Enable webhook notifications.

**Example Request:**
```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  http://localhost:8080/api/webhook/enable
```

**Example Response:**
```json
{
  "message": "Webhook notifications enabled",
  "enabled": true
}
```

### POST /api/webhook/disable

Disable webhook notifications (without removing configuration).

**Example Request:**
```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  http://localhost:8080/api/webhook/disable
```

**Example Response:**
```json
{
  "message": "Webhook notifications disabled",
  "enabled": false
}
```

---

## Alert Types

### 🔥 Temperature High Alert

**Trigger:** Temperature exceeds `ALERT_TEMP_MAX_C`

**Message Format:**
- **Title:** "Temperature Alert: HIGH"
- **Color:** Red (danger)
- **Fields:** Current temperature, threshold, timestamp

**Example:**
```
🔥 Temperature Alert: HIGH
Current Temperature: 28.5°C (83.3°F)
Threshold: 27.0°C (80.6°F)
Timestamp: 2025-12-30 14:23:45
```

### ❄️ Temperature Low Alert

**Trigger:** Temperature falls below `ALERT_TEMP_MIN_C`

**Message Format:**
- **Title:** "Temperature Alert: LOW"
- **Color:** Orange (warning)
- **Fields:** Current temperature, threshold, timestamp

### 💧 Humidity High Alert

**Trigger:** Humidity exceeds `ALERT_HUMIDITY_MAX`

**Message Format:**
- **Title:** "Humidity Alert: HIGH"
- **Color:** Orange (warning)
- **Fields:** Current humidity, threshold, timestamp

### 🏜️ Humidity Low Alert

**Trigger:** Humidity falls below `ALERT_HUMIDITY_MIN`

**Message Format:**
- **Title:** "Humidity Alert: LOW"
- **Color:** Orange (warning)
- **Fields:** Current humidity, threshold, timestamp

### 📊 Status Update

**Trigger:** Manual test or periodic update (if configured)

**Message Format:**
- **Title:** "Server Room Status Update"
- **Color:** Green (good)
- **Fields:** Temperature, humidity, CPU temperature, timestamp

---

## Alert Cooldown

To prevent alert spam, the webhook service implements a **5-minute cooldown** per alert type. This means:

- Each alert type (temp_high, temp_low, humidity_high, humidity_low) is tracked independently
- After sending an alert, the same alert type won't be sent again for 5 minutes
- Different alert types can be sent simultaneously
- The cooldown timer resets when the alert condition clears and triggers again

**Example Timeline:**
```
14:00:00 - Temperature exceeds 27°C → Alert sent
14:02:00 - Temperature still at 28°C → No alert (cooldown)
14:04:59 - Temperature still at 28°C → No alert (cooldown)
14:05:00 - Temperature still at 28°C → Alert sent (cooldown expired)
```

---

## Retry Logic

The webhook service implements **exponential backoff** for failed deliveries:

1. **First attempt:** Immediate
2. **Second attempt:** 5 seconds later
3. **Third attempt:** 10 seconds later
4. **Failure:** Logged and abandoned

**Configuration:**
- `WEBHOOK_RETRY_COUNT`: Number of attempts (default: 3)
- `WEBHOOK_RETRY_DELAY`: Base delay in seconds (default: 5)
- Delay formula: `base_delay * (2 ^ attempt_number)`

**Example with defaults:**
- Attempt 1: 0 seconds
- Attempt 2: 5 seconds (5 * 2^0)
- Attempt 3: 10 seconds (5 * 2^1)

---

## Troubleshooting

### Webhook Not Sending

**Check configuration:**
```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8080/api/webhook/config
```

**Common issues:**
1. Missing `SLACK_WEBHOOK_URL` in `.env`
2. `WEBHOOK_ENABLED` set to `false`
3. Alert cooldown period active
4. Thresholds not configured correctly

**Check logs:**
```bash
tail -f temp_monitor.log | grep -i webhook
```

### Invalid Webhook URL

**Symptoms:**
- Test webhook returns 500 error
- Log shows "Webhook failed with status 404"

**Solution:**
1. Verify webhook URL is correct
2. Ensure URL starts with `https://hooks.slack.com/services/`
3. Regenerate webhook in Slack if necessary

### Alerts Not Triggering

**Check threshold configuration:**
```bash
# View current thresholds
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8080/api/webhook/config | jq '.thresholds'

# View current readings
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8080/api/temp
```

**Verify:**
- Current readings exceed thresholds
- Thresholds are not set to `null` (disabled)
- Webhook is enabled
- Not in cooldown period (check logs)

### Timeout Errors

**Symptoms:**
- Log shows "Webhook timeout"
- Slow network or Slack API issues

**Solution:**
```bash
# Increase timeout in .env
WEBHOOK_TIMEOUT=30

# Or via API
curl -X PUT \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"webhook": {"timeout": 30}}' \
  http://localhost:8080/api/webhook/config
```

---

## Security Considerations

### Webhook URL Protection

- **Never commit** `.env` file containing webhook URL to git (already in `.gitignore`)
- Webhook URL grants **write access** to your Slack channel
- Treat webhook URL like a password
- Rotate webhook URL if compromised (regenerate in Slack settings)

### API Authentication

- All webhook management endpoints require bearer token authentication
- Only authorized users with the token can modify webhook configuration
- Use HTTPS in production to prevent token interception

### Rate Limiting

- Built-in 5-minute cooldown prevents webhook spam
- Consider implementing additional rate limiting at network level for production
- Slack has rate limits (1 message per second per webhook URL)

---

## Advanced Usage

### Custom Alert Thresholds by Environment

**Development:**
```bash
# .env.development
ALERT_TEMP_MIN_C=10.0
ALERT_TEMP_MAX_C=35.0
ALERT_HUMIDITY_MIN=20.0
ALERT_HUMIDITY_MAX=80.0
```

**Production:**
```bash
# .env.production
ALERT_TEMP_MIN_C=18.0
ALERT_TEMP_MAX_C=24.0
ALERT_HUMIDITY_MIN=40.0
ALERT_HUMIDITY_MAX=60.0
```

### Dynamic Threshold Adjustment

Adjust thresholds during operation without restart:

```bash
# Lower max temperature for summer
curl -X PUT \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"thresholds": {"temp_max_c": 23.0}}' \
  http://localhost:8080/api/webhook/config

# Raise min humidity for winter
curl -X PUT \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"thresholds": {"humidity_min": 35.0}}' \
  http://localhost:8080/api/webhook/config
```

### Multiple Slack Channels

To send alerts to multiple channels, create multiple webhook URLs in Slack and use a simple script:

```bash
#!/bin/bash
# send_to_multiple.sh

WEBHOOKS=(
  "https://hooks.slack.com/services/CHANNEL1"
  "https://hooks.slack.com/services/CHANNEL2"
)

for webhook in "${WEBHOOKS[@]}"; do
  curl -X PUT \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"webhook\": {\"url\": \"$webhook\"}}" \
    http://localhost:8080/api/webhook/config

  curl -X POST \
    -H "Authorization: Bearer $TOKEN" \
    http://localhost:8080/api/webhook/test

  sleep 2
done
```

### Temporary Disable During Maintenance

```bash
# Disable alerts before maintenance
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  http://localhost:8080/api/webhook/disable

# Perform maintenance...

# Re-enable alerts after maintenance
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  http://localhost:8080/api/webhook/enable
```

---

## Slack Message Examples

### Temperature High Alert
![Temperature High Alert](https://via.placeholder.com/400x150/dc3545/ffffff?text=Temperature+Alert:+HIGH)

```
🔥 Temperature Alert: HIGH

Current Temperature: 28.5°C (83.3°F)
Threshold: 27.0°C (80.6°F)
Timestamp: 2025-12-30 14:23:45
```

### Status Update
![Status Update](https://via.placeholder.com/400x150/28a745/ffffff?text=Server+Room+Status+Update)

```
📊 Server Room Status Update

Temperature: 22.3°C (72.1°F)
Humidity: 45.2%
CPU Temperature: 48.5°C
Last Updated: 2025-12-30 14:23:45
```

---

## Code Integration Example

If you want to send custom webhooks from your own code:

```python
from webhook_service import WebhookService, WebhookConfig

# Initialize webhook service
config = WebhookConfig(
    url="https://hooks.slack.com/services/YOUR/WEBHOOK/URL",
    enabled=True
)
webhook = WebhookService(webhook_config=config)

# Send custom message
webhook.send_slack_message(
    text="🎉 Custom Event",
    color="good",
    fields=[
        {"title": "Event Type", "value": "Deployment", "short": True},
        {"title": "Status", "value": "Success", "short": True}
    ]
)

# Send system event
webhook.send_system_event(
    event_type="startup",
    message="Temperature monitoring service started",
    severity="info"
)
```

---

## Monitoring and Logging

All webhook activity is logged to the configured log file:

```bash
# View webhook-related logs
tail -f temp_monitor.log | grep -i webhook

# Example log entries
2025-12-30 14:23:45 - INFO - Webhook service initialized
2025-12-30 14:25:10 - INFO - Webhook sent successfully to https://hooks.slack.com/services/...
2025-12-30 14:30:22 - INFO - Webhook alerts sent: ['temp_high']
2025-12-30 14:35:45 - WARNING - Webhook failed with status 429: rate_limited
2025-12-30 14:40:12 - ERROR - Webhook timeout (attempt 1/3)
```

---

## Future Enhancements

Potential improvements for future versions:

- [ ] Support for multiple webhook endpoints simultaneously
- [ ] Configurable alert cooldown period per alert type
- [ ] Scheduled periodic status updates (daily/weekly)
- [ ] Custom message templates
- [ ] Integration with other platforms (Discord, Teams, email)
- [ ] Alert acknowledgment and auto-disable
- [ ] Webhook delivery statistics and metrics
- [ ] Grafana/Prometheus integration for monitoring

---

## Support

For issues or questions:

1. Check the troubleshooting section above
2. Review logs for error messages
3. Test configuration with `/api/webhook/test`
4. Verify Slack webhook URL is valid
5. Open an issue on GitHub: https://github.com/freightCognition/temp_monitor/issues

---

**Last Updated:** 2025-12-30
**Version:** 1.0.0
**Feature Added:** Webhook integration for Slack alerts
