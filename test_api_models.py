"""
Unit tests for api_models validation functions.

Tests validate_webhook_config() and validate_thresholds() functions
that perform server-side validation beyond Flask-RESTX model constraints.
"""

import unittest
from api_models import validate_webhook_config, validate_thresholds, error_response
from webhook_service import AlertThresholds


class TestValidateWebhookConfig(unittest.TestCase):
    """Tests for validate_webhook_config function."""

    def test_valid_config_all_fields(self):
        """Valid config with all fields in range returns True."""
        config = {'retry_count': 5, 'retry_delay': 30, 'timeout': 60}
        is_valid, error = validate_webhook_config(config)
        self.assertTrue(is_valid)
        self.assertEqual(error, '')

    def test_valid_config_minimum_values(self):
        """Valid config with minimum allowed values."""
        config = {'retry_count': 1, 'retry_delay': 1, 'timeout': 5}
        is_valid, error = validate_webhook_config(config)
        self.assertTrue(is_valid)
        self.assertEqual(error, '')

    def test_valid_config_maximum_values(self):
        """Valid config with maximum allowed values."""
        config = {'retry_count': 10, 'retry_delay': 60, 'timeout': 120}
        is_valid, error = validate_webhook_config(config)
        self.assertTrue(is_valid)
        self.assertEqual(error, '')

    def test_valid_config_empty(self):
        """Empty config is valid (all fields optional)."""
        config = {}
        is_valid, error = validate_webhook_config(config)
        self.assertTrue(is_valid)
        self.assertEqual(error, '')

    def test_invalid_config_explicit_null_values(self):
        """V6: explicit null for retry_count/retry_delay/timeout is rejected
        (an absent key is a partial update; a present null is not)."""
        for field in ('retry_count', 'retry_delay', 'timeout'):
            with self.subTest(field=field):
                is_valid, error = validate_webhook_config({field: None})
                self.assertFalse(is_valid)
                self.assertIn(field, error)

    def test_invalid_retry_count_too_low(self):
        """retry_count below 1 is invalid."""
        config = {'retry_count': 0}
        is_valid, error = validate_webhook_config(config)
        self.assertFalse(is_valid)
        self.assertIn('retry_count', error)

    def test_invalid_retry_count_too_high(self):
        """retry_count above 10 is invalid."""
        config = {'retry_count': 11}
        is_valid, error = validate_webhook_config(config)
        self.assertFalse(is_valid)
        self.assertIn('retry_count', error)

    def test_invalid_retry_delay_too_low(self):
        """retry_delay below 1 is invalid."""
        config = {'retry_delay': 0}
        is_valid, error = validate_webhook_config(config)
        self.assertFalse(is_valid)
        self.assertIn('retry_delay', error)

    def test_invalid_retry_delay_too_high(self):
        """retry_delay above 60 is invalid."""
        config = {'retry_delay': 61}
        is_valid, error = validate_webhook_config(config)
        self.assertFalse(is_valid)
        self.assertIn('retry_delay', error)

    def test_invalid_timeout_too_low(self):
        """timeout below 5 is invalid."""
        config = {'timeout': 4}
        is_valid, error = validate_webhook_config(config)
        self.assertFalse(is_valid)
        self.assertIn('timeout', error)

    def test_invalid_timeout_too_high(self):
        """timeout above 120 is invalid."""
        config = {'timeout': 121}
        is_valid, error = validate_webhook_config(config)
        self.assertFalse(is_valid)
        self.assertIn('timeout', error)

    def test_valid_url(self):
        """Valid URL with scheme and host passes validation."""
        config = {'url': 'https://hooks.slack.com/services/T00/B00/xxx'}
        is_valid, error = validate_webhook_config(config)
        self.assertTrue(is_valid)
        self.assertEqual(error, '')

    def test_valid_url_http(self):
        """HTTP URL is valid (not just HTTPS)."""
        config = {'url': 'http://example.com/webhook'}
        is_valid, error = validate_webhook_config(config)
        self.assertTrue(is_valid)
        self.assertEqual(error, '')

    def test_invalid_url_empty_string(self):
        """Empty string URL is invalid."""
        config = {'url': ''}
        is_valid, error = validate_webhook_config(config)
        self.assertFalse(is_valid)
        self.assertIn('url', error)

    def test_invalid_url_whitespace_only(self):
        """Whitespace-only URL is invalid."""
        config = {'url': '   '}
        is_valid, error = validate_webhook_config(config)
        self.assertFalse(is_valid)
        self.assertIn('url', error)

    def test_invalid_url_no_scheme(self):
        """URL without scheme is invalid."""
        config = {'url': 'hooks.slack.com/services/T00/B00/xxx'}
        is_valid, error = validate_webhook_config(config)
        self.assertFalse(is_valid)
        self.assertIn('scheme', error)

    def test_invalid_url_no_host(self):
        """URL without host is invalid."""
        config = {'url': 'https://'}
        is_valid, error = validate_webhook_config(config)
        self.assertFalse(is_valid)
        self.assertIn('scheme', error)

    def test_url_none_is_invalid(self):
        """V6: explicit null URL is rejected (it would silently wipe out an
        existing webhook URL if allowed through to storage)."""
        config = {'url': None}
        is_valid, error = validate_webhook_config(config)
        self.assertFalse(is_valid)
        self.assertIn('URL required', error)

    def test_url_missing_is_valid(self):
        """Missing URL key is valid (allows partial updates)."""
        config = {'retry_count': 5}
        is_valid, error = validate_webhook_config(config)
        self.assertTrue(is_valid)
        self.assertEqual(error, '')

    def test_invalid_url_not_string(self):
        """Non-string URL is invalid."""
        config = {'url': 12345}
        is_valid, error = validate_webhook_config(config)
        self.assertFalse(is_valid)
        self.assertIn('url', error)


