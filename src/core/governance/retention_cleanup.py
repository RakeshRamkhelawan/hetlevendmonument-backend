"""
Retention Cleanup Service - GDPR/data retention compliance.

This module provides jurisdiction-aware data retention policies and automated
cleanup of expired data. Implements GDPR Article 5(1)(e) - Storage Limitation.

Features:
- Jurisdiction-aware retention periods (EU, US, UK, CA, AU)
- Automatic cleanup of expired data
- Audit logging of cleanup actions
- Configuration per data category
- Dry-run mode for testing
- Compliance reporting
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import cast

from sqlalchemy import select, text, delete
from sqlalchemy.engine import CursorResult, RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.tasks.dramatiq_broker import workflow_actor
import logging

from src.core.governance.services.audit_service import AuditService
from src.core.governance.retention_evidence import build_resource
from src.core.utils.best_effort import best_effort
from src.core.database.session import get_db_session
from src.core.database.tenant_query_filter import TenantFilterBypass
from src.core.governance.models import CouncilDecisionRow

logger = logging.getLogger(__name__)

# Allowlist of valid table names in retention operations.
# SECURITY: used by _validate_retention_identifier to prevent SQL injection
# if table_info values ever originate from external input.
_RETENTION_ALLOWED_TABLES: frozenset[str] = frozenset(
    {
        "users",
        "audit_logs",
        "user_consents",
        "ai_decisions",
        "user_behavior_observations",
        "twin_suggestion_log",
        "agent_critiques",
        "conversations",
        "conversation_messages",
        "cva_conversations",
    }
)

# Allowlist of valid column names in retention operations.
_RETENTION_ALLOWED_COLUMNS: frozenset[str] = frozenset(
    {
        "created_at",
        "updated_at",
        "timestamp",
        "tenant_id",
        "expires_at",
    }
)


class RetentieDoeltabelOntbreekt(ValueError):
    """Voor deze categorie is geen doeltabel gekozen (ADR-036 OP-115).

    Dit is NIET hetzelfde als "er valt niets op te ruimen". Het betekent dat niemand heeft
    vastgelegd WAAR de gegevens van deze categorie staan, en dat de opruimactie dus geen
    betekenis heeft. Tot 2026-08-30 viel zo'n categorie stil door naar `audit_logs`: de
    opruimjob meldde succes en richtte een `DELETE` op de auditketen. Vandaag inert (alle
    vijf ongemapte categorieen erven een bewaartermijn van 2555 dagen), maar wie ooit een
    kortere termijn voor bijvoorbeeld ANALYTICS instelt, verwijdert auditregels -- en een
    ontbrekende rij breekt de hashketen door AFWEZIGHEID, wat geen enkele hash-fix herstelt.

    Weigeren is hier het veilige antwoord: liever een zichtbare fout in de jobuitvoer dan een
    stille verwijdering in de verkeerde tabel.
    """


def _eis_een_tenant(tenant_id: int | None, table: str, handeling: str) -> int:
    """Weiger een retentie-operatie zonder tenant, en geef de tenant terug (ADR-036 OP-123/OP-129).

    Deze queries gaan via `text()`, dus de ORM-tenantfilter grijpt hier NIET in. De conditie stond
    achter `if self.tenant_id is not None:`; bij `None` viel de isolatie dus weg en werd het een
    operatie over ALLE tenants. Op het DELETE-pad was dat dataverlies (OP-123), op de vier
    telpaden een cross-tenant lezing (OP-129). Beide over tabellen die via de default in
    `_get_table_info` `audit_logs` zijn (OP-115).

    Geeft de tenant terug in plaats van alleen te weigeren, zodat de aanroeper een `int` heeft en
    de conditie onvoorwaardelijk in de SQL kan zetten in plaats van achter een `if`.
    """
    if tenant_id is None:
        raise ValueError(
            f"Weigering: {handeling} in '{table}' zonder tenant_id zou alle tenants raken. "
            "Construeer de service met een tenant_id, of vraag expliciet om een "
            "TenantFilterBypass als een cross-tenant operatie echt de bedoeling is "
            "(ADR-036 OP-123/OP-129)."
        )
    return tenant_id


def _validate_retention_identifier(value: str, allowed: frozenset[str], label: str) -> str:
    """Validate that a table or column name is in the allowed set.

    Raises ValueError if value is not in the allowlist.
    This prevents SQL injection if table_info is ever derived from
    external input rather than the hardcoded mapping.

    Args:
        value: The identifier to validate.
        allowed: Frozenset of permitted values.
        label: Human-readable label used in the error message (e.g. "table").

    Returns:
        The validated value unchanged.
    """
    if value not in allowed:
        raise ValueError(
            f"Invalid {label} '{value}' for retention operation. Allowed values: {sorted(allowed)}"
        )
    return value


class RetentionJurisdiction(str, Enum):
    """Jurisdictions with different retention requirements."""

    EU = "eu"  # European Union (GDPR)
    US = "us"  # United States
    UK = "uk"  # United Kingdom
    CA = "ca"  # Canada
    AU = "au"  # Australia


class DataCategory(str, Enum):
    """Categories of data with different retention rules."""

    PERSONAL_DATA = "personal_data"  # General personal data
    FINANCIAL = "financial"  # Financial records
    HEALTH = "health"  # Health/medical data
    AUDIT_LOG = "audit_log"  # Audit/compliance logs
    AI_DECISION = "ai_decision"  # AI decision records
    COOKIE_CONSENT = "cookie_consent"  # Cookie consent records
    USER_DATA = "user_data"
    ACTIVITY_LOGS = "activity_logs"
    AI_INTERACTIONS = "ai_interactions"
    DOCUMENTS = "documents"
    ANALYTICS = "analytics"
    TWIN_OBSERVATION = "twin_observation"  # Digital Twin behavior observations
    TWIN_COST_LOG = "twin_cost_log"  # Digital Twin suggestion cost logs
    CVA_CONVERSATION = "cva_conversation"  # CVA conversation records (GDPR Art. 17)
    CVA_MESSAGE = "cva_message"  # CVA conversation messages
    CVA_SESSION = "cva_session"  # CVA session records


@dataclass
class RetentionPolicy:
    """Configuration for data retention."""

    jurisdiction: RetentionJurisdiction
    category: DataCategory
    retention_days: int
    description: str | None = None
    regulatory_basis: str = field(default="")


# Default retention policies per jurisdiction and category
DEFAULT_POLICIES: dict[tuple[RetentionJurisdiction, DataCategory], RetentionPolicy] = {
    # EU policies (GDPR compliant)
    (RetentionJurisdiction.EU, DataCategory.PERSONAL_DATA): RetentionPolicy(
        jurisdiction=RetentionJurisdiction.EU,
        category=DataCategory.PERSONAL_DATA,
        retention_days=2555,  # 7 years
        description="GDPR compliant retention period",
        regulatory_basis="GDPR Art. 5(1)(e) - Storage Limitation",
    ),
    (RetentionJurisdiction.EU, DataCategory.AUDIT_LOG): RetentionPolicy(
        jurisdiction=RetentionJurisdiction.EU,
        category=DataCategory.AUDIT_LOG,
        retention_days=2555,  # 7 years (Dutch tax law requirement)
        description="Dutch tax law requires 7 year retention",
        regulatory_basis="GDPR Art. 5(1)(e) + Dutch Tax Law",
    ),
    (RetentionJurisdiction.EU, DataCategory.COOKIE_CONSENT): RetentionPolicy(
        jurisdiction=RetentionJurisdiction.EU,
        category=DataCategory.COOKIE_CONSENT,
        retention_days=2555,  # 7 years
        description="GDPR Art. 7 requires proof of consent",
        regulatory_basis="GDPR Art. 7 + Art. 5(1)(e)",
    ),
    (RetentionJurisdiction.EU, DataCategory.FINANCIAL): RetentionPolicy(
        jurisdiction=RetentionJurisdiction.EU,
        category=DataCategory.FINANCIAL,
        retention_days=3650,  # 10 years
        description="Financial records retention",
        regulatory_basis="GDPR + EU Accounting Directive",
    ),
    (RetentionJurisdiction.EU, DataCategory.HEALTH): RetentionPolicy(
        jurisdiction=RetentionJurisdiction.EU,
        category=DataCategory.HEALTH,
        retention_days=5475,  # 15 years
        description="Health data requires longer retention",
        regulatory_basis="GDPR + Medical Records Retention",
    ),
    (RetentionJurisdiction.EU, DataCategory.AI_DECISION): RetentionPolicy(
        jurisdiction=RetentionJurisdiction.EU,
        category=DataCategory.AI_DECISION,
        retention_days=2555,  # 7 years
        description="AI Act requires decision logging",
        regulatory_basis="EU AI Act Art. 12 + GDPR Art. 22",
    ),
    # US policies
    (RetentionJurisdiction.US, DataCategory.PERSONAL_DATA): RetentionPolicy(
        jurisdiction=RetentionJurisdiction.US,
        category=DataCategory.PERSONAL_DATA,
        retention_days=2190,  # 6 years (typical statute)
        description="Standard US retention period",
        regulatory_basis="State Privacy Laws",
    ),
    (RetentionJurisdiction.US, DataCategory.AUDIT_LOG): RetentionPolicy(
        jurisdiction=RetentionJurisdiction.US,
        category=DataCategory.AUDIT_LOG,
        retention_days=2555,  # 7 years
        description="SOX compliance",
        regulatory_basis="Sarbanes-Oxley Act",
    ),
    (RetentionJurisdiction.US, DataCategory.COOKIE_CONSENT): RetentionPolicy(
        jurisdiction=RetentionJurisdiction.US,
        category=DataCategory.COOKIE_CONSENT,
        retention_days=1095,  # 3 years
        description="CCPA/CPRA compliant",
        regulatory_basis="CCPA/CPRA",
    ),
    (RetentionJurisdiction.US, DataCategory.FINANCIAL): RetentionPolicy(
        jurisdiction=RetentionJurisdiction.US,
        category=DataCategory.FINANCIAL,
        retention_days=2555,  # 7 years
        description="IRS requirements",
        regulatory_basis="IRS Publication 583",
    ),
    (RetentionJurisdiction.US, DataCategory.HEALTH): RetentionPolicy(
        jurisdiction=RetentionJurisdiction.US,
        category=DataCategory.HEALTH,
        retention_days=2555,  # 7 years (HIPAA)
        description="HIPAA retention requirements",
        regulatory_basis="HIPAA 45 CFR 164.530(j)",
    ),
    (RetentionJurisdiction.US, DataCategory.AI_DECISION): RetentionPolicy(
        jurisdiction=RetentionJurisdiction.US,
        category=DataCategory.AI_DECISION,
        retention_days=1825,  # 5 years
        description="AI decision record retention",
        regulatory_basis="State AI Regulations",
    ),
    # UK policies (similar to EU post-Brexit)
    (RetentionJurisdiction.UK, DataCategory.PERSONAL_DATA): RetentionPolicy(
        jurisdiction=RetentionJurisdiction.UK,
        category=DataCategory.PERSONAL_DATA,
        retention_days=2555,  # 7 years
        description="UK GDPR compliant",
        regulatory_basis="UK GDPR Art. 5(1)(e)",
    ),
    (RetentionJurisdiction.UK, DataCategory.AUDIT_LOG): RetentionPolicy(
        jurisdiction=RetentionJurisdiction.UK,
        category=DataCategory.AUDIT_LOG,
        retention_days=2555,  # 7 years
        description="UK Companies Act requirements",
        regulatory_basis="Companies Act 2006",
    ),
    (RetentionJurisdiction.UK, DataCategory.COOKIE_CONSENT): RetentionPolicy(
        jurisdiction=RetentionJurisdiction.UK,
        category=DataCategory.COOKIE_CONSENT,
        retention_days=2555,  # 7 years
        description="UK GDPR Art. 7",
        regulatory_basis="UK GDPR Art. 7",
    ),
    (RetentionJurisdiction.UK, DataCategory.FINANCIAL): RetentionPolicy(
        jurisdiction=RetentionJurisdiction.UK,
        category=DataCategory.FINANCIAL,
        retention_days=2555,  # 7 years
        description="HMRC requirements",
        regulatory_basis="HMRC Guidelines",
    ),
    (RetentionJurisdiction.UK, DataCategory.HEALTH): RetentionPolicy(
        jurisdiction=RetentionJurisdiction.UK,
        category=DataCategory.HEALTH,
        retention_days=2555,  # 7 years
        description="NHS retention standards",
        regulatory_basis="NHS Records Management",
    ),
    (RetentionJurisdiction.UK, DataCategory.AI_DECISION): RetentionPolicy(
        jurisdiction=RetentionJurisdiction.UK,
        category=DataCategory.AI_DECISION,
        retention_days=2555,  # 7 years
        description="AI decision logging",
        regulatory_basis="UK GDPR + AI Guidance",
    ),
    # Canada policies
    (RetentionJurisdiction.CA, DataCategory.PERSONAL_DATA): RetentionPolicy(
        jurisdiction=RetentionJurisdiction.CA,
        category=DataCategory.PERSONAL_DATA,
        retention_days=2555,  # 7 years
        description="PIPEDA compliant",
        regulatory_basis="PIPEDA Principle 4.5",
    ),
    (RetentionJurisdiction.CA, DataCategory.AUDIT_LOG): RetentionPolicy(
        jurisdiction=RetentionJurisdiction.CA,
        category=DataCategory.AUDIT_LOG,
        retention_days=2555,  # 7 years
        description="CRA requirements",
        regulatory_basis="CRA IT Guidelines",
    ),
    (RetentionJurisdiction.CA, DataCategory.COOKIE_CONSENT): RetentionPolicy(
        jurisdiction=RetentionJurisdiction.CA,
        category=DataCategory.COOKIE_CONSENT,
        retention_days=2555,  # 7 years
        description="PIPEDA consent records",
        regulatory_basis="PIPEDA Principle 4.5",
    ),
    (RetentionJurisdiction.CA, DataCategory.FINANCIAL): RetentionPolicy(
        jurisdiction=RetentionJurisdiction.CA,
        category=DataCategory.FINANCIAL,
        retention_days=2555,  # 7 years
        description="CRA tax records",
        regulatory_basis="CRA Income Tax Act",
    ),
    (RetentionJurisdiction.CA, DataCategory.HEALTH): RetentionPolicy(
        jurisdiction=RetentionJurisdiction.CA,
        category=DataCategory.HEALTH,
        retention_days=5475,  # 15 years
        description="Provincial health records",
        regulatory_basis="Provincial Health Laws",
    ),
    (RetentionJurisdiction.CA, DataCategory.AI_DECISION): RetentionPolicy(
        jurisdiction=RetentionJurisdiction.CA,
        category=DataCategory.AI_DECISION,
        retention_days=2555,  # 7 years
        description="AI decision records",
        regulatory_basis="PIPEDA + AI Guidelines",
    ),
    # Australia policies
    (RetentionJurisdiction.AU, DataCategory.PERSONAL_DATA): RetentionPolicy(
        jurisdiction=RetentionJurisdiction.AU,
        category=DataCategory.PERSONAL_DATA,
        retention_days=2555,  # 7 years
        description="Privacy Act compliant",
        regulatory_basis="Privacy Act 1988 (APP 11)",
    ),
    (RetentionJurisdiction.AU, DataCategory.AUDIT_LOG): RetentionPolicy(
        jurisdiction=RetentionJurisdiction.AU,
        category=DataCategory.AUDIT_LOG,
        retention_days=2555,  # 7 years
        description="ATO requirements",
        regulatory_basis="ATO Record Keeping",
    ),
    (RetentionJurisdiction.AU, DataCategory.COOKIE_CONSENT): RetentionPolicy(
        jurisdiction=RetentionJurisdiction.AU,
        category=DataCategory.COOKIE_CONSENT,
        retention_days=2555,  # 7 years
        description="Privacy Act consent records",
        regulatory_basis="Privacy Act 1988",
    ),
    (RetentionJurisdiction.AU, DataCategory.FINANCIAL): RetentionPolicy(
        jurisdiction=RetentionJurisdiction.AU,
        category=DataCategory.FINANCIAL,
        retention_days=2555,  # 7 years
        description="ATO tax records",
        regulatory_basis="ATO Taxation Rulings",
    ),
    (RetentionJurisdiction.AU, DataCategory.HEALTH): RetentionPolicy(
        jurisdiction=RetentionJurisdiction.AU,
        category=DataCategory.HEALTH,
        retention_days=2555,  # 7 years
        description="My Health Records retention",
        regulatory_basis="My Health Records Act",
    ),
    (RetentionJurisdiction.AU, DataCategory.AI_DECISION): RetentionPolicy(
        jurisdiction=RetentionJurisdiction.AU,
        category=DataCategory.AI_DECISION,
        retention_days=2555,  # 7 years
        description="AI decision records",
        regulatory_basis="Privacy Act + AI Ethics",
    ),
    # Digital Twin observations (GDPR Art. 5(1)(e) - 90 days)
    # retention_days=0 because expires_at already encodes the retention boundary
    (RetentionJurisdiction.EU, DataCategory.TWIN_OBSERVATION): RetentionPolicy(
        jurisdiction=RetentionJurisdiction.EU,
        category=DataCategory.TWIN_OBSERVATION,
        retention_days=0,
        description="Digital Twin behavior observations",
        regulatory_basis="GDPR Art. 5(1)(e) - Storage Limitation",
    ),
    (RetentionJurisdiction.US, DataCategory.TWIN_OBSERVATION): RetentionPolicy(
        jurisdiction=RetentionJurisdiction.US,
        category=DataCategory.TWIN_OBSERVATION,
        retention_days=0,
        description="Digital Twin behavior observations",
        regulatory_basis="State Privacy Laws",
    ),
    (RetentionJurisdiction.UK, DataCategory.TWIN_OBSERVATION): RetentionPolicy(
        jurisdiction=RetentionJurisdiction.UK,
        category=DataCategory.TWIN_OBSERVATION,
        retention_days=0,
        description="Digital Twin behavior observations",
        regulatory_basis="UK GDPR Art. 5(1)(e)",
    ),
    (RetentionJurisdiction.CA, DataCategory.TWIN_OBSERVATION): RetentionPolicy(
        jurisdiction=RetentionJurisdiction.CA,
        category=DataCategory.TWIN_OBSERVATION,
        retention_days=0,
        description="Digital Twin behavior observations",
        regulatory_basis="PIPEDA Principle 4.5",
    ),
    (RetentionJurisdiction.AU, DataCategory.TWIN_OBSERVATION): RetentionPolicy(
        jurisdiction=RetentionJurisdiction.AU,
        category=DataCategory.TWIN_OBSERVATION,
        retention_days=0,
        description="Digital Twin behavior observations",
        regulatory_basis="Privacy Act 1988",
    ),
    # Digital Twin cost logs (Dutch tax law art. 52 AWR - 7 years)
    # retention_days=0 because expires_at already encodes the retention boundary
    (RetentionJurisdiction.EU, DataCategory.TWIN_COST_LOG): RetentionPolicy(
        jurisdiction=RetentionJurisdiction.EU,
        category=DataCategory.TWIN_COST_LOG,
        retention_days=0,
        description="Digital Twin suggestion cost logs",
        regulatory_basis="Dutch Tax Law Art. 52 AWR + GDPR Art. 5(1)(e)",
    ),
    (RetentionJurisdiction.US, DataCategory.TWIN_COST_LOG): RetentionPolicy(
        jurisdiction=RetentionJurisdiction.US,
        category=DataCategory.TWIN_COST_LOG,
        retention_days=0,
        description="Digital Twin suggestion cost logs",
        regulatory_basis="IRS Publication 583",
    ),
    (RetentionJurisdiction.UK, DataCategory.TWIN_COST_LOG): RetentionPolicy(
        jurisdiction=RetentionJurisdiction.UK,
        category=DataCategory.TWIN_COST_LOG,
        retention_days=0,
        description="Digital Twin suggestion cost logs",
        regulatory_basis="Companies Act 2006",
    ),
    (RetentionJurisdiction.CA, DataCategory.TWIN_COST_LOG): RetentionPolicy(
        jurisdiction=RetentionJurisdiction.CA,
        category=DataCategory.TWIN_COST_LOG,
        retention_days=0,
        description="Digital Twin suggestion cost logs",
        regulatory_basis="CRA IT Guidelines",
    ),
    (RetentionJurisdiction.AU, DataCategory.TWIN_COST_LOG): RetentionPolicy(
        jurisdiction=RetentionJurisdiction.AU,
        category=DataCategory.TWIN_COST_LOG,
        retention_days=0,
        description="Digital Twin suggestion cost logs",
        regulatory_basis="ATO Record Keeping",
    ),
}


def get_default_policy(
    jurisdiction: RetentionJurisdiction, category: DataCategory
) -> RetentionPolicy:
    """Get the default retention policy for a jurisdiction and category.

    Args:
        jurisdiction: The legal jurisdiction
        category: The category of data

    Returns:
        RetentionPolicy with default settings
    """
    key = (jurisdiction, category)
    if key in DEFAULT_POLICIES:
        return DEFAULT_POLICIES[key]

    # Fallback to EU policy for unknown combinations
    return DEFAULT_POLICIES.get(
        (RetentionJurisdiction.EU, category),
        RetentionPolicy(
            jurisdiction=jurisdiction,
            category=category,
            retention_days=2555,
            description="Default retention policy",
            regulatory_basis="GDPR Art. 5(1)(e)",
        ),
    )


@dataclass
class CleanupResult:
    """Result of a cleanup operation."""

    records_deleted: int
    category: str
    jurisdiction: str
    cutoff_date: datetime
    regulatory_basis: str
    dry_run: bool = False
    tenant_id: int | None = None
    execution_time_ms: int | None = None


@dataclass
class RetentionReport:
    """Compliance report for data retention."""

    total_records: int
    records_by_category: dict[str, int]
    compliance_status: str
    upcoming_cleanups: list[dict[str, object]]
    jurisdiction: str
    generated_at: datetime
    #: Categorieen die niet in het rapport konden worden meegeteld omdat er geen doeltabel
    #: voor gekozen is (ADR-036 OP-115). Tot 2026-08-30 telden die stil de rijen van
    #: `audit_logs` mee -- voor ELKE ongemapte categorie dezelfde tabel, dus zowel
    #: `total_records` als de uitsplitsing per categorie waren onjuist.
    categories_without_table: list[str] = field(default_factory=list)


class RetentionCleanupService:
    """Service for managing data retention and cleanup.

    Implements GDPR Article 5(1)(e) - Storage Limitation:
    "kept in a form which permits identification of data subjects for no longer
    than is necessary for the purposes for which the personal data are processed"
    """

    def __init__(self, db: AsyncSession, tenant_id: int | None = None) -> None:
        """Initialize the cleanup service.

        Args:
            db: Database session
            tenant_id: Optional tenant ID for multi-tenant isolation
        """
        self.db = db
        self.tenant_id = tenant_id

    async def cleanup_expired_data(
        self,
        category: DataCategory,
        jurisdiction: RetentionJurisdiction,
        dry_run: bool = False,
        custom_retention_days: int | None = None,
    ) -> CleanupResult:
        """Clean up data that has exceeded its retention period.

        Args:
            category: The category of data to clean up
            jurisdiction: The jurisdiction for retention rules
            dry_run: If True, only count records without deleting
            custom_retention_days: Override default retention period

        Returns:
            CleanupResult with details of the operation
        """
        import time

        start_time = time.time()

        # Get retention policy
        policy = get_default_policy(jurisdiction, category)
        retention_days = custom_retention_days or policy.retention_days

        # Calculate cutoff date
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)

        # Determine table and column based on category
        table_info = self._get_table_info(category)

        # Build and execute query
        if dry_run:
            records_deleted = await self._count_expired_records(table_info, cutoff_date)
        else:
            records_deleted = await self._delete_expired_records(table_info, cutoff_date)

            # Create audit log entry
            await self._create_audit_log(
                category=category,
                jurisdiction=jurisdiction,
                records_deleted=records_deleted,
                cutoff_date=cutoff_date,
                regulatory_basis=policy.regulatory_basis,
            )

        execution_time_ms = int((time.time() - start_time) * 1000)

        return CleanupResult(
            records_deleted=records_deleted,
            category=category.value,
            jurisdiction=jurisdiction.value,
            cutoff_date=cutoff_date,
            regulatory_basis=policy.regulatory_basis,
            dry_run=dry_run,
            tenant_id=self.tenant_id,
            execution_time_ms=execution_time_ms,
        )

    def _get_table_info(self, category: DataCategory) -> dict[str, str]:
        """Get database table information for a category.

        Args:
            category: Data category

        Returns:
            Dictionary with table_name, date_column, tenant_column
        """
        # Map categories to database tables (only existing tables)
        table_mapping = {
            DataCategory.PERSONAL_DATA: {
                "table": "users",
                "date_column": "created_at",
                "tenant_column": "tenant_id",
            },
            DataCategory.AUDIT_LOG: {
                "table": "audit_logs",
                "date_column": "timestamp",  # Note: audit_logs uses timestamp, not created_at
                "tenant_column": "tenant_id",
            },
            DataCategory.COOKIE_CONSENT: {
                "table": "user_consents",
                "date_column": "updated_at",
                "tenant_column": "tenant_id",
            },
            DataCategory.AI_DECISION: {
                "table": "ai_decisions",
                "date_column": "created_at",
                "tenant_column": "tenant_id",
            },
            DataCategory.TWIN_OBSERVATION: {
                "table": "user_behavior_observations",
                "date_column": "expires_at",
                "tenant_column": "tenant_id",
            },
            DataCategory.TWIN_COST_LOG: {
                "table": "twin_suggestion_log",
                "date_column": "expires_at",
                "tenant_column": "tenant_id",
            },
            DataCategory.CVA_CONVERSATION: {
                "table": "conversations",
                "date_column": "updated_at",
                "tenant_column": "tenant_id",
            },
            DataCategory.CVA_MESSAGE: {
                "table": "conversation_messages",
                "date_column": "timestamp",
                "tenant_column": "tenant_id",
            },
            DataCategory.CVA_SESSION: {
                "table": "cva_conversations",
                "date_column": "created_at",
                "tenant_column": "tenant_id",
            },
        }

        # GEEN `.get(category, {"table": "audit_logs", ...})` (ADR-036 OP-115).
        #
        # Die default stuurde elke niet-gemapte categorie naar de auditketen. Vijf categorieen
        # die de geplande job WEL doorloopt stonden niet in de afbeelding hierboven, en
        # FINANCIAL en HEALTH wezen er zelfs expliciet naar. De job meldde daarop succes voor
        # een opruimactie die of niets deed of het verkeerde deed.
        #
        # Weigeren in plaats van gokken. De aanroeper (`src/core/jobs/retention_cleanup_job.py`)
        # vangt dit per categorie op en rapporteert het als overgeslagen, dus een ontbrekende
        # doeltabel legt de job niet stil -- hij wordt alleen zichtbaar.
        try:
            return table_mapping[category]
        except KeyError:
            raise RetentieDoeltabelOntbreekt(
                f"Retentie voor categorie '{category.value}' is niet uitgevoerd: er is geen "
                "doeltabel en datumkolom voor gekozen. Vul `table_mapping` in "
                "`RetentionCleanupService._get_table_info` aan en breid "
                "`_RETENTION_ALLOWED_TABLES` mee uit. Terugvallen op `audit_logs` is geen "
                "optie: dat verwijdert auditregels (ADR-036 OP-115)."
            ) from None

    async def _count_expired_records(
        self,
        table_info: dict[str, str],
        cutoff_date: datetime,
    ) -> int:
        """Count records that would be deleted.

        Args:
            table_info: Table configuration
            cutoff_date: Date before which records are expired

        Returns:
            Number of records that would be deleted
        """
        table = _validate_retention_identifier(
            table_info["table"], _RETENTION_ALLOWED_TABLES, "table"
        )
        date_col = _validate_retention_identifier(
            table_info["date_column"], _RETENTION_ALLOWED_COLUMNS, "date column"
        )
        tenant_col = _validate_retention_identifier(
            table_info["tenant_column"], _RETENTION_ALLOWED_COLUMNS, "tenant column"
        )

        tenant = _eis_een_tenant(self.tenant_id, table, "tellen")

        query = f"""
            SELECT COUNT(*) as count
            FROM {table}
            WHERE {date_col} < :cutoff_date
            AND {tenant_col} = :tenant_id
        """  # nosec B608

        params: dict[str, int | datetime] = {
            "cutoff_date": cutoff_date,
            "tenant_id": tenant,
        }

        result = await self.db.execute(text(query), params)
        row = result.fetchone()
        return int(row[0]) if row else 0

    def get_retention_period(
        self,
        category: DataCategory,
        jurisdiction: RetentionJurisdiction,
    ) -> int:
        """Get the retention period in days for a category and jurisdiction.

        Args:
            category: The data category
            jurisdiction: The legal jurisdiction

        Returns:
            Retention period in days
        """
        policy = get_default_policy(jurisdiction, category)
        return policy.retention_days

    async def count_expiring_soon(
        self,
        category: DataCategory,
        jurisdiction: RetentionJurisdiction,
        days: int = 7,
    ) -> int:
        """Count records that will expire within the specified days.

        Args:
            category: The data category
            jurisdiction: The legal jurisdiction
            days: Number of days to look ahead (default 7)

        Returns:
            Number of records expiring soon
        """
        policy = get_default_policy(jurisdiction, category)
        table_info = self._get_table_info(category)

        # Calculate the date range for "expiring soon"
        retention_cutoff = datetime.now(timezone.utc) - timedelta(days=policy.retention_days)
        upcoming_cutoff = retention_cutoff + timedelta(days=days)

        table = _validate_retention_identifier(
            table_info["table"], _RETENTION_ALLOWED_TABLES, "table"
        )
        date_col = _validate_retention_identifier(
            table_info["date_column"], _RETENTION_ALLOWED_COLUMNS, "date column"
        )
        tenant_col = _validate_retention_identifier(
            table_info["tenant_column"], _RETENTION_ALLOWED_COLUMNS, "tenant column"
        )

        tenant = _eis_een_tenant(self.tenant_id, table, "tellen")

        query = f"""
            SELECT COUNT(*)
            FROM {table}
            WHERE {date_col} < :upcoming_cutoff
            AND {date_col} >= :retention_cutoff
            AND {tenant_col} = :tenant_id
        """  # nosec B608

        params: dict[str, int | datetime] = {
            "upcoming_cutoff": upcoming_cutoff,
            "retention_cutoff": retention_cutoff,
            "tenant_id": tenant,
        }

        result = await self.db.execute(text(query), params)
        row = result.fetchone()
        return int(row[0]) if row else 0

    async def _delete_expired_records(
        self,
        table_info: dict[str, str],
        cutoff_date: datetime,
    ) -> int:
        """Delete expired records.

        Args:
            table_info: Table configuration
            cutoff_date: Date before which records are expired

        Returns:
            Number of records deleted
        """
        table = _validate_retention_identifier(
            table_info["table"], _RETENTION_ALLOWED_TABLES, "table"
        )
        date_col = _validate_retention_identifier(
            table_info["date_column"], _RETENTION_ALLOWED_COLUMNS, "date column"
        )
        tenant_col = _validate_retention_identifier(
            table_info["tenant_column"], _RETENTION_ALLOWED_COLUMNS, "tenant column"
        )

        # WEIGEREN ZONDER TENANT (ADR-036 OP-123).
        #
        # Hier stond `if self.tenant_id is not None:` om de conditie toe te voegen. Bij `None`
        # werd dit dus een DELETE over ALLE tenants. De query gaat via `text()`, dus de
        # ORM-tenantfilter grijpt hier niet in -- die `if` was de enige isolatie.
        #
        # De vijf categorieen die de dagelijkse job opruimt vallen door naar de default in
        # `_get_table_info`, en die wijst naar `audit_logs` (OP-115). De latente route wees dus
        # naar de auditketen zelf, en een verwijderde rij breekt die door AFWEZIGHEID.
        #
        # Een cross-tenant DELETE hoort een expliciete `TenantFilterBypass` te vragen. Het
        # TEL-pad blijft bewust ongemoeid: dat verwijdert niets.
        if self.tenant_id is None:
            raise ValueError(
                f"Weigering: verwijderen uit '{table}' zonder tenant_id zou alle tenants raken. "
                "Construeer de service met een tenant_id, of vraag expliciet om een "
                "TenantFilterBypass als een cross-tenant opruiming echt de bedoeling is "
                "(ADR-036 OP-123)."
            )

        query = f"""
            DELETE FROM {table}
            WHERE {date_col} < :cutoff_date
            AND {tenant_col} = :tenant_id
        """  # nosec B608

        params: dict[str, int | datetime] = {
            "cutoff_date": cutoff_date,
            "tenant_id": self.tenant_id,
        }

        result = await self.db.execute(text(query), params)
        await self.db.commit()
        # Cast to CursorResult to access rowcount attribute
        cursor_result = cast(CursorResult[RowMapping], result)
        return cursor_result.rowcount or 0

    async def _create_audit_log(
        self,
        category: DataCategory,
        jurisdiction: RetentionJurisdiction,
        records_deleted: int,
        cutoff_date: datetime,
        regulatory_basis: str,
    ) -> None:
        """Create audit log entry for cleanup operation.

        Args:
            category: Data category that was cleaned
            jurisdiction: Jurisdiction for the cleanup
            records_deleted: Number of records deleted
            cutoff_date: Cutoff date used
            regulatory_basis: Legal basis for the cleanup
        """
        # VIA AuditService, NIET met rauwe SQL (ADR-036 OP-108).
        #
        # Dit is de zwaarste van de twee rauwe schrijvers: deze actor draait DAGELIJKS voor elke
        # tenant, over vijf jurisdicties en vijf categorieen. Elke rij liet `audit_hash` en
        # `previous_hash` leeg, dus elke omgeving liep hier gegarandeerd tegenaan en de
        # ketenverificatie kwam nooit voorbij de eerste opruimronde.
        #
        # VELDAFBEELDING -- `log_event` heeft GEEN `details`-parameter. Een naieve omzetting zou
        # categorie, jurisdictie, aantal, afkapdatum en grondslag stil laten vallen, en dat is
        # precies het art.-5(1)(e)-bewijs waarvoor deze regel bestaat. Ze gaan daarom naar
        # `metadata` (kolom `event_metadata`), samen met wat daar al stond.
        cutoff_iso = cutoff_date.isoformat()
        bewijs: dict[str, object] = {
            "category": category.value,
            "jurisdiction": jurisdiction.value,
            "records_deleted": records_deleted,
            "cutoff_date": cutoff_iso,
            "regulatory_basis": regulatory_basis,
        }

        # `records_deleted`/`cutoff_date`/`regulatory_basis` staan buiten `_compute_hash`
        # (alleen `category`/`jurisdiction` zitten via `resource` gedekt) -- ADR-036 OP-121.
        # Zelfde binden-in-`resource`-patroon als H-2 (`hitl_evidence.py`), non-destructief.
        resource = build_resource(
            category=category.value,
            jurisdiction=jurisdiction.value,
            records_deleted=records_deleted,
            cutoff_date=cutoff_iso,
            regulatory_basis=regulatory_basis,
        )

        async with best_effort("retention_cleanup_audit_log", db_session=self.db):
            await AuditService.log_event(
                db=self.db,
                event_type="gdpr_retention",
                severity="info",
                source_ip="system",
                endpoint="/api/gdpr/retention-cleanup",
                description=f"Retention cleanup for {category.value} in {jurisdiction.value}",
                user_id=None,  # System action
                tenant_id=self.tenant_id,
                action="DATA_RETENTION_CLEANUP",
                resource=resource,
                metadata=bewijs,
            )
            # `log_event` doet alleen `flush()`; zonder deze commit is de auditregel niet
            # duurzaam. Bewust `log_event` en niet `log_action`: die laatste schrijft bij
            # `tenant_id=None` HELEMAAL GEEN rij, en `self.tenant_id` mag None zijn.
            await self.db.commit()

    async def run_all_cleanups(
        self,
        jurisdiction: RetentionJurisdiction,
        dry_run: bool = False,
    ) -> list[CleanupResult]:
        """Run cleanup for all data categories.

        Args:
            jurisdiction: Jurisdiction for retention rules
            dry_run: If True, only count records without deleting

        Returns:
            List of CleanupResult for each category
        """
        results: list[CleanupResult] = []

        for category in DataCategory:
            result = await self.cleanup_expired_data(
                category=category,
                jurisdiction=jurisdiction,
                dry_run=dry_run,
            )
            results.append(result)

        return results

    async def generate_retention_report(
        self,
        jurisdiction: RetentionJurisdiction,
    ) -> RetentionReport:
        """Generate a retention compliance report.

        Args:
            jurisdiction: Jurisdiction for the report

        Returns:
            RetentionReport with compliance statistics
        """
        records_by_category: dict[str, int] = {}
        upcoming_cleanups: list[dict[str, object]] = []
        total_records = 0

        zonder_tabel: list[str] = []
        for category in DataCategory:
            policy = get_default_policy(jurisdiction, category)
            try:
                table_info = self._get_table_info(category)
            except RetentieDoeltabelOntbreekt:
                # Overslaan en benoemen, niet meetellen (ADR-036 OP-115). Meetellen zou hier
                # betekenen: de rijen van `audit_logs` optellen bij een categorie die daar
                # niets mee te maken heeft.
                zonder_tabel.append(category.value)
                continue

            # Count total records
            count = await self._count_all_records(table_info)
            records_by_category[category.value] = count
            total_records += count

            # Check upcoming cleanups (data expiring within 30 days)
            upcoming_cutoff = datetime.now(timezone.utc) + timedelta(days=30)
            retention_cutoff = datetime.now(timezone.utc) - timedelta(days=policy.retention_days)
            near_expiry_count = await self._count_near_expiry_records(
                table_info, retention_cutoff, upcoming_cutoff
            )

            if near_expiry_count > 0:
                upcoming_cleanups.append(
                    {
                        "category": category.value,
                        "records_approaching_retention": near_expiry_count,
                        "retention_deadline": retention_cutoff.isoformat(),
                    }
                )

        # Determine compliance status
        compliance_status = "compliant"
        if any(cast(int, c["records_approaching_retention"]) > 1000 for c in upcoming_cleanups):
            compliance_status = "attention_required"

        return RetentionReport(
            total_records=total_records,
            records_by_category=records_by_category,
            compliance_status=compliance_status,
            upcoming_cleanups=upcoming_cleanups,
            jurisdiction=jurisdiction.value,
            generated_at=datetime.now(timezone.utc),
            categories_without_table=zonder_tabel,
        )

    async def _count_all_records(self, table_info: dict[str, str]) -> int:
        """Count all records in a table.

        Args:
            table_info: Table configuration

        Returns:
            Total record count
        """
        table = _validate_retention_identifier(
            table_info["table"], _RETENTION_ALLOWED_TABLES, "table"
        )
        tenant_col = _validate_retention_identifier(
            table_info["tenant_column"], _RETENTION_ALLOWED_COLUMNS, "tenant column"
        )

        tenant = _eis_een_tenant(self.tenant_id, table, "tellen")

        query = f"SELECT COUNT(*) FROM {table} WHERE {tenant_col} = :tenant_id"  # nosec B608
        params: dict[str, object] = {"tenant_id": tenant}

        result = await self.db.execute(text(query), params)
        row = result.fetchone()
        return int(row[0]) if row else 0

    async def _count_near_expiry_records(
        self,
        table_info: dict[str, str],
        retention_cutoff: datetime,
        upcoming_cutoff: datetime,
    ) -> int:
        """Count records approaching retention limit.

        Args:
            table_info: Table configuration
            retention_cutoff: Date when retention expires
            upcoming_cutoff: Date for upcoming window

        Returns:
            Number of records approaching expiry
        """
        table = _validate_retention_identifier(
            table_info["table"], _RETENTION_ALLOWED_TABLES, "table"
        )
        date_col = _validate_retention_identifier(
            table_info["date_column"], _RETENTION_ALLOWED_COLUMNS, "date column"
        )
        tenant_col = _validate_retention_identifier(
            table_info["tenant_column"], _RETENTION_ALLOWED_COLUMNS, "tenant column"
        )

        tenant = _eis_een_tenant(self.tenant_id, table, "tellen")

        query = f"""
            SELECT COUNT(*)
            FROM {table}
            WHERE {date_col} < :upcoming_cutoff
            AND {date_col} >= :retention_cutoff
            AND {tenant_col} = :tenant_id
        """  # nosec B608

        params: dict[str, object] = {
            "upcoming_cutoff": upcoming_cutoff,
            "retention_cutoff": retention_cutoff,
            "tenant_id": tenant,
        }

        result = await self.db.execute(text(query), params)
        row = result.fetchone()
        return int(row[0]) if row else 0


RETENTION_DAYS_COUNCIL = 395  # ~13 maanden -- AI Act audit retention
BATCH_SIZE = 1000


@workflow_actor(
    queue_name="cleanup",
    max_retries=3,
    time_limit=600_000,
    actor_name="cleanup_council_decisions",
)
def cleanup_council_decisions() -> None:
    """Sync wrapper -- thread-safe, geen AsyncIO middleware nodig.

    NOTE: asyncio.run() maakt een fresh event loop per aanroep.
    Gebruik nooit asyncio.new_event_loop()+set_event_loop() in een actor --
    dat is niet thread-safe bij parallelle workers (CLAUDE.md valkuil).
    """
    asyncio.run(_cleanup_council_decisions_async())


async def _cleanup_council_decisions_async() -> None:
    """Interne async implementatie -- nooit direct aanroepen.

    Verwijder council_decisions ouder dan 395 dagen (cascade officer_verdicts)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS_COUNCIL)
    total_deleted = 0

    try:
        async with get_db_session() as session:
            with TenantFilterBypass():  # cross-tenant cleanup
                while True:
                    # Batch-delete oldest decisions
                    subq = (
                        select(CouncilDecisionRow.decision_id)
                        .where(CouncilDecisionRow.timestamp < cutoff)
                        .order_by(CouncilDecisionRow.timestamp.asc())
                        .limit(BATCH_SIZE)
                    ).scalar_subquery()

                    # Cascade verwijdert officer_verdicts via FK ON DELETE CASCADE
                    result = await session.execute(
                        delete(CouncilDecisionRow).where(CouncilDecisionRow.decision_id.in_(subq))
                    )
                    cursor_result = cast(CursorResult[RowMapping], result)
                    deleted = cursor_result.rowcount or 0
                    await session.commit()
                    total_deleted += deleted
                    if deleted < BATCH_SIZE:
                        break

        logger.info(
            "council retention cleanup: deleted %d decisions older than %s",
            total_deleted,
            cutoff.isoformat(),
        )
    except Exception as e:
        logger.error("council retention cleanup failed: %s", str(e), exc_info=True)
        raise


