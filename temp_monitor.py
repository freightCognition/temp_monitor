from flask import Flask, jsonify, render_template, request, abort
from flask_restx import Api, Resource
import time
import logging
import threading
import statistics
import os
import functools
import hmac
import inspect
import signal
from urllib.parse import urlparse
from dotenv import load_dotenv
from webhook_service import WebhookService, WebhookConfig, AlertThresholds
from api_models import (
    webhooks_ns, webhook_config_update, webhook_config_response,
    error_response, success_response, message_response, test_response,
    validate_thresholds, validate_webhook_config
)

try:
    import psutil
except ImportError:
    psutil = None

# Load environment variables from .env file
load_dotenv()


# --- Environment variable parsing --------------------------------------------
#
# Every env var in this module is read through one of these two helpers so
# that a malformed value fails with a message naming the variable, instead of
# either killing the WSGI worker with a bare traceback or -- worse -- being
# silently coerced to a wrong-but-plausible default.

def _parse_env_number(var_name, default, cast):
    """Parse a numeric environment variable, raising a clear RuntimeError
    instead of letting a bare ValueError/TypeError propagate out of module
    import (C4). An uncaught exception here kills the WSGI worker with a
    traceback that doesn't say which variable was at fault; this makes the
    failure diagnosable from the error message alone.

    Args:
        var_name: Name of the environment variable to read.
        default: Fallback string used when the variable is unset.
        cast: int or float -- the type to convert the raw value to.

    Returns:
        The parsed value (documented defaults apply when the var is unset).
    """
    raw = os.getenv(var_name, default)
    try:
        return cast(raw)
    except (TypeError, ValueError):
        raise RuntimeError(
            f"Invalid value for environment variable {var_name}={raw!r}: "
            f"expected a valid {cast.__name__}"
        )


_TRUTHY = ('1', 'true', 'yes', 'on')
_FALSY = ('0', 'false', 'no', 'off', '')


def _parse_env_bool(var_name, default=False):
    """Parse a boolean environment variable.

    These flags were previously parsed ad hoc, and inconsistently:
    USE_MOCK_SENSOR accepted 1/true/yes while WEBHOOK_ENABLED and the
    STATUS_UPDATE_* flags compared against the literal string 'true'. An
    operator who wrote WEBHOOK_ENABLED=yes by analogy therefore silently
    disabled webhooks. One helper means one accepted vocabulary, and an
    unrecognized value is an error rather than a silent false.

    Args:
        var_name: Name of the environment variable to read.
        default: Value used when the variable is unset or empty.

    Returns:
        bool
    """
    raw = os.getenv(var_name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized == '':
        return default
    if normalized in _TRUTHY:
        return True
    if normalized in _FALSY:
        return False
    raise RuntimeError(
        f"Invalid value for environment variable {var_name}={raw!r}: "
        f"expected one of {_TRUTHY + _FALSY[:-1]}"
    )


# Sensor driver selection.
#
# IMPORTANT: this repo previously shipped a stub named sense_hat.py in the
# repo root. Because the script directory is sys.path[0], that stub silently
# shadowed the real `sense-hat` PyPI package on every run, so production
# reported a frozen, fabricated 25.0C / 40.0% forever. The stub now lives
# under mock_sense_hat.py -- a name that cannot collide with the real
# package -- and is only loaded when USE_MOCK_SENSOR is explicitly set.
USE_MOCK_SENSOR = _parse_env_bool('USE_MOCK_SENSOR', False)
if USE_MOCK_SENSOR:
    from mock_sense_hat import SenseHat
else:
    from sense_hat import SenseHat

# Configure logging
log_file = os.getenv('LOG_FILE', 'temp_monitor.log')

# Validate and prepare log file path
log_dir = os.path.dirname(log_file)
if log_dir:  # Only validate if directory is specified (not relative path in current dir)
    try:
        os.makedirs(log_dir, exist_ok=True)
    except Exception as e:
        raise RuntimeError(f"Failed to create log directory '{log_dir}': {e}")

try:
    # S11: a plain FileHandler grows without bound. A persistent sensor
    # failure retries every 5s forever (~17,000 lines/day) on a Pi SD
    # card. RotatingFileHandler caps total log size on disk.
    from logging.handlers import RotatingFileHandler
    _log_handler = RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=5
    )
    _log_handler.setFormatter(
        logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    )
    _root_logger = logging.getLogger()
    _root_logger.setLevel(logging.INFO)
    _root_logger.addHandler(_log_handler)
except Exception as e:
    raise RuntimeError(f"Failed to configure logging with file '{log_file}': {e}")

# Initialize SenseHat
try:
    sense = SenseHat()
    sense.clear()  # Clear the LED matrix
    driver_kind = "MOCK" if USE_MOCK_SENSOR else "REAL"
    try:
        driver_path = inspect.getfile(SenseHat)
    except (TypeError, OSError):
        driver_path = "<unknown>"
    logging.info(f"Sensor driver loaded: {driver_kind} SenseHat from {driver_path}")
    if USE_MOCK_SENSOR:
        logging.warning(
            "USE_MOCK_SENSOR is set -- sensor readings are FABRICATED, not from hardware."
        )
except Exception as e:
    logging.error(f"Failed to initialize Sense HAT: {e}")
    raise

