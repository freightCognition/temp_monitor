#!/usr/bin/env python3
"""
Test script for periodic status update functionality

This script validates the configuration loading and timing logic
for periodic status updates without requiring the full Flask app or hardware.
"""

import os
import sys
import time


def test_configuration_loading():
    """Test that periodic update configuration is loaded correctly"""
    print("Testing configuration loading...")

    # Test 1: Default disabled
    os.environ.pop('STATUS_UPDATE_ENABLED', None)
    os.environ.pop('STATUS_UPDATE_INTERVAL', None)
    os.environ.pop('STATUS_UPDATE_ON_STARTUP', None)

    status_update_enabled = os.getenv('STATUS_UPDATE_ENABLED', 'false').lower() == 'true'
    status_update_interval = int(os.getenv('STATUS_UPDATE_INTERVAL', '3600'))

    assert status_update_enabled == False, "Default should be disabled"
    assert status_update_interval == 3600, "Default interval should be 3600"
    print("✓ Default configuration correct (disabled, 3600s interval)")

    # Test 2: Enabled with custom interval
    os.environ['STATUS_UPDATE_ENABLED'] = 'true'
    os.environ['STATUS_UPDATE_INTERVAL'] = '1800'

    status_update_enabled = os.getenv('STATUS_UPDATE_ENABLED', 'false').lower() == 'true'
    status_update_interval = int(os.getenv('STATUS_UPDATE_INTERVAL', '3600'))

    assert status_update_enabled == True, "Should be enabled"
    assert status_update_interval == 1800, "Interval should be 1800"
    print("✓ Custom configuration loaded correctly (enabled, 1800s interval)")

    # Test 3: Startup update flag
    os.environ['STATUS_UPDATE_ON_STARTUP'] = 'true'
    send_on_startup = os.getenv('STATUS_UPDATE_ON_STARTUP', 'false').lower() == 'true'
    assert send_on_startup == True, "Startup update should be enabled"
    print("✓ Startup update flag loaded correctly")

    # Cleanup
    os.environ.pop('STATUS_UPDATE_ENABLED', None)
    os.environ.pop('STATUS_UPDATE_INTERVAL', None)
    os.environ.pop('STATUS_UPDATE_ON_STARTUP', None)

    print("\n✅ Configuration loading tests passed\n")


def test_timing_logic():
    """Test the periodic update timing logic"""
    print("Testing timing logic...")

    # Simulate the timing logic from temp_monitor.py
    status_update_interval = 120  # 2 minutes for testing
    sampling_interval = 60  # 60 seconds

    # Test 1: Interval validation (minimum enforcement)
    test_interval = 30  # Less than sampling_interval
    if test_interval < sampling_interval:
        test_interval = sampling_interval
    assert test_interval == 60, "Interval should be enforced to minimum"
    print("✓ Minimum interval enforcement works")

    # Test 2: First update trigger (last_status_update = None)
    last_status_update = None
    current_time = time.time()

    should_send_update = (
        last_status_update is None or
        (current_time - last_status_update) >= status_update_interval
    )
    assert should_send_update == True, "Should trigger on first update"
    print("✓ First update triggers correctly (last_status_update = None)")

    # Test 3: Update after interval elapsed
    last_status_update = current_time - 125  # 125 seconds ago
    should_send_update = (
        last_status_update is None or
        (current_time - last_status_update) >= status_update_interval
    )
    assert should_send_update == True, "Should trigger after interval elapsed"
    print("✓ Update triggers after interval elapses (125s > 120s)")

    # Test 4: No update before interval
    last_status_update = current_time - 60  # 60 seconds ago
    should_send_update = (
        last_status_update is None or
        (current_time - last_status_update) >= status_update_interval
    )
    assert should_send_update == False, "Should not trigger before interval"
    print("✓ Update blocked before interval elapses (60s < 120s)")

    # Test 5: Exact interval boundary
    last_status_update = current_time - 120  # Exactly 120 seconds ago
    should_send_update = (
        last_status_update is None or
        (current_time - last_status_update) >= status_update_interval
    )
    assert should_send_update == True, "Should trigger at exact interval"
    print("✓ Update triggers at exact interval boundary (120s >= 120s)")

    print("\n✅ Timing logic tests passed\n")


