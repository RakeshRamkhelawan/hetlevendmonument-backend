"""
Unit tests for Foundation Portal models.

Covers: enums, model schema inspection, instantiation, defaults, indices.
"""

from __future__ import annotations

import pytest
from sqlalchemy import inspect as sa_inspect

from src.core.models.foundation_content import (
    ContentStatus,
    ContentTag,
    ContentType,
    EducationalAccess,
    EducationalRole,
    FoundationContent,
    FoundationPortalSettings,
    MagicLinkToken,
    NewsletterStatus,
    NewsletterSubscription,
    PortalRole,
    PortalUser,
    Privacy,
    StudyCollection,
    TagType,
    TakedownRequest,
    TakedownStatus,
)


# ============================================================================
# Enums
# ============================================================================


class TestFoundationEnums:
    @pytest.mark.unit
    def test_content_type_values(self) -> None:
        assert ContentType.STORY.value == "story"
        assert ContentType.ARTWORK.value == "artwork"
        assert ContentType.AUDIO.value == "audio"
        assert ContentType.DOCUMENT.value == "document"
        assert ContentType.POETRY.value == "poetry"
        assert ContentType.LINK.value == "link"

    @pytest.mark.unit
    def test_privacy_values(self) -> None:
        assert Privacy.PUBLIC.value == "public"
        assert Privacy.COMMUNITY.value == "community"

    @pytest.mark.unit
    def test_content_status_values(self) -> None:
        assert ContentStatus.PENDING.value == "pending"
        assert ContentStatus.APPROVED.value == "approved"
        assert ContentStatus.REJECTED.value == "rejected"
        assert ContentStatus.REMOVED.value == "removed"

    @pytest.mark.unit
    def test_tag_type_values(self) -> None:
        assert TagType.THEME.value == "theme"
        assert TagType.LOCATION.value == "location"
        assert TagType.PERIOD.value == "period"
        assert TagType.SENTIMENT.value == "sentiment"
        assert TagType.LANGUAGE.value == "language"

    @pytest.mark.unit
    def test_takedown_status_values(self) -> None:
        assert TakedownStatus.PENDING.value == "pending"
        assert TakedownStatus.APPROVED.value == "approved"
        assert TakedownStatus.REJECTED.value == "rejected"
        assert TakedownStatus.ESCALATED.value == "escalated"

    @pytest.mark.unit
    def test_newsletter_status_values(self) -> None:
        assert NewsletterStatus.PENDING_OPT_IN.value == "pending_opt_in"
        assert NewsletterStatus.SUBSCRIBED.value == "subscribed"
        assert NewsletterStatus.UNSUBSCRIBED.value == "unsubscribed"


# ============================================================================
# Model inspection (no DB required)
# ============================================================================


class TestFoundationContentSchema:
    @pytest.mark.unit
    def test_tenant_id_not_null(self) -> None:
        col = sa_inspect(FoundationContent).columns["tenant_id"]
        assert col.nullable is False

    @pytest.mark.unit
    def test_indices_present(self) -> None:
        idx_names = {idx.name for idx in FoundationContent.__table__.indexes}
        assert "idx_fc_tenant_status" in idx_names
        assert "idx_fc_tenant_type_status" in idx_names
        assert "idx_fc_tenant_created" in idx_names

    @pytest.mark.unit
    def test_default_status_pending(self) -> None:
        col = sa_inspect(FoundationContent).columns["status"]
        assert col.default is not None
        # The default is a scalar default from the PGEnum
        assert col.default.arg == ContentStatus.PENDING

    @pytest.mark.unit
    def test_rights_confirmed_default_false(self) -> None:
        col = sa_inspect(FoundationContent).columns["rights_confirmed"]
        assert col.default is not None
        assert col.default.arg is False