app = Flask(__name__)

# Global variables to store sensor data
current_temp = 0
current_humidity = 0
current_temp_compensated = True  # False when CPU-heat compensation could not be applied (S3)
last_updated = "Never"
last_updated_ts = None  # monotonic-ish timestamp (time.time()) of the last successful reading, for staleness checks (S6)
sampling_interval = 60  # seconds between temperature updates
# /health is unhealthy if the last reading is older than this many sampling intervals (S6)
staleness_threshold_seconds = sampling_interval * 3

@app.route('/')
def index():
    """Web interface showing temperature and humidity"""
    
    fahrenheit = round((current_temp * 9/5) + 32, 1)
    return render_template(
        'index.html', 
        temperature=current_temp, 
        fahrenheit=fahrenheit,
        humidity=current_humidity, 
        last_updated=last_updated
    )

class _DashboardSafeApi(Api):
    """flask_restx.Api._register_doc *unconditionally* registers a 'root'
    rule for '/' that 404s (render_root aborts 404) -- it is not guarded by
    add_specs/doc settings, and Api.prefix can't be used to relocate it
    without also relocating every namespace's URLs (register_resource
    prepends self.prefix to every resource route too, not just root).

    Left alone, that root rule collides with our own @app.route('/')
    dashboard (S12): it only worked because @app.route('/') ran first and
    werkzeug's rule sort is stable for identical static rules -- moving
    Api(...) above the route silently 404s the whole dashboard. Git
    history (commit 7f71fe0, "Fix waitress startup and root route
    shadowing") shows this ordering hazard was already hit once.

    We don't need RESTX's own root view -- '/' is our dashboard -- so skip
    only that one registration. This makes correctness structural (the
    collision can never be created) instead of order-dependent.
    """

    def _register_doc(self, app_or_blueprint):
        if self._add_specs and self._doc:
            app_or_blueprint.add_url_rule(self._doc, "doc", self.render_doc)
        # Deliberately NOT calling the parent's
        # app_or_blueprint.add_url_rule(self.prefix or "/", "root", ...) --
        # see class docstring.


# Initialize Flask-RESTX API with Swagger documentation
api = _DashboardSafeApi(
    app,
    version='1.0',
    title='Temperature Monitor API',
    description='Server room environmental monitoring API with webhook notifications',
    doc='/docs',
    authorizations={
        'bearer': {
            'type': 'apiKey',
            'in': 'header',
            'name': 'Authorization',
            'description': 'Bearer token authentication. Format: "Bearer <token>"'
        }
    }
    # Note: security='bearer' removed to allow public Swagger UI access at /docs
    # Individual endpoints are protected via @webhooks_ns.doc(security='bearer') decorators
)

# Register the webhooks namespace
api.add_namespace(webhooks_ns, path='/api/webhook')

# Metrics tracking for production deployment
app_start_time = time.time()
request_counter = 0
webhook_alert_counter = 0
counters_lock = threading.Lock()
sensor_thread = None  # Will be initialized when started


# Periodic status update configuration
status_update_enabled = _parse_env_bool('STATUS_UPDATE_ENABLED', False)
status_update_interval = _parse_env_number('STATUS_UPDATE_INTERVAL', '3600', int)
last_status_update = None  # Track time of last status update

# Validate status update interval (must be >= sampling_interval)
if status_update_enabled and status_update_interval < sampling_interval:
    logging.warning(
        f"STATUS_UPDATE_INTERVAL ({status_update_interval}s) is less than "
        f"sampling_interval ({sampling_interval}s). Using sampling_interval as minimum."
    )
    status_update_interval = sampling_interval

# Alert cooldown is read unconditionally (C8): it must be available even when
# no webhook service exists yet at import time, so that a service created
# later via PUT /api/webhook/config (see WebhookConfigResource.put) can still
# honor the operator's configured cooldown instead of silently falling back
# to WebhookService's hardcoded 900s default.
alert_cooldown_seconds = _parse_env_number('ALERT_COOLDOWN_SECONDS', '900', int)

# --- Temperature calibration -------------------------------------------------
#
# get_compensated_temperature() estimates ambient temperature from a sensor
# that is physically heated by the SoC underneath it:
#
#     comp_c = raw_c - (cpu_c - raw_c) * TEMP_CPU_FACTOR + TEMP_OFFSET_F(as C)
#
# Both parameters are empirical and MUST be calibrated against a trusted
# reference thermometer in the room where the unit actually runs. They were
# previously hardcoded, which mattered because until the mock-sensor shadowing
# bug was fixed (see the USE_MOCK_SENSOR note at the top of this file) the
# process was reading a stub that returned a constant 25.0C -- so these
# constants had never been validated against real hardware at all.
#
# TEMP_OFFSET_F default (-13.5F): the previous -4.0F default was measured to
# read +9.5F hot against the operator's reference thermometer on real
# hardware, so the default is -4.0 - 9.5 = -13.5. This is a SINGLE-POINT
# calibration: it is exact only near the CPU temperature at which it was
# measured. TEMP_CPU_FACTOR is what corrects for varying CPU load, and
# solving for it properly needs paired (raw, cpu, reference) samples taken at
# two different CPU temperatures -- see /api/raw, which reports raw_temperature
# and cpu_temperature alongside the active calibration for exactly this.
temp_cpu_factor = _parse_env_number('TEMP_CPU_FACTOR', '0.7', float)
temp_offset_f = _parse_env_number('TEMP_OFFSET_F', '-13.5', float)
humidity_offset = _parse_env_number('HUMIDITY_OFFSET', '4.0', float)

