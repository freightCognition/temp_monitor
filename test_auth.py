#!/usr/bin/env python3
"""
Tests for S8/S9: require_token() defects.

(a) token != BEARER_TOKEN was a plain string compare -- a timing oracle,
    and /api/verify-token is a free endpoint to exercise it against.
    Fix: hmac.compare_digest.
(b) auth_header.split(' ')[1] only looked at the second whitespace field,
    so "Bearer <token> junkjunk" was accepted (verified: 200). Fix: reject
    any Authorization header that isn't exactly "Bearer <token>".
(c) a wrong token returned 403 instead of 401 + WWW-Authenticate, so
    clients that retry-on-401 never retried. Fix: 401 for both missing and
    invalid tokens.
(d) abort() on the plain-Flask routes returned an HTML error body while
    the RESTX routes returned JSON. Fix: JSON everywhere.

NEAR-MISS THAT ALMOST SHIPPED (see TestAuthMatrixAcrossAllProtectedEndpoints
below): an earlier version of the (d) fix had require_token() RETURN a
jsonify() Response instead of raising. That works for plain @app.route()
views, but require_token also wraps Flask-RESTX Resource methods, and
RESTX's outer @marshal_with(...) decorator does not recognize a plain
Response -- it treated the 401 Response as return *data* and marshaled it
against the success schema, emitting 200 with every field null. That is a
full authentication bypass on every RESTX-backed endpoint (including PUT
/api/webhook/config, which rewrites the Slack webhook URL and alert
thresholds). The fix is to keep raising via abort(), which propagates
through the decorator stack untouched, and use a Flask-level
@app.errorhandler(401) to format the JSON body instead.
"""
import json
import os
import sys
import unittest
from unittest.mock import MagicMock

sys.modules['sense_hat'] = MagicMock()

import temp_monitor  # noqa: E402


class TestRequireTokenAuth(unittest.TestCase):
    def setUp(self):
        temp_monitor.app.config['TESTING'] = True
        self.client = temp_monitor.app.test_client()
        self.token = os.getenv('BEARER_TOKEN', 'test_token_ci')

    def test_trailing_garbage_after_token_is_rejected(self):
        """S8(b): 'Bearer <token> junkjunk' must NOT authenticate."""
        response = self.client.get(
            '/api/temp',
            headers={'Authorization': f'Bearer {self.token} junkjunk'}
        )
        self.assertEqual(response.status_code, 401)

    def test_valid_token_alone_is_accepted(self):
        response = self.client.get(
            '/api/temp',
            headers={'Authorization': f'Bearer {self.token}'}
        )
        self.assertEqual(response.status_code, 200)

    def test_wrong_token_returns_401_not_403(self):
        """S8(c): clients that retry-on-401 must see 401 for a bad token."""
        response = self.client.get(
            '/api/temp',
            headers={'Authorization': 'Bearer wrong_token_xyz'}
        )
        self.assertEqual(response.status_code, 401)
        self.assertIn('WWW-Authenticate', response.headers)

    def test_missing_auth_header_returns_401(self):
        response = self.client.get('/api/temp')
        self.assertEqual(response.status_code, 401)
        self.assertIn('WWW-Authenticate', response.headers)

    def test_unauthenticated_error_body_is_json_not_html(self):
        """S8(d): plain-Flask routes must return JSON like the RESTX ones."""
        response = self.client.get('/api/temp')
        self.assertEqual(response.content_type, 'application/json')
        data = response.get_json()
        self.assertIsNotNone(data)
        self.assertIn('error', data)

    def test_wrong_token_error_body_is_json(self):
        response = self.client.get(
            '/api/temp',
            headers={'Authorization': 'Bearer wrong_token_xyz'}
        )
        self.assertEqual(response.content_type, 'application/json')
        data = response.get_json()
        self.assertIsNotNone(data)
        self.assertIn('error', data)

    def test_uses_constant_time_comparison(self):
        """S8(a): guard against a plain == regression sneaking back in."""
        import inspect
        source = inspect.getsource(temp_monitor.require_token)
        self.assertIn('hmac.compare_digest', source)
        self.assertNotRegex(
            source, r'token\s*!=\s*BEARER_TOKEN',
            "require_token should not use a plain != comparison on the token"
        )

    def test_require_token_raises_rather_than_returns(self):
        """Guard against the near-miss described in the module docstring:
        require_token must raise (abort) on rejection, not return a
        Response, or RESTX's marshal_with will swallow it into a 200."""
        import inspect
        source = inspect.getsource(temp_monitor.require_token)
        self.assertNotIn(
            'return jsonify', source,
            "require_token must not return a Response on rejection -- "
            "marshal_with silently swallows it into a 200 (auth bypass)"
        )
        self.assertIn('abort(401', source)


class TestAuthMatrixAcrossAllProtectedEndpoints(unittest.TestCase):
    """Mandatory regression test, added after an auth-bypass near-miss
    (see module docstring): require_token() briefly RETURNED its 401
    response instead of raising, which flask_restx's @marshal_with()
    silently swallowed on every RESTX-backed route, turning unauthenticated
    and wrong-token requests into 200s with null bodies -- including on PUT
    /api/webhook/config, which rewrites the Slack webhook URL and alert
    thresholds, on a service reachable over a public tunnel.

    Iterates over every protected endpoint (both plain-Flask and
    RESTX-backed) rather than hardcoding one, so a newly added route or a
    decorator-stack change can never again ship without auth enforcement
    unnoticed.
    """

    PROTECTED_ENDPOINTS = [
        ('GET', '/api/temp', {}),
        ('GET', '/api/raw', {}),
        ('GET', '/api/verify-token', {}),
        ('GET', '/api/webhook/config', {}),
        ('PUT', '/api/webhook/config', {
            'data': json.dumps({'webhook': {'url': 'https://hooks.slack.com/test'}}),
            'content_type': 'application/json',
        }),
        ('POST', '/api/webhook/test', {}),
        ('POST', '/api/webhook/enable', {}),
        ('POST', '/api/webhook/disable', {}),
        ('GET', '/metrics', {}),
    ]

    def setUp(self):
        temp_monitor.app.config['TESTING'] = True
        self.client = temp_monitor.app.test_client()
        self.token = os.getenv('BEARER_TOKEN', 'test_token_ci')
        # /api/raw calls sense.get_temperature() directly; give it a real
        # float so a valid-token request doesn't 500 for unrelated reasons.
        self._orig_get_temperature = temp_monitor.sense.get_temperature
        temp_monitor.sense.get_temperature = MagicMock(return_value=20.0)

    def tearDown(self):
        temp_monitor.sense.get_temperature = self._orig_get_temperature

    def test_every_protected_endpoint_enforces_auth(self):
        failures = []
        for method, path, extra_kwargs in self.PROTECTED_ENDPOINTS:
            call = getattr(self.client, method.lower())

            no_auth = call(path, **extra_kwargs)
            wrong = call(path, headers={'Authorization': 'Bearer wrong_token'}, **extra_kwargs)
            valid = call(path, headers={'Authorization': f'Bearer {self.token}'}, **extra_kwargs)

            if no_auth.status_code != 401:
                failures.append(f"{method} {path}: no-auth header returned {no_auth.status_code}, expected 401")
            if wrong.status_code != 401:
                failures.append(f"{method} {path}: wrong token returned {wrong.status_code}, expected 401")
            if valid.status_code == 401:
                failures.append(f"{method} {path}: valid token was rejected with 401")

        self.assertEqual(failures, [], "\n" + "\n".join(failures))


if __name__ == '__main__':
    unittest.main()
