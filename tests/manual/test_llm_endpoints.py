import asyncio

import httpx


async def test_llm_endpoints():
    url = "http://localhost:8100/api/v1/llm"
    async with httpx.AsyncClient() as client:
        print("Testing /models...")
        try:
            resp = await client.get(f"{url}/models")
            print(f"Status: {resp.status_code}")
            if resp.status_code == 200:
                models = resp.json()
                print(f"Found {len(models)} models")
                for m in models[:3]:
                    print(f" - {m['id']} ({m['provider']})")
        except Exception as e:
            print(f"Error testing /models: {e}")

        print("\nTesting /status...")
        try:
            resp = await client.get(f"{url}/status")
            print(f"Status: {resp.status_code}")
            if resp.status_code == 200:
                status = resp.json()
                print(f"Overall Success: {status['successful']}")
                print(f"Overall Failed: {status['failed']}")
                for provider, res in status["test_results"].items():
                    print(f" - {provider}: {res['status']}")
        except Exception as e:
            print(f"Error testing /status: {e}")


if __name__ == "__main__":
    asyncio.run(test_llm_endpoints())
