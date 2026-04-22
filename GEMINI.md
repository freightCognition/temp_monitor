# GEMINI.md - Instructional Context

This file serves as the foundational instructional context for Gemini CLI interactions within the **Server Room Temperature Monitor** project.

## Project Overview

**Server Room Temperature Monitor** is a Python-based environmental monitoring system designed for Raspberry Pi 4 with a Sense HAT add-on board. It provides real-time tracking of temperature and humidity, compensates for CPU heat to ensure accuracy, and offers multiple ways to access and receive data.

### Key Technologies
- **Language:** Python 3.9+
- **Web Framework:** Flask with Flask-RESTX (OpenAPI/Swagger documentation)
- **Hardware Interface:** `sense-hat` library (with a mock layer for non-RPi development)
- **Deployment:** Docker, Docker Compose, Waitress (WSGI), Systemd
- **Notifications:** Slack via Incoming Webhooks

### Architecture
- **`temp_monitor.py`**: The core application, handling the Flask server, background sensor reading loop, and data caching.
- **`webhook_service.py`**: A thread-safe service managing alert logic, threshold checking, and Slack communication with exponential backoff retries.
- **`api_models.py`**: Definitions for API request/response structures and validation logic using Flask-RESTX namespaces.
- **`sense_hat.py`**: A mock implementation of the Sense HAT library, enabling development and testing on standard hardware.

---

## Building and Running

### Prerequisites
- Python 3.9 or higher
- (Optional) Raspberry Pi 4 with Sense HAT
- (Optional) Docker and Docker Compose

### Local Development Setup
1. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
2. **Environment Configuration:**
   ```bash
   cp .env.example .env
   # Generate a mandatory bearer token:
   python3 -c "import secrets; print(secrets.token_hex(32))"
   # Add the token to .env: BEARER_TOKEN=<generated_token>
   ```
3. **Run the Application:**
   ```bash
   python temp_monitor.py
   ```
   The dashboard will be available at `http://localhost:8080` and API docs at `http://localhost:8080/docs`.

### Production Deployment
- **Waitress (WSGI):** Run `./start_production.sh`.
- **Docker Compose:** Run `docker compose up -d`.
- **Systemd:** Use the service files in `deployment/systemd/`.

---

## Testing

The project uses `unittest` and `unittest.mock` to simulate hardware environments.

- **API Integration Tests:** `python test_webhook_api.py`
- **Webhook Service Tests:** `python test_webhook.py`
- **Periodic Update Tests:** `python test_periodic_updates.py`
- **Model Validation Tests:** `python test_api_models.py`

---

## Development Conventions

### Coding Standards
- **Thread Safety:** Always use `threading.Lock()` when accessing or modifying shared state (like webhook configurations or alert counters) across the background sensor thread and the Flask request threads.
- **Sensor Calibration:** Temperature readings are compensated for CPU heat using a compensation factor (default `0.7`). Adjust this in `temp_monitor.py` if physical calibration is required.
- **API Design:** All new API endpoints should be registered within the appropriate Flask-RESTX namespace in `api_models.py` and include documentation decorators.

### Contribution Guidelines
- **Bearer Authentication:** All non-public API endpoints MUST use the `@require_token` decorator.
- **Hardware Mocking:** When adding new hardware features, update `sense_hat.py` to ensure the project remains runnable on non-Raspberry Pi systems.
- **Logging:** Use the configured logger (via `logging`) instead of `print()` statements for application tracking.
