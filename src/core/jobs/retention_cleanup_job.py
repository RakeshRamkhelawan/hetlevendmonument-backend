"""
Retention Cleanup Job

Background job that enforces data retention policies per jurisdiction.
Runs daily to cleanup expired data based on GDPR and other privacy regulations.

Usage:
    from src.core.jobs.retention_cleanup_job import run_retention_cleanup
    await run_retention_cleanup()

    # Or scheduled via Dramatiq
    from src.workers.actors import run_retention_cleanup
    run_retention_cleanup.send()
"""

import logging
from datetime import datetime, timezone
from typing import TypedDict

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database.session import get_db_session
from src.core.governance.retention_cleanup import (
    DataCategory,
    RetentieDoeltabelOntbreekt,
    RetentionCleanupService,
    RetentionJurisdiction,
)

logger = logging.getLogger(__name__)


class CleanupStats(TypedDict):
    """Per-jurisdiction retention cleanup statistics."""

    jurisdiction: str
    categories_processed: int
    records_deleted: int
    errors: list[str]
    #: Categorieen die zijn overgeslagen omdat er geen doeltabel voor gekozen is. Bewust
    #: gescheiden van `errors`: er is niets stuk, er is iets niet beslist (ADR-036 OP-115).
    skipped: list[str]


class RetentionJobResult(TypedDict):
    """Overall result of a retention cleanup job run."""

    started_at: str
    jurisdictions: dict[str, CleanupStats | dict[str, str]]
    total_records_deleted: int
    total_errors: int
    completed: bool
    completed_at: str


#: Categorieen die een beleid EN een doeltabel hebben, maar die deze nachtelijke taak
#: bewust NIET automatisch opruimt. Reden per regel, en het is per stuk een besluit.
_NIET_AUTOMATISCH: dict[DataCategory, str] = {
    DataCategory.AUDIT_LOG: (
        "auditregels verwijderen breekt de SHA-256-hashketen van ADR-019 en is in ADR-036 "
        "OP-115 expliciet als onaanvaardbaar vastgelegd; die uitspraak staat zelfs in de "
        "foutmelding van `RetentieDoeltabelOntbreekt`. Een auditbewaartermijn hoort langs "
        "een eigen, met opzet ontworpen pad te lopen, niet langs een nachtelijke sweep."
    ),
    DataCategory.PERSONAL_DATA: (
        "deze categorie wijst naar `users`. Gebruikersaccounts op een timer verwijderen is "
        "een product- en juridisch besluit en geen onderhoudstaak; de AVG-route daarvoor is "
        "het wis-/DSAR-pad met een menselijke beslissing erin. Zet dit alleen aan als "
        "Rakesh daar expliciet voor kiest."
    ),
}