class TestValidateThresholds(unittest.TestCase):
    """Tests for validate_thresholds function."""

    def test_valid_thresholds_all_fields(self):
        """Valid thresholds with all fields properly ordered."""
        thresholds = {
            'temp_min_c': 15.0,
            'temp_max_c': 27.0,
            'humidity_min': 30.0,
            'humidity_max': 70.0
        }
        is_valid, error = validate_thresholds(thresholds)
        self.assertTrue(is_valid)
        self.assertEqual(error, '')

    def test_valid_thresholds_empty(self):
        """Empty thresholds is valid (all fields optional)."""
        thresholds = {}
        is_valid, error = validate_thresholds(thresholds)
        self.assertTrue(is_valid)
        self.assertEqual(error, '')

    def test_valid_thresholds_none_values(self):
        """Thresholds with None values are valid (skipped)."""
        thresholds = {
            'temp_min_c': None,
            'temp_max_c': None,
            'humidity_min': None,
            'humidity_max': None
        }
        is_valid, error = validate_thresholds(thresholds)
        self.assertTrue(is_valid)
        self.assertEqual(error, '')

    def test_valid_thresholds_only_temp(self):
        """Valid when only temperature thresholds provided."""
        thresholds = {'temp_min_c': 10.0, 'temp_max_c': 30.0}
        is_valid, error = validate_thresholds(thresholds)
        self.assertTrue(is_valid)
        self.assertEqual(error, '')

    def test_valid_thresholds_only_humidity(self):
        """Valid when only humidity thresholds provided."""
        thresholds = {'humidity_min': 20.0, 'humidity_max': 80.0}
        is_valid, error = validate_thresholds(thresholds)
        self.assertTrue(is_valid)
        self.assertEqual(error, '')

    def test_valid_thresholds_partial_pairs(self):
        """Valid when only one of a pair is provided."""
        thresholds = {'temp_min_c': 10.0, 'humidity_max': 80.0}
        is_valid, error = validate_thresholds(thresholds)
        self.assertTrue(is_valid)
        self.assertEqual(error, '')

    def test_invalid_temp_min_equals_max(self):
        """temp_min_c equal to temp_max_c is invalid."""
        thresholds = {'temp_min_c': 20.0, 'temp_max_c': 20.0}
        is_valid, error = validate_thresholds(thresholds)
        self.assertFalse(is_valid)
        self.assertIn('temp_min_c', error)

    def test_invalid_temp_min_greater_than_max(self):
        """temp_min_c greater than temp_max_c is invalid."""
        thresholds = {'temp_min_c': 30.0, 'temp_max_c': 20.0}
        is_valid, error = validate_thresholds(thresholds)
        self.assertFalse(is_valid)
        self.assertIn('temp_min_c', error)

    def test_invalid_humidity_min_equals_max(self):
        """humidity_min equal to humidity_max is invalid."""
        thresholds = {'humidity_min': 50.0, 'humidity_max': 50.0}
        is_valid, error = validate_thresholds(thresholds)
        self.assertFalse(is_valid)
        self.assertIn('humidity_min', error)

    def test_invalid_humidity_min_greater_than_max(self):
        """humidity_min greater than humidity_max is invalid."""
        thresholds = {'humidity_min': 80.0, 'humidity_max': 30.0}
        is_valid, error = validate_thresholds(thresholds)
        self.assertFalse(is_valid)
        self.assertIn('humidity_min', error)

    def test_valid_thresholds_with_negative_temps(self):
        """Valid with negative temperature values (e.g., freezer monitoring)."""
        thresholds = {'temp_min_c': -30.0, 'temp_max_c': -10.0}
        is_valid, error = validate_thresholds(thresholds)
        self.assertTrue(is_valid)
        self.assertEqual(error, '')

    def test_valid_temp_invalid_humidity(self):
        """Valid temp thresholds but invalid humidity still fails."""
        thresholds = {
            'temp_min_c': 15.0,
            'temp_max_c': 27.0,
            'humidity_min': 80.0,
            'humidity_max': 30.0
        }
        is_valid, error = validate_thresholds(thresholds)
        self.assertFalse(is_valid)
        self.assertIn('humidity_min', error)


