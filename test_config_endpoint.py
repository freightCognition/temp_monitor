#!/usr/bin/env python3
"""
TDD regression tests for the webhook config endpoint bugs (C1-C5, C8) filed
by the team lead. Each test is written to assert CORRECT behavior; they are
red against the bugs and green once temp_monitor.py is fixed.

New file, owned by this agent -- does not modify any existing test file.
"""

import json
import unittest
import unittest.mock

# Sets BEARER_TOKEN and mocks sense_hat; MUST precede importing temp_monitor.
from test_support import BaseAPITestCase, run_fresh_import

import temp_monitor  # noqa: E402
from webhook_service import WebhookService, WebhookConfig, AlertThresholds  # noqa: E402


class ConfigEndpointTestCase(BaseAPITestCase):
    """Common setup shared by all endpoint tests below."""

    def setUp(self):
        super().setUp()
        self._orig_webhook_service = temp_monitor.webhook_service

    def tearDown(self):
        temp_monitor.webhook_service = self._orig_webhook_service

    def put_config(self, payload):
        return self.client.put(
            '/api/webhook/config',
            data=json.dumps(payload),
            content_type='application/json',
            headers=self.auth_header,
        )


class TestC1PartialThresholdUpdatePreservesOthers(ConfigEndpointTestCase):
    """C1: a partial threshold update must merge with the stored thresholds,
    not wipe every omitted key to None."""

    def test_updating_one_threshold_preserves_the_others(self):
        temp_monitor.webhook_service = WebhookService(
            webhook_config=WebhookConfig(url='https://hooks.slack.com/services/X'),
            alert_thresholds=AlertThresholds(
                temp_min_c=15.0, temp_max_c=32.0, humidity_min=20.0, humidity_max=70.0
            ),
        )

        response = self.put_config({'thresholds': {'temp_max_c': 30.0}})

        self.assertEqual(response.status_code, 200)
        t = temp_monitor.webhook_service.alert_thresholds
        self.assertEqual(t.temp_max_c, 30.0, "the field actually sent should update")
        self.assertEqual(t.temp_min_c, 15.0, "omitted field must be preserved, not wiped to None")
        self.assertEqual(t.humidity_min, 20.0, "omitted field must be preserved, not wiped to None")
        self.assertEqual(t.humidity_max, 70.0, "omitted field must be preserved, not wiped to None")

    def test_explicit_null_still_clears_a_threshold(self):
        """Thresholds intentionally support explicit null-to-clear (see
        api_models.validate_thresholds allow_null=True) -- the merge fix must
        not break that by treating null the same as "omitted"."""
        temp_monitor.webhook_service = WebhookService(
            webhook_config=WebhookConfig(url='https://hooks.slack.com/services/X'),
            alert_thresholds=AlertThresholds(
                temp_min_c=15.0, temp_max_c=32.0, humidity_min=20.0, humidity_max=70.0
            ),
        )

        response = self.put_config({'thresholds': {'temp_min_c': None}})

        self.assertEqual(response.status_code, 200)
        t = temp_monitor.webhook_service.alert_thresholds
        self.assertIsNone(t.temp_min_c, "explicit null should clear the field")
        self.assertEqual(t.temp_max_c, 32.0, "other fields untouched")


class TestC2WebhookNullDoesNotClobber(ConfigEndpointTestCase):
    """C2: explicit JSON null on webhook fields must be rejected (400), and
    must not silently clobber the stored config."""

    def test_null_url_rejected_and_config_unchanged(self):
        temp_monitor.webhook_service = WebhookService(
            webhook_config=WebhookConfig(url='https://hooks.slack.com/services/ORIGINAL')
        )

        response = self.put_config({'webhook': {'url': None}})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            temp_monitor.webhook_service.webhook_config.url,
            'https://hooks.slack.com/services/ORIGINAL',
            "stored config must be unchanged after a rejected update",
        )

    def test_null_retry_count_rejected_and_config_unchanged(self):
        temp_monitor.webhook_service = WebhookService(
            webhook_config=WebhookConfig(url='https://hooks.slack.com/services/ORIGINAL', retry_count=4)
        )

        response = self.put_config({'webhook': {'retry_count': None}})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(temp_monitor.webhook_service.webhook_config.retry_count, 4)


class TestC3ThresholdCrossFieldValidationIsWired(ConfigEndpointTestCase):
    """C3: validate_thresholds must be called with current_thresholds so a
    partial update that creates min >= max against the STORED config is
    rejected, not just when both keys are in the same payload."""

    def test_partial_update_creating_min_greater_than_stored_max_is_rejected(self):
        temp_monitor.webhook_service = WebhookService(
            webhook_config=WebhookConfig(url='https://hooks.slack.com/services/X'),
            alert_thresholds=AlertThresholds(temp_min_c=10.0, temp_max_c=32.0),
        )

        # Only temp_min_c sent, but 40 > stored temp_max_c (32) -> must be rejected.
        response = self.put_config({'thresholds': {'temp_min_c': 40.0}})

        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertIn('temp_min_c must be less than temp_max_c', data.get('message', ''))
        # Stored config must be unchanged.
        self.assertEqual(temp_monitor.webhook_service.alert_thresholds.temp_min_c, 10.0)


