# Webhook Security Best Practices

This reference covers security patterns and best practices for implementing secure webhook endpoints with Flask-RESTX.

## Overview

Webhook endpoints are public HTTP endpoints that receive data from external services. They require special security considerations:

1. **Authentication**: Verify the webhook sender's identity
2. **Integrity**: Ensure the payload hasn't been tampered with
3. **Confidentiality**: Protect sensitive data in transit
4. **Rate Limiting**: Prevent abuse and DoS attacks
5. **Input Validation**: Sanitize all incoming data

## HMAC Signature Verification

### Standard HMAC-SHA256 Implementation

```python
import hmac
import hashlib
from functools import wraps
from flask import request, abort, g
import time

class SignatureVerifier:
    """HMAC signature verification for webhooks"""

    def __init__(self, secret_key, header_name='X-Webhook-Signature',
                 timestamp_header='X-Webhook-Timestamp',
                 timestamp_tolerance=300):
        self.secret_key = secret_key
        self.header_name = header_name
        self.timestamp_header = timestamp_header
        self.timestamp_tolerance = timestamp_tolerance  # seconds

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
        """Verify the signature matches"""
        expected = self.compute_signature(payload, timestamp)
        return hmac.compare_digest(expected, signature)

    def verify_timestamp(self, timestamp):
        """Check if timestamp is within tolerance"""
        try:
            ts = int(timestamp)
            current = int(time.time())
            return abs(current - ts) <= self.timestamp_tolerance
        except (ValueError, TypeError):
            return False

def require_webhook_signature(secret_key, header_name='X-Webhook-Signature'):
    """Decorator to require valid webhook signature"""
    verifier = SignatureVerifier(secret_key, header_name)

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            signature = request.headers.get(header_name)
            timestamp = request.headers.get('X-Webhook-Timestamp')

            if not signature:
                abort(401, 'Missing signature header')

            payload = request.get_data(as_text=True)

            # Verify timestamp if present
            if timestamp:
                if not verifier.verify_timestamp(timestamp):
                    abort(401, 'Timestamp expired or invalid')

            # Verify signature
            if not verifier.verify(payload, signature, timestamp):
                abort(401, 'Invalid signature')

            # Store verification info for logging
            g.webhook_verified = True
            g.webhook_timestamp = timestamp

            return f(*args, **kwargs)
        return decorated_function
    return decorator
```

### Provider-Specific Signature Verification

#### GitHub Webhooks

```python
def verify_github_signature(payload, signature, secret):
    """Verify GitHub webhook signature (X-Hub-Signature-256)"""
    if not signature:
        return False

    expected = 'sha256=' + hmac.new(
        secret.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(expected, signature)

def require_github_webhook(secret):
    """Decorator for GitHub webhook verification"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            signature = request.headers.get('X-Hub-Signature-256')
            payload = request.get_data()

            if not verify_github_signature(payload, signature, secret):
                abort(401, 'Invalid GitHub signature')

            return f(*args, **kwargs)
        return decorated_function
    return decorator
```

#### Stripe Webhooks

```python
import stripe

def verify_stripe_webhook(payload, signature, endpoint_secret):
    """Verify Stripe webhook signature"""
    try:
        event = stripe.Webhook.construct_event(
            payload, signature, endpoint_secret
        )
        return event
    except ValueError:
        return None  # Invalid payload
    except stripe.error.SignatureVerificationError:
        return None  # Invalid signature

def require_stripe_webhook(endpoint_secret):
    """Decorator for Stripe webhook verification"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            payload = request.get_data(as_text=True)
            signature = request.headers.get('Stripe-Signature')

            event = verify_stripe_webhook(payload, signature, endpoint_secret)
            if not event:
                abort(400, 'Invalid Stripe webhook')

            g.stripe_event = event
            return f(*args, **kwargs)
        return decorated_function
    return decorator
```

#### Slack Webhooks

