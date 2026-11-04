"""Integration tests for Foundation Portal migrations.

Validates that the Alembic migrations for the Foundation Portal (20260524a-e,
20260824_adr029_portal_v1, 20260909_adr029_edu_alignment) correctly created
tables, indexes, enums, foreign keys, and RLS policies.

Note: the test session fixture builds the schema via Base.metadata.create_all(),
so these tests validate model<->schema alignment. Coverage of the migration
path itself (offline SQL) lives in tests/unit/test_be_mig_013_offline_sql.py.
"""

import pytest
from sqlalchemy import text

from src.core.models.foundation_content import (
    ContentTag,
    FoundationContent,
    FoundationPortalSettings,
    MagicLinkToken,
    NewsletterSubscription,
    PortalUser,
    TakedownRequest,
)


@pytest.mark.integration
@pytest.mark.asyncio
class TestFoundationMigrationTables:
    """Verify all 7 Foundation Portal tables exist with correct columns."""

    async def test_portal_users_table_exists(self, postgres_session):
        result = await postgres_session.execute(
            text(
                "SELECT column_name, data_type, is_nullable "
                "FROM information_schema.columns WHERE table_name = 'portal_users'"
            )
        )
        rows = {r[0]: (r[1], r[2]) for r in result.fetchall()}
        assert "id" in rows
        assert "tenant_id" in rows
        assert rows["tenant_id"][1] == "NO"  # NOT NULL
        assert "email" in rows
        assert "display_name" in rows
        assert "is_verified" in rows
        assert "is_blocked" in rows
        assert "last_login_at" in rows
        assert "created_at" in rows
        assert "updated_at" in rows

    async def test_magic_link_tokens_table_exists(self, postgres_session):
        result = await postgres_session.execute(
            text(
                "SELECT column_name, data_type, is_nullable "
                "FROM information_schema.columns WHERE table_name = 'magic_link_tokens'"
            )
        )
        rows = {r[0]: (r[1], r[2]) for r in result.fetchall()}
        assert "id" in rows
        assert "tenant_id" in rows
        assert rows["tenant_id"][1] == "NO"
        assert "portal_user_id" in rows
        assert "token_hash" in rows
        assert "expires_at" in rows
        assert "used_at" in rows
        assert "created_at" in rows

    async def test_foundation_content_table_exists(self, postgres_session):
        result = await postgres_session.execute(
            text(
                "SELECT column_name, data_type, is_nullable "
                "FROM information_schema.columns WHERE table_name = 'foundation_content'"
            )
        )
        rows = {r[0]: (r[1], r[2]) for r in result.fetchall()}
        assert "id" in rows
        assert "tenant_id" in rows
        assert rows["tenant_id"][1] == "NO"
        assert "uploader_id" in rows
        assert "type" in rows
        assert "title_nl" in rows
        assert "title_en" in rows
        assert "privacy" in rows
        assert "status" in rows
        assert "rights_confirmed" in rows
        assert "file_url" in rows
        assert "file_mime" in rows
        assert "file_size_bytes" in rows
        assert "external_url" in rows
        assert "ai_tagging_failed" in rows
        assert "moderation_score" in rows
        assert "rejection_reason" in rows
        assert "takedown_reason" in rows
        assert "takedown_at" in rows
        assert "created_at" in rows
        assert "updated_at" in rows

    async def test_content_tags_table_exists_no_tenant_id(self, postgres_session):
        result = await postgres_session.execute(
            text(
                "SELECT column_name, data_type, is_nullable "
                "FROM information_schema.columns WHERE table_name = 'content_tags'"
            )
        )
        rows = {r[0]: (r[1], r[2]) for r in result.fetchall()}
        assert "id" in rows
        assert "content_id" in rows
        assert "tag_type" in rows
        assert "value" in rows
        assert "confidence" in rows
        assert "is_manual" in rows
        assert "created_at" in rows
        assert "updated_at" in rows
        # ContentTag must NOT have a tenant_id column (JOIN-based isolation)
        assert "tenant_id" not in rows

    async def test_foundation_portal_settings_table_exists(self, postgres_session):
        result = await postgres_session.execute(
            text(
                "SELECT column_name, data_type, is_nullable "
                "FROM information_schema.columns WHERE table_name = 'foundation_portal_settings'"
            )
        )
        rows = {r[0]: (r[1], r[2]) for r in result.fetchall()}
        assert "id" in rows
        assert "tenant_id" in rows
        assert rows["tenant_id"][1] == "NO"
        assert "platform_name_nl" in rows
        assert "platform_name_en" in rows
        assert "primary_color" in rows
        assert "accent_color" in rows
        assert "logo_url" in rows
        assert "favicon_url" in rows
        assert "guidelines_nl" in rows
        assert "guidelines_en" in rows
        assert "about_nl" in rows
        assert "about_en" in rows
        assert "contact_email" in rows
        assert "created_at" in rows
        assert "updated_at" in rows

    async def test_takedown_requests_table_exists(self, postgres_session):
        result = await postgres_session.execute(
            text(
                "SELECT column_name, data_type, is_nullable "
                "FROM information_schema.columns WHERE table_name = 'takedown_requests'"
            )
        )
        rows = {r[0]: (r[1], r[2]) for r in result.fetchall()}
        assert "id" in rows
        assert "tenant_id" in rows
        assert rows["tenant_id"][1] == "NO"
        assert "content_id" in rows
        assert "requester_email" in rows
        assert "requester_name" in rows
        assert "legal_basis" in rows
        assert "status" in rows
        assert "resolution_note" in rows
        assert "resolved_at" in rows
        assert "created_at" in rows

    async def test_newsletter_subscriptions_table_exists(self, postgres_session):
        result = await postgres_session.execute(
            text(
                "SELECT column_name, data_type, is_nullable "
                "FROM information_schema.columns WHERE table_name = 'newsletter_subscriptions'"
            )
        )
        rows = {r[0]: (r[1], r[2]) for r in result.fetchall()}
        assert "id" in rows
        assert "tenant_id" in rows
        assert rows["tenant_id"][1] == "NO"
        assert "email" in rows
        assert "status" in rows
        assert "unsubscribed_at" in rows
        assert "created_at" in rows


