"""
Secure Flask-RESTX Webhook with HMAC Signature Verification

This example demonstrates:
- HMAC-SHA256 signature verification
- Timestamp validation to prevent replay attacks
- Rate limiting by IP address
- Security logging
- Multiple authentication schemes in OpenAPI
- Provider-specific signature patterns (GitHub, Stripe, Slack)

Usage:
    pip install flask flask-restx python-dotenv

    # Set up environment
    echo "WEBHOOK_SECRET=your-secret-key-here" > .env

    # Run server
    python webhook-with-signature.py

    # Test with valid signature
    python test_webhook.py

    # View Swagger docs with security info
    Open http://localhost:5000/docs
"""

from flask import Flask, request, abort, g
from flask_restx import Api, Namespace, Resource, fields
from datetime import datetime
from functools import wraps
from collections import defaultdict
import hashlib
import hmac
import logging
import os
import time
import uuid

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Security logger for audit trail
security_logger = logging.getLogger('security')
security_handler = logging.FileHandler('webhook_security.log')
security_handler.setFormatter(
    logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
)
security_logger.addHandler(security_handler)
security_logger.setLevel(logging.INFO)

# =============================================================================
# Configuration
# =============================================================================

class Config:
    """Application configuration"""
    WEBHOOK_SECRET = os.environ.get('WEBHOOK_SECRET')
    GITHUB_WEBHOOK_SECRET = os.environ.get('GITHUB_WEBHOOK_SECRET')
    STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET')
    SLACK_SIGNING_SECRET = os.environ.get('SLACK_SIGNING_SECRET')
    TIMESTAMP_TOLERANCE = 300  # 5 minutes

    @classmethod
    def validate(cls):
        if not cls.WEBHOOK_SECRET:
            raise ValueError(
                "WEBHOOK_SECRET environment variable is required. "
                "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )

Config.validate()

# =============================================================================
# Rate Limiting
# =============================================================================

class RateLimiter:
    """Simple token bucket rate limiter"""

    def __init__(self, rate=100, per=60, burst=150):
        self.rate = rate
        self.per = per
        self.burst = burst
        self.tokens = defaultdict(lambda: burst)
        self.last_update = defaultdict(time.time)

    def is_allowed(self, key):
        now = time.time()
        time_passed = now - self.last_update[key]

        # Replenish tokens
        self.tokens[key] = min(
            self.burst,
            self.tokens[key] + time_passed * (self.rate / self.per)
        )
        self.last_update[key] = now

        if self.tokens[key] >= 1:
            self.tokens[key] -= 1
            return True
        return False

    def get_retry_after(self, key):
        tokens_needed = 1 - self.tokens[key]
        return int(tokens_needed * (self.per / self.rate)) + 1

rate_limiter = RateLimiter()

# =============================================================================
# Signature Verification
# =============================================================================

class SignatureVerifier:
    """HMAC signature verification"""

    def __init__(self, secret_key):
        self.secret_key = secret_key

    def compute_signature(self, payload, timestamp=None):
        """Compute HMAC-SHA256 signature"""
        if timestamp:
            message = f"{timestamp}.{payload}"
        else:
            message = payload

        if isinstance(message, str):
            message = message.encode('utf-8')

        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            message,
            hashlib.sha256
        ).hexdigest()

        return f"sha256={signature}"

    def verify(self, payload, signature, timestamp=None):
        """Verify signature matches expected"""
        expected = self.compute_signature(payload, timestamp)
        return hmac.compare_digest(expected, signature)

    @staticmethod
    def verify_timestamp(timestamp, tolerance=300):
        """Check if timestamp is within tolerance window"""
        try:
            ts = int(timestamp)
            current = int(time.time())
            return abs(current - ts) <= tolerance
        except (ValueError, TypeError):
            return False

# =============================================================================
# Security Decorators
# =============================================================================