def te_verwerken_categorieen(jurisdiction: RetentionJurisdiction) -> list[DataCategory]:
    """De categorieen die deze taak daadwerkelijk kan opruimen -- AFGELEID, niet opgesomd.

    WAT HIER MIS WAS, en het is groot. Hier stond een handmatige lijst van vijf:

        USER_DATA, ACTIVITY_LOGS, AI_INTERACTIONS, DOCUMENTS, ANALYTICS
        # NOTE: enum values may differ from current DataCategory definition

    Geen van die vijf heeft een retentiebeleid in `DEFAULT_POLICIES`, en geen van die vijf
    heeft een doeltabel in `RetentionCleanupService._get_table_info`. Gemeten 2026-09-17:
    de doorsnede van de taaklijst met "heeft beleid EN doeltabel" is LEEG. Deze taak kon
    dus nooit ook maar een rij verwijderen, in geen enkele jurisdictie.

    Zo zag dat eruit in een echte run op staging, en let op hoe onschuldig het leest:

        "total_records_deleted": 0, "total_errors": 0, "completed": true

    Nul verwijderd, nul fouten, geslaagd. De reden stond wel in het veld `skipped` -- vijf
    keer "heeft geen doeltabel" per jurisdictie -- maar niemand leest de uitvoer van een
    nachtelijke taak die zegt dat hij geslaagd is. Dit is exact waar het runbook voor
    waarschuwt ("een worker die nul rijen ziet meldt vrolijk 0 verwerkt"), alleen met een
    andere oorzaak dan de afschermingsregels.

    Het is ook dezelfde faalvorm als de triage van vanochtend: TWEE VOCABULAIRES die
    langs elkaar heen leven. De ene lijst noemt `user_data`, de andere `personal_data`.

    DE OPLOSSING IS AFLEIDEN IN PLAATS VAN OPSOMMEN. Een categorie hoort erbij als er
    (1) een bewaartermijn voor deze jurisdictie bestaat en (2) een doeltabel bekend is.
    Voeg iemand later een categorie toe met allebei, dan doet deze taak er meteen wat mee;
    voegt iemand er een toe met alleen een beleid, dan slaat de bestaande luide melding
    hem over. Een handmatige lijst kan opnieuw stil verlopen -- deze niet.

    Twee categorieen staan er bewust NIET in; zie `_NIET_AUTOMATISCH` voor de reden per
    stuk. Bewaakt door `tests/unit/jobs/test_de_retentietaak_ruimt_echt_iets_op.py`.
    """
    from src.core.governance.retention_cleanup import DEFAULT_POLICIES, RetentionCleanupService

    dienst = RetentionCleanupService.__new__(RetentionCleanupService)
    uit: list[DataCategory] = []
    for categorie in DataCategory:
        if (jurisdiction, categorie) not in DEFAULT_POLICIES:
            continue
        if categorie in _NIET_AUTOMATISCH:
            continue
        try:
            if dienst._get_table_info(categorie):
                uit.append(categorie)
        except Exception:  # noqa: BLE001 -- geen doeltabel is geen storing, alleen geen werk
            continue
    return sorted(uit, key=lambda c: c.value)


async def cleanup_by_jurisdiction(
    db: AsyncSession,
    jurisdiction: RetentionJurisdiction,
    tenant_id: int | None = None,
) -> CleanupStats:
    """
    Cleanup expired data for a specific jurisdiction.

    Args:
        db: Database session
        jurisdiction: The jurisdiction to cleanup for

    Returns:
        Dictionary with cleanup statistics
    """
    service = RetentionCleanupService(db, tenant_id=tenant_id)
    stats: CleanupStats = {
        "jurisdiction": jurisdiction.value,
        "categories_processed": 0,
        "records_deleted": 0,
        "errors": [],
        "skipped": [],
    }

    categories = te_verwerken_categorieen(jurisdiction)

    for category in categories:
        try:
            result = await service.cleanup_expired_data(
                category=category,
                jurisdiction=jurisdiction,
            )
            stats["categories_processed"] += 1
            stats["records_deleted"] += result.records_deleted
            logger.info(
                f"Cleaned up {result.records_deleted} {category.value} "
                f"records for {jurisdiction.value}"
            )
        except RetentieDoeltabelOntbreekt as e:
            # Apart van een echte fout (ADR-036 OP-115): hier is niets STUK, er is iets niet
            # BESLIST. De categorie wordt overgeslagen en dat is zichtbaar in de uitvoer.
            # Zonder dit onderscheid zou een ontbrekende doeltabel als storing binnenkomen,
            # of -- zoals tot 2026-08-30 -- als een geslaagde opruiming van `audit_logs`.
            overgeslagen = (
                f"Overgeslagen: {category.value} voor {jurisdiction.value} heeft geen "
                f"doeltabel ({e})"
            )
            logger.warning(overgeslagen)
            stats["skipped"].append(overgeslagen)
        except Exception as e:
            error_msg = f"Failed to cleanup {category.value} for {jurisdiction.value}: {e}"
            logger.error(error_msg)
            stats["errors"].append(error_msg)

    return stats


