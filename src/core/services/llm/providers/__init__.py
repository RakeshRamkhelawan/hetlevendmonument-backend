"""
LLM Provider Implementations

Available providers:
- OllamaProvider: Local Ollama models
- DeepSeekProvider: DeepSeek API
- GeminiProvider: Google Gemini API
- MistralProvider: Mistral AI (EU), het standaardmodel voor klantgegevens
- MockProvider: Demo/fallback (no external service required)
- OpenAICompatibleProvider: ELK OpenAI-compatibel eindpunt, adres uit de configuratie
"""

from src.core.services.llm.providers.deepseek import DeepSeekProvider
from src.core.services.llm.providers.gemini import GeminiProvider
from src.core.services.llm.providers.mistral import MistralProvider
from src.core.services.llm.providers.mock import MockProvider
from src.core.services.llm.providers.ollama import OllamaProvider
from src.core.services.llm.providers.openai_compatible import OpenAICompatibleProvider

__all__ = [
    "OllamaProvider",
    "DeepSeekProvider",
    "GeminiProvider",
    "MistralProvider",
    "MockProvider",
    "OpenAICompatibleProvider",
]
