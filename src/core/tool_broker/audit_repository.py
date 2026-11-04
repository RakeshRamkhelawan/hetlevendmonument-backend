"""Database repository for tool execution audit logs."""

import hashlib
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import desc, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.governance.models import ToolAuditLog
from src.core.tool_broker.audit_utils import (
    compute_audit_hash,
    compute_output_hash,
    sanitize_tool_output,
)

#: Eerste getal van het slot dat de toolauditketen van een klant serialiseert; het tweede getal
#: is de klant (twee sleutels van elk 32 bit, zoals `hr_termijn_tasks.LOCK_RUIMTE`). Bewust de
#: TWEESLEUTELVORM van `pg_advisory_xact_lock`: Postgres houdt die in een eigen sleutelruimte,
#: apart van de enkelvoudige vorm waarmee `AuditService.log_event` de `audit_logs`-keten van
#: dezelfde klant afsluit (sleutel = klantnummer). Zo blokkeren de twee ketens van een klant
#: elkaar niet, terwijl elke keten wel op zichzelf serialiseert. 7104 is al van de HR-termijnen.
TOOL_AUDIT_LOCK_RUIMTE = 7201

#: De lengte van de kolommen `tool_audit_logs.tool_name` en `.agent_id` (varchar(255), in tekens).
KOLOM_LENGTE = 255
_DIGEST_LENGTE = 64


def begrens_kolomwaarde(waarde: str) -> str:
    """Maak een waarde die in een varchar(255)-kolom past, deterministisch en zonder botsing.

    Gate 2 S3: `tool_name` komt uit een taalmodel en `agent_id` van de aanroeper; beide waren
    onbegrensd. Een naam van 300 tekens gaf `StringDataRightTruncationError` en dus GEEN auditregel.

    Gekozen: een te lange waarde wordt een voorvoegsel plus `~` plus de sha256 van de HELE waarde
    (190 + 1 + 64 = 255 tekens), geen kale afkapping. Bij kaal afkappen vallen twee verschillende
    lange namen met dezelfde kop samen tot een regel die ze niet meer uit elkaar houdt; en het
    logboek is er juist om te kunnen zeggen WELKE aanroep het was. De digest maakt de afgekapte
    waarde ook terug te vinden voor wie het origineel heeft. Waarden die passen blijven ongewijzigd.
    """
    if len(waarde) <= KOLOM_LENGTE:
        return waarde
    digest = hashlib.sha256(waarde.encode("utf-8")).hexdigest()[:_DIGEST_LENGTE]
    return waarde[: KOLOM_LENGTE - _DIGEST_LENGTE - 1] + "~" + digest