```python
def verify_slack_signature(payload, timestamp, signature, signing_secret):
    """Verify Slack webhook signature"""
    # Check timestamp (prevent replay attacks)
    if abs(time.time() - float(timestamp)) > 60 * 5:
        return False

    sig_basestring = f"v0:{timestamp}:{payload}"
    computed = 'v0=' + hmac.new(
        signing_secret.encode('utf-8'),
        sig_basestring.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(computed, signature)

def require_slack_webhook(signing_secret):
    """Decorator for Slack webhook verification"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            timestamp = request.headers.get('X-Slack-Request-Timestamp')
            signature = request.headers.get('X-Slack-Signature')
            payload = request.get_data(as_text=True)

            if not verify_slack_signature(payload, timestamp, signature, signing_secret):
                abort(401, 'Invalid Slack signature')

            return f(*args, **kwargs)
        return decorated_function
    return decorator
```

## Rate Limiting

### Token Bucket Rate Limiter

```python
from collections import defaultdict
import time
import threading

class RateLimiter:
    """Token bucket rate limiter"""

    def __init__(self, rate=10, per=60, burst=20):
        self.rate = rate  # tokens per period
        self.per = per    # period in seconds
        self.burst = burst  # max tokens
        self.tokens = defaultdict(lambda: burst)
        self.last_update = defaultdict(time.time)
        self.lock = threading.Lock()

    def is_allowed(self, key):
        """Check if request is allowed"""
        with self.lock:
            now = time.time()
            time_passed = now - self.last_update[key]

            # Add tokens based on time passed
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
        """Get seconds until next token available"""
        tokens_needed = 1 - self.tokens[key]
        return int(tokens_needed * (self.per / self.rate)) + 1

# Global rate limiter
webhook_limiter = RateLimiter(rate=100, per=60, burst=150)

def rate_limit_by_ip():
    """Decorator to rate limit by IP address"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            ip = request.remote_addr

            if not webhook_limiter.is_allowed(ip):
                retry_after = webhook_limiter.get_retry_after(ip)
                response = {
                    'error': 'Rate limit exceeded',
                    'retry_after': retry_after
                }
                return response, 429, {'Retry-After': str(retry_after)}

            return f(*args, **kwargs)
        return decorated_function
    return decorator
```

### Redis-Based Rate Limiter (Production)

```python
import redis
from datetime import datetime

class RedisRateLimiter:
    """Redis-based sliding window rate limiter"""

    def __init__(self, redis_client, prefix='ratelimit'):
        self.redis = redis_client
        self.prefix = prefix

    def is_allowed(self, key, limit=100, window=60):
        """
        Check if request is allowed using sliding window.

        Args:
            key: Identifier (IP, API key, etc.)
            limit: Maximum requests per window
            window: Window size in seconds
        """
        now = datetime.now().timestamp()
        window_start = now - window

        pipe = self.redis.pipeline()
        redis_key = f"{self.prefix}:{key}"

        # Remove old entries
        pipe.zremrangebyscore(redis_key, 0, window_start)

        # Count current entries
        pipe.zcard(redis_key)

        # Add current request
        pipe.zadd(redis_key, {str(now): now})

        # Set expiry
        pipe.expire(redis_key, window)

        results = pipe.execute()
        current_count = results[1]

        return current_count < limit

    def get_remaining(self, key, limit=100, window=60):
        """Get remaining requests in current window"""
        now = datetime.now().timestamp()
        window_start = now - window
        redis_key = f"{self.prefix}:{key}"

        # Remove old and count
        self.redis.zremrangebyscore(redis_key, 0, window_start)
        count = self.redis.zcard(redis_key)

        return max(0, limit - count)
```

## IP Allowlisting

### Static IP Allowlist

