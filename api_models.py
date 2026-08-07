"""
Flask-RESTX API Models for Temperature Monitor

Defines request/response models with validation for webhook configuration endpoints.
Provides automatic OpenAPI/Swagger documentation generation.
"""

from flask_restx import Namespace, fields
from urllib.parse import urlparse

from webhook_service import (
    RETRY_COUNT_RANGE, RETRY_DELAY_RANGE, TIMEOUT_RANGE,
    TEMP_RANGE, HUMIDITY_RANGE,
)

# Create namespace for webhook endpoints
webhooks_ns = Namespace('webhooks', description='Webhook configuration and management')

# Webhook configuration model with validation
# Note: url is not required for partial updates when webhook service already exists
webhook_config_input = webhooks_ns.model('WebhookConfigInput', {
    'url': fields.String(
        required=False,
        description='Slack webhook URL (required when creating new webhook config)',
        example='https://hooks.slack.com/services/...'
    ),
    'enabled': fields.Boolean(
        default=True,
        description='Enable/disable webhook notifications'
    ),
    'retry_count': fields.Integer(
        default=3,
        min=RETRY_COUNT_RANGE[0],
        max=RETRY_COUNT_RANGE[1],
        description='Number of retry attempts (1-10)'
    ),
    'retry_delay': fields.Integer(
        default=5,
        min=RETRY_DELAY_RANGE[0],
        max=RETRY_DELAY_RANGE[1],
        description='Initial retry delay in seconds (1-60)'
    ),
    'timeout': fields.Integer(
        default=10,
        min=TIMEOUT_RANGE[0],
        max=TIMEOUT_RANGE[1],
        description='Request timeout in seconds (5-120)'
    )
})

# Alert thresholds model
alert_thresholds_input = webhooks_ns.model('AlertThresholdsInput', {
    'temp_min_c': fields.Float(
        description='Minimum temperature threshold in Celsius (-50 to 100)',
        min=TEMP_RANGE[0],
        max=TEMP_RANGE[1],
        example=15.0
    ),
    'temp_max_c': fields.Float(
        description='Maximum temperature threshold in Celsius (-50 to 100)',
        min=TEMP_RANGE[0],
        max=TEMP_RANGE[1],
        example=27.0
    ),
    'humidity_min': fields.Float(
        description='Minimum humidity threshold percentage (0-100)',
        min=HUMIDITY_RANGE[0],
        max=HUMIDITY_RANGE[1],
        example=30.0
    ),
    'humidity_max': fields.Float(
        description='Maximum humidity threshold percentage (0-100)',
        min=HUMIDITY_RANGE[0],
        max=HUMIDITY_RANGE[1],
        example=70.0
    )
})

# Combined config update request model
webhook_config_update = webhooks_ns.model('WebhookConfigUpdate', {
    'webhook': fields.Nested(webhook_config_input, description='Webhook settings'),
    'thresholds': fields.Nested(alert_thresholds_input, description='Alert thresholds')
})

# Response models - separate from input models for flexibility
webhook_config_output = webhooks_ns.model('WebhookConfigOutput', {
    'url': fields.String(description='Webhook URL (masked - scheme and host only for security)'),
    'enabled': fields.Boolean(description='Webhook enabled status'),
    'retry_count': fields.Integer(description='Number of retry attempts'),
    'retry_delay': fields.Integer(description='Retry delay in seconds'),
    'timeout': fields.Integer(description='Request timeout in seconds')
})

alert_thresholds_output = webhooks_ns.model('AlertThresholdsOutput', {
    'temp_min_c': fields.Float(description='Minimum temperature threshold in Celsius'),
    'temp_max_c': fields.Float(description='Maximum temperature threshold in Celsius'),
    'humidity_min': fields.Float(description='Minimum humidity threshold percentage'),
    'humidity_max': fields.Float(description='Maximum humidity threshold percentage')
})

webhook_config_response = webhooks_ns.model('WebhookConfigResponse', {
    'webhook': fields.Nested(webhook_config_output),
    'thresholds': fields.Nested(alert_thresholds_output)
})

error_response = webhooks_ns.model('ErrorResponse', {
    'message': fields.String(description='Error message (validation errors, e.g. from webhooks_ns.abort)'),
    'error': fields.String(description='Error message (unhandled server errors)'),
    'error_id': fields.String(description='Unique error identifier for log correlation (500 errors)')
})

success_response = webhooks_ns.model('SuccessResponse', {
    'message': fields.String(description='Success message'),
    'config': fields.Nested(webhook_config_response, description='Updated configuration')
})

# Simple message response for enable/disable endpoints
message_response = webhooks_ns.model('MessageResponse', {
    'message': fields.String(description='Response message'),
    'enabled': fields.Boolean(description='Current enabled status')
})

# Test webhook response
test_response = webhooks_ns.model('TestResponse', {
    'message': fields.String(description='Test result message'),
    'timestamp': fields.String(description='Timestamp of the test')
})


def _validate_numeric_field(container: dict, field: str, min_val, max_val,
                             *, integer_only: bool, allow_null: bool) -> None:
    """
    Validate a single numeric field on a payload dict in place.

    Raises ValueError with a clear message on any invalid input (wrong type,
    disallowed null, or out-of-range). Booleans are explicitly rejected even
    though Python considers bool a subclass of int (True/False must not be
    accepted as 1/0). A missing key is always fine (partial update).
    """
    if field not in container:
        return

    value = container[field]

    if value is None:
        if allow_null:
            return
        raise ValueError(f'{field} cannot be null')

    is_bool = isinstance(value, bool)
    if integer_only:
        valid_type = isinstance(value, int) and not is_bool
    else:
        valid_type = isinstance(value, (int, float)) and not is_bool

    if not valid_type:
        expected = 'an integer' if integer_only else 'a number'
        raise ValueError(f'{field} must be {expected}')

    if not (min_val <= value <= max_val):
        raise ValueError(f'{field} must be between {min_val} and {max_val}')


