#!/usr/bin/env python3
"""
Test script for webhook functionality

This script tests the webhook service without requiring the full Flask app or hardware.
Uses unittest.mock to capture payloads and verify Slack message structure.
"""

import sys
import unittest
from unittest.mock import patch, MagicMock
import requests
from webhook_service import WebhookService, WebhookConfig, AlertThresholds


class TestSlackFormatting(unittest.TestCase):
    """Test Slack message formatting and payload structure"""

    def setUp(self):
        """Set up test fixtures"""
        self.config = WebhookConfig(
            url="https://hooks.slack.com/services/TEST/WEBHOOK/URL",
            enabled=True
        )
        self.service = WebhookService(webhook_config=self.config)

    @patch.object(WebhookService, '_send_webhook')
    def test_basic_message_payload_structure(self, mock_send):
        """Test basic message creates correct payload structure"""
        mock_send.return_value = True

        result = self.service.send_slack_message(
            text="Test message",
            color="good"
        )

        self.assertTrue(result)
        mock_send.assert_called_once()

        payload = mock_send.call_args[0][0]

        # Verify top-level structure
        self.assertIn("attachments", payload)
        self.assertEqual(len(payload["attachments"]), 1)

        attachment = payload["attachments"][0]

        # Verify attachment fields
        self.assertEqual(attachment["text"], "Test message")
        self.assertEqual(attachment["color"], "good")
        self.assertIn("ts", attachment)
        self.assertIsInstance(attachment["ts"], int)

        # No fields for basic message
        self.assertNotIn("fields", attachment)

    @patch.object(WebhookService, '_send_webhook')
    def test_message_with_custom_color(self, mock_send):
        """Test message with different color values"""
        mock_send.return_value = True

        for color in ["warning", "danger", "#FF5733"]:
            self.service.send_slack_message(text="Test", color=color)
            payload = mock_send.call_args[0][0]
            self.assertEqual(payload["attachments"][0]["color"], color)

    @patch.object(WebhookService, '_send_webhook')
    def test_message_with_fields(self, mock_send):
        """Test message with fields includes correct structure"""
        mock_send.return_value = True

        fields = [
            {"title": "Field 1", "value": "Value 1", "short": True},
            {"title": "Field 2", "value": "Value 2", "short": False}
        ]

        self.service.send_slack_message(
            text="Message with fields",
            color="good",
            fields=fields
        )

        payload = mock_send.call_args[0][0]
        attachment = payload["attachments"][0]

        self.assertIn("fields", attachment)
        self.assertEqual(len(attachment["fields"]), 2)
        self.assertEqual(attachment["fields"][0]["title"], "Field 1")
        self.assertEqual(attachment["fields"][0]["value"], "Value 1")
        self.assertTrue(attachment["fields"][0]["short"])
        self.assertEqual(attachment["fields"][1]["title"], "Field 2")
        self.assertFalse(attachment["fields"][1]["short"])


