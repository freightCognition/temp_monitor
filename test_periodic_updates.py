#!/usr/bin/env python3
"""
Tests for periodic status update functionality.

Unlike the previous version of this file, these tests import and exercise the
ACTUAL production code in temp_monitor.py rather than retyping its logic inline:

- The module-level env parsing / minimum-interval clamp at temp_monitor.py:106-117
  and the startup-timer initialization at temp_monitor.py:148-157 are tested by
  importing temp_monitor fresh in a subprocess with controlled environment
  variables (a true "cold start", and it sidesteps reloading the shared Flask app
  in-process).
- The periodic-update block inside update_sensor_data() at temp_monitor.py:325-351
  is tested by running that REAL function for exactly one loop iteration (see
  _run_one_iteration below), with only the sensor-reading helpers and time module
  mocked out.

Two known bugs are pinned as `@unittest.expectedFailure` tests that assert the
CORRECT behavior (see docstrings on each for the bug and file:line). They fail
today against the real bug and will start passing once temp_monitor.py is fixed.
"""

import json
import os
import subprocess
import sys
import textwrap
import time
import unittest
from unittest.mock import MagicMock

# BEARER_TOKEN must be set before importing temp_monitor: temp_monitor.py:169-175
# calls sys.exit(1) if it is missing. Set it here so this file is self-sufficient
# and doesn't depend on the caller's environment (see test_webhook_api.py:33 for
# the unreachable fallback this avoids). Note this repo's own .env ships
# `BEARER_TOKEN=` (present but empty), so os.environ.setdefault() alone would NOT
# be enough - the key already exists, just with a falsy value.
if not os.environ.get('BEARER_TOKEN'):
    os.environ['BEARER_TOKEN'] = 'test_token_periodic_updates'

# Mock sense_hat before importing temp_monitor (no Sense HAT hardware in CI).
sys.modules['sense_hat'] = MagicMock()

import temp_monitor  # noqa: E402

REPO_DIR = os.path.dirname(os.path.abspath(__file__))


class _StopLoop(BaseException):
    """Sentinel used to break update_sensor_data()'s `while True` after one
    iteration.

    Deliberately subclasses BaseException, not Exception: the loop body has a
    catch-all `except Exception` (temp_monitor.py:360) that logs and continues
    on any Exception, which would swallow a plain-Exception sentinel and keep
    looping forever instead of returning control to the test.
    """


def _new_webhook_service_mock():
    """A MagicMock standing in for WebhookService, with just enough shape that
    the unrelated check_and_alert() call inside update_sensor_data() (line 315)
    doesn't blow up on MagicMock's default (non-iterable) return value.
    """
    mock = MagicMock()
    mock.check_and_alert.return_value = {}
    mock.send_status_update.return_value = True
    return mock


def _run_one_iteration(module, mock_time_value):
    """Run module.update_sensor_data() - the REAL function - through exactly one
    iteration of its `while True` loop, then stop it.

    Only the sensor-reading helpers (not under test in this file) and time.time /
    time.sleep are mocked, so the periodic-update predicate and scheduling logic
    that actually run are the ones shipped in temp_monitor.py.
    """
    with unittest.mock.patch.object(module, 'get_compensated_temperature', return_value=22.0), \
         unittest.mock.patch.object(module, 'get_humidity', return_value=45.0), \
         unittest.mock.patch.object(module, 'get_cpu_temperature', return_value=42.0), \
         unittest.mock.patch.object(module, 'sense', MagicMock()), \
         unittest.mock.patch.object(module.time, 'time', return_value=mock_time_value), \
         unittest.mock.patch.object(module.time, 'sleep', side_effect=_StopLoop):
        try:
            module.update_sensor_data()
        except _StopLoop:
            pass
        else:
            raise AssertionError(
                "update_sensor_data() returned normally instead of looping - "
                "the time.sleep() patch should have raised _StopLoop"
            )


def _import_temp_monitor_fresh(env_overrides):
    """Import temp_monitor in a brand-new subprocess with the given environment
    variables, and return the resulting module-level state as a dict.

    This tests the REAL module-level initialization code (temp_monitor.py:106-157)
    against a genuinely clean import, without the complications of reloading the
    shared Flask/flask-restx app objects in-process.
    """
    script = textwrap.dedent("""
        import sys, os, json
        from unittest.mock import MagicMock
        sys.modules['sense_hat'] = MagicMock()
        import temp_monitor as tm
        print(json.dumps({
            'status_update_enabled': tm.status_update_enabled,
            'status_update_interval': tm.status_update_interval,
            'last_status_update': tm.last_status_update,
            'webhook_service_is_none': tm.webhook_service is None,
            'sampling_interval': tm.sampling_interval,
        }))
    """)

    env = os.environ.copy()
    # Start from a clean slate for the variables this suite controls, then
    # layer the case's overrides on top, so leftover values from the parent
    # process/shell can't leak into a "should be unset" case.
    for key in ('STATUS_UPDATE_ENABLED', 'STATUS_UPDATE_INTERVAL',
                'STATUS_UPDATE_ON_STARTUP', 'SLACK_WEBHOOK_URL'):
        env.pop(key, None)
    env.update({k: str(v) for k, v in env_overrides.items()})
    if not env.get('BEARER_TOKEN'):
        env['BEARER_TOKEN'] = 'test_token_periodic_updates'

    result = subprocess.run(
        [sys.executable, '-c', script],
        cwd=REPO_DIR, env=env, capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"Fresh import of temp_monitor failed (env={env_overrides}):\n"
            f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
        )
    # temp_monitor.py logs an "Sense HAT" line etc. to stdout in some paths; the
    # JSON we printed is always the last line.
    return json.loads(result.stdout.strip().splitlines()[-1])