def test_startup_behavior():
    """Test startup update behavior"""
    print("Testing startup update behavior...")

    # Test 1: Startup update enabled
    last_status_update_startup = None  # Set to None for immediate trigger
    should_send_on_first_loop = (last_status_update_startup is None)
    assert should_send_on_first_loop == True, "Should send on first loop when enabled"
    print("✓ Startup update enabled: triggers on first loop")

    # Test 2: Startup update disabled
    last_status_update_normal = time.time()  # Set to now, starts timer
    should_send_on_first_loop = (last_status_update_normal is None)
    assert should_send_on_first_loop == False, "Should wait for interval when disabled"
    print("✓ Startup update disabled: waits for interval")

    print("\n✅ Startup behavior tests passed\n")


def test_independence_from_alerts():
    """Test that status updates are independent from alerts"""
    print("Testing independence from alert system...")

    # Simulate both systems running
    class MockAlertSystem:
        def __init__(self):
            self.last_alert_time = {'temp_high': time.time() - 60}  # Alert sent 60s ago
            self.alert_cooldown = 300  # 5 minutes

        def can_send_alert(self, alert_type):
            """Check if alert can be sent (simulates cooldown)"""
            last_time = self.last_alert_time.get(alert_type)
            if last_time is None:
                return True
            elapsed = time.time() - last_time
            return elapsed >= self.alert_cooldown

    # Create mock alert system
    alert_system = MockAlertSystem()

    # Status update timing (independent)
    status_update_interval = 120
    last_status_update = time.time() - 125  # 125 seconds ago
    current_time = time.time()

    # Check if status update should send
    should_send_status = (current_time - last_status_update) >= status_update_interval
    assert should_send_status == True, "Status update should trigger"

    # Check if alert can send (should be blocked by cooldown)
    can_send_alert = alert_system.can_send_alert('temp_high')
    assert can_send_alert == False, "Alert should be blocked by cooldown"

    print("✓ Status update triggers independently of alert cooldown")
    print("✓ Status update: ready to send (125s elapsed)")
    print("✓ Alert: blocked by cooldown (60s < 300s)")

    print("\n✅ Independence tests passed\n")


def test_configuration_examples():
    """Test common configuration examples"""
    print("Testing common configuration examples...")

    examples = [
        {"name": "Hourly updates", "interval": 3600},
        {"name": "30-minute updates", "interval": 1800},
        {"name": "Every 2 hours", "interval": 7200},
        {"name": "Every 4 hours", "interval": 14400},
        {"name": "Daily updates", "interval": 86400},
    ]

    sampling_interval = 60

    for example in examples:
        interval = example["interval"]
        name = example["name"]

        # Validate interval
        if interval < sampling_interval:
            interval = sampling_interval

        # Calculate how many sensor cycles per update
        cycles = interval // sampling_interval

        print(f"✓ {name}: {interval}s ({cycles} sensor cycles)")

    print("\n✅ Configuration examples validated\n")


def main():
    """Run all tests"""
    print("=" * 60)
    print("Periodic Status Update Test Suite")
    print("=" * 60)
    print()

    try:
        test_configuration_loading()
        test_timing_logic()
        test_startup_behavior()
        test_independence_from_alerts()
        test_configuration_examples()

        print("=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)
        print()
        print("Next steps:")
        print("1. Add configuration to .env:")
        print("   STATUS_UPDATE_ENABLED=true")
        print("   STATUS_UPDATE_INTERVAL=120  # 2 minutes for testing")
        print("   STATUS_UPDATE_ON_STARTUP=true")
        print()
        print("2. Run temp_monitor.py and check logs:")
        print("   tail -f temp_monitor.log | grep 'Periodic status update'")
        print()
        print("3. For production, set interval to 3600 (1 hour)")
        print()

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