logging.info(
    f"Temperature calibration active: cpu_factor={temp_cpu_factor}, "
    f"offset={temp_offset_f}F, humidity_offset={humidity_offset}%"
)

# Initialize webhook service
webhook_service = None
slack_webhook_url = os.getenv('SLACK_WEBHOOK_URL')
if slack_webhook_url:
    webhook_config = WebhookConfig(
        url=slack_webhook_url,
        enabled=_parse_env_bool('WEBHOOK_ENABLED', True),
        retry_count=_parse_env_number('WEBHOOK_RETRY_COUNT', '3', int),
        retry_delay=_parse_env_number('WEBHOOK_RETRY_DELAY', '5', int),
        timeout=_parse_env_number('WEBHOOK_TIMEOUT', '10', int)
    )

    # C4: defaults documented in README (15.0/32.0/20.0/70.0) must apply
    # whenever the corresponding var is unset -- the previous `if
    # os.getenv(...)  else None` guard made the getenv() default dead code,
    # so an operator setting only one ALERT_* var silently lost alerting on
    # every other threshold.
    alert_thresholds = AlertThresholds(
        temp_min_c=_parse_env_number('ALERT_TEMP_MIN_C', '15.0', float),
        temp_max_c=_parse_env_number('ALERT_TEMP_MAX_C', '32.0', float),
        humidity_min=_parse_env_number('ALERT_HUMIDITY_MIN', '20.0', float),
        humidity_max=_parse_env_number('ALERT_HUMIDITY_MAX', '70.0', float)
    )

    webhook_service = WebhookService(
        webhook_config,
        alert_thresholds,
        alert_cooldown=alert_cooldown_seconds
    )
    logging.info("Webhook service initialized")
else:
    logging.info("Webhook service not configured (no SLACK_WEBHOOK_URL)")

# Initialize status update timer
if status_update_enabled and webhook_service:
    if _parse_env_bool('STATUS_UPDATE_ON_STARTUP', False):
        last_status_update = None  # Will trigger immediately on first loop
        logging.info("Periodic status updates enabled (will send on startup)")
    else:
        last_status_update = time.time()  # Start timer from now
        logging.info(f"Periodic status updates enabled (interval: {status_update_interval}s)")
elif status_update_enabled and not webhook_service:
    # C6: a webhook service created LATER via the API (WebhookConfigResource.put)
    # must still start its interval timer as if STATUS_UPDATE_ON_STARTUP were
    # false -- otherwise last_status_update stays None and the very next loop
    # iteration fires a status update immediately, regardless of the flag.
    # The actual timer start happens where the service is created (see C6
    # comment in WebhookConfigResource.put); this branch just explains why
    # last_status_update is deliberately left as None here.
    logging.warning(
        "STATUS_UPDATE_ENABLED is true but webhook service not configured; "
        "the update timer will start when a webhook service is later created"
    )

def generate_error_id():
    """Generate a correlation ID for error tracking in logs and responses"""
    timestamp = int(time.time() * 1000)
    import random
    suffix = format(random.randint(0, 65535), '04x')
    return f"{timestamp}_{suffix}"


# Get bearer token from environment (required)
BEARER_TOKEN = os.getenv('BEARER_TOKEN')
if not BEARER_TOKEN:
    logging.critical("BEARER_TOKEN not set in environment. Exiting.")
    print("ERROR: BEARER_TOKEN environment variable is required.")
    print("Generate a token with: python3 -c \"import secrets; print(secrets.token_hex(32))\"")
    print("Then add it to your .env file: BEARER_TOKEN=<your_token>")
    import sys
    sys.exit(1)
else:
    logging.info("Bearer token loaded from environment")

def mask_webhook_url(url):
    """
    Mask webhook URL by returning only scheme and host for security.

    This prevents sensitive path components and tokens from being exposed
    in API responses and logs, while still showing which service is configured.

    Args:
        url: Full webhook URL or None

    Returns:
        Masked URL in format 'scheme://host' or None if input is None/empty
    """
    if not url:
        return None

    try:
        parsed = urlparse(url)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
        else:
            # Malformed URL - return generic placeholder
            return "<invalid-url>"
    except Exception as e:
        logging.warning(f"Error masking webhook URL: {e}")
        return "<invalid-url>"

