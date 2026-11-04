"""
DSAR Service - GDPR Article 15, 17, 20 compliance.

Implements:
- Art. 15: Right of Access (audit trail)
- Art. 17: Right to Erasure (delete data)
- Art. 20: Right to Data Portability (export data)

Security:
- No cross-tenant access
- Admin approval required for hard delete
- Soft delete by default (30-day grace period)
- Full audit trail
"""

import importlib
import inspect
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, cast

from pydantic import BaseModel
from sqlalchemy import delete, select, text, update
from sqlalchemy.engine import CursorResult, RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.governance.audit import audit_rows_about_user
from src.core.governance.ketencontext import ketencontext
from src.core.governance.models import AuditLog
from src.core.models.rbac_models import User
from src.core.shared.tenant_beheerders import (
    AUDITACTIE_TENANT_ZONDER_BEHEERDER,
    is_laatste_beheerder,
)
from src.core.utils.best_effort import best_effort
from src.core.governance.audit_chain_key import mark_entry

logger = logging.getLogger(__name__)


def _coerce_user_id(user_id: str) -> int | str:
    """Convert user_id to int if it's a numeric string, otherwise return as-is.

    Tests use string IDs like 'user-123'. Production always passes numeric strings.
    """
    try:
        return int(str(user_id))
    except (ValueError, TypeError):
        return user_id


async def _maybe_await(value: Any) -> Any:  # TODO(TYPE): replace Any with concrete type
    """Await value if it is a coroutine (handles AsyncMock in tests)."""
    if inspect.iscoroutine(value):
        return await value
    return value


class DSARAuthorizationError(Exception):
    """Raised when DSAR request is not authorized."""

    pass


class DSARTenantIsolationError(Exception):
    """Raised when cross-tenant data access is attempted."""

    pass


class DSARNotFoundError(Exception):
    """Raised when user/tenant is not found."""

    pass


class DSARExportResult(BaseModel):
    """Result of DSAR data export (Art. 20)."""

    user_id: str
    tenant_id: int
    exported_at: datetime
    data: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    total_records: int


class DSARDeletionResult(BaseModel):
    """Result of DSAR data deletion (Art. 17)."""

    user_id: str
    tenant_id: int
    deleted_at: datetime
    delete_type: str  # "soft" or "hard"
    records_affected: dict[str, int]
    scheduled_purge_date: datetime | None


@dataclass
class DSARServiceConfig:
    """Configuration for DSAR Service."""

    soft_delete_grace_period_days: int = 30
    audit_retention_years: int = 7