class TestWebhookNumericTypeValidation(unittest.TestCase):
    """V1: table-driven type/range checks for webhook numeric fields.

    Every case must come back as a clean (False, message) tuple -- never
    raise a bare TypeError/AttributeError, and never silently accept a
    value that would break downstream code (bools, floats).
    """

    NUMERIC_FIELDS = {
        'retry_count': (1, 10),
        'retry_delay': (1, 60),
        'timeout': (5, 120),
    }

    INVALID_TYPE_CASES = [
        ('string_digit', '5'),
        ('float', 3.7),
        ('bool_true', True),
        ('bool_false', False),
        ('list', [5]),
        ('dict', {'value': 5}),
    ]

    def test_invalid_types_rejected_cleanly(self):
        for field, (min_val, max_val) in self.NUMERIC_FIELDS.items():
            for case_name, value in self.INVALID_TYPE_CASES:
                with self.subTest(field=field, case=case_name, value=value):
                    is_valid, error = validate_webhook_config({field: value})
                    self.assertFalse(is_valid)
                    self.assertIn(field, error)

    def test_out_of_range_values_rejected(self):
        for field, (min_val, max_val) in self.NUMERIC_FIELDS.items():
            for case_name, value in [('negative', -1), ('zero', 0), ('too_high', max_val + 1)]:
                if case_name == 'zero' and min_val <= 0:
                    continue
                with self.subTest(field=field, case=case_name, value=value):
                    is_valid, error = validate_webhook_config({field: value})
                    self.assertFalse(is_valid)
                    self.assertIn(field, error)

    def test_float_that_would_pass_range_check_is_still_rejected(self):
        """Regression: 3.7 used to pass `1 <= 3.7 <= 10` and get stored,
        then crash inside `range(3.7)` in the sensor thread later."""
        is_valid, error = validate_webhook_config({'retry_count': 3.7})
        self.assertFalse(is_valid)
        self.assertIn('retry_count', error)

    def test_bool_no_longer_silently_accepted(self):
        """Regression: `1 <= True <= 10` is True in Python, so a bool used
        to sneak past the old range check."""
        is_valid, error = validate_webhook_config({'retry_count': True})
        self.assertFalse(is_valid)


