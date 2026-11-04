"""GDPR purge Dramatiq actor for user data anonymization.

SP-E05: Implements real GDPR Art. 17 purge scheduler.
Anonymizes (not hard-deletes) user data to preserve audit trail.
"""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.governance.avg_wissing_planning import meld_tenant_zonder_beheerder

logger = logging.getLogger(__name__)

# Module-level placeholder; overridden conditionally below.
# Pattern matches src/workers/actors.py exactly.
purge_user_data: Any = None  # pyright: ignore


# Persoonsgegevens buiten de gebruikersrij en de gesprekstabellen, per tabel een eigen deelstap. Elke
# deelstap krijgt (db, user_id, tenant_id), wist ALLEEN rijen van die persoon binnen die tenant en
# geeft het aantal verwijderde rijen terug. `cva_conversations.user_id` en `ai_decisions.user_id`
# zijn TEKST: vergelijken met een getal geeft "operator does not exist: character varying =
# integer" (gemeten 2026-10-11).
async def _wis_cva_conversations(db: AsyncSession, user_id: int, tenant_id: int) -> int:
    from sqlalchemy import text

    result = await db.execute(
        text("DELETE FROM cva_conversations WHERE user_id = :uid AND tenant_id = :tid"),
        {"uid": str(user_id), "tid": tenant_id},
    )
    return int(getattr(result, "rowcount", 0) or 0)


async def _wis_memory_items(db: AsyncSession, user_id: int, tenant_id: int) -> int:
    # De embedding is een niet te anonimiseren afgeleide van persoonsgegevens: fysiek wissen.
    from sqlalchemy import text

    result = await db.execute(
        text("DELETE FROM memory_items WHERE user_id = :uid AND tenant_id = :tid"),
        {"uid": user_id, "tid": tenant_id},
    )
    return int(getattr(result, "rowcount", 0) or 0)


async def _wis_ai_decisions(db: AsyncSession, user_id: int, tenant_id: int) -> int:
    from sqlalchemy import text

    result = await db.execute(
        text("DELETE FROM ai_decisions WHERE user_id = :uid AND tenant_id = :tid"),
        {"uid": str(user_id), "tid": tenant_id},
    )
    return int(getattr(result, "rowcount", 0) or 0)


async def _wis_agentic_tasks(db: AsyncSession, user_id: int, tenant_id: int) -> int:
    from sqlalchemy import text

    result = await db.execute(
        text("DELETE FROM agentic_tasks WHERE created_by = :uid AND tenant_id = :tid"),
        {"uid": user_id, "tid": tenant_id},
    )
    return int(getattr(result, "rowcount", 0) or 0)


async def _wis_gamification(db: AsyncSession, user_id: int, tenant_id: int) -> int:
    from sqlalchemy import text

    params = {"uid": user_id, "tid": tenant_id}
    gewist = 0
    for opdracht in (
        text("DELETE FROM point_transactions WHERE user_id = :uid AND tenant_id = :tid"),
        text("DELETE FROM user_badges WHERE user_id = :uid AND tenant_id = :tid"),
        text("DELETE FROM user_points WHERE user_id = :uid AND tenant_id = :tid"),
    ):
        result = await db.execute(opdracht, params)
        gewist += int(getattr(result, "rowcount", 0) or 0)
    return gewist


async def _wis_profiling_opt_outs(db: AsyncSession, user_id: int, tenant_id: int) -> int:
    from sqlalchemy import text

    result = await db.execute(
        text("DELETE FROM user_profiling_opt_outs WHERE user_id = :uid AND tenant_id = :tid"),
        {"uid": str(user_id), "tid": tenant_id},
    )
    return int(getattr(result, "rowcount", 0) or 0)


