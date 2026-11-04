#!/usr/bin/env python3
import socket
import time


def test_port(host, port):
    """Test if a port is open without making HTTP request"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)
    try:
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except:
        return False


print("[*] Testing service connectivity...")
print(f"[1] Backend on port 8001: {'✅ OPEN' if test_port('localhost', 8001) else '❌ CLOSED'}")
print(f"[2] Frontend on port 5173: {'✅ OPEN' if test_port('localhost', 5173) else '❌ CLOSED'}")
print("")
print("If frontend shows ✅ OPEN:")
print("  1. Go to http://localhost:5173 in your browser")
print("  2. Clear browser cache (Ctrl+Shift+Delete)")
print("  3. Hard refresh (Ctrl+F5)")
print("  4. Try login: admin@sanskritisetu.org / Admin123!")
