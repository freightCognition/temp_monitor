---
name: Flask-RESTX Webhooks & OpenAPI
description: This skill should be used when the user asks to "create a webhook endpoint", "add webhook handlers", "implement webhook signature verification", "configure Flask-RESTX API", "generate OpenAPI documentation", "add Swagger UI", "define API models", "validate webhook payloads", "secure webhook endpoints", "implement HMAC signature validation", or mentions Flask-RESTX, webhooks, OpenAPI spec, or Swagger documentation in a Flask context.
version: 1.0.0
---

# Flask-RESTX Webhooks & OpenAPI Skill

This skill provides comprehensive guidance for building webhook endpoints and OpenAPI-documented REST APIs using Flask-RESTX. It covers request validation, response modeling, webhook security patterns, and automatic Swagger documentation generation.

## When to Activate

Activate this skill when:
- Building webhook receiver endpoints in Flask
- Adding OpenAPI/Swagger documentation to Flask APIs
- Implementing HMAC signature verification for webhooks
- Defining request/response models with Flask-RESTX
- Organizing APIs with namespaces
- Securing webhook endpoints with authentication

## Core Concepts

### Flask-RESTX Overview

Flask-RESTX is a community-driven fork of Flask-RESTPlus that provides:
- Automatic Swagger UI documentation generation
- Request validation through models and parsers
- Response marshalling with field definitions
- Namespace-based API organization
- Decorator-based endpoint documentation

Installation:
```bash
pip install flask-restx
```

### Basic API Setup

```python
from flask import Flask
from flask_restx import Api, Resource, fields

app = Flask(__name__)
api = Api(
    app,
    version='1.0',
    title='Webhook API',
    description='API for receiving and processing webhooks',
    doc='/docs'  # Swagger UI endpoint
)
```

### Namespace Organization

Organize related endpoints into namespaces for cleaner code structure:

```python
from flask_restx import Namespace

webhooks_ns = Namespace('webhooks', description='Webhook operations')
api.add_namespace(webhooks_ns, path='/api/webhooks')
```

### Model Definition

Define request/response models for validation and documentation:

```python
webhook_payload = webhooks_ns.model('WebhookPayload', {
    'event_type': fields.String(required=True, description='Type of event'),
    'timestamp': fields.DateTime(required=True, description='Event timestamp'),
    'data': fields.Raw(required=True, description='Event payload data'),
    'signature': fields.String(description='HMAC signature for verification')
})

webhook_response = webhooks_ns.model('WebhookResponse', {
    'status': fields.String(description='Processing status'),
    'message': fields.String(description='Response message'),
    'event_id': fields.String(description='Assigned event ID')
})
```

### Field Types Reference

| Field Type | Use Case | Validation Options |
|------------|----------|-------------------|
| `fields.String` | Text data | `min_length`, `max_length`, `pattern`, `enum` |
| `fields.Integer` | Whole numbers | `min`, `max` |
| `fields.Float` | Decimal numbers | `min`, `max` |
| `fields.Boolean` | True/False | - |
| `fields.DateTime` | ISO 8601 dates | - |
| `fields.List` | Arrays | Nested field type |
| `fields.Nested` | Embedded objects | Reference to another model |
| `fields.Raw` | Arbitrary JSON | - |

### Request Validation with @expect

Use the `@expect` decorator for automatic request validation:

```python
@webhooks_ns.route('/receive')
class WebhookReceiver(Resource):
    @webhooks_ns.expect(webhook_payload, validate=True)
    @webhooks_ns.marshal_with(webhook_response, code=200)
    @webhooks_ns.doc(
        responses={
            200: 'Webhook processed successfully',
            400: 'Invalid payload',
            401: 'Invalid signature',
            422: 'Validation error'
        }
    )
    def post(self):
        """Receive and process incoming webhooks"""
        data = webhooks_ns.payload
        # Process webhook...
        return {'status': 'success', 'message': 'Webhook received'}
```

### Webhook Signature Verification

Implement HMAC-SHA256 signature verification for security:

```python
import hmac
import hashlib
from functools import wraps
from flask import request, abort

def verify_webhook_signature(secret_key):
    """Decorator to verify webhook HMAC signatures"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            signature = request.headers.get('X-Webhook-Signature')
            if not signature:
                abort(401, 'Missing signature header')

            payload = request.get_data()
            expected = hmac.new(
                secret_key.encode(),
                payload,
                hashlib.sha256
            ).hexdigest()

            if not hmac.compare_digest(f'sha256={expected}', signature):
                abort(401, 'Invalid signature')

            return f(*args, **kwargs)
        return decorated_function
    return decorator
```

### Error Handling

Register custom error handlers for consistent error responses:

```python
@api.errorhandler(Exception)
def handle_exception(error):
    """Global error handler"""
    return {
        'error': str(error),
        'type': type(error).__name__
    }, getattr(error, 'code', 500)

# For validation errors specifically
from werkzeug.exceptions import BadRequest

@api.errorhandler(BadRequest)
def handle_bad_request(error):
    return {
        'error': 'Validation failed',
        'details': error.description
    }, 400
```

### OpenAPI Customization

Add metadata and customize the OpenAPI specification:

