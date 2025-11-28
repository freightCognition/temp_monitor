# CLAUDE.md - AI Assistant Guide for Temperature Monitor Project

## Project Overview

This is a **Server Room Temperature Monitor** built on Raspberry Pi with Sense HAT hardware. It's a Flask-based web application that monitors environmental conditions (temperature and humidity) and provides both a web dashboard and secure REST API endpoints.

**Primary Purpose:** Real-time monitoring of server room environmental conditions with hardware sensor integration and remote access capabilities.

**Target Hardware:** Raspberry Pi Zero 2 W with Sense HAT add-on board

---

## Codebase Structure

```
temp_monitor/
├── temp_monitor.py           # Main Flask application (367 lines)
├── generate_token.py         # Token generation utility (56 lines)
├── requirements.txt          # Python dependencies
├── .env.example             # Example environment variables
├── .env                      # Environment variables (gitignored)
├── .gitignore               # Git ignore rules
├── README.md                 # User-facing documentation
├── CLAUDE.md                # AI assistant guide
├── static/                  # Web assets served by Flask
│   ├── My-img8bit-1com-Effect.gif  # Logo displayed on dashboard
│   └── favicon.ico          # Favicon for web interface
├── My-img8bit-1com-Effect.gif  # Legacy logo copy (not used by Flask static route)
└── temp-favicon.ico         # Legacy favicon copy (not used by Flask static route)
```

### Core Files

#### `temp_monitor.py` (Main Application)
- **Lines 1-14:** Imports and environment variable loading
- **Lines 16-34:** Logging configuration with directory validation
- **Lines 36-50:** Flask app setup and global variables
- **Lines 52-70:** Bearer token initialization from environment
- **Lines 72-90:** `require_token()` decorator for API authentication
- **Lines 92-107:** Image/asset loading with base64 encoding and favicon validation
- **Lines 109-117:** `get_cpu_temperature()` - reads from `/sys/class/thermal/thermal_zone0/temp`
- **Lines 119-149:** `get_compensated_temperature()` - temperature reading with CPU heat compensation
- **Lines 151-165:** `get_humidity()` - humidity sensor reading with averaging
- **Lines 167-192:** `update_sensor_data()` - background thread for continuous monitoring
- **Lines 194-280:** `index()` - web dashboard route with HTML template
- **Lines 282-289:** `favicon()` - favicon serving endpoint with fallback handling
- **Lines 291-301:** `api_temp()` - protected API endpoint for temperature data
- **Lines 303-315:** `api_raw()` - protected debugging endpoint for raw sensor data
- **Lines 317-345:** `generate_new_token()` - API endpoint to regenerate bearer tokens
- **Lines 347-355:** `verify_token()` - token validation endpoint
- **Lines 357-367:** Main execution block - starts sensor thread and Flask server

#### `generate_token.py` (Token Management)
- Standalone utility script to generate secure bearer tokens
- Uses `secrets.token_hex(32)` for cryptographically secure random tokens
- Manages `.env` file updates while preserving other environment variables
- Can be run independently or called via API

---

## Key Technical Concepts

### 1. Temperature Compensation Algorithm
**Location:** `temp_monitor.py:119-149`

The Sense HAT sensor is affected by CPU heat due to proximity on the board. Compensation formula:
```python
comp_temp = raw_temp - ((cpu_temp - raw_temp) * factor)
```
- **factor:** 0.7 (calibration constant, may need adjustment per hardware)
- **Averaging:** Takes 5 readings from both humidity and pressure sensors
- **Outlier removal:** Removes highest and lowest values before averaging
- **Graceful degradation:** Uses raw temperature if CPU temp unavailable

### 2. Sensor Data Collection
**Location:** `temp_monitor.py:167-192`

Background thread pattern:
- Runs continuously in daemon thread
- 60-second sampling interval (configurable via `sampling_interval`)
- Updates global variables: `current_temp`, `current_humidity`, `last_updated`
- Displays temperature on LED matrix via `sense.show_message()`
- Logs all readings to file with CPU temperature when available

### 3. Bearer Token Authentication
**Location:** `temp_monitor.py:52-90`

Security implementation:
- Uses decorator pattern (`@require_token`) to protect API endpoints
- Requires `Authorization: Bearer <token>` header
- Token stored in `.env` file and loaded via `python-dotenv`
- Auto-generates token if `.env` missing (shown on console)
- Returns 401 for missing auth, 403 for invalid token

### 4. Environment Variable Configuration
**Location:** `temp_monitor.py:16-34, 94, 105`

Configuration via environment variables:
- **LOG_FILE:** Path for temperature/humidity log file (defaults to `temp_monitor.log`)
- **Static assets:** Served from the `static/` directory bundled with the app; replace the files there to customize images.
- Supports both absolute and relative paths for log files
- Log directory is auto-created if it doesn't exist

