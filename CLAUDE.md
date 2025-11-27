# CLAUDE.md - AI Assistant Guide for Temperature Monitor Project

## Project Overview

This is a **Server Room Temperature Monitor** built on Raspberry Pi with Sense HAT hardware. It's a Flask-based web application that monitors environmental conditions (temperature and humidity) and provides both a web dashboard and secure REST API endpoints.

**Primary Purpose:** Real-time monitoring of server room environmental conditions with hardware sensor integration and remote access capabilities.

**Target Hardware:** Raspberry Pi Zero 2 W with Sense HAT add-on board

---

## Codebase Structure

```
temp_monitor/
├── temp_monitor.py           # Main Flask application (352 lines)
├── generate_token.py         # Token generation utility (56 lines)
├── requirements.txt          # Python dependencies
├── README.md                 # User-facing documentation
├── .env                      # Environment variables (gitignored)
├── .gitignore               # Git ignore rules
├── assets/                   # Web assets (images, favicons)
│   ├── temp-favicon.png
│   └── temp*.webp           # Various temperature-related images
├── My-img8bit-1com-Effect.gif  # Logo displayed on dashboard
└── temp-favicon.ico         # Favicon for web interface
```

### Core Files

#### `temp_monitor.py` (Main Application)
- **Lines 1-30:** Imports, initialization, logging configuration
- **Lines 31-37:** Flask app setup and global variables
- **Lines 39-58:** Bearer token initialization from environment
- **Lines 59-77:** `require_token()` decorator for API authentication
- **Lines 79-91:** Image/asset loading with base64 encoding
- **Lines 93-101:** `get_cpu_temperature()` - reads from `/sys/class/thermal/thermal_zone0/temp`
- **Lines 103-133:** `get_compensated_temperature()` - temperature reading with CPU heat compensation
- **Lines 135-149:** `get_humidity()` - humidity sensor reading with averaging
- **Lines 151-176:** `update_sensor_data()` - background thread for continuous monitoring
- **Lines 178-264:** `index()` - web dashboard route with HTML template
- **Lines 266-273:** `favicon()` - favicon serving endpoint
- **Lines 275-285:** `api_temp()` - protected API endpoint for temperature data
- **Lines 287-299:** `api_raw()` - protected debugging endpoint for raw sensor data
- **Lines 301-329:** `generate_new_token()` - API endpoint to regenerate bearer tokens
- **Lines 331-339:** `verify_token()` - token validation endpoint
- **Lines 341-351:** Main execution block - starts sensor thread and Flask server

#### `generate_token.py` (Token Management)
- Standalone utility script to generate secure bearer tokens
- Uses `secrets.token_hex(32)` for cryptographically secure random tokens
- Manages `.env` file updates while preserving other environment variables
- Can be run independently or called via API

---

## Key Technical Concepts

### 1. Temperature Compensation Algorithm
**Location:** `temp_monitor.py:103-133`

The Sense HAT sensor is affected by CPU heat due to proximity on the board. Compensation formula:
```python
comp_temp = raw_temp - ((cpu_temp - raw_temp) * factor)
```
- **factor:** 0.7 (calibration constant, may need adjustment per hardware)
- **Averaging:** Takes 5 readings from both humidity and pressure sensors
- **Outlier removal:** Removes highest and lowest values before averaging

### 2. Sensor Data Collection
**Location:** `temp_monitor.py:151-176`

Background thread pattern:
- Runs continuously in daemon thread
- 60-second sampling interval (configurable via `sampling_interval`)
- Updates global variables: `current_temp`, `current_humidity`, `last_updated`
- Displays temperature on LED matrix via `sense.show_message()`
- Logs all readings to file

### 3. Bearer Token Authentication
**Location:** `temp_monitor.py:59-77`

Security implementation:
- Uses decorator pattern (`@require_token`) to protect API endpoints
- Requires `Authorization: Bearer <token>` header
- Token stored in `.env` file and loaded via `python-dotenv`
- Auto-generates token if `.env` missing
- Returns 401 for missing auth, 403 for invalid token

### 4. Web Dashboard Auto-Refresh
**Location:** `temp_monitor.py:188` (meta refresh tag)

```html
<meta http-equiv="refresh" content="60">
```
- Client-side refresh every 60 seconds
- No JavaScript required
- Ensures users always see current data

---

## Development Workflows

### Local Development Setup

1. **Hardware Requirements:**
   - Must have Sense HAT hardware attached for full functionality
   - Without hardware, app will fail at initialization (line 25-29)

2. **Environment Setup:**
   ```bash
   # Install system dependencies (Raspberry Pi OS)
   sudo apt-get update
   sudo apt-get install -y python3-pip python3-sense-hat

   # Create virtual environment
   python3 -m venv venv
   source venv/bin/activate

   # Install Python dependencies
   pip install -r requirements.txt
   ```

3. **Configuration:**
   - Generate bearer token: `python generate_token.py`
   - Update hardcoded paths in `temp_monitor.py`:
     - Line 18: Log file path
     - Line 82: Logo image path
     - Line 91: Favicon path