def require_token(f):
    """Decorator to require bearer token authentication for API endpoints.

    Uses flask.abort() (raises an HTTPException) rather than returning a
    Response directly: this decorator wraps both plain @app.route() view
    functions AND Flask-RESTX Resource methods, and RESTX's own decorators
    (marshal_with, response, etc.) sit *outside* this one. Returning a
    Response object short-circuits the return value but flask_restx's
    marshal_with does not recognize a plain Response and instead tries to
    marshal it against the success model -- silently turning a blocked
    request into a 200 with a null-filled body (an auth bypass). Raising
    instead propagates the exception through those decorators untouched,
    which is also what the un-authenticated-JSON error handler below
    depends on.
    """
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')

        # Check if Authorization header exists and has the correct format
        if not auth_header or not auth_header.startswith('Bearer '):
            logging.warning(f"API access attempt without valid Authorization header from {request.remote_addr}")
            abort(401, description="Authorization header with Bearer token required")

        # Extract and validate the token. Must be EXACTLY "Bearer <token>" --
        # split(' ')[1] used to silently accept trailing garbage like
        # "Bearer <token> junkjunk" because it only ever looked at the
        # second field (S8b).
        parts = auth_header.split(' ')
        token = parts[1] if len(parts) == 2 and parts[1] else None

        # Constant-time comparison (S8a): a plain != short-circuits on the
        # first differing byte, and /api/verify-token is a free oracle to
        # exploit that against.
        if not token or not hmac.compare_digest(token, BEARER_TOKEN):
            logging.warning(f"API access attempt with invalid token from {request.remote_addr}")
            # 401, not 403 (S8c): clients that retry on 401 need to see it.
            abort(401, description="Invalid bearer token")

        return f(*args, **kwargs)
    return decorated_function


@app.errorhandler(401)
def handle_unauthorized(error):
    """S8d: plain-Flask routes rendered the default Werkzeug HTML error
    page for aborts, while RESTX routes already returned JSON -- give JSON
    clients a parseable body everywhere, with the WWW-Authenticate header
    S8c needs so retry-on-401 clients behave correctly."""
    description = getattr(error, 'description', None) or 'Unauthorized'
    response = jsonify({'error': description})
    response.status_code = 401
    response.headers['WWW-Authenticate'] = 'Bearer'
    return response


@app.after_request
def ensure_www_authenticate(response):
    """RFC 7235 requires every 401 to carry a WWW-Authenticate challenge.

    The errorhandler above only fires for plain-Flask routes: Flask-RESTX
    installs its own error handling for aborts raised inside a Resource, so
    RESTX endpoints (all of /api/webhook/*) returned a 401 with no challenge
    header at all. Setting it here covers every route -- plain, RESTX, and
    any added later -- rather than relying on each handler to remember.
    """
    if response.status_code == 401:
        response.headers.setdefault('WWW-Authenticate', 'Bearer')
    return response

def get_cpu_temperature():
    """Get the temperature of the CPU for compensation"""
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            temp = float(f.read()) / 1000.0
        return temp
    except Exception as e:
        logging.error(f"Failed to get CPU temperature: {e}")
        return None

def get_compensated_temperature():
    """Get temperature from the Sense HAT with CPU compensation.

    Returns:
        float: temperature in Celsius (unchanged signature -- other test
        files mock this function with a plain return_value=<float>).

    Side effect:
        Updates the module-level `current_temp_compensated` flag to reflect
        whether CPU-heat compensation was actually applied for this
        reading. It is False when CPU temperature could not be read, in
        which case the raw ambient reading is returned as a best-effort
        value WITHOUT the CPU-heat compensation term applied. Callers that
        care must read that flag rather than treating the value as a
        normal compensated reading (see S3: a failed CPU read used to
        silently produce a ~14C step with no signal anywhere).
    """
    global current_temp_compensated

    # Get CPU temperature
    cpu_temp = get_cpu_temperature()

    # Get raw temperatures from Sense HAT
    raw_temps = []
    for _ in range(5):  # Take multiple readings
        raw_temps.append(sense.get_temperature_from_humidity())
        raw_temps.append(sense.get_temperature_from_pressure())
        time.sleep(0.1)

    # Remove outliers and calculate the average raw temperature
    # KNOWN DEFECT (S5): this pools humidity-sensor and pressure-sensor
    # readings into one list before sorting/trimming. On real hardware the
    # pressure sensor reads systematically hotter, so the list is bimodal
    # and this trims one member of *each* cluster instead of rejecting
    # either sensor's outliers -- the mean ends up a blend of two
    # differently-calibrated sources. Left as-is deliberately (see
    # test_sensor_math.py test_KNOWN_DEFECT_bimodal_sensor_blend_...);
    # fixing it changes reported temperatures and needs to be called out
    # to the user, who is actively calibrating against a real thermostat.
    if len(raw_temps) > 2:  # Need at least 3 readings to filter outliers
        raw_temps.sort()
        # Remove highest and lowest reading
        filtered_temps = raw_temps[1:-1]
        raw_temp = statistics.mean(filtered_temps)
    else:
        raw_temp = statistics.mean(raw_temps)

    # Apply compensation formula based on calibration
    # This formula assumes the CPU is significantly warmer than the ambient temperature
    # `factor` is empirical and operator-tunable via TEMP_CPU_FACTOR -- see the
    # calibration block near the top of this file.
    factor = temp_cpu_factor
    if cpu_temp is not None:
        comp_temp = raw_temp - ((cpu_temp - raw_temp) * factor)
        current_temp_compensated = True
    else:
        comp_temp = raw_temp
        current_temp_compensated = False
        logging.warning(
            "CPU temperature unavailable; reporting UNCOMPENSATED raw "
            "temperature reading instead of silently applying heat "
            "compensation as if the CPU reading had succeeded."
        )

    # Empirical offset, expressed in °F for calibration against a reference
    # thermometer and converted to a °C delta here (°F degrees are 5/9 the
    # size of °C degrees; this is a delta, so there is no 32 term).
    comp_temp = comp_temp + (temp_offset_f * 5 / 9)

    return round(comp_temp, 1)