def validate_webhook_config(webhook: dict) -> tuple:
    """
    Validate webhook configuration field types and ranges.

    Defensive against malformed/untrusted JSON: non-dict input, wrong field
    types (str/float/bool/list/dict where an int is expected), explicit
    JSON null on fields that don't support it, and out-of-range values all
    produce a clean (False, message) result instead of a raised
    TypeError/AttributeError.

    A key that is simply absent from `webhook` is treated as "not being
    updated" (partial update). A key present with an explicit JSON `null`
    is treated as an invalid attempt to clear a required field for `url`,
    `retry_count`, `retry_delay`, and `timeout`.

    Args:
        webhook: Dictionary with webhook config values

    Returns:
        Tuple of (is_valid: bool, error_message: str)
    """
    try:
        if not isinstance(webhook, dict):
            raise ValueError('webhook must be an object')

        if 'url' in webhook:
            url = webhook['url']
            if url is None:
                # Explicit null would silently wipe out an existing URL
                # (or block creation of a new config) if allowed through.
                raise ValueError('URL required: url must not be null')
            if not isinstance(url, str) or not url.strip():
                raise ValueError('url must be a non-empty string')
            # Basic URL format validation
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                raise ValueError('url must be a valid URL with scheme and host')

        if 'enabled' in webhook:
            enabled = webhook['enabled']
            # An explicit null here was previously accepted and stored, and
            # because WebhookService checks `not config.enabled`, a None
            # silently disabled ALL webhook delivery -- after a 200 OK that
            # reported success. Same failure shape as a null url.
            if enabled is None:
                raise ValueError('enabled must not be null')
            if not isinstance(enabled, bool):
                raise ValueError('enabled must be a boolean')

        _validate_numeric_field(webhook, 'retry_count', *RETRY_COUNT_RANGE, integer_only=True, allow_null=False)
        _validate_numeric_field(webhook, 'retry_delay', *RETRY_DELAY_RANGE, integer_only=True, allow_null=False)
        _validate_numeric_field(webhook, 'timeout', *TIMEOUT_RANGE, integer_only=True, allow_null=False)
    except ValueError as e:
        return False, str(e)

    return True, ''


def _get_threshold_field(source, field: str):
    """Read a threshold field from either a dict or an object (e.g. AlertThresholds)."""
    if source is None:
        return None
    if isinstance(source, dict):
        return source.get(field)
    return getattr(source, field, None)


def validate_thresholds(thresholds: dict, current_thresholds=None) -> tuple:
    """
    Validate threshold field types, absolute ranges, and cross-field
    relationships (min < max).

    Defensive against malformed/untrusted JSON: non-dict input and
    non-numeric field values (e.g. strings) produce a clean (False,
    message) result instead of a raised TypeError/AttributeError.
    Documented absolute ranges (-50..100C, 0..100%) are enforced.

    Args:
        thresholds: Dictionary with threshold values from the request payload.
        current_thresholds: Optional currently-stored thresholds (dict or an
            object such as AlertThresholds). When provided, the min/max
            cross-check validates the RESULTING merged config (payload
            values override current_thresholds values), so a partial update
            that would put min >= max against the stored config is caught.
            When omitted (default), behavior is unchanged from before:
            the cross-check only fires when both keys of a pair are present
            in the payload itself.

    Returns:
        Tuple of (is_valid: bool, error_message: str)
    """
    try:
        if not isinstance(thresholds, dict):
            raise ValueError('thresholds must be an object')

        _validate_numeric_field(thresholds, 'temp_min_c', *TEMP_RANGE, integer_only=False, allow_null=True)
        _validate_numeric_field(thresholds, 'temp_max_c', *TEMP_RANGE, integer_only=False, allow_null=True)
        _validate_numeric_field(thresholds, 'humidity_min', *HUMIDITY_RANGE, integer_only=False, allow_null=True)
        _validate_numeric_field(thresholds, 'humidity_max', *HUMIDITY_RANGE, integer_only=False, allow_null=True)

        def effective(field):
            # Mirror the merge in temp_monitor.py's PUT handler exactly: a
            # key that is PRESENT (even as explicit JSON null) overrides the
            # stored value; only an ABSENT key falls back to current_thresholds.
            # Treating an explicit null as "fall back to current" (the
            # previous behavior) disagreed with the merge, which treats
            # explicit null as "clear this field" -- so a legal clear could
            # get a spurious 400 naming the field the operator just cleared.
            if field in thresholds:
                return thresholds[field]
            return _get_threshold_field(current_thresholds, field)

        temp_min = effective('temp_min_c')
        temp_max = effective('temp_max_c')
        if temp_min is not None and temp_max is not None and temp_min >= temp_max:
            raise ValueError('temp_min_c must be less than temp_max_c')

        humidity_min = effective('humidity_min')
        humidity_max = effective('humidity_max')
        if humidity_min is not None and humidity_max is not None and humidity_min >= humidity_max:
            raise ValueError('humidity_min must be less than humidity_max')
    except ValueError as e:
        return False, str(e)

    return True, ''
