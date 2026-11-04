"""
Pydantic schemas for the Co-Pilot service.

These schemas define the strict JSON contract between the LLM and the
CopilotService, as well as the request/response types for the turn endpoint.

Per ADR-027 paragraaf 9:
    - JSON mode is mandatory for all LLM calls that produce actions.
    - Pydantic validation is the final safety net; on parse failure -> 1 retry,
      then BLOCKED.

Per CLAUDE.md regel 10: ASCII-only in source code.
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# EU AI Act art. 50 / ADR-036 D9: stable, machine-readable disclosure carried on
# every copilot turn response so the user is always informed the answer is AI-made.
AI_DISCLOSURE_NOTICE = (
    "AI-GENERATED: This response was produced by an AI system (SanskritiSetu). "
    "EU AI Act Art. 50 disclosure."
)


class CopilotAction(BaseModel):
    """LLM JSON output contract (ADR-027 paragraaf 9). Strict.

    **`action` is begrensd in VORM en LENGTE (ADR-036 OP-78).** Dat veld had geen enkele
    beperking, terwijl `message` ernaast wel `max_length=4000` heeft. De waarde loopt via
    `proposal_builder` en `copilot/service.py` naar `create_hitl_request` en wordt daar
    `hitl_tickets.tool_name` -- en sinds OP-71 gaat hij mee de ADR-019 hashketen in, die per
    ontwerp onuitwisbaar is. Een prompt-injectie kon daar dus vrije tekst permanent in laten
    vastleggen, en `/hitl/audit` serveerde die terug aan elke tenantbeheerder.

    Het patroon staat alle namen toe die de broker vandaag uitvoert (`create_task`,
    `local__send_email`, `sequentialthinking__think`, ...) en maakt vrije tekst
    onrepresenteerbaar: geen spaties, geen apenstaartje, geen dubbele punt, geen hoofdletters.
    `max_length=64` blijft ruim onder de kolom van 256 tekens, zodat een te lange naam een nette
    weigering geeft in plaats van een databasefout halverwege de beurt.

    Een model dat zich vergist krijgt een tweede kans: `llm_handler` vangt een `ValidationError`
    af en probeert het opnieuw met een corrigerende systeemprompt.
    """

    model_config = ConfigDict(extra="forbid")

    message: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="Response in user's language",
    )
    action: str | None = Field(
        None,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_]*$",
        description="Tool name or None",
    )
    action_params: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )  # TODO(TYPE): replace Any with concrete type
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str = Field(..., min_length=1)


class CopilotTurnRequest(BaseModel):
    """Request body for POST /api/v1/copilot/turn."""

    model_config = ConfigDict(extra="forbid")

    message: str = Field(..., min_length=1, max_length=2000)
    context: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )  # TODO(TYPE): replace Any with concrete type
    stream: bool = False
    language: Literal["nl", "en"] = "nl"


class CopilotTurnResponse(BaseModel):
    """Response body for POST /api/v1/copilot/turn."""

    model_config = ConfigDict(extra="forbid")

    decision_id: str
    verdict: Literal[
        "approved",
        "modified",
        "hitl_required",
        "deferred",
        "blocked",
    ]
    message: str
    action: str | None = None
    action_params: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )  # TODO(TYPE): replace Any with concrete type
    confidence: float = 0.0
    council_summary: dict[str, int] = Field(default_factory=dict)
    hitl_request_id: str | None = None
    explanation_url: str | None = None
    ai_disclosure: str = Field(
        default=AI_DISCLOSURE_NOTICE,
        description="Machine-readable EU AI Act art. 50 disclosure (ADR-036 D9).",
    )


class ProactiveResponseRequest(BaseModel):
    """User-respons op een proactief signaal (knop uit notificatie)."""

    model_config = ConfigDict(extra="forbid")

    action_type: str = Field(
        ...,
        description="Acceptably-typed user response, bv. 'confirm', "
        "'cancel', 'snooze', 'dismiss', 'navigate'.",
        pattern=r"^[a-z_]{1,32}$",
    )
    params: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict,
        description="Optionele actie-parameters (bv. snooze_seconds).",
    )


class ProactiveResponseResponse(BaseModel):
    """Server-respons na verwerking van proactieve user-actie."""

    model_config = ConfigDict(extra="forbid")

    signal_id: UUID
    accepted: bool
    resulting_action: str | None = None
    message: str
