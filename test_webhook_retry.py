#!/usr/bin/env python3
"""
Tests for WebhookService._send_webhook retry/backoff logic (B2).

Prior to this file, every existing test patched _send_webhook itself (so the
retry loop never ran), or patched requests.post with enabled=False (so the
early-return at the top of _send_webhook fired before requests.post was ever
reached, making assert_not_called() assertions vacuously true). These tests
patch requests.post directly with enabled=True, so the actual attempt count,
backoff delay sequence, and exception-handling paths are exercised.

time.sleep is patched so the tests run fast despite exercising real
exponential backoff math.
"""

import unittest
from unittest.mock import patch, MagicMock, call
import requests
from webhook_service import WebhookService, WebhookConfig


class TestRetryAttemptCount(unittest.TestCase):
    def setUp(self):
        self.config = WebhookConfig(
            url="https://hooks.slack.com/services/TEST/WEBHOOK/URL",
            enabled=True,
            retry_count=3,
            retry_delay=5,
            timeout=10
        )
        self.service = WebhookService(webhook_config=self.config)

    @patch('webhook_service.time.sleep')
    @patch('webhook_service.requests.post')
    def test_attempt_count_equals_retry_count_on_persistent_failure(self, mock_post, mock_sleep):
        mock_post.return_value = MagicMock(status_code=500, text="error")

        result = self.service._send_webhook({"test": "payload"})

        self.assertFalse(result)
        self.assertEqual(mock_post.call_count, 3)

    @patch('webhook_service.time.sleep')
    @patch('webhook_service.requests.post')
    def test_succeeds_on_first_attempt_no_retry_no_sleep(self, mock_post, mock_sleep):
        mock_post.return_value = MagicMock(status_code=200, text="ok")

        result = self.service._send_webhook({"test": "payload"})

        self.assertTrue(result)
        self.assertEqual(mock_post.call_count, 1)
        mock_sleep.assert_not_called()

    @patch('webhook_service.time.sleep')
    @patch('webhook_service.requests.post')
    def test_succeeds_after_intermittent_failures(self, mock_post, mock_sleep):
        mock_post.side_effect = [
            MagicMock(status_code=500, text="error"),
            MagicMock(status_code=500, text="error"),
            MagicMock(status_code=200, text="ok"),
        ]

        result = self.service._send_webhook({"test": "payload"})

        self.assertTrue(result)
        self.assertEqual(mock_post.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)


class TestBackoffDelays(unittest.TestCase):
    def setUp(self):
        self.config = WebhookConfig(
            url="https://hooks.slack.com/services/TEST/WEBHOOK/URL",
            enabled=True,
            retry_count=4,
            retry_delay=5,
            timeout=10
        )
        self.service = WebhookService(webhook_config=self.config)

    @patch('webhook_service.time.sleep')
    @patch('webhook_service.requests.post')
    def test_delay_sequence_is_exponential(self, mock_post, mock_sleep):
        mock_post.return_value = MagicMock(status_code=500, text="error")

        self.service._send_webhook({"test": "payload"})

        # delay = initial_delay * 2**attempt for attempts 0,1,2 (3 sleeps
        # between 4 attempts; no sleep after the final attempt).
        expected = [call(5), call(10), call(20)]
        self.assertEqual(mock_sleep.call_args_list, expected)

    @patch('webhook_service.time.sleep')
    @patch('webhook_service.requests.post')
    def test_no_sleep_after_final_attempt(self, mock_post, mock_sleep):
        mock_post.return_value = MagicMock(status_code=500, text="error")

        self.service._send_webhook({"test": "payload"})

        # retry_count=4 attempts -> exactly 3 sleeps between them, none after
        # the last attempt.
        self.assertEqual(mock_sleep.call_count, 3)

    @patch('webhook_service.time.sleep')
    @patch('webhook_service.requests.post')
    def test_delay_capped_at_300_seconds(self, mock_post, mock_sleep):
        config = WebhookConfig(
            url="https://hooks.slack.com/services/TEST/WEBHOOK/URL",
            enabled=True,
            retry_count=6,
            retry_delay=60,
            timeout=10
        )
        service = WebhookService(webhook_config=config)
        mock_post.return_value = MagicMock(status_code=500, text="error")

        service._send_webhook({"test": "payload"})

        # 60 is the LARGEST retry_delay the config layer accepts
        # (RETRY_DELAY_RANGE, enforced by WebhookConfig.__post_init__ and by
        # api_models._validate_numeric_field). This case used to pass 100,
        # which the PUT API has always rejected and which only became
        # constructible at all because env-var config bypassed validation --
        # the very gap __post_init__ closes. Don't raise it back; 60 still
        # reaches the cap:
        # 60*2^0=60, 60*2^1=120, 60*2^2=240, 60*2^3=480->300, 60*2^4=960->300
        expected = [call(60), call(120), call(240), call(300), call(300)]
        self.assertEqual(mock_sleep.call_args_list, expected)


class TestExceptionPaths(unittest.TestCase):
    def setUp(self):
        self.config = WebhookConfig(
            url="https://hooks.slack.com/services/TEST/WEBHOOK/URL",
            enabled=True,
            retry_count=2,
            retry_delay=1,
            timeout=10
        )
        self.service = WebhookService(webhook_config=self.config)

    @patch('webhook_service.time.sleep')
    @patch('webhook_service.requests.post')
    def test_timeout_exception_retries_and_ultimately_fails(self, mock_post, mock_sleep):
        mock_post.side_effect = requests.exceptions.Timeout("timed out")

        result = self.service._send_webhook({"test": "payload"})

        self.assertFalse(result)
        self.assertEqual(mock_post.call_count, 2)
        mock_sleep.assert_called_once()

    @patch('webhook_service.time.sleep')
    @patch('webhook_service.requests.post')
    def test_request_exception_retries_and_ultimately_fails(self, mock_post, mock_sleep):
        mock_post.side_effect = requests.exceptions.ConnectionError("connection refused")

        result = self.service._send_webhook({"test": "payload"})

        self.assertFalse(result)
        self.assertEqual(mock_post.call_count, 2)
        mock_sleep.assert_called_once()

    @patch('webhook_service.time.sleep')
    @patch('webhook_service.requests.post')
    def test_recovers_after_exception_on_final_retry(self, mock_post, mock_sleep):
        mock_post.side_effect = [
            requests.exceptions.Timeout("timed out"),
            MagicMock(status_code=200, text="ok"),
        ]

        result = self.service._send_webhook({"test": "payload"})

        self.assertTrue(result)
        self.assertEqual(mock_post.call_count, 2)

    @patch('webhook_service.time.sleep')
    @patch('webhook_service.requests.post')
    def test_mixed_exception_types_across_attempts(self, mock_post, mock_sleep):
        config = WebhookConfig(
            url="https://hooks.slack.com/services/TEST/WEBHOOK/URL",
            enabled=True,
            retry_count=3,
            retry_delay=1,
            timeout=10
        )
        service = WebhookService(webhook_config=config)
        mock_post.side_effect = [
            requests.exceptions.Timeout("timed out"),
            requests.exceptions.ConnectionError("connection refused"),
            requests.exceptions.RequestException("generic failure"),
        ]

        result = service._send_webhook({"test": "payload"})

        self.assertFalse(result)
        self.assertEqual(mock_post.call_count, 3)


if __name__ == "__main__":
    unittest.main()
