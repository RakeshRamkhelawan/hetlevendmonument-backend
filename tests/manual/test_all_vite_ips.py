#!/usr/bin/env python3
"""Test Vite on all reported IPs"""

import socket

import pytest


def _test_port(host, port):
    """Helper function to test if a port is open"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    try:
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


@pytest.mark.skip(reason="Manual test script")
def test_all_vite_ips():
    """Test Vite on all reported IPs - manual execution only"""
    print("[*] Testing Vite on all reported IPs...")
    ips = [
        ("localhost", "127.0.0.1"),
        ("192.168.178.61", "192.168.178.61"),
        ("172.29.128.1", "172.29.128.1"),
    ]

    for name, ip in ips:
        status = "OPEN" if _test_port(ip, 5173) else "CLOSED"
        print(f"  {name} ({ip}):5173 - {status}")

    print("\n[!] If any IP shows OPEN:")
    print("    - Use that IP in your browser, e.g. http://192.168.178.61:5173")
    print("    - Vite may not work properly on 127.0.0.1 on Windows")
    print("    - Use the network IP shown by Vite instead")
