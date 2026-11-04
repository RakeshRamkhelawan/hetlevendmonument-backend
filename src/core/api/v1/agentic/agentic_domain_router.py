"""Agentic domain operations sub-router (ADR-033 Laag 1)."""

# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)

import asyncio
import json
import logging
import re
import time
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.user_helpers import get_user_id
from src.core.api.v1.agentic.dependencies import (
    DomainPack,
    DomainPackOrchestrator,
    Voortgang,
    FeedbackProcessingService,
    FinanceSupervisor,
    TenantPackActivationsRepository,
    agent_execute_limit,
    audit_service,
    get_db,
    get_feedback_service,
    get_pack_activations_repository,
    require_resource_permission,
    validate_csrf_token,
)
from src.core.auth.api_deps import get_current_user
from src.core.exceptions import AuthError
from src.core.middleware.tenant_context import require_tenant_id
from src.core.shared.interfaces import ExecutionResult, TaskData
from src.core.utils.best_effort import best_effort

logger = logging.getLogger(__name__)

#: Bovengrens voor de serialisatie van `input_data` (tekens). Gekozen als ruim genoeg voor een
#: factuurregel of een lijst medewerkers en ver onder wat een prompt opblaast; niet gemeten tegen
#: een echt model.
MAX_INVOER_TEKENS = 50_000

agentic_domain_router = APIRouter()


class FinanceDecomposeRequest(BaseModel):
    task: str
    context: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type


class PackExecuteRequest(BaseModel):
    """Een domeinpakket uitvoeren. De klant komt uit de JWT, nooit uit deze body."""

    pack_id: str = Field(min_length=1, max_length=100, description="Id uit de pakketcatalogus")
    input_data: dict[str, object] = Field(
        default_factory=dict,
        description="Invoer van de gebruiker; komt als params['input'] bij elke stap",
    )
    sla_seconds: int | None = Field(
        default=None,
        ge=30,
        le=3600,
        description="Totaaltijd voor de hele run; zonder waarde gelden alleen de SLA's per stap",
    )


    @field_validator("input_data")
    @classmethod
    def _invoer_niet_te_groot(cls, waarde: dict[str, object]) -> dict[str, object]:
        """De invoer gaat als tekst de LLM-prompt van elke stap in: begrens hem per verzoek."""
        if len(json.dumps(waarde, default=str)) > MAX_INVOER_TEKENS:
            raise ValueError(f"input_data is groter dan {MAX_INVOER_TEKENS} tekens")
        return waarde


class PackStepResult(BaseModel):
    agent_id: str | None
    status: Literal["succeeded", "failed", "skipped", "interrupted"]
    task_id: str
    error: str | None
    #: Alleen voor de receiptscanner: aantal, totaal en btw per tarief van de BEVESTIGDE bonnen.
    samenvatting: dict[str, object] | None = None


class PackExecuteResponse(BaseModel):
    pack_id: str
    status: Literal["succeeded", "partial", "failed"]
    steps: list[PackStepResult]
    duration_ms: int
    sla_breached: bool
    escalated_to_human: bool


class FeedbackSubmitRequest(BaseModel):
    conversation_id: str
    feedback_type: str = Field(..., pattern="^(positive|negative|correction)$")
    comment: str | None = None
    corrected_supervisor: str | None = None
    confidence: float = Field(..., ge=0.0, le=1.0)
    rating: int | None = Field(None, ge=1, le=5)


