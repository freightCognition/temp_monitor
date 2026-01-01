# Flask-RESTX API Plugin

Expert guidance for building Flask-RESTX APIs with webhooks, OpenAPI documentation, and security best practices.

## Overview

This Claude Code plugin provides comprehensive knowledge and patterns for:

- **Flask-RESTX APIs** - Building RESTful APIs with automatic Swagger documentation
- **Webhook Endpoints** - Implementing secure webhook receivers with signature verification
- **OpenAPI Specification** - Generating and customizing OpenAPI/Swagger documentation
- **Security Patterns** - HMAC signature verification, rate limiting, input validation
- **Request Validation** - Model-based request/response validation with Flask-RESTX

## Installation

### Local Installation

1. Copy this plugin to your Claude Code plugins directory:
```bash
cp -r flask-restx-api ~/.claude/plugins/local/
```

2. Restart Claude Code or reload plugins

### Verify Installation

The skill will activate automatically when you ask Claude about Flask-RESTX, webhooks, or OpenAPI topics.

## Skills Included

### flask-restx-webhooks

Expert guidance for Flask-RESTX webhook implementations and OpenAPI documentation.

**Triggers when you ask about:**
- Creating webhook endpoints
- Implementing HMAC signature verification
- Configuring Flask-RESTX APIs
- Generating OpenAPI/Swagger documentation
- Validating webhook payloads
- Securing webhook endpoints

## Usage Examples

### Basic Webhook Implementation

```
Ask Claude: "Help me create a Flask-RESTX webhook endpoint with request validation"
```

Claude will provide:
- Complete Flask-RESTX setup
- Model definitions for request/response
- Webhook endpoint with validation
- Automatic Swagger documentation

### Secure Webhook with Signature Verification

```
Ask Claude: "Add HMAC signature verification to my webhook endpoint"
```

Claude will implement:
- HMAC-SHA256 signature verification
- Timestamp validation for replay protection
- Decorator-based security
- Provider-specific patterns (GitHub, Stripe, Slack)

### OpenAPI Documentation

```
Ask Claude: "Generate OpenAPI documentation for my Flask API"
```

Claude will show you:
- Flask-RESTX API configuration
- Model definitions and validation
- Authentication schemes in OpenAPI
- Customizing Swagger UI

## What's Included

### Reference Documentation

Detailed guides in `skills/flask-restx-webhooks/references/`:

- **webhook-patterns.md** - Common webhook implementation patterns
  - Event routing strategies
  - Idempotency patterns
  - Async processing
  - Retry and error handling
  - Testing approaches

- **openapi-integration.md** - OpenAPI/Swagger documentation
  - API configuration
  - Model definitions
  - Authentication schemes
  - Namespace organization
  - Exporting specifications

- **security-best-practices.md** - Security patterns
  - HMAC signature verification
  - Rate limiting implementations
  - IP allowlisting
  - Input validation and sanitization
  - Logging and auditing

### Working Examples

Complete, runnable code in `skills/flask-restx-webhooks/examples/`:

- **basic-webhook.py** - Simple webhook endpoint with Flask-RESTX
  - Model-based validation
  - Event routing
  - Swagger documentation
  - Error handling

- **webhook-with-signature.py** - Secure webhook with HMAC verification
  - Signature verification
  - Timestamp validation
  - Rate limiting
  - Security logging
  - Provider-specific patterns

- **test_webhook.py** - Test suite for webhook security
  - Signature generation
  - Security test cases
  - Rate limit testing

- **openapi-spec.yaml** - Complete OpenAPI 3.0 specification
  - Modern OpenAPI example
  - Webhook documentation
  - Security schemes
  - Request/response models

## Quick Start

### 1. Run the Basic Example

```bash
cd ~/.claude/plugins/local/flask-restx-api/skills/flask-restx-webhooks/examples
pip install flask flask-restx python-dotenv
python basic-webhook.py
```

Open http://localhost:5000/docs to see the Swagger UI.

### 2. Test Secure Webhooks

```bash
# Set up environment
echo "WEBHOOK_SECRET=$(python -c 'import secrets; print(secrets.token_hex(32))')" > .env

# Run secure webhook server
python webhook-with-signature.py

# In another terminal, run tests
python test_webhook.py
```

### 3. Ask Claude for Help

```
"Help me implement a webhook endpoint for Stripe payment events with signature verification"

"Show me how to add rate limiting to my Flask-RESTX webhook endpoints"

"Generate OpenAPI documentation for my webhook API"
```

## Features

### Automatic Swagger Documentation

Flask-RESTX automatically generates interactive API documentation:

- Request/response models
- Validation rules
- Authentication requirements
- Try-it-out functionality
- OpenAPI/Swagger JSON export

### Security Built-In

Security patterns included:

- HMAC-SHA256 signature verification
- Timestamp-based replay protection
- IP-based rate limiting
- Input sanitization
- Security event logging

### Provider Compatibility

Examples for common webhook providers:

- GitHub (X-Hub-Signature-256)
- Stripe (Stripe-Signature)
- Slack (X-Slack-Signature)
- Generic HMAC patterns

### Production-Ready Patterns

- Async webhook processing with queues
- Idempotency handling
- Dead letter queues
- Retry logic with backoff
- Structured logging
- Metrics collection

## Architecture

The skill uses progressive disclosure:

1. **SKILL.md** (1,800 words) - Core concepts loaded when skill triggers
2. **references/** - Detailed patterns loaded as needed by Claude
3. **examples/** - Complete working code for reference

This keeps Claude's context efficient while providing comprehensive knowledge.

## Requirements

### Python Packages

```bash
pip install flask>=2.0.0 flask-restx>=1.3.0 python-dotenv>=1.0.0
```

### Optional Packages

For advanced features:

```bash
# Rate limiting with Redis
pip install redis

# Task queues
pip install celery

# Additional security
pip install flask-talisman bleach
```

## Contributing

To extend this plugin:

1. Add new patterns to `references/` files
2. Create working examples in `examples/`
3. Update `SKILL.md` with references to new content
4. Test with Claude to verify triggering

## License

MIT License - See LICENSE file for details

## Support

For issues or questions:

- Check the examples in `skills/flask-restx-webhooks/examples/`
- Review reference docs in `skills/flask-restx-webhooks/references/`
- Ask Claude for help with specific Flask-RESTX questions

## Version History

### 1.0.0 (2025-01-15)

Initial release with:
- Flask-RESTX webhook skill
- Security best practices
- OpenAPI documentation guidance
- Working examples and tests
- Comprehensive reference documentation

---

Built for Claude Code - Making Flask-RESTX development easier and more secure.