class TestContentTagSchema:
    @pytest.mark.unit
    def test_no_tenant_id_column(self) -> None:
        col_names = {c.name for c in sa_inspect(ContentTag).columns}
        assert "tenant_id" not in col_names

    @pytest.mark.unit
    def test_fk_ondelete_cascade(self) -> None:
        fks = ContentTag.__table__.foreign_keys
        assert any(
            fk.column.name == "id" and fk.column.table.name == "foundation_content" for fk in fks
        )
        fk = next(fk for fk in fks if fk.column.table.name == "foundation_content")
        assert fk.ondelete == "CASCADE"

    @pytest.mark.unit
    def test_docstring_mentions_adr029(self) -> None:
        assert "ADR-029" in (ContentTag.__doc__ or "")
        assert "JOIN" in (ContentTag.__doc__ or "")

    @pytest.mark.unit
    def test_index_present(self) -> None:
        idx_names = {idx.name for idx in ContentTag.__table__.indexes}
        assert "idx_tag_content_type" in idx_names


class TestFoundationPortalSettingsSchema:
    @pytest.mark.unit
    def test_tenant_id_unique(self) -> None:
        col = sa_inspect(FoundationPortalSettings).columns["tenant_id"]
        assert col.unique is True
        assert col.nullable is False


class TestPortalUserSchema:
    @pytest.mark.unit
    def test_unique_tenant_email_index(self) -> None:
        idx_names = {idx.name for idx in PortalUser.__table__.indexes}
        assert "idx_pu_tenant_email" in idx_names

    @pytest.mark.unit
    def test_tenant_id_not_null(self) -> None:
        col = sa_inspect(PortalUser).columns["tenant_id"]
        assert col.nullable is False


class TestMagicLinkTokenSchema:
    @pytest.mark.unit
    def test_token_hash_unique(self) -> None:
        col = sa_inspect(MagicLinkToken).columns["token_hash"]
        assert col.unique is True
        assert col.nullable is False

    @pytest.mark.unit
    def test_fk_ondelete_cascade(self) -> None:
        fks = MagicLinkToken.__table__.foreign_keys
        fk = next(fk for fk in fks if fk.column.table.name == "portal_users")
        assert fk.ondelete == "CASCADE"

    @pytest.mark.unit
    def test_expires_at_index(self) -> None:
        idx_names = {idx.name for idx in MagicLinkToken.__table__.indexes}
        assert "idx_mlt_expires" in idx_names

    @pytest.mark.unit
    def test_tenant_id_not_null(self) -> None:
        col = sa_inspect(MagicLinkToken).columns["tenant_id"]
        assert col.nullable is False


class TestTakedownRequestSchema:
    @pytest.mark.unit
    def test_status_is_enum_not_string(self) -> None:
        col = sa_inspect(TakedownRequest).columns["status"]
        # Should be an ENUM column type, not String
        assert "ENUM" in str(col.type).upper() or "enum" in str(type(col.type)).lower()

    @pytest.mark.unit
    def test_tenant_id_not_null(self) -> None:
        col = sa_inspect(TakedownRequest).columns["tenant_id"]
        assert col.nullable is False

    @pytest.mark.unit
    def test_index_present(self) -> None:
        idx_names = {idx.name for idx in TakedownRequest.__table__.indexes}
        assert "idx_td_tenant_status" in idx_names


class TestNewsletterSubscriptionSchema:
    @pytest.mark.unit
    def test_unsubscribe_token_hash_unique_not_null(self) -> None:
        col = sa_inspect(NewsletterSubscription).columns["unsubscribe_token_hash"]
        assert col.unique is True
        assert col.nullable is False

    @pytest.mark.unit
    def test_consent_ip_varchar45(self) -> None:
        col = sa_inspect(NewsletterSubscription).columns["consent_ip"]
        assert col.type.length == 45  # IPv6 max

    @pytest.mark.unit
    def test_tenant_id_not_null(self) -> None:
        col = sa_inspect(NewsletterSubscription).columns["tenant_id"]
        assert col.nullable is False

    @pytest.mark.unit
    def test_indices_present(self) -> None:
        idx_names = {idx.name for idx in NewsletterSubscription.__table__.indexes}
        assert "idx_ns_tenant_email" in idx_names
        assert "idx_ns_tenant_status" in idx_names


# ============================================================================
# Instantiation tests (require DB)
# ============================================================================


