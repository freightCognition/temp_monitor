# Mock SenseHat library for testing without actual hardware
import time

class SenseHat:
    def __init__(self):
        print("Using mock SenseHat")

    def clear(self):
        pass

    def get_temperature_from_humidity(self):
        return 25.0

    def get_temperature_from_pressure(self):
        return 25.0

    def get_humidity(self):
        return 40.0

    def get_temperature(self):
        return 25.0

    def show_message(self, message):
        print(f"Mock SenseHat displaying: {message}")

    def get_pixels(self):
        return [[(0, 0, 0)] * 8] * 8

    def set_pixels(self, pixels):
        pass
