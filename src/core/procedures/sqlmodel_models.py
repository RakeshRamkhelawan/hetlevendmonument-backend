"""
SQLModel-based models for the procedures system (Phase 3)

This module provides SQLModel classes that serve as both ORM models
and Pydantic schemas, eliminating type drift between the database
layer and the API layer.

Migration status:
- DomainPack: MIGRATED (was src.core.procedures.models.DomainPack)
- ProcedureMetadata: NOT YET MIGRATED
- ProcedureExecution: NOT YET MIGRATED
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Column, Index, Integer, String, DateTime
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.sql import func
from sqlmodel import Field, SQLModel


# ============================================================================
# DOMAIN PACK SQLMODEL
# ============================================================================


class DomainPack(SQLModel, table=True):  # pyright: ignore[reportCallIssue, reportGeneralTypeIssues]
    """
    Domain Pack Model - represents a collection of related procedures
    for a specific department/domain.

    This single class serves as:
    - SQLAlchemy ORM model (table=True)
    - Pydantic validation schema
    - FastAPI response model
    """

    __tablename__ = "domain_packs"
    __table_args__ = (
        Index("idx_domain_packs_tenant", "tenant_id"),
        Index(
            "idx_domain_packs_tenant_name_version",
            "tenant_id",
            "name",
            "version",
            unique=True,
        ),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True, nullable=False),
    )
    tenant_id: int = Field(
        sa_column=Column(Integer, nullable=False, index=True),
        description="Tenant ID (integer, matches tenants.id)",
    )
    name: str = Field(
        sa_column=Column(String(255), nullable=False, index=True),
        min_length=1,
        max_length=255,
    )
    department: str = Field(
        sa_column=Column(String(255), nullable=False),
        min_length=1,
        max_length=255,
    )
    version: int = Field(default=1, sa_column=Column(Integer, nullable=False, default=1))
    description: str | None = Field(
        default=None,
        sa_column=Column(String(2000), nullable=True),
        max_length=2000,
    )
    capabilities: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False, default=list),
    )
    input_contracts: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, default=dict),
    )
    output_contracts: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, default=dict),
    )
    status: str = Field(
        default="active",
        sa_column=Column(String(50), nullable=False, default="active", index=True),
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
            onupdate=func.now(),
        ),
    )

    # Health monitoring fields
    last_used_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    usage_count: int = Field(default=0, sa_column=Column(Integer, nullable=False, default=0))
    error_count: int = Field(default=0, sa_column=Column(Integer, nullable=False, default=0))
    health_status: str = Field(
        default="healthy",
        sa_column=Column(String(50), nullable=False, default="healthy", index=True),
    )
    last_health_check: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )


class DomainPackCreate(SQLModel):
    """Schema for creating a new domain pack (no id, no timestamps)."""

    name: str = Field(min_length=1, max_length=255)
    department: str = Field(min_length=1, max_length=255)
    version: int = Field(default=1, ge=1)
    description: str | None = Field(default=None, max_length=2000)
    capabilities: list[str] = Field(default_factory=list)
    input_contracts: dict[str, Any] = Field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    output_contracts: dict[str, Any] = Field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    status: str | None = Field(default="active")


class DomainPackUpdate(SQLModel):
    """Schema for updating a domain pack (all fields optional)."""

    department: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    capabilities: list[str] | None = None
    input_contracts: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    output_contracts: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    status: str | None = None


# Backwards compatibility aliases
DomainPackRead = DomainPack
