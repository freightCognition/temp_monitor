FROM python:3.9-slim-bullseye

# Install system dependencies for Sense HAT
RUN apt-get update && \
    apt-get install -y \
        python3-sense-hat \
        libatlas-base-dev \
        i2c-tools \
        librtimulib-dev \
        librtimulib7 \
        python3-dev \
        build-essential \
        cmake \
        git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install RTIMULib Python bindings from source
RUN git clone https://github.com/RPi-Distro/RTIMULib.git /tmp/RTIMULib && \
    cd /tmp/RTIMULib/Linux/python && \
    python setup.py install && \
    cd / && \
    rm -rf /tmp/RTIMULib

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY temp_monitor.py generate_token.py ./

# Create directories for volumes
RUN mkdir -p /app/logs /app/assets

# Expose the Flask port
EXPOSE 8080

CMD ["python", "temp_monitor.py"]
