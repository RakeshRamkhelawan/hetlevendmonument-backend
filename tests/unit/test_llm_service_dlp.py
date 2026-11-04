"""TDD tests for LLMService.complete_json() DLP intercept -- SP-DLP-001 review fix C-2."""

import pytest

from src.core.governance.gdpr_enforcer import GDPREnforcer
from src.core.llm.llm_client import LLMMessage, LLMProvider, LLMResponse
from src.core.llm.llm_service import LLMService


def _make_service(provider_mock: object) -> LLMService:
    """Build a minimal LLMService without singleton side-effects."""
    svc: LLMService = object.__new__(LLMService)
    svc.providers = {LLMProvider.MOCK: provider_mock}  # type: ignore[attr-defined]
    svc.default_provider = LLMProvider.MOCK
    svc.default_model = "mock-model"
    svc._tokens_used = 0  # type: ignore[attr-defined]
    svc.token_budget = None  # type: ignore[attr-defined]
    svc._gdpr_enforcer = GDPREnforcer()  # type: ignore[attr-defined]
    return svc


class _RecordingProvider:
    """Captures messages passed to complete_json for assertion."""

    received: list[LLMMessage]

    def __init__(self) -> None:
        self.received = []

    async def complete_json(
        self,
        messages: list[LLMMessage],
        schema: object,
        model: str | None = None,
        **kwargs: object,
    ) -> LLMResponse:
        self.received = list(messages)
        return LLMResponse(content='{"ok": true}', model="mock", provider="mock", success=True)


@pytest.mark.asyncio
async def test_llm_service_complete_json_sanitizes_pii_before_provider():
    provider = _RecordingProvider()
    svc = _make_service(provider)

    await svc.complete_json(
        messages=[LLMMessage(role="user", content="jan@example.com")],
        schema=dict,
    )

    assert provider.received, "complete_json nooit doorgegeven aan provider"
    assert "jan@example.com" not in provider.received[0].content, (
        "PII lekte verbatim naar provider via complete_json"
    )


@pytest.mark.asyncio
async def test_llm_service_complete_json_preserves_system_role():
    provider = _RecordingProvider()
    svc = _make_service(provider)

    await svc.complete_json(
        messages=[LLMMessage(role="system", content="jan@example.com is de admin")],
        schema=dict,
    )

    assert provider.received[0].content == "jan@example.com is de admin"


class _EchoingProvider:
    """Echos first user-message placeholder terug in JSON response."""

    received: list[LLMMessage]

    def __init__(self) -> None:
        self.received = []

    async def complete_json(
        self,
        messages: list[LLMMessage],
        schema: object,
        model: str | None = None,
        **kwargs: object,
    ) -> LLMResponse:
        self.received = list(messages)
        first_user = next((m.content for m in messages if m.role == "user"), "")
        return LLMResponse(
            content=f'{{"result": "{first_user}"}}',
            model="mock",
            provider="mock",
            success=True,
        )


@pytest.mark.asyncio
async def test_llm_service_complete_json_detokenizes_response():
    """R1: placeholder in JSON-response mag niet naar caller lekken."""
    provider = _EchoingProvider()
    svc = _make_service(provider)

    response = await svc.complete_json(
        messages=[LLMMessage(role="user", content="jan@example.com")],
        schema=dict,
    )

    assert "[TOKEN_PII_" not in response.content, (
        f"placeholder lekt in complete_json response: {response.content!r}"
    )
    assert "jan@example.com" in response.content, "originele waarde niet hersteld in response"


@pytest.mark.asyncio
async def test_llm_service_sanitize_messages_no_token_collision_multi_user():
    """R2: twee user-berichten met PII mogen niet hetzelfde placeholder krijgen."""
    svc: "LLMService" = object.__new__(LLMService)
    svc.providers = {}  # type: ignore[attr-defined]
    svc._gdpr_enforcer = GDPREnforcer()  # type: ignore[attr-defined]

    msgs = [
        LLMMessage(role="user", content="jan@example.com"),
        LLMMessage(role="user", content="piet@example.com"),
    ]
    sanitized, token_map = svc._sanitize_messages(msgs)

    assert len(token_map) == 2, f"verwacht 2 tokens, maar: {token_map}"
    placeholders = {m.content for m in sanitized}
    assert len(placeholders) == 2, f"beide berichten kregen hetzelfde placeholder: {placeholders}"


class _RecordingGenerateProvider:
    """Registreert de prompt die generate_response ontvangt."""

    received_prompt: str

    def __init__(self) -> None:
        self.received_prompt = ""

    async def generate_response(self, prompt: str, **kwargs: object) -> dict[str, object]:
        self.received_prompt = prompt
        return {"content": prompt, "success": True, "model": "mock", "provider": "mock"}


@pytest.mark.asyncio
async def test_llm_service_generate_response_sanitizes_prompt():
    """CRITICAL: generate_response() mag geen raw PII doorsturen naar provider."""
    provider = _RecordingGenerateProvider()
    svc = _make_service(provider)

    await svc.generate_response("jan@example.com")

    assert "jan@example.com" not in provider.received_prompt, (
        f"PII verbatim naar provider: {provider.received_prompt!r}"
    )
