# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""GDPR Article 17: Right to Erasure (delete-all endpoint).

Routes:
  POST /api/gdpr/delete-all
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy import delete as sql_delete
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.actors.gdpr_purge import purge_user_data
from src.core.auth.api_deps import UserResponse
from src.core.feature_flags.models import FeatureFlag
from src.core.models.rbac_models import Tenant, User, user_roles
from src.core.utils.best_effort import best_effort

from .dependencies import Agent, AuditService, C7ExecutionTask as Task, C7Workflow as Workflow

from .dependencies import (
    ACTIE_AANGEBODEN,
    bouw_tenant_dossier,
    dossier_checksum,
    eis_dat_tenant_gewist_mag_worden,
    export_aangeboden,
    export_is_te_vaak_gevraagd,
    telling,
    get_current_tenant_id,
    get_current_user,
    anonimiseer_auditlog_van_tenant,
    anonimiseer_bewaarde_rapporten_van_tenant,
    get_db,
    lopende_delete_all,
    plan_gebruiker_wissing,
    require_admin_role,
    ruim_tenant_blokkades_op,
)
from .schemas import (
    DeleteDataRequest,
    DeleteDataResponse,
    DeleteType,
    TenantExportRequest,
    TenantExportResponse,
)

BERICHT_EXPORT_EERST = (
    "Voordat de gegevens worden gewist moet er eerst een export zijn aangeboden aan de klant, de "
    "bewaarder of de curator (POST /api/gdpr/delete-all/export): de wettelijke bewaarplicht van "
    "administratie ligt bij de klant, niet bij ons."
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/gdpr", tags=["GDPR Compliance"])


def _schedule_purge_task(user_id: int, tenant_id: int, scope: str = "all") -> None:
    """Schedule GDPR purge via Dramatiq actor (ADR-006: Dramatiq + Redis)."""
    purge_user_data.send(
        user_id=user_id,
        tenant_id=tenant_id,
        scope=scope,
    )
    logger.info(
        "gdpr_purge_scheduled: user_id=%s, tenant_id=%s, scope=%s",
        user_id,
        tenant_id,
        scope,
    )


def _tenant_nummer(tenant_id: str | int) -> int:
    """De tenant als getal. Een tenant uit de JWT is altijd een getal; is hij het niet, dan is de
    sessie onbruikbaar voor een wissing en volgt een 400 (geen 500, geen ongevangen fout).

    Gevonden 2026-10-14: `int(tenant_id)` stond voor de export-eerst-controle BUITEN het try-blok en
    gaf bij een tekst-tenant een ongevangen ValueError.
    """
    try:
        return int(tenant_id)
    except (TypeError, ValueError):
        logger.warning("GDPR route: tenant in de sessie is geen getal: %r", tenant_id)
        raise HTTPException(
            status_code=400, detail="Tenant in the session is not a valid tenant number"
        ) from None


async def _wis_rolkoppelingen_en_tenantloze_tabellen(db: AsyncSession, tenant_id: int) -> None:
    """Wat de harde wissing van de gebruikers en de tenant anders laat staan of blokkeert.

    - `user_roles`: `fk_user_roles_user_tenant` (OP-190 deel 2) heeft geen ON DELETE, dus de
      gebruikers laten zich anders niet verwijderen (gemeten 2026-10-11: elke harde wissing gaf 500).
    - `ai_decisions` en `user_profiling_opt_outs` hebben GEEN vreemde sleutel naar de tenant en
      blijven na de wissing als wees achter met persoonsgegevens (gemeten 2026-10-11).
    """
    await db.execute(sql_delete(user_roles).filter(user_roles.c.tenant_id == tenant_id))
    await db.execute(text("DELETE FROM ai_decisions WHERE tenant_id = :tid"), {"tid": tenant_id})
    await db.execute(
        text("DELETE FROM user_profiling_opt_outs WHERE tenant_id = :tid"), {"tid": tenant_id}
    )


@router.post(
    "/delete-all/export",
    response_model=TenantExportResponse,
    dependencies=[Depends(require_admin_role)],
    summary="Export all tenant data before deletion (GDPR Article 28(3)(g))",
)
async def export_tenant_data_before_deletion(
    request: TenantExportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id),
) -> TenantExportResponse:
    """Bouw de export van ALLE gegevens van de eigen tenant en leg vast dat die is aangeboden.

    Pas na deze aanbieding mag een harde wissing doorgaan, of de purge van een tenantbrede wissing
    na de 30 dagen. De export is voor de klant, of voor de bewaarder (BW 2:24) of curator (Fw 105b)
    die de beheerder opgeeft. De tenant komt uit de JWT, nooit uit de body.
    """
    tenant_nr = _tenant_nummer(tenant_id)
    if await export_is_te_vaak_gevraagd(db, tenant_nr):
        raise HTTPException(
            status_code=429,
            detail="Er zijn het laatste uur al te veel exports gevraagd; probeer het later opnieuw.",
        )
    dossier = await bouw_tenant_dossier(db, tenant_nr)
    tabellen, rijen, afgekapt = telling(dossier)
    checksum = dossier_checksum(dossier)
    await AuditService.log_action(
        tenant_id=tenant_nr,
        action=ACTIE_AANGEBODEN,
        resource="tenant_export:" + str(tenant_id),
        user_id=current_user.id,
        details={
            "recipient": request.recipient,
            "recipient_name": request.recipient_name,
            "sha256": checksum,
            "tables": tabellen,
            "rows": rijen,
            "truncated_tables": afgekapt,
        },
        session=db,
        event_type="gdpr_export",
        threat_level="info",
        client_ip="unknown",
        endpoint="/api/gdpr/delete-all/export",
        description="Tenant export offered before deletion",
    )
    await db.commit()
    return TenantExportResponse(
        recipient=request.recipient,
        sha256=checksum,
        tables=tabellen,
        rows=rijen,
        truncated_tables=afgekapt,
        message=(
            "De export is aangeboden aan: "
            + request.recipient
            + ". Bewaar dit bestand en het controlegetal (sha256); daarna mag de wissing "
            "doorgaan. Namen van tabellen met te veel rijen staan in truncated_tables."
        ),
        data=dossier,
    )