class TestNonDictContainers(unittest.TestCase):
    """V2: non-dict `webhook`/`thresholds` payloads must not crash."""

    def test_webhook_string_container(self):
        is_valid, error = validate_webhook_config('my url')
        self.assertFalse(is_valid)
        self.assertIn('object', error)

    def test_webhook_list_container(self):
        is_valid, error = validate_webhook_config(['a'])
        self.assertFalse(is_valid)
        self.assertIn('object', error)

    def test_thresholds_string_container(self):
        is_valid, error = validate_thresholds('x')
        self.assertFalse(is_valid)
        self.assertIn('object', error)

    def test_thresholds_list_container(self):
        is_valid, error = validate_thresholds(['x'])
        self.assertFalse(is_valid)
        self.assertIn('object', error)


class TestThresholdAbsoluteRanges(unittest.TestCase):
    """V3: documented absolute ranges (-50..100C, 0..100%) are enforced."""

    def test_temp_min_below_absolute_floor(self):
        is_valid, error = validate_thresholds({'temp_min_c': -9999})
        self.assertFalse(is_valid)
        self.assertIn('temp_min_c', error)

    def test_temp_max_above_absolute_ceiling(self):
        is_valid, error = validate_thresholds({'temp_max_c': 9999})
        self.assertFalse(is_valid)
        self.assertIn('temp_max_c', error)

    def test_humidity_min_below_zero(self):
        is_valid, error = validate_thresholds({'humidity_min': -50})
        self.assertFalse(is_valid)
        self.assertIn('humidity_min', error)

    def test_humidity_max_above_hundred(self):
        is_valid, error = validate_thresholds({'humidity_max': 500})
        self.assertFalse(is_valid)
        self.assertIn('humidity_max', error)

    def test_all_out_of_range_together_rejected(self):
        """Reproduces the exact payload from the bug report."""
        payload = {
            'temp_min_c': -9999,
            'temp_max_c': 9999,
            'humidity_min': -50,
            'humidity_max': 500,
        }
        is_valid, error = validate_thresholds(payload)
        self.assertFalse(is_valid)


class TestThresholdTypeConfusion(unittest.TestCase):
    """V4: non-numeric threshold values are rejected instead of crashing
    the sensor loop or the cross-field comparison later."""

    def test_string_temp_min_rejected(self):
        is_valid, error = validate_thresholds({'temp_min_c': 'hot'})
        self.assertFalse(is_valid)
        self.assertIn('temp_min_c', error)

    def test_string_vs_number_pair_rejected_before_comparison(self):
        """Old code raised a bare TypeError comparing 'abc' >= 30 here."""
        is_valid, error = validate_thresholds({'temp_min_c': 'abc', 'temp_max_c': 30})
        self.assertFalse(is_valid)
        self.assertIn('temp_min_c', error)

    def test_bool_threshold_rejected(self):
        is_valid, error = validate_thresholds({'humidity_min': True})
        self.assertFalse(is_valid)


