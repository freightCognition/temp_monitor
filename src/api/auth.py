import functools
import logging
from flask import request, abort, jsonify

import sys
import os
# Add project root to sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.utils.config import config # Import the global AppConfig instance

logger = logging.getLogger(__name__)

def require_token(f):
    """Decorator to require bearer token authentication for API endpoints."""
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')

        if not config.BEARER_TOKEN:
            logger.critical("API call attempted but BEARER_TOKEN is not configured on the server.")
            abort(500, description="Server configuration error: Authentication mechanism not properly set up.")

        if not auth_header or not auth_header.startswith('Bearer '):
            logger.warning(f"API access attempt without valid Authorization header from {request.remote_addr}")
            abort(401, description="Authorization header with Bearer token required.")

        token = auth_header.split(' ')[1]
        if token != config.BEARER_TOKEN:
            logger.warning(f"API access attempt with invalid token from {request.remote_addr}")
            abort(403, description="Invalid bearer token.")

        return f(*args, **kwargs)
    return decorated_function

# Note: Token generation and saving to .env is complex to do directly from here
# as it requires modifying the .env file which might be outside the app's typical write permissions
# and also needs to update the 'config' object in real-time or require a restart.
# The original script updated a global variable and wrote to .env.
# For a more robust solution, token management might be handled by an admin script
# or a dedicated settings page that can trigger a config reload.
# For now, we'll keep a simplified version of token verification.
# The generation part from the original script is harder to port directly into a stateless API call
# without more infrastructure for config updates.

def setup_auth_routes(app):
    """Sets up authentication related routes, e.g., for token verification."""

    @app.route('/api/verify-token', methods=['GET'])
    @require_token
    def verify_token_route():
        """Verify if the provided token is valid."""
        return jsonify({'valid': True, 'message': 'Token is valid'}), 200

    # The /api/generate-token endpoint from the original script is problematic because:
    # 1. It modifies the .env file, which might not be writable by the web server user.
    # 2. It modifies a global variable (BEARER_TOKEN) in the running process.
    #    This change might not propagate correctly in multi-worker setups (like Gunicorn).
    #    The  object would need to be reloaded.
    # A better approach for token rotation would be an out-of-band script or a CLI command.
    # For this refactor, we will omit the /api/generate-token endpoint.
    # Token generation should be handled via  or manually.
    logger.info("Auth routes (verify-token) initialized.")
    # If generate_token.py is kept, it should be the primary way to generate tokens.