@pytest.mark.integration
@pytest.mark.asyncio
class TestFoundationMigrationRLS:
    """Verify ContentTag has no RLS (JOIN-based isolation).

    NOTE: RLS policies are applied by Alembic migrations, not by
    Base.metadata.create_all() used in the test session fixture.
    RLS policy correctness is validated via offline SQL dry-run and
    dedicated security tests that bootstrap policies manually.
    """

    async def test_rls_disabled_on_content_tags(self, postgres_session):
        result = await postgres_session.execute(
            text(
                "SELECT rowsecurity FROM pg_tables "
                "WHERE schemaname = 'public' AND tablename = 'content_tags'"
            )
        )
        row = result.fetchone()
        assert row is not None
        assert row[0] is False, "content_tags must NOT have RLS (no tenant_id)"


@pytest.mark.integration
@pytest.mark.asyncio
class TestFoundationMigrationEnums:
    """Verify PostgreSQL enums were created with correct values."""

    async def test_content_type_enum_values(self, postgres_session):
        result = await postgres_session.execute(
            text(
                "SELECT enumlabel FROM pg_enum "
                "WHERE enumtypid = 'content_type_enum'::regtype ORDER BY enumsortorder"
            )
        )
        labels = [r[0] for r in result.fetchall()]
        # Hoofdletter member-namen: het ORM serialiseert zonder values_callable
        # member-namen. BE-MIG-014 (20260910) voegde de laatste zes toe.
        assert labels == [
            "STORY",
            "ARTWORK",
            "AUDIO",
            "DOCUMENT",
            "POETRY",
            "LINK",
            "VIDEO",
            "EDUCATIONAL_WORKBOOK",
            "EDUCATIONAL_VIDEO",
            "TEACHER_GUIDE",
            "EVENT_REPORT",
            "ART_DOCUMENTATION",
        ]

    async def test_visibility_enum_values(self, postgres_session):
        result = await postgres_session.execute(
            text(
                "SELECT enumlabel FROM pg_enum "
                "WHERE enumtypid = 'visibility_enum'::regtype ORDER BY enumsortorder"
            )
        )
        labels = [r[0] for r in result.fetchall()]
        # Lowercase .value's: de kolom gebruikt values_callable (BE-MIG-014).
        assert labels == ["public", "edu", "community"]

    async def test_foundation_content_visibility_columns(self, postgres_session):
        result = await postgres_session.execute(
            text(
                "SELECT column_name, is_nullable, column_default "
                "FROM information_schema.columns WHERE table_name = 'foundation_content' "
                "AND column_name IN ('visibility', 'target_age_group')"
            )
        )
        rows = {r[0]: (r[1], r[2]) for r in result.fetchall()}
        assert rows["visibility"][0] == "NO"
        assert rows["visibility"][1] == "'public'::visibility_enum"
        assert rows["target_age_group"][0] == "YES"

    async def test_visibility_index_exists(self, postgres_session):
        result = await postgres_session.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE schemaname = 'public' AND tablename = 'foundation_content' "
                "AND indexname = 'idx_fc_tenant_visibility_status'"
            )
        )
        row = result.fetchone()
        assert row is not None
        assert "tenant_id" in row[0]
        assert "visibility" in row[0]
        assert "status" in row[0]

    async def test_privacy_enum_values(self, postgres_session):
        result = await postgres_session.execute(
            text(
                "SELECT enumlabel FROM pg_enum "
                "WHERE enumtypid = 'privacy_enum'::regtype ORDER BY enumsortorder"
            )
        )
        labels = [r[0] for r in result.fetchall()]
        assert labels == ["PUBLIC", "COMMUNITY"]

    async def test_content_status_enum_values(self, postgres_session):
        result = await postgres_session.execute(
            text(
                "SELECT enumlabel FROM pg_enum "
                "WHERE enumtypid = 'content_status_enum'::regtype ORDER BY enumsortorder"
            )
        )
        labels = [r[0] for r in result.fetchall()]
        assert labels == ["PENDING", "APPROVED", "REJECTED", "REMOVED"]

    async def test_tag_type_enum_values(self, postgres_session):
        result = await postgres_session.execute(
            text(
                "SELECT enumlabel FROM pg_enum "
                "WHERE enumtypid = 'tag_type_enum'::regtype ORDER BY enumsortorder"
            )
        )
        labels = [r[0] for r in result.fetchall()]
        assert labels == ["THEME", "LOCATION", "PERIOD", "SENTIMENT", "LANGUAGE"]

    async def test_takedown_status_enum_values(self, postgres_session):
        result = await postgres_session.execute(
            text(
                "SELECT enumlabel FROM pg_enum "
                "WHERE enumtypid = 'takedown_status_enum'::regtype ORDER BY enumsortorder"
            )
        )
        labels = [r[0] for r in result.fetchall()]
        assert labels == ["PENDING", "APPROVED", "REJECTED", "ESCALATED"]

    async def test_newsletter_status_enum_values(self, postgres_session):
        result = await postgres_session.execute(
            text(
                "SELECT enumlabel FROM pg_enum "
                "WHERE enumtypid = 'newsletter_status_enum'::regtype ORDER BY enumsortorder"
            )
        )
        labels = [r[0] for r in result.fetchall()]
        # BOUNCED (foundation_content.py:79) ontbrak hier -- de kolom heeft 4 leden,
        # niet 3; dit assertte tegen een verouderde lijst, niet tegen een echte drift.
        assert labels == ["PENDING_OPT_IN", "SUBSCRIBED", "UNSUBSCRIBED", "BOUNCED"]

    async def test_newsletter_status_enum_no_dead_lowercase_bounced(self, postgres_session):
        # Migratie 20260824 voegde een dode dubbele waarde 'bounced' (lowercase)
        # toe naast 'BOUNCED'; 20260909_adr029_edu_alignment recreerde het type
        # zonder die waarde. Het model serialiseert member-namen (hoofdletters).
        result = await postgres_session.execute(
            text(
                "SELECT enumlabel FROM pg_enum "
                "WHERE enumtypid = 'newsletter_status_enum'::regtype ORDER BY enumsortorder"
            )
        )
        labels = [r[0] for r in result.fetchall()]
        assert "bounced" not in labels

    async def test_portal_role_enum_values_match_model(self, postgres_session):
        # Het model gebruikt values_callable (lowercase .value's) omdat migratie
        # 20260824 dit type met lowercase waarden maakte; zonder die callable
        # zou de ORM hoofdletter-namen serialiseren en elke insert falen.
        result = await postgres_session.execute(
            text(
                "SELECT enumlabel FROM pg_enum "
                "WHERE enumtypid = 'portal_role_enum'::regtype ORDER BY enumsortorder"
            )
        )
        labels = [r[0] for r in result.fetchall()]
        assert labels == ["admin", "curator", "teacher", "student", "visitor"]

    async def test_educational_role_enum_values_match_model(self, postgres_session):
        result = await postgres_session.execute(
            text(
                "SELECT enumlabel FROM pg_enum "
                "WHERE enumtypid = 'educational_role_enum'::regtype ORDER BY enumsortorder"
            )
        )
        labels = [r[0] for r in result.fetchall()]
        assert labels == ["teacher", "student", "admin", "curator", "visitor"]


