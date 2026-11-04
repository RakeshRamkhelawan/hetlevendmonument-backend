import asyncio
import os

import httpx
from dotenv import load_dotenv

load_dotenv()


async def test_deepseek():
    api_key = os.getenv("DEEPSEEK_API_KEY")
    print(f"Testing key: {api_key[:5]}...{api_key[-5:] if api_key else ''}")

    if not api_key:
        print("DEEPSEEK_API_KEY not found")
        return

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": "Hello"}],
        "max_tokens": 10,
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                "https://api.deepseek.com/chat/completions",
                json=payload,
                headers=headers,
                timeout=10.0,
            )
            print(f"Status Code: {response.status_code}")
            print(f"Response: {response.text}")
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(test_deepseek())
