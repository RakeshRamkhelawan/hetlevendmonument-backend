"""Admin domain dependencies (ADR-033 Laag 1)."""

import os
import logging
from collections.abc import Sequence
from typing import Any, Protocol

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.auth.uitnodiging import stuur_uitnodiging
from src.core.auth.api_deps import (
    Permission,
    UserResponse,
    get_current_user_dependency as get_current_user,
    is_admin,
    is_platform_superuser,
    require_permission,
    require_resource_permission,
)
from src.core.database.database import get_db
from src.core.database.models.experiment import Experiment, ExperimentVariant
from src.core.governance.models import AuditLog
from src.core.middleware.tenant_context import require_tenant_id
from src.core.governance.services.audit_service import log_security_event
from src.core.services.experiment_service import ExperimentService
from src.core.services.rbac_service import RBACService
from src.core.repositories.payable_repository import (
    NewPayable,
    NewSupplier,
    PayableRepository,
    SupplierRepository,
)
from src.core.repositories.receivable_repository import (
    NewReceivable,
    ReceivableChanges,
    ReceivableRepository,
)

__all__ = [
    "_current_user_value",
    "_resolve_tenant_id",
    "AuditLog",
    "Experiment",
    "ExperimentService",
    "ExperimentVariant",
    "get_db",
    "log_security_event",
    "stuur_uitnodiging",
    "RBACService",
    "require_admin_role",
    "dubbele_volgorde_fout",
    "LLMProviderBeheer",
    "is_dubbele_volgorde",
    "LLM_PROVIDER_VOLGORDE_CONSTRAINT",
    "schrijf_llm_provider_audit",
    "ApVerbindingBeheerProtocol",
    "bouw_ap_verbinding_beheer",
    "ap_hoofdsleutel_fout",
    "require_platform_superuser",
    "schrijf_ap_verbinding_audit",
    # Her-export, zodat een sub-router het antwoordmodel kan annoteren zonder zelf
    # `src.core.auth` te kennen. Dat scheelt een (bestand -> auth)-paar in de
    # fan-out-meting van `core_api`, en die stond al exact op zijn plafond (557).
    "UserResponse",
    # Her-export voor `api/v1/receivables` (debiteurenagent dag 2, 2026-10-05), om dezelfde
    # reden: dit bestand kent `auth` en de repository-laag al, dus het receivables-domein voegt
    # via deze facade geen nieuw (bestand -> module)-paar toe aan het fan-out-plafond van
    # `core_api` (557, gemeten: rechtstreeks importeren gaf 559).
    "get_current_user",
    "is_admin",
    # Her-export voor `api/v1/noodstop` (noodstop per klant, 2026-10-21), om dezelfde reden als hierboven:
    # dit bestand kent `auth` en `middleware.tenant_context` al, dus het noodstop-domein voegt via deze
    # facade geen twee nieuwe (bestand -> module)-paren toe aan het fan-out-plafond van `core_api`.
    "is_platform_superuser",
    "require_tenant_id",
    "Permission",
    "require_permission",
    "require_resource_permission",
    "NewReceivable",
    "ReceivableChanges",
    "ReceivableRepository",
    # Her-export voor `api/v1/payables` (crediteuren dag 1, 2026-10-24), om dezelfde reden als `receivables`: geen nieuw
    # (bestand -> module)-paar in het fan-out-budget van `core_api`.
    "NewPayable",
    "NewSupplier",
    "PayableRepository",
    "SupplierRepository",
]

logger = logging.getLogger(__name__)


