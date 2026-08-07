#!/usr/bin/env python3
"""
Tests for S12/S13: the root route was registered twice.

@app.route('/') -> index, AND Api(app, ...) unconditionally adds its own
'root' rule for '/' (flask_restx.Api._register_doc always calls
app.add_url_rule(self.prefix or "/", "root", self.render_root), which
404s). It only worked because the @app.route('/') decorator ran first and
werkzeug's rule sort is stable for identical static rules -- moving the
Api(...) construction above the route would silently 404 the whole
dashboard. Git history (commit 7f71fe0, "Fix waitress startup and root
route shadowing") shows this was already hit once as an ordering bug.

Fix: temp_monitor._DashboardSafeApi (a small Api subclass) overrides
_register_doc to skip only that one auto-root-rule registration, leaving
/docs and all namespace routes untouched. This makes the fix structural,
not ordering-dependent.

NOTE ON AN ABANDONED APPROACH: an earlier version of this fix gave Api() a
non-"/" `prefix=` instead, reasoning that self.prefix only affects the
auto-root rule. That reasoning was wrong and shipped a total outage:
flask_restx.Api.register_resource -> _register_view also prepends
self.prefix to every namespace resource URL (via _complete_url), so ALL
FOUR /api/webhook/* routes moved under the prefix and 404'd -- verified by
dumping the live url_map, which is exactly what
TestNoDocumentedRouteReturns404 below exists to catch automatically next
time.
"""
import json
import os
import sys
import unittest
from unittest.mock import MagicMock

sys.modules['sense_hat'] = MagicMock()

import temp_monitor  # noqa: E402


class TestDashboardRoute(unittest.TestCase):
    def setUp(self):
        temp_monitor.app.config['TESTING'] = True
        self.client = temp_monitor.app.test_client()
        self._orig_temp = temp_monitor.current_temp
        self._orig_humidity = temp_monitor.current_humidity

    def tearDown(self):
        temp_monitor.current_temp = self._orig_temp
        temp_monitor.current_humidity = self._orig_humidity

    def test_root_returns_200_and_shows_temperature(self):
        temp_monitor.current_temp = 21.5
        temp_monitor.current_humidity = 44.0

        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn('21.5', body)

    def test_root_has_exactly_one_url_rule(self):
        root_rules = [r for r in temp_monitor.app.url_map.iter_rules() if r.rule == '/']
        self.assertEqual(len(root_rules), 1, f"expected exactly one rule for '/', found {root_rules}")
        self.assertEqual(root_rules[0].endpoint, 'index')


class TestRootRouteRegistrationIsOrderIndependent(unittest.TestCase):
    """S12: reproduce the exact ordering hazard flask_restx.Api creates
    (its 'root' rule for '/') with a minimal app, and prove that
    temp_monitor's _DashboardSafeApi (which skips that one registration)
    makes '/' resolve to our own view regardless of which runs first --
    the same class used for real in temp_monitor.py."""

    def _build_app(self, api_before_route):
        from flask import Flask

        app = Flask(__name__)
        app.config['TESTING'] = True

        def register_index():
            @app.route('/')
            def index():
                return 'dashboard', 200

        def register_api():
            temp_monitor._DashboardSafeApi(app, doc='/docs')

        if api_before_route:
            register_api()
            register_index()
        else:
            register_index()
            register_api()

        return app

    def test_api_registered_before_route(self):
        app = self._build_app(api_before_route=True)
        client = app.test_client()
        response = client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_data(as_text=True), 'dashboard')

    def test_api_registered_after_route(self):
        app = self._build_app(api_before_route=False)
        client = app.test_client()
        response = client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_data(as_text=True), 'dashboard')


class TestNoDocumentedRouteReturns404(unittest.TestCase):
    """Mandatory regression guard (see module docstring): a routing/
    registration change must never again silently 404 a documented route
    without a test catching it immediately. This is what would have caught
    the Api(prefix=...) mistake that 404'd all four /api/webhook/* routes.

    Deliberately iterates over every documented route from CLAUDE.md's API
    table rather than hardcoding a single endpoint, so a newly added route
    is covered automatically once it's added here.
    """

    DOCUMENTED_ROUTES = [
        ('GET', '/'),
        ('GET', '/docs'),
        ('GET', '/health'),
        ('GET', '/metrics'),
        ('GET', '/api/temp'),
        ('GET', '/api/raw'),
        ('GET', '/api/verify-token'),
        ('GET', '/api/webhook/config'),
        ('PUT', '/api/webhook/config'),
        ('POST', '/api/webhook/test'),
        ('POST', '/api/webhook/enable'),
        ('POST', '/api/webhook/disable'),
    ]

    def setUp(self):
        temp_monitor.app.config['TESTING'] = True
        self.client = temp_monitor.app.test_client()
        token = os.getenv('BEARER_TOKEN', 'test_token_ci')
        self.auth_header = {'Authorization': f'Bearer {token}'}
        # /api/raw calls sense.get_temperature() directly; give it a real
        # float so this doesn't 500 for reasons unrelated to routing.
        self._orig_get_temperature = temp_monitor.sense.get_temperature
        temp_monitor.sense.get_temperature = MagicMock(return_value=20.0)

    def tearDown(self):
        temp_monitor.sense.get_temperature = self._orig_get_temperature

    def test_no_documented_route_404s(self):
        failures = []
        for method, path in self.DOCUMENTED_ROUTES:
            kwargs = {'headers': self.auth_header}
            if method == 'PUT':
                kwargs['data'] = json.dumps({'webhook': {'url': 'https://hooks.slack.com/test'}})
                kwargs['content_type'] = 'application/json'
            response = getattr(self.client, method.lower())(path, **kwargs)
            if response.status_code == 404:
                failures.append(f"{method} {path}")
        self.assertEqual(failures, [], f"these documented routes 404'd: {failures}")

    def test_url_map_has_exactly_one_rule_per_documented_path(self):
        """A duplicate rule for the same path (S12's original shape of
        bug) is itself worth catching even when it isn't currently causing
        a visible 404."""
        paths = {path for _, path in self.DOCUMENTED_ROUTES}
        for path in paths:
            matching = [r for r in temp_monitor.app.url_map.iter_rules() if r.rule == path]
            self.assertEqual(
                len(matching), 1,
                f"expected exactly one url_map rule for {path!r}, found {matching}"
            )


if __name__ == '__main__':
    unittest.main()
