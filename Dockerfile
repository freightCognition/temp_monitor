FROM debian:bullseye-slim

# Install system Python, Sense HAT stack, and I2C tools
# Using system Python ensures apt-installed packages (sense-hat, RTIMU) are visible
RUN apt-get update && \
    apt-get install -y \
      python3 \
      python3-pip \
      python3-sense-hat \
      i2c-tools && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install only Flask and python-dotenv via pip
# sense-hat is provided by the apt python3-sense-hat package above
RUN python3 -m pip install --no-cache-dir flask==2.3.3 python-dotenv==1.0.0

# Copy application files
COPY temp_monitor.py generate_token.py ./

# Create directories for volumes
RUN mkdir -p /app/logs /app/assets

# Expose the Flask port
EXPOSE 8080

CMD ["python3", "temp_monitor.py"]
