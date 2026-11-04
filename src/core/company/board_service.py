"""BoardService - Presentatie- en routeringslaag voor board governance.

Deze service fungeert als presentatielaag bovenop PolicyEngine voor governance
beslissingen en board approvals. Behandelt routing naar juiste board members
op basis van action type en risk level.

Architecture: docs/ARCHITECTURE_PAPERCLIP_INTEGRATION.md S.7.4
PRD: docs/3-PRDs/PRD_PAPERCLIP_INTEGRATION_v1.0.md S.4.4
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional, Type

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.company.context import AgentExecutionContext
from src.core.company.models import BoardDecision, BoardDecisionStatus, Company
from src.core.company.schemas import BoardDecisionResponse, BoardQueueResponse
from src.core.database.database import DatabaseManager
from src.core.exceptions.exceptions import NotFoundError, ValidationError
from src.core.governance.policy_engine import PolicyEngine, PolicyRiskLevel

# Namespace for generating deterministic UUIDs from user IDs
USER_ID_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


class BoardServiceError(Exception):
    """Base exception for BoardService errors."""

    pass


class GoldenRuleR3Violation(BoardServiceError):
    """Raised when Golden Rule R3 is violated (missing goal_id, risk_level, or budget_impact)."""

    pass


class BoardRoleError(BoardServiceError):
    """Raised when user doesn't have required board role."""

    pass