class TestThresholdCrossFieldWithCurrent(unittest.TestCase):
    """V5: when current_thresholds is supplied, the min/max check validates
    the RESULTING merged config, not just the payload in isolation."""

    def test_default_behavior_unchanged_when_current_not_supplied(self):
        """PUT {temp_min_c: 40} alone, with no current_thresholds passed,
        must behave exactly as before: no cross-check fires."""
        is_valid, error = validate_thresholds({'temp_min_c': 40})
        self.assertTrue(is_valid)
        self.assertEqual(error, '')

    def test_merged_check_catches_min_above_stored_max_dict(self):
        current = {'temp_min_c': 15.0, 'temp_max_c': 32.0}
        is_valid, error = validate_thresholds({'temp_min_c': 40}, current_thresholds=current)
        self.assertFalse(is_valid)
        self.assertIn('temp_min_c', error)

    def test_merged_check_accepts_valid_partial_update_dict(self):
        current = {'temp_min_c': 15.0, 'temp_max_c': 32.0}
        is_valid, error = validate_thresholds({'temp_min_c': 20}, current_thresholds=current)
        self.assertTrue(is_valid)
        self.assertEqual(error, '')

    def test_merged_check_works_against_alert_thresholds_object(self):
        """current_thresholds may be the AlertThresholds dataclass directly,
        not just a dict, so callers don't need to unpack it manually."""
        current = AlertThresholds(temp_min_c=15.0, temp_max_c=32.0, humidity_min=20.0, humidity_max=70.0)
        is_valid, error = validate_thresholds({'temp_min_c': 40}, current_thresholds=current)
        self.assertFalse(is_valid)
        self.assertIn('temp_min_c', error)

    def test_merged_check_humidity(self):
        current = {'humidity_min': 20.0, 'humidity_max': 70.0}
        is_valid, error = validate_thresholds({'humidity_min': 90}, current_thresholds=current)
        self.assertFalse(is_valid)
        self.assertIn('humidity_min', error)

    def test_explicit_null_to_clear_agrees_with_merge(self):
        """Fix 8, exact scenario from the bug report: stored temp_min_c=15,
        temp_max_c=32; payload clears max (null) while raising min to 20.
        The merge produces temp_max_c=None, so no cross-check should fire
        -- this must be VALID.

        Note: for these particular numbers the old buggy `effective()`
        also happens to return valid here (20 still compares below the
        stale fallback max of 32), so this case alone would not have
        caught the bug -- see
        test_explicit_null_to_clear_would_have_failed_before_fix below for
        the case that actually distinguishes buggy from fixed behavior.
        Kept here because it's the literal reported scenario.
        """
        current = {'temp_min_c': 15.0, 'temp_max_c': 32.0}
        payload = {'temp_max_c': None, 'temp_min_c': 20}
        is_valid, error = validate_thresholds(payload, current_thresholds=current)
        self.assertTrue(is_valid)
        self.assertEqual(error, '')

    def test_explicit_null_to_clear_would_have_failed_before_fix(self):
        """Fix 8 regression: temp_monitor.py's actual merge
        (`if field in threshold_data: return threshold_data[field]`)
        treats a PRESENT key as authoritative even when its value is JSON
        null -- that's how a field gets cleared. The old `effective()` here
        instead fell back to current_thresholds whenever the payload value
        was None, so validation disagreed with what actually gets applied.

        Stored: temp_min_c=15, temp_max_c=32. Payload clears min (null)
        while dropping max to 10 (below the stale stored min, but not
        below the cleared/None min). The merge produces temp_min_c=None,
        so no cross-check should fire -- this must be VALID.

        Before the fix: effective('temp_min_c') fell back to the stale
        stored 15.0 instead of None, so 15.0 >= 10 incorrectly failed
        validation with "temp_min_c must be less than temp_max_c" -- a
        spurious 400 naming the very field the operator just cleared.
        """
        current = {'temp_min_c': 15.0, 'temp_max_c': 32.0}
        payload = {'temp_min_c': None, 'temp_max_c': 10}
        is_valid, error = validate_thresholds(payload, current_thresholds=current)
        self.assertTrue(is_valid)
        self.assertEqual(error, '')

    def test_explicit_null_to_clear_still_rejects_when_result_invalid(self):
        """Sanity check for the same fix: clearing a field that is NOT
        involved in the conflict must not mask a genuine cross-field
        violation. Stored: temp_min_c=15, temp_max_c=32. Payload clears
        humidity_max (unrelated) while pushing temp_min_c above the
        stored temp_max_c -- this must still be INVALID.
        """
        current = {'temp_min_c': 15.0, 'temp_max_c': 32.0}
        payload = {'humidity_max': None, 'temp_min_c': 40}
        is_valid, error = validate_thresholds(payload, current_thresholds=current)
        self.assertFalse(is_valid)
        self.assertIn('temp_min_c', error)


class TestErrorResponseModel(unittest.TestCase):
    """V7: the documented ErrorResponse model must match what the API
    actually returns -- 'message' from webhooks_ns.abort() (400s), and
    'error'/'error_id' from the manual 500 handler in temp_monitor.py.
    The old model documented {error, details}, neither of which the
    abort() path (which emits {message: ...}, per test_webhook_api.py)
    or the 500 path (which emits error_id) ever produced."""

    def test_model_declares_message_field(self):
        self.assertIn('message', error_response)

    def test_model_declares_error_and_error_id_fields(self):
        self.assertIn('error', error_response)
        self.assertIn('error_id', error_response)

    def test_model_no_longer_declares_unused_details_field(self):
        self.assertNotIn('details', error_response)


if __name__ == '__main__':
    unittest.main()
