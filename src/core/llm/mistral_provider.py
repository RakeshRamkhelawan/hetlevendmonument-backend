"""Mistral AI (Frankrijk, EU) als taalmodel -- de standaard voor klantgegevens (ADR-041 B14).

Mistral spreekt de OpenAI-chatvorm (`/v1/chat/completions`, `tools`, `response_format`), dus deze klasse
is een dunne laag daaroverheen, in dezelfde vorm als `DeepSeekProvider`.

**De sleutel.** `MISTRAL_API_KEY` komt UITSLUITEND uit de omgeving of uit een expliciete parameter.
Hij staat niet in `repr`, niet in een foutmelding en niet in een logregel: een afwijzing van Mistral
wordt gelogd met de statuscode en NIET met de tekst van het antwoord (die kan de sleutel of een stuk
van het verzoek terugspelen). Bewaakt door `tests/unit/llm/test_mistral_provider.py`.

**Het model.** `LLM_MODEL` telt alleen als `LLM_PROVIDER=mistral`; de uitrol zet vandaag nog
`LLM_MODEL=deepseek-chat`, en dat mag nooit bij Mistral aankomen. Een andere waarde valt terug op
`mistral-small-latest`.

**PII.** Net als de andere providers maskeert `generate_response` persoonsgegevens in de
gebruikersberichten voordat ze de deur uit gaan (`LLMClient._sanitize_messages`).
"""

from __future__ import annotations

import json
import logging
import os
import time

import httpx

from .llm_client import LLMClient, LLMConfig, LLMMessage, LLMModel, LLMProvider, LLMResponse

logger = logging.getLogger(__name__)

#: Het Franse, in de EU gehoste eindpunt. Instelbaar voor een test of een regionaal eindpunt.
STANDAARD_BASIS_URL = "https://api.mistral.ai/v1"
STANDAARD_MODEL = "mistral-small-latest"
_SLEUTEL_ONTBREEKT = "MISTRAL_API_KEY is niet gezet"

#: Een JSON-object zoals het over de lijn gaat; de waarden worden bij gebruik versmald.
_Json = dict[str, object]


def _als_dict(waarde: object) -> _Json:
    """`waarde` als woordenboek; alles wat geen woordenboek is wordt een leeg woordenboek."""
    return waarde if isinstance(waarde, dict) else {}


def _als_lijst(waarde: object) -> list[object]:
    return waarde if isinstance(waarde, list) else []


def gekozen_model() -> str:
    """Het model uit `LLM_MODEL`, maar alleen als de provider Mistral is; anders het standaardmodel."""
    if os.getenv("LLM_PROVIDER", "").strip().lower() == "mistral":
        naam = os.getenv("LLM_MODEL", "").strip()
        if naam and "deepseek" not in naam.lower():
            return naam
    return STANDAARD_MODEL


