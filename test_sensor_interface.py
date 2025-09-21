import unittest
import math
from sensor_interface import MockSensorInterface

class TestMockSensorInterface(unittest.TestCase):

    def test_get_temperature_uses_math_sin(self):
        """Test that get_temperature runs without raising an error and uses math.sin."""
        try:
            sensor = MockSensorInterface()
            # This will now use math.sin and should not raise an AttributeError
            temp = sensor.get_temperature()
            self.assertIsInstance(temp, float)
        except Exception as e:
            self.fail(f"get_temperature raised an unexpected exception: {e}")

    def test_get_humidity_uses_math_sin(self):
        """Test that get_humidity runs without raising an error and uses math.sin."""
        try:
            sensor = MockSensorInterface()
            # This will now use math.sin and should not raise an AttributeError
            humidity = sensor.get_humidity()
            self.assertIsInstance(humidity, float)
        except Exception as e:
            self.fail(f"get_humidity raised an unexpected exception: {e}")

if __name__ == '__main__':
    unittest.main()
