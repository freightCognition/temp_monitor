#!/usr/bin/env python3
"""
Tests for S6/S7 and S10:

S6/S7 - /health returned 200 "healthy" unconditionally even when the
sensor thread was dead or the last reading was stale (current_temp stuck
at its initial value, last_updated stuck at "Never"). Docker's
HEALTHCHECK, systemd, and any load balancer all saw green regardless.
Fix: return 503 when the thread is dead OR the last reading is stale.

S10 - /health and /metrics were both unauthenticated, and /metrics leaked
process internals (RSS, thread count, open FD count) plus a free
psutil.cpu_percent() sample per request to any unauthenticated caller --
and the service is reachable over a public tunnel. Fix: keep /health
unauthenticated but strip it to liveness only (no sensor values, no
process internals); require the bearer token on /metrics.
"""
import time
import unittest

# Sets BEARER_TOKEN and mocks sense_hat; MUST precede importing temp_monitor.
from test_support import BaseAPITestCase

import temp_monitor  # noqa: E402


class _FakeThread:
    def __init__(self, alive):
        self._alive = alive

    def is_alive(self):
        return self._alive


class HealthTestBase(BaseAPITestCase):
    def setUp(self):
        super().setUp()
        self._orig_thread = temp_monitor.sensor_thread
        self._orig_last_updated_ts = temp_monitor.last_updated_ts
        self._orig_compensated = temp_monitor.current_temp_compensated

    def tearDown(self):
        temp_monitor.sensor_thread = self._orig_thread
        temp_monitor.last_updated_ts = self._orig_last_updated_ts
        temp_monitor.current_temp_compensated = self._orig_compensated


class TestHealthStalenessAndLiveness(HealthTestBase):
    def test_503_when_thread_is_dead(self):
        temp_monitor.sensor_thread = _FakeThread(alive=False)
        temp_monitor.last_updated_ts = time.time()  # fresh reading, but thread dead

        response = self.client.get('/health')
        data = response.get_json()
        self.assertEqual(response.status_code, 503)
        self.assertFalse(data['sensor_thread_alive'])
        self.assertEqual(data['status'], 'unhealthy')

    def test_503_when_thread_never_started(self):
        temp_monitor.sensor_thread = None
        temp_monitor.last_updated_ts = None

        response = self.client.get('/health')
        data = response.get_json()
        self.assertEqual(response.status_code, 503)
        self.assertFalse(data['sensor_thread_alive'])

    def test_503_when_reading_is_stale(self):
        temp_monitor.sensor_thread = _FakeThread(alive=True)
        stale_age = temp_monitor.staleness_threshold_seconds + 30
        temp_monitor.last_updated_ts = time.time() - stale_age

        response = self.client.get('/health')
        data = response.get_json()
        self.assertEqual(response.status_code, 503)
        self.assertTrue(data['sensor_thread_alive'])
        self.assertTrue(data['reading_stale'])
        self.assertEqual(data['status'], 'unhealthy')

    def test_200_when_thread_alive_and_reading_fresh(self):
        temp_monitor.sensor_thread = _FakeThread(alive=True)
        temp_monitor.last_updated_ts = time.time()

        response = self.client.get('/health')
        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['status'], 'healthy')
        self.assertTrue(data['sensor_thread_alive'])
        self.assertFalse(data['reading_stale'])

    def test_health_does_not_leak_sensor_values_or_process_internals(self):
        """S10: /health is public -- it must stay liveness-only."""
        temp_monitor.sensor_thread = _FakeThread(alive=True)
        temp_monitor.last_updated_ts = time.time()

        response = self.client.get('/health')
        data = response.get_json()
        for leaky_key in (
            'temperature_c', 'humidity', 'current_temp', 'current_humidity',
            'memory_mb', 'file_descriptors', 'cpu_percent',
        ):
            self.assertNotIn(leaky_key, data)

    def test_health_is_unauthenticated(self):
        temp_monitor.sensor_thread = _FakeThread(alive=True)
        temp_monitor.last_updated_ts = time.time()

        response = self.client.get('/health')  # no Authorization header
        self.assertIn(response.status_code, (200, 503))


class TestMetricsRequiresAuth(HealthTestBase):
    def test_metrics_rejects_unauthenticated_requests(self):
        response = self.client.get('/metrics')
        self.assertEqual(response.status_code, 401)

    def test_metrics_allows_authenticated_requests(self):
        response = self.client.get('/metrics', headers=self.auth_header)
        self.assertEqual(response.status_code, 200)


if __name__ == '__main__':
    unittest.main()