class TestAlertPayloads(unittest.TestCase):
    """Test alert message payloads"""

    def setUp(self):
        """Set up test fixtures with thresholds"""
        self.config = WebhookConfig(
            url="https://hooks.slack.com/services/TEST/WEBHOOK/URL",
            enabled=True
        )
        self.thresholds = AlertThresholds(
            temp_min_c=15.0,
            temp_max_c=27.0,
            humidity_min=30.0,
            humidity_max=70.0
        )
        self.service = WebhookService(
            webhook_config=self.config,
            alert_thresholds=self.thresholds
        )

    def _reset_cooldown(self):
        """Helper to reset alert cooldown"""
        with self.service._lock:
            self.service.last_alert_time.clear()

    @patch.object(WebhookService, '_send_webhook')
    def test_temp_high_alert_payload(self, mock_send):
        """Test high temperature alert has correct payload structure"""
        mock_send.return_value = True
        self._reset_cooldown()

        alerts = self.service.check_and_alert(30.0, 50.0, "2025-12-30 12:00:00")

        self.assertIn('temp_high', alerts)
        mock_send.assert_called_once()

        payload = mock_send.call_args[0][0]
        attachment = payload["attachments"][0]

        # Verify text and color
        self.assertIn("Temperature Alert: HIGH", attachment["text"])
        self.assertEqual(attachment["color"], "danger")

        # Verify fields structure and content
        fields = attachment["fields"]
        self.assertEqual(len(fields), 3)

        # Field 0: Current Temperature
        self.assertEqual(fields[0]["title"], "Current Temperature")
        self.assertIn("30", fields[0]["value"])
        self.assertIn("86", fields[0]["value"])  # 30°C = 86°F
        self.assertTrue(fields[0]["short"])

        # Field 1: Threshold
        self.assertEqual(fields[1]["title"], "Threshold")
        self.assertIn("27", fields[1]["value"])
        self.assertTrue(fields[1]["short"])

        # Field 2: Timestamp
        self.assertEqual(fields[2]["title"], "Timestamp")
        self.assertEqual(fields[2]["value"], "2025-12-30 12:00:00")
        self.assertFalse(fields[2]["short"])

    @patch.object(WebhookService, '_send_webhook')
    def test_temp_low_alert_payload(self, mock_send):
        """Test low temperature alert has correct payload structure"""
        mock_send.return_value = True
        self._reset_cooldown()

        alerts = self.service.check_and_alert(10.0, 50.0, "2025-12-30 12:00:00")

        self.assertIn('temp_low', alerts)
        payload = mock_send.call_args[0][0]
        attachment = payload["attachments"][0]

        self.assertIn("Temperature Alert: LOW", attachment["text"])
        self.assertEqual(attachment["color"], "warning")
        self.assertEqual(len(attachment["fields"]), 3)

    @patch.object(WebhookService, '_send_webhook')
    def test_humidity_high_alert_payload(self, mock_send):
        """Test high humidity alert has correct payload structure"""
        mock_send.return_value = True
        self._reset_cooldown()

        alerts = self.service.check_and_alert(22.0, 75.0, "2025-12-30 12:00:00")

        self.assertIn('humidity_high', alerts)
        payload = mock_send.call_args[0][0]
        attachment = payload["attachments"][0]

        self.assertIn("Humidity Alert: HIGH", attachment["text"])
        self.assertEqual(attachment["color"], "warning")

        fields = attachment["fields"]
        self.assertEqual(fields[0]["title"], "Current Humidity")
        self.assertEqual(fields[0]["value"], "75.0%")
        self.assertEqual(fields[1]["title"], "Threshold")
        self.assertEqual(fields[1]["value"], "70.0%")

    @patch.object(WebhookService, '_send_webhook')
    def test_humidity_low_alert_payload(self, mock_send):
        """Test low humidity alert has correct payload structure"""
        mock_send.return_value = True
        self._reset_cooldown()

        alerts = self.service.check_and_alert(22.0, 25.0, "2025-12-30 12:00:00")

        self.assertIn('humidity_low', alerts)
        payload = mock_send.call_args[0][0]
        attachment = payload["attachments"][0]

        self.assertIn("Humidity Alert: LOW", attachment["text"])
        self.assertEqual(attachment["color"], "warning")
        fields = attachment["fields"]
        self.assertEqual(fields[0]["title"], "Current Humidity")
        self.assertEqual(fields[0]["value"], "25.0%")
        self.assertEqual(fields[1]["title"], "Threshold")
        self.assertEqual(fields[1]["value"], "30.0%")

    @patch.object(WebhookService, '_send_webhook')
    def test_normal_readings_no_alert(self, mock_send):
        """Test normal readings do not trigger any alerts"""
        mock_send.return_value = True
        self._reset_cooldown()

        alerts = self.service.check_and_alert(22.0, 50.0, "2025-12-30 12:00:00")

        self.assertEqual(len(alerts), 0)
        mock_send.assert_not_called()


