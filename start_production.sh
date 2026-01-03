#!/bin/bash

# Production startup script for Raspberry Pi 4
# This script starts the temperature monitor service using Waitress
# for production-grade deployment.

set -e

export PRODUCTION_MODE=true

# Check if running on Raspberry Pi
if [ -f /proc/device-tree/model ]; then
    MODEL=$(cat /proc/device-tree/model)
    echo "Running on: $MODEL"
fi

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Error: Virtual environment not found at ./venv"
    echo "Please create one with: python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Verify required modules are installed
echo "Checking dependencies..."
python -c "import waitress, psutil, flask" || {
    echo "Error: Required packages not installed"
    echo "Run: pip install -r requirements.txt"
    exit 1
}

# Create logs directory if it doesn't exist
mkdir -p logs

echo "Starting Temperature Monitor in production mode..."
echo "Server will be available at http://localhost:8080"
echo "Health endpoint: http://localhost:8080/health"
echo "Metrics endpoint: http://localhost:8080/metrics"
echo "API documentation: http://localhost:8080/docs"
echo ""
echo "Press Ctrl+C to stop"
echo ""

# Start server with Waitress
waitress-serve \
    --host=0.0.0.0 \
    --port=8080 \
    --threads=1 \
    --channel-timeout=120 \
    --connection-limit=50 \
    --call wsgi:app
