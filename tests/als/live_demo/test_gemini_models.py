"""Test script for Gemini model auto-selection."""

import asyncio
import os
import sys

sys.path.insert(0, r"c:\Users\rsram\OneDrive\Documenten\GitHub\SanskritiSetu.org")


# Load .env
def load_env():
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    os.environ[key] = value


load_env()

print("=" * 70)
print("GEMINI MODEL AUTO-SELECTION TEST")
print("=" * 70)

# List available models
from src.core.als.llm_integration import list_available_gemini_models

print("\nAvailable Gemini models (newest first):")
for i, model in enumerate(list_available_gemini_models(), 1):
    print(f"  {i}. {model}")

# Test auto-selection
print("\n" + "=" * 70)
print("Testing Gemini Provider with Auto-Selection")
print("=" * 70)


async def test_gemini():
    try:
        from src.core.als.llm_integration import GeminiProvider

        # Auto-select best model
        print("\nInitializing GeminiProvider (auto-selecting best model)...")
        provider = GeminiProvider()
        print(f"[OK] Selected model: {provider.model}")

        # Test generation
        print("\nTesting generation with selected model...")
        result = await provider.generate(
            prompt="Say 'Model working' in 2 words", temperature=0.1, max_tokens=10
        )

        if result["success"]:
            print("[OK] Generation successful!")
            print(f"  Model used: {result['model']}")
            print(f"  Response: {result['content'].strip()}")
        else:
            print(f"[FAIL] Generation failed: {result['error']}")

    except Exception as e:
        print(f"[FAIL] Error: {e}")
        import traceback

        traceback.print_exc()


# Run test
asyncio.run(test_gemini())

print("\n" + "=" * 70)
print("TEST COMPLETE")
print("=" * 70)