class TestMinimumIntervalClamp(unittest.TestCase):
    """temp_monitor.py:111-117: STATUS_UPDATE_INTERVAL is clamped up to
    sampling_interval (60s) when it's set lower - but only while status updates
    are actually enabled.
    """

    def test_interval_below_minimum_is_clamped_up(self):
        state = _import_temp_monitor_fresh({
            'STATUS_UPDATE_ENABLED': 'true',
            'STATUS_UPDATE_INTERVAL': '30',
        })
        self.assertEqual(state['status_update_interval'], state['sampling_interval'])

    def test_interval_at_or_above_minimum_is_untouched(self):
        state = _import_temp_monitor_fresh({
            'STATUS_UPDATE_ENABLED': 'true',
            'STATUS_UPDATE_INTERVAL': '120',
        })
        self.assertEqual(state['status_update_interval'], 120)

    def test_clamp_only_applies_when_enabled(self):
        """The clamp guard is `if status_update_enabled and status_update_interval
        < sampling_interval` (temp_monitor.py:112) - when updates are disabled, an
        under-minimum interval is left as-is.
        """
        state = _import_temp_monitor_fresh({
            'STATUS_UPDATE_ENABLED': 'false',
            'STATUS_UPDATE_INTERVAL': '10',
        })
        self.assertEqual(state['status_update_interval'], 10)


class TestStartupInitialization(unittest.TestCase):
    """temp_monitor.py:148-155: STATUS_UPDATE_ON_STARTUP controls whether
    last_status_update starts as None (fires immediately on the first loop) or as
    time.time() (waits a full interval).
    """

    def test_on_startup_true_triggers_immediate_first_update(self):
        state = _import_temp_monitor_fresh({
            'STATUS_UPDATE_ENABLED': 'true',
            'SLACK_WEBHOOK_URL': 'https://hooks.slack.com/services/T00/B00/XXX',
            'STATUS_UPDATE_ON_STARTUP': 'true',
        })
        self.assertFalse(state['webhook_service_is_none'])
        self.assertIsNone(state['last_status_update'])

    def test_on_startup_false_waits_for_first_interval(self):
        before = time.time()
        state = _import_temp_monitor_fresh({
            'STATUS_UPDATE_ENABLED': 'true',
            'SLACK_WEBHOOK_URL': 'https://hooks.slack.com/services/T00/B00/XXX',
            'STATUS_UPDATE_ON_STARTUP': 'false',
        })
        after = time.time()
        self.assertFalse(state['webhook_service_is_none'])
        self.assertIsNotNone(state['last_status_update'])
        # Timer should have been started "now" (at import time), not left unset.
        self.assertGreaterEqual(state['last_status_update'], before)
        self.assertLessEqual(state['last_status_update'], after)


