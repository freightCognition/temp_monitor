"""
Test script for webhook signature verification

This script demonstrates how to generate valid HMAC signatures
and send test webhooks to the secure endpoint.

Usage:
    # Set up environment
    echo "WEBHOOK_SECRET=your-secret-key" > .env

    # Run the webhook server in another terminal
    python webhook-with-signature.py

    # Run tests
    python test_webhook.py
"""

import requests
import hmac
import hashlib
import json
import time
import os
from dotenv import load_dotenv

load_dotenv()

WEBHOOK_SECRET = os.environ.get('WEBHOOK_SECRET', 'test-secret-key')
BASE_URL = 'http://localhost:5000/api/webhooks'


def generate_signature(payload, secret, timestamp=None):
    """Generate HMAC-SHA256 signature for webhook"""
    if isinstance(payload, dict):
        payload = json.dumps(payload)

    if timestamp:
        message = f"{timestamp}.{payload}"
    else:
        message = payload

    signature = hmac.new(
        secret.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    return f"sha256={signature}"


def send_webhook(endpoint, payload, use_timestamp=True):
    """Send webhook with valid signature"""
    url = f"{BASE_URL}/{endpoint}"
    body = json.dumps(payload)

    timestamp = str(int(time.time())) if use_timestamp else None
    signature = generate_signature(body, WEBHOOK_SECRET, timestamp)

    headers = {
        'Content-Type': 'application/json',
        'X-Webhook-Signature': signature
    }

    if timestamp:
        headers['X-Webhook-Timestamp'] = timestamp

    print(f"\n{'='*60}")
    print(f"Sending webhook to: {url}")
    print(f"Payload: {body}")
    print(f"Signature: {signature}")
    if timestamp:
        print(f"Timestamp: {timestamp}")
    print('='*60)

    response = requests.post(url, data=body, headers=headers)

    print(f"\nResponse Status: {response.status_code}")
    print(f"Response Body: {response.text}")

    return response


def test_valid_signature():
    """Test with valid signature"""
    print("\n" + "="*60)
    print("TEST 1: Valid Signature")
    print("="*60)

    payload = {
        'event_type': 'user.created',
        'timestamp': '2024-01-15T10:30:00Z',
        'data': {
            'user_id': '12345',
            'email': 'test@example.com'
        }
    }

    response = send_webhook('secure', payload)
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    print("✓ Test passed")


def test_invalid_signature():
    """Test with invalid signature"""
    print("\n" + "="*60)
    print("TEST 2: Invalid Signature")
    print("="*60)

    url = f"{BASE_URL}/secure"
    payload = {'event_type': 'test', 'data': {}}
    body = json.dumps(payload)

    headers = {
        'Content-Type': 'application/json',
        'X-Webhook-Signature': 'sha256=invalid_signature_here'
    }

    print(f"Sending webhook with INVALID signature to: {url}")
    response = requests.post(url, data=body, headers=headers)

    print(f"\nResponse Status: {response.status_code}")
    print(f"Response Body: {response.text}")

    assert response.status_code == 401, f"Expected 401, got {response.status_code}"
    print("✓ Test passed (correctly rejected)")


def test_missing_signature():
    """Test without signature header"""
    print("\n" + "="*60)
    print("TEST 3: Missing Signature")
    print("="*60)

    url = f"{BASE_URL}/secure"
    payload = {'event_type': 'test', 'data': {}}

    headers = {'Content-Type': 'application/json'}

    print(f"Sending webhook WITHOUT signature to: {url}")
    response = requests.post(url, json=payload, headers=headers)

    print(f"\nResponse Status: {response.status_code}")
    print(f"Response Body: {response.text}")

    assert response.status_code == 401, f"Expected 401, got {response.status_code}"
    print("✓ Test passed (correctly rejected)")


def test_expired_timestamp():
    """Test with expired timestamp"""
    print("\n" + "="*60)
    print("TEST 4: Expired Timestamp")
    print("="*60)

    url = f"{BASE_URL}/secure"
    payload = {'event_type': 'test', 'timestamp': '2024-01-15T10:30:00Z', 'data': {}}
    body = json.dumps(payload)

    # Use timestamp from 10 minutes ago (should be rejected)
    old_timestamp = str(int(time.time()) - 600)
    signature = generate_signature(body, WEBHOOK_SECRET, old_timestamp)

    headers = {
        'Content-Type': 'application/json',
        'X-Webhook-Signature': signature,
        'X-Webhook-Timestamp': old_timestamp
    }

    print(f"Sending webhook with OLD timestamp: {old_timestamp}")
    response = requests.post(url, data=body, headers=headers)

    print(f"\nResponse Status: {response.status_code}")
    print(f"Response Body: {response.text}")

    assert response.status_code == 401, f"Expected 401, got {response.status_code}"
    print("✓ Test passed (correctly rejected)")


def test_verify_endpoint():
    """Test the signature verification endpoint"""
    print("\n" + "="*60)
    print("TEST 5: Verify Endpoint")
    print("="*60)

    payload = {}
    response = send_webhook('verify', payload)

    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    data = response.json()
    assert data['verified'] == True
    print("✓ Test passed")


def test_rate_limiting():
    """Test rate limiting (sends many requests)"""
    print("\n" + "="*60)
    print("TEST 6: Rate Limiting")
    print("="*60)

    payload = {'event_type': 'test', 'timestamp': '2024-01-15T10:30:00Z', 'data': {}}

    print("Sending 105 requests rapidly...")
    success_count = 0
    rate_limited_count = 0

    for i in range(105):
        response = send_webhook('secure', payload, use_timestamp=True)
        if response.status_code == 200:
            success_count += 1
        elif response.status_code == 429:
            rate_limited_count += 1

        # Don't print every response
        if (i + 1) % 20 == 0:
            print(f"  Sent {i + 1} requests...")

    print(f"\nSuccessful: {success_count}")
    print(f"Rate Limited: {rate_limited_count}")

    assert rate_limited_count > 0, "Expected some requests to be rate limited"
    print("✓ Test passed (rate limiting working)")


def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("Flask-RESTX Webhook Security Tests")
    print("="*60)
    print(f"Target: {BASE_URL}")
    print(f"Secret: {WEBHOOK_SECRET[:10]}...")
    print("="*60)

    try:
        # Check if server is running
        response = requests.get('http://localhost:5000/health', timeout=2)
        if response.status_code != 200:
            print("\n✗ Server health check failed")
            print("  Make sure webhook-with-signature.py is running")
            return
    except requests.exceptions.ConnectionError:
        print("\n✗ Cannot connect to server")
        print("  Start the server with: python webhook-with-signature.py")
        return

    tests = [
        test_valid_signature,
        test_invalid_signature,
        test_missing_signature,
        test_expired_timestamp,
        test_verify_endpoint,
        # test_rate_limiting,  # Uncomment to test rate limiting
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"\n✗ Test failed: {e}")
            failed += 1
        except Exception as e:
            print(f"\n✗ Test error: {e}")
            failed += 1

    print("\n" + "="*60)
    print(f"Test Results: {passed} passed, {failed} failed")
    print("="*60 + "\n")


if __name__ == '__main__':
    main()
