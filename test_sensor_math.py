#!/usr/bin/env python3
"""
Tests for S3/S4/S5: the temperature/humidity compensation math had zero
test coverage, and a failed CPU-temperature read silently substituted the
raw (uncompensated) reading with no marker anywhere -- a ~14C swing that
looks like a real environmental change.

Covers:
- get_cpu_temperature(): success and failure paths
- get_compensated_temperature(): exact table-driven outputs, including the
  -4F correction and the CPU-compensation term, PLUS the new
  (temperature, is_compensated) contract from S3
- get_humidity(): exact table-driven outputs including the +4% correction
  and the 100% cap
- S5 known defect: the outlier-trim in get_compensated_temperature()
  interleaves humidity-sensor and pressure-sensor readings into one list
  before sorting/trimming, so on a real bimodal split it removes one
  extreme from each cluster rather than rejecting either sensor's outliers,
  producing a blended mean. This test PINS that behavior as currently
  implemented; it is not a fix. If this test's expected value ever needs to
  change, that means the blending behavior changed -- flag it loudly, the
  user is actively calibrating against a real thermostat.
"""
import unittest
from unittest.mock import MagicMock, patch, mock_open

# Sets BEARER_TOKEN and mocks sense_hat; MUST precede importing temp_monitor.
from test_support import BaseAPITestCase

import temp_monitor  # noqa: E402


class TestGetCpuTemperature(unittest.TestCase):
    def test_reads_millidegrees_and_converts_to_celsius(self):
        with patch('builtins.open', mock_open(read_data='45000\n')):
            self.assertEqual(temp_monitor.get_cpu_temperature(), 45.0)

    def test_returns_none_and_warns_on_read_failure(self):
        with patch('builtins.open', side_effect=OSError('no such file')):
            with self.assertLogs(level='ERROR') as log_ctx:
                result = temp_monitor.get_cpu_temperature()
        self.assertIsNone(result)
        self.assertTrue(any('cpu temperature' in msg.lower() for msg in log_ctx.output))


class TestGetCompensatedTemperature(unittest.TestCase):
    def setUp(self):
        self._orig_compensated = temp_monitor.current_temp_compensated

    def tearDown(self):
        temp_monitor.current_temp_compensated = self._orig_compensated

    def _set_raw_readings(self, humidity_sensor_values, pressure_sensor_values):
        temp_monitor.sense.get_temperature_from_humidity = MagicMock(
            side_effect=humidity_sensor_values
        )
        temp_monitor.sense.get_temperature_from_pressure = MagicMock(
            side_effect=pressure_sensor_values
        )

    @patch('temp_monitor.time.sleep', return_value=None)
    @patch('temp_monitor.get_cpu_temperature', return_value=30.0)
    def test_uniform_readings_with_cpu_compensation(self, mock_cpu, mock_sleep):
        # raw = 20.0C uniform, cpu = 30.0C
        # comp = 20.0 - ((30.0-20.0)*0.7) = 13.0
        # comp += -13.5*5/9 (=-7.5)         = 5.5
        self._set_raw_readings([20.0] * 5, [20.0] * 5)
        temp = temp_monitor.get_compensated_temperature()
        self.assertEqual(temp, 5.5)
        self.assertTrue(temp_monitor.current_temp_compensated)

    @patch('temp_monitor.time.sleep', return_value=None)
    @patch('temp_monitor.get_cpu_temperature', return_value=None)
    def test_cpu_unavailable_uses_raw_and_flags_uncompensated(self, mock_cpu, mock_sleep):
        # raw = 20.0C uniform, cpu unavailable -> no compensation term applied
        # comp = 20.0 - 7.5 = 12.5
        self._set_raw_readings([20.0] * 5, [20.0] * 5)
        with self.assertLogs(level='WARNING') as log_ctx:
            temp = temp_monitor.get_compensated_temperature()
        self.assertEqual(temp, 12.5)
        self.assertFalse(temp_monitor.current_temp_compensated)
        self.assertTrue(any('cpu temperature' in msg.lower() for msg in log_ctx.output))

    @patch('temp_monitor.time.sleep', return_value=None)
    @patch('temp_monitor.get_cpu_temperature', return_value=None)
    def test_KNOWN_DEFECT_bimodal_sensor_blend_not_outlier_rejection(self, mock_cpu, mock_sleep):
        """S5: humidity-sensor reads a clean 20.0C, pressure-sensor reads a
        clean 24.0C (systematic hardware skew, not noise). A correct
        outlier filter operating per-sensor would reject neither (both are
        internally consistent) or would need to reconcile two calibrated
        sources -- but the current code pools all 10 readings into one
        sorted list and trims exactly one from each end, so the trim
        removes one member of *each* cluster and the mean is a blend:
            sorted:  [20,20,20,20,20, 24,24,24,24,24]
            trimmed: [20,20,20,20,   24,24,24,24]      (8 left)
            mean = (80 + 96) / 8 = 22.0
            comp = 22.0 + (-13.5*5/9) = 22.0 - 7.5 = 14.5
        This pins the CURRENT behavior. It is not correct behavior -- it's
        documentation. If get_compensated_temperature() is later fixed to
        filter outliers per-sensor, this expected value (14.5) will change
        and this test must be updated deliberately, not silently.

        NOTE: this blend bias is currently ABSORBED INTO the empirical
        TEMP_OFFSET_F calibration -- the operator measured the +9.5F error
        with this blending in place. Fixing the blend and keeping the
        offset would double-correct. Recalibrate if the blend is ever fixed.
        """
        self._set_raw_readings([20.0] * 5, [24.0] * 5)
        temp = temp_monitor.get_compensated_temperature()
        self.assertEqual(temp, 14.5)
        self.assertFalse(temp_monitor.current_temp_compensated)