class TestStatusUpdatePayload(unittest.TestCase):
    """Test status update message payloads"""

    def setUp(self):
        """Set up test fixtures"""
        self.config = WebhookConfig(
            url="https://hooks.slack.com/services/TEST/WEBHOOK/URL",
            enabled=True
        )
        self.service = WebhookService(webhook_config=self.config)

    @patch.object(WebhookService, '_send_webhook')
    def test_status_update_payload_structure(self, mock_send):
        """Test status update has correct payload structure"""
        mock_send.return_value = True

        result = self.service.send_status_update(
            temperature_c=22.5,
            humidity=55.0,
            cpu_temp=45.0,
            timestamp="2025-12-30 12:00:00"
        )

        self.assertTrue(result)
        mock_send.assert_called_once()

        payload = mock_send.call_args[0][0]
        attachment = payload["attachments"][0]

        # Verify text and color
        self.assertIn("Server Room Status Update", attachment["text"])
        self.assertEqual(attachment["color"], "good")

        # Verify fields order and content
        fields = attachment["fields"]
        self.assertEqual(len(fields), 4)

        # Field order: Temperature, Humidity, CPU Temperature, Last Updated
        self.assertEqual(fields[0]["title"], "Temperature")
        self.assertIn("22.5", fields[0]["value"])
        self.assertIn("72.5", fields[0]["value"])  # 22.5°C = 72.5°F
        self.assertTrue(fields[0]["short"])

        self.assertEqual(fields[1]["title"], "Humidity")
        self.assertEqual(fields[1]["value"], "55.0%")
        self.assertTrue(fields[1]["short"])

        self.assertEqual(fields[2]["title"], "CPU Temperature")
        self.assertEqual(fields[2]["value"], "45.0°C")
        self.assertTrue(fields[2]["short"])

        self.assertEqual(fields[3]["title"], "Last Updated")
        self.assertEqual(fields[3]["value"], "2025-12-30 12:00:00")
        self.assertFalse(fields[3]["short"])

    @patch.object(WebhookService, '_send_webhook')
    def test_status_update_without_cpu_temp(self, mock_send):
        """Test status update without CPU temperature"""
        mock_send.return_value = True

        self.service.send_status_update(
            temperature_c=22.5,
            humidity=55.0,
            cpu_temp=None,
            timestamp="2025-12-30 12:00:00"
        )

        payload = mock_send.call_args[0][0]
        fields = payload["attachments"][0]["fields"]

        # Only 3 fields when CPU temp is None
        self.assertEqual(len(fields), 3)
        field_titles = [f["title"] for f in fields]
        self.assertNotIn("CPU Temperature", field_titles)
        self.assertIn("Temperature", field_titles)
        self.assertIn("Humidity", field_titles)
        self.assertIn("Last Updated", field_titles)


class TestSystemEventPayloads(unittest.TestCase):
    """Test system event message payloads"""

    def setUp(self):
        """Set up test fixtures"""
        self.config = WebhookConfig(
            url="https://hooks.slack.com/services/TEST/WEBHOOK/URL",
            enabled=True
        )
        self.service = WebhookService(webhook_config=self.config)

    @patch.object(WebhookService, '_send_webhook')
    def test_startup_event_payload(self, mock_send):
        """Test startup event has correct icon and color"""
        mock_send.return_value = True

        self.service.send_system_event(
            event_type="startup",
            message="Service started successfully",
            severity="info"
        )

        payload = mock_send.call_args[0][0]
        attachment = payload["attachments"][0]

        self.assertIn("STARTUP", attachment["text"])
        self.assertIn("Service started successfully", attachment["text"])
        self.assertEqual(attachment["color"], "good")

        # Verify timestamp field
        fields = attachment["fields"]
        self.assertEqual(len(fields), 1)
        self.assertEqual(fields[0]["title"], "Timestamp")

    @patch.object(WebhookService, '_send_webhook')
    def test_shutdown_event_payload(self, mock_send):
        """Test shutdown event has correct icon"""
        mock_send.return_value = True

        self.service.send_system_event(
            event_type="shutdown",
            message="Service stopping",
            severity="info"
        )

        payload = mock_send.call_args[0][0]
        attachment = payload["attachments"][0]

        self.assertIn("SHUTDOWN", attachment["text"])

    @patch.object(WebhookService, '_send_webhook')
    def test_error_event_payload(self, mock_send):
        """Test error event has danger color"""
        mock_send.return_value = True

        self.service.send_system_event(
            event_type="error",
            message="Critical failure",
            severity="error"
        )

        payload = mock_send.call_args[0][0]
        attachment = payload["attachments"][0]

        self.assertIn("ERROR", attachment["text"])
        self.assertEqual(attachment["color"], "danger")

    @patch.object(WebhookService, '_send_webhook')
    def test_warning_severity_color(self, mock_send):
        """Test warning severity maps to warning color"""
        mock_send.return_value = True

        self.service.send_system_event(
            event_type="info",
            message="Warning message",
            severity="warning"
        )

        payload = mock_send.call_args[0][0]
        self.assertEqual(payload["attachments"][0]["color"], "warning")