4. **Running Locally:**
   ```bash
   python temp_monitor.py
   ```
   - Server runs on `0.0.0.0:8080`
   - Web dashboard: `http://localhost:8080`
   - API: `http://localhost:8080/api/temp` (requires auth header)

### Testing API Endpoints

```bash
# Get token from .env
TOKEN=$(grep BEARER_TOKEN .env | cut -d= -f2)

# Test temperature endpoint
curl -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/temp

# Test raw data endpoint (debugging)
curl -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/raw

# Verify token
curl -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/verify-token

# Generate new token
curl -X POST -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/generate-token
```

### Git Workflow

Based on recent commits:
- Feature branches follow pattern: `claude/claude-md-*` or user-specific prefixes
- Pull request workflow for all changes
- Commit message format: `<type>: <description>` (e.g., `feat: add bearer token authentication`)
- Recent PR topics: bug fixes, API schema, authentication features

**Current Branch:** `claude/claude-md-mih5ygkdlylf5q31-01SRHr3eBKXwcgtdd89ks7mj`

### Deployment as Systemd Service

The README documents systemd service setup:
- Service file: `/etc/systemd/system/temp_monitor.service`
- Runs as non-root user
- Auto-restart on failure (10 second delay)
- Starts after network is available

---

## Key Conventions & Patterns

### Code Style
- **Logging:** All significant events logged via `logging` module
- **Error Handling:** Try-except blocks with logging for hardware operations
- **Threading:** Daemon threads for background tasks
- **Global State:** Global variables for sensor data (thread-safe due to GIL)

### API Response Format
All API endpoints return JSON with consistent structure:

```json
{
  "temperature_c": 23.5,
  "temperature_f": 74.3,
  "humidity": 45.2,
  "timestamp": "2023-09-19 14:23:45"
}
```

### Security Practices
- Bearer tokens are 64-character hex strings (32 bytes)
- `.env` file is gitignored (never commit tokens)
- API endpoints are protected by default (use `@require_token`)
- Web dashboard (`/`) is public (no authentication)
- Favicon route is public

### Hardcoded Values to Be Aware Of

**User-specific paths that need updating:**
- `temp_monitor.py:18` - Log file: `/home/fakebizprez/temp_monitor.log`
- `temp_monitor.py:82` - Logo: `/home/fakebizprez/My-img8bit-1com-Effect.gif`
- `temp_monitor.py:91` - Favicon: `/home/fakebizprez/temp-favicon.ico`

**Configuration constants:**
- `temp_monitor.py:37` - Sampling interval: 60 seconds
- `temp_monitor.py:127` - Temperature compensation factor: 0.7
- `temp_monitor.py:351` - Flask port: 8080

---

## Common Tasks for AI Assistants

### Adding a New API Endpoint

1. Define route with `@app.route('/api/new-endpoint')`
2. Add `@require_token` decorator if authentication needed
3. Return JSON using `jsonify()`
4. Log access attempts
5. Update README with endpoint documentation

### Modifying Temperature Compensation

1. Edit `get_compensated_temperature()` function (line 103)
2. Adjust `factor` variable (currently 0.7)
3. Consider hardware-specific calibration
4. Test with physical hardware for accuracy
5. Update comments explaining calibration methodology

### Changing Sampling Interval

1. Modify `sampling_interval` global variable (line 37)
2. Update web dashboard meta refresh (line 188) to match
3. Consider LED display frequency impact
4. Update README documentation

### Bug Fixes Related to Hardware

**Common issues:**
- **Missing CPU temp:** Gracefully handled (returns None), see line 100-101
- **Sense HAT not detected:** App fails at startup with clear error message
- **Outlier filtering:** Requires at least 3 readings, see line 116

**Recent bug fix example:**
- Commit 909e636: "Handle missing CPU temperature gracefully"
- Shows pattern: add None checks, provide fallback behavior, log errors

---

## Dependencies & Requirements

### Python Dependencies (requirements.txt)
- `flask==2.3.3` - Web framework
- `sense-hat==2.6.0` - Sense HAT hardware interface
- `python-dotenv==1.0.0` - Environment variable management

### System Dependencies
- `python3-sense-hat` - System package for Sense HAT drivers
- Raspberry Pi OS (Raspbian) recommended
- I2C must be enabled for Sense HAT communication

### Hardware Dependencies
- Raspberry Pi (any model, Zero 2 W tested)
- Sense HAT add-on board (8x8 LED matrix, multiple sensors)
- Power supply adequate for Pi + Sense HAT

---

## Security Considerations

### Current Security Model
- **API endpoints:** Protected with bearer token authentication
- **Web dashboard:** Public access (no authentication required)
- **Token generation:** Requires existing valid token to generate new one
- **Token storage:** File-based (`.env`), not in database

### Potential Security Improvements for AI to Consider
- Add rate limiting to prevent brute force token attempts
- Implement token expiration/rotation policy
- Add HTTPS support (currently HTTP only)
- Consider adding authentication to web dashboard for public deployments
- Implement audit logging for security events

---

## Testing Strategy

