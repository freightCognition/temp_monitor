# Webhook Implementation Patterns

This reference covers common webhook implementation patterns for Flask-RESTX applications.

## Event-Driven Architecture

### Webhook Flow Overview

```
┌─────────────┐     HTTP POST     ┌─────────────┐     Process     ┌─────────────┐
│   Sender    │ ───────────────▶  │  Receiver   │ ──────────────▶ │   Handler   │
│  (Provider) │                   │  (Your API) │                 │   (Logic)   │
└─────────────┘                   └─────────────┘                 └─────────────┘
       │                                 │                               │
       │                                 ▼                               │
       │                          Validate Signature                     │
       │                          Parse Payload                          │
       │                          Route to Handler                       │
       │                                 │                               │
       ◀─────────────────────────────────┴───────────────────────────────┘
              Return Response (200, 202, 4xx, 5xx)
```

## Event Type Routing

### Pattern 1: Single Endpoint with Event Routing

Route different event types through a single endpoint:

```python
from flask_restx import Namespace, Resource, fields

webhooks_ns = Namespace('webhooks', description='Webhook operations')

# Generic webhook payload model
webhook_model = webhooks_ns.model('Webhook', {
    'event_type': fields.String(required=True, enum=[
        'user.created',
        'user.updated',
        'user.deleted',
        'order.placed',
        'order.completed',
        'payment.received'
    ]),
    'timestamp': fields.DateTime(required=True),
    'data': fields.Raw(required=True)
})

# Event handlers registry
EVENT_HANDLERS = {}

def register_handler(event_type):
    """Decorator to register event handlers"""
    def decorator(func):
        EVENT_HANDLERS[event_type] = func
        return func
    return decorator

@register_handler('user.created')
def handle_user_created(data):
    """Handle new user creation"""
    user_id = data.get('user_id')
    email = data.get('email')
    # Process new user...
    return {'processed': True, 'user_id': user_id}

@register_handler('order.placed')
def handle_order_placed(data):
    """Handle new order"""
    order_id = data.get('order_id')
    # Process order...
    return {'processed': True, 'order_id': order_id}

@webhooks_ns.route('/events')
class WebhookEvents(Resource):
    @webhooks_ns.expect(webhook_model, validate=True)
    @webhooks_ns.doc(description='Receive webhook events')
    def post(self):
        payload = webhooks_ns.payload
        event_type = payload['event_type']

        handler = EVENT_HANDLERS.get(event_type)
        if not handler:
            return {'error': f'Unknown event type: {event_type}'}, 400

        try:
            result = handler(payload['data'])
            return {'status': 'processed', 'result': result}, 200
        except Exception as e:
            return {'error': str(e)}, 500
```

### Pattern 2: Separate Endpoints per Event Category

Organize by event category for larger APIs:

```python
# User events namespace
users_webhooks_ns = Namespace('webhooks/users', description='User webhook events')

user_event = users_webhooks_ns.model('UserEvent', {
    'action': fields.String(required=True, enum=['created', 'updated', 'deleted']),
    'user_id': fields.String(required=True),
    'email': fields.String(),
    'metadata': fields.Raw()
})

@users_webhooks_ns.route('')
class UserWebhooks(Resource):
    @users_webhooks_ns.expect(user_event, validate=True)
    def post(self):
        """Handle user-related webhook events"""
        payload = users_webhooks_ns.payload
        action = payload['action']

        if action == 'created':
            return self._handle_created(payload)
        elif action == 'updated':
            return self._handle_updated(payload)
        elif action == 'deleted':
            return self._handle_deleted(payload)

    def _handle_created(self, payload):
        # Handle user creation
        return {'status': 'user_created'}, 200

    def _handle_updated(self, payload):
        # Handle user update
        return {'status': 'user_updated'}, 200

    def _handle_deleted(self, payload):
        # Handle user deletion
        return {'status': 'user_deleted'}, 200


# Order events namespace
orders_webhooks_ns = Namespace('webhooks/orders', description='Order webhook events')

order_event = orders_webhooks_ns.model('OrderEvent', {
    'action': fields.String(required=True, enum=['placed', 'shipped', 'delivered', 'cancelled']),
    'order_id': fields.String(required=True),
    'items': fields.List(fields.Raw()),
    'total': fields.Float()
})

@orders_webhooks_ns.route('')
class OrderWebhooks(Resource):
    @orders_webhooks_ns.expect(order_event, validate=True)
    def post(self):
        """Handle order-related webhook events"""
        # Similar pattern to user webhooks
        pass
```