class TestFoundationModelInstantiation:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_foundation_content_create(self, db_session) -> None:
        from src.core.models.rbac_models import Tenant

        tenant = Tenant(name="Test Tenant", slug="test-tenant")
        db_session.add(tenant)
        await db_session.flush()

        content = FoundationContent(
            tenant_id=tenant.id,
            type=ContentType.STORY,
            title_nl="Test Story",
            language="nl",
        )
        db_session.add(content)
        await db_session.flush()

        assert content.id is not None
        assert content.tenant_id == tenant.id
        assert content.status == ContentStatus.PENDING
        assert content.rights_confirmed is False
        assert content.is_anonymous is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_content_tag_create(self, db_session) -> None:
        from src.core.models.rbac_models import Tenant

        tenant = Tenant(name="Test Tenant 2", slug="test-tenant-2")
        db_session.add(tenant)
        await db_session.flush()

        content = FoundationContent(
            tenant_id=tenant.id,
            type=ContentType.ARTWORK,
            title_nl="Test Art",
        )
        db_session.add(content)
        await db_session.flush()

        tag = ContentTag(
            content_id=content.id,
            tag_type=TagType.THEME,
            value="vrijheid",
            confidence=0.95,
        )
        db_session.add(tag)
        await db_session.flush()

        assert tag.id is not None
        assert tag.content_id == content.id

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_portal_user_create(self, db_session) -> None:
        from src.core.models.rbac_models import Tenant

        tenant = Tenant(name="Test Tenant 3", slug="test-tenant-3")
        db_session.add(tenant)
        await db_session.flush()

        user = PortalUser(
            tenant_id=tenant.id,
            email="user@example.com",
        )
        db_session.add(user)
        await db_session.flush()

        assert user.id is not None
        assert user.is_verified is False
        assert user.is_blocked is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_magic_link_token_create(self, db_session) -> None:
        from datetime import datetime, timezone
        from src.core.models.rbac_models import Tenant

        tenant = Tenant(name="Test Tenant 4", slug="test-tenant-4")
        db_session.add(tenant)
        await db_session.flush()

        user = PortalUser(
            tenant_id=tenant.id,
            email="user2@example.com",
        )
        db_session.add(user)
        await db_session.flush()

        token = MagicLinkToken(
            tenant_id=tenant.id,
            portal_user_id=user.id,
            token_hash="abc123",
            expires_at=datetime.now(timezone.utc),
        )
        db_session.add(token)
        await db_session.flush()

        assert token.id is not None
        assert token.created_at is not None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_takedown_request_create(self, db_session) -> None:
        from src.core.models.rbac_models import Tenant

        tenant = Tenant(name="Test Tenant 5", slug="test-tenant-5")
        db_session.add(tenant)
        await db_session.flush()

        content = FoundationContent(
            tenant_id=tenant.id,
            type=ContentType.STORY,
            title_nl="Test Story 2",
        )
        db_session.add(content)
        await db_session.flush()

        td = TakedownRequest(
            tenant_id=tenant.id,
            content_id=content.id,
            requester_email="claimer@example.com",
            requester_name="John Doe",
            legal_basis="Copyright infringement",
        )
        db_session.add(td)
        await db_session.flush()

        assert td.id is not None
        assert td.status == TakedownStatus.PENDING

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_newsletter_subscription_create(self, db_session) -> None:
        from src.core.models.rbac_models import Tenant

        tenant = Tenant(name="Test Tenant 6", slug="test-tenant-6")
        db_session.add(tenant)
        await db_session.flush()

        sub = NewsletterSubscription(
            tenant_id=tenant.id,
            email="reader@example.com",
            unsubscribe_token_hash="unsub123",
            consent_ip="192.0.2.1",
            consent_user_agent="Mozilla/5.0",
        )
        db_session.add(sub)
        await db_session.flush()

        assert sub.id is not None
        assert sub.status == NewsletterStatus.PENDING_OPT_IN

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_portal_settings_create(self, db_session) -> None:
        from src.core.models.rbac_models import Tenant

        tenant = Tenant(name="Test Tenant 7", slug="test-tenant-7")
        db_session.add(tenant)
        await db_session.flush()

        settings = FoundationPortalSettings(
            tenant_id=tenant.id,
            platform_name_nl="Levend Monument",
        )
        db_session.add(settings)
        await db_session.flush()

        assert settings.id is not None
        assert settings.primary_color == "#1a2f45"
        assert settings.accent_color == "#e8b86d"


