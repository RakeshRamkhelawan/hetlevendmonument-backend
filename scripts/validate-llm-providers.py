#!/usr/bin/env python3
"""LLM Provider Import Validation.

Checks that all LLM provider modules are importable before deployment.
No network calls, no API keys needed -- pure import validation.

Exit code: 0 if all providers are importable, 1 if any fail.
Used in ci-local.sh to catch ModuleNotFoundError early.
"""

import sys
from pathlib import Path

# Add repo root to path for imports
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))


def validate_llm_providers() -> int:
    """Validate all LLM provider imports. Returns 0 on success, 1 on failure."""
    providers = [
        ("anthropic", "import anthropic"),
        ("google-genai", "from google import genai"),
        ("openai", "from openai import AsyncOpenAI"),
        ("deepseek", "from src.core.llm.deepseek_provider import DeepSeekProvider"),
        ("gemini", "from src.core.llm.gemini_provider import GeminiProvider"),
        ("ollama", "from src.core.llm.ollama_provider import OllamaProvider"),
        ("mock", "from src.core.llm.mock_provider import MockProvider"),
        ("kimi-proxy", "from src.core.llm.kimi_proxy_provider import KimiProxyProvider"),
        ("llm-config", "from src.core.llm.llm_config import get_llm_service"),
    ]

    failures = []
    print("[LLM] Provider import validation...")
    for name, stmt in providers:
        try:
            exec(stmt, {})
            print(f"  [OK] {name}")
        except ImportError as e:
            error_msg = str(e).replace("\n", " ")
            print(f"  [FAIL] {name}: {error_msg}")
            failures.append((name, error_msg))
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            print(f"  [FAIL] {name}: {error_msg}")
            failures.append((name, error_msg))

    if failures:
        print(f"\n[ERROR] {len(failures)} LLM provider(s) failed import validation:")
        for name, error in failures:
            print(f"  - {name}: {error}")
        return 1

    print(f"\n[OK] All {len(providers)} LLM providers validated successfully")
    return 0


if __name__ == "__main__":
    sys.exit(validate_llm_providers())
