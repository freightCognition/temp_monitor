#!/usr/bin/env python3
"""Shared fixtures for this repo's test files.

Import this BEFORE importing temp_monitor:

    import test_support  # noqa: F401  (must precede temp_monitor)
    import temp_monitor

Importing it does two things that every test file in this repo needs and
previously repeated by hand:

1. Guarantees BEARER_TOKEN is set. temp_monitor calls sys.exit(1) at import
   when it is missing, and this repo's own .env ships `BEARER_TOKEN=`
   (present but EMPTY), so os.environ.setdefault() is not sufficient -- the
   key already exists with a falsy value.
2. Installs a MagicMock for `sense_hat`, since CI and dev machines have no
   Sense HAT hardware.

It also provides BaseAPITestCase (Flask test client + Bearer auth header) and
run_fresh_import() (cold-start a fresh temp_monitor in a subprocess), both of
which were previously copy-pasted across several test files.
"""

import json
import os
import subprocess
import sys
import textwrap
import unittest
from unittest.mock import MagicMock

REPO_DIR = os.path.dirname(os.path.abspath(__file__))

# Default token used when the environment doesn't supply one. CI sets
# BEARER_TOKEN explicitly; this keeps every test file runnable standalone.
DEFAULT_TEST_TOKEN = 'test_token_ci'

if not os.environ.get('BEARER_TOKEN'):
    os.environ['BEARER_TOKEN'] = DEFAULT_TEST_TOKEN

sys.modules.setdefault('sense_hat', MagicMock())


def auth_header(token=None):
    """Build the Authorization header for the active bearer token."""
    return {'Authorization': f'Bearer {token or os.environ["BEARER_TOKEN"]}'}


class BaseAPITestCase(unittest.TestCase):
    """Flask test client plus a valid Bearer auth header.

    Subclasses that need their own setUp must call super().setUp().
    """

    def setUp(self):
        import temp_monitor

        self.app = temp_monitor.app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        self.token = os.environ['BEARER_TOKEN']
        self.auth_header = auth_header(self.token)


# Source prelude for a cold-start subprocess: mock the hardware, then import
# temp_monitor as `tm`. Kept here so the three call sites that need a genuinely
# fresh import can't drift apart.
_FRESH_IMPORT_PRELUDE = textwrap.dedent("""
    import sys, os, json
    from unittest.mock import MagicMock
    sys.modules['sense_hat'] = MagicMock()
    import temp_monitor as tm
""")


def run_fresh_import(probe, env_overrides=None, scrub=(), body='',
                     expect_success=True, timeout=30):
    """Import temp_monitor in a brand-new subprocess and report on it.

    This exercises the REAL module-level initialization against a genuinely
    clean import, without the complications of reloading the shared
    Flask/flask-restx app objects in-process.

    Args:
        probe: Source text of a dict literal, evaluated after import with the
            module bound to `tm`, e.g. "{'interval': tm.status_update_interval}".
        env_overrides: Environment variables to set for the child process.
        scrub: Variables to REMOVE from the inherited environment before
            applying overrides, so a value left over in the parent shell
            can't leak into a case that means "this var is unset".
        body: Optional extra source lines to run after import and before the
            probe is printed (e.g. issuing a request against the fresh app).
        expect_success: When True, a non-zero exit is an assertion failure and
            the parsed probe dict is returned. When False, the raw
            CompletedProcess is returned so the caller can inspect the failure.

    Returns:
        The parsed probe dict, or CompletedProcess when expect_success=False.
    """
    script = _FRESH_IMPORT_PRELUDE + body + f"\nprint(json.dumps({probe}))\n"

    env = os.environ.copy()
    for key in scrub:
        env.pop(key, None)
    env.update({k: str(v) for k, v in (env_overrides or {}).items()})
    if not env.get('BEARER_TOKEN'):
        env['BEARER_TOKEN'] = DEFAULT_TEST_TOKEN

    result = subprocess.run(
        [sys.executable, '-c', script],
        cwd=REPO_DIR, env=env, capture_output=True, text=True, timeout=timeout,
    )

    if not expect_success:
        return result

    if result.returncode != 0:
        raise AssertionError(
            f"Fresh import of temp_monitor failed (env={env_overrides}):\n"
            f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
        )
    # temp_monitor logs startup lines to stdout on some paths; the JSON we
    # printed is always the last line.
    return json.loads(result.stdout.strip().splitlines()[-1])