class DSARService:
    """
    GDPR DSAR (Data Subject Access Request) service.

    Implements:
    - Art. 15: Right of Access (audit trail)
    - Art. 17: Right to Erasure (soft/hard delete)
    - Art. 20: Right to Data Portability (export)

    Security Features:
    - Tenant isolation enforced
    - Authorization checks (own data or admin)
    - Audit logging for all actions
    - Soft delete with configurable grace period
    - Hard delete requires admin approval

    Example:
        service = DSARService(db)

        # Export own data (Art. 20)
        result = await service.export_user_data(
            user_id="123",
            tenant_id=1,
            requested_by_user_id="123",
            is_admin=False,
        )

        # Soft delete (Art. 17) - marks inactive, 30-day grace
        result = await service.delete_user_data(
            user_id="123",
            tenant_id=1,
            hard_delete=False,
            requested_by_user_id="123",
            is_admin=False,
        )

        # Hard delete - requires admin
        result = await service.delete_user_data(
            user_id="123",
            tenant_id=1,
            hard_delete=True,
            requested_by_user_id="admin_123",
            is_admin=True,
        )
    """

    DEFAULT_GRACE_PERIOD_DAYS = 30

    def __init__(
        self,
        db: AsyncSession,
        config: DSARServiceConfig | None = None,
    ):
        """
        Initialize DSAR Service.

        Args:
            db: SQLAlchemy async session
            config: Optional configuration override
        """
        self._db = db
        self._config = config or DSARServiceConfig()

    def _authorize(
        self,
        target_user_id: str,
        requesting_user_id: str,
        is_admin: bool,
    ) -> None:
        """
        Authorize DSAR request.

        Users can only access their own data unless they are admin.

        Args:
            target_user_id: ID of data subject
            requesting_user_id: ID of requester
            is_admin: Whether requester has admin privileges

        Raises:
            DSARAuthorizationError: If not authorized
        """
        if requesting_user_id != target_user_id and not is_admin:
            raise DSARAuthorizationError(
                f"User {requesting_user_id} is not authorized to access "
                f"data of user {target_user_id}. "
                f"Only the data subject or an admin can access this data."
            )

    async def _verify_tenant_isolation(
        self,
        user_id: str,
        tenant_id: int,
    ) -> User:
        """
        Verify user belongs to tenant (anti cross-tenant leak).

        Args:
            user_id: User ID to verify
            tenant_id: Expected tenant ID

        Returns:
            User object if verified

        Raises:
            DSARTenantIsolationError: If user not in tenant
            DSARNotFoundError: If user not found
        """
        result = await self._db.execute(
            select(User).where(
                User.id == _coerce_user_id(user_id),
                User.tenant_id == tenant_id,
            )
        )
        user = await _maybe_await(result.scalar_one_or_none())

        if not user:
            raise DSARTenantIsolationError(
                f"User {user_id} not found in tenant {tenant_id}. "
                f"Cross-tenant access is not permitted."
            )

        return cast(User, user)

    async def _get_user(self, user_id: str) -> User | None:
        """Get user by ID."""
        result = await self._db.execute(select(User).where(User.id == _coerce_user_id(user_id)))
        return result.scalar_one_or_none()

    async def _create_audit_log(
        self,
        tenant_id: int,
        user_id: int | None,
        action: str,
        resource: str,
        details: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        threat_level: str,
        endpoint: str,
        description: str,
        event_metadata: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """Create audit log entry. Best-effort: never raises to caller."""
        async with best_effort(f"dsar audit log ({action})", db_session=self._db):
            audit_entry = AuditLog(
                tenant_id=tenant_id,
                user_id=user_id,
                action=action,
                resource=resource,
                details=details,
                event_type="gdpr_dsar",
                threat_level=threat_level,
                client_ip="unknown",
                endpoint=endpoint,
                description=description,
                event_metadata=event_metadata,
            )
            # ADR-019: SHA-256 hash chain voor tamper-evidence.
            # NOTE: de tijdstempel wordt EXPLICIET gezet (niet via server_default) zodat de hash
            # reproduceerbaar is bij herverificatie -- PostgreSQL bewaart microseconden. Dat
            # gebeurt hieronder NA het slot.
            try:
                # Advisory lock serializes chain writes per tenant -- prevents forked chain.
                await self._db.execute(
                    text("SELECT pg_advisory_xact_lock(:key)"), {"key": tenant_id}
                )
                # DE TIJDSTEMPEL NA HET SLOT (ADR-036 OP-110). De schrijvers ketenen aan de laatste rij
                # ORDER BY timestamp DESC, id DESC en de verifier loopt de keten op diezelfde volgorde. Een
                # tijdstempel die VOOR het slot wordt gekozen, kan na die van een latere schrijver worden
                # geketend: op tijd VOOR hem, in de keten ACHTER hem, en dan meldt verify_chain manipulatie
                # op een gave keten. Binnen het slot is elke tijdstempel later dan die van de vorige
                # schrijver. De tijdstempel zit in de hash en staat er hier VOOR het hashen; wat er
                # gehasht wordt is niet veranderd. Zelfde vorm als AuditService.log_event.
                audit_entry.timestamp = datetime.now(timezone.utc)
                async with self._db.begin_nested():  # SAVEPOINT -- keeps outer tx alive on error
                    # lazy import -- avoids circular dep at module load
                    from src.core.governance.hash_chain import HashChainVerifier

                    async with ketencontext(self._db, tenant_id):
                        prev_result = await self._db.execute(
                            select(AuditLog.audit_hash)
                            .where(
                                AuditLog.tenant_id == tenant_id,
                                AuditLog.audit_hash.isnot(None),
                            )
                            .order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
                            .limit(1)
                        )
                        _previous_hash: str | None = prev_result.scalar_one_or_none()
                    _verifier = HashChainVerifier(db_session=self._db)
                    audit_entry.previous_hash = _previous_hash
                    # Markeer WELK algoritme deze rij gebruikt, VOOR het hashen (ADR-036 OP-120).
                    # `mark_entry` schakelt alleen om als er een echte sleutel is; zonder sleutel blijft
                    # de rij op legacy SHA-256 in plaats van hard te falen en stil ongehasht te landen.
                    mark_entry(audit_entry)
                    audit_entry.audit_hash = _verifier._compute_hash(audit_entry, _previous_hash)
            except Exception as _e:
                logger.error(
                    "dsar: hash chain populatie mislukt voor tenant %s: %s: %s",
                    tenant_id,
                    type(_e).__name__,
                    _e,
                    exc_info=True,
                )
                # Audit log wordt alsnog weggeschreven zonder hash (degraded mode)
            # Een regel ZONDER keten (de ketenlookup faalde al voor het slot) heeft hier nog geen
            # tijdstempel. Die hoort niet in een keten en hoeft dus niet na een slot.
            if audit_entry.timestamp is None:
                audit_entry.timestamp = datetime.now(timezone.utc)
            self._db.add(audit_entry)
            await self._db.commit()

    async def _is_laatste_beheerder(self, tenant_id: int, user_id: str) -> bool:
        """Is deze gebruiker de enige actieve beheerder van de tenant? Faalt de meting: False.

        Alleen lezen; de wissing gaat in elk geval door. Zelfde telling als LAST_ADMIN.
        """
        gebruiker = _coerce_user_id(user_id)
        if not isinstance(gebruiker, int):
            return False  # geen numeriek id (alleen in tests): kan geen beheerder van een tenant zijn

        resultaat = False
        async with best_effort("laatste-beheerder meting voor AVG-wissing", db_session=self._db):
            resultaat = await is_laatste_beheerder(self._db, tenant_id, gebruiker)
        return resultaat

    async def _meld_als_laatste_beheerder(self, tenant_id: int, was_laatste: bool) -> None:
        """WARNING plus auditregel als de gewiste de laatste beheerder was; anders niets.

        Alleen het tenant-id, geen persoonsgegevens: de gewiste persoon staat er bewust niet in.
        """
        if not was_laatste:
            return
        logger.warning(
            "%s: tenant %s heeft na een AVG-wissing geen actieve beheerder meer; geef de klant een "
            "nieuwe beheerder",
            AUDITACTIE_TENANT_ZONDER_BEHEERDER,
            tenant_id,
        )
        await self._create_audit_log(
            tenant_id=tenant_id,
            user_id=None,
            action=AUDITACTIE_TENANT_ZONDER_BEHEERDER,
            resource=f"tenant:{tenant_id}",
            details={"tenant_id": tenant_id, "reden": "avg_wissing_laatste_beheerder"},
            threat_level="warning",
            endpoint="/api/gdpr/delete",
            description=f"Tenant {tenant_id} heeft na een AVG-wissing geen actieve beheerder meer",
            event_metadata={"dsar_action": "delete"},
        )

    async def _delete_agentic_tasks(self, tenant_id: int, user_id: str) -> int:
        """Physically delete a user's agentic_tasks (tenant-scoped). GDPR-A17-004.

        agentic_tasks has no is_active column, so erasure is physical in both soft and
        hard mode -- consistent with how CVA conversations are handled.
        """
        try:
            from src.domains.tasks.models import Task

            # begin_nested so a failure rolls back the savepoint and does not leave the
            # transaction in an aborted state before the later delete(User) + commit.
            async with self._db.begin_nested():
                result = await self._db.execute(
                    delete(Task).where(
                        Task.tenant_id == tenant_id,
                        Task.created_by == _coerce_user_id(user_id),
                    )
                )
                return cast(CursorResult[RowMapping], result).rowcount or 0
        except Exception as e:
            logger.error(
                "dsar: agentic_tasks delete failed for user %s: %s: %s",
                user_id,
                type(e).__name__,
                e,
                exc_info=True,
            )
            return 0

    async def _purge_memory_items(self, tenant_id: int, user_id: str) -> int:
        """Physically delete a user's memory_items (tenant-scoped). AUDIT-004 / Art. 17.

        memory_items.content_embedding is a non-anonymisable derivative of
        personal data, so erasure must be a physical DELETE in BOTH soft and
        hard mode -- consistent with CVA conversations and agentic_tasks
        (GDPR-A17-004). Anonymisation is impossible for embeddings; only hard
        DELETE satisfies Art. 17 for Twin memory. One DELETE purges the row
        and its embedding column together (no separate vector store exists).
        """
        try:
            # importlib avoids direct ImportFrom (DSM boundary governance -> agent_runtime)
            memory_models = importlib.import_module("src.domains.memory.models")
            memory_item = memory_models.MemoryItem

            # begin_nested so a failure rolls back the savepoint and does not leave the
            # transaction in an aborted state before the later delete(User) + commit.
            async with self._db.begin_nested():
                result = await self._db.execute(
                    delete(memory_item).where(
                        memory_item.tenant_id == tenant_id,
                        memory_item.user_id == _coerce_user_id(user_id),
                    )
                )
                return cast(CursorResult[RowMapping], result).rowcount or 0
        except Exception as e:
            logger.error(
                "dsar: memory_items purge failed for user %s: %s: %s",
                user_id,
                type(e).__name__,
                e,
                exc_info=True,
            )
            return 0

    async def _clear_copilot_sessions(self, tenant_id: int, user_id: str) -> int:
        """Clear a user's copilot Redis sessions (best-effort). GDPR-A17-004.

        Never fails the DSAR delete on a Redis outage; logs with exc_info.
        """
        try:
            # importlib avoids direct ImportFrom (DSM boundary governance -> agent_runtime)
            conv_mod = importlib.import_module("src.core.copilot.conversation_memory")
            ConversationMemory = conv_mod.ConversationMemory
            from src.core.shared.redis_client import get_redis

            redis = await get_redis()
            memory = ConversationMemory(redis)
            cleared = await memory.clear_user_sessions(tenant_id, int(_coerce_user_id(user_id)))
            # int(): ConversationMemory komt via importlib binnen (zie hierboven) en is
            # daardoor Any, dus het aantal is niet bewijsbaar een int. Een TYPE_CHECKING-
            # import zou dat wel oplossen maar is precies de ImportFrom die de
            # DSM-grens governance -> agent_runtime verbiedt.
            return int(cleared)
        except Exception as e:
            logger.error(
                "dsar: copilot session clear failed for user %s: %s: %s",
                user_id,
                type(e).__name__,
                e,
                exc_info=True,
            )
            return 0

    async def export_user_data(
        self,
        user_id: str,
        tenant_id: int,
        requested_by_user_id: str | None = None,
        is_admin: bool = False,
    ) -> DSARExportResult:
        """
        Export all data for a user (GDPR Art. 20 - Right to Data Portability).

        Args:
            user_id: Data subject ID
            tenant_id: Tenant context
            requested_by_user_id: Who requested the export (defaults to user_id)
            is_admin: Whether requester is admin

        Returns:
            DSARExportResult with all user data

        Raises:
            DSARAuthorizationError: If not authorized
            DSARTenantIsolationError: If cross-tenant access attempted
        """
        exported_at = datetime.now(timezone.utc)
        requester = requested_by_user_id or user_id

        # Authorize
        self._authorize(user_id, requester, is_admin)

        # Verify tenant isolation
        user = await self._verify_tenant_isolation(user_id, tenant_id)

        # Collect data from all domains
        data: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        total_records = 0

        # 1. User profile
        data["user_profile"] = [
            {
                "id": str(user.id),
                "email": user.email,
                "is_active": user.is_active,
                "created_at": (user.created_at.isoformat() if user.created_at else None),
                "last_login": (
                    user.last_login.isoformat()
                    if hasattr(user, "last_login") and user.last_login
                    else None
                ),
            }
        ]
        total_records += 1

        # 2. Workflows (if exists)
        try:
            async with self._db.begin_nested():
                from src.core.workflow.models import C7Workflow as Workflow

                workflows_result = await self._db.execute(
                    select(Workflow).where(
                        Workflow.tenant_id == tenant_id,
                        Workflow.created_by == _coerce_user_id(user_id),
                    )
                )
                workflows = workflows_result.scalars().all()
                data["workflows"] = [
                    {
                        "id": str(w.id),
                        "name": w.name,
                        "created_at": (w.created_at.isoformat() if w.created_at else None),
                    }
                    for w in workflows
                ]
                total_records += len(workflows)
        except Exception:
            await self._db.rollback()
            data["workflows"] = []

        # 3. Agents (if exists) -- raw SQL avoids governance->agent_runtime import (ADR-034)
        try:
            agents_result = await self._db.execute(
                text("SELECT id, name, agent_type FROM agents WHERE tenant_id = :tenant_id"),
                {"tenant_id": tenant_id},
            )
            agent_rows = agents_result.mappings().all()
            data["agents"] = [
                {
                    "id": str(r["id"]),
                    "name": r["name"],
                    "agent_type": r["agent_type"],
                }
                for r in agent_rows
            ]
            total_records += len(agent_rows)
        except Exception as e:
            logger.error(
                "dsar: agent fetch failed for tenant %s: %s: %s",
                tenant_id,
                type(e).__name__,
                e,
                exc_info=True,
            )
            data["agents"] = []

        # 4. Audit logs (limited to 90 days for performance)
        audit_cutoff = datetime.now(timezone.utc) - timedelta(days=90)
        audit_result = await self._db.execute(
            select(AuditLog)
            .where(
                AuditLog.tenant_id == tenant_id,
                audit_rows_about_user(_coerce_user_id(user_id)),
                AuditLog.timestamp > audit_cutoff,
            )
            .order_by(AuditLog.timestamp.desc())
            .limit(1000)
        )
        audit_logs = audit_result.scalars().all()
        data["audit_logs"] = [
            {
                "id": log.id,
                "action": log.action,
                "timestamp": log.timestamp.isoformat(),
                "resource": log.resource,
            }
            for log in audit_logs
        ]
        total_records += len(audit_logs)

        # 5. Conversations (CVA)
        try:
            async with self._db.begin_nested():
                from src.core.conversations.models import CVAConversation

                conv_result = await self._db.execute(
                    select(CVAConversation).where(
                        CVAConversation.tenant_id == tenant_id,
                        CVAConversation.user_id == _coerce_user_id(user_id),
                    )
                )
                conversations = conv_result.scalars().all()
                data["conversations"] = [
                    {
                        "id": str(c.id),
                        "title": c.title if hasattr(c, "title") else None,
                        "created_at": (c.created_at.isoformat() if c.created_at else None),
                    }
                    for c in conversations
                ]
                total_records += len(conversations)
        except Exception:
            await self._db.rollback()
            data["conversations"] = []

        # 6. Cookie Consent preferences
        try:
            async with self._db.begin_nested():
                from src.core.governance.models import UserConsent

                consent_result = await self._db.execute(
                    select(UserConsent).where(
                        UserConsent.tenant_id == tenant_id,
                        UserConsent.user_id == str(user_id),
                    )
                )
                consents = consent_result.scalars().all()
                data["cookie_consents"] = [
                    {
                        "essential": c.essential,
                        "analytics": c.analytics,
                        "marketing": c.marketing,
                        "personalization": c.personalization,
                        "policy_version": c.policy_version,
                        "created_at": (c.created_at.isoformat() if c.created_at else None),
                        "updated_at": (c.updated_at.isoformat() if c.updated_at else None),
                    }
                    for c in consents
                ]
                total_records += len(consents)
        except Exception:
            await self._db.rollback()
            data["cookie_consents"] = []

        # 7. AI Decisions
        try:
            async with self._db.begin_nested():
                from src.core.governance.models import AIDecision

                decisions_result = await self._db.execute(
                    select(AIDecision).where(
                        AIDecision.tenant_id == tenant_id,
                        AIDecision.user_id == str(user_id),
                    )
                )
                decisions = decisions_result.scalars().all()
                data["ai_decisions"] = [
                    {
                        "id": d.id,
                        "agent_id": d.agent_id,
                        "decision_type": d.decision_type,
                        "explanation": d.explanation,
                        "created_at": (d.created_at.isoformat() if d.created_at else None),
                    }
                    for d in decisions
                ]
                total_records += len(decisions)
        except Exception:
            await self._db.rollback()
            data["ai_decisions"] = []

        # 8. Profiling Opt-outs
        try:
            async with self._db.begin_nested():
                from src.core.governance.models import UserProfilingOptOut

                optouts_result = await self._db.execute(
                    select(UserProfilingOptOut).where(
                        UserProfilingOptOut.tenant_id == tenant_id,
                        UserProfilingOptOut.user_id == str(user_id),
                    )
                )
                optouts = optouts_result.scalars().all()
                data["profiling_opt_outs"] = [
                    {
                        "profiling_type": o.profiling_type,
                        "opted_out": o.opted_out,
                        "created_at": (o.created_at.isoformat() if o.created_at else None),
                    }
                    for o in optouts
                ]
                total_records += len(optouts)
        except Exception:
            await self._db.rollback()
            data["profiling_opt_outs"] = []

        # 9. Gamification data
        try:
            async with self._db.begin_nested():
                from src.core.models.gamification_models import PointTransaction, UserPoints

                # Points
                points_result = await self._db.execute(
                    select(UserPoints).where(
                        UserPoints.user_id == _coerce_user_id(user_id),
                        UserPoints.tenant_id == tenant_id,
                    )
                )
                points = points_result.scalar_one_or_none()
                if points:
                    # Transactions
                    transactions_result = await self._db.execute(
                        select(PointTransaction).where(
                            PointTransaction.user_id == _coerce_user_id(user_id),
                            PointTransaction.tenant_id == tenant_id,
                        )
                    )
                    transactions = transactions_result.scalars().all()
                    data["gamification"] = {
                        "points": {
                            "total": points.total_points,
                            "level": points.level,
                            "streak": points.current_streak,
                        },
                        "transactions": [
                            {
                                "id": t.id,
                                "points": t.points,
                                "reason": t.reason,
                                "created_at": (t.created_at.isoformat() if t.created_at else None),
                            }
                            for t in transactions
                        ],
                    }
                    total_records += 1 + len(transactions)
        except Exception:
            await self._db.rollback()
            data["gamification"] = {}

        # 10. Agentic tasks (GDPR-A17-004)
        try:
            async with self._db.begin_nested():
                from src.domains.tasks.models import Task

                tasks_result = await self._db.execute(
                    select(Task).where(
                        Task.tenant_id == tenant_id,
                        Task.created_by == _coerce_user_id(user_id),
                    )
                )
                tasks = tasks_result.scalars().all()
                data["agentic_tasks"] = [
                    {
                        "id": str(t.id),
                        "title": t.title,
                        "status": str(t.status),
                        "created_at": (t.created_at.isoformat() if t.created_at else None),
                    }
                    for t in tasks
                ]
                total_records += len(tasks)
        except Exception:
            await self._db.rollback()
            data["agentic_tasks"] = []

        # 11. Copilot conversation memory (GDPR-A17-004; live Redis sessions only, TTL 1h)
        try:
            from uuid import UUID as _UUID

            # importlib avoids direct ImportFrom (DSM boundary governance -> agent_runtime)
            conv_mod = importlib.import_module("src.core.copilot.conversation_memory")
            ConversationMemory = conv_mod.ConversationMemory
            from src.core.shared.redis_client import get_redis

            redis = await get_redis()
            memory = ConversationMemory(redis)
            session_ids = await memory.get_user_sessions(tenant_id, int(_coerce_user_id(user_id)))
            # Niet `conversations`: die naam is in deze functie al gebonden aan de
            # CVAConversation-rijen (regel ~520). Die waarde is daar volledig verwerkt, dus
            # het herbinden brak niets, maar twee betekenissen onder een naam in de
            # GDPR-export leest verkeerd -- en mypy zag het verschil wel.
            copilot_conversations: list[dict[str, object]] = []
            for sid in session_ids:
                history = await memory.get_history(tenant_id, _UUID(sid))
                copilot_conversations.append(
                    {
                        "session_id": sid,
                        "messages": [
                            {"role": m.role, "content": m.content, "timestamp": m.timestamp}
                            for m in history
                        ],
                    }
                )
            data["copilot_conversations"] = copilot_conversations
            total_records += len(copilot_conversations)
        except Exception as exc:
            logger.warning(
                "dsar: copilot conversation export failed for user %s: %s: %s",
                user_id,
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            data["copilot_conversations"] = []

        # Create audit log
        await self._create_audit_log(
            tenant_id=tenant_id,
            user_id=cast(Optional[int], _coerce_user_id(requester) if requester else None),
            action="gdpr.dsar_export",
            resource=f"user:{user_id}",
            details={
                "data_subject": user_id,
                "requested_by": requester,
                "categories": list(data.keys()),
                "total_records": total_records,
            },
            threat_level="info",
            endpoint="/api/gdpr/export",
            description=f"DSAR export for user {user_id}",
            event_metadata={
                "dsar_action": "export",
                "data_subject": user_id,
            },
        )

        return DSARExportResult(
            user_id=str(user_id),
            tenant_id=tenant_id,
            exported_at=exported_at,
            data=data,
            total_records=total_records,
        )

    async def delete_user_data(
        self,
        user_id: str,
        tenant_id: int,
        hard_delete: bool = False,
        requested_by_user_id: str | None = None,
        is_admin: bool = False,
    ) -> DSARDeletionResult:
        """
        Delete all data for a user (GDPR Art. 17 - Right to Erasure).

        Supports both soft delete (default, 30-day grace period) and
        hard delete (permanent, admin only).

        Args:
            user_id: Data subject ID
            tenant_id: Tenant context
            hard_delete: True = permanent delete, False = soft delete
            requested_by_user_id: Who requested deletion
            is_admin: Whether requester is admin

        Returns:
            DSARDeletionResult with deletion details

        Raises:
            DSARAuthorizationError: If not authorized or hard delete without admin
            DSARTenantIsolationError: If cross-tenant access attempted
        """
        deleted_at = datetime.now(timezone.utc)
        requester = requested_by_user_id or user_id

        # Authorize
        self._authorize(user_id, requester, is_admin)

        # Hard delete requires admin
        if hard_delete and not is_admin:
            raise DSARAuthorizationError(
                "Hard delete requires admin privileges. Soft delete is available for all users."
            )

        # Verify tenant isolation
        user = await self._verify_tenant_isolation(user_id, tenant_id)

        # De wissing is wettelijk en wordt NOOIT geblokkeerd door LAST_ADMIN; wel meten we VOOR de
        # wijziging of dit de laatste beheerder was, om er daarna een spoor van achter te laten.
        was_laatste_beheerder = await self._is_laatste_beheerder(tenant_id, user_id)

        records_affected: dict[str, int] = {}
        scheduled_purge_date: datetime | None = None

        if hard_delete:
            # HARD DELETE: Permanent removal
            # 1. Delete workflows
            try:
                from src.core.workflow.models import C7Workflow as Workflow

                workflows_result = await self._db.execute(
                    delete(Workflow).where(
                        Workflow.tenant_id == tenant_id,
                        Workflow.created_by == _coerce_user_id(user_id),
                    )
                )
                # Cast to CursorResult to access rowcount attribute
                cursor_result = cast(CursorResult[RowMapping], workflows_result)
                records_affected["workflows"] = cursor_result.rowcount or 0
            except Exception as e:
                logger.error(
                    "dsar: workflow hard-delete failed for user %s: %s: %s",
                    user_id,
                    type(e).__name__,
                    e,
                    exc_info=True,
                )
                records_affected["workflows"] = 0

            # 2. Delete CVA conversations (user_message + cva_response content)
            try:
                async with self._db.begin_nested():
                    from src.core.conversations.models import CVAConversation

                    cva_result = await self._db.execute(
                        delete(CVAConversation).where(
                            CVAConversation.tenant_id == tenant_id,
                            CVAConversation.user_id == _coerce_user_id(user_id),
                        )
                    )
                    # Cast to CursorResult to access rowcount attribute
                    cursor_result = cast(CursorResult[RowMapping], cva_result)
                    records_affected["conversations"] = cursor_result.rowcount or 0
            except Exception as e:
                logger.error(
                    "dsar: cva_conversation hard-delete failed for user %s: %s: %s",
                    user_id,
                    type(e).__name__,
                    e,
                    exc_info=True,
                )
                records_affected["conversations"] = 0

            # 3. Delete UserConsent (AUDIT-GDPR-008 / Art. 17)
            try:
                from src.core.governance.models import UserConsent

                consent_result = await self._db.execute(
                    delete(UserConsent).where(
                        UserConsent.tenant_id == tenant_id,
                        UserConsent.user_id == str(user_id),
                    )
                )
                cursor_result = cast(CursorResult[RowMapping], consent_result)
                records_affected["user_consent"] = cursor_result.rowcount or 0
            except Exception as e:
                logger.error(
                    "dsar: user_consent hard-delete failed for user %s: %s: %s",
                    user_id,
                    type(e).__name__,
                    e,
                    exc_info=True,
                )
                records_affected["user_consent"] = 0

            # 4. Delete UserProfilingOptOut (AUDIT-GDPR-008 / Art. 17)
            try:
                from src.core.governance.models import UserProfilingOptOut

                optout_result = await self._db.execute(
                    delete(UserProfilingOptOut).where(
                        UserProfilingOptOut.tenant_id == tenant_id,
                        UserProfilingOptOut.user_id == str(user_id),
                    )
                )
                cursor_result = cast(CursorResult[RowMapping], optout_result)
                records_affected["profiling_opt_out"] = cursor_result.rowcount or 0
            except Exception as e:
                logger.error(
                    "dsar: profiling_opt_out hard-delete failed for user %s: %s: %s",
                    user_id,
                    type(e).__name__,
                    e,
                    exc_info=True,
                )
                records_affected["profiling_opt_out"] = 0

            # 5. Delete AIDecision (AUDIT-GDPR-008 / Art. 17)
            try:
                from src.core.governance.models import AIDecision

                ai_result = await self._db.execute(
                    delete(AIDecision).where(
                        AIDecision.tenant_id == tenant_id,
                        AIDecision.user_id == str(user_id),
                    )
                )
                cursor_result = cast(CursorResult[RowMapping], ai_result)
                records_affected["ai_decisions"] = cursor_result.rowcount or 0
            except Exception as e:
                logger.error(
                    "dsar: ai_decision hard-delete failed for user %s: %s: %s",
                    user_id,
                    type(e).__name__,
                    e,
                    exc_info=True,
                )
                records_affected["ai_decisions"] = 0

            # 6. Delete PointTransaction + UserPoints (AUDIT-GDPR-008 / Art. 17)
            try:
                from src.core.models.gamification_models import PointTransaction, UserPoints

                pt_result = await self._db.execute(
                    delete(PointTransaction).where(
                        PointTransaction.tenant_id == tenant_id,
                        PointTransaction.user_id == _coerce_user_id(user_id),
                    )
                )
                cursor_result = cast(CursorResult[RowMapping], pt_result)
                records_affected["point_transactions"] = cursor_result.rowcount or 0

                up_result = await self._db.execute(
                    delete(UserPoints).where(
                        UserPoints.tenant_id == tenant_id,
                        UserPoints.user_id == _coerce_user_id(user_id),
                    )
                )
                cursor_result = cast(CursorResult[RowMapping], up_result)
                records_affected["user_points"] = cursor_result.rowcount or 0
            except Exception as e:
                logger.error(
                    "dsar: gamification hard-delete failed for user %s: %s: %s",
                    user_id,
                    type(e).__name__,
                    e,
                    exc_info=True,
                )
                records_affected["point_transactions"] = 0
                records_affected["user_points"] = 0

            # 6b. Delete agentic tasks + clear copilot memory (GDPR-A17-004)
            records_affected["agentic_tasks"] = await self._delete_agentic_tasks(tenant_id, user_id)
            records_affected["copilot_sessions"] = await self._clear_copilot_sessions(
                tenant_id, user_id
            )
            # 6c. Purge Twin memory items (AUDIT-004): embeddings cannot be anonymised,
            # only physical DELETE satisfies Art. 17.
            records_affected["memory_items"] = await self._purge_memory_items(tenant_id, user_id)

            # 7. Delete user (last -- referential integrity)
            await self._db.execute(delete(User).where(User.id == _coerce_user_id(user_id)))
            records_affected["user"] = 1
            await self._db.commit()

        else:
            # SOFT DELETE: Mark as inactive with grace period
            grace_period = timedelta(days=self.DEFAULT_GRACE_PERIOD_DAYS)
            scheduled_purge_date = deleted_at + grace_period

            # Mark user inactive
            user.is_active = False
            user.deleted_at = deleted_at
            user.deletion_scheduled_for = scheduled_purge_date

            records_affected["user_marked"] = 1

            # Mark workflows inactive (if column exists)
            try:
                from src.core.workflow.models import C7Workflow as Workflow

                workflows_result = await self._db.execute(
                    update(Workflow)
                    .where(
                        Workflow.tenant_id == tenant_id,
                        Workflow.created_by == _coerce_user_id(user_id),
                    )
                    .values(is_active=False)
                )
                # Cast to CursorResult to access rowcount attribute
                cursor_result = cast(CursorResult[RowMapping], workflows_result)
                records_affected["workflows_marked"] = cursor_result.rowcount or 0
            except Exception as e:
                logger.error(
                    "dsar: workflow soft-delete failed for user %s: %s: %s",
                    user_id,
                    type(e).__name__,
                    e,
                    exc_info=True,
                )
                records_affected["workflows_marked"] = 0

            # Physically delete CVA conversations (no is_active column -- Art. 17 erasure)
            try:
                async with self._db.begin_nested():
                    from src.core.conversations.models import CVAConversation

                    cva_result = await self._db.execute(
                        delete(CVAConversation).where(
                            CVAConversation.tenant_id == tenant_id,
                            CVAConversation.user_id == _coerce_user_id(user_id),
                        )
                    )
                    # Cast to CursorResult to access rowcount attribute
                    cursor_result = cast(CursorResult[RowMapping], cva_result)
                    records_affected["conversations_deleted"] = cursor_result.rowcount or 0
            except Exception as e:
                logger.error(
                    "dsar: cva_conversation soft-delete failed for user %s: %s: %s",
                    user_id,
                    type(e).__name__,
                    e,
                    exc_info=True,
                )
                records_affected["conversations_deleted"] = 0

            # agentic_tasks + copilot memory: physical erasure (no is_active column),
            # consistent with CVA conversations above (GDPR-A17-004).
            records_affected["agentic_tasks_deleted"] = await self._delete_agentic_tasks(
                tenant_id, user_id
            )
            records_affected["copilot_sessions"] = await self._clear_copilot_sessions(
                tenant_id, user_id
            )
            # Twin memory items: physical erasure in soft mode too (AUDIT-004) --
            # the embedding column is a non-anonymisable derivative of personal data.
            records_affected["memory_items_deleted"] = await self._purge_memory_items(
                tenant_id, user_id
            )

            await self._db.commit()

        # Create audit log (survives deletion)
        threat_level = "critical" if hard_delete else "warning"
        await self._create_audit_log(
            tenant_id=tenant_id,
            user_id=cast(Optional[int], _coerce_user_id(requester) if requester else None),
            action="gdpr.dsar_delete",
            resource=f"user:{user_id}",
            details={
                "data_subject": user_id,
                "requested_by": requester,
                "delete_type": "hard" if hard_delete else "soft",
                "records_affected": records_affected,
                "scheduled_purge": (
                    scheduled_purge_date.isoformat() if scheduled_purge_date else None
                ),
            },
            threat_level=threat_level,
            endpoint="/api/gdpr/delete",
            description=f"DSAR {'hard' if hard_delete else 'soft'} delete for user {user_id}",
            event_metadata={
                "dsar_action": "delete",
                "data_subject": user_id,
                "hard_delete": hard_delete,
            },
        )

        await self._meld_als_laatste_beheerder(tenant_id, was_laatste_beheerder)

        return DSARDeletionResult(
            user_id=str(user_id),
            tenant_id=tenant_id,
            deleted_at=deleted_at,
            delete_type="hard" if hard_delete else "soft",
            records_affected=records_affected,
            scheduled_purge_date=scheduled_purge_date,
        )


# Module exports
__all__ = [
    "DSARService",
    "DSARExportResult",
    "DSARDeletionResult",
    "DSARServiceConfig",
    "DSARAuthorizationError",
    "DSARTenantIsolationError",
    "DSARNotFoundError",
]
