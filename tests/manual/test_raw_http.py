"""Direct test met curl-achtige output"""

import http.client
import json

import pytest


@pytest.mark.skip(reason="Manual test script")
def test_raw_http_login():
    """Direct HTTP test - manual execution only"""
    conn = http.client.HTTPConnection("localhost", 8001, timeout=30)

    # Create JSON body
    body = json.dumps({"email": "admin@sanskritisetu.org", "password": "Admin123!"})

    # Send request
    headers = {"Content-Type": "application/json", "Content-Length": str(len(body))}

    print(f"Sending: {body}")
    print(f"Headers: {headers}")

    conn.request("POST", "/api/v1/auth/login", body, headers)
    response = conn.getresponse()

    print(f"\nStatus: {response.status} {response.reason}")
    print(f"Response: {response.read().decode()}")

    conn.close()
