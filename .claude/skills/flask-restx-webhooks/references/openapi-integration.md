# OpenAPI Integration with Flask-RESTX

This reference covers advanced OpenAPI configuration, customization, and best practices for Flask-RESTX applications.

## OpenAPI Specification Overview

Flask-RESTX generates OpenAPI 2.0 (Swagger) specifications automatically. The specification includes:

- API metadata (title, version, description)
- Endpoints with methods and parameters
- Request/response models
- Authentication schemes
- Error responses

## API Configuration

### Basic API Setup

```python
from flask import Flask
from flask_restx import Api

app = Flask(__name__)

api = Api(
    app,
    version='1.0.0',
    title='My API',
    description='A comprehensive API description',
    terms_url='https://example.com/terms',
    license='MIT',
    license_url='https://opensource.org/licenses/MIT',
    contact='api-support@example.com',
    contact_url='https://example.com/support',
    contact_email='api@example.com',
    doc='/docs',  # Swagger UI path
    prefix='/api/v1',  # API prefix
    default='main',  # Default namespace name
    default_label='Main operations',  # Default namespace description
    validate=True,  # Enable validation globally
    ordered=True,  # Order operations by method
    authorizations=None,  # Security definitions (see below)
    security=None,  # Default security requirement
    default_mediatype='application/json'
)
```

### Custom Swagger UI Path

```python
# Disable Swagger UI
api = Api(app, doc=False)

# Custom path
api = Api(app, doc='/api-docs')

# Multiple documentation endpoints
@app.route('/swagger.json')
def swagger_json():
    return api.__schema__

@app.route('/openapi.yaml')
def openapi_yaml():
    import yaml
    return yaml.dump(api.__schema__)
```

## Authentication and Authorization

### API Key Authentication

```python
authorizations = {
    'apikey': {
        'type': 'apiKey',
        'in': 'header',
        'name': 'X-API-Key',
        'description': 'API key for authentication'
    }
}

api = Api(
    app,
    authorizations=authorizations,
    security='apikey'  # Apply to all endpoints by default
)
```

### Bearer Token Authentication

```python
authorizations = {
    'bearer': {
        'type': 'apiKey',
        'in': 'header',
        'name': 'Authorization',
        'description': 'Bearer token. Format: "Bearer {token}"'
    }
}

api = Api(app, authorizations=authorizations)

# Apply to specific endpoint
@ns.route('/protected')
class ProtectedResource(Resource):
    @ns.doc(security='bearer')
    def get(self):
        """Protected endpoint requiring bearer token"""
        return {'message': 'Authenticated'}
```

### Multiple Authentication Schemes

```python
authorizations = {
    'apikey': {
        'type': 'apiKey',
        'in': 'header',
        'name': 'X-API-Key'
    },
    'oauth2': {
        'type': 'oauth2',
        'flow': 'accessCode',
        'tokenUrl': 'https://auth.example.com/token',
        'authorizationUrl': 'https://auth.example.com/authorize',
        'scopes': {
            'read': 'Read access',
            'write': 'Write access',
            'admin': 'Admin access'
        }
    },
    'webhook_signature': {
        'type': 'apiKey',
        'in': 'header',
        'name': 'X-Webhook-Signature',
        'description': 'HMAC-SHA256 signature of request body'
    }
}

api = Api(app, authorizations=authorizations)

# Require specific auth for endpoint
@ns.route('/admin')
class AdminResource(Resource):
    @ns.doc(security=[{'oauth2': ['admin']}])
    def get(self):
        """Admin-only endpoint"""
        pass
```

## Model Definitions

### Basic Models

```python
from flask_restx import fields

# Simple model
user_model = api.model('User', {
    'id': fields.Integer(readonly=True, description='User ID'),
    'username': fields.String(required=True, min_length=3, max_length=50),
    'email': fields.String(required=True, pattern=r'^[\w\.-]+@[\w\.-]+\.\w+$'),
    'role': fields.String(enum=['user', 'admin', 'moderator']),
    'created_at': fields.DateTime(readonly=True)
})
```

### Nested Models

```python
# Address model
address_model = api.model('Address', {
    'street': fields.String(required=True),
    'city': fields.String(required=True),
    'country': fields.String(required=True),
    'postal_code': fields.String()
})

# User with nested address
user_with_address = api.model('UserWithAddress', {
    'id': fields.Integer(readonly=True),
    'username': fields.String(required=True),
    'address': fields.Nested(address_model)
})

# User with list of addresses
user_multi_address = api.model('UserMultiAddress', {
    'id': fields.Integer(readonly=True),
    'username': fields.String(required=True),
    'addresses': fields.List(fields.Nested(address_model))
})
```