### Manual Testing
1. **Hardware verification:** Check Sense HAT LED display shows temperature
2. **Web dashboard:** Access via browser, verify auto-refresh works
3. **API endpoints:** Test with curl commands (see Testing API Endpoints section)
4. **Error conditions:** Test without Sense HAT, with invalid tokens, etc.

### No Automated Tests Currently
- No test suite exists in repository
- Consider adding pytest-based tests for:
  - Temperature compensation calculations
  - Token validation logic
  - API endpoint responses
  - Error handling scenarios

---

## Troubleshooting Guide for AI Assistants

### Application Won't Start
- **Check:** Sense HAT hardware connection
- **Check:** I2C enabled via `sudo raspi-config`
- **Check:** Python dependencies installed
- **Check:** Correct Python version (3.7+)

### Inaccurate Temperature Readings
- **Adjust:** Compensation factor in `get_compensated_temperature()` (line 127)
- **Check:** CPU temperature sensor accessible
- **Consider:** Enclosure affecting airflow
- **Verify:** Sense HAT firmly seated on GPIO pins

### API Authentication Failures
- **Check:** `.env` file exists and contains BEARER_TOKEN
- **Verify:** Token format in Authorization header: `Bearer <token>`
- **Check:** Token matches exactly (case-sensitive)
- **Review:** Logs at `/home/fakebizprez/temp_monitor.log` for details

### Web Dashboard Not Updating
- **Check:** Background sensor thread is running
- **Verify:** No exceptions in logs
- **Check:** Browser cache (hard refresh with Ctrl+F5)
- **Test:** API endpoint directly to verify data is being collected

---

## Recent Changes & History

Based on git log analysis:

1. **Latest (b13c8e6):** README updates
2. **Bug fix (909e636):** Handle missing CPU temperature gracefully
3. **Feature (cc6cdc9):** Added bearer token authentication to API endpoints and token management tools
4. **Feature (694a83f):** API schema creation

### Evolution Pattern
- Started as simple temperature monitor
- Added API endpoints for programmatic access
- Enhanced security with bearer token authentication
- Ongoing refinement of error handling and edge cases

---

## Best Practices for AI Assistants

### When Making Changes

1. **Always read files before editing** - Never assume structure
2. **Update README.md** when adding features or changing APIs
3. **Add logging statements** for significant operations
4. **Handle hardware failures gracefully** - Sense HAT may not always be available
5. **Test with actual hardware** when possible
6. **Update this CLAUDE.md** when making architectural changes
7. **Follow existing code style** - spacing, naming conventions, etc.
8. **Consider deployment context** - This runs on Raspberry Pi, not cloud servers

### Code Review Checklist

- [ ] Hardware errors handled with try-except
- [ ] Logging added for new operations
- [ ] API endpoints have `@require_token` decorator (unless intentionally public)
- [ ] JSON responses use `jsonify()`
- [ ] Documentation updated (README.md, docstrings)
- [ ] Hardcoded paths reviewed (should use config/env vars)
- [ ] Thread safety considered for global variables
- [ ] Error messages are informative

### Don't Do These Things

- ❌ Remove hardware error handling (app must be resilient)
- ❌ Commit `.env` file (contains secrets)
- ❌ Make web dashboard require authentication without discussing (design decision)
- ❌ Change core temperature compensation without calibration data
- ❌ Add heavy dependencies (runs on resource-constrained Raspberry Pi Zero)
- ❌ Remove logging statements (critical for debugging headless deployments)
- ❌ Use blocking operations in sensor thread (would freeze monitoring)

---

## Future Enhancement Ideas

Areas where improvements could be made:

1. **Configuration Management:** Move hardcoded paths to config file or environment variables
2. **Database Integration:** Store historical data for trending analysis
3. **Alerting:** Email/SMS notifications for out-of-range conditions
4. **Graphing:** Historical charts in web dashboard
5. **Multi-sensor Support:** Monitor multiple rooms with multiple devices
6. **HTTPS Support:** SSL/TLS for secure remote access
7. **Docker Support:** Containerization for easier deployment
8. **Automated Testing:** Unit and integration test suite
9. **Web Dashboard Auth:** Optional authentication for public deployments
10. **API Versioning:** `/api/v1/temp` for future compatibility

---

## Quick Reference

### File Locations
- Main app: `temp_monitor.py`
- Token utility: `generate_token.py`
- Dependencies: `requirements.txt`
- Config: `.env` (not in git)
- Docs: `README.md`, `CLAUDE.md`

### Important Functions
- `get_compensated_temperature()` - Core temp reading logic
- `update_sensor_data()` - Background monitoring loop
- `require_token()` - Authentication decorator

### API Endpoints
- `GET /` - Web dashboard (public)
- `GET /api/temp` - Current readings (protected)
- `GET /api/raw` - Raw sensor data (protected)
- `GET /api/verify-token` - Token validation (protected)
- `POST /api/generate-token` - Generate new token (protected)

### Configuration
- Port: 8080
- Sampling: 60 seconds
- Compensation factor: 0.7
- Token length: 64 hex chars

---

*This document was generated for AI assistants working with the Temperature Monitor codebase. Last updated: 2025-11-27*