```python
ALLOWED_IPS = {
    '192.168.1.100',
    '10.0.0.0/8',  # CIDR notation
    '172.16.0.0/12'
}

def ip_in_range(ip, cidr):
    """Check if IP is in CIDR range"""
    import ipaddress
    try:
        return ipaddress.ip_address(ip) in ipaddress.ip_network(cidr)
    except ValueError:
        return False

def is_ip_allowed(ip):
    """Check if IP is in allowlist"""
    import ipaddress

    for allowed in ALLOWED_IPS:
        if '/' in allowed:
            if ip_in_range(ip, allowed):
                return True
        elif ip == allowed:
            return True
    return False

def require_allowed_ip():
    """Decorator to require allowed IP"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            ip = request.remote_addr

            # Handle X-Forwarded-For behind proxy
            forwarded = request.headers.get('X-Forwarded-For')
            if forwarded:
                ip = forwarded.split(',')[0].strip()

            if not is_ip_allowed(ip):
                abort(403, 'IP not allowed')

            return f(*args, **kwargs)
        return decorated_function
    return decorator
```

### Dynamic IP Registration

```python
class IPRegistry:
    """Dynamic IP allowlist with registration"""

    def __init__(self):
        self.registered_ips = {}  # ip -> metadata
        self.verification_tokens = {}  # token -> ip

    def generate_verification_token(self):
        """Generate verification token"""
        import secrets
        return secrets.token_urlsafe(32)

    def start_registration(self, ip, metadata=None):
        """Start IP registration process"""
        token = self.generate_verification_token()
        self.verification_tokens[token] = {
            'ip': ip,
            'metadata': metadata,
            'created_at': time.time()
        }
        return token

    def verify_registration(self, token, requesting_ip):
        """Complete IP registration"""
        if token not in self.verification_tokens:
            return False

        registration = self.verification_tokens[token]

        # Check token age (24 hour expiry)
        if time.time() - registration['created_at'] > 86400:
            del self.verification_tokens[token]
            return False

        # Register IP
        self.registered_ips[requesting_ip] = {
            'metadata': registration['metadata'],
            'registered_at': time.time()
        }

        del self.verification_tokens[token]
        return True

    def is_registered(self, ip):
        """Check if IP is registered"""
        return ip in self.registered_ips

ip_registry = IPRegistry()
```

## Input Validation and Sanitization

### Request Validation

```python
from flask_restx import fields
import bleach
import re

def sanitize_string(value, max_length=1000):
    """Sanitize string input"""
    if not isinstance(value, str):
        return value

    # Limit length
    value = value[:max_length]

    # Remove control characters
    value = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', value)

    # Strip HTML
    value = bleach.clean(value, tags=[], strip=True)

    return value.strip()

def sanitize_payload(data, max_depth=10, current_depth=0):
    """Recursively sanitize payload"""
    if current_depth > max_depth:
        raise ValueError('Maximum nesting depth exceeded')

    if isinstance(data, dict):
        return {
            sanitize_string(k): sanitize_payload(v, max_depth, current_depth + 1)
            for k, v in data.items()
        }
    elif isinstance(data, list):
        return [
            sanitize_payload(item, max_depth, current_depth + 1)
            for item in data
        ]
    elif isinstance(data, str):
        return sanitize_string(data)
    else:
        return data

# Validation models with sanitization
class SanitizedString(fields.String):
    """String field with automatic sanitization"""

    def format(self, value):
        return sanitize_string(super().format(value))

webhook_payload = api.model('SecureWebhookPayload', {
    'event_type': SanitizedString(
        required=True,
        pattern=r'^[a-z][a-z0-9_\.]+$',
        max_length=50
    ),
    'data': fields.Raw(required=True)
})
```

### Schema Validation

