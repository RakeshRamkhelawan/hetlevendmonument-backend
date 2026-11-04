"""
Foundation Portal Content Models

9 models + 7 enums for the Levend Monument Foundation Portal (ADR-029).
All models have tenant_id NOT NULL except ContentTag (JOIN-based isolation).

Base import: src.core.database.database (NOT src.core.models.base)
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.core.database.database import Base

# ============================================================================
# Enums
# ============================================================================


class ContentType(str, enum.Enum):
    STORY = "story"
    ARTWORK = "artwork"
    AUDIO = "audio"
    DOCUMENT = "document"
    POETRY = "poetry"
    LINK = "link"
    # Sprint C (BE-MIG-014): educatieve en video/verslag-types. De Python
    # .value's zijn lowercase, maar de Postgres-enum content_type_enum bevat
    # de member-NAMEN (hoofdletters, zonder values_callable) -- de migratie
    # voegt daarom 'VIDEO', 'EDUCATIONAL_WORKBOOK', ... toe, niet lowercase.
    VIDEO = "video"
    EDUCATIONAL_WORKBOOK = "educational_workbook"
    EDUCATIONAL_VIDEO = "educational_video"
    TEACHER_GUIDE = "teacher_guide"
    EVENT_REPORT = "event_report"
    ART_DOCUMENTATION = "art_documentation"


class Privacy(str, enum.Enum):
    PUBLIC = "public"
    COMMUNITY = "community"


class Visibility(str, enum.Enum):
    """Publicatie-kanaal van content (ADR-029 Sprint C, BE-MIG-014).

    Aparta van Privacy: `edu`-content mag NOOIT in het publieke archief
    verschijnen; edu is een kanaal, geen privacy-niveau (audit N-2).
    Postgres-enum visibility_enum bevat de lowercase .value's
    (values_callable op de kolom, zelfde patroon als EducationalRole).
    """

    PUBLIC = "public"
    EDU = "edu"
    COMMUNITY = "community"


class ContentStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    REMOVED = "removed"


class TagType(str, enum.Enum):
    THEME = "theme"
    LOCATION = "location"
    PERIOD = "period"
    SENTIMENT = "sentiment"
    LANGUAGE = "language"


class TakedownStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"


class NewsletterStatus(str, enum.Enum):
    PENDING_OPT_IN = "pending_opt_in"
    SUBSCRIBED = "subscribed"
    UNSUBSCRIBED = "unsubscribed"
    BOUNCED = "bounced"


class PortalRole(str, enum.Enum):
    ADMIN = "admin"
    CURATOR = "curator"
    TEACHER = "teacher"
    STUDENT = "student"
    VISITOR = "visitor"


class EducationalRole(str, enum.Enum):
    TEACHER = "teacher"
    STUDENT = "student"
    ADMIN = "admin"
    CURATOR = "curator"
    VISITOR = "visitor"


# ============================================================================
# Models
# ============================================================================


class FoundationContent(Base):  # type: ignore[misc]
    """Content uploaded by portal users (stories, artwork, audio, etc.)."""

    __tablename__ = "foundation_content"
    __table_args__ = (
        Index("idx_fc_tenant_status", "tenant_id", "status"),
        Index("idx_fc_tenant_type_status", "tenant_id", "type", "status"),
        Index("idx_fc_tenant_created", "tenant_id", "created_at"),
        # Sprint D edu-lijstquery filtert precies op deze drie (O7, BE-MIG-014).
        Index("idx_fc_tenant_visibility_status", "tenant_id", "visibility", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    uploader_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("portal_users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    type: Mapped[ContentType] = mapped_column(
        PGEnum(ContentType, name="content_type_enum"),
        nullable=False,
    )
    title_nl: Mapped[str] = mapped_column(String(255), nullable=False)
    title_en: Mapped[str | None] = mapped_column(String(255))
    description_nl: Mapped[str | None] = mapped_column(Text)
    description_en: Mapped[str | None] = mapped_column(Text)
    body_nl: Mapped[str | None] = mapped_column(Text)
    body_en: Mapped[str | None] = mapped_column(Text)
    creator_name: Mapped[str | None] = mapped_column(String(255))
    is_anonymous: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    language: Mapped[str] = mapped_column(String(8), nullable=False, default="nl")
    privacy: Mapped[Privacy] = mapped_column(
        PGEnum(Privacy, name="privacy_enum"), default=Privacy.PUBLIC
    )
    visibility: Mapped[Visibility] = mapped_column(
        # values_callable: zelfde patroon als PortalRole/EducationalRole (zie
        # EducationalAccess.role). visibility_enum bevat de lowercase .value's
        # ('public', 'edu', 'community'); zonder values_callable serialiseert
        # SQLAlchemy de member-NAMEN en faalt elke ORM-insert (case-bug
        # uit 20260824).
        PGEnum(
            Visibility,
            name="visibility_enum",
            values_callable=lambda e: [m.value for m in e],
        ),
        default=Visibility.PUBLIC,
        server_default="public",
        nullable=False,
    )
    status: Mapped[ContentStatus] = mapped_column(
        PGEnum(ContentStatus, name="content_status_enum"),
        default=ContentStatus.PENDING,
        nullable=False,
        index=True,
    )
    rights_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    file_url: Mapped[str | None] = mapped_column(String(1024))
    file_mime: Mapped[str | None] = mapped_column(String(100))
    file_size_bytes: Mapped[int | None] = mapped_column(Integer)
    external_url: Mapped[str | None] = mapped_column(String(1024))
    ai_tagging_failed: Mapped[bool] = mapped_column(Boolean, default=False)
    moderation_score: Mapped[float | None] = mapped_column(Float)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    takedown_reason: Mapped[str | None] = mapped_column(Text)
    takedown_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    location_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    license: Mapped[str | None] = mapped_column(String(50), nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Bewust String(50) en geen enum (O4, BE-MIG-014): leeftijdsgroepen
    # verschillen per stichting en evolueren; validatie hoort bij de
    # metadata-schema's in Sprint D.
    target_age_group: Mapped[str | None] = mapped_column(String(50), nullable=True)
    metadata_: Mapped[dict[str, Any] | None] = (  # TODO(TYPE): replace Any with concrete type
        mapped_column("metadata", JSONB, nullable=True, default=dict)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    tags = relationship(
        "ContentTag",
        back_populates="content",
        cascade="all, delete-orphan",
    )


class ContentTag(Base):  # type: ignore[misc]
    """AI-generated or manual tag on a content item.

    BELANGRIJK: ContentTag heeft geen eigen tenant_id.
    Isolatie loopt altijd via JOIN op FoundationContent.
    De ORM do_orm_execute hook (ADR-004) filtert ContentTag NIET
    zelfstandig. Queries op ContentTag MOETEN altijd via JOIN of
    subquery op FoundationContent.id lopen.

    Zie ADR-029 sectie "Belangrijke isolatie-uitzonderingen".
    """

    __tablename__ = "content_tags"
    __table_args__ = (Index("idx_tag_content_type", "content_id", "tag_type"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    content_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("foundation_content.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tag_type: Mapped[TagType] = mapped_column(
        PGEnum(TagType, name="tag_type_enum"),
        nullable=False,
    )
    value: Mapped[str] = mapped_column(String(100), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    is_manual: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    content = relationship("FoundationContent", back_populates="tags")


class FoundationPortalSettings(Base):  # type: ignore[misc]
    """Portal-specific settings per tenant (white-labeling, branding)."""

    __tablename__ = "foundation_portal_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    platform_name_nl: Mapped[str] = mapped_column(String(120), nullable=False)
    platform_name_en: Mapped[str | None] = mapped_column(String(120))
    primary_color: Mapped[str] = mapped_column(String(7), default="#1a2f45")
    accent_color: Mapped[str] = mapped_column(String(7), default="#e8b86d")
    logo_url: Mapped[str | None] = mapped_column(String(1024))
    favicon_url: Mapped[str | None] = mapped_column(String(1024))
    guidelines_nl: Mapped[str | None] = mapped_column(Text)
    guidelines_en: Mapped[str | None] = mapped_column(Text)
    about_nl: Mapped[str | None] = mapped_column(Text)
    about_en: Mapped[str | None] = mapped_column(Text)
    contact_email: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class PortalUser(Base):  # type: ignore[misc]
    """Uploader account (passwordless, magic-link login).

    Separate from backend admin User (RBAC) in rbac_models.py.
    """

    __tablename__ = "portal_users"
    __table_args__ = (Index("idx_pu_tenant_email", "tenant_id", "email", unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(120))
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    role: Mapped[PortalRole] = mapped_column(
        # values_callable: de migratie 20260824_adr029_portal_v1 maakte dit enum-type
        # met de lowercase .value's ('admin', ...). Zonder values_callable serialiseert
        # SQLAlchemy de member-NAMEN ('ADMIN', ...) en faalt elke ORM-insert tegen de DB.
        PGEnum(
            PortalRole,
            name="portal_role_enum",
            values_callable=lambda e: [m.value for m in e],
        ),
        default=PortalRole.VISITOR,
        nullable=False,
    )
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    consent_given: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    consent_given_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    tokens = relationship(
        "MagicLinkToken",
        back_populates="portal_user",
        cascade="all, delete-orphan",
    )


class MagicLinkToken(Base):  # type: ignore[misc]
    """One-time token for magic-link login. SHA-256 hash stored, never raw."""

    __tablename__ = "magic_link_tokens"
    __table_args__ = (
        Index("idx_mlt_tenant_user", "tenant_id", "portal_user_id"),
        Index("idx_mlt_expires", "expires_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    portal_user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("portal_users.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    portal_user = relationship("PortalUser", back_populates="tokens")


class TakedownRequest(Base):  # type: ignore[misc]
    """NTD (Notice-and-Takedown) request: third party claims rights violation."""

    __tablename__ = "takedown_requests"
    __table_args__ = (Index("idx_td_tenant_status", "tenant_id", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("foundation_content.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requester_email: Mapped[str] = mapped_column(String(255), nullable=False)
    requester_name: Mapped[str] = mapped_column(String(255), nullable=False)
    legal_basis: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[TakedownStatus] = mapped_column(
        PGEnum(TakedownStatus, name="takedown_status_enum"),
        default=TakedownStatus.PENDING,
        nullable=False,
    )
    resolution_note: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class NewsletterSubscription(Base):  # type: ignore[misc]
    """Double opt-in newsletter subscription per tenant.

    Local storage for unsubscribe + DSAR export independence from Brevo.
    """

    __tablename__ = "newsletter_subscriptions"
    __table_args__ = (
        Index("idx_ns_tenant_email", "tenant_id", "email", unique=True),
        Index("idx_ns_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    confirm_token_hash: Mapped[str | None] = mapped_column(String(128), unique=True)
    unsubscribe_token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    status: Mapped[NewsletterStatus] = mapped_column(
        PGEnum(NewsletterStatus, name="newsletter_status_enum"),
        default=NewsletterStatus.PENDING_OPT_IN,
        nullable=False,
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    unsubscribed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consent_ip: Mapped[str | None] = mapped_column(String(45))
    consent_user_agent: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class EducationalAccess(Base):  # type: ignore[misc]
    """Educational access code for teachers and students.

    Each code grants access to study collections within a tenant.
    """

    __tablename__ = "educational_access"
    __table_args__ = (
        Index("idx_ea_tenant_code", "tenant_id", "code_hash", unique=True),
        Index("idx_ea_tenant_email", "tenant_id", "email"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    role: Mapped[EducationalRole] = mapped_column(
        # Zelfde reden als bij PortalUser.role: het DB-type bevat de lowercase
        # .value's van EducationalRole (migratie 20260824_adr029_portal_v1).
        PGEnum(
            EducationalRole,
            name="educational_role_enum",
            values_callable=lambda e: [m.value for m in e],
        ),
        default=EducationalRole.STUDENT,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    study_collections = relationship(
        "StudyCollection",
        back_populates="educational_access",
        cascade="all, delete-orphan",
    )


class StudyCollection(Base):  # type: ignore[misc]
    """A collection of study materials linked to an educational access code.

    Students/teachers with the matching educational access can view the collection.
    """

    __tablename__ = "study_collections"
    __table_args__ = (Index("idx_sc_tenant_code", "tenant_id", "educational_access_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    educational_access_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("educational_access.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Docentenomgeving (BE-EP-055): een klas van een docent. Zonder eigenaar is het een
    # klascode van een curator (oude vorm) en ziet de klas al het lesmateriaal.
    owner_portal_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("portal_users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    target_age_group: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    educational_access = relationship("EducationalAccess", back_populates="study_collections")


class FoundationContactSubmission(Base):  # type: ignore[misc]
    """Contact inquiry or support ticket submitted by a visitor (ADR-029 P2 / BE-EP-048)."""

    __tablename__ = "foundation_contact_submissions"
    __table_args__ = (
        UniqueConstraint("reference_number", name="uq_fcs_reference_number"),
        Index("idx_fcs_tenant_created", "tenant_id", "created_at"),
        Index("idx_fcs_tenant_email", "tenant_id", "email"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reference_number: Mapped[str] = mapped_column(
        String(32), nullable=False, unique=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(
        String(50), nullable=False, default="general", server_default="general"
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class FoundationDonation(Base):  # type: ignore[misc]
    """Heritage donation or adoption record (ADR-029 P2-2 / BE-EP-046)."""

    __tablename__ = "foundation_donations"
    __table_args__ = (
        UniqueConstraint("stripe_session_id", name="uq_fd_stripe_session_id"),
        Index("idx_fd_tenant_status", "tenant_id", "status"),
        Index("idx_fd_tenant_created", "tenant_id", "created_at"),
        Index("idx_fd_adopted_content", "tenant_id", "adopted_content_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3), default="EUR", server_default="EUR", nullable=False
    )
    frequency: Mapped[str] = mapped_column(
        String(20), default="once", server_default="once", nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default="pending", nullable=False
    )
    donor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_anonymous: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    adopted_content_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("foundation_content.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    stripe_session_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True, index=True
    )
    stripe_payment_intent_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True, index=True
    )
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FoundationArchiveExport(Base):  # type: ignore[misc]
    """Een BagIt-archiefexport van gepubliceerde items (ADR-029 Cat 4, BE-EP-054).

    Elke rij is een VOLLEDIGE momentopname van wat op dat moment publiek is, als zip-bestand in
    de opslag. Het controlegetal (`sha256`) maakt achteraf aantoonbaar dat het bestand in de
    opslag nog hetzelfde is als wat er toen is gemaakt.
    """

    __tablename__ = "foundation_archive_exports"
    __table_args__ = (
        CheckConstraint(
            "trigger IN ('schema', 'handmatig')", name="ck_foundation_archive_exports_trigger"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    bag_name: Mapped[str] = mapped_column(String(200), nullable=False)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False)
    payload_file_count: Mapped[int] = mapped_column(Integer, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    trigger: Mapped[str] = mapped_column(String(20), nullable=False)
    created_by_portal_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("portal_users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class FoundationTeacherApplication(Base):  # type: ignore[misc]
    """Aanvraag van een docentaccount (BE-EP-055).

    Een beheerder keurt goed of af. Bij goedkeuring krijgt de PortalUser met dit e-mailadres
    de rol TEACHER (nooit lager dan een bestaande curator- of beheerdersrol).
    """

    __tablename__ = "foundation_teacher_applications"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="ck_foundation_teacher_applications_status",
        ),
        Index("ix_foundation_teacher_applications_tenant_email", "tenant_id", "email"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    school: Mapped[str] = mapped_column(String(200), nullable=False)
    function: Mapped[str | None] = mapped_column(String(200), nullable=True)
    motivation: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    portal_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("portal_users.id", ondelete="SET NULL"),
        nullable=True,
    )
    decided_by_portal_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("portal_users.id", ondelete="SET NULL"),
        nullable=True,
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class FoundationClassLesson(Base):  # type: ignore[misc]
    """Een les (werkblad) die een docent voor een klas heeft opengezet (BE-EP-055)."""

    __tablename__ = "foundation_class_lessons"
    __table_args__ = (
        UniqueConstraint(
            "study_collection_id", "content_id", name="uq_foundation_class_lessons_klas_les"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    study_collection_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("study_collections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("foundation_content.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class FoundationStudentAnswer(Base):  # type: ignore[misc]
    """Antwoorden van een leerling op een werkblad (BE-EP-055).

    Privacy (minderjarigen): alleen een voornaam of bijnaam, geen e-mail of account. De
    leerling herkent zijn eigen inzending aan een willekeurig token in de browser; hier staat
    alleen de hash. Elke rij wordt 8 weken na `created_at` verwijderd
    (src/core/services/foundation_leerlingantwoorden.py).
    """

    __tablename__ = "foundation_student_answers"
    __table_args__ = (
        UniqueConstraint(
            "study_collection_id",
            "content_id",
            "client_token_hash",
            name="uq_foundation_student_answers_leerling",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    study_collection_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("study_collections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("foundation_content.id", ondelete="CASCADE"),
        nullable=False,
    )
    student_name: Mapped[str] = mapped_column(String(40), nullable=False)
    client_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    answers: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False, default=dict)
    teacher_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    feedback_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class FoundationContentBestand(Base):  # type: ignore[misc]
    """Extra bestanden bij een verhaal (BE-EP-057).

    Het eerste bestand van een verhaal staat, zoals altijd, in ``FoundationContent.file_url``.
    Elk volgend bestand (tot ``MAX_BESTANDEN_PER_VERHAAL`` in totaal) komt in deze tabel.
    Toegang tot een extra bestand volgt exact dezelfde regels als het hoofdbestand van het
    verhaal (status, zichtbaarheid, privacy), zie ``upload.verify_content_media_access``.
    """

    __tablename__ = "foundation_content_bestanden"
    __table_args__ = (
        UniqueConstraint("content_id", "volgorde", name="uq_foundation_content_bestanden_volgorde"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("foundation_content.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: 2 = het tweede bestand van het verhaal (het eerste staat op FoundationContent).
    volgorde: Mapped[int] = mapped_column(Integer, nullable=False)
    file_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_mime: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


#: Hoeveel bestanden een verhaal maximaal heeft: het hoofdbestand plus de extra bestanden.
MAX_BESTANDEN_PER_VERHAAL = 10