### Model Inheritance

```python
# Base model
base_model = api.model('Base', {
    'id': fields.Integer(readonly=True),
    'created_at': fields.DateTime(readonly=True),
    'updated_at': fields.DateTime(readonly=True)
})

# Extended model using inheritance
user_model = api.inherit('User', base_model, {
    'username': fields.String(required=True),
    'email': fields.String(required=True)
})

# Another extension
admin_model = api.inherit('Admin', user_model, {
    'permissions': fields.List(fields.String),
    'department': fields.String()
})
```

### Polymorphic Models

```python
# Base event model
base_event = api.model('BaseEvent', {
    'event_type': fields.String(required=True, discriminator=True),
    'timestamp': fields.DateTime(required=True)
})

# User event
user_event = api.inherit('UserEvent', base_event, {
    'user_id': fields.String(required=True),
    'action': fields.String(enum=['login', 'logout', 'register'])
})

# Order event
order_event = api.inherit('OrderEvent', base_event, {
    'order_id': fields.String(required=True),
    'total': fields.Float(),
    'items': fields.List(fields.Raw)
})
```

## Field Types and Validation

### String Fields

```python
string_examples = api.model('StringExamples', {
    # Basic string
    'name': fields.String(description='User name'),

    # Required with length constraints
    'username': fields.String(
        required=True,
        min_length=3,
        max_length=20,
        description='Username (3-20 characters)'
    ),

    # Enum values
    'status': fields.String(
        enum=['active', 'inactive', 'pending'],
        default='pending'
    ),

    # Pattern validation (regex)
    'email': fields.String(
        pattern=r'^[\w\.-]+@[\w\.-]+\.\w+$',
        example='user@example.com'
    ),

    # With example
    'phone': fields.String(
        example='+1-555-123-4567',
        description='Phone number in international format'
    )
})
```

### Numeric Fields

```python
numeric_examples = api.model('NumericExamples', {
    # Integer with range
    'age': fields.Integer(
        min=0,
        max=150,
        description='Age in years'
    ),

    # Float with constraints
    'price': fields.Float(
        min=0.0,
        description='Price in dollars'
    ),

    # Fixed precision decimal
    'amount': fields.Fixed(
        decimals=2,
        description='Monetary amount'
    ),

    # Arbitrary precision
    'scientific': fields.Arbitrary(
        description='Scientific notation number'
    )
})
```

### Date and Time Fields

```python
datetime_examples = api.model('DateTimeExamples', {
    # ISO 8601 datetime
    'created_at': fields.DateTime(
        description='Creation timestamp (ISO 8601)',
        example='2024-01-15T10:30:00Z'
    ),

    # Date only
    'birth_date': fields.Date(
        description='Birth date',
        example='1990-05-20'
    )
})
```

### Complex Fields

```python
complex_examples = api.model('ComplexExamples', {
    # List of strings
    'tags': fields.List(
        fields.String,
        description='List of tags'
    ),

    # List of nested objects
    'items': fields.List(
        fields.Nested(item_model),
        description='Order items'
    ),

    # Raw JSON (any structure)
    'metadata': fields.Raw(
        description='Arbitrary JSON metadata'
    ),

    # URL field
    'website': fields.Url(
        description='Website URL'
    ),

    # Boolean
    'is_active': fields.Boolean(
        default=True,
        description='Whether user is active'
    ),

    # Wildcard (any fields)
    'extra': fields.Wildcard(fields.String)
})
```

## Endpoint Documentation

### Route Documentation

```python
@ns.route('/users/<int:user_id>')
@ns.param('user_id', 'The user identifier', _in='path')
class UserResource(Resource):

    @ns.doc(
        description='Retrieve a user by ID',
        responses={
            200: 'Success',
            404: 'User not found',
            500: 'Internal server error'
        },
        params={
            'user_id': 'The unique user identifier'
        }
    )
    @ns.marshal_with(user_model)
    def get(self, user_id):
        """Get a specific user

        Returns the user details for the given ID.
        """
        return get_user(user_id)

    @ns.doc(
        description='Update a user',
        responses={
            200: 'User updated',
            400: 'Validation error',
            404: 'User not found'
        }
    )
    @ns.expect(user_update_model, validate=True)
    @ns.marshal_with(user_model)
    def put(self, user_id):
        """Update a user

        Updates the user with the provided data.
        """
        return update_user(user_id, ns.payload)

    @ns.doc(
        description='Delete a user',
        responses={
            204: 'User deleted',
            404: 'User not found'
        }
    )
    @ns.response(204, 'User deleted')
    def delete(self, user_id):
        """Delete a user

        Permanently removes the user.
        """
        delete_user(user_id)
        return '', 204
```