```python
from jsonschema import validate, ValidationError as JSONSchemaError

WEBHOOK_SCHEMA = {
    "type": "object",
    "required": ["event_type", "timestamp", "data"],
    "additionalProperties": False,
    "properties": {
        "event_type": {
            "type": "string",
            "pattern": "^[a-z][a-z0-9_\\.]+$",
            "maxLength": 50
        },
        "timestamp": {
            "type": "string",
            "format": "date-time"
        },
        "data": {
            "type": "object",
            "maxProperties": 100
        },
        "metadata": {
            "type": "object",
            "maxProperties": 20
        }
    }
}

def validate_webhook_schema(payload):
    """Validate webhook payload against schema"""
    try:
        validate(instance=payload, schema=WEBHOOK_SCHEMA)
        return True, None
    except JSONSchemaError as e:
        return False, str(e.message)
```

## Secret Management

### Environment Variables

```python
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Secure configuration from environment"""

    WEBHOOK_SECRET = os.environ.get('WEBHOOK_SECRET')
    GITHUB_WEBHOOK_SECRET = os.environ.get('GITHUB_WEBHOOK_SECRET')
    STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET')

    @classmethod
    def validate(cls):
        """Ensure all required secrets are set"""
        required = ['WEBHOOK_SECRET']

        missing = [
            key for key in required
            if not getattr(cls, key)
        ]

        if missing:
            raise ValueError(f"Missing required secrets: {missing}")
```

### Secret Rotation

```python
class RotatingSecretManager:
    """Manage rotating webhook secrets"""

    def __init__(self, primary_secret, secondary_secret=None):
        self.secrets = [primary_secret]
        if secondary_secret:
            self.secrets.append(secondary_secret)

    def verify_signature(self, payload, signature):
        """Try verification with all active secrets"""
        for secret in self.secrets:
            verifier = SignatureVerifier(secret)
            if verifier.verify(payload, signature):
                return True
        return False

    def rotate(self, new_secret):
        """Rotate to new secret (keep old as secondary)"""
        self.secrets = [new_secret, self.secrets[0]]

# Usage
secret_manager = RotatingSecretManager(
    primary_secret=os.environ.get('WEBHOOK_SECRET'),
    secondary_secret=os.environ.get('WEBHOOK_SECRET_OLD')
)
```

## Logging and Auditing

### Security Event Logging

```python
import logging
import json
from datetime import datetime

class SecurityLogger:
    """Structured security event logger"""

    def __init__(self):
        self.logger = logging.getLogger('security')
        handler = logging.FileHandler('security.log')
        handler.setFormatter(logging.Formatter('%(message)s'))
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)

    def log_event(self, event_type, **kwargs):
        """Log security event"""
        event = {
            'timestamp': datetime.utcnow().isoformat(),
            'event_type': event_type,
            **kwargs
        }
        self.logger.info(json.dumps(event))

    def log_auth_success(self, ip, endpoint, user_agent=None):
        self.log_event(
            'auth_success',
            ip=ip,
            endpoint=endpoint,
            user_agent=user_agent
        )

    def log_auth_failure(self, ip, endpoint, reason, user_agent=None):
        self.log_event(
            'auth_failure',
            ip=ip,
            endpoint=endpoint,
            reason=reason,
            user_agent=user_agent
        )

    def log_rate_limit(self, ip, endpoint):
        self.log_event(
            'rate_limit_exceeded',
            ip=ip,
            endpoint=endpoint
        )

    def log_suspicious_activity(self, ip, details):
        self.log_event(
            'suspicious_activity',
            ip=ip,
            details=details
        )

security_logger = SecurityLogger()
```

### Request Logging Middleware

```python
from flask import g
import time
import uuid

@app.before_request
def before_request():
    """Log incoming webhook requests"""
    g.request_id = str(uuid.uuid4())
    g.request_start = time.time()

    security_logger.log_event(
        'webhook_received',
        request_id=g.request_id,
        ip=request.remote_addr,
        endpoint=request.path,
        method=request.method,
        user_agent=request.headers.get('User-Agent'),
        content_length=request.content_length
    )

@app.after_request
def after_request(response):
    """Log request completion"""
    duration = (time.time() - g.request_start) * 1000

    security_logger.log_event(
        'webhook_completed',
        request_id=g.request_id,
        status_code=response.status_code,
        duration_ms=duration
    )

    return response
```

