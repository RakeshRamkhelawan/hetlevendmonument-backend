import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class ProjectIteration(BaseModel):
    """Represents a single cycle in a recurring project (e.g., Visit 1 of 9)"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    index: int  # 1, 2, 3...
    status: str = "PENDING"  # PENDING, ACTIVE, COMPLETED, SKIPPED
    scheduled_date: datetime | None = None

    # Specific variables for THIS iteration (e.g. "Rome", "Mr. Rossi")
    iteration_vars: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type

    # Tracking outputs
    outputs: dict[str, Any] = {}  # e.g. {"article_url": "...", "email_sent": true}  # TODO(TYPE): replace Any with concrete type


class ProjectConfig(BaseModel):
    """
    Universal Definition of a Long-Running Autonomous Project.
    Used across ALL domains (HR, IT, MKT, etc.)

    SECURITY: tenant_id added for multi-tenant isolation (Fase 0.2)
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str  # Multi-tenant isolation (Fase 0.2 security fix)
    name: str
    description: str
    domain: str  # e.g. "MARKETING", "HR", "IT"
    owner_id: str  # User ID of the human owner

    # The Blueprint
    sop_ref: str  # ID of the Meta-SOP to use (e.g. "SOP-RECURRING-EVENT")

    # Global Context (Applies to all iterations)
    static_context: dict[str, Any] = {}  # e.g. {"tone": "British", "guidelines": "..."}  # TODO(TYPE): replace Any with concrete type

    # Missing Info Definitions (What needs to be asked?)
    required_vars: list[str] = []  # e.g. ["location", "ilo_name"]

    # The Timeline
    iterations: list[ProjectIteration] = []

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    status: str = "ACTIVE"  # ACTIVE, PAUSED, ARCHIVED

    def get_current_iteration(self) -> ProjectIteration | None:
        """Find the first PENDING or ACTIVE iteration"""
        for it in self.iterations:
            if it.status in ["PENDING", "ACTIVE"]:
                return it
        return None