class MistralProvider(LLMClient):
    """Mistral chat completions, met JSON-uitvoer en toolaanroepen."""

    def __init__(
        self,
        config: LLMConfig | str | None = None,
        api_key: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        sleutel: str | None
        if isinstance(config, str):
            sleutel, config = config, None
        else:
            sleutel = api_key or (config.api_key if config is not None else None)
        # `or None`: een lege tekst is geen sleutel.
        self._api_key: str | None = sleutel or os.environ.get("MISTRAL_API_KEY") or None

        if config is None:
            config = LLMConfig(
                provider=LLMProvider.MISTRAL,
                model=LLMModel.MISTRAL_SMALL,
                api_key="",
                temperature=0.7,
                max_tokens=2000,
            )
        # De sleutel hoort NIET in de config die elders kan worden weergegeven.
        config.api_key = ""
        super().__init__(config)

        self.base_url = os.getenv("MISTRAL_BASE_URL", STANDAARD_BASIS_URL).rstrip("/")
        if not self.base_url.lower().startswith("https://"):
            # De sleutel gaat als bearer mee; naar een onbeveiligd adres zou hij leesbaar over het net gaan.
            raise ValueError("MISTRAL_BASE_URL moet een https-adres zijn")
        self.model_name = gekozen_model()
        self._transport = transport
        self._available = bool(self._api_key)
        self._initialized = False

        if not self._available:
            logger.warning("%s: de Mistral-provider is niet beschikbaar", _SLEUTEL_ONTBREEKT)
        else:
            logger.info("Mistral-provider gereed, model %s", self.model_name)

    def __repr__(self) -> str:
        return f"MistralProvider(model={self.model_name!r}, beschikbaar={self._available})"

    # -- levenscyclus ------------------------------------------------------------------------

    async def initialize(self) -> bool:
        self._initialized = self._available
        return self._available

    @property
    def initialized(self) -> bool:
        return self._initialized

    @property
    def model_names(self) -> list[str]:
        return [STANDAARD_MODEL, "mistral-large-latest"]

    # -- de aanroep --------------------------------------------------------------------------

    def _fout(self, melding: str) -> LLMResponse:
        return LLMResponse(
            content="",
            model=self.model_name,
            provider=LLMProvider.MISTRAL.value,
            success=False,
            error_message=melding,
        )

    async def _post(self, payload: _Json) -> _Json:
        """Een verzoek. Geeft het JSON-antwoord terug of laat een HTTP-fout door (zonder antwoordtekst)."""
        async with httpx.AsyncClient(timeout=60.0, transport=self._transport) as client:
            antwoord = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        antwoord.raise_for_status()
        return _als_dict(antwoord.json())

    def _payload(self, berichten: list[_Json], kwargs: _Json, *, stream: bool = False) -> _Json:
        payload: _Json = {
            "model": kwargs.get("model") or self.model_name,
            "messages": berichten,
            "temperature": kwargs.get("temperature", self.config.temperature),
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "stream": stream,
        }
        if kwargs.get("response_format"):
            payload["response_format"] = kwargs["response_format"]
        tools = kwargs.get("tools")
        if tools:
            payload["tools"] = _tools_in_openai_vorm(_als_lijst(tools))
            payload["tool_choice"] = kwargs.get("tool_choice", "auto")
        return payload

    async def _vraag(
        self, berichten: list[_Json], kwargs: _Json
    ) -> tuple[LLMResponse, list[_Json]]:
        """Stuur het verzoek en lees het antwoord; geeft ook de toolaanroepen terug."""
        if not self._available:
            return self._fout(f"{_SLEUTEL_ONTBREEKT}; de aanroep is niet verstuurd"), []
        start = time.time()
        try:
            data = await self._post(self._payload(berichten, kwargs))
        except httpx.HTTPStatusError as exc:
            # Alleen de statuscode: de tekst van het antwoord blijft buiten log en foutmelding.
            logger.error("Mistral wees het verzoek af: HTTP %s", exc.response.status_code)
            return self._fout(f"Mistral gaf HTTP {exc.response.status_code}"), []
        except httpx.HTTPError as exc:
            logger.error("Mistral onbereikbaar: %s", type(exc).__name__)
            return self._fout(f"Mistral onbereikbaar ({type(exc).__name__})"), []

        keuzes = _als_lijst(data.get("choices"))
        keuze = _als_dict(keuzes[0]) if keuzes else {}
        bericht = _als_dict(keuze.get("message"))
        oproepen = _lees_toolaanroepen(_als_lijst(bericht.get("tool_calls")))
        inhoud = bericht.get("content")
        antwoord = LLMResponse(
            content=inhoud if isinstance(inhoud, str) else "",
            model=str(data.get("model", self.model_name)),
            provider=LLMProvider.MISTRAL.value,
            usage=_als_dict(data.get("usage")) or None,
            response_time=time.time() - start,
            metadata={"provider": "mistral", "finish_reason": keuze.get("finish_reason")},
        )
        return antwoord, oproepen

    async def chat_completion(self, messages: list[LLMMessage], **kwargs: object) -> LLMResponse:
        berichten: list[_Json] = [{"role": m.role, "content": m.content} for m in messages]
        antwoord, _toolaanroepen = await self._vraag(berichten, dict(kwargs))
        return antwoord

    async def text_completion(self, prompt: str, **kwargs: object) -> LLMResponse:
        return await self.chat_completion([LLMMessage(role="user", content=prompt)], **kwargs)

    async def complete_json(
        self, messages: list[LLMMessage], schema: type, **kwargs: object
    ) -> LLMResponse:
        """JSON-uitvoer via de eigen `response_format` van Mistral."""
        kwargs.setdefault("response_format", {"type": "json_object"})
        return await self.chat_completion(messages, **kwargs)

    async def generate_response(
        self, prompt: str, model: str | None = None, **kwargs: object
    ) -> dict[str, object]:
        """Het antwoord als woordenboek, met `function_calls` als het model een tool wil aanroepen.

        Dezelfde vorm als `OllamaProvider.generate_response`, want `LLMService.generate_with_tools`
        en de agenten lezen `function_calls` en `requires_function_execution`.
        """
        ruw = kwargs.pop("messages", None)
        berichten: list[_Json]
        if ruw:
            berichten, tokens = _maskeer_gebruikersberichten(self, _als_lijst(ruw))
        else:
            masked, tokens = self._gdpr_enforcer.redact_pii(prompt)
            berichten = [{"role": "user", "content": masked}]
        if model:
            kwargs["model"] = model
        try:
            antwoord, oproepen = await self._vraag(berichten, dict(kwargs))
        except Exception as exc:  # een aanroeper wil een woordenboek, geen uitzondering
            logger.error("Mistral generate_response mislukt: %s", type(exc).__name__)
            return {"success": False, "error": type(exc).__name__}
        if not antwoord.success:
            return {"success": False, "error": antwoord.error_message}
        inhoud = antwoord.content
        if tokens:
            inhoud = self._gdpr_enforcer.detokenize(inhoud, tokens)
            # Ook de argumenten van een toolaanroep: het model werkt met de tokens, de tool moet
            # de echte waarde krijgen (anders zoekt hij naar "[TOKEN_PII_0]").
            oproepen = [
                {**oproep, "args": _herstel_tokens(oproep.get("args"), self, tokens)}
                for oproep in oproepen
            ]
        return {
            "success": True,
            "content": inhoud,
            "model": antwoord.model,
            "provider": LLMProvider.MISTRAL.value,
            "usage": antwoord.usage,
            "metadata": antwoord.metadata,
            "function_calls": oproepen or None,
            "requires_function_execution": bool(oproepen),
        }


def _herstel_tokens(waarde: object, provider: LLMClient, tokens: dict[str, str]) -> object:
    """Zet gemaskeerde tokens in toolargumenten (ook genest) terug naar de oorspronkelijke waarde."""
    if isinstance(waarde, str):
        return provider._gdpr_enforcer.detokenize(waarde, tokens)
    if isinstance(waarde, dict):
        return {k: _herstel_tokens(v, provider, tokens) for k, v in waarde.items()}
    if isinstance(waarde, list):
        return [_herstel_tokens(v, provider, tokens) for v in waarde]
    return waarde


def _tools_in_openai_vorm(tools: list[object]) -> list[_Json]:
    """Een kale functiebeschrijving wordt `{"type": "function", "function": {...}}`; die vorm blijft staan."""
    uit: list[_Json] = []
    for tool in tools:
        beschrijving = _als_dict(tool)
        if beschrijving.get("type") == "function":
            uit.append(beschrijving)
        else:
            uit.append({"type": "function", "function": beschrijving})
    return uit


def _lees_toolaanroepen(ruw: list[object]) -> list[_Json]:
    """`tool_calls` van Mistral naar `[{"name", "args"}]`; de argumenten komen als JSON-tekst."""
    oproepen: list[_Json] = []
    for item in ruw:
        functie = _als_dict(_als_dict(item).get("function"))
        argumenten: object = functie.get("arguments", {})
        if isinstance(argumenten, str):
            try:
                argumenten = json.loads(argumenten) if argumenten.strip() else {}
            except json.JSONDecodeError:
                # Niet stil een lege set maken: de aanroeper moet kunnen zien dat het misging.
                logger.warning(
                    "Mistral gaf toolargumenten die geen JSON zijn (%s)", functie.get("name")
                )
                argumenten = {"_ongeldige_json": argumenten}
        oproepen.append({"name": functie.get("name"), "args": argumenten})
    return oproepen


def _maskeer_gebruikersberichten(
    provider: LLMClient, ruw: list[object]
) -> tuple[list[_Json], dict[str, str]]:
    """Dezelfde PII-maskering als `LLMClient._sanitize_messages`, maar met behoud van toolvelden."""
    kaal: list[LLMMessage] = []
    for bericht in ruw:
        if isinstance(bericht, dict):
            inhoud = bericht.get("content")
            kaal.append(
                LLMMessage(
                    role=str(bericht.get("role", "user")),
                    content=inhoud if isinstance(inhoud, str) else "",
                )
            )
        elif isinstance(bericht, LLMMessage):
            kaal.append(bericht)
    schoon, tokens = provider._sanitize_messages(kaal)
    uit: list[_Json] = []
    for oorspronkelijk, gemaskeerd in zip(ruw, schoon):
        bericht_uit: _Json = (
            dict(oorspronkelijk) if isinstance(oorspronkelijk, dict) else {"role": gemaskeerd.role}
        )
        bericht_uit["content"] = gemaskeerd.content
        uit.append(bericht_uit)
    return uit, tokens
