"""
Dramatiq actor for hash-chained audit writes from hot paths without a DB session.

GOV-002 (ADR-031, ADR-019, ADR-006): some security-event callers (token revocation,
rate-limiting, session dashboards) run in Redis-only hot paths with no AsyncSession in
scope. Rather than threading a DB session into those hot paths (extra latency + coupling
on security-critical code), the write is enqueued via the existing Dramatiq/Redis broker
(ADR-006) and applied asynchronously through the canonical hash-chain path. Ordering and
hash-chain integrity are preserved because governance/audit.py::AuditService.log_action()
already serializes writes per tenant via pg_advisory_xact_lock.
"""

import logging
from typing import Any

from src.core.tasks.dramatiq_broker import workflow_actor

from src.core.tasks.eigen_loop import SessieFabriek, draai_in_eigen_loop

logger = logging.getLogger(__name__)


async def _write_audit_log(
    sessie_fabriek: SessieFabriek,
    tenant_id: int,
    action: str,
    resource: str,
    user_id: int | None,
    details: dict[str, Any] | None,  # TODO(TYPE): replace Any with concrete type
    threat_level: str,
    client_ip: str,
    endpoint: str,
    description: str | None,
) -> None:
    from src.core.database.bypass_session import adopt_tenant  # noqa: PLC0415
    from src.core.governance.audit import AuditService  # noqa: PLC0415

    # Eigen poolloze engine per run (zie `eigen_loop`): de gedeelde, gepoolde engine hangt na de
    # eerste `asyncio.run` aan een gesloten loop en laat de tweede run falen.
    async with sessie_fabriek() as session, adopt_tenant(session, tenant_id):
        # De klant wordt AANGENOMEN, en dit is de eerlijke reden (ADR-036 OP-153).
        #
        # Deze actor draait in een Dramatiq-worker, buiten elk verzoek, dus de ContextVar
        # is leeg. Gemeten 2026-09-16 op de ketendatabase: `AuditService.log_action`
        # schrijft uitsluitend in `audit_logs`, en die tabel heeft `relrowsecurity = f`
        # en nul policies. VANDAAG is deze regel dus niet nodig.
        #
        # Hij staat er om twee redenen die wel gemeten zijn. Ten eerste neemt `log_action`
        # een `pg_advisory_xact_lock` op de klant; die klant hoort dan ook de context van
        # de transactie te zijn, anders is de serialisatie een toevallige afspraak in
        # plaats van een eigenschap. Ten tweede stelt reviewpunt D1 voor om `audit_logs`
        # alsnog een LEES-policy te geven (`USING (tenant_id IS NULL OR ...)` met
        # `WITH CHECK (true)`), omdat dat de tabel met de meeste persoonsgegevens is en
        # er geen tweede laag onder zit. Gaat dat door, dan is deze regel wel nodig.
        #
        # Een eerdere versie van dit comment zei dat `log_action` ook de ketenverankering
        # raakt. Dat was niet nagemeten en het klopt niet: de verankering is een hash IN
        # `audit_logs` zelf.
        #
        # De aanname staat hier BINNEN de coroutine, niet voor `asyncio.run()`. Een
        # ContextVar die buiten een `asyncio.run()` wordt gezet leeft in een kopie van de
        # context; dat is een gemeten valkuil in dit project.
        #
        # `tenant_id` is een parameter van de actor en komt van de verzendende hot path,
        # nooit uit gebruikersinvoer.
        await AuditService.log_action(
            tenant_id=tenant_id,
            action=action,
            resource=resource,
            user_id=user_id,
            details=details,
            session=session,
            threat_level=threat_level,
            client_ip=client_ip,
            endpoint=endpoint,
            description=description,
        )


@workflow_actor(queue_name="audit_queue")
def write_audit_log_task(
    tenant_id: int,
    action: str,
    resource: str,
    user_id: int | None = None,
    details: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    threat_level: str = "INFO",
    client_ip: str = "SYSTEM",
    endpoint: str = "INTERNAL",
    description: str | None = None,
) -> None:
    """Fire-and-forget hash-chained audit write. Failures are logged, never raised back
    to the enqueueing hot path (audit logging must not block the primary operation)."""
    try:
        draai_in_eigen_loop(
            lambda sessie_fabriek: _write_audit_log(
                sessie_fabriek,
                tenant_id=tenant_id,
                action=action,
                resource=resource,
                user_id=user_id,
                details=details,
                threat_level=threat_level,
                client_ip=client_ip,
                endpoint=endpoint,
                description=description,
            )
        )
    except Exception as e:
        logger.error(
            "write_audit_log_task failed for tenant %s action %s: %s: %s",
            tenant_id,
            action,
            type(e).__name__,
            e,
            exc_info=True,
        )
