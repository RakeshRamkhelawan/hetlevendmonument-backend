"""Test script for DeepSeek and Gemini API keys."""

import os
import sys

sys.path.insert(0, "c:\\Users\\rsram\\OneDrive\\Documenten\\GitHub\\SanskritiSetu.org")


# Load .env file
def load_env():
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    os.environ[key] = value


def main():
    load_env()

    print("=" * 60)
    print("LLM API KEY VALIDATION")
    print("=" * 60)

    # Initialize status variables
    deepseek_working = False
    gemini_working = False

    # Test DeepSeek
    print("\n=== Testing DeepSeek API ===")
    deepseek_key = os.environ.get("DEEPSEEK_API_KEY")
    if not deepseek_key:
        print("[FAIL] DEEPSEEK_API_KEY not found in environment")
    else:
        print(f"[OK] DEEPSEEK_API_KEY found: {deepseek_key[:10]}...")
        try:
            import requests

            response = requests.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {deepseek_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": "Say OK in 1 word"}],
                    "max_tokens": 10,
                },
                timeout=30,
            )
            if response.status_code == 200:
                data = response.json()
                content = data["choices"][0]["message"]["content"].strip()
                print(f"[OK] DeepSeek API WORKING: '{content}'")
                deepseek_working = True
            else:
                print(f"[FAIL] DeepSeek API Error {response.status_code}: {response.text[:200]}")
                deepseek_working = False
        except Exception as e:
            print(f"[FAIL] DeepSeek Error: {e}")
            deepseek_working = False

    # Test Gemini with new provider (with fallback)
    print("\n=== Testing Gemini API (with auto-fallback) ===")
    gemini_key = os.environ.get("GOOGLE_API_KEY")
    if not gemini_key:
        print("[FAIL] GOOGLE_API_KEY not found in environment")
    else:
        print(f"[OK] GOOGLE_API_KEY found: {gemini_key[:10]}...")
        try:
            import asyncio

            from src.core.als.llm_integration import GeminiProvider

            async def test_gemini():
                provider = GeminiProvider()  # Auto-selects best model
                print(f"[INFO] Selected model: {provider.model}")

                result = await provider.generate(
                    prompt="Say OK in 1 word", temperature=0.1, max_tokens=10
                )
                return result

            result = asyncio.run(test_gemini())

            if result["success"]:
                print(
                    f"[OK] Gemini API WORKING (model: {result['model']}): '{result['content'].strip()}'"
                )
                gemini_working = True
            else:
                print(f"[FAIL] Gemini Error: {result['error'][:200]}")
                gemini_working = False
        except Exception as e:
            print(f"[FAIL] Gemini Error: {e}")
            gemini_working = False

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"DeepSeek API: {'[OK] WORKING' if deepseek_working else '[FAIL] FAILED'}")
    print(f"Gemini API:   {'[OK] WORKING' if gemini_working else '[FAIL] FAILED'}")

    if deepseek_working and gemini_working:
        print("\n[OK] Both LLM APIs are working!")
        sys.exit(0)
    elif deepseek_working or gemini_working:
        print("\n[OK] At least one LLM API is working!")
        sys.exit(0)
    else:
        print("\n[FAIL] No working LLM APIs found")
        sys.exit(1)


if __name__ == "__main__":
    main()
