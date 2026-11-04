"""Model Provenance Tracking for EU AI Act compliance.

Task 9: Article 53 Model Provenance
Tracks all LLM calls with provider, model, version, and hashes.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from src.core.governance.models import ModelProvenanceDB


@dataclass
class ProvenanceRecord:
    """Provenance record for a single LLM call.

    Attributes:
        record_id: Unique record identifier
        timestamp: When the call was made
        provider: LLM provider (OpenAI, Google, etc.)
        model: Model name
        model_version: Specific model version
        input_hash: SHA-256 hash of input data
        output_hash: SHA-256 hash of output data
        tenant_id: Tenant context (str for dataclass compat; service uses int FK)
        user_id: User who initiated the call
        retention_until: Data retention deadline (6 months per Article 12)
    """

    record_id: str
    timestamp: datetime
    provider: str
    model: str
    model_version: str
    input_hash: str
    output_hash: str
    tenant_id: str | None = None
    user_id: str | None = None
    retention_until: datetime | None = None

    def __post_init__(self) -> None:
        """Set retention date if not provided (6 months default)."""
        if self.retention_until is None:
            self.retention_until = self.timestamp + timedelta(days=180)

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert to dictionary."""
        return {
            "record_id": self.record_id,
            "timestamp": self.timestamp.isoformat(),
            "provider": self.provider,
            "model": self.model,
            "model_version": self.model_version,
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "retention_until": self.retention_until.isoformat() if self.retention_until else None,
        }


def compute_hash(data: str) -> str:
    """Compute full SHA-256 hash of data (64 hex chars, Article 53 tamper-evidence)."""
    return hashlib.sha256(data.encode()).hexdigest()


def new_provenance_record(
    provider: str,
    model: str,
    model_version: str,
    input_data: str,
    output_data: str,
    tenant_id: str | None = None,
    user_id: str | None = None,
) -> ProvenanceRecord:
    """Build a ProvenanceRecord dataclass without persisting it.

    Use ProvenanceService.log_provenance() to persist to the database.
    """
    return ProvenanceRecord(
        record_id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc),
        provider=provider,
        model=model,
        model_version=model_version,
        input_hash=compute_hash(input_data),
        output_hash=compute_hash(output_data),
        tenant_id=tenant_id,
        user_id=user_id,
    )


class ProvenanceService:
    """Async DB-backed provenance service (replaces _provenance_store singleton).

    Always inject tenant_id from JWT context as int -- never from request body.
    Note: ProvenanceRecord.tenant_id is str|None for backward compat with callers;
    ProvenanceService always uses self._tenant_id (int) for the DB FK.
    """

    def __init__(self, db: AsyncSession, tenant_id: int) -> None:
        self._db = db
        self._tenant_id = tenant_id

    async def log_provenance(self, record: ProvenanceRecord) -> ModelProvenanceDB:
        """Persist a provenance record to DB.

        Uses self._tenant_id (from JWT) as the DB FK -- ignores record.tenant_id
        which is a str and may differ from the int FK.
        """
        from src.core.governance.models import ModelProvenanceDB

        db_row = ModelProvenanceDB(
            tenant_id=self._tenant_id,
            provider=record.provider,
            model=record.model,
            model_version=record.model_version,
            input_hash=record.input_hash,
            output_hash=record.output_hash,
            user_id=record.user_id,
            retention_until=record.retention_until,
        )
        self._db.add(db_row)
        await self._db.commit()
        await self._db.refresh(db_row)
        return db_row

    async def list_provenance(
        self,
        provider: str | None = None,
        model: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ModelProvenanceDB]:
        """List non-deleted provenance records for this tenant."""
        from src.core.governance.models import ModelProvenanceDB

        q = (
            select(ModelProvenanceDB)
            .where(
                ModelProvenanceDB.tenant_id == self._tenant_id,
                ModelProvenanceDB.deleted_at.is_(None),
            )
            .order_by(ModelProvenanceDB.registered_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if provider:
            q = q.where(ModelProvenanceDB.provider == provider)
        if model:
            q = q.where(ModelProvenanceDB.model == model)
        result = await self._db.execute(q)
        return list(result.scalars().all())

    async def get_expired_records(self) -> list[ModelProvenanceDB]:
        """Get records past retention period (for cleanup scheduler)."""
        from src.core.governance.models import ModelProvenanceDB

        now = datetime.now(timezone.utc)
        result = await self._db.execute(
            select(ModelProvenanceDB).where(
                ModelProvenanceDB.tenant_id == self._tenant_id,
                ModelProvenanceDB.retention_until < now,
                ModelProvenanceDB.deleted_at.is_(None),
            )
        )
        return list(result.scalars().all())