class TestC4EnvDefaultsApply(unittest.TestCase):
    """C4: documented env defaults (15.0/32.0/20.0/70.0) must actually apply
    when the corresponding env var is unset, and non-numeric values must fail
    at import with a clear message instead of a bare traceback."""

    def _import_fresh(self, env_overrides, expect_success=True):
        return run_fresh_import(
            probe=(
                "{"
                "'has_webhook_service': tm.webhook_service is not None,"
                "'temp_min_c': tm.webhook_service.alert_thresholds.temp_min_c if tm.webhook_service else None,"
                "'temp_max_c': tm.webhook_service.alert_thresholds.temp_max_c if tm.webhook_service else None,"
                "'humidity_min': tm.webhook_service.alert_thresholds.humidity_min if tm.webhook_service else None,"
                "'humidity_max': tm.webhook_service.alert_thresholds.humidity_max if tm.webhook_service else None,"
                "}"
            ),
            env_overrides=env_overrides,
            scrub=('ALERT_TEMP_MIN_C', 'ALERT_TEMP_MAX_C', 'ALERT_HUMIDITY_MIN',
                   'ALERT_HUMIDITY_MAX', 'SLACK_WEBHOOK_URL', 'STATUS_UPDATE_INTERVAL'),
            expect_success=expect_success,
        )

    def test_unset_threshold_envs_use_documented_defaults(self):
        state = self._import_fresh({
            'SLACK_WEBHOOK_URL': 'https://hooks.slack.com/services/T00/B00/XXX',
            'ALERT_TEMP_MAX_C': '40.0',  # operator sets only ONE var
        })
        self.assertTrue(state['has_webhook_service'])
        self.assertEqual(state['temp_max_c'], 40.0, "explicitly set var should apply")
        self.assertEqual(state['temp_min_c'], 15.0, "documented default should apply, not None")
        self.assertEqual(state['humidity_min'], 20.0, "documented default should apply, not None")
        self.assertEqual(state['humidity_max'], 70.0, "documented default should apply, not None")

    def test_non_numeric_status_update_interval_fails_clearly_at_import(self):
        result = self._import_fresh(
            {'STATUS_UPDATE_INTERVAL': 'abc'}, expect_success=False
        )
        self.assertNotEqual(result.returncode, 0, "import should fail, not silently continue")
        self.assertIn(
            "Invalid value for environment variable STATUS_UPDATE_INTERVAL='abc'",
            result.stderr,
            "error should clearly name the offending variable and its bad value, "
            "not just an opaque 'invalid literal for int()' ValueError",
        )


class TestC5ErrorResponsesReachClientIntact(ConfigEndpointTestCase):
    """C5: a 500 from the PUT handler must not be marshalled into nulls --
    the error text and error_id must survive in the response body."""

    def test_internal_error_response_contains_error_and_error_id(self):
        temp_monitor.webhook_service = WebhookService(
            webhook_config=WebhookConfig(url='https://hooks.slack.com/services/X')
        )
        # Force an internal error inside the try block.
        with unittest.mock.patch.object(
            temp_monitor.webhook_service, 'set_webhook_config',
            side_effect=RuntimeError("boom")
        ):
            response = self.put_config({'webhook': {'enabled': False}})

        self.assertEqual(response.status_code, 500)
        data = json.loads(response.data)
        self.assertIsNotNone(
            data.get('error') or data.get('message'),
            f"error text must survive marshalling, got: {data}",
        )
        self.assertTrue(
            data.get('error_id'),
            f"error_id must survive marshalling for log correlation, got: {data}",
        )


class TestC8RecreatedServicePreservesCooldown(ConfigEndpointTestCase):
    """C8: creating a webhook service for the first time via the API must use
    the configured ALERT_COOLDOWN_SECONDS, not silently fall back to the
    hardcoded 900s default."""

    def test_cooldown_env_var_applies_when_service_created_via_api(self):
        state = run_fresh_import(
            probe=(
                "{"
                "'status': resp.status_code,"
                "'cooldown': tm.webhook_service.alert_cooldown if tm.webhook_service else None,"
                "}"
            ),
            body=(
                "client = tm.app.test_client()\n"
                "token = os.environ['BEARER_TOKEN']\n"
                "resp = client.put(\n"
                "    '/api/webhook/config',\n"
                "    data=json.dumps({'webhook': {'url': 'https://hooks.slack.com/services/T00/B00/XXX'}}),\n"
                "    content_type='application/json',\n"
                "    headers={'Authorization': f'Bearer {token}'},\n"
                ")\n"
            ),
            env_overrides={'ALERT_COOLDOWN_SECONDS': '120'},
            scrub=('SLACK_WEBHOOK_URL',),
        )
        self.assertEqual(state['status'], 200)
        self.assertEqual(
            state['cooldown'], 120,
            "newly-created webhook service should honor ALERT_COOLDOWN_SECONDS, not default to 900",
        )


if __name__ == '__main__':
    unittest.main(verbosity=2)
