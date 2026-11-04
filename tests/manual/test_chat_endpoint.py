import json
import time

import requests

BASE_URL = "http://localhost:8100/api/v1"  # Port updated from 8000 to 8100


def login():
    print("Logging in...")
    try:
        response = requests.post(
            f"{BASE_URL}/auth/login",
            data={"username": "admin@sanskritisetu.org", "password": "admin"},
        )
        if response.status_code == 200:
            token = response.json()["access_token"]
            print("Login successful.")
            return token
        else:
            print(f"Login failed: {response.status_code} {response.text}")
            return None
    except Exception as e:
        print(f"Login exception: {e}")
        return None


def chat(token):
    print("Sending chat request...")
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "message": "Hello CVA",
        "conversation_history": [],
        "user_id": "test_script",
        "context": {},
    }
    try:
        response = requests.post(f"{BASE_URL}/cva/chat", json=payload, headers=headers, timeout=60)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
    except Exception as e:
        print(f"Chat request exception: {e}")


if __name__ == "__main__":
    token = login()
    if token:
        chat(token)