async def run_retention_cleanup() -> RetentionJobResult:
    """
    Run the complete retention cleanup job for every active tenant.

    This function:
    1. Discovers active tenants (worker has no request middleware ContextVar)
    2. For each tenant, processes all jurisdictions (EU, US, UK, CA, AU)
    3. Cleans up expired data per jurisdiction's retention policy
    4. Logs results and sends notifications if configured

    Should be called daily by the scheduler.

    Returns:
        Dictionary with overall cleanup statistics
    """
    logger.info("Starting retention cleanup job")

    results: RetentionJobResult = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "jurisdictions": {},
        "total_records_deleted": 0,
        "total_errors": 0,
        "completed": False,
        "completed_at": "",
    }

    jurisdictions = [
        RetentionJurisdiction.EU,
        RetentionJurisdiction.US,
        RetentionJurisdiction.UK,
        RetentionJurisdiction.CA,
        RetentionJurisdiction.AU,
    ]

    from sqlalchemy import select

    from src.core.database.tenant_query_filter import TenantFilterBypass
    from src.core.models.rbac_models import Tenant

    aggregated: dict[str, CleanupStats] = {
        jurisdiction.value: {
            "jurisdiction": jurisdiction.value,
            "categories_processed": 0,
            "records_deleted": 0,
            "errors": [],
            "skipped": [],
        }
        for jurisdiction in jurisdictions
    }
    jurisdiction_errors: dict[str, str] = {}

    async with get_db_session() as db:
        with TenantFilterBypass():
            tenant_result = await db.execute(select(Tenant.id).where(Tenant.is_active.is_(True)))
            tenant_ids = [row[0] for row in tenant_result.fetchall()]

        from src.core.database.bypass_session import adopt_tenant

        for tenant_id in tenant_ids:
            # De tenant wordt PER RONDE aangenomen (ADR-036 OP-155).
            #
            # Deze taak draait in een worker, buiten elk verzoek, dus er is geen
            # tenantcontext. Zij VERWIJDERT uit onder meer `user_consents`, `ai_decisions`
            # en `twin_suggestion_log` -- alle drie met een RLS-policy sinds
            # `20260915_rls_resterende_tabellen.py`.
            #
            # Zonder deze regel gaat dat na de omschakeling naar `sanskritisetu_app` STIL
            # mis, en stil is hier erger dan luid. Gemeten 2026-09-16: bij DELETE bepaalt
            # `USING` eerst WELKE RIJEN zichtbaar zijn; zonder tenantcontext zijn dat er
            # nul, dus `DELETE 0`, geen fout, commit slaagt. Deze taak zou dan
            # `records_deleted: 0` als succes rapporteren en `retention_evidence.py` zou een
            # ondertekend bewijs vastleggen dat retentie heeft gedraaid -- een AVG-controle
            # die groen meldt terwijl zij niets doet.
            #
            # Gevonden door de Gate 2-securityreview van 2026-09-15, die aantoonde dat mijn
            # eerdere claim "schrijven faalt luid" alleen voor INSERT gold.
            async with adopt_tenant(db, tenant_id):
                for jurisdiction in jurisdictions:
                    try:
                        jurisdiction_stats = await cleanup_by_jurisdiction(
                            db, jurisdiction, tenant_id=tenant_id
                        )
                        existing = aggregated[jurisdiction.value]
                        existing["categories_processed"] += jurisdiction_stats[
                            "categories_processed"
                        ]
                        existing["records_deleted"] += jurisdiction_stats["records_deleted"]
                        existing["errors"].extend(jurisdiction_stats["errors"])
                        existing["skipped"].extend(jurisdiction_stats["skipped"])
                        results["total_records_deleted"] += jurisdiction_stats["records_deleted"]
                        results["total_errors"] += len(jurisdiction_stats["errors"])
                    except Exception as e:
                        error_msg = (
                            f"Failed to process jurisdiction {jurisdiction.value} "
                            f"for tenant {tenant_id}: {e}"
                        )
                        logger.error(error_msg)
                        jurisdiction_errors[jurisdiction.value] = error_msg
                        results["total_errors"] += 1

    # Convert aggregated stats to result dict; error entries override stats for
    # jurisdictions that failed for every tenant.
    results["jurisdictions"] = {
        **{key: value for key, value in aggregated.items() if key not in jurisdiction_errors},
        **{key: {"error": value} for key, value in jurisdiction_errors.items()},
    }

    results["completed_at"] = datetime.now(timezone.utc).isoformat()
    results["completed"] = True

    logger.info(
        "Retention cleanup completed: %d records deleted, %d errors",
        results["total_records_deleted"],
        results["total_errors"],
    )

    return results
