"""
RBAC Models - Role-Based Access Control
SQLAlchemy models for roles, permissions, user-role associations, and audit logging

MULTI-TENANT UPDATE:
All models now include tenant_id for complete tenant isolation

OWASP A09 UPDATE:
Added AuditLog and SecurityAlert models for comprehensive security logging
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    DDL,
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    event,
    text,
    false,
)
from sqlalchemy.engine.default import DefaultExecutionContext
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates
from sqlalchemy.sql import func

from src.core.database.database import Base

def _klant_van_de_gebruiker(context: DefaultExecutionContext) -> int | None:
    """Vult `user_roles.tenant_id` uit de gebruiker van DEZE rij (nooit uit invoer).

    Een ORM-mutatie via `user.roles` en een kale `user_roles.insert().values(user_id, role_id)`
    kennen de kolom niet; zonder deze default liep elk van die paden stuk op de NOT NULL. Op
    PostgreSQL vangt de trigger uit de migratie hetzelfde voor rauwe SQL. Is de gebruiker niet
    zichtbaar (andere klant onder RLS, of niet bestaand), dan komt er `None` uit en weigert de
    database de rij -- er wordt dus nooit een klant geraden.
    """
    gebruiker = context.get_current_parameters().get("user_id")  # type: ignore[no-untyped-call]  # SQLAlchemy-stub: ongetypeerd
    if gebruiker is None:
        return None
    rij = context.connection.execute(
        text("SELECT tenant_id FROM users WHERE id = :gebruiker"), {"gebruiker": gebruiker}
    ).first()
    return None if rij is None else int(rij[0])


# Association table for many-to-many User-Role relationship
user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    # OP-190 deel 2: de klant van de koppeling. De samengestelde sleutels hieronder dwingen af
    # dat gebruiker, rol en koppeling bij DEZELFDE klant horen, ook voor de tabeleigenaar. Een
    # insert zonder waarde krijgt de klant van de gebruiker via de trigger uit de migratie
    # `20261009_user_roles_tenant_id`.
    Column("tenant_id", Integer, nullable=False, default=_klant_van_de_gebruiker),
    ForeignKeyConstraint(
        ["user_id", "tenant_id"], ["users.id", "users.tenant_id"], name="fk_user_roles_user_tenant"
    ),
    ForeignKeyConstraint(
        ["role_id", "tenant_id"], ["roles.id", "roles.tenant_id"], name="fk_user_roles_role_tenant"
    ),
    # Leidende tenantindex (migratie `20261026_user_roles_tenant_index`): elke query onder RLS filtert op `tenant_id`, en vrijwel
    # elke op de gebruiker. Zonder deze regel meldt `alembic check` drift.
    Index("ix_user_roles_tenant_user", "tenant_id", "user_id"),
    extend_existing=True,
)

# Schema's die uit het model worden gebouwd (`create_all`: de integratietests) krijgen dezelfde
# vultrigger als de migratieketen (`20261009_user_roles_tenant_id`). Zonder hem zou elke rauwe
# `INSERT INTO user_roles (user_id, role_id)` daar op de NOT NULL stuklopen. De tekst staat
# bewust ook in de migratie: een migratie importeert geen applicatiecode.
event.listen(
    user_roles,
    "after_create",
    DDL(  # type: ignore[no-untyped-call]  # SQLAlchemy-stub: DDL is ongetypeerd
        "CREATE OR REPLACE FUNCTION user_roles_vul_tenant_id() RETURNS trigger AS $f$ "
        "BEGIN IF NEW.tenant_id IS NULL THEN "
        "SELECT tenant_id INTO NEW.tenant_id FROM users WHERE id = NEW.user_id; "
        "END IF; RETURN NEW; END $f$ LANGUAGE plpgsql"
    ).execute_if(dialect="postgresql"),
)
event.listen(
    user_roles,
    "after_create",
    DDL(  # type: ignore[no-untyped-call]  # SQLAlchemy-stub: DDL is ongetypeerd
        "CREATE TRIGGER trg_user_roles_vul_tenant_id BEFORE INSERT ON user_roles "
        "FOR EACH ROW EXECUTE FUNCTION user_roles_vul_tenant_id()"
    ).execute_if(dialect="postgresql"),
)


#: Vier ogen (ADR-039): de sleutel in `Tenant.settings` en de standaard voor een NIEUWE omgeving
#: ("Standaardinstelling vier ogen", Rakesh 2026-10-05): AAN voor HR (Annex III), betalingen,
#: IBAN wijzigen, afboeken en overdracht aan incasso; UIT voor herinneringen en aanmaningen.
#: Hier en niet in `governance/four_eyes.py` (waar de catalogus met omschrijvingen staat): de
#: aanmaakpaden zitten in de lagen database, auth en services, en die importeren `Tenant` al
#: uit dit bestand. Een import uit governance zou daar een verboden of nieuwe koppeling zijn
#: (gemeten met `tests/architecture/test_dsm_governance_regression.py` en
#: `test_dsm_008_reclassification.py`).
FOUR_EYES_SETTINGS_KEY = "four_eyes_actions"
#: Staat deze op `True`, dan ziet een beheerder eerst de uitleg over vier ogen (ADR-039,
#: "Bestaande ondernemingen", Rakesh 2026-10-05). Gezet bij het aanmaken van een omgeving en door
#: de migratie `20261007_vier_ogen_bestaande_tenants`; weg na bevestigen door een beheerder.
FOUR_EYES_EXPLANATION_PENDING_KEY = "four_eyes_explanation_pending"
#: Merkteken van die migratie, zodat haar `downgrade()` alleen terugdraait wat zij zette.
FOUR_EYES_MIGRATION_MARK_KEY = "four_eyes_set_by_migration"
DEFAULT_FOUR_EYES_ACTIONS: tuple[str, ...] = (
    "query_hr_database",
    "analyze_skill_gap",
    "schedule_training",
    "make_payment",
    "change_iban",
    "write_off_receivable",
    "transfer_to_debt_collection",
)


def with_four_eyes_defaults(settings: object) -> dict[str, object]:
    """Instellingen voor een tenant die NU wordt aangemaakt: de standaard erbij als hij ontbreekt.

    Een sleutel die de aanmaker zelf meegaf, blijft staan. De uitlegmarkering komt er ook bij:
    de beheerder ziet bij de eerste keer inloggen wat de keuzes zijn. Bestaande tenants gaan hier
    niet doorheen; die kregen de standaard eenmalig via de migratie
    `20261007_vier_ogen_bestaande_tenants`.
    """
    uit: dict[str, object] = dict(settings) if isinstance(settings, dict) else {}
    uit.setdefault(FOUR_EYES_SETTINGS_KEY, list(DEFAULT_FOUR_EYES_ACTIONS))
    uit.setdefault(FOUR_EYES_EXPLANATION_PENDING_KEY, True)
    return uit

class Tenant(Base):  # type: ignore[misc]
    """Multi-tenant organization model for complete data isolation"""

    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)

    # Settings
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Staat dit UIT, dan weigert het schrijfpad een extern LLM-eindpunt voor deze tenant en
    # praat hij alleen met het lokale model. Standaard FALSE: de belofte "alle data blijft op
    # eigen server" hoort een schakelaar te zijn en geen gewoonte, en wie er nooit iets over
    # zei krijgt de veilige stand. Zie fase 2 van het lokaal-eerst-LLM-plan.
    # Dit gaat over eindpunten die de KLANT zelf opgeeft; Mistral (de platformverwerker, besluit
    # Rakesh 2026-10-15) valt er bewust buiten -- zie `src/core/shared/tenant_llm_keuze.py`.
    externe_providers_toegestaan: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    max_users: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    max_agents: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    max_storage_gb: Mapped[int] = mapped_column(Integer, default=5, nullable=False)

    # Subscription
    subscription_tier: Mapped[str | None] = mapped_column(
        String(50), server_default="free", default="free"
    )
    subscription_status: Mapped[str | None] = mapped_column(
        String(50), server_default="active", default="active"
    )
    stripe_customer_id: Mapped[str | None] = mapped_column(
        String(100), unique=True, nullable=True, index=True
    )

    # Metadata
    settings: Mapped[Any | None] = mapped_column(JSON, default=dict)  # TODO(TYPE): replace Any with concrete type
    metadata_: Mapped[Any | None] = mapped_column(  # TODO(TYPE): replace Any with concrete type
        "metadata", JSON, default=dict
    )  # Use metadata_ to avoid SQLAlchemy reserved word

    # Timestamps
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now()
    )

    # Agentic system fields (added 2026-02-02)
    industry: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )  # e.g., 'healthcare', 'finance'
    primary_locale: Mapped[str | None] = mapped_column(
        String(10), server_default="en_US", nullable=True
    )
    supported_locales: Mapped[Any | None] = mapped_column(  # TODO(TYPE): replace Any with concrete type
        JSON, nullable=True
    )  # ['en_US', 'nl_NL', 'hi_IN']
    primary_timezone: Mapped[str | None] = mapped_column(
        String(50), server_default="UTC", nullable=True
    )
    primary_currency: Mapped[str | None] = mapped_column(
        String(3), server_default="USD", nullable=True
    )
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)  # ISO 3166-1 alpha-2
    region: Mapped[str | None] = mapped_column(
        String(20), server_default="eu-west", nullable=True
    )  # Deployment region

    # Digital Twin configuration (added 2026-05-21)
    data_residency: Mapped[str] = mapped_column(
        String(16), server_default="global", default="global", nullable=False
    )  # "global" or "eu-only"
    twin_hard_delete_max_hours: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )  # Override for TWIN_HARD_DELETE_MAX_HOURS; NULL falls back to global config

    # Prana budget (ADR-036 D3/D7, hersteld 2026-08-15 -- SP-COUNCIL-GATE-001).
    # `PranaGuard` leest deze twee kolommen sinds maart 2026, maar ze bestonden nergens: de
    # migratie die ze aanmaakte (`archive/698adff2b1af`) is uit de keten gehaald en
    # `a10bd0ad9807` liet ze door een autogenerate vallen. Elke aanroep gaf daardoor een
    # AttributeError en `_run_within_budget` vertaalde dat naar een mislukte uitvoering --
    # de financiele rem viel om in de RUIME richting op het copilot-pad en in de STRIKTE
    # richting op het agent-pad, waar geen enkele skill meer draaide.
    # BigInteger en niet Integer: `prana_spent` loopt monotoon op zolang er geen
    # resetperiode is (OP-139), dus 2^31 is een echte bovengrens. Types en defaults zijn
    # overgenomen uit de gearchiveerde migratie, zodat een database die die ooit heeft
    # gedraaid identiek uitkomt.
    prana_budget: Mapped[int] = mapped_column(
        BigInteger, server_default="100000", nullable=False
    )
    prana_spent: Mapped[int] = mapped_column(BigInteger, server_default="0", nullable=False)

    # Relationships (RBAC only - no cross-domain to avoid circular imports)
    users = relationship("User", back_populates="tenant", cascade="all, delete-orphan")
    roles = relationship("Role", back_populates="tenant", cascade="all, delete-orphan")

    # Indexes
    __table_args__ = (
        Index("idx_tenant_slug", "slug"),
        Index("idx_tenant_domain", "domain"),
        Index("idx_tenant_is_active", "is_active"),
    )

    @validates("subscription_tier")
    def validate_subscription_tier(self, key: str, value: str | None) -> str | None:
        if value is None:
            return None
        allowed_tiers = {"free", "starter", "pro", "enterprise"}
        if value not in allowed_tiers:
            raise ValueError(f"Invalid subscription tier: {value}")
        return value

    @validates("subscription_status")
    def validate_subscription_status(self, key: str, value: str | None) -> str | None:
        if value is None:
            return None
        allowed_statuses = {
            "active",
            "trialing",
            "past_due",
            "canceled",
            "cancelled",
            "incomplete",
            "incomplete_expired",
            "unpaid",
            "suspended",
        }
        if value not in allowed_statuses:
            raise ValueError(f"Invalid subscription status: {value}")
        return value

    def __repr__(self) -> str:
        return f"<Tenant(id={self.id}, name='{self.name}', slug='{self.slug}')>"


# Auto-generate slug from name if not provided, then validate
from sqlalchemy import event

from src.core.schemas.validators import slug_from_name, validate_slug


@event.listens_for(Tenant, "before_insert")
@event.listens_for(Tenant, "before_update")
def _tenant_validate_slug(mapper: Any, connection: Any, target: Any) -> None:  # TODO(TYPE): replace Any with concrete type
    if not getattr(target, "slug", None) and getattr(target, "name", None):
        target.slug = slug_from_name(target.name)
    # Hier staat BEWUST geen `reserved=`-toets, ook al is dit de laatste plek voor de INSERT.
    # Deze listener hangt ook aan `before_update` (de decorator hierboven), en dus vuurt hij
    # op elke bijwerking van een BESTAANDE tenant. Een reserved-toets hier zou een tenant die
    # zo'n slug al draagt onbijwerkbaar maken -- het defect verschuift dan van "aanmaken
    # weigert niets" naar "een bestaande rij is niet meer te repareren", en dat raakt data die
    # er al is. De weigering hoort daarom op de AANMAAK-schema's, waar hij ook staat:
    # tenant_schemas.TenantCreate en tenant_management/crud_router.py::TenantCreate.
    if target.slug:
        validate_slug(target.slug)  # raises ValueError -> caller handles


class Role(Base):  # type: ignore[misc]
    """Role model for RBAC system with multi-tenant support"""

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Multi-tenant isolation
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now()
    )

    # Relationships
    tenant = relationship("Tenant", back_populates="roles")
    permissions = relationship(
        "RolePermission", back_populates="role", cascade="all, delete-orphan"
    )
    # Expliciete join: de koppeltabel heeft naast de enkelvoudige ook samengestelde sleutels
    # naar `roles`, en zonder dit ziet SQLAlchemy twee mogelijke paden.
    users = relationship(
        "User",
        secondary="user_roles",
        primaryjoin="Role.id == user_roles.c.role_id",
        secondaryjoin="User.id == user_roles.c.user_id",
        back_populates="roles",
    )

    # Composite indexes for multi-tenant queries
    __table_args__ = (
        Index("idx_role_tenant_name", "tenant_id", "name", unique=True),
        Index("idx_role_tenant_active", "tenant_id", "is_active"),
        # Doel van de samengestelde sleutel `user_roles (role_id, tenant_id)` (OP-190 deel 2).
        UniqueConstraint("id", "tenant_id", name="uq_roles_id_tenant"),
    )

    def __repr__(self) -> str:
        return f"<Role(id={self.id}, tenant_id={self.tenant_id}, name='{self.name}')>"


class RolePermission(Base):  # type: ignore[misc]
    """Permission model for fine-grained access control"""

    __tablename__ = "role_permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    role_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )  # STRUCTURAL FIX: Enable tenant auto-filtering
    resource: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    conditions: Mapped[Any | None] = mapped_column(  # TODO(TYPE): replace Any with concrete type
        JSON, nullable=True
    )  # For attribute-based access control
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    role = relationship("Role", back_populates="permissions")
    tenant = relationship("Tenant")  # Add tenant relationship

    # Composite unique constraint
    __table_args__ = {"sqlite_autoincrement": True}  # For compatibility

    def __repr__(self) -> str:
        return (
            f"<RolePermission(role_id={self.role_id}, "
            f"resource='{self.resource}', action='{self.action}')>"
        )


class User(Base):  # type: ignore[misc]
    """
    User model for RBAC system with multi-tenant support
    NOTE: This is the authoritative User schema for Alembic migrations.

    BACKWARDS COMPATIBILITY: Includes role_id column for legacy auth code.
    - Modern RBAC uses user_roles junction table (many-to-many)
    - Legacy code uses role_id foreign key (one-to-one)
    - Both schemas coexist during migration period
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Multi-tenant isolation
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    deletion_scheduled_for: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(
        String(100), unique=True, nullable=True, index=True
    )

    # Agentic system fields (added 2026-02-02)
    preferred_locale: Mapped[str | None] = mapped_column(
        String(10), nullable=True
    )  # User's preferred locale
    preferred_timezone: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # User's preferred timezone

    # Relationships
    tenant = relationship("Tenant", back_populates="users")

    # Many-to-Many relationship with Role via user_roles junction table
    roles = relationship(
        "Role",
        secondary=user_roles,
        primaryjoin=lambda: User.id == user_roles.c.user_id,
        secondaryjoin=lambda: Role.id == user_roles.c.role_id,
        back_populates="users",
    )

    # NOTE: UserPersona relationship removed to fix circular import.
    # Access user's agentic persona via:
    # session.query(UserPersona).filter_by(user_id=user.id).first()

    # Composite indexes for multi-tenant queries
    __table_args__ = (
        # DOEL van een samengestelde foreign key, geen gewone uniciteit.
        # `20260529b_harden_user_persona_preferences_tenant_integrity.py:58-65` maakt
        # `fk_user_persona_preferences_user_tenant` naar `users(id, tenant_id)`, en
        # PostgreSQL staat zo'n FK alleen toe met een UNIQUE constraint op precies die
        # kolommen. De migratie maakt hem aan (regel 25); dit model deed dat niet, dus op
        # elke `Base.metadata.create_all`-route -- iedere unittest -- ontbrak de constraint
        # EN daarmee de FK die de tenant-integriteit moest afdwingen.
        # Een `Index(..., unique=True)` volstaat hier NIET: PostgreSQL accepteert die wel
        # als FK-doel, maar SQLAlchemy genereert er bij `create_all` geen constraint voor.
        # Het zusje `personas` draagt de zijne al (`persona_models.py:40`).
        UniqueConstraint("id", "tenant_id", name="uq_users_id_tenant"),
        Index("idx_user_tenant_email", "tenant_id", "email", unique=True),
        Index("idx_user_tenant_active", "tenant_id", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, tenant_id={self.tenant_id}, email='{self.email}')>"


# ========================================
# SECURITY ALERT MODEL (OWASP A09)
# ========================================
# NOTE: AuditLog model is defined in src/core/governance/models.py
# SecurityAlert is kept here for RBAC-related security alerting


class SecurityAlert(Base):  # type: ignore[misc]
    """
    Security Alerts - Aggregated security incidents requiring attention

    Created when suspicious patterns are detected across multiple audit logs.
    Part of OWASP A09: Security Logging and Monitoring Failures mitigation.
    """

    __tablename__ = "security_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Multi-tenant isolation
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Alert identification
    alert_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    alert_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # SecurityEventType that triggered
    severity: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # ThreatLevel

    # Alert details
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[Any | None] = mapped_column(JSON, nullable=True)  # Structured alert data  # TODO(TYPE): replace Any with concrete type

    # Pattern detection info
    detection_rule: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )  # Rule that triggered alert
    event_count: Mapped[int | None] = mapped_column(Integer, default=1)  # Number of related events
    first_event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Source info
    source_ip: Mapped[str | None] = mapped_column(
        String(45), nullable=True
    )  # Primary IP if applicable
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    affected_resources: Mapped[Any | None] = mapped_column(  # TODO(TYPE): replace Any with concrete type
        JSON, nullable=True
    )  # List of affected resources

    # Related audit logs (JSON array of event_ids)
    related_event_ids: Mapped[Any | None] = mapped_column(JSON, nullable=True)  # TODO(TYPE): replace Any with concrete type

    # Alert status
    status: Mapped[str] = mapped_column(
        String(20), default="new", nullable=False, index=True
    )  # AlertStatus enum

    # Resolution tracking
    acknowledged_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Automated response (if any)
    auto_response_taken: Mapped[bool | None] = mapped_column(Boolean, default=False)
    auto_response_details: Mapped[Any | None] = mapped_column(JSON, nullable=True)  # TODO(TYPE): replace Any with concrete type

    # Timestamps
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now()
    )

    # Relationships
    tenant = relationship("Tenant")
    user = relationship("User", foreign_keys=[user_id])
    acknowledger = relationship("User", foreign_keys=[acknowledged_by])
    resolver = relationship("User", foreign_keys=[resolved_by])

    # Composite indexes
    __table_args__ = (
        Index("idx_alert_tenant_status", "tenant_id", "status"),
        Index("idx_alert_tenant_severity", "tenant_id", "severity"),
        Index("idx_alert_tenant_created", "tenant_id", "created_at"),
        Index("idx_alert_status_severity", "status", "severity"),
    )

    def __repr__(self) -> str:
        return (
            f"<SecurityAlert(id={self.id}, alert_type='{self.alert_type}', status='{self.status}')>"
        )
