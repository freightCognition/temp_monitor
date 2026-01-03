FROM python:3.9-slim-bullseye

# Install system dependencies for Sense HAT
RUN apt-get update && \
    apt-get install -y \
        libatlas-base-dev \
        i2c-tools \
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
COPY temp_monitor.py webhook_service.py sense_hat.py api_models.py wsgi.py ./
COPY static ./static

# Create directories for volumes
RUN mkdir -p /app/logs /app/static

# Expose the Flask port
EXPOSE 8080

# Health check for monitoring and load balancers
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:8080/health', timeout=5)" || exit 1

# Use Waitress for production deployment
CMD ["waitress-serve", "--host=0.0.0.0", "--port=8080", "--threads=1", "--channel-timeout=120", "--call", "wsgi:app"]
