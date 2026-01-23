"""
Webhook Service for Temperature Monitor

Handles outbound webhooks to Slack for temperature/humidity alerts and status updates.
"""

import requests
import logging
import time
import json
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict
from datetime import datetime
import threading
from urllib.parse import urlparse


@dataclass
class WebhookConfig:
    """Configuration for a webhook endpoint"""
    url: str
    enabled: bool = True
    retry_count: int = 3
    retry_delay: int = 5  # seconds
    timeout: int = 10  # seconds


@dataclass
class AlertThresholds:
    """Temperature and humidity thresholds for alerts"""
    temp_min_c: Optional[float] = 15.0  # 59°F
    temp_max_c: Optional[float] = 32.0  # 90°F
    humidity_min: Optional[float] = 20.0
    humidity_max: Optional[float] = 70.0


class WebhookService:
    """Service for managing and sending webhooks"""

    def __init__(self, webhook_config: Optional[WebhookConfig] = None,
                 alert_thresholds: Optional[AlertThresholds] = None,
                 alert_cooldown: Optional[int] = None):
        self.webhook_config = webhook_config
        self.alert_thresholds = alert_thresholds or AlertThresholds()
        self.last_alert_time = {}  # Track last alert per type to avoid spam
        self.alert_cooldown = alert_cooldown if alert_cooldown is not None else 900
        self._lock = threading.Lock()

    def _mask_url(self, url: str) -> str:
        """
        Mask webhook URL by returning only scheme and host for security.

        This prevents sensitive path components and tokens from being exposed in logs.

        Args:
            url: Full webhook URL

        Returns:
            Masked URL in format 'scheme://host' or '<invalid-url>' if malformed
        """
        try:
            parsed = urlparse(url)
            if parsed.scheme and parsed.netloc:
                return f"{parsed.scheme}://{parsed.netloc}"
            else:
                return "<invalid-url>"
        except Exception as e:
            logging.warning(f"Error masking webhook URL: {e}")
            return "<invalid-url>"

    def set_webhook_config(self, config: WebhookConfig):
        """Update webhook configuration"""
        with self._lock:
            self.webhook_config = config
            logging.info(f"Webhook configuration updated: {self._mask_url(config.url)}")

    def set_alert_thresholds(self, thresholds: AlertThresholds):
        """Update alert thresholds"""
        with self._lock:
            self.alert_thresholds = thresholds
            logging.info(f"Alert thresholds updated: {asdict(thresholds)}")

    def _send_webhook(self, payload: Dict[str, Any]) -> bool:
        """
        Send webhook with retry logic

        Args:
            payload: Dictionary to send as JSON

        Returns:
            True if successful, False otherwise
        """
        if not self.webhook_config or not self.webhook_config.enabled:
            logging.debug("Webhook not configured or disabled, skipping send")
            return False

        url = self.webhook_config.url

        for attempt in range(self.webhook_config.retry_count):
            try:
                response = requests.post(
                    url,
                    json=payload,
                    timeout=self.webhook_config.timeout,
                    headers={'Content-Type': 'application/json'}
                )

                if response.status_code == 200:
                    logging.info(f"Webhook sent successfully to {self._mask_url(url)}")
                    return True
                else:
                    logging.warning(
                        f"Webhook failed with status {response.status_code}: {response.text}"
                    )

            except requests.exceptions.Timeout:
                logging.error(f"Webhook timeout (attempt {attempt + 1}/{self.webhook_config.retry_count})")
            except requests.exceptions.RequestException as e:
                logging.error(f"Webhook request failed (attempt {attempt + 1}/{self.webhook_config.retry_count}): {e}")

            # Wait before retry (exponential backoff)
            if attempt < self.webhook_config.retry_count - 1:
                delay = min(self.webhook_config.retry_delay * (2 ** attempt), 300)  # Cap at 5 minutes
                time.sleep(delay)

        logging.error(f"Webhook failed after {self.webhook_config.retry_count} attempts")
        return False

    def _can_send_alert(self, alert_type: str) -> bool:
        """
        Check if enough time has passed since last alert of this type

        Args:
            alert_type: Type of alert (e.g., 'temp_high', 'humidity_low')

        Returns:
            True if alert can be sent, False if in cooldown period
        """
        with self._lock:
            last_time = self.last_alert_time.get(alert_type)
            if last_time is None:
                return True

            elapsed = time.time() - last_time
            return elapsed >= self.alert_cooldown

    def _mark_alert_sent(self, alert_type: str):
        """Record that an alert was sent"""
        with self._lock:
            self.last_alert_time[alert_type] = time.time()

    def send_slack_message(self, text: str, color: str = "good",
                          fields: Optional[List[Dict[str, str]]] = None) -> bool:
        """
        Send a formatted Slack message

        Args:
            text: Main message text
            color: Message color (good, warning, danger, or hex color)
            fields: Optional list of field dictionaries with 'title' and 'value'

        Returns:
            True if successful, False otherwise
        """
        attachment = {
            "color": color,
            "text": text,
            "ts": int(time.time())
        }

        if fields:
            attachment["fields"] = fields

        payload = {
            "attachments": [attachment]
        }

        return self._send_webhook(payload)

    def check_and_alert(self, temperature_c: float, humidity: float,
                       timestamp: str) -> Dict[str, bool]:
        """
        Check sensor readings against thresholds and send alerts if needed

        Args:
            temperature_c: Current temperature in Celsius
            humidity: Current humidity percentage
            timestamp: Timestamp of reading

        Returns:
            Dictionary with alert types as keys and success status as values
        """
        alerts_sent = {}

        # Check temperature high
        if (self.alert_thresholds.temp_max_c is not None and
            temperature_c > self.alert_thresholds.temp_max_c):

            if self._can_send_alert('temp_high'):
                temp_f = round((temperature_c * 9/5) + 32, 1)
                max_f = round((self.alert_thresholds.temp_max_c * 9/5) + 32, 1)

                success = self.send_slack_message(
                    text=f"🔥 *Temperature Alert: HIGH*",
                    color="danger",
                    fields=[
                        {
                            "title": "Current Temperature",
                            "value": f"{temperature_c}°C ({temp_f}°F)",
                            "short": True
                        },
                        {
                            "title": "Threshold",
                            "value": f"{self.alert_thresholds.temp_max_c}°C ({max_f}°F)",
                            "short": True
                        },
                        {
                            "title": "Timestamp",
                            "value": timestamp,
                            "short": False
                        }
                    ]
                )

                if success:
                    self._mark_alert_sent('temp_high')
                alerts_sent['temp_high'] = success

        # Check temperature low
        if (self.alert_thresholds.temp_min_c is not None and
            temperature_c < self.alert_thresholds.temp_min_c):

            if self._can_send_alert('temp_low'):
                temp_f = round((temperature_c * 9/5) + 32, 1)
                min_f = round((self.alert_thresholds.temp_min_c * 9/5) + 32, 1)

                success = self.send_slack_message(
                    text=f"❄️ *Temperature Alert: LOW*",
                    color="warning",
                    fields=[
                        {
                            "title": "Current Temperature",
                            "value": f"{temperature_c}°C ({temp_f}°F)",
                            "short": True
                        },
                        {
                            "title": "Threshold",
                            "value": f"{self.alert_thresholds.temp_min_c}°C ({min_f}°F)",
                            "short": True
                        },
                        {
                            "title": "Timestamp",
                            "value": timestamp,
                            "short": False
                        }
                    ]
                )

                if success:
                    self._mark_alert_sent('temp_low')
                alerts_sent['temp_low'] = success

        # Check humidity high
        if (self.alert_thresholds.humidity_max is not None and
            humidity > self.alert_thresholds.humidity_max):

            if self._can_send_alert('humidity_high'):
                success = self.send_slack_message(
                    text=f"💧 *Humidity Alert: HIGH*",
                    color="warning",
                    fields=[
                        {
                            "title": "Current Humidity",
                            "value": f"{humidity}%",
                            "short": True
                        },
                        {
                            "title": "Threshold",
                            "value": f"{self.alert_thresholds.humidity_max}%",
                            "short": True
                        },
                        {
                            "title": "Timestamp",
                            "value": timestamp,
                            "short": False
                        }
                    ]
                )

                if success:
                    self._mark_alert_sent('humidity_high')
                alerts_sent['humidity_high'] = success

        # Check humidity low
        if (self.alert_thresholds.humidity_min is not None and
            humidity < self.alert_thresholds.humidity_min):

            if self._can_send_alert('humidity_low'):
                success = self.send_slack_message(
                    text=f"🏜️ *Humidity Alert: LOW*",
                    color="warning",
                    fields=[
                        {
                            "title": "Current Humidity",
                            "value": f"{humidity}%",
                            "short": True
                        },
                        {
                            "title": "Threshold",
                            "value": f"{self.alert_thresholds.humidity_min}%",
                            "short": True
                        },
                        {
                            "title": "Timestamp",
                            "value": timestamp,
                            "short": False
                        }
                    ]
                )

                if success:
                    self._mark_alert_sent('humidity_low')
                alerts_sent['humidity_low'] = success

        return alerts_sent

    def send_status_update(self, temperature_c: float, humidity: float,
                          cpu_temp: Optional[float], timestamp: str) -> bool:
        """
        Send a status update with current readings

        Args:
            temperature_c: Current temperature in Celsius
            humidity: Current humidity percentage
            cpu_temp: CPU temperature if available
            timestamp: Timestamp of reading

        Returns:
            True if successful, False otherwise
        """
        temp_f = round((temperature_c * 9/5) + 32, 1)

        fields = [
            {
                "title": "Temperature",
                "value": f"{temperature_c}°C ({temp_f}°F)",
                "short": True
            },
            {
                "title": "Humidity",
                "value": f"{humidity}%",
                "short": True
            }
        ]

        if cpu_temp is not None:
            fields.append({
                "title": "CPU Temperature",
                "value": f"{cpu_temp}°C",
                "short": True
            })

        fields.append({
            "title": "Last Updated",
            "value": timestamp,
            "short": False
        })

        return self.send_slack_message(
            text="📊 *Server Room Status Update*",
            color="good",
            fields=fields
        )

    def send_system_event(self, event_type: str, message: str,
                         severity: str = "info") -> bool:
        """
        Send a system event notification

        Args:
            event_type: Type of event (startup, shutdown, error, etc.)
            message: Event message
            severity: Severity level (info, warning, error)

        Returns:
            True if successful, False otherwise
        """
        color_map = {
            "info": "good",
            "warning": "warning",
            "error": "danger"
        }

        icon_map = {
            "startup": "🚀",
            "shutdown": "🛑",
            "error": "⚠️",
            "info": "ℹ️"
        }

        icon = icon_map.get(event_type, "📢")
        color = color_map.get(severity, "good")

        return self.send_slack_message(
            text=f"{icon} *System Event: {event_type.upper()}*\n{message}",
            color=color,
            fields=[
                {
                    "title": "Timestamp",
                    "value": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "short": False
                }
            ]
        )
