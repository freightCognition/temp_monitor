#!/usr/bin/env python3
"""
Test script for webhook functionality

This script tests the webhook service without requiring the full Flask app or hardware.
Uses unittest.mock to capture payloads and verify Slack message structure.
"""

import sys
import unittest
from unittest.mock import patch, MagicMock
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
        """Disabled thresholds (None) should not trigger alerts"""
        thresholds = AlertThresholds(
            temp_min_c=None,
            temp_max_c=30.0,
            humidity_min=None,
            humidity_max=80.0
        )
        service = WebhookService(alert_thresholds=thresholds)

        alerts = service.check_and_alert(10.0, 25.0, "2025-12-30 12:00:00")

        self.assertNotIn('temp_low', alerts)
        self.assertNotIn('humidity_low', alerts)


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