def get_humidity():
    """Get humidity from the Sense HAT"""
    # Take multiple readings and average them
    readings = []
    for _ in range(3):
        readings.append(sense.get_humidity())
        time.sleep(0.1)
    
    # Remove outliers if possible
    if len(readings) > 2:
        readings.sort()
        readings = readings[1:-1]  # Remove highest and lowest
    
    humidity = statistics.mean(readings)

    # Empirical correction, operator-tunable via HUMIDITY_OFFSET
    humidity += humidity_offset

    # Ensure humidity doesn't exceed 100%
    if humidity > 100:
        humidity = 100

    # Return the average
    return round(humidity, 1)

def update_sensor_data():
    """Background thread function to update sensor data periodically"""
    global current_temp, current_humidity, last_updated, last_updated_ts

    while True:
        try:
            # get_compensated_temperature() sets current_temp_compensated
            # as a side effect (see its docstring / S3).
            current_temp = get_compensated_temperature()
            current_humidity = get_humidity()
            last_updated = time.strftime("%Y-%m-%d %H:%M:%S")
            last_updated_ts = time.time()

            cpu_temp_val = get_cpu_temperature()
            cpu_temp_display = f"{cpu_temp_val}°C" if cpu_temp_val is not None else "N/A"
            logging.info(
                f"Temperature: {current_temp}°C, Humidity: {current_humidity}%, CPU Temp: {cpu_temp_display}"
            )

            # Check thresholds and send alerts via webhook
            if webhook_service:
                try:
                    alerts_sent = webhook_service.check_and_alert(
                        current_temp, current_humidity, last_updated
                    )
                    if alerts_sent and any(alerts_sent.values()):
                        increment_alert_counter()
                        logging.info(f"Webhook alerts sent: {list(alerts_sent.keys())}")
                except Exception as webhook_error:
                    logging.error(f"Error sending webhook alert: {webhook_error}")

            # Send periodic status updates if enabled
            if status_update_enabled and webhook_service:
                global last_status_update
                current_time = time.time()

                # Check if it's time for a status update
                should_send_update = (
                    last_status_update is None or  # First update or startup update
                    (current_time - last_status_update) >= status_update_interval
                )

                if should_send_update:
                    try:
                        cpu_temp = get_cpu_temperature()
                        success = webhook_service.send_status_update(
                            current_temp, current_humidity, cpu_temp, last_updated
                        )

                        if success:
                            logging.info("Periodic status update sent successfully")
                        else:
                            logging.warning("Periodic status update failed, will retry at next interval")

                    except Exception as update_error:
                        logging.error(f"Error sending periodic status update: {update_error}")
                    finally:
                        # C7: anchor the next interval at (previous + interval),
                        # not at current_time (the moment this check happened to
                        # run). The loop only samples once per sampling_interval,
                        # so a firing can land up to sampling_interval late; using
                        # current_time as the new anchor would make that lateness
                        # the baseline for the NEXT interval too, and the
                        # schedule would drift progressively later forever.
                        # last_status_update is None on a startup-triggered
                        # first send, so anchor from current_time in that one
                        # case (there is no previous anchor to advance from).
                        last_status_update = (
                            current_time if last_status_update is None
                            else last_status_update + status_update_interval
                        )

            # Display temperature on Sense HAT LED matrix
            temp_f = round((current_temp * 9/5) + 32, 1)
            message = f"Temp: {temp_f}F"
            sense.show_message(message)

            # Sleep for the specified interval
            time.sleep(sampling_interval)
        except Exception as e:
            logging.error(f"Error updating sensor data: {e}")
            time.sleep(5)  # Short sleep before retry on error

@app.route('/api/temp')
@require_token
def api_temp():
    """API endpoint returning temperature data as JSON"""
    fahrenheit = round((current_temp * 9/5) + 32, 1)
    return jsonify({
        'temperature_c': current_temp,
        'temperature_f': fahrenheit,
        'humidity': current_humidity,
        'compensated': current_temp_compensated,
        'timestamp': last_updated
    })

@app.route('/api/raw')
@require_token
def api_raw():
    """API endpoint for debugging, showing raw vs compensated temperature"""
    cpu_temp = get_cpu_temperature()
    raw_temp = sense.get_temperature()

    def _round(value):
        """Coerce a sensor reading for JSON, or None if it isn't a number.

        cpu_temperature was already None-guarded below, but raw_temperature
        was not: sense.get_temperature() returns None when the driver cannot
        read the sensor, and round(None, 1) raised TypeError -- turning this
        debugging endpoint into a bare 500 at exactly the moment the sensor
        is misbehaving and you most need to inspect it.
        """
        try:
            return round(float(value), 1)
        except (TypeError, ValueError):
            return None

    return jsonify({
        'cpu_temperature': _round(cpu_temp),
        'raw_temperature': _round(raw_temp),
        'compensated_temperature': current_temp,
        'compensated': current_temp_compensated,
        'humidity': current_humidity,
        'timestamp': last_updated,
        # Echo the active calibration so an operator comparing this endpoint
        # against a reference thermometer can see exactly which constants
        # produced compensated_temperature, without shelling into the box.
        'calibration': {
            'cpu_factor': temp_cpu_factor,
            'offset_f': temp_offset_f,
            'humidity_offset': humidity_offset,
        },
    })

