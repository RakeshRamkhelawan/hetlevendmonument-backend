"""
Tests for Audit API Endpoints
=============================

Comprehensive test suite for /api/v1/audit/* endpoints.
Target: 100% code coverage
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

# Import the module under test
from src.core.api.audit_endpoints import (  # Enums; Models; Helper functions; Endpoints; Router
    AuditEvent,
    AuditEventType,
    AuditListResponse,
    DataCategory,
    DataProcessingRecord,
    ExportFormat,
    GDPRExportMetadata,
    GDPRExportResponse,
    MissionAuditDetail,
    MissionAuditSummary,
    MissionStatus,
    export_mission_audit,
    format_csv_export,
    generate_data_processing_records,
    generate_sample_audit_trail,
    generate_sample_missions,
    get_mission_detail,
    get_tenant,
    get_user_email,
    get_user_id,
    list_missions_audit,
    router,
)

# ============================================================================
# Test Enums
# ============================================================================


class TestEnums:
    """Test all enum definitions"""

    def test_mission_status_values(self):
        """Test MissionStatus enum has all expected values"""
        assert MissionStatus.PENDING == "pending"
        assert MissionStatus.APPROVED == "approved"
        assert MissionStatus.REJECTED == "rejected"
        assert MissionStatus.IN_PROGRESS == "in_progress"
        assert MissionStatus.COMPLETED == "completed"
        assert MissionStatus.FAILED == "failed"
        assert MissionStatus.CANCELLED == "cancelled"

    def test_audit_event_type_values(self):
        """Test AuditEventType enum has all expected values"""
        assert AuditEventType.CREATED == "created"
        assert AuditEventType.UPDATED == "updated"
        assert AuditEventType.STATUS_CHANGE == "status_change"
        assert AuditEventType.APPROVED == "approved"
        assert AuditEventType.REJECTED == "rejected"
        assert AuditEventType.EXECUTED == "executed"
        assert AuditEventType.COMPLETED == "completed"
        assert AuditEventType.FAILED == "failed"
        assert AuditEventType.DATA_ACCESS == "data_access"
        assert AuditEventType.EXPORT == "export"

    def test_export_format_values(self):
        """Test ExportFormat enum has all expected values"""
        assert ExportFormat.JSON == "json"
        assert ExportFormat.CSV == "csv"
        assert ExportFormat.PDF == "pdf"

    def test_data_category_values(self):
        """Test DataCategory enum has all expected values"""
        assert DataCategory.PERSONAL == "personal"
        assert DataCategory.SENSITIVE == "sensitive"
        assert DataCategory.BEHAVIORAL == "behavioral"
        assert DataCategory.TECHNICAL == "technical"
        assert DataCategory.DERIVED == "derived"


# ============================================================================
# Test Pydantic Models
# ============================================================================


class TestPydanticModels:
    """Test Pydantic model creation and validation"""

    def test_audit_event_creation(self):
        """Test AuditEvent model creation"""
        event = AuditEvent(
            id="evt_123",
            event_type=AuditEventType.CREATED,
            timestamp="2025-12-17T10:00:00Z",
            actor_id="user_001",
        )
        assert event.id == "evt_123"
        assert event.event_type == AuditEventType.CREATED
        assert event.actor_id == "user_001"
        assert event.details == {}

    def test_audit_event_with_all_fields(self):
        """Test AuditEvent with all optional fields"""
        event = AuditEvent(
            id="evt_456",
            event_type=AuditEventType.UPDATED,
            timestamp="2025-12-17T11:00:00Z",
            actor_id="user_002",
            actor_email="user@example.com",
            details={"field": "value"},
            ip_address="192.168.1.1",
            user_agent="Test Agent",
        )
        assert event.actor_email == "user@example.com"
        assert event.ip_address == "192.168.1.1"
        assert event.user_agent == "Test Agent"

    def test_data_processing_record_creation(self):
        """Test DataProcessingRecord model creation"""
        record = DataProcessingRecord(
            category=DataCategory.TECHNICAL,
            purpose="Testing",
            legal_basis="Consent",
            retention_period="1 year",
        )
        assert record.category == DataCategory.TECHNICAL
        assert record.purpose == "Testing"
        assert record.recipients == []

    def test_data_processing_record_with_recipients(self):
        """Test DataProcessingRecord with recipients"""
        record = DataProcessingRecord(
            category=DataCategory.PERSONAL,
            purpose="Analytics",
            legal_basis="Legitimate interest",
            retention_period="2 years",
            recipients=["Team A", "Team B"],
        )
        assert len(record.recipients) == 2
        assert "Team A" in record.recipients

    def test_mission_audit_summary_creation(self):
        """Test MissionAuditSummary model creation"""
        summary = MissionAuditSummary(
            mission_id="mission_001",
            name="Test Mission",
            status=MissionStatus.PENDING,
            created_at="2025-12-17T10:00:00Z",
            updated_at="2025-12-17T11:00:00Z",
            created_by="user_001",
            tenant_id=1,
        )
        assert summary.mission_id == "mission_001"
        assert summary.name == "Test Mission"
        assert summary.event_count == 0
        assert summary.data_categories == []

    def test_mission_audit_summary_with_all_fields(self):
        """Test MissionAuditSummary with all optional fields"""
        summary = MissionAuditSummary(
            mission_id="mission_002",
            name="Complete Mission",
            description="Full description",
            status=MissionStatus.APPROVED,
            created_at="2025-12-17T10:00:00Z",
            updated_at="2025-12-17T11:00:00Z",
            created_by="user_001",
            approved_by="user_002",
            approved_at="2025-12-17T10:30:00Z",
            event_count=5,
            last_event_type=AuditEventType.APPROVED,
            data_categories=[DataCategory.TECHNICAL],
            tenant_id=1,
        )
        assert summary.approved_by == "user_002"
        assert summary.event_count == 5
        assert summary.last_event_type == AuditEventType.APPROVED

    def test_mission_audit_detail_creation(self):
        """Test MissionAuditDetail model creation"""
        detail = MissionAuditDetail(
            mission_id="mission_001",
            name="Test Mission",
            status=MissionStatus.COMPLETED,
            created_at="2025-12-17T10:00:00Z",
            updated_at="2025-12-17T11:00:00Z",
            created_by="user_001",
            tenant_id=1,
        )
        assert detail.audit_trail == []
        assert detail.data_processing == []
        assert detail.metadata == {}

    def test_audit_list_response_creation(self):
        """Test AuditListResponse model creation"""
        response = AuditListResponse(
            missions=[],
            total=0,
            page=1,
            page_size=20,
            has_more=False,
            message="No missions",
        )
        assert response.total == 0
        assert response.has_more is False

    def test_gdpr_export_metadata_creation(self):
        """Test GDPRExportMetadata model creation"""
        metadata = GDPRExportMetadata(
            export_id="exp_123",
            exported_at="2025-12-17T12:00:00Z",
            exported_by="user_001",
            format=ExportFormat.JSON,
            purpose="Audit",
            legal_basis="GDPR Article 20",
            retention_notice="Store securely",
        )
        assert metadata.export_id == "exp_123"
        assert metadata.format == ExportFormat.JSON

    def test_gdpr_export_response_creation(self):
        """Test GDPRExportResponse model creation"""
        metadata = GDPRExportMetadata(
            export_id="exp_123",
            exported_at="2025-12-17T12:00:00Z",
            exported_by="user_001",
            format=ExportFormat.JSON,
            purpose="Audit",
            legal_basis="GDPR Article 20",
            retention_notice="Store securely",
        )
        mission = MissionAuditDetail(
            mission_id="mission_001",
            name="Test",
            status=MissionStatus.PENDING,
            created_at="2025-12-17T10:00:00Z",
            updated_at="2025-12-17T11:00:00Z",
            created_by="user_001",
            tenant_id=1,
        )
        response = GDPRExportResponse(
            metadata=metadata, mission=mission, message="Export complete", success=True
        )
        assert response.success is True


# ============================================================================
# Test Helper Functions
# ============================================================================


class TestHelperFunctions:
    """Test helper functions"""

    @pytest.mark.asyncio
    async def test_get_tenant_success(self):
        """Test get_tenant returns tenant ID when available"""
        with patch("src.core.api.audit_endpoints.get_current_tenant_id", return_value=1):
            tenant_id = await get_tenant()
            assert tenant_id == 1

    @pytest.mark.asyncio
    async def test_get_tenant_missing(self):
        """Test get_tenant raises exception when tenant missing"""
        with patch("src.core.api.audit_endpoints.get_current_tenant_id", return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                await get_tenant()
            assert exc_info.value.status_code == 400
            assert "Tenant context required" in str(exc_info.value.detail)

    def test_get_user_id_from_dict_user_id(self):
        """Test get_user_id extracts user_id from dict"""
        user = {"user_id": "user_123"}
        assert get_user_id(user) == "user_123"

    def test_get_user_id_from_dict_id(self):
        """Test get_user_id extracts id from dict"""
        user = {"id": "user_456"}
        assert get_user_id(user) == "user_456"

    def test_get_user_id_from_object(self):
        """Test get_user_id extracts id from object"""
        user = MagicMock()
        user.id = "user_789"
        assert get_user_id(user) == "user_789"

    def test_get_user_id_unknown(self):
        """Test get_user_id returns unknown when no id"""
        user = {}
        assert get_user_id(user) == "unknown"

    def test_get_user_id_no_id_attribute(self):
        """Test get_user_id handles object without id attribute"""
        user = MagicMock(spec=[])  # No attributes
        assert get_user_id(user) == "unknown"

    def test_get_user_email_from_dict(self):
        """Test get_user_email extracts email from dict"""
        user = {"email": "user@example.com"}
        assert get_user_email(user) == "user@example.com"

    def test_get_user_email_from_object(self):
        """Test get_user_email extracts email from object"""
        user = MagicMock()
        user.email = "obj@example.com"
        assert get_user_email(user) == "obj@example.com"

    def test_get_user_email_none(self):
        """Test get_user_email returns None when no email"""
        user = {}
        assert get_user_email(user) is None

    def test_get_user_email_no_email_attribute(self):
        """Test get_user_email handles object without email attribute"""
        user = MagicMock(spec=[])
        assert get_user_email(user) is None


# ============================================================================
# Test Generate Sample Audit Trail
# ============================================================================


class TestGenerateSampleAuditTrail:
    """Test audit trail generation"""

    def test_generates_audit_trail_for_pending(self):
        """Test audit trail for pending mission"""
        trail = generate_sample_audit_trail("mission_001", MissionStatus.PENDING)
        assert len(trail) >= 2  # At least created and updated
        assert trail[0].event_type == AuditEventType.CREATED

    def test_generates_audit_trail_for_approved(self):
        """Test audit trail for approved mission"""
        trail = generate_sample_audit_trail("mission_002", MissionStatus.APPROVED)
        event_types = [e.event_type for e in trail]
        assert AuditEventType.APPROVED in event_types

    def test_generates_audit_trail_for_rejected(self):
        """Test audit trail for rejected mission"""
        trail = generate_sample_audit_trail("mission_003", MissionStatus.REJECTED)
        event_types = [e.event_type for e in trail]
        assert AuditEventType.REJECTED in event_types

    def test_generates_audit_trail_for_in_progress(self):
        """Test audit trail for in_progress mission"""
        trail = generate_sample_audit_trail("mission_004", MissionStatus.IN_PROGRESS)
        event_types = [e.event_type for e in trail]
        assert AuditEventType.APPROVED in event_types
        assert AuditEventType.EXECUTED in event_types

    def test_generates_audit_trail_for_completed(self):
        """Test audit trail for completed mission"""
        trail = generate_sample_audit_trail("mission_005", MissionStatus.COMPLETED)
        event_types = [e.event_type for e in trail]
        assert AuditEventType.COMPLETED in event_types

    def test_generates_audit_trail_for_failed(self):
        """Test audit trail for failed mission"""
        trail = generate_sample_audit_trail("mission_006", MissionStatus.FAILED)
        event_types = [e.event_type for e in trail]
        assert AuditEventType.FAILED in event_types

    def test_audit_events_have_required_fields(self):
        """Test all audit events have required fields"""
        trail = generate_sample_audit_trail("mission_007", MissionStatus.COMPLETED)
        for event in trail:
            assert event.id is not None
            assert event.event_type is not None
            assert event.timestamp is not None
            assert event.actor_id is not None


# ============================================================================
# Test Generate Data Processing Records
# ============================================================================


class TestGenerateDataProcessingRecords:
    """Test data processing record generation"""

    def test_generates_records(self):
        """Test records are generated"""
        records = generate_data_processing_records()
        assert len(records) > 0

    def test_records_have_required_fields(self):
        """Test records have all required fields"""
        records = generate_data_processing_records()
        for record in records:
            assert record.category is not None
            assert record.purpose is not None
            assert record.legal_basis is not None
            assert record.retention_period is not None

    def test_records_cover_multiple_categories(self):
        """Test records cover multiple data categories"""
        records = generate_data_processing_records()
        categories = {r.category for r in records}
        assert len(categories) > 1


# ============================================================================
# Test Generate Sample Missions
# ============================================================================


class TestGenerateSampleMissions:
    """Test sample mission generation"""

    def test_generates_missions(self):
        """Test missions are generated"""
        missions = generate_sample_missions(1)
        assert len(missions) > 0

    def test_missions_have_required_fields(self):
        """Test missions have required fields"""
        missions = generate_sample_missions(1)
        for mission in missions:
            assert mission.mission_id is not None
            assert mission.name is not None
            assert mission.status is not None
            assert mission.tenant_id == 1

    def test_filter_by_status(self):
        """Test filtering by status"""
        missions = generate_sample_missions(1, MissionStatus.COMPLETED)
        for mission in missions:
            assert mission.status == MissionStatus.COMPLETED

    def test_filter_returns_empty_for_no_match(self):
        """Test filtering returns empty for no matches"""
        missions = generate_sample_missions(1, MissionStatus.CANCELLED)
        # CANCELLED not in sample data
        assert len(missions) == 0


# ============================================================================
# Test Get Mission Detail
# ============================================================================


class TestGetMissionDetail:
    """Test mission detail retrieval"""

    def test_get_existing_mission(self):
        """Test getting existing mission returns detail"""
        detail = get_mission_detail("mission_001", 1)
        assert detail is not None
        assert detail.mission_id == "mission_001"
        assert detail.tenant_id == 1

    def test_get_nonexistent_mission(self):
        """Test getting non-existent mission returns None"""
        detail = get_mission_detail("nonexistent_999", 1)
        assert detail is None

    def test_detail_includes_audit_trail(self):
        """Test detail includes audit trail"""
        detail = get_mission_detail("mission_001", 1)
        assert detail is not None
        assert len(detail.audit_trail) > 0

    def test_detail_includes_data_processing(self):
        """Test detail includes data processing records"""
        detail = get_mission_detail("mission_001", 1)
        assert detail is not None
        assert len(detail.data_processing) > 0


# ============================================================================
# Test Format CSV Export
# ============================================================================


class TestFormatCSVExport:
    """Test CSV export formatting"""

    def test_csv_contains_header(self):
        """Test CSV contains header section"""
        mission = get_mission_detail("mission_001", 1)
        csv = format_csv_export(mission)
        assert "# GDPR Data Export" in csv

    def test_csv_contains_mission_summary(self):
        """Test CSV contains mission summary"""
        mission = get_mission_detail("mission_001", 1)
        csv = format_csv_export(mission)
        assert "## Mission Summary" in csv
        assert "mission_001" in csv

    def test_csv_contains_audit_trail(self):
        """Test CSV contains audit trail"""
        mission = get_mission_detail("mission_001", 1)
        csv = format_csv_export(mission)
        assert "## Audit Trail" in csv

    def test_csv_contains_data_processing(self):
        """Test CSV contains data processing records"""
        mission = get_mission_detail("mission_001", 1)
        csv = format_csv_export(mission)
        assert "## Data Processing Records" in csv


# ============================================================================
# Test List Missions Endpoint
# ============================================================================


class TestListMissionsEndpoint:
    """Test list_missions_audit endpoint"""

    @pytest.mark.asyncio
    async def test_list_missions_basic(self):
        """Test basic mission listing"""
        mock_db = AsyncMock()
        mock_user = {"user_id": "test_user"}

        with patch("src.core.api.audit_endpoints.get_current_tenant_id", return_value=1):
            response = await list_missions_audit(
                status_filter=None,
                page=1,
                page_size=20,
                db=mock_db,
                tenant_id=1,
                current_user=mock_user,
            )

        assert isinstance(response, AuditListResponse)
        assert response.total > 0
        assert response.page == 1

    @pytest.mark.asyncio
    async def test_list_missions_with_status_filter(self):
        """Test mission listing with status filter"""
        mock_db = AsyncMock()
        mock_user = {"user_id": "test_user"}

        with patch("src.core.api.audit_endpoints.get_current_tenant_id", return_value=1):
            response = await list_missions_audit(
                status_filter=MissionStatus.COMPLETED,
                page=1,
                page_size=20,
                db=mock_db,
                tenant_id=1,
                current_user=mock_user,
            )

        for mission in response.missions:
            assert mission.status == MissionStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_list_missions_pagination(self):
        """Test mission listing pagination"""
        mock_db = AsyncMock()
        mock_user = {"user_id": "test_user"}

        with patch("src.core.api.audit_endpoints.get_current_tenant_id", return_value=1):
            response = await list_missions_audit(
                status_filter=None,
                page=1,
                page_size=2,
                db=mock_db,
                tenant_id=1,
                current_user=mock_user,
            )

        assert len(response.missions) <= 2
        # If total > 2, should have more pages
        if response.total > 2:
            assert response.has_more is True

    @pytest.mark.asyncio
    async def test_list_missions_page_2(self):
        """Test getting second page of missions"""
        mock_db = AsyncMock()
        mock_user = {"user_id": "test_user"}

        with patch("src.core.api.audit_endpoints.get_current_tenant_id", return_value=1):
            response = await list_missions_audit(
                status_filter=None,
                page=2,
                page_size=2,
                db=mock_db,
                tenant_id=1,
                current_user=mock_user,
            )

        assert response.page == 2


# ============================================================================
# Test Export Mission Endpoint
# ============================================================================


class TestExportMissionEndpoint:
    """Test export_mission_audit endpoint"""

    @pytest.mark.asyncio
    async def test_export_json_format(self):
        """Test JSON export format"""
        mock_db = AsyncMock()
        mock_user = {"user_id": "test_user", "email": "test@example.com"}

        with patch("src.core.api.audit_endpoints.get_current_tenant_id", return_value=1):
            response = await export_mission_audit(
                mission_id="mission_001",
                format=ExportFormat.JSON,
                include_processing_records=True,
                db=mock_db,
                tenant_id=1,
                current_user=mock_user,
            )

        assert response.status_code == 200
        content = json.loads(response.body)
        assert "metadata" in content
        assert "mission" in content
        assert content["success"] is True

    @pytest.mark.asyncio
    async def test_export_csv_format(self):
        """Test CSV export format"""
        mock_db = AsyncMock()
        mock_user = {"user_id": "test_user"}

        with patch("src.core.api.audit_endpoints.get_current_tenant_id", return_value=1):
            response = await export_mission_audit(
                mission_id="mission_001",
                format=ExportFormat.CSV,
                include_processing_records=True,
                db=mock_db,
                tenant_id=1,
                current_user=mock_user,
            )

        assert response.media_type == "text/csv"
        assert "mission_001" in response.body.decode()

    @pytest.mark.asyncio
    async def test_export_pdf_format(self):
        """Test PDF export format (simulated)"""
        mock_db = AsyncMock()
        mock_user = {"user_id": "test_user"}

        with patch("src.core.api.audit_endpoints.get_current_tenant_id", return_value=1):
            response = await export_mission_audit(
                mission_id="mission_001",
                format=ExportFormat.PDF,
                include_processing_records=True,
                db=mock_db,
                tenant_id=1,
                current_user=mock_user,
            )

        assert response.status_code == 200
        content = json.loads(response.body)
        assert "pdf-simulated" in response.headers.get("X-Export-Format", "")

    @pytest.mark.asyncio
    async def test_export_mission_not_found(self):
        """Test export returns 404 for non-existent mission"""
        mock_db = AsyncMock()
        mock_user = {"user_id": "test_user"}

        with patch("src.core.api.audit_endpoints.get_current_tenant_id", return_value=1):
            with pytest.raises(HTTPException) as exc_info:
                await export_mission_audit(
                    mission_id="nonexistent_999",
                    format=ExportFormat.JSON,
                    include_processing_records=True,
                    db=mock_db,
                    tenant_id=1,
                    current_user=mock_user,
                )

        assert exc_info.value.status_code == 404
        assert "not found" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_export_without_processing_records(self):
        """Test export without processing records"""
        mock_db = AsyncMock()
        mock_user = {"user_id": "test_user"}

        with patch("src.core.api.audit_endpoints.get_current_tenant_id", return_value=1):
            response = await export_mission_audit(
                mission_id="mission_001",
                format=ExportFormat.JSON,
                include_processing_records=False,
                db=mock_db,
                tenant_id=1,
                current_user=mock_user,
            )

        content = json.loads(response.body)
        assert content["mission"]["data_processing"] == []

    @pytest.mark.asyncio
    async def test_export_adds_export_event(self):
        """Test export adds export event to audit trail"""
        mock_db = AsyncMock()
        mock_user = {"user_id": "test_user"}

        with patch("src.core.api.audit_endpoints.get_current_tenant_id", return_value=1):
            response = await export_mission_audit(
                mission_id="mission_001",
                format=ExportFormat.JSON,
                include_processing_records=True,
                db=mock_db,
                tenant_id=1,
                current_user=mock_user,
            )

        content = json.loads(response.body)
        audit_trail = content["mission"]["audit_trail"]
        export_events = [e for e in audit_trail if e["event_type"] == "export"]
        assert len(export_events) > 0


# ============================================================================
# Test Router Configuration
# ============================================================================


class TestRouter:
    """Test router configuration"""

    def test_router_prefix(self):
        """Test router has correct prefix"""
        assert router.prefix == "/api/v1/audit"

    def test_router_tags(self):
        """Test router has correct tags"""
        assert "audit" in router.tags

    def test_missions_route_registered(self):
        """Test missions route is registered"""
        routes = [route.path for route in router.routes if hasattr(route, "path")]
        assert any("missions" in path for path in routes)

    def test_export_route_registered(self):
        """Test export route is registered"""
        routes = [route.path for route in router.routes if hasattr(route, "path")]
        assert any("export" in path for path in routes)

    def test_missions_endpoint_method(self):
        """Test missions endpoint supports GET"""
        for route in router.routes:
            if hasattr(route, "path") and route.path == "/missions":
                assert "GET" in route.methods
                break

    def test_export_endpoint_method(self):
        """Test export endpoint supports GET"""
        for route in router.routes:
            if hasattr(route, "path") and "export" in route.path:
                assert "GET" in route.methods
                break


# ============================================================================
# Test Edge Cases
# ============================================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    def test_mission_status_cancelled(self):
        """Test cancelled mission status"""
        trail = generate_sample_audit_trail("mission_x", MissionStatus.CANCELLED)
        assert len(trail) >= 2  # At least created and updated

    def test_empty_missions_list(self):
        """Test empty missions list response"""
        missions = generate_sample_missions(1, MissionStatus.CANCELLED)
        assert missions == []

    def test_different_mission_details(self):
        """Test getting different mission details"""
        detail_001 = get_mission_detail("mission_001", 1)
        detail_002 = get_mission_detail("mission_002", 1)

        assert detail_001 is not None
        assert detail_002 is not None
        assert detail_001.mission_id != detail_002.mission_id

    def test_mission_003_detail(self):
        """Test mission_003 detail retrieval"""
        detail = get_mission_detail("mission_003", 1)
        assert detail is not None
        assert detail.mission_id == "mission_003"
        assert detail.approved_by is None  # Pending mission


# ============================================================================
# Test Integration Scenarios
# ============================================================================


class TestIntegrationScenarios:
    """Test integration scenarios"""

    @pytest.mark.asyncio
    async def test_list_then_export_workflow(self):
        """Test listing then exporting a mission"""
        mock_db = AsyncMock()
        mock_user = {"user_id": "test_user"}

        # First list missions
        with patch("src.core.api.audit_endpoints.get_current_tenant_id", return_value=1):
            list_response = await list_missions_audit(
                status_filter=None,
                page=1,
                page_size=20,
                db=mock_db,
                tenant_id=1,
                current_user=mock_user,
            )

        assert list_response.total > 0
        mission_id = list_response.missions[0].mission_id

        # Then export that mission
        with patch("src.core.api.audit_endpoints.get_current_tenant_id", return_value=1):
            export_response = await export_mission_audit(
                mission_id=mission_id,
                format=ExportFormat.JSON,
                include_processing_records=True,
                db=mock_db,
                tenant_id=1,
                current_user=mock_user,
            )

        content = json.loads(export_response.body)
        assert content["mission"]["mission_id"] == mission_id

    @pytest.mark.asyncio
    async def test_filter_then_export_completed_missions(self):
        """Test filtering completed missions then exporting"""
        mock_db = AsyncMock()
        mock_user = {"user_id": "test_user"}

        # Filter for completed missions
        with patch("src.core.api.audit_endpoints.get_current_tenant_id", return_value=1):
            list_response = await list_missions_audit(
                status_filter=MissionStatus.COMPLETED,
                page=1,
                page_size=20,
                db=mock_db,
                tenant_id=1,
                current_user=mock_user,
            )

        if list_response.total > 0:
            mission_id = list_response.missions[0].mission_id

            # Export with CSV format
            with patch("src.core.api.audit_endpoints.get_current_tenant_id", return_value=1):
                export_response = await export_mission_audit(
                    mission_id=mission_id,
                    format=ExportFormat.CSV,
                    include_processing_records=True,
                    db=mock_db,
                    tenant_id=1,
                    current_user=mock_user,
                )

            assert export_response.media_type == "text/csv"