## Idempotency Patterns

### Pattern 1: Header-Based Idempotency Key

```python
from datetime import datetime, timedelta
import hashlib

# In production, use Redis or database
idempotency_store = {}

def check_idempotency(key, ttl_hours=24):
    """Check if event was already processed"""
    if key in idempotency_store:
        stored_time = idempotency_store[key]
        if datetime.now() - stored_time < timedelta(hours=ttl_hours):
            return True
    return False

def mark_processed(key):
    """Mark event as processed"""
    idempotency_store[key] = datetime.now()

@webhooks_ns.route('/receive')
class IdempotentWebhook(Resource):
    def post(self):
        # Get idempotency key from header or generate from payload
        idempotency_key = request.headers.get('X-Idempotency-Key')

        if not idempotency_key:
            # Generate from payload hash
            payload_bytes = request.get_data()
            idempotency_key = hashlib.sha256(payload_bytes).hexdigest()

        if check_idempotency(idempotency_key):
            return {
                'status': 'already_processed',
                'idempotency_key': idempotency_key
            }, 200

        # Process webhook...
        result = process_webhook(webhooks_ns.payload)

        mark_processed(idempotency_key)

        return {
            'status': 'processed',
            'idempotency_key': idempotency_key,
            'result': result
        }, 200
```

### Pattern 2: Event ID Tracking with Database

```python
from sqlalchemy import Column, String, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class ProcessedEvent(Base):
    __tablename__ = 'processed_events'

    event_id = Column(String(64), primary_key=True)
    event_type = Column(String(50))
    processed_at = Column(DateTime)
    success = Column(Boolean)
    error_message = Column(String(500), nullable=True)

def is_duplicate(db_session, event_id):
    """Check if event was already processed"""
    return db_session.query(ProcessedEvent).filter_by(
        event_id=event_id
    ).first() is not None

def record_event(db_session, event_id, event_type, success, error=None):
    """Record processed event"""
    event = ProcessedEvent(
        event_id=event_id,
        event_type=event_type,
        processed_at=datetime.utcnow(),
        success=success,
        error_message=str(error) if error else None
    )
    db_session.add(event)
    db_session.commit()
```

## Async Processing Patterns

### Pattern 1: Queue-Based Processing

```python
from queue import Queue
from threading import Thread
import logging

logger = logging.getLogger(__name__)

class WebhookProcessor:
    def __init__(self, num_workers=4):
        self.queue = Queue()
        self.workers = []

        for i in range(num_workers):
            worker = Thread(target=self._worker, daemon=True)
            worker.start()
            self.workers.append(worker)

    def _worker(self):
        while True:
            event = self.queue.get()
            try:
                self._process_event(event)
            except Exception as e:
                logger.error(f"Failed to process event {event.get('id')}: {e}")
            finally:
                self.queue.task_done()

    def _process_event(self, event):
        event_type = event.get('event_type')
        data = event.get('data')

        # Route to appropriate handler
        handler = EVENT_HANDLERS.get(event_type)
        if handler:
            handler(data)

    def enqueue(self, event):
        self.queue.put(event)
        return self.queue.qsize()

# Global processor instance
processor = WebhookProcessor()

@webhooks_ns.route('/async')
class AsyncWebhook(Resource):
    @webhooks_ns.expect(webhook_model, validate=True)
    def post(self):
        """Queue webhook for async processing"""
        import uuid

        event_id = str(uuid.uuid4())
        event = {
            'id': event_id,
            **webhooks_ns.payload
        }

        queue_size = processor.enqueue(event)

        return {
            'status': 'queued',
            'event_id': event_id,
            'queue_position': queue_size
        }, 202
```

### Pattern 2: Celery Task-Based Processing