# Add an endpoint to check if token is valid
@app.route('/api/verify-token', methods=['GET'])
@require_token
def verify_token():
    """Verify if the provided token is valid"""
    return jsonify({
        'valid': True,
        'message': 'Token is valid'
    })

# Webhook management endpoints using Flask-RESTX
@webhooks_ns.route('/config')
class WebhookConfigResource(Resource):
    """Webhook configuration management"""

    @webhooks_ns.doc(security='bearer')
    @webhooks_ns.marshal_with(webhook_config_response)
    @webhooks_ns.response(200, 'Success', webhook_config_response)
    @require_token
    def get(self):
        """Get current webhook configuration"""
        if not webhook_service or not webhook_service.webhook_config:
            return {
                'webhook': {
                    'url': None,
                    'enabled': False,
                    'retry_count': 3,
                    'retry_delay': 5,
                    'timeout': 10
                },
                'thresholds': {
                    'temp_min_c': None,
                    'temp_max_c': None,
                    'humidity_min': None,
                    'humidity_max': None
                }
            }

        config = webhook_service.webhook_config
        thresholds = webhook_service.alert_thresholds

        return {
            'webhook': {
                'url': mask_webhook_url(config.url),
                'enabled': config.enabled,
                'retry_count': config.retry_count,
                'retry_delay': config.retry_delay,
                'timeout': config.timeout
            },
            'thresholds': {
                'temp_min_c': thresholds.temp_min_c,
                'temp_max_c': thresholds.temp_max_c,
                'humidity_min': thresholds.humidity_min,
                'humidity_max': thresholds.humidity_max
            }
        }

    @webhooks_ns.doc(security='bearer')
    @webhooks_ns.expect(webhook_config_update)
    @webhooks_ns.marshal_with(success_response)
    @webhooks_ns.response(400, 'Validation Error', error_response)
    @webhooks_ns.response(500, 'Server Error', error_response)
    @require_token
    def put(self):
        """Update webhook configuration with validation"""
        global webhook_service

        data = webhooks_ns.payload

        # Validate webhook config field ranges
        if 'webhook' in data and data['webhook']:
            is_valid, error_msg = validate_webhook_config(data['webhook'])
            if not is_valid:
                webhooks_ns.abort(400, error_msg)

        # Cross-field validation for thresholds. C3: pass the currently
        # stored thresholds so the min/max cross-check validates the
        # RESULTING merged config, not just the keys present in this
        # payload -- otherwise a partial update (e.g. only temp_min_c) that
        # pushes min above the STORED max is accepted.
        if 'thresholds' in data and data['thresholds']:
            is_valid, error_msg = validate_thresholds(
                data['thresholds'],
                current_thresholds=webhook_service.alert_thresholds if webhook_service else None
            )
            if not is_valid:
                webhooks_ns.abort(400, error_msg)

        # Validate URL is provided when no existing URL to fall back to
        if 'webhook' in data and data['webhook']:
            webhook_data = data['webhook']
            has_existing_url = (
                webhook_service and
                webhook_service.webhook_config and
                webhook_service.webhook_config.url
            )
            if not has_existing_url and not webhook_data.get('url'):
                webhooks_ns.abort(400, 'URL required when no existing webhook config')

        # C6: remember whether a webhook service exists BEFORE this request,
        # so we can tell below whether one gets created fresh by this call.
        service_created_by_this_request = webhook_service is None

        try:
            # Update webhook config if provided
            if 'webhook' in data and data['webhook']:
                webhook_data = data['webhook']

                # If webhook service doesn't exist, create it. C8: pass the
                # module-level alert_cooldown_seconds (parsed from
                # ALERT_COOLDOWN_SECONDS at import) so a service created here
                # doesn't silently revert to WebhookService's hardcoded 900s
                # default.
                if not webhook_service:
                    webhook_service = WebhookService(alert_cooldown=alert_cooldown_seconds)

                existing_config = webhook_service.webhook_config if webhook_service else None

                def merged_config(field, default):
                    """Take the submitted value when the key is present (even
                    if explicitly null), else the currently stored value, else
                    the documented default."""
                    if field in webhook_data:
                        return webhook_data[field]
                    return getattr(existing_config, field, default)

                config = WebhookConfig(
                    url=merged_config('url', ''),
                    enabled=merged_config('enabled', True),
                    retry_count=merged_config('retry_count', 3),
                    retry_delay=merged_config('retry_delay', 5),
                    timeout=merged_config('timeout', 10)
                )
                webhook_service.set_webhook_config(config)

            # Update thresholds if provided. C1: merge with the currently
            # stored thresholds so an omitted key is preserved, not wiped to
            # None -- dict.get(field, fallback) only returns the fallback
            # when the key is ABSENT, so a key explicitly sent as JSON null
            # still clears that field (thresholds intentionally support
            # null-to-clear; see api_models.validate_thresholds
            # allow_null=True).
            if 'thresholds' in data and data['thresholds']:
                threshold_data = data['thresholds']
                existing_thresholds = webhook_service.alert_thresholds if webhook_service else None

                def merged_threshold(field):
                    if field in threshold_data:
                        return threshold_data[field]
                    return getattr(existing_thresholds, field, None)

                thresholds = AlertThresholds(
                    temp_min_c=merged_threshold('temp_min_c'),
                    temp_max_c=merged_threshold('temp_max_c'),
                    humidity_min=merged_threshold('humidity_min'),
                    humidity_max=merged_threshold('humidity_max')
                )

                if not webhook_service:
                    # C8: same cooldown fix as the webhook branch above.
                    webhook_service = WebhookService(
                        alert_thresholds=thresholds, alert_cooldown=alert_cooldown_seconds
                    )
                else:
                    webhook_service.set_alert_thresholds(thresholds)

            # C6: a webhook service created by THIS request needs its status
            # update timer started the same way module-init does for
            # STATUS_UPDATE_ON_STARTUP=false (temp_monitor.py init block
            # above) -- otherwise last_status_update stays None and the very
            # next sensor-loop iteration fires a status update immediately,
            # ignoring STATUS_UPDATE_ON_STARTUP.
            if service_created_by_this_request and webhook_service and status_update_enabled:
                global last_status_update
                if last_status_update is None:
                    last_status_update = time.time()
                    logging.info(
                        "Webhook service created via API; status update timer started"
                    )

            return {
                'message': 'Webhook configuration updated successfully',
                'config': {
                    'webhook': {
                        'url': mask_webhook_url(webhook_service.webhook_config.url) if webhook_service and webhook_service.webhook_config else None,
                        'enabled': webhook_service.webhook_config.enabled if webhook_service and webhook_service.webhook_config else False,
                        'retry_count': webhook_service.webhook_config.retry_count if webhook_service and webhook_service.webhook_config else 3,
                        'retry_delay': webhook_service.webhook_config.retry_delay if webhook_service and webhook_service.webhook_config else 5,
                        'timeout': webhook_service.webhook_config.timeout if webhook_service and webhook_service.webhook_config else 10
                    },
                    'thresholds': {
                        'temp_min_c': webhook_service.alert_thresholds.temp_min_c if webhook_service else None,
                        'temp_max_c': webhook_service.alert_thresholds.temp_max_c if webhook_service else None,
                        'humidity_min': webhook_service.alert_thresholds.humidity_min if webhook_service else None,
                        'humidity_max': webhook_service.alert_thresholds.humidity_max if webhook_service else None
                    }
                }
            }

        except Exception as e:
            error_id = generate_error_id()
            logging.exception(f"Error updating webhook config [error_id: {error_id}]")
            # C5: this method is decorated with @marshal_with(success_response)
            # -- a plain `return {...}, 500` gets marshalled AGAINST THAT
            # SUCCESS SCHEMA, silently dropping 'error'/'error_id' and
            # emitting {"message": null, "config": {...all nulls}}, which
            # destroys the diagnostics right when they're needed most (same
            # marshalling trap that previously caused an auth bypass
            # elsewhere in this file). webhooks_ns.abort() raises an
            # HTTPException that flask-restx handles separately from
            # marshal_with, so the error text and error_id reach the client
            # intact.
            webhooks_ns.abort(500, 'Failed to update webhook configuration', error_id=error_id)