@router.post(
    "/delete-all",
    response_model=DeleteDataResponse,
    # GDPR-001: een tenantbrede wis is alleen voor een beheerder. Als dependency komt de 403
    # voor de validatie van de body (plan nazorg, punt d). De letterlijke controle op de rol
    # "admin" in de handler blijft staan (BE-GDPR-001, bewaakt door
    # tests/architecture/test_delete_authz_admin_only.py); samen geldt de strengste van de twee.
    dependencies=[Depends(require_admin_role)],
    summary="Delete All Tenant Data (GDPR Article 17)",
    description="""
    Delete all data associated with the current tenant.

    **GDPR Article 17 - Right to Erasure ('Right to be Forgotten'):**
    - User can request deletion of personal data
    - Data must be erased without undue delay

    **Delete Types:**
    - SOFT: users become inactive now; the data is wiped 30 days later by the daily planner.
      Within those 30 days the request can be revoked (`POST /api/gdpr/delete-all/revoke`).
    - HARD: Permanent deletion (requires admin approval)

    **Security:**
    - Requires confirmation code (must match tenant_id)
    - Soft delete by default
    - Hard delete requires admin role
    - Action is irreversible after purge date
    - Full audit trail
    """,
)
async def delete_tenant_data(
    request: DeleteDataRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id),
    *,
    http_request: Request,
) -> DeleteDataResponse:
    """Delete all tenant data for GDPR compliance (Article 17)."""
    logger.warning("GDPR deletion requested by user %s for tenant %s", current_user.id, tenant_id)

    # `tenant_id` komt uit een ContextVar en is een getal; de bevestigingscode is tekst. Zonder
    # `str()` verschilden "3" en 3 altijd en gaf de route ELKE keer 400 (gemeten 2026-10-11).
    if request.confirmation_code != str(tenant_id):
        raise HTTPException(status_code=400, detail="Confirmation code does not match tenant ID")

    # GDPR-001: a tenant-wide delete-all wipes ALL users/agents/workflows, so it is an
    # admin-only action for BOTH soft and hard delete. The confirmation_code (== the
    # caller's own tenant_id, from the JWT) is a UX safeguard, not an authz control.
    # Role is taken from the verified JWT (current_user.roles), never from the request body.
    if "admin" not in current_user.roles:
        raise HTTPException(
            status_code=403, detail="Tenant-wide deletion requires admin privileges"
        )

    tenant_nr = _tenant_nummer(tenant_id)
    # Een tenantbrede wissing raakt geen platformbeheerder, tenzij de aanvrager er zelf een is (brief
    # 2026-10-19). Voor de export-eerst-controle en voor elke wijziging.
    await eis_dat_tenant_gewist_mag_worden(db, http_request, int(current_user.id), tenant_nr)
    if request.delete_type == DeleteType.HARD and not await export_aangeboden(db, tenant_nr):
        raise HTTPException(status_code=409, detail=BERICHT_EXPORT_EERST)

    try:
        records_deleted = 0
        categories_deleted: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        purge_date: datetime | None = None
        uitgezette_workflow_ids: list[str] = []  # voor intrekken: alleen wat DEZE aanvraag uitzette

        if request.delete_type == DeleteType.SOFT:
            deletion_date = datetime.now(timezone.utc)
            purge_date = deletion_date + timedelta(days=30)

            tenant_result = await db.execute(select(Tenant).filter(Tenant.id == tenant_id))
            tenant = tenant_result.scalar_one_or_none()

            if not tenant:
                raise HTTPException(status_code=404, detail="Tenant not found")

            # De tenant zelf blijft actief tijdens de wachttijd: de aanvragende beheerder moet de
            # aanvraag kunnen intrekken. De gebruikers zijn inactief (kunnen niet inloggen).
            if hasattr(tenant, "deletion_reason"):
                tenant.deletion_reason = request.reason

            users_result = await db.execute(select(User).filter(User.tenant_id == tenant_id))
            users = users_result.scalars().all()
            # Een tweede aanvraag houdt de termijn van de eerste (het antwoord noemt die datum).
            eerder = await lopende_delete_all(db, tenant_nr)
            if eerder is not None and eerder[0] > deletion_date:
                # Alleen een NOG LOPENDE termijn: een verstreken termijn overnemen liet de
                # wachttijd van 30 dagen voor een nieuwe aanvraag wegvallen.
                purge_date = eerder[0]
            for user in users:
                # Niets wordt nu gewist: de gebruiker wordt inactief en de purge volgt na 30 dagen
                # (`avg_purge_job`); tot dan is de aanvraag in te trekken (`/delete-all/revoke`).
                # De aanvrager blijft ACTIEF om te kunnen intrekken; zijn gegevens worden na de
                # termijn net als die van de rest gewist.
                if str(user.id) == str(current_user.id):
                    if user.deletion_scheduled_for is None:
                        user.deletion_scheduled_for = purge_date
                else:
                    plan_gebruiker_wissing(user, deletion_date, purge_date)
            records_deleted += len(users)
            categories_deleted.append("users")

            agents_result = await db.execute(select(Agent).filter(Agent.tenant_id == tenant_id))
            agents = agents_result.scalars().all()
            for agent in agents:
                if hasattr(agent, "is_active"):
                    agent.is_active = False
                if hasattr(agent, "deleted_at"):
                    agent.deleted_at = deletion_date
            records_deleted += len(agents)
            categories_deleted.append("agents")

            workflows_result = await db.execute(
                select(Workflow).filter(Workflow.tenant_id == tenant_id)
            )
            workflows = workflows_result.scalars().all()
            for workflow in workflows:
                if workflow.is_active:
                    uitgezette_workflow_ids.append(str(workflow.id))
                workflow.is_active = False
                if hasattr(workflow, "deleted_at"):
                    workflow.deleted_at = deletion_date
            records_deleted += len(workflows)
            categories_deleted.append("workflows")

            logger.warning(
                "SOFT DELETE: Marked %s records for deletion. Purge scheduled for %s",
                records_deleted,
                purge_date,
            )

        else:
            # HARD DELETE: permanent deletion in FK-safe order
            tasks_result = await db.execute(sql_delete(Task).filter(Task.tenant_id == tenant_id))
            records_deleted += getattr(tasks_result, "rowcount", 0)
            categories_deleted.append("tasks")

            workflows_result = await db.execute(
                sql_delete(Workflow).filter(Workflow.tenant_id == tenant_id)
            )
            records_deleted += getattr(workflows_result, "rowcount", 0)
            categories_deleted.append("workflows")

            agents_result = await db.execute(sql_delete(Agent).filter(Agent.tenant_id == tenant_id))
            records_deleted += getattr(agents_result, "rowcount", 0)
            categories_deleted.append("agents")

            ff_result = await db.execute(
                sql_delete(FeatureFlag).filter(FeatureFlag.tenant_id == tenant_id)
            )
            records_deleted += getattr(ff_result, "rowcount", 0)
            categories_deleted.append("feature_flags")

            # De rolkoppelingen eerst: `fk_user_roles_user_tenant` (OP-190 deel 2) heeft geen ON DELETE,
            # dus de gebruikers laten zich anders niet verwijderen (gemeten 2026-10-11: elke harde
            # wissing gaf 500).
            await ruim_tenant_blokkades_op(db, tenant_nr)
            # Het auditlog BLIJFT bestaan, zonder persoonsgegevens en zonder de keten te breken
            # (`avg_auditlog.py`); de gebruikers kunnen daarna weg omdat `user_id` leeg is.
            await anonimiseer_auditlog_van_tenant(db, tenant_nr)
            # AI-incidentmeldingen en toezichthouder-rapporten: bewaren, zonder persoonsgegevens.
            await anonimiseer_bewaarde_rapporten_van_tenant(db, tenant_nr)
            await _wis_rolkoppelingen_en_tenantloze_tabellen(db, tenant_nr)

            users_result = await db.execute(sql_delete(User).filter(User.tenant_id == tenant_id))
            records_deleted += getattr(users_result, "rowcount", 0)
            categories_deleted.append("users")

            tenant_result = await db.execute(sql_delete(Tenant).filter(Tenant.id == tenant_id))
            records_deleted += getattr(tenant_result, "rowcount", 0)
            categories_deleted.append("tenant")

            # Auditregels blijven bewaard, geanonimiseerd; bewaartermijn volgens de werkgever
            # (er is geen wettelijke termijn gemeten).
            purge_date = None
            logger.critical(
                "HARD DELETE: Permanently deleted %s records for tenant %s",
                records_deleted,
                tenant_id,
            )

        # Commit deletions first so they are durable regardless of audit outcome.
        await db.commit()

        # Audit log is best-effort: deletion already committed, must not cause 500.
        async with best_effort("gdpr delete audit log", db_session=db):
            await AuditService.log_action(
                tenant_id=tenant_nr,
                action="gdpr_delete_all",
                resource="tenant_data:" + str(tenant_id),
                # Bij een harde wissing bestaat de aanvrager niet meer: een verwijzing naar zijn
                # (verwijderde) gebruikersrij zou de regel laten mislukken.
                user_id=None if request.delete_type == DeleteType.HARD else current_user.id,
                details={
                    "delete_type": request.delete_type,
                    "records_deleted": records_deleted,
                    "categories_deleted": categories_deleted,
                    # Vrije tekst van de beheerder: bij een harde wissing niet bewaren.
                    "reason": None if request.delete_type == DeleteType.HARD else request.reason,
                    "scheduled_purge": purge_date.isoformat() if purge_date else None,
                    "deactivated_workflow_ids": uitgezette_workflow_ids,
                },
                session=db,
                event_type="gdpr_delete",
                threat_level=("critical" if request.delete_type == DeleteType.HARD else "warning"),
                client_ip="unknown",
                endpoint="/api/gdpr/delete-all",
                description=(
                    "GDPR data deletion ("
                    + str(request.delete_type)
                    + ") for tenant "
                    + str(tenant_id)
                ),
            )
            await db.commit()

        return DeleteDataResponse(
            tenant_id=str(tenant_id),
            delete_type=request.delete_type,
            deletion_date=datetime.now(timezone.utc),
            scheduled_purge_date=purge_date,
            records_deleted=records_deleted,
            categories_deleted=categories_deleted,
            message=BERICHT_EXPORT_EERST if request.delete_type == DeleteType.SOFT else "",
        )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(
            "GDPR deletion failed for tenant %s: %s: %s",
            tenant_id,
            type(e).__name__,
            e,
            exc_info=True,
        )
        async with best_effort("gdpr delete failure audit log", db_session=db):
            await AuditService.log_action(
                tenant_id=tenant_nr,
                action="gdpr_delete_all",
                resource="tenant_data:" + str(tenant_id),
                user_id=current_user.id,
                details={"error": "Er is een fout opgetreden.", "delete_type": request.delete_type},
                session=db,
                event_type="gdpr_delete_failed",
                threat_level="error",
                client_ip="unknown",
                endpoint="/api/gdpr/delete-all",
                description=("GDPR data deletion failed for tenant " + str(tenant_id)),
            )
            await db.commit()
        raise HTTPException(status_code=500, detail="Internal error")
