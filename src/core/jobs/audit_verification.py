"""
Audit Trail Verification Job

Periodically verifies the hash chain integrity of audit logs for all tenants.
Runs daily to ensure audit trail integrity per ADR-019.

Sprint 7, Task 3.3
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database.bypass_session import adopt_tenant
from src.core.governance.hash_chain import HashChainVerifier
from src.core.governance.models import AuditChainAnchor
from src.core.models.rbac_models import Tenant

logger = logging.getLogger(__name__)


@dataclass
class JobResult:
    """Result of running the audit trail verification job."""

    total_tenants: int
    verified_tenants: int
    failed_tenants: int
    total_entries_checked: int
    total_broken_chains: int
    started_at: datetime
    completed_at: datetime
    duration_ms: float


@dataclass
class TenantVerificationResult:
    """Result of verifying a single tenant's audit trail."""

    tenant_id: int
    is_valid: bool
    total_entries: int
    verified_entries: int
    broken_at_entry_id: int | None
    checked_at: datetime
    verification_time_ms: float
    #: De laatste hash in de keten. Nodig om te zien of geschiedenis is HERSCHREVEN bij een
    #: gelijkgebleven aantal rijen -- een telling alleen mist dat (ADR-036 OP-119).
    head_hash: str | None = None
    #: Rijen zonder hash. Het aantal is een bekend gat; de TOENAME is het watermerk (OP-118).
    unhashed_entries: int = 0
    #: De laagste `id` met een gesleutelde hash, of `None`. Wordt eenmalig het knippunt voor
    #: OP-120: na dit punt is een ONgesleutelde rij zelf een afwijking, ook als de hash klopt.
    first_keyed_entry_id: int | None = None


def _tel_afwijking(afwijking: "ChainAnchorDeviation") -> None:
    """Publiceer de afwijking als Prometheus-teller (ADR-036 OP-109).

    Lazy import: `audit_chain_metrics` raakt de globale registry, en dat willen we niet bij het
    importeren van deze module afdwingen. Best-effort -- een kapotte metriek mag de verificatie
    nooit tegenhouden, want dan verliezen we het signaal EN de meting.
    """
    try:
        from src.core.observability import audit_chain_metrics as m

        label = str(afwijking.tenant_id)
        if afwijking.soort == "unhashed_increase":
            m.audit_chain_unhashed_total.labels(tenant_id=label).inc()
        else:
            # row_count_drop en head_changed_without_growth zijn allebei verlies of herschrijving
            # van vastgelegd bewijs -- dat is het P0-signaal, geen dekkingsgat.
            m.audit_chain_tampering_total.labels(tenant_id=label).inc()
    except Exception as exc:  # noqa: BLE001 -- gelogd, nooit fataal
        logger.error("kon ketenafwijking niet tellen: %s: %s", type(exc).__name__, exc)


@dataclass
class ChainAnchorDeviation:
    """Een verschil tussen de vorige gemeten toestand en nu (ADR-036 OP-118/OP-119)."""

    tenant_id: int
    soort: str  # row_count_drop | head_changed_without_growth | unhashed_increase
    toelichting: str


