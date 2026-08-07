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
import subprocess
import sys
import unittest
from logging.handlers import RotatingFileHandler

from unittest.mock import MagicMock

sys.modules['sense_hat'] = MagicMock()

import temp_monitor  # noqa: E402


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


if __name__ == '__main__':
    unittest.main()
