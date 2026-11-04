#!/usr/bin/env python3
"""
Wait for Docker services to be ready before running tests.
Polls health endpoints with exponential backoff.

Usage:
    python scripts/wait_for_services.py
    python scripts/wait_for_services.py --timeout 120
"""

import argparse
import socket
import sys
import time
import urllib.error
import urllib.request
from typing import Dict, List, Tuple

# Service configurations: (name, url, expected_status_codes)
SERVICES: List[Tuple[str, str, List[int]]] = [
    ("PostgreSQL", "http://localhost:5434/", [200, 404, 500]),  # Any response = alive
    ("Redis", "http://localhost:6380/", [200, 404, 500]),
    ("Backend API", "http://localhost:8000/api/v1/", [200, 401, 403, 404]),
    ("RabbitMQ", "http://localhost:15673/", [200, 401]),
]

# For TCP-only checks (no HTTP)
TCP_SERVICES: List[Tuple[str, str, int]] = [
    ("PostgreSQL", "localhost", 5434),
    ("Redis", "localhost", 6380),
    ("RabbitMQ", "localhost", 5673),
]


def check_tcp(host: str, port: int, timeout: float = 2.0) -> bool:
    """Check if a TCP port is accepting connections."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, socket.error, ConnectionRefusedError, OSError):
        return False


def check_http(url: str, expected_codes: List[int], timeout: float = 5.0) -> Tuple[bool, str]:
    """
    Check if HTTP endpoint responds with expected status code.

    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        request = urllib.request.Request(url, method="GET")
        request.add_header("User-Agent", "wait-for-services/1.0")

        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = response.status
            if status in expected_codes:
                return True, f"HTTP {status}"
            return False, f"Unexpected HTTP {status}"

    except urllib.error.HTTPError as e:
        # HTTP errors still mean the service is responding
        if e.code in expected_codes:
            return True, f"HTTP {e.code}"
        return False, f"HTTP {e.code}"

    except urllib.error.URLError as e:
        return False, f"Connection failed: {e.reason}"

    except socket.timeout:
        return False, "Timeout"

    except Exception as e:
        return False, f"Error: {e}"


def wait_for_services(timeout: int = 60, interval: float = 2.0, use_tcp: bool = True) -> bool:
    """
    Wait for all services to become available.

    Args:
        timeout: Maximum seconds to wait
        interval: Seconds between checks
        use_tcp: Use TCP checks instead of HTTP for infrastructure services

    Returns:
        True if all services ready, False if timeout
    """
    start_time = time.time()
    services_to_check = TCP_SERVICES if use_tcp else []
    http_services = [("Backend API", "http://localhost:8000/api/v1/", [200, 401, 403, 404])]

    print(f"[INFO] Waiting for services (timeout: {timeout}s)...")
    print("=" * 60)

    ready: Dict[str, bool] = {name: False for name, _, _ in services_to_check + http_services}

    while time.time() - start_time < timeout:
        all_ready = True

        # Check TCP services
        for name, host, port in services_to_check:
            if not ready[name]:
                if check_tcp(host, port):
                    ready[name] = True
                    print(f"[OK] {name} is ready (TCP {host}:{port})")
                else:
                    all_ready = False

        # Check HTTP services
        for name, url, expected in http_services:
            if not ready[name]:
                success, msg = check_http(url, expected)
                if success:
                    ready[name] = True
                    print(f"[OK] {name} is ready ({msg})")
                else:
                    all_ready = False

        if all_ready:
            elapsed = time.time() - start_time
            print("=" * 60)
            print(f"[OK] All services ready in {elapsed:.1f}s")
            return True

        # Show waiting status
        waiting = [name for name, is_ready in ready.items() if not is_ready]
        if waiting:
            elapsed = time.time() - start_time
            print(f"[WAIT] {elapsed:.0f}s - Waiting for: {', '.join(waiting)}")

        time.sleep(interval)

    # Timeout reached
    print("=" * 60)
    print(f"[FAIL] Timeout after {timeout}s")
    not_ready = [name for name, is_ready in ready.items() if not is_ready]
    print(f"[FAIL] Services not ready: {', '.join(not_ready)}")
    return False


def main():
    parser = argparse.ArgumentParser(description="Wait for Docker services to be ready")
    parser.add_argument(
        "--timeout",
        "-t",
        type=int,
        default=60,
        help="Maximum seconds to wait (default: 60)",
    )
    parser.add_argument(
        "--interval",
        "-i",
        type=float,
        default=2.0,
        help="Seconds between checks (default: 2.0)",
    )
    parser.add_argument(
        "--http-only",
        action="store_true",
        help="Use HTTP checks only (slower but more thorough)",
    )

    args = parser.parse_args()

    success = wait_for_services(
        timeout=args.timeout, interval=args.interval, use_tcp=not args.http_only
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
