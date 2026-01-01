"""
Basic Flask-RESTX Webhook Application

A minimal example demonstrating:
- Flask-RESTX API setup with Swagger documentation
- Webhook endpoint with request validation
- Model-based payload definition
- Response marshalling
- Basic error handling

Usage:
    pip install flask flask-restx python-dotenv
    python basic-webhook.py

    # Test webhook
    curl -X POST http://localhost:5000/api/webhooks/receive \
        -H "Content-Type: application/json" \
        -d '{"event_type": "user.created", "timestamp": "2024-01-15T10:30:00Z", "data": {"user_id": "123"}}'

    # View Swagger docs
    Open http://localhost:5000/docs in browser
"""

from flask import Flask
from flask_restx import Api, Namespace, Resource, fields
from datetime import datetime
import logging
import uuid

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
app.config['RESTX_VALIDATE'] = True  # Enable global validation

# Create API with Swagger documentation
api = Api(
    app,
    version='1.0.0',
    title='Webhook Receiver API',
    description='Simple webhook receiver with Flask-RESTX',
    doc='/docs',
    prefix='/api'
)

# Create webhooks namespace
webhooks_ns = Namespace(
    'webhooks',
    description='Webhook receiving endpoints'
)

# =============================================================================
# Model Definitions
# =============================================================================

# Incoming webhook payload model
webhook_payload = webhooks_ns.model('WebhookPayload', {
    'event_type': fields.String(
        required=True,
        description='Type of event (e.g., user.created, order.placed)',
        example='user.created'
    ),
    'timestamp': fields.DateTime(
        required=True,
        description='When the event occurred (ISO 8601)',
        example='2024-01-15T10:30:00Z'
    ),
    'data': fields.Raw(
        required=True,
        description='Event-specific payload data',
        example={'user_id': '12345', 'email': 'user@example.com'}
    ),
    'metadata': fields.Raw(
        required=False,
        description='Optional metadata about the event',
        example={'source': 'api', 'version': '2.0'}
    )
})

# Response model for successful processing
webhook_response = webhooks_ns.model('WebhookResponse', {
    'status': fields.String(
        description='Processing status',
        example='received'
    ),
    'event_id': fields.String(
        description='Assigned event ID for tracking',
        example='evt_abc123'
    ),
    'message': fields.String(
        description='Human-readable message',
        example='Webhook received successfully'
    ),
    'processed_at': fields.DateTime(
        description='When the webhook was processed'
    )
})

# Error response model
error_response = webhooks_ns.model('ErrorResponse', {
    'error': fields.String(description='Error type'),
    'message': fields.String(description='Error description'),
    'details': fields.Raw(description='Additional error details')
})

# =============================================================================
# Event Handlers
# =============================================================================

def handle_user_created(data):
    """Handle user.created events"""
    user_id = data.get('user_id')
    email = data.get('email')
    logger.info(f"New user created: {user_id} ({email})")
    return {'action': 'user_welcomed', 'user_id': user_id}


def handle_user_updated(data):
    """Handle user.updated events"""
    user_id = data.get('user_id')
    logger.info(f"User updated: {user_id}")
    return {'action': 'user_synced', 'user_id': user_id}


def handle_order_placed(data):
    """Handle order.placed events"""
    order_id = data.get('order_id')
    total = data.get('total', 0)
    logger.info(f"Order placed: {order_id} (${total})")
    return {'action': 'order_confirmed', 'order_id': order_id}


# Event handler registry
EVENT_HANDLERS = {
    'user.created': handle_user_created,
    'user.updated': handle_user_updated,
    'order.placed': handle_order_placed,
}

# =============================================================================
# Webhook Endpoints
# =============================================================================

@webhooks_ns.route('/receive')
class WebhookReceiver(Resource):
    """Main webhook receiving endpoint"""

    @webhooks_ns.expect(webhook_payload, validate=True)
    @webhooks_ns.marshal_with(webhook_response, code=200)
    @webhooks_ns.response(400, 'Invalid payload', error_response)
    @webhooks_ns.response(422, 'Validation error', error_response)
    @webhooks_ns.doc(
        description='''
        Receive and process webhook events.

        Supported event types:
        - `user.created` - New user registration
        - `user.updated` - User profile update
        - `order.placed` - New order placed

        The endpoint validates the payload structure and routes
        to the appropriate handler based on event_type.
        '''
    )
    def post(self):
        """Receive a webhook event"""
        payload = webhooks_ns.payload
        event_type = payload['event_type']
        data = payload['data']

        # Generate event ID
        event_id = f"evt_{uuid.uuid4().hex[:12]}"

        logger.info(f"Received webhook: {event_type} ({event_id})")

        # Find and execute handler
        handler = EVENT_HANDLERS.get(event_type)

        if handler:
            try:
                result = handler(data)
                logger.info(f"Webhook processed: {event_id} -> {result}")
            except Exception as e:
                logger.error(f"Handler error for {event_id}: {e}")
                # Still acknowledge receipt
        else:
            logger.warning(f"No handler for event type: {event_type}")

        return {
            'status': 'received',
            'event_id': event_id,
            'message': f'Webhook {event_type} received successfully',
            'processed_at': datetime.utcnow()
        }


@webhooks_ns.route('/events')
class SupportedEvents(Resource):
    """List supported webhook event types"""

    @webhooks_ns.doc(description='Get list of supported event types')
    def get(self):
        """List all supported event types"""
        return {
            'supported_events': list(EVENT_HANDLERS.keys()),
            'count': len(EVENT_HANDLERS)
        }


# =============================================================================
# Error Handlers
# =============================================================================

@api.errorhandler(Exception)
def handle_exception(error):
    """Global error handler"""
    logger.error(f"Unhandled exception: {error}")
    return {
        'error': 'internal_error',
        'message': str(error)
    }, 500


@webhooks_ns.errorhandler
def handle_namespace_error(error):
    """Namespace-specific error handler"""
    return {
        'error': 'webhook_error',
        'message': str(error)
    }, getattr(error, 'code', 400)


# =============================================================================
# Register Namespace and Run
# =============================================================================

api.add_namespace(webhooks_ns, path='/webhooks')


# Health check endpoint
@app.route('/health')
def health():
    """Health check endpoint"""
    return {'status': 'healthy', 'timestamp': datetime.utcnow().isoformat()}


if __name__ == '__main__':
    print("\n" + "="*60)
    print("Flask-RESTX Webhook Server")
    print("="*60)
    print(f"  Swagger UI:  http://localhost:5000/docs")
    print(f"  Webhook URL: http://localhost:5000/api/webhooks/receive")
    print(f"  Health:      http://localhost:5000/health")
    print("="*60 + "\n")

    app.run(host='0.0.0.0', port=5000, debug=True)
