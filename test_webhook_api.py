#!/usr/bin/env python3
"""
Integration tests for Flask-RESTX Webhook API endpoints

Tests the REST API endpoints that manage webhook configuration,
focusing on the bug fix for AttributeError when creating new webhook service.
"""

import sys
import os
import json
import unittest
from unittest.mock import Mock, patch, MagicMock

# Mock the sense_hat module before importing temp_monitor
sys.modules['sense_hat'] = MagicMock()

# Now import after mocking
from temp_monitor import app, webhook_service
from webhook_service import WebhookService, WebhookConfig, AlertThresholds


class TestWebhookAPIEndpoints(unittest.TestCase):
    """Test Flask-RESTX webhook API endpoints"""

    def setUp(self):
        """Set up test client and test data"""
        self.app = app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

        # Get bearer token from environment
        self.token = os.getenv('BEARER_TOKEN', 'test_token_12345')
        self.auth_header = {'Authorization': f'Bearer {self.token}'}

        # Save original webhook_service state
        self.original_webhook_service = webhook_service

    def tearDown(self):
        """Clean up after tests"""
        # Restore original webhook_service
        import temp_monitor
        temp_monitor.webhook_service = self.original_webhook_service

    def test_create_webhook_config_new_service(self):
        """Test creating webhook config when webhook_service doesn't exist

        This is the critical test for the bug fix at line 495.
        When webhook_service is None, creating a new config should work without AttributeError.
        """
        # Ensure webhook_service is None to simulate the bug scenario
        import temp_monitor
        temp_monitor.webhook_service = None

        payload = {
            'webhook': {
                'url': 'https://hooks.slack.com/services/TEST/NEW/CONFIG',
                'enabled': True,
                'retry_count': 5,
                'retry_delay': 10,
                'timeout': 15
            }
        }

        response = self.client.put(
            '/api/webhook/config',
            data=json.dumps(payload),
            content_type='application/json',
            headers=self.auth_header
        )

        # Should succeed without AttributeError
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('message', data)

        # Verify webhook_service was created
        self.assertIsNotNone(temp_monitor.webhook_service)
        self.assertEqual(temp_monitor.webhook_service.webhook_config.url,
                        'https://hooks.slack.com/services/TEST/NEW/CONFIG')
        self.assertEqual(temp_monitor.webhook_service.webhook_config.retry_count, 5)

    def test_create_webhook_config_missing_url(self):
        """Test that creating webhook config without URL returns 400 error"""
        import temp_monitor
        temp_monitor.webhook_service = None

        payload = {
            'webhook': {
                'enabled': True
                # URL is missing - should trigger validation error
            }
        }

        response = self.client.put(
            '/api/webhook/config',
            data=json.dumps(payload),
            content_type='application/json',
            headers=self.auth_header
        )

        # Should fail with 400 Bad Request
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertIn('message', data)
        self.assertIn('URL required', data['message'])

    def test_update_existing_webhook_config(self):
        """Test updating webhook config when service already exists"""
        # Create an existing webhook service
        import temp_monitor
        existing_config = WebhookConfig(
            url='https://hooks.slack.com/services/EXISTING',
            enabled=True
        )
        temp_monitor.webhook_service = WebhookService(webhook_config=existing_config)

        payload = {
            'webhook': {
                'enabled': False,  # Just update enabled, don't change URL
                'retry_count': 7
            }
        }

        response = self.client.put(
            '/api/webhook/config',
            data=json.dumps(payload),
            content_type='application/json',
            headers=self.auth_header
        )

        self.assertEqual(response.status_code, 200)

        # Verify config was updated
        self.assertFalse(temp_monitor.webhook_service.webhook_config.enabled)
        self.assertEqual(temp_monitor.webhook_service.webhook_config.retry_count, 7)

    def test_get_webhook_config_exists(self):
        """Test getting webhook config when it exists"""
        import temp_monitor
        config = WebhookConfig(url='https://hooks.slack.com/test')
        thresholds = AlertThresholds(temp_min_c=15.0, temp_max_c=27.0)
        temp_monitor.webhook_service = WebhookService(
            webhook_config=config,
            alert_thresholds=thresholds
        )

        response = self.client.get(
            '/api/webhook/config',
            headers=self.auth_header
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)

        self.assertIn('webhook', data)
        self.assertEqual(data['webhook']['url'], 'https://hooks.slack.com/test')

        self.assertIn('thresholds', data)
        self.assertEqual(data['thresholds']['temp_min_c'], 15.0)
        self.assertEqual(data['thresholds']['temp_max_c'], 27.0)

    def test_get_webhook_config_not_exists(self):
        """Test getting webhook config when service doesn't exist"""
        import temp_monitor
        temp_monitor.webhook_service = None

        response = self.client.get(
            '/api/webhook/config',
            headers=self.auth_header
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)

        # Should return default values
        self.assertIn('webhook', data)
        self.assertIsNone(data['webhook']['url'])
        self.assertFalse(data['webhook']['enabled'])

    def test_create_webhook_with_thresholds(self):
        """Test creating webhook config with alert thresholds"""
        import temp_monitor
        temp_monitor.webhook_service = None

        payload = {
            'webhook': {
                'url': 'https://hooks.slack.com/services/TEST',
                'enabled': True
            },
            'thresholds': {
                'temp_min_c': 10.0,
                'temp_max_c': 30.0,
                'humidity_min': 20.0,
                'humidity_max': 80.0
            }
        }

        response = self.client.put(
            '/api/webhook/config',
            data=json.dumps(payload),
            content_type='application/json',
            headers=self.auth_header
        )

        self.assertEqual(response.status_code, 200)

        # Verify both webhook and thresholds were set
        self.assertIsNotNone(temp_monitor.webhook_service)
        self.assertIsNotNone(temp_monitor.webhook_service.webhook_config)
        self.assertIsNotNone(temp_monitor.webhook_service.alert_thresholds)

        self.assertEqual(temp_monitor.webhook_service.alert_thresholds.temp_min_c, 10.0)
        self.assertEqual(temp_monitor.webhook_service.alert_thresholds.temp_max_c, 30.0)

    def test_invalid_thresholds_validation(self):
        """Test that invalid thresholds (min >= max) return 400 error"""
        import temp_monitor
        temp_monitor.webhook_service = None

        payload = {
            'webhook': {
                'url': 'https://hooks.slack.com/services/TEST'
            },
            'thresholds': {
                'temp_min_c': 30.0,  # Min > Max - invalid!
                'temp_max_c': 20.0
            }
        }

        response = self.client.put(
            '/api/webhook/config',
            data=json.dumps(payload),
            content_type='application/json',
            headers=self.auth_header
        )

        # Should fail with 400 Bad Request
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertIn('message', data)
        self.assertIn('temp_min_c must be less than temp_max_c', data['message'])

    def test_authentication_required(self):
        """Test that API endpoints require authentication"""
        payload = {
            'webhook': {
                'url': 'https://hooks.slack.com/test'
            }
        }

        # Request without auth header
        response = self.client.put(
            '/api/webhook/config',
            data=json.dumps(payload),
            content_type='application/json'
        )

        # Should fail with 401 Unauthorized
        self.assertEqual(response.status_code, 401)

    def test_invalid_token(self):
        """Test that invalid bearer token is rejected"""
        payload = {
            'webhook': {
                'url': 'https://hooks.slack.com/test'
            }
        }

        # Request with invalid token
        response = self.client.put(
            '/api/webhook/config',
            data=json.dumps(payload),
            content_type='application/json',
            headers={'Authorization': 'Bearer invalid_token_xyz'}
        )

        # Should fail with 403 Forbidden
        self.assertEqual(response.status_code, 403)


def main():
    """Run all tests"""
    print("=" * 70)
    print("Flask-RESTX Webhook API Integration Tests")
    print("=" * 70)
    print()

    # Run tests
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestWebhookAPIEndpoints)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print()
    print("=" * 70)
    if result.wasSuccessful():
        print("✅ ALL API TESTS PASSED")
    else:
        print("❌ SOME TESTS FAILED")
    print("=" * 70)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