```python
from celery import Celery

celery_app = Celery('webhooks', broker='redis://localhost:6379/0')

@celery_app.task(bind=True, max_retries=3)
def process_webhook_task(self, event_data):
    """Celery task for webhook processing"""
    try:
        event_type = event_data.get('event_type')
        handler = EVENT_HANDLERS.get(event_type)

        if handler:
            return handler(event_data.get('data'))
        else:
            raise ValueError(f'Unknown event type: {event_type}')

    except Exception as exc:
        # Retry with exponential backoff
        self.retry(exc=exc, countdown=2 ** self.request.retries)

@webhooks_ns.route('/celery')
class CeleryWebhook(Resource):
    @webhooks_ns.expect(webhook_model, validate=True)
    def post(self):
        """Queue webhook via Celery"""
        task = process_webhook_task.delay(webhooks_ns.payload)

        return {
            'status': 'queued',
            'task_id': task.id
        }, 202
```

## Retry and Error Handling

### Pattern 1: Automatic Retry with Backoff

```python
import time
from functools import wraps

def retry_on_failure(max_retries=3, backoff_factor=2):
    """Decorator for automatic retry with exponential backoff"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        sleep_time = backoff_factor ** attempt
                        logger.warning(
                            f"Attempt {attempt + 1} failed, "
                            f"retrying in {sleep_time}s: {e}"
                        )
                        time.sleep(sleep_time)

            raise last_exception
        return wrapper
    return decorator

@register_handler('payment.received')
@retry_on_failure(max_retries=3, backoff_factor=2)
def handle_payment(data):
    """Handle payment with automatic retry"""
    # Process payment - will retry on failure
    external_api.process_payment(data)
    return {'processed': True}
```

### Pattern 2: Dead Letter Queue

```python
from datetime import datetime

# Dead letter queue for failed events
dead_letter_queue = []

def send_to_dlq(event, error, attempts):
    """Send failed event to dead letter queue"""
    dlq_entry = {
        'event': event,
        'error': str(error),
        'attempts': attempts,
        'failed_at': datetime.utcnow().isoformat()
    }
    dead_letter_queue.append(dlq_entry)
    logger.error(f"Event sent to DLQ: {dlq_entry}")

@webhooks_ns.route('/receive-with-dlq')
class WebhookWithDLQ(Resource):
    MAX_ATTEMPTS = 3

    def post(self):
        event = webhooks_ns.payload
        attempts = int(request.headers.get('X-Retry-Count', 0)) + 1

        try:
            result = self._process_event(event)
            return {'status': 'processed', 'result': result}, 200

        except Exception as e:
            if attempts >= self.MAX_ATTEMPTS:
                send_to_dlq(event, e, attempts)
                return {
                    'status': 'failed',
                    'error': str(e),
                    'sent_to_dlq': True
                }, 200  # Return 200 to prevent sender retry

            # Return 5xx to trigger sender retry
            return {
                'status': 'temporary_failure',
                'error': str(e),
                'attempt': attempts
            }, 503

    def _process_event(self, event):
        # Processing logic here
        pass

# Endpoint to view/retry DLQ items
@webhooks_ns.route('/dlq')
class DeadLetterQueue(Resource):
    def get(self):
        """View dead letter queue"""
        return {'items': dead_letter_queue, 'count': len(dead_letter_queue)}

    def post(self):
        """Retry all DLQ items"""
        retried = []
        for item in dead_letter_queue[:]:
            try:
                # Retry processing
                process_webhook(item['event'])
                dead_letter_queue.remove(item)
                retried.append(item['event'].get('id'))
            except Exception as e:
                logger.error(f"DLQ retry failed: {e}")

        return {'retried': retried, 'remaining': len(dead_letter_queue)}
```

## Webhook Response Patterns

### Synchronous Response

Return immediately after processing:

```python
@webhooks_ns.route('/sync')
class SyncWebhook(Resource):
    def post(self):
        start_time = time.time()

        result = process_webhook(webhooks_ns.payload)

        return {
            'status': 'processed',
            'result': result,
            'processing_time_ms': (time.time() - start_time) * 1000
        }, 200
```

### Asynchronous Acknowledgment

Acknowledge receipt, process later:

```python
@webhooks_ns.route('/ack')
class AckWebhook(Resource):
    def post(self):
        event_id = str(uuid.uuid4())

        # Store for async processing
        pending_events[event_id] = {
            'payload': webhooks_ns.payload,
            'received_at': datetime.utcnow()
        }

        return {
            'status': 'acknowledged',
            'event_id': event_id,
            'message': 'Webhook received, processing asynchronously'
        }, 202
```