class TestWebhookDisabled(unittest.TestCase):
    """Test that send is not invoked when webhook is disabled"""

    @patch('webhook_service.requests.post')
    def test_send_not_called_when_disabled(self, mock_post):
        """Verify requests.post is NOT called when enabled=False"""
        config = WebhookConfig(
            url="https://hooks.slack.com/services/TEST/WEBHOOK/URL",
            enabled=False
        )
        service = WebhookService(webhook_config=config)

        result = service.send_slack_message(text="Should not send")

        self.assertFalse(result)
        mock_post.assert_not_called()

    @patch('webhook_service.requests.post')
    def test_status_update_not_sent_when_disabled(self, mock_post):
        """Verify status update does not send when disabled"""
        config = WebhookConfig(
            url="https://hooks.slack.com/services/TEST/WEBHOOK/URL",
            enabled=False
        )
        service = WebhookService(webhook_config=config)

        result = service.send_status_update(22.0, 50.0, 40.0, "2025-12-30 12:00:00")

        self.assertFalse(result)
        mock_post.assert_not_called()

    @patch('webhook_service.requests.post')
    def test_system_event_not_sent_when_disabled(self, mock_post):
        """Verify system event does not send when disabled"""
        config = WebhookConfig(
            url="https://hooks.slack.com/services/TEST/WEBHOOK/URL",
            enabled=False
        )
        service = WebhookService(webhook_config=config)

        result = service.send_system_event("startup", "Test", "info")

        self.assertFalse(result)
        mock_post.assert_not_called()

    @patch('webhook_service.requests.post')
    def test_alerts_not_sent_when_disabled(self, mock_post):
        """Verify alerts do not send when disabled"""
        config = WebhookConfig(
            url="https://hooks.slack.com/services/TEST/WEBHOOK/URL",
            enabled=False
        )
        thresholds = AlertThresholds(temp_max_c=25.0)
        service = WebhookService(webhook_config=config, alert_thresholds=thresholds)

        # Trigger a high temp alert
        alerts = service.check_and_alert(30.0, 50.0, "2025-12-30 12:00:00")

        # Alert detected but not sent
        self.assertIn('temp_high', alerts)
        self.assertFalse(alerts['temp_high'])
        mock_post.assert_not_called()


class TestThresholdDetection(unittest.TestCase):
    """Test threshold detection logic"""

    def setUp(self):
        """Set up test fixtures"""
        self.config = WebhookConfig(
            url="https://hooks.slack.com/services/TEST/WEBHOOK/URL",
            enabled=False  # Disable actual sends
        )
        self.thresholds = AlertThresholds(
            temp_min_c=15.0,
            temp_max_c=27.0,
            humidity_min=30.0,
            humidity_max=70.0
        )
        self.service = WebhookService(
            webhook_config=self.config,
            alert_thresholds=self.thresholds
        )

    def _reset_cooldown(self):
        """Helper to reset alert cooldown"""
        with self.service._lock:
            self.service.last_alert_time.clear()

    def test_normal_readings_no_alerts(self):
        """Normal readings should not trigger alerts"""
        alerts = self.service.check_and_alert(22.0, 50.0, "2025-12-30 12:00:00")
        self.assertEqual(len(alerts), 0)

    def test_high_temperature_triggers(self):
        """High temperature should trigger temp_high alert"""
        self._reset_cooldown()
        alerts = self.service.check_and_alert(30.0, 50.0, "2025-12-30 12:00:00")
        self.assertIn('temp_high', alerts)

    def test_low_temperature_triggers(self):
        """Low temperature should trigger temp_low alert"""
        self._reset_cooldown()
        alerts = self.service.check_and_alert(10.0, 50.0, "2025-12-30 12:00:00")
        self.assertIn('temp_low', alerts)

    def test_high_humidity_triggers(self):
        """High humidity should trigger humidity_high alert"""
        self._reset_cooldown()
        alerts = self.service.check_and_alert(22.0, 75.0, "2025-12-30 12:00:00")
        self.assertIn('humidity_high', alerts)

    def test_low_humidity_triggers(self):
        """Low humidity should trigger humidity_low alert"""
        self._reset_cooldown()
        alerts = self.service.check_and_alert(22.0, 25.0, "2025-12-30 12:00:00")
        self.assertIn('humidity_low', alerts)


