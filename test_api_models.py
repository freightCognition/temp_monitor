"""
Unit tests for api_models validation functions.

Tests validate_webhook_config() and validate_thresholds() functions
that perform server-side validation beyond Flask-RESTX model constraints.
"""

import unittest
from api_models import validate_webhook_config, validate_thresholds


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

    def test_valid_config_none_values(self):
        """Config with None values is valid (skipped during validation)."""
        config = {'retry_count': None, 'retry_delay': None, 'timeout': None}
        is_valid, error = validate_webhook_config(config)
        self.assertTrue(is_valid)
        self.assertEqual(error, '')

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


if __name__ == '__main__':
    unittest.main()