class TestCalibrationIsOperatorTunable(unittest.TestCase):
    """Regression tests for the production defect where reported temperature
    ran +9.5F hot against the operator's reference thermometer.

    Root cause of *why now*: until this branch, the repo shipped a stub named
    sense_hat.py that shadowed the real sense-hat package on sys.path, so the
    process read a constant fabricated 25.0C. The compensation constants had
    therefore never been validated against real hardware. Renaming the stub
    exposed the real (uncalibrated) reading.

    These tests pin (a) the corrected default and (b) that both calibration
    parameters are genuinely wired to the module globals, so an operator can
    recalibrate via TEMP_CPU_FACTOR / TEMP_OFFSET_F without a code change.
    """

    def setUp(self):
        self._orig_factor = temp_monitor.temp_cpu_factor
        self._orig_offset = temp_monitor.temp_offset_f
        self._orig_humidity_offset = temp_monitor.humidity_offset
        self._orig_compensated = temp_monitor.current_temp_compensated

    def tearDown(self):
        temp_monitor.temp_cpu_factor = self._orig_factor
        temp_monitor.temp_offset_f = self._orig_offset
        temp_monitor.humidity_offset = self._orig_humidity_offset
        temp_monitor.current_temp_compensated = self._orig_compensated

    def _set_raw_readings(self, humidity_sensor_values, pressure_sensor_values):
        temp_monitor.sense.get_temperature_from_humidity = MagicMock(
            side_effect=humidity_sensor_values
        )
        temp_monitor.sense.get_temperature_from_pressure = MagicMock(
            side_effect=pressure_sensor_values
        )

    def test_default_offset_is_nine_point_five_f_cooler_than_the_old_constant(self):
        """The shipped default must read exactly 9.5F cooler than the old
        hardcoded -4.0F offset -- that is the measured field error."""
        self.assertAlmostEqual(temp_monitor.temp_offset_f, -4.0 - 9.5, places=6)

    @patch('temp_monitor.time.sleep', return_value=None)
    @patch('temp_monitor.get_cpu_temperature', return_value=51.121)
    def test_reported_temp_drops_by_9_5f_at_the_field_operating_point(self, _cpu, _sleep):
        """Reproduces the reported field conditions (CPU 51.121C, the raw
        reading that yielded the 27.7C shown in Slack) and asserts the new
        default reports 9.5F -- 5.2777C -- cooler than the old constant did.
        """
        raw = 38.65  # solves 1.7*raw - 0.7*51.121 - (4*5/9) = 27.7

        temp_monitor.temp_offset_f = -4.0  # old, pre-fix default
        self._set_raw_readings([raw] * 5, [raw] * 5)
        before = temp_monitor.get_compensated_temperature()

        temp_monitor.temp_offset_f = self._orig_offset  # shipped default
        self._set_raw_readings([raw] * 5, [raw] * 5)
        after = temp_monitor.get_compensated_temperature()

        self.assertAlmostEqual(before, 27.7, places=1)
        self.assertAlmostEqual(before - after, 9.5 * 5 / 9, places=1)

    @patch('temp_monitor.time.sleep', return_value=None)
    @patch('temp_monitor.get_cpu_temperature', return_value=30.0)
    def test_cpu_factor_is_read_from_the_module_global(self, _cpu, _sleep):
        """A changed TEMP_CPU_FACTOR must actually move the output, i.e. the
        0.7 is no longer hardcoded inside the function."""
        temp_monitor.temp_offset_f = 0.0
        temp_monitor.temp_cpu_factor = 0.0
        self._set_raw_readings([20.0] * 5, [20.0] * 5)
        # factor 0.0 -> no CPU term at all -> raw passes through
        self.assertEqual(temp_monitor.get_compensated_temperature(), 20.0)

        temp_monitor.temp_cpu_factor = 0.2
        self._set_raw_readings([20.0] * 5, [20.0] * 5)
        # 20.0 - ((30.0-20.0)*0.2) = 18.0
        self.assertEqual(temp_monitor.get_compensated_temperature(), 18.0)

    @patch('temp_monitor.time.sleep', return_value=None)
    def test_humidity_offset_is_read_from_the_module_global(self, _sleep):
        temp_monitor.humidity_offset = 0.0
        temp_monitor.sense.get_humidity = MagicMock(side_effect=[30.0, 40.0, 50.0])
        self.assertEqual(temp_monitor.get_humidity(), 40.0)