# ============================================================================
# ADR-029 v1 -- New fields & models (2026-08-24)
# ============================================================================


class TestPortalRoleEnum:
    @pytest.mark.unit
    def test_all_roles_present(self) -> None:
        assert PortalRole.ADMIN.value == "admin"
        assert PortalRole.CURATOR.value == "curator"
        assert PortalRole.TEACHER.value == "teacher"
        assert PortalRole.STUDENT.value == "student"
        assert PortalRole.VISITOR.value == "visitor"

    @pytest.mark.unit
    def test_default_role_is_visitor(self) -> None:
        from sqlalchemy import inspect as sa_inspect
        col = sa_inspect(PortalUser).columns["role"]
        assert col.default is not None
        assert col.default.arg == PortalRole.VISITOR


class TestFoundationContentGeoFields:
    @pytest.mark.unit
    def test_lat_lng_nullable(self) -> None:
        from sqlalchemy import inspect as sa_inspect
        lat_col = sa_inspect(FoundationContent).columns["lat"]
        lng_col = sa_inspect(FoundationContent).columns["lng"]
        assert lat_col.nullable is True
        assert lng_col.nullable is True

    @pytest.mark.unit
    def test_metadata_is_jsonb(self) -> None:
        col = FoundationContent.__table__.columns["metadata"]
        assert "JSONB" in str(type(col.type)).upper() or "json" in str(type(col.type)).lower()


class TestPortalUserNewFields:
    @pytest.mark.unit
    def test_role_not_null(self) -> None:
        from sqlalchemy import inspect as sa_inspect
        col = sa_inspect(PortalUser).columns["role"]
        assert col.nullable is False

    @pytest.mark.unit
    def test_email_verified_default_false(self) -> None:
        from sqlalchemy import inspect as sa_inspect
        col = sa_inspect(PortalUser).columns["email_verified"]
        assert col.default is not None
        assert col.default.arg is False

    @pytest.mark.unit
    def test_consent_given_default_false(self) -> None:
        from sqlalchemy import inspect as sa_inspect
        col = sa_inspect(PortalUser).columns["consent_given"]
        assert col.default is not None
        assert col.default.arg is False


class TestNewsletterStatusBounced:
    @pytest.mark.unit
    def test_bounced_value(self) -> None:
        assert NewsletterStatus.BOUNCED.value == "bounced"


class TestEducationalAccessSchema:
    @pytest.mark.unit
    def test_tenant_id_not_null(self) -> None:
        from sqlalchemy import inspect as sa_inspect
        col = sa_inspect(EducationalAccess).columns["tenant_id"]
        assert col.nullable is False

    @pytest.mark.unit
    def test_code_hash_unique(self) -> None:
        from sqlalchemy import inspect as sa_inspect
        col = sa_inspect(EducationalAccess).columns["code_hash"]
        assert col.unique is True

    @pytest.mark.unit
    def test_is_active_default_true(self) -> None:
        from sqlalchemy import inspect as sa_inspect
        col = sa_inspect(EducationalAccess).columns["is_active"]
        assert col.default is not None
        assert col.default.arg is True


class TestStudyCollectionSchema:
    @pytest.mark.unit
    def test_tenant_id_not_null(self) -> None:
        from sqlalchemy import inspect as sa_inspect
        col = sa_inspect(StudyCollection).columns["tenant_id"]
        assert col.nullable is False

    @pytest.mark.unit
    def test_educational_access_id_indexed(self) -> None:
        idx_names = {idx.name for idx in StudyCollection.__table__.indexes}
        assert "idx_sc_tenant_code" in idx_names