```python
api = Api(
    app,
    version='1.0',
    title='Webhook Service API',
    description='Service for receiving and processing webhook events',
    license='MIT',
    contact='api@example.com',
    authorizations={
        'webhook_signature': {
            'type': 'apiKey',
            'in': 'header',
            'name': 'X-Webhook-Signature',
            'description': 'HMAC-SHA256 signature of request body'
        },
        'bearer': {
            'type': 'apiKey',
            'in': 'header',
            'name': 'Authorization',
            'description': 'Bearer token authentication'
        }
    },
    security='webhook_signature'
)
```

### Async Webhook Processing

For high-volume webhooks, implement async processing:

```python
from queue import Queue
from threading import Thread
import uuid

webhook_queue = Queue()

def process_webhook_worker():
    """Background worker for webhook processing"""
    while True:
        event = webhook_queue.get()
        try:
            # Process event asynchronously
            handle_event(event)
        except Exception as e:
            logger.error(f"Failed to process event: {e}")
        finally:
            webhook_queue.task_done()

# Start worker thread
worker = Thread(target=process_webhook_worker, daemon=True)
worker.start()

@webhooks_ns.route('/async')
class AsyncWebhookReceiver(Resource):
    @webhooks_ns.expect(webhook_payload, validate=True)
    def post(self):
        """Queue webhook for async processing"""
        event_id = str(uuid.uuid4())
        webhook_queue.put({
            'id': event_id,
            'payload': webhooks_ns.payload
        })
        return {
            'status': 'queued',
            'event_id': event_id
        }, 202
```

## Implementation Workflow

### Step 1: Project Setup

```python
# requirements.txt
flask>=2.0.0
flask-restx>=1.3.0
python-dotenv>=1.0.0
```

### Step 2: Application Structure

```
project/
├── app/
│   ├── __init__.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── webhooks.py
│   │   └── models.py
│   └── utils/
│       ├── __init__.py
│       └── security.py
├── config.py
└── run.py
```

### Step 3: Configure Flask-RESTX

Initialize the API in `app/api/__init__.py`:

```python
from flask_restx import Api

api = Api(
    title='My Webhook API',
    version='1.0',
    description='Webhook processing service',
    doc='/docs'
)

from .webhooks import webhooks_ns
api.add_namespace(webhooks_ns)
```

### Step 4: Define Models and Endpoints

Create namespaced endpoints in `app/api/webhooks.py` following the patterns in this skill.

### Step 5: Enable Validation

Set global validation in Flask config:

```python
app.config['RESTX_VALIDATE'] = True
app.config['RESTX_MASK_SWAGGER'] = False
```

## Common Patterns

### Idempotency for Webhooks

Prevent duplicate processing with idempotency keys:

```python
processed_events = set()  # Use Redis in production

@webhooks_ns.route('/receive')
class WebhookReceiver(Resource):
    def post(self):
        event_id = request.headers.get('X-Idempotency-Key')
        if event_id in processed_events:
            return {'status': 'already_processed'}, 200

        # Process webhook...
        processed_events.add(event_id)
        return {'status': 'success'}, 200
```

### Retry Logic Documentation

Document retry behavior in your OpenAPI spec:

```python
@webhooks_ns.doc(
    description='''
    Webhook receiver endpoint.

    **Retry Policy:**
    - Returns 200 for successful processing
    - Returns 202 for queued processing
    - Returns 4xx for permanent failures (no retry)
    - Returns 5xx for temporary failures (retry with backoff)
    '''
)
```

## Additional Resources

### Reference Files

For detailed patterns and advanced techniques, consult:
- **`references/webhook-patterns.md`** - Common webhook implementation patterns
- **`references/openapi-integration.md`** - Advanced OpenAPI configuration
- **`references/security-best-practices.md`** - Webhook security patterns

### Example Files

Working examples in `examples/`:
- **`examples/basic-webhook.py`** - Simple webhook endpoint
- **`examples/webhook-with-signature.py`** - HMAC signature verification
- **`examples/openapi-spec.yaml`** - Complete OpenAPI specification

## Integration Notes

### With Existing Flask Apps

Add Flask-RESTX to existing Flask applications:

```python
from flask import Flask
from flask_restx import Api

app = Flask(__name__)

# Keep existing routes
@app.route('/health')
def health():
    return {'status': 'ok'}

# Add API namespace for new endpoints
api = Api(app, doc='/api/docs', prefix='/api')
```

### Testing Webhooks

Use tools like ngrok for local testing:

```bash
# Expose local server
ngrok http 8080

# Test with curl
curl -X POST https://your-ngrok-url/api/webhooks/receive \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Signature: sha256=..." \
  -d '{"event_type": "test", "data": {}}'
```

## Quick Reference

### Essential Decorators

| Decorator | Purpose |
|-----------|---------|
| `@ns.route('/path')` | Define endpoint URL |
| `@ns.expect(model)` | Validate request body |
| `@ns.marshal_with(model)` | Format response |
| `@ns.doc()` | Add documentation |
| `@ns.param()` | Document parameters |
| `@ns.response()` | Document response codes |

### Validation Configuration

```python
# Enable strict validation
app.config['RESTX_VALIDATE'] = True

# Custom validation error code
app.config['RESTX_VALIDATION_ERROR_CODE'] = 422
```

### Accessing Swagger Spec

```python
# Get OpenAPI JSON spec
@app.route('/openapi.json')
def openapi_spec():
    return api.__schema__
```
