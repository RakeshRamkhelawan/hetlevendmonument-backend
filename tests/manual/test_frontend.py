#!/usr/bin/env python3
"""Frontend connectivity test"""

from datetime import datetime, timezone

import pytest
import requests


def _log(msg):
    """Helper function to log with timestamp"""
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {msg}")


@pytest.mark.skip(reason="Manual test script")
def test_frontend():
    """Frontend connectivity test - manual execution only"""
    _log("=== FRONTEND CONNECTIVITY TEST ===\n")

    _log("[1] Testing frontend dev server on port 5173:")
    try:
        response = requests.get("http://localhost:5173/", timeout=5)
        _log(f"    Status: {response.status_code}")
        _log(f"    Content-Type: {response.headers.get('Content-Type')}")
        if response.status_code == 200:
            _log(f"    Body size: {len(response.text)} bytes")
            if "<!DOCTYPE html>" in response.text or "<html" in response.text:
                _log("    Frontend dev server is SERVING HTML")
            else:
                _log(f"    First 100 chars: {response.text[:100]}")
        else:
            _log(f"    Status {response.status_code}")
    except Exception as e:
        _log(f"    Error: {e}")

    _log("")
    _log("[2] Summary:")
    _log("    Both services should now be running:")
    _log("    - Frontend: http://localhost:5173")
    _log("    - Backend: http://localhost:8001")
    _log("    - CORS: Configured for localhost:5173")
    _log("")
    _log("[3] Next steps:")
    _log("    1. Open browser to http://localhost:5173")
    _log("    2. Clear cache (Ctrl+Shift+Delete)")
    _log("    3. Hard refresh (Ctrl+F5)")
    _log("    4. Test login with admin@sanskritisetu.org / Admin123!")
