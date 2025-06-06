import time
import logging
import statistics
import os
import random # For mock data

# Configure logging for the sensor manager module
logger = logging.getLogger(__name__)

# Attempt to import SenseHat and set a flag
try:
    from sense_hat import SenseHat
    sense = SenseHat()
    sense.clear()  # Clear the LED matrix if Sense HAT is present
    SENSE_HAT_AVAILABLE = True
    logger.info("Sense HAT library loaded and initialized.")
except (ImportError, RuntimeError) as e:
    logger.warning(f"Sense HAT library not found or failed to initialize: {e}. Using mock data.")
    SENSE_HAT_AVAILABLE = False
    sense = None # Ensure sense object is None if not available

# --- CPU Temperature Reading ---
def get_cpu_temperature():
    """Get the temperature of the CPU."""
    # In a real Raspberry Pi, this would read from '/sys/class/thermal/thermal_zone0/temp'
    # For environments without this file (like development machines or CI), return a mock value.
    if os.path.exists("/sys/class/thermal/thermal_zone0/temp"):
        try:
            with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                temp = float(f.read()) / 1000.0
            logger.debug(f"CPU temperature read: {temp}°C")
            return temp
        except Exception as e:
            logger.error(f"Failed to get CPU temperature: {e}")
            return None # Or a mock value if preferred for consistency
    else:
        # Mock CPU temperature if the system file doesn't exist
        mock_cpu_temp = random.uniform(40.0, 60.0)
        logger.debug(f"Using mock CPU temperature: {mock_cpu_temp}°C")
        return mock_cpu_temp

# --- Compensated Temperature Reading ---
def get_compensated_temperature():
    """Get temperature from the Sense HAT with CPU compensation.
    Returns a mock value if Sense HAT is not available.
    """
    if not SENSE_HAT_AVAILABLE:
        mock_temp = random.uniform(18.0, 28.0) # Realistic ambient temperature range
        logger.debug(f"Sense HAT unavailable. Returning mock compensated temperature: {mock_temp}°C")
        return round(mock_temp, 1)

    try:
        cpu_temp = get_cpu_temperature()

        raw_temps = []
        for _ in range(5):  # Take multiple readings
            raw_temps.append(sense.get_temperature_from_humidity())
            raw_temps.append(sense.get_temperature_from_pressure())
            time.sleep(0.05) # Shorter sleep for faster readings in a sequence

        if not raw_temps:
            logger.warning("No raw temperature readings obtained from Sense HAT.")
            return random.uniform(18.0, 28.0) # Fallback mock

        # Remove outliers and calculate the average raw temperature
        if len(raw_temps) > 2:
            raw_temps.sort()
            filtered_temps = raw_temps[1:-1]
            raw_temp = statistics.mean(filtered_temps) if filtered_temps else statistics.mean(raw_temps)
        else:
            raw_temp = statistics.mean(raw_temps)

        # Apply compensation formula (factor might need calibration on actual hardware)
        # This formula assumes the CPU is significantly warmer than the ambient temperature.
        factor = 0.7 # This was from the original script, should be configurable eventually
        if cpu_temp is not None:
            comp_temp = raw_temp - ((cpu_temp - raw_temp) * factor)
        else:
            # If CPU temp isn't available, use raw temp or a less aggressive compensation
            logger.warning("CPU temperature not available for compensation. Using raw sensor temperature.")
            comp_temp = raw_temp

        logger.debug(f"Raw temp: {raw_temp:.2f}°C, CPU temp: {cpu_temp:.2f}°C, Compensated temp: {comp_temp:.1f}°C")
        return round(comp_temp, 1)
    except Exception as e:
        logger.error(f"Error getting compensated temperature from Sense HAT: {e}")
        # Fallback to a mock value in case of any error during Sense HAT interaction
        return round(random.uniform(18.0, 28.0), 1)

# --- Humidity Reading ---
def get_humidity():
    """Get humidity from the Sense HAT.
    Returns a mock value if Sense HAT is not available.
    """
    if not SENSE_HAT_AVAILABLE:
        mock_humidity = random.uniform(30.0, 70.0) # Realistic humidity range
        logger.debug(f"Sense HAT unavailable. Returning mock humidity: {mock_humidity}%")
        return round(mock_humidity, 1)

    try:
        readings = []
        for _ in range(3):
            readings.append(sense.get_humidity())
            time.sleep(0.05)

        if not readings:
            logger.warning("No humidity readings obtained from Sense HAT.")
            return random.uniform(30.0, 70.0) # Fallback mock

        if len(readings) > 2:
            readings.sort()
            readings = readings[1:-1]

        humidity = statistics.mean(readings) if readings else random.uniform(30.0, 70.0)
        logger.debug(f"Humidity read: {humidity:.1f}%")
        return round(humidity, 1)
    except Exception as e:
        logger.error(f"Error getting humidity from Sense HAT: {e}")
        # Fallback to a mock value
        return round(random.uniform(30.0, 70.0), 1)