RETENTION_DAYS_AGENT_CRITIQUES = 180  # 6 maanden


@workflow_actor(
    queue_name="cleanup",
    max_retries=3,
    time_limit=600_000,
    actor_name="cleanup_agent_critiques",
)
def cleanup_agent_critiques() -> None:
    """Sync wrapper -- thread-safe, geen AsyncIO middleware nodig.

    NOTE: asyncio.run() maakt een fresh event loop per aanroep.
    Gebruik nooit asyncio.new_event_loop()+set_event_loop() in een actor --
    dat is niet thread-safe bij parallelle workers (CLAUDE.md valkuil).
    """
    asyncio.run(_cleanup_agent_critiques_async())


async def _cleanup_agent_critiques_async() -> None:
    """Interne async implementatie -- nooit direct aanroepen.

    Verwijder agent_critiques ouder dan 180 dagen."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS_AGENT_CRITIQUES)
    total_deleted = 0

    try:
        from src.core.models.critique_models import CritiqueRecord  # noqa: PLC0415  # type: ignore[import-not-found]

        async with get_db_session() as session:
            with TenantFilterBypass():  # cross-tenant cleanup
                while True:
                    subq = (
                        select(CritiqueRecord.id)
                        .where(CritiqueRecord.created_at < cutoff)
                        .order_by(CritiqueRecord.created_at.asc())
                        .limit(BATCH_SIZE)
                    ).scalar_subquery()

                    result = await session.execute(
                        delete(CritiqueRecord).where(CritiqueRecord.id.in_(subq))
                    )
                    cursor_result = cast(CursorResult[RowMapping], result)
                    deleted = cursor_result.rowcount or 0
                    await session.commit()
                    total_deleted += deleted
                    if deleted < BATCH_SIZE:
                        break

        logger.info(
            "agent_critiques retention cleanup: deleted %d records older than %s",
            total_deleted,
            cutoff.isoformat(),
        )
    except Exception as e:
        logger.error(
            "agent_critiques retention cleanup failed: %s: %s", type(e).__name__, e, exc_info=True
        )
        raise


#: Bewaartermijn voor AFGEHANDELDE HITL-tickets, gelijk aan die van council-besluiten.
#:
#: Een goedkeuring is toezichtsbewijs onder hetzelfde AI-Act-regime als een raadsbesluit, dus een
#: afwijkende termijn zou uitgelegd moeten worden. 395 dagen is ~13 maanden.
RETENTION_DAYS_HITL = 395


@workflow_actor(
    queue_name="cleanup",
    max_retries=3,
    time_limit=600_000,
    actor_name="cleanup_resolved_hitl_tickets",
)
def cleanup_resolved_hitl_tickets() -> None:
    """Sync wrapper -- zie `cleanup_council_decisions` voor waarom `asyncio.run()`."""
    asyncio.run(_cleanup_resolved_hitl_tickets_async())


async def _cleanup_resolved_hitl_tickets_async() -> None:
    """Verwijder AFGEHANDELDE HITL-tickets ouder dan de bewaartermijn (ADR-036 OP-47).

    **Waarom dit ontbrak en waarom markeren geen retentie is.** `cleanup_expired_hitl_tickets`
    (`src/workers/actors.py`) zet tickets op `expired`, maar gemeten met
    `git grep "delete(HITLTicket)"` over `src/`: er is geen enkel pad dat ooit een rij uit
    `hitl_tickets` verwijdert, en geen art.-17-route raakt deze tabel. Elk ticket bleef dus eeuwig
    staan -- ook nadat de inhoud bij de beslissing was opgeruimd.

    **Alleen afgehandelde tickets.** De filter eist `resolved_at IS NOT NULL`. Een ticket dat nog
    PENDING is, is nog niet beoordeeld en mag niet verdwijnen; het uurlijkse expiry-werk zet het
    eerst op `expired`, en pas dan telt de klok voor deze actor. Zonder die eis zou een oud maar
    onbehandeld verzoek stil weggaan en zou niemand ooit zien dat er iets is blijven liggen.
    """
    from src.core.tool_broker.models import HITLTicket

    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS_HITL)
    total_deleted = 0

    try:
        async with get_db_session() as session:
            with TenantFilterBypass():  # cross-tenant cleanup
                while True:
                    subq = (
                        select(HITLTicket.id)
                        .where(
                            HITLTicket.resolved_at.is_not(None),
                            HITLTicket.resolved_at < cutoff,
                        )
                        .order_by(HITLTicket.resolved_at.asc())
                        .limit(BATCH_SIZE)
                    ).scalar_subquery()

                    result = await session.execute(
                        delete(HITLTicket).where(HITLTicket.id.in_(subq))
                    )
                    cursor_result = cast(CursorResult[RowMapping], result)
                    deleted = cursor_result.rowcount or 0
                    await session.commit()
                    total_deleted += deleted
                    if deleted < BATCH_SIZE:
                        break

        logger.info(
            "hitl retention cleanup: deleted %d resolved tickets older than %s",
            total_deleted,
            cutoff.isoformat(),
        )
    except Exception as e:
        logger.error(
            "hitl retention cleanup failed: %s: %s", type(e).__name__, e, exc_info=True
        )
        raise