@pytest.mark.integration
@pytest.mark.asyncio
class TestFoundationMigrationIndexes:
    """Verify critical composite indexes exist for query performance."""

    async def test_portal_users_tenant_email_unique(self, postgres_session):
        result = await postgres_session.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE schemaname = 'public' AND tablename = 'portal_users' "
                "AND indexname = 'idx_pu_tenant_email'"
            )
        )
        row = result.fetchone()
        assert row is not None
        assert "UNIQUE" in row[0]

    async def test_foundation_content_tenant_status_index(self, postgres_session):
        result = await postgres_session.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE schemaname = 'public' AND tablename = 'foundation_content' "
                "AND indexname = 'idx_fc_tenant_status'"
            )
        )
        row = result.fetchone()
        assert row is not None
        assert "tenant_id" in row[0]
        assert "status" in row[0]

    async def test_foundation_content_tenant_type_status_index(self, postgres_session):
        result = await postgres_session.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE schemaname = 'public' AND tablename = 'foundation_content' "
                "AND indexname = 'idx_fc_tenant_type_status'"
            )
        )
        row = result.fetchone()
        assert row is not None
        assert "tenant_id" in row[0]
        assert "type" in row[0]
        assert "status" in row[0]

    async def test_newsletter_subscriptions_tenant_email_unique(self, postgres_session):
        result = await postgres_session.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE schemaname = 'public' AND tablename = 'newsletter_subscriptions' "
                "AND indexname = 'idx_ns_tenant_email'"
            )
        )
        row = result.fetchone()
        assert row is not None
        assert "UNIQUE" in row[0]