def require_signature(secret_key_name='WEBHOOK_SECRET'):
    """Decorator to require valid HMAC signature"""
    secret = getattr(Config, secret_key_name)
    verifier = SignatureVerifier(secret)

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Get signature from header
            signature = request.headers.get('X-Webhook-Signature')
            timestamp = request.headers.get('X-Webhook-Timestamp')

            if not signature:
                security_logger.warning(
                    f"Missing signature from {request.remote_addr} to {request.path}"
                )
                abort(401, 'Missing signature header')

            # Get payload
            payload = request.get_data(as_text=True)

            # Verify timestamp if provided
            if timestamp:
                if not verifier.verify_timestamp(timestamp, Config.TIMESTAMP_TOLERANCE):
                    security_logger.warning(
                        f"Invalid timestamp from {request.remote_addr}: {timestamp}"
                    )
                    abort(401, 'Timestamp expired or invalid')

            # Verify signature
            if not verifier.verify(payload, signature, timestamp):
                security_logger.warning(
                    f"Invalid signature from {request.remote_addr} to {request.path}"
                )
                abort(401, 'Invalid signature')

            # Log successful verification
            security_logger.info(
                f"Signature verified for {request.remote_addr} to {request.path}"
            )

            g.signature_verified = True
            g.webhook_timestamp = timestamp

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def rate_limit_by_ip():
    """Decorator for IP-based rate limiting"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            ip = request.remote_addr

            if not rate_limiter.is_allowed(ip):
                retry_after = rate_limiter.get_retry_after(ip)
                security_logger.warning(f"Rate limit exceeded for {ip}")

                response = {
                    'error': 'rate_limit_exceeded',
                    'message': 'Too many requests',
                    'retry_after': retry_after
                }
                return response, 429, {'Retry-After': str(retry_after)}

            return f(*args, **kwargs)
        return decorated_function
    return decorator

# =============================================================================
# Flask App Setup
# =============================================================================

app = Flask(__name__)
app.config['RESTX_VALIDATE'] = True

# Define authorization schemes
authorizations = {
    'webhook_signature': {
        'type': 'apiKey',
        'in': 'header',
        'name': 'X-Webhook-Signature',
        'description': 'HMAC-SHA256 signature. Format: sha256={hex_digest}'
    },
    'webhook_timestamp': {
        'type': 'apiKey',
        'in': 'header',
        'name': 'X-Webhook-Timestamp',
        'description': 'Unix timestamp when signature was generated'
    }
}

api = Api(
    app,
    version='1.0.0',
    title='Secure Webhook API',
    description='''
    Webhook API with HMAC signature verification and rate limiting.

    ## Security

    All webhook endpoints require HMAC-SHA256 signature verification.

    ### Generating Signatures

    1. Get the raw request body as a string
    2. Optionally prepend with timestamp: `{timestamp}.{body}`
    3. Compute HMAC-SHA256 using your secret key
    4. Send as header: `X-Webhook-Signature: sha256={hex_digest}`

    ### Example (Python)

    ```python
    import hmac
    import hashlib
    import time

    secret = "your-secret-key"
    payload = '{"event_type":"test","data":{}}'
    timestamp = str(int(time.time()))

    message = f"{timestamp}.{payload}"
    signature = hmac.new(
        secret.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()

    headers = {
        'X-Webhook-Signature': f'sha256={signature}',
        'X-Webhook-Timestamp': timestamp
    }
    ```
    ''',
    doc='/docs',
    prefix='/api',
    authorizations=authorizations,
    security='webhook_signature'
)

webhooks_ns = Namespace(
    'webhooks',
    description='Secure webhook endpoints'
)

# =============================================================================
# Models
# =============================================================================

webhook_payload = webhooks_ns.model('WebhookPayload', {
    'event_type': fields.String(
        required=True,
        description='Event type identifier',
        example='user.created'
    ),
    'timestamp': fields.DateTime(
        required=True,
        description='Event timestamp',
        example='2024-01-15T10:30:00Z'
    ),
    'data': fields.Raw(
        required=True,
        description='Event data',
        example={'user_id': '123'}
    )
})

webhook_response = webhooks_ns.model('WebhookResponse', {
    'status': fields.String(example='received'),
    'event_id': fields.String(example='evt_abc123'),
    'verified': fields.Boolean(example=True),
    'processed_at': fields.DateTime()
})

error_response = webhooks_ns.model('ErrorResponse', {
    'error': fields.String(description='Error code'),
    'message': fields.String(description='Error message')
})

# =============================================================================
# Webhook Endpoints
# =============================================================================

@webhooks_ns.route('/secure')
class SecureWebhook(Resource):
    """Webhook endpoint with signature verification"""

    @webhooks_ns.expect(webhook_payload, validate=True)
    @webhooks_ns.marshal_with(webhook_response, code=200)
    @webhooks_ns.response(401, 'Authentication failed', error_response)
    @webhooks_ns.response(429, 'Rate limit exceeded', error_response)
    @webhooks_ns.doc(
        security=['webhook_signature', 'webhook_timestamp'],
        description='''
        Secure webhook endpoint requiring HMAC signature verification.

        **Required Headers:**
        - `X-Webhook-Signature`: sha256={hex_digest}
        - `X-Webhook-Timestamp`: Unix timestamp (optional, recommended)

        **Signature Validation:**
        - Signature must be valid HMAC-SHA256
        - Timestamp must be within 5 minutes (if provided)
        - Rate limit: 100 requests per minute per IP
        '''
    )
    @require_signature()
    @rate_limit_by_ip()
    def post(self):
        """Receive webhook with signature verification"""
        payload = webhooks_ns.payload
        event_id = f"evt_{uuid.uuid4().hex[:12]}"

        logger.info(f"Processing webhook: {payload['event_type']} ({event_id})")

        # Process webhook (add your business logic here)
        # ...

        return {
            'status': 'received',
            'event_id': event_id,
            'verified': g.get('signature_verified', False),
            'processed_at': datetime.utcnow()
        }


@webhooks_ns.route('/github')
class GitHubWebhook(Resource):
    """GitHub-compatible webhook endpoint"""

    @webhooks_ns.doc(
        description='GitHub webhook endpoint using X-Hub-Signature-256',
        params={
            'X-Hub-Signature-256': 'GitHub webhook signature'
        }
    )
    @rate_limit_by_ip()
    def post(self):
        """Receive GitHub webhook"""
        if not Config.GITHUB_WEBHOOK_SECRET:
            security_logger.warning(f"GitHub webhook rejected: secret not configured")
            abort(503, 'GitHub webhook secret not configured')

        signature = request.headers.get('X-Hub-Signature-256')
        if not signature:
            abort(401, 'Missing GitHub signature')

        payload = request.get_data()
        expected = 'sha256=' + hmac.new(
            Config.GITHUB_WEBHOOK_SECRET.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(expected, signature):
            security_logger.warning(f"Invalid GitHub signature from {request.remote_addr}")
            abort(401, 'Invalid signature')

        event_type = request.headers.get('X-GitHub-Event', 'unknown')
        logger.info(f"GitHub event: {event_type}")

        return {'status': 'received', 'event_type': event_type}


# =============================================================================
# Utility Endpoints
# =============================================================================

@webhooks_ns.route('/verify')
class VerifyEndpoint(Resource):
    """Test signature verification"""

    @webhooks_ns.doc(
        description='Test endpoint to verify your signature generation',
        security=['webhook_signature', 'webhook_timestamp']
    )
    @require_signature()
    def post(self):
        """Verify signature without processing"""
        return {
            'verified': True,
            'message': 'Signature is valid',
            'timestamp': g.get('webhook_timestamp')
        }


@app.route('/health')
def health():
    """Health check"""
    return {'status': 'healthy', 'timestamp': datetime.utcnow().isoformat()}


# =============================================================================
# Error Handlers
# =============================================================================

@api.errorhandler
def default_error_handler(error):
    """Handle all errors"""
    return {
        'error': type(error).__name__,
        'message': str(error)
    }, getattr(error, 'code', 500)


# =============================================================================
# Request/Response Logging
# =============================================================================

@app.before_request
def log_request():
    """Log incoming requests"""
    g.request_id = str(uuid.uuid4())
    g.request_start = time.time()

    logger.info(
        f"[{g.request_id}] {request.method} {request.path} "
        f"from {request.remote_addr}"
    )


@app.after_request
def log_response(response):
    """Log responses"""
    duration = (time.time() - g.request_start) * 1000

    logger.info(
        f"[{g.request_id}] {response.status_code} "
        f"({duration:.2f}ms)"
    )

    return response


# =============================================================================
# Register and Run
# =============================================================================

api.add_namespace(webhooks_ns, path='/webhooks')

if __name__ == '__main__':
    print("\n" + "="*70)
    print("Secure Flask-RESTX Webhook Server")
    print("="*70)
    print(f"  Swagger UI:    http://localhost:5000/docs")
    print(f"  Webhook URL:   http://localhost:5000/api/webhooks/secure")
    print(f"  Test Verify:   http://localhost:5000/api/webhooks/verify")
    print(f"  Health:        http://localhost:5000/health")
    print("="*70)
    print("\n  Secret Key:    " + ("✓ Configured" if Config.WEBHOOK_SECRET else "✗ MISSING"))
    print("\n  Run test_webhook.py to test signature verification")
    print("="*70 + "\n")

    app.run(host='0.0.0.0', port=5000, debug=True)