### 5. Web Dashboard Auto-Refresh
**Location:** `temp_monitor.py:204` (meta refresh tag)

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
   - Copy `.env.example` to `.env` and customize as needed:
     ```bash
     cp .env.example .env
     ```
  - Generate bearer token: `python generate_token.py` (or manually set in `.env`)
  - Update environment variables in `.env`:
    - `LOG_FILE`: Path to log file
    - `BEARER_TOKEN`: API authentication token (auto-generated if omitted)
    - Static assets are located in `static/`; replace those files directly if you want custom branding

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

### Configuration via Environment Variables

**Path variables (configured in `.env`):**
- `LOG_FILE` - Log file path (defaults to `temp_monitor.log`)
- `BEARER_TOKEN` - API authentication token (auto-generated if missing)

**Static assets:**
- Served from the `static/` directory; replace `static/My-img8bit-1com-Effect.gif` or `static/favicon.ico` to customize branding.

**Hardcoded constants (code-level configuration):**
- `temp_monitor.py:50` - Sampling interval: 60 seconds
- `temp_monitor.py:143` - Temperature compensation factor: 0.7
- `temp_monitor.py:367` - Flask port: 8080

**File validation and safety:**
- Log directory is auto-created if missing (lines 20-25)
- All file operations wrapped in try-except blocks

---

## Common Tasks for AI Assistants

### Adding a New API Endpoint

1. Define route with `@app.route('/api/new-endpoint')`
2. Add `@require_token` decorator if authentication needed
3. Return JSON using `jsonify()`
4. Log access attempts
5. Update README with endpoint documentation

### Modifying Temperature Compensation

1. Edit `get_compensated_temperature()` function (line 119)
2. Adjust `factor` variable (currently 0.7, line 143)
3. Consider hardware-specific calibration
4. Test with physical hardware for accuracy
5. Update comments explaining calibration methodology

### Changing Sampling Interval

1. Modify `sampling_interval` global variable (line 50)
2. Update web dashboard meta refresh (line 204) to match
3. Consider LED display frequency impact
4. Update README documentation

### Adding Configuration Options

1. Add variable to global configuration (top of file)
2. Load from environment with `os.getenv('VARIABLE_NAME', default)`
3. Validate and document in `.env.example`
4. Update CLAUDE.md with configuration section
5. Ensure backwards compatibility with defaults

### Bug Fixes Related to Hardware

**Common issues:**
- **Missing CPU temp:** Gracefully handled (returns None), see line 116-117
- **Sense HAT not detected:** App fails at startup with clear error message (lines 37-42)
- **Outlier filtering:** Requires at least 3 readings, see line 132
- **Missing logo image:** Logs error but app continues, see lines 100-102
- **Missing favicon:** Logs warning at startup, returns 404 on request (lines 106-107, 286-289)

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

### Latest Changes (Current Sprint)

1. **Environment Variables Configuration** (6e1f06f)
   - Replaced hardcoded paths with environment variables for logs
   - Static assets now live in the `static/` directory instead of configurable paths
   - Supports both absolute and relative paths for log configuration

2. **Log File Path Validation** (43e866d)
   - Added automatic creation of log directory if missing
   - Proper error handling for directory creation failures
   - Clear error messages if logging cannot be initialized

3. **Static Asset Validation** (001e0a5)
   - Added existence check for favicon file at startup
   - Logs warning if favicon is missing
   - Gracefully handles missing favicon without crashing (returns 404)

4. **Security Enhancement** (0a6b4ff)
   - Updated `.env.example` with instructions not to hardcode BEARER_TOKEN
   - Token auto-generation is now the recommended approach

5. **Development Infrastructure** (05dcd8d)
   - Added Python cache files to `.gitignore`
   - Includes `__pycache__/`, `*.pyc`, `*.pyo`, `*.pyd`

### Evolution Pattern
- Started as simple temperature monitor
- Added API endpoints for programmatic access
- Enhanced security with bearer token authentication
- Ongoing refinement of error handling and edge cases
- Recent focus: Configuration management and file validation

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

1. **Database Integration:** Store historical data for trending analysis
2. **Alerting:** Email/SMS notifications for out-of-range conditions
3. **Graphing:** Historical charts in web dashboard
4. **Multi-sensor Support:** Monitor multiple rooms with multiple devices
5. **HTTPS Support:** SSL/TLS for secure remote access
6. **Docker Support:** Containerization for easier deployment
7. **Automated Testing:** Unit and integration test suite for critical functions
8. **Web Dashboard Auth:** Optional authentication for public deployments
9. **API Versioning:** `/api/v1/temp` for future compatibility
10. **Rate Limiting:** Implement rate limiting on API endpoints
11. **Token Expiration:** Add token expiration and rotation policies

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

*This document is maintained for AI assistants working with the Temperature Monitor codebase. Last updated: 2025-11-27*

### Documentation Updates in This Version
- Updated all line numbers to reflect current codebase structure
- Added Environment Variable Configuration section
- Documented recent changes including path configuration, file validation, and security improvements
- Clarified configuration approach (environment variables instead of hardcoded values)
- Added new subsection "Adding Configuration Options" for common tasks
- Enhanced troubleshooting section with file validation issues
