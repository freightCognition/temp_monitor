FROM python:3.9-slim-bullseye

# Install system dependencies for Sense HAT and I2C hardware access
# Note: python3-sense-hat provides the sense_hat module with RTIMU support
# We don't install sense-hat via pip to avoid conflicts with the apt package
RUN apt-get update && \
    apt-get install -y python3-sense-hat i2c-tools && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install only Flask and python-dotenv via pip
# sense-hat is provided by the apt python3-sense-hat package above
RUN pip install --no-cache-dir flask==2.3.3 python-dotenv==1.0.0

# Copy application files
COPY temp_monitor.py generate_token.py ./

# Create directories for volumes
RUN mkdir -p /app/logs /app/assets

# Expose the Flask port
EXPOSE 8080

CMD ["python", "temp_monitor.py"]