async def _voer_deelstappen_uit(
    db: AsyncSession, user_id: int, tenant_id: int, scope: str
) -> tuple[dict[str, int], list[str]]:
    """Gesprekken en overige persoonsgegevens wissen: elke deelstap in een eigen savepoint.

    Geeft (aantallen per stap, namen van mislukte stappen). Een deelstap die faalt stopt de purge
    niet maar wordt NIET stil geslikt: zij staat in de lijst (antwoord + auditregel) en in een
    WARNING. De stappen worden op aanroepmoment opgezocht (niet als module-constante), zodat een
    test een deelstap kan vervangen.
    """
    aantallen: dict[str, int] = {}
    mislukt: list[str] = []
    stappen = [
        ("cva_conversations", ("all", "messages"), _wis_cva_conversations),
        ("memory_items", ("all", "profile"), _wis_memory_items),
        ("ai_decisions", ("all", "profile"), _wis_ai_decisions),
        ("agentic_tasks", ("all", "profile"), _wis_agentic_tasks),
        ("gamification", ("all", "profile"), _wis_gamification),
        ("profiling_opt_outs", ("all", "profile"), _wis_profiling_opt_outs),
    ]
    for naam, scopes, wis in stappen:
        if scope not in scopes:
            continue
        try:
            async with db.begin_nested():
                aantallen[f"{naam}_deleted"] = await wis(db, user_id, tenant_id)
        except Exception as stap_exc:
            mislukt.append(naam)
            logger.warning(
                "gdpr_purge_deelstap_mislukt: stap=%s, user_id=%s, tenant_id=%s: %s: %s",
                naam,
                user_id,
                tenant_id,
                type(stap_exc).__name__,
                stap_exc,
                exc_info=True,
            )
    return aantallen, mislukt


class PurgeDeelstappenMislukt(RuntimeError):
    """Een of meer deelstappen van de purge zijn mislukt; de actor probeert opnieuw."""


async def _termijn_is_verstreken(user_id: int, tenant_id: int) -> bool:
    """Staat deze gebruiker nog gepland voor wissing EN is de termijn van 30 dagen om?

    Gelezen op het moment van uitvoeren (niet op het moment van inplannen): is de aanvraag
    tussentijds ingetrokken, dan wordt er niets gewist.
    """
    from datetime import datetime, timezone

    from sqlalchemy import text

    from src.core.database.session import get_db_session
    from src.core.database.tenant_query_filter import TenantFilterBypass
    from src.core.governance.avg_tenant_export import export_aangeboden
    from src.core.governance.avg_wissing_planning import alle_delete_all_termijnen

    async with get_db_session() as db:
        with TenantFilterBypass():
            gepland = (
                await db.execute(
                    text(
                        "SELECT deletion_scheduled_for FROM users "
                        "WHERE id = :uid AND tenant_id = :tid"
                    ),
                    {"uid": user_id, "tid": tenant_id},
                )
            ).scalar_one_or_none()
            if gepland is None or gepland > datetime.now(timezone.utc):
                return False
            # Eerst export (besluit Rakesh 2026-10-12): hoort deze gebruiker bij een tenantbrede
            # wissing, dan wacht de purge tot er een export is aangeboden. Een losse
            # medewerker-wissing heeft een eigen termijn en wacht nergens op.
            if gepland in await alle_delete_all_termijnen(db, tenant_id):
                return await export_aangeboden(db, tenant_id)
    return True


async def _run_purge_en_controleer(
    user_id: int, tenant_id: int, scope: str, alleen_indien_vervallen: bool = False
) -> dict[str, object]:
    """Draai de purge; faalt een deelstap, dan een exceptie zodat Dramatiq opnieuw probeert.

    De purge is idempotent, dus opnieuw proberen is veilig. Zonder deze exceptie zag Dramatiq een
    geslaagde taak en bleven de persoonsgegevens staan met alleen een WARNING als signaal.
    """
    if alleen_indien_vervallen and not await _termijn_is_verstreken(user_id, tenant_id):
        return {"overgeslagen": "termijn niet verstreken of aanvraag ingetrokken", "mislukte_deelstappen": []}
    resultaat = await _run_purge(user_id, tenant_id, scope)
    mislukt = resultaat.get("mislukte_deelstappen")
    if mislukt:
        raise PurgeDeelstappenMislukt(
            f"purge user_id={user_id} tenant_id={tenant_id}: deelstappen mislukt: {mislukt}"
        )
    return resultaat


