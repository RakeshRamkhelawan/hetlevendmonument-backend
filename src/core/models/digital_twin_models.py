"""SQLAlchemy model voor agent twin consent events -- AUDIT-DB14b (Optie B).

ADR-026: consent-wijzigingen zijn onveranderlijk (INSERT only, never UPDATE).
ADR-005: tenant_id NOT NULL voor RLS-compliantie.

Verplaatst uit `src/core/api/v1/digital_twin/models.py` (was sinds OP-147,
2026-08-17, de enige registratie in `import_all_models.py` die de API-laag
importeerde -- Contract "Infrastructuurlaag mag niet API-laag importeren" in
`.importlinter`). Geen gedragswijziging: zelfde `Base`
(`src.core.database.database.Base`), zelfde tabelnaam.
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer

from src.core.database.database import Base


class AgentTwinConsentEvent(Base):  # type: ignore[misc]
    """Immutable consent log for agent digital twin (ADR-026)."""

    __tablename__ = "agent_twin_consent_events"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(Integer, nullable=False, index=True)
    tenant_id = Column(Integer, nullable=False, index=True)
    observe = Column(Boolean, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
