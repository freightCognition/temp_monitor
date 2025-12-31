# Webhook Quick Start Guide

## 🚀 Get Started in 3 Minutes

### Step 1: Get Your Slack Webhook URL

1. Go to https://api.slack.com/messaging/webhooks
2. Create a new app and enable "Incoming Webhooks"
3. Add webhook to your desired channel
4. Copy the webhook URL

### Step 2: Configure

Add to `.env`:

```bash
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

### Step 3: Restart & Test

```bash
# Restart the app
python temp_monitor.py

# Test the webhook
TOKEN=$(grep BEARER_TOKEN .env | cut -d= -f2)
curl -X POST -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/webhook/test
```

You're done! 🎉

---

## 📊 What You Get

### Automatic Alerts

The system monitors your environment 24/7 and sends Slack alerts when:

- 🔥 **Temperature too high** (default: >27°C / 80.6°F)
- ❄️ **Temperature too low** (default: <15°C / 59°F)
- 💧 **Humidity too high** (default: >70%)
- 🏜️ **Humidity too low** (default: <30%)

### Smart Features

- ✅ **5-minute cooldown** prevents alert spam
- ✅ **Automatic retry** with exponential backoff (up to 3 attempts)
- ✅ **Thread-safe** for reliable operation
- ✅ **Color-coded** Slack messages for quick status recognition

---

## 🎯 Common Tasks

### Change Alert Thresholds

Add to `.env`:

```bash
ALERT_TEMP_MIN_C=18.0    # 64.4°F
ALERT_TEMP_MAX_C=24.0    # 75.2°F
ALERT_HUMIDITY_MIN=40.0
ALERT_HUMIDITY_MAX=60.0
```

### Enable Hourly Status Updates

Get regular status reports even when everything is normal:

```bash
# Add to .env
STATUS_UPDATE_ENABLED=true
STATUS_UPDATE_INTERVAL=3600  # Every hour

# Optional: Send update on startup
STATUS_UPDATE_ON_STARTUP=true
```

**Other useful intervals:**
- Every 30 min: `1800`
- Every 2 hours: `7200`
- Daily: `86400`

### Temporarily Disable Alerts

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  http://localhost:8080/api/webhook/disable
```

### Re-enable Alerts

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  http://localhost:8080/api/webhook/enable
```

### Check Current Configuration

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8080/api/webhook/config | jq
```

### Update Configuration Without Restart

```bash
curl -X PUT \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "thresholds": {
      "temp_max_c": 25.0,
      "humidity_max": 65.0
    }
  }' \
  http://localhost:8080/api/webhook/config
```

---

## 🔧 Troubleshooting

### Not receiving alerts?

1. Check webhook is enabled:
   ```bash
   curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8080/api/webhook/config | jq '.webhook.enabled'
   ```

2. Verify thresholds are configured:
   ```bash
   curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8080/api/webhook/config | jq '.thresholds'
   ```

3. Check current readings vs thresholds:
   ```bash
   curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8080/api/temp
   ```

4. Look at logs:
   ```bash
   tail -f temp_monitor.log | grep -i webhook
   ```

### Test webhook failing?

- Verify webhook URL is correct in `.env`
- Check Slack webhook is active in Slack settings
- Ensure you have network connectivity
- Check firewall isn't blocking outbound HTTPS

---

## 📚 Full Documentation

For complete details, see [WEBHOOKS.md](WEBHOOKS.md)

---

## 🔐 Security Notes

- Never commit `.env` file (already in `.gitignore`)
- Treat webhook URL like a password
- All webhook management requires bearer token authentication
- Use HTTPS in production (webhook URLs are HTTPS by default)

---

## 🎨 Example Slack Messages

### Temperature Alert
```
🔥 Temperature Alert: HIGH

Current Temperature: 28.5°C (83.3°F)
Threshold: 27.0°C (80.6°F)
Timestamp: 2025-12-30 14:23:45
```

### Status Update
```
📊 Server Room Status Update

Temperature: 22.3°C (72.1°F)
Humidity: 45.2%
CPU Temperature: 48.5°C
Last Updated: 2025-12-30 14:23:45
```

---

**Need help?** Check [WEBHOOKS.md](WEBHOOKS.md) for detailed documentation.