### Query Parameters

```python
from flask_restx import reqparse

# Define parser
user_parser = reqparse.RequestParser()
user_parser.add_argument(
    'page',
    type=int,
    default=1,
    help='Page number',
    location='args'
)
user_parser.add_argument(
    'per_page',
    type=int,
    default=20,
    choices=[10, 20, 50, 100],
    help='Items per page',
    location='args'
)
user_parser.add_argument(
    'search',
    type=str,
    help='Search term',
    location='args'
)
user_parser.add_argument(
    'status',
    type=str,
    action='append',  # Allow multiple values
    help='Filter by status',
    location='args'
)

@ns.route('/users')
class UserList(Resource):
    @ns.expect(user_parser)
    @ns.marshal_list_with(user_model)
    def get(self):
        """List users with pagination and filtering"""
        args = user_parser.parse_args()
        return get_users(
            page=args['page'],
            per_page=args['per_page'],
            search=args['search'],
            status=args['status']
        )
```

### Header Parameters

```python
header_parser = reqparse.RequestParser()
header_parser.add_argument(
    'X-Request-ID',
    type=str,
    location='headers',
    required=False,
    help='Request tracking ID'
)
header_parser.add_argument(
    'Accept-Language',
    type=str,
    location='headers',
    default='en',
    help='Preferred language'
)

@ns.route('/data')
class DataResource(Resource):
    @ns.expect(header_parser)
    def get(self):
        args = header_parser.parse_args()
        request_id = args.get('X-Request-ID')
        lang = args.get('Accept-Language')
        # Process with headers...
```

## Response Documentation

### Standard Responses

```python
# Define response models
error_model = api.model('Error', {
    'error': fields.String(description='Error message'),
    'code': fields.String(description='Error code'),
    'details': fields.Raw(description='Additional error details')
})

pagination_model = api.model('Pagination', {
    'page': fields.Integer(description='Current page'),
    'per_page': fields.Integer(description='Items per page'),
    'total': fields.Integer(description='Total items'),
    'pages': fields.Integer(description='Total pages')
})

# Paginated response wrapper
def paginated_model(name, item_model):
    return api.model(f'Paginated{name}', {
        'items': fields.List(fields.Nested(item_model)),
        'pagination': fields.Nested(pagination_model)
    })

user_list_model = paginated_model('Users', user_model)

@ns.route('/users')
class UserList(Resource):
    @ns.marshal_with(user_list_model)
    @ns.response(200, 'Success', user_list_model)
    @ns.response(400, 'Bad request', error_model)
    @ns.response(401, 'Unauthorized', error_model)
    def get(self):
        """List all users with pagination"""
        pass
```

### Envelope Pattern

```python
# Response envelope
def create_envelope(name, data_model):
    return api.model(f'{name}Response', {
        'success': fields.Boolean(default=True),
        'data': fields.Nested(data_model),
        'meta': fields.Raw(description='Response metadata'),
        'timestamp': fields.DateTime()
    })

user_response = create_envelope('User', user_model)

@ns.route('/users/<int:id>')
class UserResource(Resource):
    @ns.marshal_with(user_response)
    def get(self, id):
        user = get_user(id)
        return {
            'success': True,
            'data': user,
            'meta': {'version': '1.0'},
            'timestamp': datetime.utcnow()
        }
```

## Namespace Organization

### Modular API Structure

```python
# api/__init__.py
from flask_restx import Api

api = Api(
    title='My API',
    version='1.0',
    description='Modular API with namespaces'
)

# Import and register namespaces
from .users import ns as users_ns
from .webhooks import ns as webhooks_ns
from .admin import ns as admin_ns

api.add_namespace(users_ns, path='/users')
api.add_namespace(webhooks_ns, path='/webhooks')
api.add_namespace(admin_ns, path='/admin')
```

```python
# api/users.py
from flask_restx import Namespace, Resource, fields

ns = Namespace('users', description='User operations')

user_model = ns.model('User', {
    'id': fields.Integer(),
    'username': fields.String(required=True)
})

@ns.route('/')
class UserList(Resource):
    @ns.marshal_list_with(user_model)
    def get(self):
        """List all users"""
        pass

    @ns.expect(user_model)
    @ns.marshal_with(user_model, code=201)
    def post(self):
        """Create a new user"""
        pass
```

