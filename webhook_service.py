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
        self.active_alerts = set()  # Alert types currently in an alerting state
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

    def _scrub_exception(self, exc: Exception, url: str) -> str:
        """
        Remove the webhook URL (and its secret path segments) from an
        exception's message before it gets logged.

        requests exceptions (e.g. connection errors) often embed the full
        URL or its path in their message, which would otherwise leak the
        Slack webhook secret into logs and defeat _mask_url.

        Args:
            exc: The exception whose message may contain the secret URL
            url: The webhook URL that was being requested

        Returns:
            The exception message with the URL/path replaced by a masked form
        """
        text = str(exc)
        text = text.replace(url, self._mask_url(url))

        try:
            path = urlparse(url).path
            if path:
                text = text.replace(path, "<redacted-path>")
        except Exception:
            pass

        return text

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
        # Snapshot config under the lock so a concurrent set_webhook_config()
        # can't hand us a null/half-updated config between the check and use.
        with self._lock:
            config = self.webhook_config

        if not config or not config.enabled:
            logging.debug("Webhook not configured or disabled, skipping send")
            return False

        url = config.url

        for attempt in range(config.retry_count):
            try:
                response = requests.post(
                    url,
                    json=payload,
                    timeout=config.timeout,
                    headers={'Content-Type': 'application/json'}
                )

                if 200 <= response.status_code < 300:
                    logging.info(f"Webhook sent successfully to {self._mask_url(url)}")
                    return True
                else:
                    body = (response.text or "")[:200]
                    logging.warning(
                        f"Webhook failed with status {response.status_code}: {body}"
                    )

            except requests.exceptions.Timeout:
                logging.error(f"Webhook timeout (attempt {attempt + 1}/{config.retry_count})")
            except requests.exceptions.RequestException as e:
                scrubbed = self._scrub_exception(e, url)
                logging.error(f"Webhook request failed (attempt {attempt + 1}/{config.retry_count}): {scrubbed}")

            # Wait before retry (exponential backoff), but not after the last attempt
            if attempt < config.retry_count - 1:
                delay = min(config.retry_delay * (2 ** attempt), 300)  # Cap at 5 minutes
                time.sleep(delay)

        logging.error(f"Webhook failed after {config.retry_count} attempts")
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

            # time.monotonic() never runs backwards, unlike time.time() which
            # can be stepped by NTP (a Raspberry Pi has no RTC, so this
            # happens at every boot). A backwards wall-clock step would make
            # `elapsed` negative and suppress every alert type.
            elapsed = time.monotonic() - last_time
            return elapsed >= self.alert_cooldown

    def _mark_alert_sent(self, alert_type: str):
        """Record that an alert was sent"""
        with self._lock:
            self.last_alert_time[alert_type] = time.monotonic()

    def send_slack_message(self, text: str, color: str = "good",
                          fields: Optional[List[Dict[str, Any]]] = None) -> bool:
        """
        Send a formatted Slack message

        Args:
            text: Main message text
            color: Message color (good, warning, danger, or hex color)
            fields: Optional list of field dictionaries with 'title', 'value',
                and 'short' (bool)

        Returns:
            True if successful, False otherwise
        """
        attachment = {
            "color": color,
            "text": text,
            # Required by Slack's legacy attachment schema: without it, push
            # notifications render with empty/blank text.
            "fallback": text,
            "mrkdwn_in": ["text"],
            "ts": int(time.time())
        }

        if fields:
            attachment["fields"] = fields

        payload = {
            "attachments": [attachment]
        }

        return self._send_webhook(payload)

    def _mark_alert_active(self, alert_type: str):
        """Record that an alert type is currently in an alerting state"""
        with self._lock:
            self.active_alerts.add(alert_type)

    # Recovery notification text, keyed by the same alert_type strings used
    # by _can_send_alert / _mark_alert_sent / _mark_alert_active. Keeping the
    # text in one table means a call site only has to name the alert type
    # correctly, not also restate its message.
    _RESOLVED_MESSAGES = {
        'temp_high': "✅ *Temperature Alert Resolved: HIGH*",
        'temp_low': "✅ *Temperature Alert Resolved: LOW*",
        'humidity_high': "✅ *Humidity Alert Resolved: HIGH*",
        'humidity_low': "✅ *Humidity Alert Resolved: LOW*",
    }

    def _record_recovery(self, alerts_sent: Dict[str, bool], alert_type: str,
                         timestamp: str):
        """Run recovery for alert_type and record the outcome in alerts_sent.

        No key is added when the alert type was not active, so a reading that
        was never in an alerting state produces no "<type>_resolved" entry.
        """
        resolved = self._handle_recovery(
            alert_type, self._RESOLVED_MESSAGES[alert_type], timestamp)
        if resolved is not None:
            alerts_sent[f'{alert_type}_resolved'] = resolved

    def _handle_recovery(self, alert_type: str, resolved_text: str,
                        timestamp: str) -> Optional[bool]:
        """
        If alert_type is currently active, clear its cooldown and send a
        "resolved" notification.

        Without this, a spike sends an alert, a recovery is silent, and a
        second spike shortly after gets suppressed by the still-active
        cooldown from the FIRST spike -- total silence until the cooldown
        window expires even though the room is alerting again.

        Args:
            alert_type: Type of alert (e.g., 'temp_high', 'humidity_low')
            resolved_text: Message text for the resolved notification
            timestamp: Timestamp of the reading that triggered recovery

        Returns:
            True/False success of the resolved notification if one was sent,
            None if the alert type was not active (nothing to resolve)
        """
        with self._lock:
            if alert_type not in self.active_alerts:
                return None
            self.active_alerts.discard(alert_type)
            self.last_alert_time.pop(alert_type, None)

        return self.send_slack_message(
            text=resolved_text,
            color="good",
            fields=[
                {
                    "title": "Timestamp",
                    "value": timestamp,
                    "short": False
                }
            ]
        )

    def check_and_alert(self, temperature_c: float, humidity: float,
                       timestamp: str) -> Dict[str, bool]:
        """
        Check sensor readings against thresholds and send alerts if needed.
        Also detects recovery: when a reading returns inside thresholds for
        an alert type that was active, the cooldown is cleared and a
        "resolved" notification is sent.

        Args:
            temperature_c: Current temperature in Celsius
            humidity: Current humidity percentage
            timestamp: Timestamp of reading

        Returns:
            Dictionary with alert types (and "<type>_resolved" for recovery
            notifications) as keys and success status as values
        """
        alerts_sent = {}

        # Snapshot thresholds under the lock so a concurrent
        # set_alert_thresholds() can't hand us a torn/half-updated view
        # (e.g. a None check followed by a multiply against a value that
        # changed in between).
        with self._lock:
            thresholds = self.alert_thresholds

        # Check temperature high
        if (thresholds.temp_max_c is not None and
            temperature_c > thresholds.temp_max_c):

            if self._can_send_alert('temp_high'):
                temp_f = round((temperature_c * 9/5) + 32, 1)
                max_f = round((thresholds.temp_max_c * 9/5) + 32, 1)

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
                            "value": f"{thresholds.temp_max_c}°C ({max_f}°F)",
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
                    self._mark_alert_active('temp_high')
                alerts_sent['temp_high'] = success
        else:
            self._record_recovery(alerts_sent, 'temp_high', timestamp)

        # Check temperature low
        if (thresholds.temp_min_c is not None and
            temperature_c < thresholds.temp_min_c):

            if self._can_send_alert('temp_low'):
                temp_f = round((temperature_c * 9/5) + 32, 1)
                min_f = round((thresholds.temp_min_c * 9/5) + 32, 1)

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
                            "value": f"{thresholds.temp_min_c}°C ({min_f}°F)",
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
                    self._mark_alert_active('temp_low')
                alerts_sent['temp_low'] = success
        else:
            self._record_recovery(alerts_sent, 'temp_low', timestamp)

        # Check humidity high
        if (thresholds.humidity_max is not None and
            humidity > thresholds.humidity_max):

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
                            "value": f"{thresholds.humidity_max}%",
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
                    self._mark_alert_active('humidity_high')
                alerts_sent['humidity_high'] = success
        else:
            self._record_recovery(alerts_sent, 'humidity_high', timestamp)

        # Check humidity low
        if (thresholds.humidity_min is not None and
            humidity < thresholds.humidity_min):

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
                            "value": f"{thresholds.humidity_min}%",
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
                    self._mark_alert_active('humidity_low')
                alerts_sent['humidity_low'] = success
        else:
            self._record_recovery(alerts_sent, 'humidity_low', timestamp)

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