def get_raw_temperature_reading():
    """Gets a single raw temperature reading from the Sense HAT, primarily for diagnostics.
    Returns a mock value if Sense HAT is not available.
    """
    if not SENSE_HAT_AVAILABLE:
        mock_raw_temp = random.uniform(20.0, 30.0)
        logger.debug(f"Sense HAT unavailable. Returning mock raw temperature: {mock_raw_temp}°C")
        return round(mock_raw_temp, 1)

    try:
        # SenseHat.get_temperature() is an average from both pressure and humidity sensors
        raw_temp = sense.get_temperature()
        logger.debug(f"Raw temperature (direct): {raw_temp:.1f}°C")
        return round(raw_temp, 1)
    except Exception as e:
        logger.error(f"Error getting raw temperature from Sense HAT: {e}")
        return round(random.uniform(20.0, 30.0), 1)


# --- Combined Sensor Data Function ---
def get_all_sensor_data():
    """Collects all relevant sensor data in one call."""
    compensated_temp = get_compensated_temperature()
    humidity = get_humidity()
    cpu_temp = get_cpu_temperature() # Might be None or mock
    raw_temp_from_compensation_logic = None # The 'raw_temp' calculated inside get_compensated_temperature is more refined

    # If we need the direct raw_temperature as well for storage:
    raw_diagnostics_temp = get_raw_temperature_reading()

    data = {
        "temperature_c": compensated_temp,
        "humidity": humidity,
        "cpu_temperature": round(cpu_temp, 1) if cpu_temp is not None else None,
        "raw_temperature_reading": raw_diagnostics_temp # This is the direct reading
    }
    logger.info(f"Collected sensor data: {data}")
    return data

# --- Sense HAT Display (Optional, for direct feedback on device) ---
def display_on_sense_hat(message):
    """Displays a message on the Sense HAT LED matrix if available."""
    if SENSE_HAT_AVAILABLE:
        try:
            sense.show_message(str(message), scroll_speed=0.05)
            logger.debug(f"Displayed on Sense HAT: {message}")
        except Exception as e:
            logger.error(f"Failed to display message on Sense HAT: {e}")
    else:
        logger.debug(f"Sense HAT unavailable. Message not displayed: {message}")

if __name__ == '__main__':
    # Configure basic logging for direct script execution testing
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(message)s')

    logger.info("Testing Sensor Manager...")
    if SENSE_HAT_AVAILABLE:
        logger.info("Sense HAT is AVAILABLE.")
    else:
        logger.info("Sense HAT is NOT AVAILABLE. Using MOCK data.")

    print("\n--- Reading CPU Temperature ---")
    cpu_t = get_cpu_temperature()
    print(f"CPU Temperature: {cpu_t}°C" if cpu_t is not None else "CPU Temperature: N/A")

    print("\n--- Reading Compensated Temperature ---")
    comp_t = get_compensated_temperature()
    print(f"Compensated Temperature: {comp_t}°C")

    print("\n--- Reading Humidity ---")
    hum = get_humidity()
    print(f"Humidity: {hum}%")

    print("\n--- Reading Raw Temperature (Diagnostic) ---")
    raw_t = get_raw_temperature_reading()
    print(f"Raw Temperature (Diagnostic): {raw_t}°C")

    print("\n--- Reading All Sensor Data ---")
    all_data = get_all_sensor_data()
    print(f"All Data: {all_data}")

    print("\n--- Testing Sense HAT Display (if available) ---")
    if SENSE_HAT_AVAILABLE:
        try:
            temp_f = round((all_data.get('temperature_c', 0) * 9/5) + 32, 1)
            display_on_sense_hat(f"T:{temp_f}F H:{all_data.get('humidity',0)}%")
            print("Message displayed on Sense HAT (check device).")
            time.sleep(2) # Give time for message to scroll
            sense.clear()
        except Exception as e:
            print(f"Error during Sense HAT display test: {e}")
    else:
        print("Sense HAT display test skipped (hardware not available).")
        display_on_sense_hat("Test") # This will log a debug message

    logger.info("Sensor Manager test finished.")
