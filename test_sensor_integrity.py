#!/usr/bin/env python3
"""
Tests for S1/S2: a local sense_hat.py stub in the repo root shadowed the
real `sense-hat` PyPI package, because the script directory is sys.path[0]
when running `python temp_monitor.py`. All sensor readings were silently
coming from the hardcoded stub (25.0C / 40.0% humidity) instead of hardware.

Fix under test:
- the stub is renamed to mock_sense_hat.py so it can never collide with
  the real package name on sys.path
- it is only importable via the explicit USE_MOCK_SENSOR env flag
- startup logs unambiguously which driver (real vs mock) was loaded and
  its module file path
"""
import os
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))


def _base_env():
    env = os.environ.copy()
    env['BEARER_TOKEN'] = 'test_token_ci'
    env.pop('USE_MOCK_SENSOR', None)
    return env


class TestNoLocalSenseHatShadow(unittest.TestCase):
    def test_no_sense_hat_stub_in_repo_root(self):
        """The repo root must not contain sense_hat.py -- that name is
        reserved for the real hardware package and would shadow it."""
        shadow_path = os.path.join(REPO_ROOT, 'sense_hat.py')
        self.assertFalse(
            os.path.exists(shadow_path),
            "sense_hat.py exists in repo root and will shadow the real "
            "sense-hat package because the script directory is sys.path[0]"
        )

    def test_mock_driver_exists_under_distinct_name(self):
        mock_path = os.path.join(REPO_ROOT, 'mock_sense_hat.py')
        self.assertTrue(os.path.exists(mock_path), "mock_sense_hat.py should exist")

    def test_default_import_does_not_shadow_real_package(self):
        """S2: with USE_MOCK_SENSOR unset, the SenseHat class temp_monitor
        ends up using must NOT originate from the repository directory --
        it must come from wherever the real 'sense_hat' package resolves on
        sys.path. Simulate the real package living outside the repo and
        assert the shadow can never silently win."""
        with tempfile.TemporaryDirectory() as fake_pkg_dir:
            fake_module = os.path.join(fake_pkg_dir, 'sense_hat.py')
            with open(fake_module, 'w') as f:
                f.write(
                    "class SenseHat:\n"
                    "    def __init__(self):\n"
                    "        pass\n"
                    "    def clear(self):\n"
                    "        pass\n"
                )

            env = _base_env()
            env['PYTHONPATH'] = fake_pkg_dir + os.pathsep + env.get('PYTHONPATH', '')
            script = (
                "import temp_monitor, inspect\n"
                "print(inspect.getfile(temp_monitor.SenseHat))\n"
            )
            result = subprocess.run(
                [sys.executable, '-c', script],
                cwd=REPO_ROOT, env=env, capture_output=True, text=True
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            loaded_from = result.stdout.strip()
            self.assertFalse(
                loaded_from.startswith(REPO_ROOT),
                f"SenseHat was loaded from the repo directory ({loaded_from}) "
                "instead of the real package -- the shadow bug is back."
            )
            self.assertEqual(os.path.realpath(loaded_from), os.path.realpath(fake_module))

    def test_mock_flag_loads_mock_driver_explicitly(self):
        env = _base_env()
        env['USE_MOCK_SENSOR'] = '1'
        script = (
            "import temp_monitor, inspect\n"
            "print(inspect.getfile(temp_monitor.SenseHat))\n"
        )
        result = subprocess.run(
            [sys.executable, '-c', script],
            cwd=REPO_ROOT, env=env, capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('mock_sense_hat.py', result.stdout)

    def test_startup_logs_which_driver_and_path(self):
        """Startup must log unambiguously which sensor driver was loaded,
        so a frozen-mock-in-production incident like this shows up in logs."""
        env = _base_env()
        env['USE_MOCK_SENSOR'] = '1'
        log_path = os.path.join(REPO_ROOT, '_test_sensor_integrity.log')
        env['LOG_FILE'] = log_path
        try:
            result = subprocess.run(
                [sys.executable, '-c', 'import temp_monitor'],
                cwd=REPO_ROOT, env=env, capture_output=True, text=True
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            with open(log_path) as f:
                content = f.read()
            self.assertIn('mock_sense_hat', content.lower())
        finally:
            if os.path.exists(log_path):
                os.remove(log_path)

    def test_existing_test_style_mock_still_works(self):
        """Other test files do sys.modules['sense_hat'] = MagicMock() before
        importing temp_monitor. Confirm the rename doesn't break that."""
        env = _base_env()
        script = (
            "import sys\n"
            "from unittest.mock import MagicMock\n"
            "sys.modules['sense_hat'] = MagicMock()\n"
            "import temp_monitor\n"
            "print('ok')\n"
        )
        result = subprocess.run(
            [sys.executable, '-c', script],
            cwd=REPO_ROOT, env=env, capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('ok', result.stdout)


if __name__ == '__main__':
    unittest.main()