@pytest.mark.integration
@pytest.mark.asyncio
class TestFoundationMigrationEduAlignment:
    """Verify educational_access / study_collections match the ORM models.

    Migratie 20260824_adr029_portal_v1 maakte een afwijkende kolomset aan
    (`code` String(20) resp. `access_code` String(20)); migratie
    20260909_adr029_edu_alignment bracht de tabellen terug in lijn met
    EducationalAccess / StudyCollection in src/core/models/foundation_content.py.
    """

    async def test_educational_access_code_hash_column(self, postgres_session):
        result = await postgres_session.execute(
            text(
                "SELECT column_name, data_type, character_maximum_length, is_nullable "
                "FROM information_schema.columns WHERE table_name = 'educational_access'"
            )
        )
        rows = {r[0]: r for r in result.fetchall()}
        # Migratie 20260824 maakte plaintext `code` String(20); het model eist
        # `code_hash` String(64) (SHA-256 hashes, nooit plaintext).
        assert "code" not in rows
        assert "code_hash" in rows
        col = rows["code_hash"]
        assert col[1] == "character varying"
        assert col[2] == 64
        assert col[3] == "NO"  # NOT NULL

    async def test_study_collections_educational_access_fk_column(self, postgres_session):
        result = await postgres_session.execute(
            text(
                "SELECT column_name, data_type, is_nullable "
                "FROM information_schema.columns WHERE table_name = 'study_collections'"
            )
        )
        rows = {r[0]: r for r in result.fetchall()}
        assert "access_code" not in rows
        assert "educational_access_id" in rows
        col = rows["educational_access_id"]
        assert col[1] == "integer"
        assert col[2] == "NO"  # NOT NULL

    async def test_study_collections_fk_targets_educational_access(self, postgres_session):
        result = await postgres_session.execute(
            text(
                "SELECT ccu.table_name FROM information_schema.table_constraints tc "
                "JOIN information_schema.key_column_usage kcu "
                "ON tc.constraint_name = kcu.constraint_name "
                "JOIN information_schema.constraint_column_usage ccu "
                "ON tc.constraint_name = ccu.constraint_name "
                "WHERE tc.constraint_type = 'FOREIGN KEY' "
                "AND tc.table_name = 'study_collections' "
                "AND kcu.column_name = 'educational_access_id'"
            )
        )
        row = result.fetchone()
        assert row is not None
        assert row[0] == "educational_access"

    async def test_educational_access_tenant_code_index_on_code_hash(self, postgres_session):
        result = await postgres_session.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE schemaname = 'public' AND tablename = 'educational_access' "
                "AND indexname = 'idx_ea_tenant_code'"
            )
        )
        row = result.fetchone()
        assert row is not None
        assert "UNIQUE" in row[0]
        # Pin de exacte kolomlijst: hiermee is de oude kolom `code` gegarandeerd
        # afwezig. (De oude assertie `"code " not in indexdef` matchte op de
        # index-NAAM `idx_ea_tenant_code` en faalde daardoor altijd.)
        assert "(tenant_id, code_hash)" in row[0]

    async def test_study_collections_tenant_code_index_on_access_fk(self, postgres_session):
        result = await postgres_session.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE schemaname = 'public' AND tablename = 'study_collections' "
                "AND indexname = 'idx_sc_tenant_code'"
            )
        )
        row = result.fetchone()
        assert row is not None
        assert "tenant_id" in row[0]
        assert "educational_access_id" in row[0]
        assert "access_code" not in row[0]

    async def test_study_collections_access_fk_single_column_index(self, postgres_session):
        # Het model declareert index=True op educational_access_id; SQLAlchemy
        # genereert daarvoor ix_study_collections_educational_access_id.
        result = await postgres_session.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE schemaname = 'public' AND tablename = 'study_collections' "
                "AND indexname = 'ix_study_collections_educational_access_id'"
            )
        )
        row = result.fetchone()
        assert row is not None
        assert "educational_access_id" in row[0]

    async def test_educational_access_code_hash_unique(self, postgres_session):
        result = await postgres_session.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE schemaname = 'public' AND tablename = 'educational_access' "
                "AND indexname = 'educational_access_code_hash_key'"
            )
        )
        row = result.fetchone()
        assert row is not None
        assert "UNIQUE" in row[0]
        assert "code_hash" in row[0]
