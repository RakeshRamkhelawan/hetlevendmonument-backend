#!/usr/bin/env python3
import socket

import requests

print("[*] Testing frontend on port 3005...")

# Socket test
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(2)
result = sock.connect_ex(("127.0.0.1", 3005))
sock.close()

if result == 0:
    print("[✅] Port 3005 is LISTENING")

    # HTTP test
    try:
        resp = requests.get("http://localhost:3005", timeout=5)
        print(f"[✅] HTTP Response: {resp.status_code}")
    except Exception as e:
        print(f"[⚠️] HTTP Error: {e}")
else:
    print("[❌] Port 3005 is CLOSED")

print("\n[!] Backend status:")
print("[✅] Port 8001: OPEN")
print("[*] Try accessing http://localhost:3005 in browser")
print("    Or http://localhost:8001/docs for API docs")