## HTTPS and Transport Security

### Force HTTPS

```python
from flask_talisman import Talisman

# Production security headers
talisman = Talisman(
    app,
    force_https=True,
    strict_transport_security=True,
    strict_transport_security_max_age=31536000,  # 1 year
    content_security_policy={
        'default-src': "'self'",
        'script-src': "'self'",
        'style-src': "'self'"
    }
)

# Or manual HTTPS redirect
@app.before_request
def require_https():
    if not request.is_secure and app.env != 'development':
        url = request.url.replace('http://', 'https://', 1)
        return redirect(url, code=301)
```

### Security Headers

```python
@app.after_request
def add_security_headers(response):
    """Add security headers to all responses"""

    # Prevent clickjacking
    response.headers['X-Frame-Options'] = 'DENY'

    # XSS protection
    response.headers['X-XSS-Protection'] = '1; mode=block'

    # Content type sniffing protection
    response.headers['X-Content-Type-Options'] = 'nosniff'

    # Referrer policy
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'

    return response
```

## Complete Secure Webhook Endpoint

```python
from flask import Flask, request, g
from flask_restx import Api, Resource, Namespace, fields
import os

app = Flask(__name__)
api = Api(app, doc='/docs')

webhooks_ns = Namespace('webhooks', description='Secure webhook endpoints')

# Security components
secret_manager = RotatingSecretManager(
    primary_secret=os.environ.get('WEBHOOK_SECRET')
)
rate_limiter = RateLimiter(rate=100, per=60)
security_logger = SecurityLogger()

# Secure payload model
webhook_payload = webhooks_ns.model('SecurePayload', {
    'event_type': fields.String(required=True),
    'timestamp': fields.DateTime(required=True),
    'data': fields.Raw(required=True)
})

@webhooks_ns.route('/secure')
class SecureWebhook(Resource):

    @webhooks_ns.expect(webhook_payload, validate=True)
    @webhooks_ns.doc(
        security='webhook_signature',
        responses={
            200: 'Webhook processed',
            401: 'Authentication failed',
            429: 'Rate limit exceeded'
        }
    )
    def post(self):
        """Secure webhook endpoint with full protection"""
        ip = request.remote_addr

        # Rate limiting
        if not rate_limiter.is_allowed(ip):
            security_logger.log_rate_limit(ip, request.path)
            return {'error': 'Rate limit exceeded'}, 429

        # Signature verification
        signature = request.headers.get('X-Webhook-Signature')
        payload = request.get_data(as_text=True)

        if not secret_manager.verify_signature(payload, signature):
            security_logger.log_auth_failure(
                ip, request.path, 'Invalid signature'
            )
            return {'error': 'Invalid signature'}, 401

        security_logger.log_auth_success(ip, request.path)

        # Sanitize and validate
        data = sanitize_payload(webhooks_ns.payload)
        valid, error = validate_webhook_schema(data)

        if not valid:
            return {'error': f'Validation failed: {error}'}, 400

        # Process webhook
        result = process_webhook(data)

        return {
            'status': 'processed',
            'request_id': g.request_id
        }, 200

api.add_namespace(webhooks_ns, path='/api/webhooks')
```

## Security Checklist

### Before Deployment

- [ ] HTTPS enforced on all endpoints
- [ ] HMAC signature verification implemented
- [ ] Rate limiting configured
- [ ] Input validation enabled
- [ ] Secrets stored securely (not in code)
- [ ] Security logging enabled
- [ ] Security headers configured
- [ ] IP allowlisting considered (if applicable)

### Ongoing Maintenance

- [ ] Regular secret rotation
- [ ] Security log monitoring
- [ ] Rate limit tuning based on usage
- [ ] Dependency updates for security patches
- [ ] Periodic security audits