### Cross-Namespace Model Sharing

```python
# api/models.py - Shared models
from flask_restx import fields

def register_shared_models(api):
    """Register models that are shared across namespaces"""

    api.models['Timestamp'] = api.model('Timestamp', {
        'created_at': fields.DateTime(),
        'updated_at': fields.DateTime()
    })

    api.models['Error'] = api.model('Error', {
        'error': fields.String(),
        'message': fields.String()
    })

# In namespace files, reference shared models
@ns.route('/resource')
class MyResource(Resource):
    @ns.response(400, 'Bad Request', api.models['Error'])
    def get(self):
        pass
```

## Exporting OpenAPI Specification

### JSON Export

```python
@app.route('/openapi.json')
def openapi_json():
    """Export OpenAPI specification as JSON"""
    return api.__schema__

# Or with custom modifications
@app.route('/openapi-custom.json')
def openapi_custom():
    schema = dict(api.__schema__)

    # Add custom extensions
    schema['x-custom-field'] = 'custom value'

    # Modify info
    schema['info']['x-logo'] = {
        'url': 'https://example.com/logo.png'
    }

    return schema
```

### YAML Export

```python
import yaml

@app.route('/openapi.yaml')
def openapi_yaml():
    """Export OpenAPI specification as YAML"""
    schema = api.__schema__
    return yaml.dump(schema, default_flow_style=False)
```

### File Export (CLI)

```python
# export_openapi.py
import json
import yaml
from app import create_app

def export_openapi(format='json', output_file=None):
    app = create_app()

    with app.app_context():
        from app.api import api
        schema = api.__schema__

        if format == 'yaml':
            content = yaml.dump(schema, default_flow_style=False)
        else:
            content = json.dumps(schema, indent=2)

        if output_file:
            with open(output_file, 'w') as f:
                f.write(content)
            print(f'OpenAPI spec exported to {output_file}')
        else:
            print(content)

if __name__ == '__main__':
    import sys
    fmt = sys.argv[1] if len(sys.argv) > 1 else 'json'
    out = sys.argv[2] if len(sys.argv) > 2 else None
    export_openapi(fmt, out)
```

## Swagger UI Customization

### Custom UI Settings

```python
api = Api(
    app,
    doc='/docs',
    # Swagger UI configuration
    config={
        'deepLinking': True,
        'displayOperationId': True,
        'defaultModelsExpandDepth': 3,
        'defaultModelExpandDepth': 3,
        'defaultModelRendering': 'model',
        'displayRequestDuration': True,
        'docExpansion': 'list',
        'filter': True,
        'showExtensions': True,
        'showCommonExtensions': True,
        'supportedSubmitMethods': ['get', 'post', 'put', 'delete', 'patch'],
        'validatorUrl': None
    }
)
```

### Custom CSS and JavaScript

```python
# Serve custom Swagger UI assets
@app.route('/docs/custom.css')
def custom_swagger_css():
    return '''
    .swagger-ui .topbar { display: none }
    .swagger-ui .info .title { color: #333 }
    ''', 200, {'Content-Type': 'text/css'}

# Add to API
api = Api(
    app,
    doc='/docs',
    # Reference custom CSS
)
```

## Best Practices

### Versioning

```python
# Version in URL
api_v1 = Api(app, version='1.0', prefix='/api/v1')
api_v2 = Api(app, version='2.0', prefix='/api/v2')

# Or version in header
@ns.route('/resource')
class VersionedResource(Resource):
    @ns.doc(params={'X-API-Version': 'API version (1 or 2)'})
    def get(self):
        version = request.headers.get('X-API-Version', '1')
        if version == '2':
            return self._v2_response()
        return self._v1_response()
```

### Deprecation

```python
@ns.route('/old-endpoint')
@ns.deprecated
class DeprecatedResource(Resource):
    @ns.doc(description='**DEPRECATED**: Use /new-endpoint instead')
    def get(self):
        """This endpoint is deprecated"""
        pass
```

### Tags and Organization

```python
# Group operations with tags
@ns.route('/resource')
class MyResource(Resource):
    @ns.doc(tags=['operations', 'crud'])
    def get(self):
        pass
```

### Documentation Best Practices

1. **Use descriptive operation IDs**: Flask-RESTX auto-generates these, but you can customize
2. **Provide examples**: Use the `example` parameter in fields
3. **Document all responses**: Include error responses
4. **Use markdown in descriptions**: Swagger UI renders markdown
5. **Keep models DRY**: Use inheritance and references
6. **Validate on input**: Always use `validate=True` with `@expect`
