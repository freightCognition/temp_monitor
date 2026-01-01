"""
Flask-RESTX API Models for Temperature Monitor

Defines request/response models with validation for webhook configuration endpoints.
Provides automatic OpenAPI/Swagger documentation generation.
"""

from flask_restx import Namespace, fields

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
        min=1,
        max=10,
        description='Number of retry attempts (1-10)'
    ),
    'retry_delay': fields.Integer(
        default=5,
        min=1,
        max=60,
        description='Initial retry delay in seconds (1-60)'
    ),
    'timeout': fields.Integer(
        default=10,
        min=5,
        max=120,
        description='Request timeout in seconds (5-120)'
    )
})

# Alert thresholds model
alert_thresholds_input = webhooks_ns.model('AlertThresholdsInput', {
    'temp_min_c': fields.Float(
        description='Minimum temperature threshold in Celsius (-50 to 100)',
        min=-50,
        max=100,
        example=15.0
    ),
    'temp_max_c': fields.Float(
        description='Maximum temperature threshold in Celsius (-50 to 100)',
        min=-50,
        max=100,
        example=27.0
    ),
    'humidity_min': fields.Float(
        description='Minimum humidity threshold percentage (0-100)',
        min=0,
        max=100,
        example=30.0
    ),
    'humidity_max': fields.Float(
        description='Maximum humidity threshold percentage (0-100)',
        min=0,
        max=100,
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
    'error': fields.String(description='Error message'),
    'details': fields.String(description='Additional error details')
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


def validate_webhook_config(webhook: dict) -> tuple:
    """
    Validate webhook configuration field ranges.

    Args:
        webhook: Dictionary with webhook config values

    Returns:
        Tuple of (is_valid: bool, error_message: str)
    """
    if 'retry_count' in webhook and webhook['retry_count'] is not None:
        if not (1 <= webhook['retry_count'] <= 10):
            return False, 'retry_count must be between 1 and 10'

    if 'retry_delay' in webhook and webhook['retry_delay'] is not None:
        if not (1 <= webhook['retry_delay'] <= 60):
            return False, 'retry_delay must be between 1 and 60 seconds'

    if 'timeout' in webhook and webhook['timeout'] is not None:
        if not (5 <= webhook['timeout'] <= 120):
            return False, 'timeout must be between 5 and 120 seconds'

    return True, ''


def validate_thresholds(thresholds: dict) -> tuple:
    """
    Validate threshold relationships (cross-field validation).

    Args:
        thresholds: Dictionary with threshold values

    Returns:
        Tuple of (is_valid: bool, error_message: str)
    """
    if thresholds.get('temp_min_c') is not None and thresholds.get('temp_max_c') is not None:
        if thresholds['temp_min_c'] >= thresholds['temp_max_c']:
            return False, 'temp_min_c must be less than temp_max_c'

    if thresholds.get('humidity_min') is not None and thresholds.get('humidity_max') is not None:
        if thresholds['humidity_min'] >= thresholds['humidity_max']:
            return False, 'humidity_min must be less than humidity_max'

    return True, ''
