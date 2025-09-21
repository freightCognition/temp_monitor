"""
Sensor interface abstraction layer for Temperature Monitor.
Provides both real Sense HAT interface and mock interface for development.
"""

import os
import time
import logging
import random
from abc import ABC, abstractmethod
from typing import Optional, Tuple


class SensorInterface(ABC):
    """Abstract base class for sensor interfaces."""
    
    @abstractmethod
    def get_temperature(self) -> float:
        """Get raw temperature reading in Celsius."""
        pass
    
    @abstractmethod
    def get_humidity(self) -> float:
        """Get humidity reading as percentage."""
        pass
    
    @abstractmethod
    def get_cpu_temperature(self) -> float:
        """Get CPU temperature in Celsius."""
        pass
    
    @abstractmethod
    def clear_display(self) -> None:
        """Clear the LED display."""
        pass
    
    @abstractmethod
    def show_message(self, message: str, text_colour: Optional[Tuple[int, int, int]] = None) -> None:
        """Show a scrolling message on the LED display."""
        pass
    
    @abstractmethod
    def set_pixels(self, pixels: list) -> None:
        """Set the LED matrix pixels."""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if the sensor hardware is available."""
        pass


class RealSensorInterface(SensorInterface):
    """Real Sense HAT sensor interface."""
    
    def __init__(self):
        self._sense_hat = None
        self._available = False
        self._initialize()
    
    def _initialize(self):
        """Initialize the Sense HAT."""
        try:
            from sense_hat import SenseHat
            self._sense_hat = SenseHat()
            self._sense_hat.clear()
            self._available = True
            logging.info("Sense HAT initialized successfully")
        except ImportError:
            logging.error("sense-hat library not available")
        except Exception as e:
            logging.error(f"Failed to initialize Sense HAT: {e}")
    
    def get_temperature(self) -> float:
        """Get raw temperature from humidity sensor."""
        if not self._available:
            raise RuntimeError("Sense HAT not available")
        
        try:
            return self._sense_hat.get_temperature_from_humidity()
        except Exception as e:
            logging.error(f"Error reading temperature: {e}")
            raise
    
    def get_humidity(self) -> float:
        """Get humidity reading."""
        if not self._available:
            raise RuntimeError("Sense HAT not available")
        
        try:
            return self._sense_hat.get_humidity()
        except Exception as e:
            logging.error(f"Error reading humidity: {e}")
            raise
    
    def get_cpu_temperature(self) -> float:
        """Get CPU temperature from thermal zone."""
        try:
            with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
                cpu_temp = float(f.read().strip()) / 1000.0
            return cpu_temp
        except Exception as e:
            logging.error(f"Error reading CPU temperature: {e}")
            # Fallback to a reasonable estimate
            return 45.0
    
    def clear_display(self) -> None:
        """Clear the LED display."""
        if self._available:
            try:
                self._sense_hat.clear()
            except Exception as e:
                logging.error(f"Error clearing display: {e}")
    
    def show_message(self, message: str, text_colour: Optional[Tuple[int, int, int]] = None) -> None:
        """Show a scrolling message on the LED display."""
        if self._available:
            try:
                if text_colour:
                    self._sense_hat.show_message(message, text_colour=text_colour)
                else:
                    self._sense_hat.show_message(message)
            except Exception as e:
                logging.error(f"Error showing message: {e}")
    
    def set_pixels(self, pixels: list) -> None:
        """Set the LED matrix pixels."""
        if self._available:
            try:
                self._sense_hat.set_pixels(pixels)
            except Exception as e:
                logging.error(f"Error setting pixels: {e}")
    
    def is_available(self) -> bool:
        """Check if the sensor hardware is available."""
        return self._available


class MockSensorInterface(SensorInterface):
    """Mock sensor interface for development and testing."""
    
    def __init__(self):
        self._base_temp = 22.0  # Base room temperature
        self._base_humidity = 45.0  # Base humidity
        self._cpu_temp = 55.0  # Mock CPU temperature
        self._start_time = time.time()
        logging.info("Mock sensor interface initialized")
    
    def get_temperature(self) -> float:
        """Generate mock temperature with realistic variation."""
        # Simulate daily temperature cycle and random variation
        elapsed = time.time() - self._start_time
        daily_cycle = 2.0 * (0.5 + 0.5 * (time.sin(elapsed / 3600.0 * 2 * 3.14159 / 24)))  # 24-hour cycle
        random_variation = random.uniform(-0.5, 0.5)
        return self._base_temp + daily_cycle + random_variation
    
    def get_humidity(self) -> float:
        """Generate mock humidity with realistic variation."""
        # Simulate humidity changes with random variation
        elapsed = time.time() - self._start_time
        slow_variation = 10.0 * (0.5 + 0.5 * (time.sin(elapsed / 7200.0)))  # 2-hour cycle
        random_variation = random.uniform(-2.0, 2.0)
        humidity = self._base_humidity + slow_variation + random_variation
        return max(20.0, min(80.0, humidity))  # Clamp between 20-80%
    
    def get_cpu_temperature(self) -> float:
        """Generate mock CPU temperature."""
        # Simulate CPU temperature with some variation
        random_variation = random.uniform(-3.0, 8.0)
        return self._cpu_temp + random_variation
    
    def clear_display(self) -> None:
        """Mock clear display - logs action."""
        logging.debug("Mock: Clearing LED display")
    
    def show_message(self, message: str, text_colour: Optional[Tuple[int, int, int]] = None) -> None:
        """Mock show message - logs action."""
        logging.debug(f"Mock: Showing message '{message}' with color {text_colour}")
    
    def set_pixels(self, pixels: list) -> None:
        """Mock set pixels - logs action."""
        logging.debug(f"Mock: Setting {len(pixels)} pixels on LED matrix")
    
    def is_available(self) -> bool:
        """Mock sensors are always available."""
        return True


def create_sensor_interface(use_mock: bool = False) -> SensorInterface:
    """Factory function to create appropriate sensor interface."""
    if use_mock:
        return MockSensorInterface()
    
    # Try to create real interface first
    real_interface = RealSensorInterface()
    if real_interface.is_available():
        return real_interface
    
    # Fall back to mock interface
    logging.warning("Real sensors not available, falling back to mock sensors")
    return MockSensorInterface()