class AuditTrailVerificationJob:
    """
    Background job that verifies hash chain integrity of audit logs.

    This job:
    1. Gets all active tenants
    2. For each tenant, verifies the audit log hash chain
    3. Stores the verification result
    4. Updates the tenant's last_verified_at timestamp
    5. Returns aggregated results

    Usage:
        job = AuditTrailVerificationJob(db_session=session)
        result = await job.run()
    """

    def __init__(self, db_session: AsyncSession):
        """
        Initialize the job with a database session.

        Args:
            db_session: Async SQLAlchemy session for database operations
        """
        self.db_session = db_session

    async def run(self) -> JobResult:
        """
        Run verification for all active tenants.

        Returns:
            JobResult with aggregated verification statistics
        """
        started_at = datetime.now(timezone.utc)
        start_time = time.time()

        # Get all active tenants
        tenant_query = select(Tenant).where(Tenant.is_active.is_(True))
        result = await self.db_session.execute(tenant_query)
        tenants = result.scalars().all()

        total_tenants = len(tenants)
        verified_tenants = 0
        failed_tenants = 0
        total_entries_checked = 0
        total_broken_chains = 0

        logger.info(
            "Starting audit trail verification for %d tenants", total_tenants
        )

        for tenant in tenants:
            try:
                # De klant wordt PER RONDE aangenomen (ADR-036 OP-153).
                #
                # Deze taak draait op een planner, buiten elk verzoek, dus de ContextVar
                # is leeg. De klantenlijst hierboven blijft werken -- `tenants` heeft geen
                # afschermingsregel (gemeten 2026-09-16: `relrowsecurity = f`, nul
                # policies) -- maar alles DAARBINNEN raakt tabellen die er wel een hebben.
                #
                # `store_result` schrijft een INSERT, en die zou zich na de omschakeling
                # naar `sanskritisetu_app` met een foutmelding melden. `verify_tenant`
                # LEEST, en dat is het gevaarlijke geval: nul rijen zonder enig signaal,
                # oftewel een hashketen die "in orde" heet omdat er niets in te zien was.
                #
                # `tenant.id` komt uit de database, nooit uit invoer.
                async with adopt_tenant(self.db_session, tenant.id):
                    tenant_result = await self.verify_tenant(tenant.id)
                    await self.store_result(tenant_result)

                total_entries_checked += tenant_result.total_entries

                if tenant_result.is_valid:
                    verified_tenants += 1
                else:
                    failed_tenants += 1
                    total_broken_chains += 1

                logger.debug(
                    "Verified tenant %d: valid=%s, entries=%d",
                    tenant.id,
                    tenant_result.is_valid,
                    tenant_result.total_entries,
                )
            except Exception as e:
                failed_tenants += 1
                logger.error(
                    "Failed to verify tenant %d: %s: %s",
                    tenant.id,
                    type(e).__name__,
                    e,
                    exc_info=True,
                )
                # Continue with next tenant - don't let one failure stop the job

        completed_at = datetime.now(timezone.utc)
        duration_ms = (time.time() - start_time) * 1000

        logger.info(
            "Audit trail verification completed: %d verified, %d failed, "
            "%d broken chains, duration=%.2fms",
            verified_tenants,
            failed_tenants,
            total_broken_chains,
            duration_ms,
        )

        return JobResult(
            total_tenants=total_tenants,
            verified_tenants=verified_tenants,
            failed_tenants=failed_tenants,
            total_entries_checked=total_entries_checked,
            total_broken_chains=total_broken_chains,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
        )

    async def _laagste_gesleutelde_id(self, tenant_id: int) -> int | None:
        """De laagste `id` met een gesleutelde hash -- het knippunt zodra het er is."""
        from src.core.governance.audit_chain_key import ALGORITHM_NAME
        from src.core.governance.models import AuditLog

        resultaat = await self.db_session.execute(
            select(AuditLog.id)
            .where(AuditLog.tenant_id == tenant_id, AuditLog.hash_algorithm == ALGORITHM_NAME)
            .order_by(AuditLog.id.asc())
            .limit(1)
        )
        return resultaat.scalar_one_or_none()

    async def verify_tenant(self, tenant_id: int) -> TenantVerificationResult:
        """
        Verify single tenant's audit trail using HashChainVerifier.

        Args:
            tenant_id: The tenant ID to verify

        Returns:
            TenantVerificationResult with verification details
        """
        # Het knippunt uit het anker meegeven, zodat een ONgesleutelde rij NA de omschakeling
        # als afwijking wordt gemeld (ADR-036 OP-120). De drie admin-endpoints doen dat bewust
        # niet -- die kennen de ankertabel niet -- en gedragen zich dus als voorheen.
        anker = (
            await self.db_session.execute(
                select(AuditChainAnchor).where(AuditChainAnchor.tenant_id == tenant_id)
            )
        ).scalar_one_or_none()

        verifier = HashChainVerifier(self.db_session)
        chain_result = await verifier.verify_chain(
            tenant_id, chain_epoch_id=anker.chain_epoch_id if anker else None
        )

        return TenantVerificationResult(
            tenant_id=tenant_id,
            is_valid=chain_result.is_valid,
            total_entries=chain_result.total_entries,
            verified_entries=chain_result.verified_entries,
            broken_at_entry_id=chain_result.broken_at_entry_id,
            checked_at=chain_result.checked_at,
            verification_time_ms=chain_result.verification_time_ms,
            head_hash=await self._kop_van_de_keten(tenant_id),
            unhashed_entries=chain_result.unhashed_entries,
            first_keyed_entry_id=await self._laagste_gesleutelde_id(tenant_id),
        )

    async def _kop_van_de_keten(self, tenant_id: int) -> str | None:
        """De laatste `audit_hash` van deze tenant.

        EXACT dezelfde lookup als de zes schrijvers doen -- `audit_hash IS NOT NULL`, gesorteerd
        op `(timestamp, id)` aflopend. Een andere volgorde zou een andere kop opleveren dan
        waaraan daadwerkelijk is geketend, en dan meldt het anker een wijziging die er niet is.
        Deze query wordt bediend door de partiele index `ix_audit_logs_chain_lookup`.
        """
        from src.core.governance.models import AuditLog

        resultaat = await self.db_session.execute(
            select(AuditLog.audit_hash)
            .where(AuditLog.tenant_id == tenant_id, AuditLog.audit_hash.isnot(None))
            .order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
            .limit(1)
        )
        return resultaat.scalar_one_or_none()

    async def store_result(
        self, result: TenantVerificationResult
    ) -> list[ChainAnchorDeviation]:
        """Vergelijk met het vorige anker en werk het bij (ADR-036 OP-118/OP-119).

        Geeft de gevonden afwijkingen terug. Een lege lijst betekent: niets verloren.

        **Wat hier stond en waarom het niets deed.** Deze methode zette
        `tenant.last_verified_at`, en die kolom bestaat niet -- niet op het model, niet in enige
        migratie. SQLAlchemy kent hem dan niet, dus er werd niets gevlagd en niets weggeschreven.
        De twee tests die dit dekten gebruikten een `MagicMock`, en die accepteert elk attribuut;
        ze slaagden dus ook terwijl er niets gebeurde.

        **De volgorde is essentieel: eerst VERGELIJKEN, dan pas overschrijven.** Andersom is het
        anker altijd gelijk aan de laatste meting en detecteert het per constructie niets.
        """
        bestaand = (
            await self.db_session.execute(
                select(AuditChainAnchor).where(AuditChainAnchor.tenant_id == result.tenant_id)
            )
        ).scalar_one_or_none()

        afwijkingen = self._vergelijk_met_anker(bestaand, result)

        if bestaand is None:
            # Eerste meting voor deze tenant: vastleggen, niet alarmeren. Zonder deze tak zou
            # elke nieuwe tenant een vals alarm geven en gelooft niemand het signaal nog.
            self.db_session.add(
                AuditChainAnchor(
                    tenant_id=result.tenant_id,
                    head_hash=result.head_hash,
                    chain_epoch_id=result.first_keyed_entry_id,
                    row_count=result.total_entries,
                    unhashed_count=result.unhashed_entries,
                    last_verified_at=result.checked_at,
                )
            )
        else:
            # HET KNIPPUNT (ADR-036 OP-120). Eenmalig zetten en NOOIT verlagen: zou het
            # meebewegen met de laagste gesleutelde rij, dan verschuift een aanvaller het door
            # een oude rij te vervangen en valt alles ervoor weer buiten de controle.
            if bestaand.chain_epoch_id is None and result.first_keyed_entry_id is not None:
                bestaand.chain_epoch_id = result.first_keyed_entry_id
            bestaand.head_hash = result.head_hash
            bestaand.row_count = result.total_entries
            bestaand.unhashed_count = result.unhashed_entries
            bestaand.last_verified_at = result.checked_at

        await self.db_session.commit()

        for afwijking in afwijkingen:
            logger.error(
                "audit chain anchor deviation: %s -- %s",
                afwijking.soort,
                afwijking.toelichting,
                extra={"tenant_id": afwijking.tenant_id},
            )
            _tel_afwijking(afwijking)

        return afwijkingen

    @staticmethod
    def _vergelijk_met_anker(
        anker: "AuditChainAnchor | None", result: TenantVerificationResult
    ) -> list[ChainAnchorDeviation]:
        """De drie dingen die een staatloze verifier per constructie niet kan zien."""
        if anker is None:
            return []

        afwijkingen: list[ChainAnchorDeviation] = []

        # OP-119. Auditregels horen alleen bij te komen. Verdwijnen ze, dan is dat of een
        # opruimjob die de verkeerde tabel raakt (OP-115) of iemand die sporen wist.
        if result.total_entries < anker.row_count:
            afwijkingen.append(
                ChainAnchorDeviation(
                    tenant_id=result.tenant_id,
                    soort="row_count_drop",
                    toelichting=(
                        f"{anker.row_count} -> {result.total_entries} auditregels. Regels horen "
                        "alleen bij te komen."
                    ),
                )
            )

        # Een telling alleen is niet genoeg: wie een rij VERVANGT houdt het aantal gelijk. Groeit
        # de keten wel, dan is een nieuwe kop juist de normale gang van zaken.
        elif result.total_entries == anker.row_count and result.head_hash != anker.head_hash:
            afwijkingen.append(
                ChainAnchorDeviation(
                    tenant_id=result.tenant_id,
                    soort="head_changed_without_growth",
                    toelichting=(
                        f"De kop veranderde van {anker.head_hash} naar {result.head_hash} "
                        f"terwijl het aantal regels op {anker.row_count} bleef."
                    ),
                )
            )

        # OP-118, het watermerk. Het BESTAANDE aantal ongehashte rijen is een bekend gat waarvoor
        # geen backfill mogelijk is (OP-108); daar alarmeren zou elke dag afgaan. Een TOENAME is
        # iets anders: sinds alle schrijvers de keten vullen hoort dat getal niet meer te stijgen.
        if result.unhashed_entries > anker.unhashed_count:
            afwijkingen.append(
                ChainAnchorDeviation(
                    tenant_id=result.tenant_id,
                    soort="unhashed_increase",
                    toelichting=(
                        f"{anker.unhashed_count} -> {result.unhashed_entries} regels zonder hash. "
                        "Sinds alle schrijvers de keten vullen is een nieuwe er een te veel."
                    ),
                )
            )

        return afwijkingen


# Default schedule configuration
DEFAULT_SCHEDULE = "0 3 * * *"  # Daily at 3:00 AM


def get_schedule() -> str:
    """
    Get the job schedule from environment variable or use default.

    Returns:
        Cron expression string
    """
    import os

    return os.getenv("AUDIT_VERIFICATION_SCHEDULE", DEFAULT_SCHEDULE)