class TestCooldownLogic(unittest.TestCase):
    """Test alert cooldown logic"""

    def setUp(self):
        """Set up test fixtures"""
        self.config = WebhookConfig(
            url="https://hooks.slack.com/services/TEST/WEBHOOK/URL",
            enabled=False
        )
        self.thresholds = AlertThresholds(temp_max_c=25.0)
        self.service = WebhookService(
            webhook_config=self.config,
            alert_thresholds=self.thresholds
        )

    def test_first_alert_allowed(self):
        """First alert should be allowed"""
        can_send = self.service._can_send_alert('test_alert')
        self.assertTrue(can_send)

    def test_cooldown_blocks_immediate_retry(self):
        """Immediate retry should be blocked by cooldown"""
        self.service._mark_alert_sent('test_alert')
        can_send = self.service._can_send_alert('test_alert')
        self.assertFalse(can_send)

    def test_different_alert_types_independent(self):
        """Different alert types should be independent"""
        self.service._mark_alert_sent('test_alert')
        can_send = self.service._can_send_alert('different_alert')
        self.assertTrue(can_send)


class TestConfiguration(unittest.TestCase):
    """Test configuration management"""

    def test_default_config_values(self):
        """Default configuration values should be correct"""
        config = WebhookConfig(url="https://test.url")
        self.assertTrue(config.enabled)
        self.assertEqual(config.retry_count, 3)
        self.assertEqual(config.retry_delay, 5)
        self.assertEqual(config.timeout, 10)

    def test_custom_config_values(self):
        """Custom configuration values should be applied"""
        config = WebhookConfig(
            url="https://test.url",
            enabled=False,
            retry_count=5,
            retry_delay=10,
            timeout=30
        )
        self.assertFalse(config.enabled)
        self.assertEqual(config.retry_count, 5)
        self.assertEqual(config.retry_delay, 10)
        self.assertEqual(config.timeout, 30)

    def test_disabled_thresholds_dont_trigger(self):
        """Disabled thresholds (None) should not trigger alerts, even at extreme
        readings that WOULD trigger a low alert if the None threshold were
        mistakenly enforced. This proves the check is truly skipped rather than
        passing vacuously because the reading happened not to breach anything."""
        thresholds = AlertThresholds(
            temp_min_c=None,
            temp_max_c=30.0,
            humidity_min=None,
            humidity_max=80.0
        )
        service = WebhookService(alert_thresholds=thresholds)

        # Extreme low values: would trigger temp_low/humidity_low under any
        # sane real threshold, so this only stays silent if None truly disables
        # the check.
        alerts = service.check_and_alert(-10.0, 1.0, "2025-12-30 12:00:00")

        self.assertNotIn('temp_low', alerts)
        self.assertNotIn('humidity_low', alerts)

        # Sanity check: the max thresholds (which are NOT None) still function,
        # so we know check_and_alert is actually evaluating readings and not
        # just short-circuiting everything.
        alerts_max = service.check_and_alert(35.0, 90.0, "2025-12-30 12:00:01")
        self.assertIn('temp_high', alerts_max)
        self.assertIn('humidity_high', alerts_max)


class TestSuccessStatusCodes(unittest.TestCase):
    """Any 2xx status code must count as a successful send (B1).

    Previously only exactly 200 counted as success, so a relay/endpoint that
    legitimately returns 201/202/204 would be treated as a failure: every
    retry would burn, _send_webhook would return False, _mark_alert_sent
    would never run, and the cooldown would never be recorded -- causing the
    same alert to resend every cycle forever.
    """

    @patch('webhook_service.requests.post')
    def test_2xx_status_codes_count_as_success_and_record_cooldown(self, mock_post):
        for status in (200, 201, 202, 204):
            with self.subTest(status=status):
                mock_post.return_value = MagicMock(status_code=status, text="")
                config = WebhookConfig(
                    url="https://hooks.slack.com/services/TEST/WEBHOOK/URL",
                    enabled=True,
                    retry_count=1
                )
                thresholds = AlertThresholds(temp_max_c=25.0)
                service = WebhookService(
                    webhook_config=config,
                    alert_thresholds=thresholds,
                    alert_cooldown=300
                )

                alerts = service.check_and_alert(30.0, 50.0, f"T-{status}")

                self.assertTrue(
                    alerts.get('temp_high'),
                    f"status {status} should count as success"
                )
                # Cooldown must have been recorded on success: an immediate
                # second check must be suppressed.
                self.assertFalse(
                    service._can_send_alert('temp_high'),
                    f"status {status} success did not record cooldown"
                )