class ToolAuditRepository:
    """Database repository for tool execution audit logs."""

    def __init__(self, db: AsyncSession, tenant_id: int) -> None:
        self.db = db
        self.tenant_id = tenant_id

    async def log_execution(
        self,
        agent_id: str,
        tool_name: str,
        risk_level: str,
        tool_input: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        tool_output: dict[str, Any] | None,  # TODO(TYPE): replace Any with concrete type
        status: str,
        duration_seconds: float,
        task_id: str | None = None,
        error_detail: str | None = None,
        hitl_ticket_ref: str | None = None,
        hitl_approved_by: str | None = None,
    ) -> ToolAuditLog:
        """Log a tool execution to the audit trail.

        `tool_input` wordt hier NIET geredigeerd, en dat is opzet. De pseudonimisering gebeurt
        op een enkel punt in `ToolBrokerService.execute_tool`
        (`tool_broker/redaction.py::redact_for_publication`), voordat de payload uiteen gaat
        naar de event bus, de leeropslag en deze auditregel. Hier nog eens redigeren zou de
        digests zelf hashen -- de bewerking is niet idempotent.

        Dat er geen enkele aanroeper een rauwe payload meegeeft, wordt afgedwongen door
        `tests/architecture/test_tool_payloads_are_pseudonymised.py`.

        OP-29 (opgelost, 2026-08-26): `tool_output`/`error_detail` komen hier al geredigeerd
        binnen -- `service.py::_write_audit` berekent `publish_result`/`publish_error` via
        `redaction.py::safe_digest_result`/`safe_value_digest` VOORDAT deze methode wordt
        aangeroepen. `sanitize_tool_output` hieronder draait dus over een reeds gehashte digest,
        niet over de rauwe modeloutput; de BLOCKLIST-op-sleutelnamen-zwakte die deze functie
        heeft (`{"employee_id": "<e-mailadres>"}` glipt erdoor) is voor de enige aanroeper van
        deze methode niet meer bereikbaar. `sanitize_tool_output` blijft als tweede, goedkope
        laag staan op een waarde die al veilig is -- niet omdat hij nog nodig is voor DEZE
        aanroeper.
        """
        # EEN plek (Gate 2 S3): hier, voor het hashen. De hash gaat zo over precies de waarde die
        # wordt opgeslagen, en een te lange naam geeft geen database-fout meer.
        agent_id = begrens_kolomwaarde(agent_id)
        tool_name = begrens_kolomwaarde(tool_name)

        output_hash = compute_output_hash(tool_output) if tool_output else None
        sanitized_output = None
        if tool_output:
            sanitized_output = sanitize_tool_output(tool_output)

        # Brief 2026-10-22 (bundel logboekketens): de vorige hash, de tijdstempel, de hash en de
        # schrijfactie horen in EEN transactie onder een slot per klant. Eerst las de aanroeper de
        # vorige hash in een aparte aanroep, zonder slot: twee gelijktijdige toolacties lazen dezelfde
        # vorige hash en SPLITSTEN de keten. Het slot geldt tot de commit hieronder.
        await self.db.execute(
            text("SELECT pg_advisory_xact_lock(:ruimte, :tenant)"),
            {"ruimte": TOOL_AUDIT_LOCK_RUIMTE, "tenant": self.tenant_id},
        )
        # DE TIJDSTEMPEL NA HET SLOT (zelfde reden als ADR-036 OP-110): binnen het slot is elke
        # volgende tijdstempel later dan die van de vorige schrijver, dus tijd en keten lopen gelijk.
        # De tijdstempel zit in de hash en wordt hier VOOR het hashen gezet; wat er gehasht wordt
        # is niet veranderd.
        timestamp = datetime.now(timezone.utc)
        previous_hash = await self.get_last_audit_hash()
        audit_hash = compute_audit_hash(
            tenant_id=self.tenant_id,
            agent_id=agent_id,
            tool_name=tool_name,
            timestamp=timestamp,
            status=status,
            output_hash=output_hash,
            previous_hash=previous_hash,
            tool_input=tool_input,
            task_id=task_id,
            error_detail=error_detail,
            hitl_ticket_ref=hitl_ticket_ref,
            hitl_approved_by=hitl_approved_by,
        )

        log = ToolAuditLog(
            tenant_id=self.tenant_id,
            agent_id=agent_id,
            task_id=task_id,
            tool_name=tool_name,
            risk_level=risk_level,
            tool_input=tool_input,
            status=status,
            error_detail=error_detail,
            output_hash=output_hash,
            previous_hash=previous_hash,
            audit_hash=audit_hash,
            hitl_ticket_ref=hitl_ticket_ref,
            hitl_approved_by=hitl_approved_by,
            duration_seconds=duration_seconds,
            tool_output=sanitized_output,
            timestamp=timestamp,
        )

        self.db.add(log)
        await self.db.commit()
        await self.db.refresh(log)
        return log

    async def get_last_audit_hash(self) -> str | None:
        """Get audit hash of most recent log for THIS TENANT's chain.

        Ordening op tijdstempel EN id: twee regels met dezelfde tijdstempel hebben anders een
        niet-vastliggende volgorde. Dezelfde volgorde als `verify_chain_integrity`.
        """
        result = await self.db.execute(
            select(ToolAuditLog.audit_hash)
            .where(ToolAuditLog.tenant_id == self.tenant_id)
            .order_by(desc(ToolAuditLog.timestamp), desc(ToolAuditLog.id))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_logs(self, limit: int = 50, offset: int = 0) -> list[ToolAuditLog]:
        """Get a tenant's tool-audit logs, newest first (paginated, tenant-isolated)."""
        result = await self.db.execute(
            select(ToolAuditLog)
            .where(ToolAuditLog.tenant_id == self.tenant_id)
            .order_by(desc(ToolAuditLog.timestamp))
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def count_logs(self) -> int:
        """Count a tenant's tool-audit logs (tenant-isolated)."""
        from sqlalchemy import func

        result = await self.db.execute(
            select(func.count())
            .select_from(ToolAuditLog)
            .where(ToolAuditLog.tenant_id == self.tenant_id)
        )
        return int(result.scalar_one() or 0)

    async def get_logs_by_agent(self, agent_id: str, limit: int = 50) -> list[ToolAuditLog]:
        """Get recent audit logs for an agent (tenant-isolated)."""
        result = await self.db.execute(
            select(ToolAuditLog)
            .where(
                ToolAuditLog.tenant_id == self.tenant_id,
                ToolAuditLog.agent_id == agent_id,
            )
            .order_by(desc(ToolAuditLog.timestamp))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_logs_by_tool(self, tool_name: str, limit: int = 50) -> list[ToolAuditLog]:
        """Get recent executions of a specific tool (tenant-isolated)."""
        result = await self.db.execute(
            select(ToolAuditLog)
            .where(
                ToolAuditLog.tenant_id == self.tenant_id,
                ToolAuditLog.tool_name == tool_name,
            )
            .order_by(desc(ToolAuditLog.timestamp))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def verify_chain_integrity(self) -> bool:
        """Verify the audit log chain is unbroken for THIS TENANT."""
        result = await self.db.execute(
            select(ToolAuditLog)
            .where(ToolAuditLog.tenant_id == self.tenant_id)
            .order_by(ToolAuditLog.timestamp.asc(), ToolAuditLog.id.asc())
        )
        logs = list(result.scalars().all())

        if not logs:
            return True

        if logs[0].previous_hash not in (None, "genesis"):
            return False

        for i in range(1, len(logs)):
            if logs[i].previous_hash != logs[i - 1].audit_hash:
                return False

        return True

    async def get_blocked_tools_count(self) -> int:
        """Count blocked tool execution attempts (tenant-isolated)."""
        result = await self.db.execute(
            select(ToolAuditLog).where(
                ToolAuditLog.tenant_id == self.tenant_id,
                ToolAuditLog.status == "blocked",
            )
        )
        return len(result.scalars().all())
