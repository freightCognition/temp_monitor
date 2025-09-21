"""
Configuration management for Temperature Monitor application.
Supports environment variables with sensible defaults.
"""

import os
from pathlib import Path
import logging


class Config:
    """Configuration class that loads settings from environment variables."""
    
    def __init__(self):
        self.base_dir = Path(__file__).parent.absolute()
        
    # Environment detection
    @property
    def environment(self):
        return os.getenv('ENVIRONMENT', 'development').lower()
    
    @property
    def is_production(self):
        return self.environment == 'production'
    
    @property
    def is_development(self):
        return self.environment == 'development'
    
    @property
    def is_docker(self):
        return os.getenv('RUNNING_IN_DOCKER', 'false').lower() == 'true'
    
    # File paths
    @property
    def log_file_path(self):
        default_path = self.base_dir / 'temp_monitor.log' if not self.is_docker else '/app/logs/temp_monitor.log'
        return os.getenv('LOG_FILE_PATH', str(default_path))
    
    @property
    def logo_image_path(self):
        default_path = self.base_dir / 'assets' / 'My-img8bit-1com-Effect.gif'
        return os.getenv('LOGO_IMAGE_PATH', str(default_path))
    
    @property
    def favicon_path(self):
        default_path = self.base_dir / 'assets' / 'temp-favicon.ico'
        return os.getenv('FAVICON_PATH', str(default_path))
    
    # Flask configuration
    @property
    def host(self):
        return os.getenv('HOST', '0.0.0.0')
    
    @property
    def port(self):
        return int(os.getenv('PORT', '5000'))
    
    @property
    def debug(self):
        return os.getenv('DEBUG', 'false').lower() == 'true' and not self.is_production
    
    # Sensor configuration
    @property
    def sampling_interval(self):
        return float(os.getenv('SAMPLING_INTERVAL', '10.0'))
    
    @property
    def cpu_temp_factor(self):
        return float(os.getenv('CPU_TEMP_FACTOR', '2.0'))
    
    @property
    def temperature_samples(self):
        return int(os.getenv('TEMPERATURE_SAMPLES', '3'))
    
    @property
    def use_mock_sensors(self):
        # Auto-detect if we should use mock sensors
        if os.getenv('USE_MOCK_SENSORS'):
            return os.getenv('USE_MOCK_SENSORS', 'false').lower() == 'true'
        # Default to mock in Docker or if sense-hat import fails
        return self.is_docker or not self._sense_hat_available()
    
    # Logging configuration
    @property
    def log_level(self):
        level_str = os.getenv('LOG_LEVEL', 'INFO' if self.is_production else 'DEBUG')
        return getattr(logging, level_str.upper(), logging.INFO)
    
    @property
    def log_format(self):
        if self.is_production or self.is_docker:
            return '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s"}'
        return '%(asctime)s - %(levelname)s - %(message)s'
    
    # Security configuration
    @property
    def bearer_token(self):
        return os.getenv('BEARER_TOKEN')
    
    @property
    def token_min_length(self):
        return int(os.getenv('TOKEN_MIN_LENGTH', '32'))
    
    # API configuration
    @property
    def enable_cors(self):
        return os.getenv('ENABLE_CORS', 'false').lower() == 'true'
    
    @property
    def cors_origins(self):
        return os.getenv('CORS_ORIGINS', '*').split(',')
    
    @property
    def rate_limit_per_minute(self):
        return int(os.getenv('RATE_LIMIT_PER_MINUTE', '60'))
    
    # Health check configuration
    @property
    def health_check_enabled(self):
        return os.getenv('HEALTH_CHECK_ENABLED', 'true').lower() == 'true'
    
    def _sense_hat_available(self):
        """Check if Sense HAT is available."""
        try:
            from sense_hat import SenseHat
            sense = SenseHat()
            return True
        except Exception:
            return False
    
    def validate(self):
        """Validate configuration and return list of issues."""
        issues = []
        
        # Check if log directory is writable
        log_path = Path(self.log_file_path)
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            # Test write access
            test_file = log_path.parent / '.write_test'
            test_file.touch()
            test_file.unlink()
        except Exception as e:
            issues.append(f"Log directory not writable: {e}")
        
        # Check bearer token
        if not self.bearer_token:
            issues.append("BEARER_TOKEN not set - API endpoints will be inaccessible")
        elif len(self.bearer_token) < self.token_min_length:
            issues.append(f"BEARER_TOKEN too short (minimum {self.token_min_length} characters)")
        
        # Check sampling interval
        if self.sampling_interval < 1.0:
            issues.append("SAMPLING_INTERVAL too low (minimum 1.0 seconds)")
        
        return issues
    
    def create_directories(self):
        """Create necessary directories."""
        directories = [
            Path(self.log_file_path).parent,
            Path(self.logo_image_path).parent,
            Path(self.favicon_path).parent,
        ]
        
        for directory in directories:
            try:
                directory.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                print(f"Warning: Could not create directory {directory}: {e}")


# Global configuration instance
config = Config()