class TestMonotonicCooldown(unittest.TestCase):
    """Cooldown must be immune to wall-clock steps (B3).

    A Raspberry Pi has no RTC; NTP can step the wall clock backwards shortly
    after boot. If cooldown math uses time.time(), a backwards step makes
    `elapsed` negative and suppresses every alert type until the (now bogus)
    cooldown window passes -- potentially forever if the clock keeps getting
    corrected. time.monotonic() is immune to this because it never goes
    backwards.
    """

    def setUp(self):
        self.config = WebhookConfig(
            url="https://hooks.slack.com/services/TEST/WEBHOOK/URL",
            enabled=False
        )
        self.service = WebhookService(webhook_config=self.config, alert_cooldown=60)

    @patch('webhook_service.time.time')
    @patch('webhook_service.time.monotonic')
    def test_wall_clock_backwards_step_does_not_suppress_alerts(self, mock_monotonic, mock_time):
        # monotonic time advances normally by 70s (past the 60s cooldown)
        mock_monotonic.side_effect = [1000.0, 1070.0]
        # wall clock jumps backwards by 900s, as an NTP step at boot would do
        mock_time.side_effect = [1000.0, 100.0]

        self.service._mark_alert_sent('test_alert')
        can_send = self.service._can_send_alert('test_alert')

        self.assertTrue(
            can_send,
            "cooldown must use a monotonic clock, immune to backwards wall-clock steps"
        )
        mock_time.assert_not_called()


class TestAlertRecovery(unittest.TestCase):
    """Cooldown must clear on recovery, with a resolved notification sent (B4).

    Without this, a spike at T=0 sends an alert; recovery at T=1min is
    silent; a second spike at T=3min is suppressed by the still-active
    cooldown from the FIRST spike -- total silence until the cooldown
    window expires, even though the room re-entered an alert state.
    """

    def setUp(self):
        self.config = WebhookConfig(
            url="https://hooks.slack.com/services/TEST/WEBHOOK/URL",
            enabled=True,
            retry_count=1
        )
        self.thresholds = AlertThresholds(temp_max_c=25.0)

    @patch('webhook_service.requests.post')
    def test_recovery_clears_cooldown_and_sends_resolved_notification(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, text="")
        service = WebhookService(
            webhook_config=self.config,
            alert_thresholds=self.thresholds,
            alert_cooldown=300
        )

        # Spike: alert fires
        spike = service.check_and_alert(30.0, 50.0, "T0")
        self.assertTrue(spike.get('temp_high'))
        self.assertEqual(mock_post.call_count, 1)

        # Recovery: reading back within threshold -> resolved notification,
        # cooldown cleared
        recovered = service.check_and_alert(20.0, 50.0, "T1")
        self.assertTrue(recovered.get('temp_high_resolved'))
        self.assertEqual(mock_post.call_count, 2)

        # Second spike immediately after recovery must NOT be suppressed by
        # the stale cooldown from the first spike.
        respike = service.check_and_alert(31.0, 50.0, "T2")
        self.assertTrue(respike.get('temp_high'))
        self.assertEqual(mock_post.call_count, 3)

    @patch('webhook_service.requests.post')
    def test_no_resolved_notification_when_never_alerted(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, text="")
        service = WebhookService(
            webhook_config=self.config,
            alert_thresholds=self.thresholds,
            alert_cooldown=300
        )

        # Normal reading, never alerted -> no resolved notification either
        normal = service.check_and_alert(20.0, 50.0, "T0")
        self.assertNotIn('temp_high_resolved', normal)
        mock_post.assert_not_called()