async def _run_purge(
    user_id: int, tenant_id: int, scope: str
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Core purge logic: anonymize user data within tenant boundary.

    Idempotent: re-running on already-purged data is safe.
    """
    from datetime import datetime, timezone

    from sqlalchemy import text, update

    from src.core.database.session import get_db_session
    from src.core.database.tenant_query_filter import TenantFilterBypass
    from src.core.models.rbac_models import User
    from src.core.shared.tenant_beheerders import is_laatste_beheerder
    from src.core.utils.best_effort import best_effort

    logger.info(
        "gdpr_purge_started: user_id=%s, tenant_id=%s, scope=%s",
        user_id,
        tenant_id,
        scope,
    )

    results: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
        "user_id": user_id,
        "tenant_id": tenant_id,
        "scope": scope,
    }

    was_laatste_beheerder = False
    mislukte_deelstappen: list[str] = []
    results["mislukte_deelstappen"] = mislukte_deelstappen
    try:
        async with get_db_session() as db:
            with TenantFilterBypass():
                # VOOR elke wijziging meten of dit de laatste beheerder is (alleen lezen; dezelfde
                # telling als LAST_ADMIN). De purge is wettelijk en gaat altijd door; scope
                # `messages` laat de gebruiker staan, dus daar verandert de beheerderstelling niet.
                if scope in ("all", "profile"):
                    async with best_effort("laatste-beheerder meting voor purge", db_session=db):
                        was_laatste_beheerder = await is_laatste_beheerder(
                            db, tenant_id, user_id
                        )

                # Scope "all" or "messages": anonymize conversation content
                if scope in ("all", "messages"):
                    msg_result = await db.execute(
                        text(
                            """
                            UPDATE conversation_messages
                            SET content = '[GDPR PURGED]'
                            WHERE conversation_id IN (
                                SELECT id FROM conversations
                                WHERE user_id = :user_id AND tenant_id = :tenant_id
                            )
                            """
                        ),
                        {"user_id": user_id, "tenant_id": tenant_id},
                    )
                    results["messages_anonymized"] = getattr(msg_result, "rowcount", 0)

                    conv_result = await db.execute(
                        text(
                            """
                            UPDATE conversations
                            SET title = '[GDPR PURGED]'
                            WHERE user_id = :user_id AND tenant_id = :tenant_id
                            """
                        ),
                        {"user_id": user_id, "tenant_id": tenant_id},
                    )
                    results["conversations_anonymized"] = getattr(conv_result, "rowcount", 0)

                aantallen, mislukt = await _voer_deelstappen_uit(db, user_id, tenant_id, scope)
                results.update(aantallen)
                mislukte_deelstappen.extend(mislukt)

                # Scope "all" or "profile": anonymize user profile
                if scope in ("all", "profile"):
                    user_result = await db.execute(
                        update(User)
                        .where(
                            User.id == user_id,
                            User.tenant_id == tenant_id,
                        )
                        .values(
                            email=f"purged_{user_id}@purged.invalid",
                            hashed_password="[PURGED]",
                            is_active=False,
                            deleted_at=datetime.now(timezone.utc),
                            # NULL en geen vaste tekst: `ix_users_stripe_customer_id` is UNIQUE, dus de
                            # tweede gepurgede gebruiker kreeg een UniqueViolation (gemeten 2026-10-12).
                            stripe_customer_id=None,
                            last_login=None,
                            preferred_locale=None,
                            preferred_timezone=None,
                        )
                    )
                    results["user_profile_anonymized"] = getattr(user_result, "rowcount", 0)

                # De termijn pas wissen als ALLE deelstappen slaagden: anders ziet de retry (en de
                # planner van morgen) een gebruiker zonder termijn en blijft de rest staan.
                if scope in ("all", "profile") and not mislukte_deelstappen:
                    await db.execute(
                        update(User)
                        .where(User.id == user_id, User.tenant_id == tenant_id)
                        .values(deletion_scheduled_for=None)
                    )

            # get_db_session() commits on successful exit; no explicit commit here.

        # Audit log is best-effort: must not fail the primary purge.
        try:
            async with get_db_session() as audit_db:
                from src.core.database.tenant_query_filter import TenantFilterBypass
                from src.core.governance.audit import AuditService

                with TenantFilterBypass():
                    async with best_effort("gdpr purge actor", db_session=audit_db):
                        await AuditService.log_action(
                            tenant_id=tenant_id,
                            action="gdpr_purge_executed",
                            resource=f"user_data:{user_id}",
                            user_id=user_id,
                            details={"scope": scope, **results},
                            session=audit_db,
                            event_type="gdpr_purge",
                            threat_level="warning",
                            client_ip="system",
                            endpoint="gdpr_purge_actor",
                            description=(
                                f"GDPR purge completed for user {user_id} in tenant {tenant_id}"
                                if not mislukte_deelstappen
                                else f"GDPR purge PARTIAL for user {user_id} in tenant {tenant_id}: "
                                f"failed substeps {mislukte_deelstappen}"
                            ),
                        )
        except Exception as audit_exc:
            logger.warning(
                "gdpr_purge_audit_failed: %s: %s",
                type(audit_exc).__name__,
                audit_exc,
            )

        if was_laatste_beheerder:
            # De purge zelf is al klaar: een mislukte melding mag hem niet als mislukt laten lijken
            # en dus niet de hele purge opnieuw laten lopen.
            try:
                await meld_tenant_zonder_beheerder(tenant_id)
            except Exception as melding_exc:
                logger.warning(
                    "gdpr_purge_beheerdermelding_failed: %s: %s",
                    type(melding_exc).__name__,
                    melding_exc,
                    exc_info=True,
                )

        logger.info(
            "gdpr_purge_completed: user_id=%s, tenant_id=%s, scope=%s, results=%s",
            user_id,
            tenant_id,
            scope,
            results,
        )
        return results

    except Exception as exc:
        logger.error(
            "gdpr_purge_failed: %s: %s",
            type(exc).__name__,
            exc,
            exc_info=True,
            extra={"user_id": user_id, "tenant_id": tenant_id},
        )
        raise


# Conditional Dramatiq registration (same pattern as src/workers/actors.py)
try:
    from src.core.tasks.dramatiq_broker import _DRAMATIQ_AVAILABLE
except ImportError:
    # Alleen een ontbrekende dramatiq (tests). Een ontbrekende REDIS_URL is een RuntimeError en hoort NIET stil
    # een nep-actor op te leveren: dan zou de AVG-verwijdertaak zonder fout nooit draaien (Gate 2, OP-13).
    _DRAMATIQ_AVAILABLE = False

if _DRAMATIQ_AVAILABLE:
    from src.core.tasks.dramatiq_broker import workflow_actor

    @workflow_actor(
        queue_name="maintenance",
        max_retries=3,
        time_limit=300_000,  # 5 minutes
    )
    async def purge_user_data(
        user_id: int, tenant_id: int, scope: str = "all", alleen_indien_vervallen: bool = False
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """GDPR purge actor: anonymizes user data for a specific user+tenant.

        KRITISCH: tenant_id-filter verplicht op ALLE queries (ADR-005).
        Anonimisering i.p.v. hard delete -- audit trail bewaarplicht.
        """
        return await _run_purge_en_controleer(user_id, tenant_id, scope, alleen_indien_vervallen)

else:
    # Testing mode: dummy sender for test patching.
    class _DummySender:
        def send(self, *args: Any, **kwargs: Any) -> Any:  # TODO(TYPE): replace with concrete type
            logger.debug(
                "Dummy purge_user_data.send called: args=%s, kwargs=%s",
                args,
                kwargs,
            )
            return None

    purge_user_data = _DummySender()  # pyright: ignore
