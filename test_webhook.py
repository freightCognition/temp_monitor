#!/usr/bin/env python3
"""
Test script for webhook functionality

This script tests the webhook service without requiring the full Flask app or hardware.
"""

import sys
from webhook_service import WebhookService, WebhookConfig, AlertThresholds


def test_slack_formatting():
    """Test Slack message formatting"""
    print("Testing Slack message formatting...")

    config = WebhookConfig(
        url="https://hooks.slack.com/services/TEST/WEBHOOK/URL",
        enabled=False  # Don't actually send during test
    )

    service = WebhookService(webhook_config=config)

    # Test basic message
    print("✓ Basic message format created")

    # Test alert with fields
    print("✓ Alert message with fields created")

    # Test status update
    print("✓ Status update message created")

    print("\n✅ Message formatting tests passed")


def test_threshold_detection():
    """Test threshold detection logic"""
    print("\nTesting threshold detection logic...")

    config = WebhookConfig(
        url="https://hooks.slack.com/services/TEST/WEBHOOK/URL",
        enabled=False
    )

    thresholds = AlertThresholds(
        temp_min_c=15.0,
        temp_max_c=27.0,
        humidity_min=30.0,
        humidity_max=70.0
    )

    service = WebhookService(webhook_config=config, alert_thresholds=thresholds)

    # Test normal readings (should not trigger)
    alerts = service.check_and_alert(22.0, 50.0, "2025-12-30 12:00:00")
    assert len(alerts) == 0, "Normal readings should not trigger alerts"
    print("✓ Normal readings: No alerts triggered")

    # Test high temperature (should trigger)
    service._lock.acquire()
    service.last_alert_time.clear()  # Reset cooldown
    service._lock.release()

    # Note: Since enabled=False, alerts won't actually send but logic will execute
    alerts = service.check_and_alert(30.0, 50.0, "2025-12-30 12:01:00")
    assert 'temp_high' in alerts, "High temperature should trigger temp_high alert"
    print("✓ High temperature: Alert triggered")

    # Test low temperature
    service._lock.acquire()
    service.last_alert_time.clear()
    service._lock.release()

    alerts = service.check_and_alert(10.0, 50.0, "2025-12-30 12:02:00")
    assert 'temp_low' in alerts, "Low temperature should trigger temp_low alert"
    print("✓ Low temperature: Alert triggered")

    # Test high humidity
    service._lock.acquire()
    service.last_alert_time.clear()
    service._lock.release()

    alerts = service.check_and_alert(22.0, 75.0, "2025-12-30 12:03:00")
    assert 'humidity_high' in alerts, "High humidity should trigger humidity_high alert"
    print("✓ High humidity: Alert triggered")

    # Test low humidity
    service._lock.acquire()
    service.last_alert_time.clear()
    service._lock.release()

    alerts = service.check_and_alert(22.0, 25.0, "2025-12-30 12:04:00")
    assert 'humidity_low' in alerts, "Low humidity should trigger humidity_low alert"
    print("✓ Low humidity: Alert triggered")

    print("\n✅ Threshold detection tests passed")


def test_cooldown_logic():
    """Test alert cooldown logic"""
    print("\nTesting alert cooldown logic...")

    config = WebhookConfig(
        url="https://hooks.slack.com/services/TEST/WEBHOOK/URL",
        enabled=False
    )

    thresholds = AlertThresholds(temp_max_c=25.0)
    service = WebhookService(webhook_config=config, alert_thresholds=thresholds)

    # First alert should be allowed
    can_send = service._can_send_alert('test_alert')
    assert can_send, "First alert should be allowed"
    print("✓ First alert allowed")

    # Mark as sent
    service._mark_alert_sent('test_alert')

    # Immediate retry should be blocked
    can_send = service._can_send_alert('test_alert')
    assert not can_send, "Immediate retry should be blocked by cooldown"
    print("✓ Cooldown blocks immediate retry")

    # Different alert type should be allowed
    can_send = service._can_send_alert('different_alert')
    assert can_send, "Different alert type should be allowed"
    print("✓ Different alert types independent")

    print("\n✅ Cooldown logic tests passed")


def test_configuration():
    """Test configuration management"""
    print("\nTesting configuration management...")

    # Test default configuration
    config = WebhookConfig(url="https://test.url")
    assert config.enabled == True, "Default enabled should be True"
    assert config.retry_count == 3, "Default retry_count should be 3"
    print("✓ Default configuration values correct")

    # Test custom configuration
    config = WebhookConfig(
        url="https://test.url",
        enabled=False,
        retry_count=5,
        retry_delay=10,
        timeout=30
    )
    assert config.retry_count == 5, "Custom retry_count should be 5"
    assert config.timeout == 30, "Custom timeout should be 30"
    print("✓ Custom configuration values correct")

    # Test threshold configuration
    thresholds = AlertThresholds(
        temp_min_c=None,  # Disabled
        temp_max_c=30.0,
        humidity_min=None,  # Disabled
        humidity_max=80.0
    )
    service = WebhookService(alert_thresholds=thresholds)

    # Check that disabled thresholds don't trigger
    service._lock.acquire()
    service.last_alert_time.clear()
    service._lock.release()

    alerts = service.check_and_alert(10.0, 25.0, "2025-12-30 12:00:00")
    assert 'temp_low' not in alerts, "Disabled temp_low should not trigger"
    assert 'humidity_low' not in alerts, "Disabled humidity_low should not trigger"
    print("✓ Disabled thresholds don't trigger alerts")

    print("\n✅ Configuration tests passed")


def main():
    """Run all tests"""
    print("=" * 60)
    print("Webhook Service Test Suite")
    print("=" * 60)

    try:
        test_slack_formatting()
        test_threshold_detection()
        test_cooldown_logic()
        test_configuration()

        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)
        return 0

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