class TestCooldownEndToEnd(unittest.TestCase):
    """Drive check_and_alert TWICE with a mocked transport and enabled=True,
    asserting the second call is suppressed by cooldown (B5)."""

    @patch('webhook_service.requests.post')
    def test_second_identical_alert_is_suppressed(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, text="")
        config = WebhookConfig(
            url="https://hooks.slack.com/services/TEST/WEBHOOK/URL",
            enabled=True,
            retry_count=1
        )
        thresholds = AlertThresholds(temp_max_c=25.0)
        service = WebhookService(
            webhook_config=config,
            alert_thresholds=thresholds,
            alert_cooldown=300
        )

        first = service.check_and_alert(30.0, 50.0, "T0")
        self.assertTrue(first.get('temp_high'))
        self.assertEqual(mock_post.call_count, 1)

        second = service.check_and_alert(30.0, 50.0, "T1")
        self.assertNotIn('temp_high', second)
        self.assertEqual(mock_post.call_count, 1)


class TestSecretScrubbing(unittest.TestCase):
    """Webhook secrets must never leak into logs (B7).

    response.text was logged unbounded, and RequestException messages embed
    the full URL including the secret Slack path
    (".../services/T.../B.../<secret>"), defeating the _mask_url design used
    everywhere else.
    """

    @patch('webhook_service.requests.post')
    def test_request_exception_does_not_leak_secret_path(self, mock_post):
        secret_url = "https://hooks.slack.com/services/TSECRET/BSECRET/supersecrettoken"
        mock_post.side_effect = requests.exceptions.ConnectionError(
            "HTTPSConnectionPool(host='hooks.slack.com', port=443): "
            "Max retries exceeded with url: /services/TSECRET/BSECRET/supersecrettoken "
            "(Caused by NewConnectionError('...'))"
        )
        config = WebhookConfig(url=secret_url, enabled=True, retry_count=1)
        service = WebhookService(webhook_config=config)

        with self.assertLogs(level='ERROR') as cm:
            result = service._send_webhook({"test": "payload"})

        self.assertFalse(result)
        log_output = "\n".join(cm.output)
        self.assertNotIn("TSECRET", log_output)
        self.assertNotIn("BSECRET", log_output)
        self.assertNotIn("supersecrettoken", log_output)

    @patch('webhook_service.requests.post')
    def test_response_body_is_truncated_in_logs(self, mock_post):
        long_body = "SECRETVALUE" + ("x" * 5000)
        mock_post.return_value = MagicMock(status_code=500, text=long_body)
        config = WebhookConfig(
            url="https://hooks.slack.com/services/TEST/WEBHOOK/URL",
            enabled=True,
            retry_count=1
        )
        service = WebhookService(webhook_config=config)

        with self.assertLogs(level='WARNING') as cm:
            service._send_webhook({"test": "payload"})

        log_output = "\n".join(cm.output)
        self.assertLess(len(log_output), len(long_body))


class TestSlackPayloadSchema(unittest.TestCase):
    """Slack attachment payload must include fallback + mrkdwn_in (B8).

    Without `fallback`, Slack's legacy attachment schema renders an empty
    push notification -- exactly what on-call sees first.
    """

    @patch.object(WebhookService, '_send_webhook')
    def test_payload_includes_fallback_and_mrkdwn_in(self, mock_send):
        mock_send.return_value = True
        config = WebhookConfig(
            url="https://hooks.slack.com/services/TEST/WEBHOOK/URL",
            enabled=True
        )
        service = WebhookService(webhook_config=config)

        service.send_slack_message(text="Test message", color="danger")

        payload = mock_send.call_args[0][0]
        attachment = payload["attachments"][0]

        self.assertEqual(attachment["fallback"], "Test message")
        self.assertIn("mrkdwn_in", attachment)
        self.assertIn("text", attachment["mrkdwn_in"])


def main():
    """Run all tests using unittest"""
    # Create a test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestSlackFormatting))
    suite.addTests(loader.loadTestsFromTestCase(TestAlertPayloads))
    suite.addTests(loader.loadTestsFromTestCase(TestStatusUpdatePayload))
    suite.addTests(loader.loadTestsFromTestCase(TestSystemEventPayloads))
    suite.addTests(loader.loadTestsFromTestCase(TestWebhookDisabled))
    suite.addTests(loader.loadTestsFromTestCase(TestThresholdDetection))
    suite.addTests(loader.loadTestsFromTestCase(TestCooldownLogic))
    suite.addTests(loader.loadTestsFromTestCase(TestConfiguration))

    # Run with verbosity
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