@agentic_domain_router.post("/finance/decompose")
async def finance_decompose(
    request: FinanceDecomposeRequest,
    _current_user: object = Depends(get_current_user),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Decompose a finance task into subtasks."""
    try:
        tenant_id_int = require_tenant_id()
        supervisor = FinanceSupervisor(agent_id="finance_supervisor", tenant_id=tenant_id_int)
        task_data = TaskData(
            title=request.task, description=request.task, metadata=request.context or {}
        )
        subtasks = await supervisor.decompose_task(task_data)
        return {"task": request.task, "subtasks": subtasks, "count": len(subtasks)}
    except AuthError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Internal error")


@agentic_domain_router.post(
    "/packs/execute",
    response_model=PackExecuteResponse,
    dependencies=[
        Depends(require_resource_permission("packs", "execute")),
        Depends(validate_csrf_token),
    ],
)
@agent_execute_limit
async def execute_pack(
    request: PackExecuteRequest,
    http_request: Request,
    current_user: object = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    activaties: TenantPackActivationsRepository = Depends(get_pack_activations_repository),
) -> PackExecuteResponse:
    """Voer een domeinpakket uit de catalogus uit (ADR-036 OP-09).

    Wie mag het: wie `packs:execute` heeft (standaard `user`, `editor` en `admin`); de rolcontrole
    en de CSRF-controle staan vooraan, dus een geweigerde aanvraag start geen enkele stap.
    Het pack komt uit de catalogus (`config/domain_packs.yaml`); een onbekend `pack_id` geeft 404
    `PACK_NOT_FOUND`. De invoer van de gebruiker komt als `params["input"]` bij elke stap aan.

    Een mislukte of deels gelukte run blijft HTTP 200: de uitleg staat per stap in `steps`.

    Rate-limited op 10/min per tenant+gebruiker (BE-AGT-043). Een verzoek veroorzaakt tot
    `max_steps` Council-beraadslagingen, elk met een `pg_advisory_xact_lock` per tenant op de
    ADR-019 hash-keten; zonder limiet kan een geauthenticeerde gebruiker de audit-keten van zijn
    eigen tenant laten dichtslibben. `http_request` staat er alleen voor de decorator, die de
    Request via isinstance zoekt.
    """
    try:
        tenant_id = require_tenant_id()
        # ADR-036 D2 (BE-AGT-042): de geauthenticeerde gebruiker is de verantwoordelijke mens
        # voor wat deze uitvoering doet; de Council legt zijn besluit op een user_id vast.
        # BE-AGT-043: een verzoek zonder herleidbare gebruiker stopt hier, niet diep in de keten
        # met een 200 en een pack waarvan elke stap faalde.
        initiated_by_user_id = get_user_id(current_user)
        if initiated_by_user_id is None:
            raise AuthError("Geen herleidbare gebruiker aan dit verzoek gekoppeld")

        orchestrator = DomainPackOrchestrator()
        pack = orchestrator.get_pack(request.pack_id)
        if pack is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "PACK_NOT_FOUND",
                    "message": f"Pack '{request.pack_id}' staat niet in de catalogus",
                },
            )
        # Pakket aanzetten (dag 1): een pakket draait pas voor een klant nadat een beheerder het
        # heeft aangezet; geen rij betekent uit. Na de 404, zodat een onbekend pakket onbekend blijft.
        if not await activaties.is_enabled(tenant_id, request.pack_id):
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "PACK_NOT_ENABLED",
                    "message": (
                        "Dit pakket staat niet aan voor uw bedrijf. "
                        "Vraag uw beheerder om het aan te zetten."
                    ),
                },
            )

        # De rolcontrole heeft via `get_db` al een transactie op deze sessie geopend. Sluit hem
        # VOOR de run: die bestaat uit meerdere LLM-aanroepen en een open transactie zou de hele
        # tijd een poolverbinding vasthouden (backend-regel: geen transactie open tijdens
        # externe aanroepen). De auditregel hieronder begint een nieuwe.
        await db.commit()

        sla_breached = False
        voortgang = Voortgang()
        begonnen = time.perf_counter()
        try:
            results = await asyncio.wait_for(
                orchestrator.run_pack_by_id(
                    request.pack_id,
                    tenant_id,
                    initiated_by_user_id=initiated_by_user_id,
                    input_data=request.input_data,
                    voortgang=voortgang,
                ),
                timeout=request.sla_seconds,
            )
        except TimeoutError:
            sla_breached = True
            results = _na_time_out(orchestrator, pack, voortgang, tenant_id)
        response = _naar_antwoord(
            request.pack_id,
            results,
            sla_breached=sla_breached,
            duur_ms=int((time.perf_counter() - begonnen) * 1000),
        )

        # De invoer van de gebruiker (`input_data`) staat bewust NIET in de auditregel.
        async with best_effort("pack.executed audit log", db_session=db):
            await audit_service.log_action(
                tenant_id=tenant_id,
                action="pack.executed",
                resource=f"pack:{request.pack_id}",
                user_id=initiated_by_user_id,
                details={
                    "status": response.status,
                    "steps": len(response.steps),
                    "sla_breached": response.sla_breached,
                },
                session=db,
            )
        return response
    except AuthError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "pack execute failed: pack=%s: %s: %s",
            request.pack_id,
            type(e).__name__,
            e,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Internal error") from e


def _na_time_out(
    orchestrator: DomainPackOrchestrator,
    pack: DomainPack,
    voortgang: Voortgang,
    tenant_id: int,
) -> list[ExecutionResult]:
    """Per stap wat er gebeurd is toen de SLA van de hele run afliep (besluit regie 2026-10-10).

    Klaar: het echte resultaat. Begonnen maar niet klaar: `interrupted`, want die stap kan al
    effect hebben gehad en de klant mag hem niet als niet-gedaan lezen. Nooit begonnen:
    `skipped`. `voortgang` wordt per stap bijgehouden (ook binnen een parallel blok), dus een
    gelukte stap naast een afgebroken buurman blijft gelukt.
    """
    resultaten: list[ExecutionResult] = []
    for index, stap in enumerate(pack.steps):
        if index in voortgang.klaar:
            resultaten.append(voortgang.klaar[index])
        elif index in voortgang.gestart:
            resultaten.append(
                orchestrator.interrupted_result(
                    stap,
                    tenant_id,
                    "Onderbroken: de SLA van de hele run liep af tijdens deze stap; hij kan "
                    "gedeeltelijk zijn uitgevoerd, controleer het resultaat",
                )
            )
        else:
            resultaten.append(
                orchestrator.skipped_result(
                    stap, tenant_id, "Overgeslagen: de SLA van de hele run was al verlopen"
                )
            )
    return resultaten


#: De tekst voor een mislukte stap. `error_message` van zo'n stap is vaak `str(exception)`: Engels, technisch
#: en met interne paden; die hoort niet in het antwoord aan een gebruiker. De uitzondering zelf staat al
#: met `exc_info` in het log van `_execute_step`. Overgeslagen en onderbroken stappen hebben een vaste
#: Nederlandse tekst en blijven zoals ze zijn.
STAPFOUT_TEKST = "De stap kon niet worden uitgevoerd."


def _stapfout(r: ExecutionResult) -> str | None:
    return STAPFOUT_TEKST if _stapstatus(r) == "failed" else r.error_message


def _aantal(waarde: object) -> bool:
    return isinstance(waarde, int) and not isinstance(waarde, bool)


def _samenvatting_bonnen(data: dict[str, object]) -> dict[str, object] | None:
    """Receiptscanner: aantal, totaal en btw per tarief van de bevestigde bonnen."""
    aantal, totaal, btw = data.get("aantal"), data.get("totaal"), data.get("btw")
    if (
        not _aantal(aantal)
        or not isinstance(totaal, str)
        or not isinstance(btw, dict)
        or not all(isinstance(k, str) and isinstance(v, str) for k, v in btw.items())
    ):
        return None
    uit: dict[str, object] = {"aantal": aantal, "totaal": totaal, "btw": dict(btw)}
    if "kwartaal" in data:
        kwartaal = data["kwartaal"]
        if not isinstance(kwartaal, str) or _KWARTAAL_LABEL.fullmatch(kwartaal) is None:
            return None
        uit = {"kwartaal": kwartaal, **uit}
    return uit


_BTW_TARIEVEN = frozenset({"9", "21", "overig"})
_KWARTAAL_LABEL = re.compile(r"[0-9]{4}-Q[1-4]")


def _telling(waarde: object) -> bool:
    return _aantal(waarde) and isinstance(waarde, int) and waarde >= 0


def _samenvatting_debiteuren(data: dict[str, object]) -> dict[str, object] | None:
    """Dunning: alleen de tellingen van wat de stap deed; nooit de tekst van het model of een vordering."""
    openstaand, voorgesteld = data.get("openstaand"), data.get("voorgesteld")
    if (openstaand is not None and not _telling(openstaand)) or not _telling(voorgesteld):
        return None
    uit: dict[str, object] = {"openstaand": openstaand, "voorgesteld": voorgesteld}
    if "openstaand_afgekapt" in data:
        if data["openstaand_afgekapt"] is not True:
            return None
        uit["openstaand_afgekapt"] = True
    return uit


def _samenvatting_btw_overzicht(data: dict[str, object]) -> dict[str, object] | None:
    """Vatcompliance: kwartaal, voorbelasting per tarief en de aantallen van het btw-overzicht."""
    kwartaal, rubriek = data.get("kwartaal"), data.get("rubriek")
    aantal, controleren = data.get("aantal"), data.get("aantal_controleren")
    dubbel = data.get("aantal_dubbel")
    voorbelasting, totaal = data.get("voorbelasting"), data.get("totaal")
    if (
        not isinstance(kwartaal, str)
        or _KWARTAAL_LABEL.fullmatch(kwartaal) is None
        or not isinstance(rubriek, str)
        or not _aantal(aantal)
        or not _aantal(controleren)
        or not _aantal(dubbel)
        or not isinstance(totaal, str)
        or not isinstance(voorbelasting, dict)
        or set(voorbelasting) != _BTW_TARIEVEN
        or not all(isinstance(v, str) for v in voorbelasting.values())
    ):
        return None
    return {
        "kwartaal": kwartaal,
        "rubriek": rubriek,
        "aantal": aantal,
        "aantal_controleren": controleren,
        "aantal_dubbel": dubbel,
        "voorbelasting": dict(voorbelasting),
        "totaal": totaal,
    }


#: Alleen deze agents geven een samenvatting vrij aan het scherm (bedragen van bevestigde bonnen, geen
#: persoonsgegevens), elk met een eigen vaste vorm en alleen die sleutels. Van elke andere agent, en bij een
#: andere vorm, gaat `result_data` nooit mee.
_SAMENVATTINGEN = {
    "receiptscanner": _samenvatting_bonnen,
    "vatcompliance": _samenvatting_btw_overzicht,
    "dunning": _samenvatting_debiteuren,
}


def _stapsamenvatting(r: ExecutionResult) -> dict[str, object] | None:
    data = r.result_data
    maak = _SAMENVATTINGEN.get(r.agent_id or "")
    if maak is None or not r.success or not isinstance(data, dict):
        return None
    return maak(data)


def _stapstatus(r: ExecutionResult) -> Literal["succeeded", "failed", "skipped", "interrupted"]:
    if r.success:
        return "succeeded"
    if r.task_id == "skipped":
        return "skipped"
    return "interrupted" if r.task_id == "interrupted" else "failed"


def _naar_antwoord(
    pack_id: str, results: list[ExecutionResult], *, sla_breached: bool, duur_ms: int = 0
) -> PackExecuteResponse:
    """Zet de resultaten per stap om naar het antwoord; de som bepaalt de status van de run."""
    geslaagd = sum(1 for r in results if r.success)
    mislukt = len(results) - geslaagd
    status: Literal["succeeded", "partial", "failed"]
    if not results:
        # Een pack zonder enige stap (of een afgebroken run) heeft niets bereikt.
        status = "failed"
    elif mislukt == 0:
        # Alles gedaan en gelukt. Een SLA-overschrijding die hier nog bij komt (tijdens het
        # ROI-logboek van de laatste stap) blijft zichtbaar in `sla_breached`, maar maakt de run
        # niet mislukt: de klant zou hem anders opnieuw draaien en het werk dubbel doen.
        status = "succeeded"
    elif geslaagd and mislukt:
        status = "partial"
    else:
        status = "failed"
    stappen = [
        PackStepResult(
            agent_id=r.agent_id,
            status=_stapstatus(r),
            task_id=r.task_id,
            error=_stapfout(r),
            samenvatting=_stapsamenvatting(r),
        )
        for r in results
    ]
    return PackExecuteResponse(
        pack_id=pack_id,
        status=status,
        steps=stappen,
        duration_ms=duur_ms,
        sla_breached=sla_breached or any(r.task_id == "timeout" for r in results),
        # Niets gelukt: een mens moet kijken (zelfde regel als de oude `execute_pack`).
        escalated_to_human=status == "failed",
    )


@agentic_domain_router.post("/feedback")
async def submit_feedback(
    request: FeedbackSubmitRequest,
    service: FeedbackProcessingService | None = Depends(get_feedback_service),
    _current_user: object = Depends(get_current_user),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Submit learning feedback."""
    try:
        tenant_id_str = str(require_tenant_id())
        feedback_dict: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "conversation_id": request.conversation_id,
            "tenant_id": tenant_id_str,
            "feedback_type": request.feedback_type,
            "comment": request.comment,
            "corrected_supervisor": request.corrected_supervisor,
            "confidence": request.confidence,
            "rating": request.rating or 3,
        }
        if service is None:
            raise HTTPException(status_code=503, detail="Feedback service not available")
        result = await service.process_feedback(feedback_dict)
        return {
            "feedback_id": result.get("insight_id", "unknown"),
            "status": "processed" if result.get("processed") else "failed",
            "conversation_id": request.conversation_id,
            "insight_created": result.get("insight_created", False),
            "adaptation_created": result.get("adaptation_created", False),
            "rule_id": result.get("rule_id"),
        }
    except AuthError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Internal error")