async def require_admin_role(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Check if user has admin role -- delegeert naar `is_admin` (ADR-036 OP-40).

    Tot 2026-09-01 stond hier een eigen `role in ["admin", "system_admin"]`, exacte case en
    zonder superuser-bypass. Dat was een van de zeven eigen definities.
    """
    user_roles = current_user.roles or []

    logger.info("require_admin_role: user=%s, roles=%s", current_user.email, user_roles)

    if not is_admin(current_user):
        logger.warning(
            "Permission denied: user %s has roles %s (geen beheerdersrol)",
            current_user.email,
            user_roles,
        )
        raise HTTPException(status_code=403, detail="Admin access required")

    return current_user


def _current_user_value(user: UserResponse, field: str, default: Any | None = None) -> Any:  # TODO(TYPE): replace Any with concrete type
    """Safely extract attribute from UserResponse or dict payload."""
    if isinstance(user, dict):
        return user.get(field, default)
    return getattr(user, field, default)


def _resolve_tenant_id(current_user: UserResponse) -> int:
    """Resolve tenant id from JWT middleware context (ADR-003)."""
    if os.getenv("TESTING") == "1":
        tenant_id = _current_user_value(current_user, "tenant_id")
        if tenant_id is not None:
            return int(tenant_id)
    return require_tenant_id()


class ProviderRegel(Protocol):
    """Wat de router van EEN providerrij nodig heeft -- de velden, niet de klasse.

    Dit is de kern van ADR-033 Contract 1: de router mag `ProviderOverzicht` uit de servicelaag
    niet importeren, maar hij mag wel opschrijven welke velden hij uitleest. De frozen dataclass
    daar voldoet hier structureel aan zonder dit Protocol te kennen; komt er een veld bij dat de
    router leest, dan hoort het hier ook. Zonder dit stond er `list[Any]`, en dan gooide de
    typecontrole weg op precies de grens die je wilt bewaken.
    """

    @property
    def id(self) -> int: ...

    @property
    def volgorde(self) -> int: ...

    @property
    def naam(self) -> str: ...

    @property
    def base_url(self) -> str: ...

    @property
    def model(self) -> str: ...

    @property
    def heeft_sleutel(self) -> bool: ...

    @property
    def actief(self) -> bool: ...


class LLMProviderBeheer(Protocol):
    """Wat de router van de providerservice verwacht -- en niet meer dan dat.

    Een Protocol en geen import van `TenantLLMProviderService`: ADR-033 Contract 1 verbiedt de
    router om die klasse te kennen, en een kale `-> Any` gooit de typecontrole weg op precies
    de grens die je wilt bewaken. Dat laatste werd door een Gate 2-reviewer aangemerkt en door
    de Any-poort in de pre-commit hook geweigerd -- beide terecht.

    `toon` gaf tot 2026-09-21 `list[Any]` terug met een TODO, en de toelichting daarbij zei dat
    een echt type een gedeeld antwoordmodel vraagt en dus groter is dan deze feature. Dat was
    onjuist: een PROTOCOL voor de rij doet precies wat hier nodig is. Het noemt WAT de router van
    een rij nodig heeft in plaats van WELKE klasse hem levert, en dat is geen import over de
    grens maar de bedoeling van Contract 1. De frozen dataclass in de servicelaag voldoet er
    structureel aan zonder ervan te weten. (Gevonden doordat de Any-ratel na BE-LLM-003 rood
    stond: 7111 -> 7117, gemeten 2026-09-21.)
    """

    async def configureer(
        self,
        tenant_id: int,
        *,
        volgorde: int,
        naam: str,
        base_url: str,
        model: str,
        api_key: str | None = None,
        actief: bool = True,
    ) -> int: ...

    # `Sequence` en niet `list`: `list` is invariant, dus `list[ProviderOverzicht]` zou niet
    # toewijsbaar zijn aan `list[ProviderRegel]` en de implementatie zou het Protocol niet
    # vervullen. `Sequence` is covariant en de router leest alleen.
    async def toon(self, tenant_id: int) -> Sequence[ProviderRegel]: ...


def bouw_llm_provider_service(db: AsyncSession) -> LLMProviderBeheer:
    """Knoop de LLM-providerservice aan elkaar -- de FACADE, niet de router.

    ADR-033 Contract 1: een sub-router mag domeinlogica niet rechtstreeks importeren. De eerste
    versie van `llm_providers_router.py` deed dat wel en liet drie bewakers omvallen
    (`test_importlinter_contract1_covers_sub_routers`, `test_dsm_api_violations`,
    `test_fan_out_budget[core_api]`). Deze laag mag het wel, en is er juist voor.

    Lokale imports, net als elders in dit bestand: ze houden de fan-out van de API-laag omlaag
    en voorkomen dat een importcyclus bij het opstarten ontstaat.

    Gooit `HoofdsleutelOntbreekt` als MASTER_ENCRYPTION_KEY niet gezet is. Dat is opzet: zonder
    hoofdsleutel worden opgeslagen klantsleutels onleesbaar na een herstart, en dat hoort luid
    te falen in plaats van stil door te gaan.
    """
    from src.core.repositories.tenant_llm_provider_repository import TenantLLMProviderRepository
    from src.core.security.llm_endpoint_policy import maak_klant_endpoint_protector
    from src.core.security.tenant_secret_encryption import TenantSecretEncryption
    from src.core.services.tenant_llm_provider_service import TenantLLMProviderService

    return TenantLLMProviderService(
        repository=TenantLLMProviderRepository(db),
        encryptie=TenantSecretEncryption(),
        protector=maak_klant_endpoint_protector(),
    )


def llm_provider_fouten() -> tuple[type[Exception], type[Exception]]:
    """De twee fouttypes die de router moet kunnen onderscheiden, zonder ze te importeren.

    Teruggeven in plaats van laten importeren: zie `bouw_llm_provider_service` voor waarom de
    router deze modules niet rechtstreeks mag kennen.
    """
    from src.core.security.tenant_secret_encryption import HoofdsleutelOntbreekt
    from src.core.services.tenant_llm_provider_service import ExterneProviderNietToegestaan

    return ExterneProviderNietToegestaan, HoofdsleutelOntbreekt


#: De constraint die afgaat als twee providers dezelfde plek in de keten krijgen.
LLM_PROVIDER_VOLGORDE_CONSTRAINT = "uq_tenant_llm_providers_tenant_volgorde"


def dubbele_volgorde_fout() -> type[Exception]:
    """`IntegrityError`, zodat de router een 409 kan geven waar eerst een 500 stond.

    `uq_tenant_llm_providers_tenant_volgorde` slaat toe zodra een adviseur twee providers op
    dezelfde plek in de keten zet. Zonder deze tak gaf dat een kale 500 en werd er GEEN
    auditregel geschreven, want die staat na de aanroep (Gate 2-bevinding 2026-09-20).

    Let op: dit is het BREDE type. Of de fout werkelijk over de volgorde gaat, bepaalt
    `is_dubbele_volgorde` hieronder -- anders zou elke integriteitsfout (een verwijderde tenant
    via de foreign key, een NOT NULL, of een constraint die er in fase 2b bijkomt) worden
    gemeld als "volgorde al in gebruik". Dat is niet alleen onjuist tegenover de aanvrager;
    het zou een echt defect als invoerfout wegschrijven en er geen spoor van overlaten.
    """
    from sqlalchemy.exc import IntegrityError

    return IntegrityError


def is_dubbele_volgorde(exc: Exception) -> bool:
    """Gaat deze `IntegrityError` over de volgorde-constraint, of over iets anders?

    Op de naam van de constraint en niet op de tekst van de melding: die verschilt per
    databasedriver en per versie. `psycopg` hangt de originele fout onder `.orig`, en die
    draagt de naam mee; als dat om wat voor reden ook niet lukt, valt de controle terug op de
    tekstweergave -- en bij twijfel is het antwoord NEE, zodat een onbekende fout de 500 krijgt
    die erbij hoort in plaats van een geruststellende 409.
    """
    origineel = getattr(exc, "orig", None)
    diagnose = getattr(origineel, "diag", None)
    naam = getattr(diagnose, "constraint_name", None)
    if naam:
        return bool(naam == LLM_PROVIDER_VOLGORDE_CONSTRAINT)
    return LLM_PROVIDER_VOLGORDE_CONSTRAINT in str(origineel or exc)


async def schrijf_llm_provider_audit(
    db: AsyncSession,
    *,
    event_type: str,
    # `int | None` en niet `object`: `log_security_event` neemt precies dat, en een bredere
    # annotatie gaf pyright terecht een fout. Gemeten 2026-09-21 bij het omlaag brengen van de
    # Any-ratel -- de brede variant maakte de teller lager en het type onwaar.
    user_id: int | None,
    tenant_id: int,
    ip_address: str,
    request_method: str,
    details: dict[str, object],
) -> None:
    """Schrijf een auditregel voor het providerbeheer -- MET database, en best-effort.

    **Waarom deze helper bestaat en de router niet gewoon `log_security_event` aanroept.**
    Gemeten in Gate 2 (2026-09-20): `log_security_event` keert zonder `db` meteen terug
    (`audit_service.py:188-190`, "No database session provided, skipping database audit log").
    De drie aanroepen in de router gaven geen `db` mee, dus er werd een logregel geschreven en
    GEEN `AuditLog`-rij -- terwijl de routerdocstring en de feature-spec allebei beweerden dat
    er een auditspoor ontstond. Dat is precies het patroon waar CLAUDE.md voor waarschuwt: code
    die niets doet en er in elke test en elk dashboard uitziet als code die werkt. Door het
    meegeven van `db` hier af te dwingen, kan een aanroeper het niet meer vergeten.

    **En waarom er een expliciete `commit()` bij hoort.** Dit was de bevinding NA de reparatie
    hierboven, gevonden in de tweede reviewronde en nagemeten: `AuditService.log_event` doet
    alleen `await db.flush()` (`audit_service.py:123`, binnen `begin_nested`), en
    `log_security_event` commit nergens. De sessie van `get_db` commit pas NA de handler, en
    alleen als die geen uitzondering gooit -- bij een uitzondering doet hij
    `await session.rollback()` (`database.py:509-513`). Op de twee WEIGERPADEN gooit de router
    daarna een `HTTPException`, dus de zojuist geschreven auditregel werd teruggedraaid. Het
    spoor van precies de twee gebeurtenissen die je forensisch nodig hebt -- een beheerder die
    een verboden of intern adres probeert -- bestond dus niet. Op het slaagpad bleef hij wel
    staan, want daar commit `get_db` gewoon; dat verschil maakte het onzichtbaar.

    **Best-effort, conform backend-patterns regel 3.** De aanroeper legt de primaire data EERST
    vast; dit blok is secundair en mag falen zonder de handeling mee te slepen.

    Het pad is `/admin/llm-providers` en niet `/api/v1/admin/...`: de router wordt via
    `registries/auth_admin.py` zonder dat voorvoegsel gemount. Een forensisch spoor met een
    niet-bestaand pad erin is minder waard.
    """
    from src.core.utils.best_effort import best_effort

    async with best_effort(f"auditregel {event_type} voor llm-providerbeheer", db_session=db):
        await log_security_event(
            event_type=event_type,
            user_id=user_id,
            tenant_id=tenant_id,
            request_path="/admin/llm-providers",
            request_method=request_method,
            ip_address=ip_address,
            details=details,
            db=db,
        )
        await db.commit()


class ApVerbindingBeheerProtocol(Protocol):
    """Wat de beheerroute van de AP-verbindingservice nodig heeft (zonder hem te importeren)."""

    async def toon(self, tenant_id: int) -> object: ...

    async def leg_vast(
        self,
        tenant_id: int,
        *,
        base_url: str,
        email: str,
        wachtwoord: str,
        project_id: str,
    ) -> object: ...


def bouw_ap_verbinding_beheer(db: AsyncSession) -> ApVerbindingBeheerProtocol:
    """Knoop de AP-verbindingservice aan elkaar -- de FACADE, niet de router (ADR-033).

    Gooit `HoofdsleutelOntbreekt` als MASTER_ENCRYPTION_KEY niet gezet is: zonder hoofdsleutel
    zou een opgeslagen wachtwoord onleesbaar worden na een herstart, en dat hoort luid te falen.
    """
    from src.core.activepieces.verbinding_beheer import ApVerbindingBeheer
    from src.core.repositories.tenant_ap_verbinding_repository import TenantAPVerbindingRepository
    from src.core.security.tenant_secret_encryption import TenantSecretEncryption

    return ApVerbindingBeheer(
        opslag=TenantAPVerbindingRepository(db), encryptie=TenantSecretEncryption()
    )


def ap_hoofdsleutel_fout() -> type[Exception]:
    """De fout 'hoofdsleutel ontbreekt', zonder dat de router hem hoeft te importeren."""
    from src.core.security.tenant_secret_encryption import HoofdsleutelOntbreekt

    return HoofdsleutelOntbreekt


async def require_platform_superuser(
    current_user: UserResponse = Depends(get_current_user),
) -> UserResponse:
    """Alleen een platformbeheerder, geen tenantbeheerder.

    Een tenantbeheerder mag NIET bepalen waar de workflows van zijn bedrijf draaien of met welk
    account: dat is inrichting door het platform (ADR-040 B3). `is_admin` laat een
    tenantbeheerder door en is hier dus de verkeerde vraag.
    """
    from src.core.auth.api_deps import is_platform_superuser

    if not is_platform_superuser(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Alleen voor het platform")
    return current_user


async def schrijf_ap_verbinding_audit(
    db: AsyncSession,
    *,
    event_type: str,
    user_id: int | None,
    tenant_id: int,
    ip_address: str,
    request_method: str,
    details: dict[str, object],
) -> None:
    """Auditregel voor het beheer van de AP-verbinding -- met database, best-effort, na een commit.

    Zelfde redenering als `schrijf_llm_provider_audit`: zonder `db` schrijft `log_security_event`
    geen rij, en zonder `commit()` verdwijnt de regel op een weigerpad. De `details` bevatten
    NOOIT het wachtwoord.
    """
    from src.core.utils.best_effort import best_effort

    async with best_effort(f"auditregel {event_type} voor ap-verbindingbeheer", db_session=db):
        await log_security_event(
            event_type=event_type,
            user_id=user_id,
            tenant_id=tenant_id,
            request_path=f"/admin/tenants/{tenant_id}/ap-verbinding",
            request_method=request_method,
            ip_address=ip_address,
            details=details,
            db=db,
        )
        await db.commit()