class TestGetHumidity(unittest.TestCase):
    @patch('temp_monitor.time.sleep', return_value=None)
    def test_trims_outliers_applies_plus_four_correction(self, mock_sleep):
        # readings [30,40,50] -> sorted, trim first/last -> [40] -> mean 40
        # +4 correction -> 44.0
        temp_monitor.sense.get_humidity = MagicMock(side_effect=[30.0, 40.0, 50.0])
        self.assertEqual(temp_monitor.get_humidity(), 44.0)

    @patch('temp_monitor.time.sleep', return_value=None)
    def test_caps_at_100_percent(self, mock_sleep):
        # readings [97,98,99] -> trim -> [98] -> +4 = 102 -> capped to 100
        temp_monitor.sense.get_humidity = MagicMock(side_effect=[97.0, 98.0, 99.0])
        self.assertEqual(temp_monitor.get_humidity(), 100.0)


class TestApiTempExposesCompensatedFlag(BaseAPITestCase):
    """S4: assert /api/temp (and /api/raw) carry the uncompensated flag
    when CPU compensation could not be applied, so clients don't mistake a
    degraded reading for a normal one."""

    def setUp(self):
        super().setUp()
        self._orig_temp = temp_monitor.current_temp
        self._orig_compensated = temp_monitor.current_temp_compensated
        self._orig_humidity = temp_monitor.current_humidity

    def tearDown(self):
        temp_monitor.current_temp = self._orig_temp
        temp_monitor.current_temp_compensated = self._orig_compensated
        temp_monitor.current_humidity = self._orig_humidity

    def test_api_temp_reports_uncompensated_reading(self):
        temp_monitor.current_temp = 17.8
        temp_monitor.current_temp_compensated = False
        temp_monitor.current_humidity = 44.0

        response = self.client.get('/api/temp', headers=self.auth_header)
        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertIn('compensated', data)
        self.assertFalse(data['compensated'])

    def test_api_temp_reports_compensated_reading(self):
        temp_monitor.current_temp = 10.8
        temp_monitor.current_temp_compensated = True
        temp_monitor.current_humidity = 44.0

        response = self.client.get('/api/temp', headers=self.auth_header)
        data = response.get_json()
        self.assertTrue(data['compensated'])

    def test_api_raw_reports_compensated_flag(self):
        temp_monitor.current_temp_compensated = False
        with patch('temp_monitor.get_cpu_temperature', return_value=None), \
             patch.object(temp_monitor.sense, 'get_temperature', return_value=20.0):
            response = self.client.get('/api/raw', headers=self.auth_header)
        data = response.get_json()
        self.assertIn('compensated', data)
        self.assertFalse(data['compensated'])


if __name__ == '__main__':
    unittest.main()