@webhooks_ns.route('/test')
class WebhookTestResource(Resource):
    """Test webhook functionality"""

    @webhooks_ns.doc(security='bearer')
    @webhooks_ns.marshal_with(test_response)
    @webhooks_ns.response(400, 'Webhook not configured', error_response)
    @webhooks_ns.response(500, 'Server Error', error_response)
    @require_token
    def post(self):
        """Send a test webhook message"""
        if not webhook_service or not webhook_service.webhook_config:
            webhooks_ns.abort(400, 'Webhook not configured')

        try:
            cpu_temp = get_cpu_temperature()
            success = webhook_service.send_status_update(
                current_temp,
                current_humidity,
                cpu_temp,
                last_updated
            )

            if success:
                return {
                    'message': 'Test webhook sent successfully',
                    'timestamp': last_updated
                }
            else:
                webhooks_ns.abort(500, 'Failed to send test webhook')

        except Exception as e:
            error_id = generate_error_id()
            logging.exception(f"Error sending test webhook [error_id: {error_id}]")
            webhooks_ns.abort(500, 'Failed to send test webhook')


@webhooks_ns.route('/enable')
class WebhookEnableResource(Resource):
    """Enable webhook notifications"""

    @webhooks_ns.doc(security='bearer')
    @webhooks_ns.marshal_with(message_response)
    @webhooks_ns.response(400, 'Webhook not configured', error_response)
    @require_token
    def post(self):
        """Enable webhook notifications"""
        if not webhook_service or not webhook_service.webhook_config:
            webhooks_ns.abort(400, 'Webhook not configured')

        webhook_service.webhook_config.enabled = True
        logging.info("Webhook notifications enabled")

        return {
            'message': 'Webhook notifications enabled',
            'enabled': True
        }