class TestPeriodicUpdateLoopBody(unittest.TestCase):
    """Drives the REAL update_sensor_data() loop body (temp_monitor.py:296-362)
    for a single iteration and inspects its effect on module state.
    """

    def setUp(self):
        self._orig_webhook_service = temp_monitor.webhook_service
        self._orig_enabled = temp_monitor.status_update_enabled
        self._orig_interval = temp_monitor.status_update_interval
        self._orig_last_update = temp_monitor.last_status_update

    def tearDown(self):
        temp_monitor.webhook_service = self._orig_webhook_service
        temp_monitor.status_update_enabled = self._orig_enabled
        temp_monitor.status_update_interval = self._orig_interval
        temp_monitor.last_status_update = self._orig_last_update

    def test_no_update_before_interval_elapsed(self):
        temp_monitor.status_update_enabled = True
        temp_monitor.status_update_interval = 120
        temp_monitor.last_status_update = 1000.0
        temp_monitor.webhook_service = _new_webhook_service_mock()

        _run_one_iteration(temp_monitor, mock_time_value=1000.0 + 119)

        temp_monitor.webhook_service.send_status_update.assert_not_called()
        self.assertEqual(
            temp_monitor.last_status_update, 1000.0,
            "last_status_update must be untouched when no update was sent"
        )

    def test_update_fires_at_exact_interval_boundary(self):
        temp_monitor.status_update_enabled = True
        temp_monitor.status_update_interval = 120
        temp_monitor.last_status_update = 1000.0
        temp_monitor.webhook_service = _new_webhook_service_mock()

        _run_one_iteration(temp_monitor, mock_time_value=1000.0 + 120)

        temp_monitor.webhook_service.send_status_update.assert_called_once()

    def test_update_fires_after_interval_elapsed(self):
        temp_monitor.status_update_enabled = True
        temp_monitor.status_update_interval = 120
        temp_monitor.last_status_update = 1000.0
        temp_monitor.webhook_service = _new_webhook_service_mock()

        _run_one_iteration(temp_monitor, mock_time_value=1000.0 + 200)

        temp_monitor.webhook_service.send_status_update.assert_called_once()

    def test_first_update_fires_when_last_status_update_is_none(self):
        temp_monitor.status_update_enabled = True
        temp_monitor.status_update_interval = 120
        temp_monitor.last_status_update = None
        temp_monitor.webhook_service = _new_webhook_service_mock()

        _run_one_iteration(temp_monitor, mock_time_value=1_700_000_000.0)

        temp_monitor.webhook_service.send_status_update.assert_called_once()

    def test_no_updates_sent_when_disabled(self):
        temp_monitor.status_update_enabled = False
        temp_monitor.status_update_interval = 120
        temp_monitor.last_status_update = 1000.0
        temp_monitor.webhook_service = _new_webhook_service_mock()

        _run_one_iteration(temp_monitor, mock_time_value=1000.0 + 500)

        temp_monitor.webhook_service.send_status_update.assert_not_called()

    def test_bug_webhook_service_created_late_ignores_startup_flag(self):
        """FIXED - was BUG (temp_monitor.py:156-157). Unpinned from
        @unittest.expectedFailure once the PUT handler began starting the timer
        for a service it creates. This test now guards the fix.

        Original defect: when STATUS_UPDATE_ENABLED is true but no
        webhook_service exists at import time, the init block's elif branch only
        logs a warning - it never sets last_status_update. If a webhook_service is
        later created through the real API endpoint (temp_monitor.py:488-489,
        exercised below via an actual PUT /api/webhook/config request),
        last_status_update is still None, so the very next loop iteration fires a
        status update immediately - regardless of STATUS_UPDATE_ON_STARTUP.

        Correct behavior: creating the webhook service later should start the
        interval timer (as if STATUS_UPDATE_ON_STARTUP were false), not trigger an
        immediate send.
        """
        temp_monitor.status_update_enabled = True
        temp_monitor.status_update_interval = 3600
        temp_monitor.webhook_service = None
        temp_monitor.last_status_update = None  # as left by temp_monitor.py:156-157

        client = temp_monitor.app.test_client()
        token = os.environ['BEARER_TOKEN']
        response = client.put(
            '/api/webhook/config',
            data=json.dumps({'webhook': {'url': 'https://hooks.slack.com/services/T00/B00/XXX'}}),
            content_type='application/json',
            headers={'Authorization': f'Bearer {token}'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(temp_monitor.webhook_service)

        # Avoid a real network call; only whether send_status_update fires matters.
        temp_monitor.webhook_service.send_status_update = MagicMock(return_value=True)

        _run_one_iteration(temp_monitor, mock_time_value=time.time())

        # CORRECT behavior: STATUS_UPDATE_ON_STARTUP was never set to true, so the
        # first status update should wait a full interval, not fire immediately.
        temp_monitor.webhook_service.send_status_update.assert_not_called()

    def test_bug_schedule_anchor_uses_fire_time_not_target_time(self):
        """FIXED - was BUG (temp_monitor.py:351). Unpinned from
        @unittest.expectedFailure once the schedule began anchoring to
        (previous + interval). This test now guards against drift regressing.

        Original defect: on send, last_status_update was set to
        current_time (the moment the check happened to run), not to
        (previous last_status_update + status_update_interval). Because the loop
        only checks once per sampling_interval (60s), a firing can land up to
        ~sampling_interval late, and that lateness becomes the baseline for the
        next interval - so the cadence drifts progressively later instead of
        holding to a fixed schedule.

        Correct behavior: the anchor should advance by exactly `interval`.
        """
        temp_monitor.status_update_enabled = True
        temp_monitor.status_update_interval = 3600
        temp_monitor.last_status_update = 0.0
        temp_monitor.webhook_service = _new_webhook_service_mock()

        # This tick runs 60s late (3660 instead of 3600) - realistic, since the
        # loop only samples once every sampling_interval (60s), temp_monitor.py:359.
        _run_one_iteration(temp_monitor, mock_time_value=3660.0)

        temp_monitor.webhook_service.send_status_update.assert_called_once()
        self.assertEqual(
            temp_monitor.last_status_update, 3600.0,
            "correct scheduling should anchor the next interval at 0 + 3600, "
            "not at the actual (late) fire time of 3660"
        )


if __name__ == '__main__':
    unittest.main(verbosity=2)