class TestAdr029Instantiation:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_foundation_content_with_geo(self, db_session) -> None:
        from src.core.models.rbac_models import Tenant

        tenant = Tenant(name="Geo Tenant", slug="geo-tenant")
        db_session.add(tenant)
        await db_session.flush()

        content = FoundationContent(
            tenant_id=tenant.id,
            type=ContentType.STORY,
            title_nl="Geo Story",
            lat=51.912,
            lng=4.342,
            location_name="Vlaardingen",
            license="CC-BY-4.0",
            category="heritage",
            metadata={"year": 2024, "source": "archive"},
        )
        db_session.add(content)
        await db_session.flush()

        assert content.lat == 51.912
        assert content.lng == 4.342
        assert content.location_name == "Vlaardingen"
        assert content.metadata == {"year": 2024, "source": "archive"}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_portal_user_with_role(self, db_session) -> None:
        from src.core.models.rbac_models import Tenant

        tenant = Tenant(name="Role Tenant", slug="role-tenant")
        db_session.add(tenant)
        await db_session.flush()

        user = PortalUser(
            tenant_id=tenant.id,
            email="curator@example.com",
            role=PortalRole.CURATOR,
            email_verified=True,
            consent_given=True,
        )
        db_session.add(user)
        await db_session.flush()

        assert user.role == PortalRole.CURATOR
        assert user.email_verified is True
        assert user.consent_given is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    @pytest.mark.parametrize("role_value", ["teacher", "student", "admin", "curator", "visitor"])
    async def test_educational_access_all_roles(self, db_session, role_value) -> None:
        """Alle 5 EducationalRole waarden moeten correct opslaan in de database."""
        from src.core.models.rbac_models import Tenant

        tenant = Tenant(name=f"Edu Tenant {role_value}", slug=f"edu-tenant-{role_value}")
        db_session.add(tenant)
        await db_session.flush()

        access = EducationalAccess(
            tenant_id=tenant.id,
            code_hash=f"EDU2024{role_value.upper()}",
            email=f"user@{role_value}.nl",
            role=role_value,
        )
        db_session.add(access)
        await db_session.flush()

        assert access.id is not None
        assert access.role == role_value

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_educational_access_create(self, db_session) -> None:
        from src.core.models.rbac_models import Tenant

        tenant = Tenant(name="Edu Tenant", slug="edu-tenant")
        db_session.add(tenant)
        await db_session.flush()

        access = EducationalAccess(
            tenant_id=tenant.id,
            code_hash="EDU2024A",
            email="teacher@school.nl",
            role="teacher",
            is_active=True,
        )
        db_session.add(access)
        await db_session.flush()

        assert access.id is not None
        assert access.code_hash == "EDU2024A"
        assert access.role == "teacher"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_study_collection_create(self, db_session) -> None:
        from src.core.models.rbac_models import Tenant

        tenant = Tenant(name="Study Tenant", slug="study-tenant")
        db_session.add(tenant)
        await db_session.flush()

        # First create an EducationalAccess entry
        access = EducationalAccess(
            tenant_id=tenant.id,
            code_hash="EDU2024A",
            email="teacher@school.nl",
            role="teacher",
        )
        db_session.add(access)
        await db_session.flush()

        collection = StudyCollection(
            tenant_id=tenant.id,
            name="Keti Koti Lesmateriaal",
            description="Educational content for schools",
            educational_access_id=access.id,
        )
        db_session.add(collection)
        await db_session.flush()

        assert collection.id is not None
        assert collection.name == "Keti Koti Lesmateriaal"
        assert collection.educational_access_id == access.id


# ============================================================================
# Unhappy path tests (FA-006)
# ============================================================================


class TestAdr029UnhappyPaths:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_educational_access_duplicate_code_hash_raises(self, db_session) -> None:
        """Duplicate access code_hash within same tenant must raise IntegrityError."""
        from sqlalchemy.exc import IntegrityError
        from src.core.models.rbac_models import Tenant

        tenant = Tenant(name="Dup Tenant", slug="dup-tenant")
        db_session.add(tenant)
        await db_session.flush()

        access1 = EducationalAccess(
            tenant_id=tenant.id,
            code_hash="SAMECODE",
            email="a@school.nl",
        )
        db_session.add(access1)
        await db_session.flush()

        access2 = EducationalAccess(
            tenant_id=tenant.id,
            code_hash="SAMECODE",
            email="b@school.nl",
        )
        db_session.add(access2)
        with pytest.raises(IntegrityError):
            await db_session.flush()

    @pytest.mark.unit
    def test_portal_user_invalid_role_rejected(self) -> None:
        """Assigning an invalid string to PortalRole should raise ValueError."""
        with pytest.raises(ValueError):
            PortalRole("superadmin")  # type: ignore[call-arg]


