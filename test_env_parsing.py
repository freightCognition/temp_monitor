#!/usr/bin/env python3
"""
Table-driven tests for _parse_env_bool and _parse_env_number (temp_monitor.py).

_parse_env_bool has NO direct test anywhere in this repo despite being the
entire point of the env-parsing refactor described in its own docstring:
USE_MOCK_SENSOR, WEBHOOK_ENABLED, and the STATUS_UPDATE_* flags were
previously parsed ad hoc and inconsistently (e.g. WEBHOOK_ENABLED=yes
silently disabled webhooks because that code path only ever compared
against the literal string 'true'). This file closes that gap.

It also covers Fix 1's regression on _parse_env_number: a SET-BUT-EMPTY
numeric var (e.g. `ALERT_TEMP_MIN_C=` in .env) used to reach
os.getenv(var_name, default) as '' -- the default only applies when the key
is entirely ABSENT -- and float('') raised, crashing the whole process at
import. The fix makes empty mean "use the default", matching
_parse_env_bool's existing behavior.
"""
import os
import unittest

# Sets BEARER_TOKEN and mocks sense_hat; MUST precede importing temp_monitor.
from test_support import run_fresh_import

import temp_monitor  # noqa: E402


class TestParseEnvBool(unittest.TestCase):
    """Direct, in-process tests of temp_monitor._parse_env_bool."""

    TRUTHY = ('1', 'true', 'yes', 'on', 'TRUE', 'Yes', 'ON', 'True')
    FALSY = ('0', 'false', 'no', 'off', 'FALSE', 'No', 'OFF', 'False')

    def _set(self, value):
        if value is None:
            os.environ.pop('TEST_BOOL_VAR', None)
        else:
            os.environ['TEST_BOOL_VAR'] = value

    def tearDown(self):
        os.environ.pop('TEST_BOOL_VAR', None)

    def test_truthy_values_accepted_case_insensitively(self):
        for value in self.TRUTHY:
            with self.subTest(value=value):
                self._set(value)
                self.assertTrue(temp_monitor._parse_env_bool('TEST_BOOL_VAR', False))

    def test_falsy_values_accepted_case_insensitively(self):
        for value in self.FALSY:
            with self.subTest(value=value):
                self._set(value)
                self.assertFalse(temp_monitor._parse_env_bool('TEST_BOOL_VAR', True))

    def test_unset_uses_default(self):
        self._set(None)
        self.assertTrue(temp_monitor._parse_env_bool('TEST_BOOL_VAR', True))
        self.assertFalse(temp_monitor._parse_env_bool('TEST_BOOL_VAR', False))

    def test_empty_uses_default(self):
        self._set('')
        self.assertTrue(temp_monitor._parse_env_bool('TEST_BOOL_VAR', True))
        self.assertFalse(temp_monitor._parse_env_bool('TEST_BOOL_VAR', False))

    def test_whitespace_only_uses_default(self):
        self._set('   ')
        self.assertTrue(temp_monitor._parse_env_bool('TEST_BOOL_VAR', True))
        self.assertFalse(temp_monitor._parse_env_bool('TEST_BOOL_VAR', False))

    def test_invalid_value_raises_naming_the_variable(self):
        self._set('maybe')
        with self.assertRaises(RuntimeError) as cm:
            temp_monitor._parse_env_bool('TEST_BOOL_VAR', False)
        self.assertIn('TEST_BOOL_VAR', str(cm.exception))
        self.assertIn('maybe', str(cm.exception))


class TestParseEnvNumber(unittest.TestCase):
    """Direct, in-process tests of temp_monitor._parse_env_number."""

    def _set(self, value):
        if value is None:
            os.environ.pop('TEST_NUM_VAR', None)
        else:
            os.environ['TEST_NUM_VAR'] = value

    def tearDown(self):
        os.environ.pop('TEST_NUM_VAR', None)

    def test_valid_int(self):
        self._set('42')
        self.assertEqual(temp_monitor._parse_env_number('TEST_NUM_VAR', '0', int), 42)

    def test_valid_float(self):
        self._set('3.5')
        self.assertEqual(temp_monitor._parse_env_number('TEST_NUM_VAR', '0', float), 3.5)

    def test_unset_uses_default(self):
        self._set(None)
        self.assertEqual(temp_monitor._parse_env_number('TEST_NUM_VAR', '15.0', float), 15.0)

    def test_empty_uses_default(self):
        """Fix 1: a SET-BUT-EMPTY numeric var must use the default instead
        of crashing on cast('')."""
        self._set('')
        self.assertEqual(temp_monitor._parse_env_number('TEST_NUM_VAR', '15.0', float), 15.0)

    def test_whitespace_only_uses_default(self):
        self._set('   ')
        self.assertEqual(temp_monitor._parse_env_number('TEST_NUM_VAR', '15.0', float), 15.0)

    def test_invalid_value_raises_naming_the_variable(self):
        self._set('not_a_number')
        with self.assertRaises(RuntimeError) as cm:
            temp_monitor._parse_env_number('TEST_NUM_VAR', '0', float)
        self.assertIn('TEST_NUM_VAR', str(cm.exception))
        self.assertIn('not_a_number', str(cm.exception))


class TestParseEnvNumberEmptyAtImport(unittest.TestCase):
    """Import-time case for Fix 1: ALERT_TEMP_MIN_C= (present, empty) must
    import cleanly and yield the documented default (15.0), not crash the
    whole process. Uses run_fresh_import because this is specifically about
    module-level initialization order, not just the helper function called
    in isolation."""

    def test_empty_alert_temp_min_c_imports_cleanly_with_default(self):
        state = run_fresh_import(
            probe=(
                "{'temp_min_c': tm.webhook_service.alert_thresholds.temp_min_c "
                "if tm.webhook_service else None}"
            ),
            env_overrides={
                'SLACK_WEBHOOK_URL': 'https://hooks.slack.com/services/T00/B00/XXX',
                'ALERT_TEMP_MIN_C': '',
            },
            scrub=('ALERT_TEMP_MIN_C', 'SLACK_WEBHOOK_URL'),
        )
        self.assertEqual(state['temp_min_c'], 15.0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
