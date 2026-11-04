import asyncio
import os

from dotenv import load_dotenv

# Force reload of .env to be sure
load_dotenv(override=True)

try:
    from google import genai
    from google.genai import types

    print("✅ google.genai imported successfully")
except ImportError:
    print("❌ google.genai NOT installed")
    exit(1)


async def test_gemini():
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")

    print("\n--- DIAGNOSTICS ---")
    if api_key:
        masked = api_key[:5] + "..." + api_key[-5:] if len(api_key) > 10 else "Too Short"
        print(f"Key loaded from env: {masked}")
        print(f"Key length: {len(api_key)}")
    else:
        print("❌ No GOOGLE_API_KEY or GEMINI_API_KEY found in environment")
        return

    print("\n--- CONNECTIVITY TEST ---")
    try:
        client = genai.Client(api_key=api_key)

        # Simple generation
        print("Attempting to generate content with gemini-2.0-flash...")
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents="Respond with 'OK'",
            config=types.GenerateContentConfig(max_output_tokens=10),
        )
        print(f"Response: {response.text}")
        print("✅ SUCCESS: Key is valid and working.")

    except Exception as e:
        print(f"❌ FAILED: {str(e)}")
        # Check permissions/quota specific errors
        if "403" in str(e):
            print(">> Hint: Key might lack permissions or be restricted.")
        if "400" in str(e):
            print(">> Hint: Key might be invalid or project constraints apply.")


if __name__ == "__main__":
    asyncio.run(test_gemini())