@webhooks_ns.route('/disable')
class WebhookDisableResource(Resource):
    """Disable webhook notifications"""

    @webhooks_ns.doc(security='bearer')
    @webhooks_ns.marshal_with(message_response)
    @webhooks_ns.response(400, 'Webhook not configured', error_response)
    @require_token
    def post(self):
        """Disable webhook notifications"""
        if not webhook_service or not webhook_service.webhook_config:
            webhooks_ns.abort(400, 'Webhook not configured')

        webhook_service.webhook_config.enabled = False
        logging.info("Webhook notifications disabled")

        return {
            'message': 'Webhook notifications disabled',
            'enabled': False
        }


# Production Deployment Endpoints
# ============================================================================

@app.route('/health')
def health():
    """Liveness check for monitoring and load balancers.

    Public (unauthenticated) by design, so it is intentionally stripped to
    liveness signals only -- NO sensor readings and NO process internals
    (S10). Returns 503 when the sensor thread is dead OR the last reading
    is stale, instead of unconditionally reporting "healthy" (S6): a
    thread that is technically alive but stuck (e.g. every read failing
    inside a caught exception) used to look identical to a healthy one to
    Docker's HEALTHCHECK, systemd, and any load balancer.
    """
    try:
        sensor_alive = sensor_thread is not None and sensor_thread.is_alive()

        reading_age = None
        reading_stale = True  # no reading yet counts as stale
        if last_updated_ts is not None:
            reading_age = time.time() - last_updated_ts
            reading_stale = reading_age > staleness_threshold_seconds

        healthy = sensor_alive and not reading_stale

        return jsonify({
            'status': 'healthy' if healthy else 'unhealthy',
            'uptime_seconds': time.time() - app_start_time,
            'sensor_thread_alive': sensor_alive,
            'reading_stale': reading_stale,
            'last_reading_age_seconds': round(reading_age, 1) if reading_age is not None else None,
            'temperature_compensated': current_temp_compensated,
            'timestamp': time.time()
        }), (200 if healthy else 503)
    except Exception as e:
        error_id = generate_error_id()
        logging.exception(f"Health check error [error_id: {error_id}]")
        return jsonify({'status': 'error', 'error_id': error_id}), 500


@app.route('/metrics')
@require_token
def metrics():
    """System and application metrics for Pi 4 monitoring.

    Requires a bearer token (S10): this endpoint exposes process internals
    (RSS, thread count, open FD count) and a live psutil.cpu_percent()
    sample per request, and the service is reachable over a public tunnel.
    """
    try:
        metrics_data = {
            'application': {
                'total_requests': request_counter,
                'webhook_alerts_sent': webhook_alert_counter,
                'uptime_seconds': time.time() - app_start_time,
                'last_sensor_update': last_updated,
                'current_temp_c': current_temp,
                'current_humidity_percent': current_humidity,
                'sensor_thread_alive': sensor_thread is not None and sensor_thread.is_alive()
            },
            'hardware': {
                'cpu_temp_c': get_cpu_temperature()
            }
        }

        # Add system metrics if psutil is available
        if psutil:
            try:
                process = psutil.Process()
                metrics_data['system'] = {
                    'cpu_percent': psutil.cpu_percent(interval=0.1),
                    'memory_mb': process.memory_info().rss / 1024 / 1024,
                    'memory_percent': process.memory_percent(),
                    'threads': process.num_threads(),
                    'file_descriptors': process.num_fds() if hasattr(process, 'num_fds') else 'N/A'
                }
            except Exception as psutil_error:
                logging.exception("Error collecting system metrics")
                metrics_data['system'] = {'error': 'Unable to collect system metrics'}
        else:
            metrics_data['system'] = {'error': 'psutil not available'}

        return jsonify(metrics_data), 200
    except Exception as e:
        error_id = generate_error_id()
        logging.exception(f"Metrics endpoint error [error_id: {error_id}]")
        return jsonify({'error': 'Unable to retrieve metrics', 'error_id': error_id}), 500


def start_sensor_thread():
    """
    Start the background sensor thread.

    Returns:
        threading.Thread: The started sensor thread

    Raises:
        RuntimeError: If sensor thread fails to start
    """
    global sensor_thread

    if sensor_thread is not None and sensor_thread.is_alive():
        logging.warning("Sensor thread is already running, skipping restart")
        return sensor_thread

    logging.info("Starting temperature monitor sensor thread")
    sensor_thread = threading.Thread(target=update_sensor_data, daemon=True)
    sensor_thread.start()

    # Give the thread a moment to get initial readings
    time.sleep(2)

    if not sensor_thread.is_alive():
        raise RuntimeError("Sensor thread failed to start")

    logging.info("Sensor thread started successfully")
    return sensor_thread


def increment_request_counter():
    """Middleware-like function to track requests"""
    global request_counter
    with counters_lock:
        request_counter += 1


def increment_alert_counter():
    """Increment webhook alert counter"""
    global webhook_alert_counter
    with counters_lock:
        webhook_alert_counter += 1


# Add request counter tracking
@app.before_request
def before_request():
    """Track incoming requests for metrics"""
    increment_request_counter()


if __name__ == '__main__':
    try:
        # Start the background sensor thread
        start_sensor_thread()

        # Start the Flask web server in development mode
        logging.info("Starting Flask development server on 0.0.0.0:8080")
        app.run(host='0.0.0.0', port=8080)
    except Exception as e:
        logging.error(f"Failed to start service: {e}")
        raise