### Status Callback

Return status URL for checking progress:

```python
@webhooks_ns.route('/with-status')
class StatusWebhook(Resource):
    def post(self):
        event_id = str(uuid.uuid4())

        # Queue for processing
        processor.enqueue({'id': event_id, **webhooks_ns.payload})

        return {
            'status': 'queued',
            'event_id': event_id,
            'status_url': f'/api/webhooks/status/{event_id}'
        }, 202

@webhooks_ns.route('/status/<event_id>')
class WebhookStatus(Resource):
    def get(self, event_id):
        """Check webhook processing status"""
        status = get_event_status(event_id)

        if not status:
            return {'error': 'Event not found'}, 404

        return status
```

## Testing Webhooks

### Mock Webhook Sender

```python
import requests
import hmac
import hashlib
import json

class WebhookTestClient:
    def __init__(self, base_url, secret_key):
        self.base_url = base_url
        self.secret_key = secret_key

    def send_webhook(self, endpoint, payload, event_type='test'):
        url = f"{self.base_url}{endpoint}"
        body = json.dumps(payload)

        # Generate signature
        signature = hmac.new(
            self.secret_key.encode(),
            body.encode(),
            hashlib.sha256
        ).hexdigest()

        headers = {
            'Content-Type': 'application/json',
            'X-Webhook-Signature': f'sha256={signature}',
            'X-Event-Type': event_type,
            'X-Idempotency-Key': str(uuid.uuid4())
        }

        response = requests.post(url, data=body, headers=headers)
        return response

# Usage in tests
def test_webhook_endpoint():
    client = WebhookTestClient(
        'http://localhost:5000',
        'your-secret-key'
    )

    response = client.send_webhook(
        '/api/webhooks/receive',
        {'event_type': 'user.created', 'data': {'user_id': '123'}}
    )

    assert response.status_code == 200
    assert response.json()['status'] == 'processed'
```

## Logging and Monitoring

### Structured Logging

```python
import logging
import json

class WebhookLogger:
    def __init__(self):
        self.logger = logging.getLogger('webhooks')

    def log_received(self, event_id, event_type, source_ip):
        self.logger.info(json.dumps({
            'action': 'webhook_received',
            'event_id': event_id,
            'event_type': event_type,
            'source_ip': source_ip,
            'timestamp': datetime.utcnow().isoformat()
        }))

    def log_processed(self, event_id, duration_ms, success):
        self.logger.info(json.dumps({
            'action': 'webhook_processed',
            'event_id': event_id,
            'duration_ms': duration_ms,
            'success': success,
            'timestamp': datetime.utcnow().isoformat()
        }))

    def log_error(self, event_id, error):
        self.logger.error(json.dumps({
            'action': 'webhook_error',
            'event_id': event_id,
            'error': str(error),
            'error_type': type(error).__name__,
            'timestamp': datetime.utcnow().isoformat()
        }))

webhook_logger = WebhookLogger()
```

### Metrics Collection

```python
from dataclasses import dataclass, field
from collections import defaultdict
import time

@dataclass
class WebhookMetrics:
    total_received: int = 0
    total_processed: int = 0
    total_failed: int = 0
    processing_times: list = field(default_factory=list)
    events_by_type: dict = field(default_factory=lambda: defaultdict(int))

    def record_received(self, event_type):
        self.total_received += 1
        self.events_by_type[event_type] += 1

    def record_processed(self, duration_ms):
        self.total_processed += 1
        self.processing_times.append(duration_ms)

    def record_failed(self):
        self.total_failed += 1

    def get_stats(self):
        avg_time = sum(self.processing_times) / len(self.processing_times) if self.processing_times else 0

        return {
            'total_received': self.total_received,
            'total_processed': self.total_processed,
            'total_failed': self.total_failed,
            'success_rate': self.total_processed / self.total_received if self.total_received else 0,
            'avg_processing_time_ms': avg_time,
            'events_by_type': dict(self.events_by_type)
        }

metrics = WebhookMetrics()

# Expose metrics endpoint
@webhooks_ns.route('/metrics')
class WebhookMetricsEndpoint(Resource):
    def get(self):
        """Get webhook processing metrics"""
        return metrics.get_stats()
```