class BoardService:
    """Presentatie- en routeringslaag bovenop PolicyEngine.

    Deze service beheert board governance beslissingen inclusief:
    - Submit decisions voor board approval
    - Auto-routing naar juiste board members
    - Tenant-configureerbare board role mapping
    - Approval queue management

    Golden Rule R3: Elke beslissing MOET goal_id, risk_level, en budget_impact hebben.
    """

    # Default board role routing mapping
    DEFAULT_ROUTING = {
        "budget": "CFO",
        "agent_management": "CTO",
        "agent_hire": "CTO",
        "agent_firing": "CHRO",
        "cross_department": "CEO",
        "data_export": "Compliance Officer",
        "security": "CISO",
        "hr": "CHRO",
        "legal": "General Counsel",
        "default": "tenant_admin",
    }

    # Risk level thresholds
    RISK_LEVELS = {
        "LOW": PolicyRiskLevel.LOW,
        "MEDIUM": PolicyRiskLevel.MEDIUM,
        "HIGH": PolicyRiskLevel.HIGH,
        "CRITICAL": PolicyRiskLevel.CRITICAL,
    }

    def __init__(
        self,
        db_manager: DatabaseManager,
        policy_engine: PolicyEngine,
        tenant_context: Any,  # TenantContext  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """Initialize BoardService.

        Args:
            db_manager: Database manager for session management
            policy_engine: PolicyEngine for governance validation
            tenant_context: Tenant context for isolation
        """
        self.db_manager = db_manager
        self.policy_engine = policy_engine
        self.tenant_context = tenant_context

    async def submit(
        self,
        action_type: str,
        action_context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        context: AgentExecutionContext,
    ) -> BoardDecision:
        """Submit een actie voor board approval.

        Golden Rule R3: goal_id, risk_level, en budget_impact zijn verplicht.

        Args:
            action_type: Type actie (bijv. "budget", "agent_hire")
            action_context: Context voor de actie
            context: Agent execution context

        Returns:
            BoardDecision record

        Raises:
            GoldenRuleR3Violation: Als goal_id, risk_level, of budget_impact ontbreekt
            NotFoundError: Als company niet gevonden wordt
        """
        tenant_id = self.tenant_context.tenant_id

        # Golden Rule R3: Validate required fields
        self._validate_golden_rule_r3(action_context, context)

        # Validate company_id is present
        if context.company_id is None:
            raise ValidationError("company_id is required for board decision submission")

        async with self.db_manager.get_session() as session:
            # Get company for board role config
            company = await self._get_company(session, context.company_id, tenant_id)

            # Determine board role via routing logic
            board_role = self._route_to_board_member(
                action_type=action_type,
                risk_level=context.policy_scope.risk_level,
                department_id=context.department_id,
                company=company,
            )

            # Check auto-approve threshold
            board_config = company.board_role_config or {}
            thresholds = board_config.get("thresholds", {})
            auto_approve_below = thresholds.get("auto_approve_below", "LOW")

            # Check if auto-approve applies
            decision_status = BoardDecisionStatus.PENDING
            if self._should_auto_approve(context.policy_scope.risk_level, auto_approve_below):
                decision_status = BoardDecisionStatus.APPROVED

            # Create board decision
            decision = BoardDecision(
                tenant_id=tenant_id,
                company_id=context.company_id,
                requested_by=self._get_current_user_id(),
                board_role=board_role,
                action_type=action_type,
                action_context=action_context,
                goal_id=context.goal_chain.task_goal_id or context.goal_chain.mission_id,
                decision=(
                    decision_status.value
                    if decision_status != BoardDecisionStatus.PENDING
                    else None
                ),
                decided_by=(
                    self._get_current_user_id()
                    if decision_status == BoardDecisionStatus.APPROVED
                    else None
                ),
                decided_at=(
                    datetime.now(timezone.utc)
                    if decision_status == BoardDecisionStatus.APPROVED
                    else None
                ),
                reason=(
                    "Auto-approved based on risk level threshold"
                    if decision_status == BoardDecisionStatus.APPROVED
                    else None
                ),
            )

            session.add(decision)
            await session.commit()
            await session.refresh(decision)

            # Send notification (only for non-auto-approved)
            if decision_status == BoardDecisionStatus.PENDING:
                await self._send_notification(decision, "pending")

            return decision

    async def approve(
        self,
        decision_id: uuid.UUID,
        user_id: int,
        reason: str | None = None,
    ) -> BoardDecision:
        """Keur een board decision goed.

        Args:
            decision_id: Decision UUID
            user_id: User ID die goedkeurt
            reason: Optionele reden voor goedkeuring

        Returns:
            Geupdatete BoardDecision

        Raises:
            NotFoundError: Als decision niet gevonden wordt
            BoardRoleError: Als user niet de juiste board role heeft
            BoardServiceError: Als decision al besloten is
        """
        tenant_id = self.tenant_context.tenant_id

        async with self.db_manager.get_session() as session:
            decision = await self._get_decision(session, decision_id, tenant_id)

            # Check if already decided
            if decision.decision is not None:
                raise BoardServiceError(f"Decision already {decision.decision}")

            # Validate user has required board role
            has_role = await self._user_has_board_role(
                session, user_id, decision.board_role, tenant_id
            )
            if not has_role:
                raise BoardRoleError(
                    f"User {user_id} does not have required board role: {decision.board_role}"
                )

            # Update decision
            decision.decision = BoardDecisionStatus.APPROVED.value
            decision.decided_by = user_id
            decision.decided_at = datetime.now(timezone.utc)
            decision.reason = reason

            await session.commit()
            await session.refresh(decision)

            # Send notification
            await self._send_notification(decision, "approved")

            return decision

    async def reject(
        self,
        decision_id: uuid.UUID,
        user_id: int,
        reason: str,
    ) -> BoardDecision:
        """Wijs een board decision af.

        Args:
            decision_id: Decision UUID
            user_id: User ID die afwijst
            reason: Verplichte reden voor afwijzing

        Returns:
            Geupdatete BoardDecision

        Raises:
            NotFoundError: Als decision niet gevonden wordt
            BoardRoleError: Als user niet de juiste board role heeft
            ValidationError: Als reason ontbreekt
            BoardServiceError: Als decision al besloten is
        """
        tenant_id = self.tenant_context.tenant_id

        # Reason is required for rejection
        if not reason or not reason.strip():
            raise ValidationError("Reason is required for rejection")

        async with self.db_manager.get_session() as session:
            decision = await self._get_decision(session, decision_id, tenant_id)

            # Check if already decided
            if decision.decision is not None:
                raise BoardServiceError(f"Decision already {decision.decision}")

            # Validate user has required board role
            has_role = await self._user_has_board_role(
                session, user_id, decision.board_role, tenant_id
            )
            if not has_role:
                raise BoardRoleError(
                    f"User {user_id} does not have required board role: {decision.board_role}"
                )

            # Update decision
            decision.decision = BoardDecisionStatus.REJECTED.value
            decision.decided_by = user_id
            decision.decided_at = datetime.now(timezone.utc)
            decision.reason = reason

            await session.commit()
            await session.refresh(decision)

            # Send notification
            await self._send_notification(decision, "rejected")

            return decision

    async def get_queue(
        self,
        user_id: int,
    ) -> BoardQueueResponse:
        """Haal pending decisions op voor een user's board role(s).

        Args:
            user_id: User ID

        Returns:
            BoardQueueResponse met pending decisions
        """
        tenant_id = self.tenant_context.tenant_id

        async with self.db_manager.get_session() as session:
            # Get user's board roles
            user_roles = await self._get_user_board_roles(session, user_id, tenant_id)

            if not user_roles:
                return BoardQueueResponse(decisions=[], pending_count=0)

            # Query pending decisions for user's board roles
            result = await session.execute(
                select(BoardDecision)
                .where(
                    BoardDecision.tenant_id == tenant_id,
                    BoardDecision.board_role.in_(user_roles),
                    BoardDecision.decision.is_(None),  # Pending
                )
                .order_by(BoardDecision.created_at.desc())
            )
            decisions = result.scalars().all()

            # Convert to response models
            decision_responses = [self._to_response_model(d) for d in decisions]

            return BoardQueueResponse(
                decisions=decision_responses,
                pending_count=len(decision_responses),
            )

    async def get_history(
        self,
        company_id: uuid.UUID,
    ) -> list[BoardDecisionResponse]:
        """Haal alle decisions op voor een company.

        Args:
            company_id: Company UUID

        Returns:
            Lijst van BoardDecisionResponse, gesorteerd op datum
        """
        tenant_id = self.tenant_context.tenant_id

        async with self.db_manager.get_session() as session:
            result = await session.execute(
                select(BoardDecision)
                .where(
                    BoardDecision.tenant_id == tenant_id,
                    BoardDecision.company_id == company_id,
                )
                .order_by(BoardDecision.created_at.desc())
            )
            decisions = result.scalars().all()

            return [self._to_response_model(d) for d in decisions]

    def _route_to_board_member(
        self,
        action_type: str,
        risk_level: str,
        department_id: uuid.UUID | None,
        company: Company,
    ) -> str:
        """Bepaal board role voor een actie.

        Routing logic:
        1. Check company.board_role_config voor tenant-specifieke routing
        2. Gebruik default mapping als geen config
        3. Escalate naar CEO bij HIGH/CRITICAL als configured

        Args:
            action_type: Type actie
            risk_level: Risk level (LOW, MEDIUM, HIGH, CRITICAL)
            department_id: Department UUID (voor department-specifieke routing)
            company: Company model met board_role_config

        Returns:
            Board role string (bijv. "CFO", "CTO", "CEO")
        """
        board_config = company.board_role_config or {}

        # Check for escalation
        thresholds = board_config.get("thresholds", {})
        escalate_above = thresholds.get("escalate_above", "HIGH")

        if self._risk_level_higher_than(risk_level, escalate_above):
            return "CEO"

        # Check tenant-specific routing
        if action_type in board_config:
            return str(board_config[action_type])

        # Map action type to routing key
        routing_key = self._map_action_type(action_type)

        # Check default routing
        if routing_key in board_config:
            return str(board_config[routing_key])

        # Fall back to hardcoded defaults
        return self.DEFAULT_ROUTING.get(routing_key, self.DEFAULT_ROUTING["default"])

    def _translate_to_business_language(self, policy_result: dict[str, Any]) -> str:  # TODO(TYPE): replace Any with concrete type
        """Vertaal PolicyEngine resultaat naar business taal.

        Args:
            policy_result: PolicyEngine validatie resultaat

        Returns:
            Human-readable string in Dutch
        """
        risk_level = policy_result.get("risk_level", "LOW")
        requires_approval = policy_result.get("requires_approval", False)

        if risk_level == "CRITICAL":
            return "Board approval vereist - kritieke actie gedetecteerd"
        elif risk_level == "HIGH" and requires_approval:
            return "Afdelingshoofd moet goedkeuren - verhoogd risico"
        elif risk_level == "MEDIUM":
            return "Team lead notificatie - medium risico"
        else:
            return "Automatisch goedgekeurd - laag risico"

    def _validate_golden_rule_r3(
        self,
        action_context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        context: AgentExecutionContext,
    ) -> None:
        """Validate Golden Rule R3: goal_id, risk_level, budget_impact required.

        Args:
            action_context: Action context
            context: Agent execution context

        Raises:
            GoldenRuleR3Violation: Als verplichte velden ontbreken
        """
        missing: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Check goal_id
        if not context.goal_chain.task_goal_id and not context.goal_chain.mission_id:
            missing.append("goal_id (no task_goal_id or mission_id in goal_chain)")

        # Check risk_level
        if not context.policy_scope.risk_level:
            missing.append("risk_level")

        # Check budget_impact (in action_context)
        if "budget_impact" not in action_context:
            missing.append("budget_impact")

        if missing:
            raise GoldenRuleR3Violation(
                f"Golden Rule R3 violation - missing required fields: {', '.join(missing)}"
            )

    def _should_auto_approve(self, risk_level: str, threshold: str) -> bool:
        """Check if decision should be auto-approved based on risk level.

        Args:
            risk_level: Actual risk level
            threshold: Auto-approve threshold

        Returns:
            True if should auto-approve
        """
        risk_order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
        actual_level = risk_order.get(risk_level.upper(), 0)
        threshold_level = risk_order.get(threshold.upper(), 0)
        return actual_level <= threshold_level

    def _risk_level_higher_than(self, risk_level: str, threshold: str) -> bool:
        """Check if risk level is higher than threshold.

        Args:
            risk_level: Risk level to check
            threshold: Threshold to compare against

        Returns:
            True if risk_level > threshold
        """
        risk_order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
        actual = risk_order.get(risk_level.upper(), 0)
        threshold_val = risk_order.get(threshold.upper(), 0)
        return actual > threshold_val

    def _map_action_type(self, action_type: str) -> str:
        """Map action type to routing key.

        Args:
            action_type: Action type string

        Returns:
            Routing key
        """
        action_lower = action_type.lower()

        if "budget" in action_lower or "finance" in action_lower or "cost" in action_lower:
            return "budget"
        # Check firing/removal BEFORE generic agent check
        elif "agent" in action_lower and (
            "fire" in action_lower
            or "fir" in action_lower
            or "remove" in action_lower
            or "delete" in action_lower
        ):
            return "agent_firing"
        # Check hiring AFTER firing (more specific first)
        elif "agent" in action_lower and (
            "hire" in action_lower or "add" in action_lower or "create" in action_lower
        ):
            return "agent_hire"
        elif "agent" in action_lower:
            return "agent_management"
        elif "export" in action_lower or "download" in action_lower:
            return "data_export"
        elif "security" in action_lower:
            return "security"
        elif "hr" in action_lower or "employee" in action_lower:
            return "hr"
        elif "legal" in action_lower:
            return "legal"
        elif "cross" in action_lower:
            return "cross_department"
        else:
            return "default"

    async def _get_company(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        tenant_id: int,
    ) -> Company:
        """Get company by ID with tenant check."""
        result = await session.execute(
            select(Company).where(
                Company.id == company_id,
                Company.tenant_id == tenant_id,
            )
        )
        company = result.scalar_one_or_none()
        if not company:
            raise NotFoundError(f"Company {company_id} not found")
        return company

    async def _get_decision(
        self,
        session: AsyncSession,
        decision_id: uuid.UUID,
        tenant_id: int,
    ) -> BoardDecision:
        """Get decision by ID with tenant check."""
        result = await session.execute(
            select(BoardDecision).where(
                BoardDecision.id == decision_id,
                BoardDecision.tenant_id == tenant_id,
            )
        )
        decision = result.scalar_one_or_none()
        if not decision:
            raise NotFoundError(f"Decision {decision_id} not found")
        return decision

    async def _user_has_board_role(
        self,
        session: AsyncSession,
        user_id: int,
        board_role: str,
        tenant_id: int,
    ) -> bool:
        """Check if user has specific board role.

        Args:
            session: Database session
            user_id: User ID
            board_role: Required board role
            tenant_id: Tenant ID

        Returns:
            True if user has board role
        """
        # For now, check if user has a role with the board_role name
        # This is a simplified implementation - in production, this would
        # check a dedicated board_roles table or role metadata
        from src.core.models.rbac_models import Role, User

        result = await session.execute(
            select(User).where(
                User.id == user_id,
                User.tenant_id == tenant_id,
            )
        )
        user = result.scalar_one_or_none()
        if not user:
            return False

        # Check if any of user's roles match the board role
        for role in user.roles:
            if role.name.lower() == board_role.lower():
                return True
            # Special case: admin roles have all board permissions
            if role.name.lower() in ["admin", "system_admin", "tenant_admin"]:
                return True

        return False

    async def _get_user_board_roles(
        self,
        session: AsyncSession,
        user_id: int,
        tenant_id: int,
    ) -> list[str]:
        """Get all board roles for a user.

        Args:
            session: Database session
            user_id: User ID
            tenant_id: Tenant ID

        Returns: List[Any] of board role strings  # TODO(TYPE): replace Any with concrete type
        """
        from src.core.models.rbac_models import User

        result = await session.execute(
            select(User).where(
                User.id == user_id,
                User.tenant_id == tenant_id,
            )
        )
        user = result.scalar_one_or_none()
        if not user:
            return []

        roles: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for role in user.roles:
            roles.append(role.name)
            # Map common roles to board roles
            if role.name.lower() == "cfo":
                roles.extend(["CFO", "Finance"])
            elif role.name.lower() == "cto":
                roles.extend(["CTO", "Technology"])
            elif role.name.lower() == "ceo":
                roles.extend(["CEO", "Executive"])
            elif role.name.lower() == "chro":
                roles.extend(["CHRO", "HR"])
            elif role.name.lower() in ["admin", "system_admin"]:
                # Admin has all board roles
                roles.extend(
                    [
                        "CFO",
                        "CTO",
                        "CEO",
                        "CHRO",
                        "CISO",
                        "Compliance Officer",
                        "General Counsel",
                        "tenant_admin",
                    ]
                )

        return list(set(roles))

    def _get_current_user_id(self) -> int:
        """Get current user ID from tenant context or return default."""
        # In a real implementation, this would get the user ID from the
        # current request context (e.g., from JWT token)
        if hasattr(self.tenant_context, "user_id") and self.tenant_context.user_id:
            return int(self.tenant_context.user_id)
        return 1  # Default for testing

    def _int_to_uuid(self, user_id: int) -> uuid.UUID:
        """Convert integer user_id to deterministic UUID.

        Args:
            user_id: Integer user ID from database

        Returns:
            Deterministic UUID generated from user_id
        """
        return uuid.uuid5(USER_ID_NAMESPACE, str(user_id))

    def _to_response_model(self, decision: BoardDecision) -> BoardDecisionResponse:
        """Convert BoardDecision ORM to response model."""
        return BoardDecisionResponse(
            id=decision.id,
            company_id=decision.company_id,
            requested_by=self._int_to_uuid(decision.requested_by),
            board_role=decision.board_role,
            action_type=decision.action_type,
            action_context=decision.action_context,
            goal_id=decision.goal_id,
            decision=decision.decision,  # type: ignore[arg-type]
            decided_by=self._int_to_uuid(decision.decided_by) if decision.decided_by else None,
            reason=decision.reason,
            decided_at=decision.decided_at,
            created_at=decision.created_at,
        )

    async def _send_notification(
        self,
        decision: BoardDecision,
        status: str,
    ) -> None:
        """Send notification about decision status change.

        Args:
            decision: Board decision
            status: New status (pending, approved, rejected)
        """
        # This is a placeholder - in production, this would integrate
        # with the notification service
        # For now, just log it
        import logging

        logger = logging.getLogger(__name__)
        logger.info(
            f"Notification: Decision {decision.id} is {status}. "
            f"Action: {decision.action_type}, Board role: {decision.board_role}"
        )
