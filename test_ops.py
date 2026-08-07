#!/usr/bin/env python3
"""
Tests for S11 (log rotation) and S14 (double startup sleep).

S11: temp_monitor.py installed a plain logging.FileHandler via
logging.basicConfig(). A persistent sensor failure logs an error and
retries every 5s forever (~17,000 lines/day), unbounded, on a Pi SD card.
Fix: RotatingFileHandler with a bounded size and backup count.

S14: temp_monitor.py's start_sensor_thread() sleeps 2s, and wsgi.py sleeps
another 2s for the same stated reason ("give the thread a moment"),
delaying every import/startup by 4s -- and neither duration is even long
enough to guarantee a first reading. Fix: a single wait, in one place.
"""
import json
import subprocess
import sys
import unittest
import unittest.mock
from logging.handlers import RotatingFileHandler

# Sets BEARER_TOKEN and mocks sense_hat; MUST precede importing temp_monitor.
from test_support import BaseAPITestCase

import temp_monitor  # noqa: E402
from webhook_service import WebhookService, WebhookConfig  # noqa: E402


class TestLogRotation(unittest.TestCase):
    def test_root_logger_uses_rotating_file_handler(self):
        handlers = temp_monitor.logging.getLogger().handlers
        rotating = [h for h in handlers if isinstance(h, RotatingFileHandler)]
        self.assertTrue(
            rotating,
            f"expected a RotatingFileHandler on the root logger, found: {handlers}"
        )
        handler = rotating[0]
        self.assertGreater(handler.maxBytes, 0, "maxBytes must be bounded (> 0)")
        self.assertGreater(handler.backupCount, 0, "backupCount must be > 0 to keep any history")

    def test_no_plain_unbounded_file_handler(self):
        """A plain FileHandler (not a RotatingFileHandler) would grow
        without bound -- make sure none is present."""
        handlers = temp_monitor.logging.getLogger().handlers
        plain_file_handlers = [
            h for h in handlers
            if type(h) is temp_monitor.logging.FileHandler  # exact type, not the RotatingFileHandler subclass
        ]
        self.assertEqual(plain_file_handlers, [])


class TestNoDoubleStartupSleep(unittest.TestCase):
    def test_wsgi_does_not_sleep_after_start_sensor_thread(self):
        """S14: start_sensor_thread() already waits for a first reading;
        wsgi.py must not add a second, redundant sleep on top of it."""
        with open('wsgi.py') as f:
            source = f.read()
        # after start_sensor_thread() returns, there should be no further
        # call to time.sleep in this module
        after_start_call = source.split('start_sensor_thread()', 1)[1]
        self.assertNotIn(
            'time.sleep', after_start_call,
            "wsgi.py still sleeps again after start_sensor_thread() already waited"
        )

    def test_wsgi_still_starts_sensor_thread_successfully(self):
        """Regression guard: the cleanup must not break wsgi's ability to
        start the sensor thread on import."""
        result = subprocess.run(
            [sys.executable, '-c', (
                "import sys\n"
                "from unittest.mock import MagicMock\n"
                "sys.modules['sense_hat'] = MagicMock()\n"
                "import wsgi\n"
                "print('ok')\n"
            )],
            capture_output=True, text=True,
            env={'BEARER_TOKEN': 'test_token_ci', 'PATH': __import__('os').environ.get('PATH', '')},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('ok', result.stdout)


class TestWebhookTestEndpointCleanFailure(BaseAPITestCase):
    """Fix 9: WebhookTestResource.post()'s own webhooks_ns.abort(500, ...)
    call for an ordinary "the webhook send failed" outcome (Slack
    unreachable, non-2xx response, etc.) is an HTTPException, which
    subclasses Exception -- so the broad `except Exception` below it caught
    that control flow too, logging a full traceback via logging.exception
    as though it were a genuine crash, and generating a SECOND error_id
    that didn't match the one already in the abort() response body. The
    fix adds an `except HTTPException: raise` before the broad clause, and
    passes error_id through on both paths."""

    def setUp(self):
        super().setUp()
        self._orig_webhook_service = temp_monitor.webhook_service
        temp_monitor.webhook_service = WebhookService(
            webhook_config=WebhookConfig(url='https://hooks.slack.com/services/TEST')
        )

    def tearDown(self):
        temp_monitor.webhook_service = self._orig_webhook_service

    def test_clean_send_failure_returns_error_id_without_logging_traceback(self):
        with unittest.mock.patch.object(
            temp_monitor.webhook_service, 'send_status_update', return_value=False
        ), unittest.mock.patch.object(temp_monitor.logging, 'exception') as mock_exception:
            response = self.client.post('/api/webhook/test', headers=self.auth_header)

        self.assertEqual(response.status_code, 500)
        data = json.loads(response.data)
        self.assertTrue(
            data.get('error_id'),
            f"error_id must be present on a clean send failure, got: {data}",
        )
        mock_exception.assert_not_called()

    def test_genuine_exception_still_logs_and_returns_matching_error_id(self):
        """Regression guard: a REAL unexpected exception must still be
        logged (unlike the clean-failure path above) and still carry an
        error_id in the response, same as every other 500 in this file."""
        with unittest.mock.patch.object(
            temp_monitor.webhook_service, 'send_status_update',
            side_effect=RuntimeError('boom')
        ), unittest.mock.patch.object(temp_monitor.logging, 'exception') as mock_exception:
            response = self.client.post('/api/webhook/test', headers=self.auth_header)

        self.assertEqual(response.status_code, 500)
        data = json.loads(response.data)
        self.assertTrue(data.get('error_id'), f"error_id must be present, got: {data}")
        mock_exception.assert_called_once()


if __name__ == '__main__':
    unittest.main()