# ============================================================================
# BE-MIG-014 -- Sprint C datamodel: Visibility, ContentType-uitbreiding,
# target_age_group (2026-09-10)
# ============================================================================


class TestContentTypeSprintC:
    @pytest.mark.unit
    def test_six_new_values(self) -> None:
        assert ContentType.VIDEO.value == "video"
        assert ContentType.EDUCATIONAL_WORKBOOK.value == "educational_workbook"
        assert ContentType.EDUCATIONAL_VIDEO.value == "educational_video"
        assert ContentType.TEACHER_GUIDE.value == "teacher_guide"
        assert ContentType.EVENT_REPORT.value == "event_report"
        assert ContentType.ART_DOCUMENTATION.value == "art_documentation"

    @pytest.mark.unit
    def test_original_values_unchanged(self) -> None:
        assert ContentType.STORY.value == "story"
        assert ContentType.ARTWORK.value == "artwork"
        assert ContentType.AUDIO.value == "audio"
        assert ContentType.DOCUMENT.value == "document"
        assert ContentType.POETRY.value == "poetry"
        assert ContentType.LINK.value == "link"


class TestVisibilityEnum:
    @pytest.mark.unit
    def test_values_lowercase(self) -> None:
        from src.core.models.foundation_content import Visibility

        assert Visibility.PUBLIC.value == "public"
        assert Visibility.EDU.value == "edu"
        assert Visibility.COMMUNITY.value == "community"

    @pytest.mark.unit
    def test_column_uses_values_callable(self) -> None:
        """visibility_enum in Postgres bevat lowercase waarden; de kolom moet
        dus values_callable gebruiken (zelfde patroon als EducationalRole)."""
        col = sa_inspect(FoundationContent).columns["visibility"]
        assert col.type.values_callable is not None

    @pytest.mark.unit
    def test_default_public(self) -> None:
        col = sa_inspect(FoundationContent).columns["visibility"]
        from src.core.models.foundation_content import Visibility

        assert col.nullable is False
        assert col.default is not None
        assert col.default.arg == Visibility.PUBLIC
        assert col.server_default is not None
        assert str(col.server_default.arg) == "public"

    @pytest.mark.unit
    def test_visibility_index_present(self) -> None:
        idx_names = {idx.name for idx in FoundationContent.__table__.indexes}
        assert "idx_fc_tenant_visibility_status" in idx_names


class TestTargetAgeGroup:
    @pytest.mark.unit
    def test_nullable_string_50(self) -> None:
        col = sa_inspect(FoundationContent).columns["target_age_group"]
        assert col.nullable is True
        assert col.type.length == 50


class TestSprintCInstantiation:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_content_default_visibility_public(self, db_session) -> None:
        from src.core.models.foundation_content import Visibility
        from src.core.models.rbac_models import Tenant

        tenant = Tenant(name="Vis Tenant", slug="vis-tenant")
        db_session.add(tenant)
        await db_session.flush()

        content = FoundationContent(
            tenant_id=tenant.id,
            type=ContentType.STORY,
            title_nl="Default visibility",
        )
        db_session.add(content)
        await db_session.flush()

        assert content.visibility == Visibility.PUBLIC
        assert content.target_age_group is None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_content_edu_visibility_with_age_group(self, db_session) -> None:
        from src.core.models.foundation_content import Visibility
        from src.core.models.rbac_models import Tenant

        tenant = Tenant(name="Edu Vis Tenant", slug="edu-vis-tenant")
        db_session.add(tenant)
        await db_session.flush()

        content = FoundationContent(
            tenant_id=tenant.id,
            type=ContentType.EDUCATIONAL_WORKBOOK,
            title_nl="Werkboek Keti Koti",
            visibility=Visibility.EDU,
            target_age_group="12-14",
        )
        db_session.add(content)
        await db_session.flush()

        assert content.id is not None
        assert content.visibility == Visibility.EDU
        assert content.type == ContentType.EDUCATIONAL_WORKBOOK
        assert content.target_age_group == "12-14"
