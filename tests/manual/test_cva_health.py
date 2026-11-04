"""Test CVA health endpoint with proper authentication"""

import asyncio

import httpx


async def test_cva():
    try:
        async with httpx.AsyncClient(base_url="http://localhost:8100", timeout=30.0) as client:
            # Login
            print("Attempting login with 'password123'...")
            login_data = {
                "username": "admin@sanskritisetu.org",
                "password": "password123",
            }
            resp = await client.post("/api/v1/auth/login", data=login_data)

            if resp.status_code != 200:
                print(f"Login FAILED: {resp.status_code} - {resp.text}")
                return

            token = resp.json()["access_token"]
            print("Login SUCCESS. Token acquired.")

            # Test CVA Health
            print("Requesting CVA Health...")
            headers = {"Authorization": f"Bearer {token}"}
            cva_resp = await client.get("/api/v1/cva/health", headers=headers)
            print(f"CVA Health: {cva_resp.status_code}")
            print(f"Response: {cva_resp.text}")

    except Exception as e:
        print(f"EXCEPTION: {e}")


if __name__ == "__main__":
    asyncio.run(test_cva())
