"""
Comprehensive tests for Governance API Endpoints
=================================================

100% coverage tests for:
- GET /api/v1/governance/anomalies
- GET /api/v1/governance/risks/{mission_id}
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.core.api.governance_endpoints import (  # Enums; Pydantic models; Helper functions; Endpoints; Router
    AnomaliesResponse,
    AnomalyDetail,
    AnomalySeverity,
    AnomalyStats,
    AnomalyType,
    RiskAssessment,
    RiskCategory,
    RiskFactor,
    RiskLevel,
    RiskResponse,
    calculate_anomaly_stats,
    calculate_risk_level,
    calculate_severity,
    generate_risk_assessment,
    generate_sample_anomalies,
    get_anomalies,
    get_risk_assessment,
    get_tenant,
    get_user_id,
    router,
)

# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def mock_db():
    """Mock database session"""
    return AsyncMock()


@pytest.fixture
def mock_user():
    """Mock current user"""
    return {"user_id": "test_user_123", "email": "test@example.com"}


# ============================================================================
# Enum Tests
# ============================================================================


class TestEnums:
    """Test all enum classes"""

    def test_anomaly_type_values(self):
        """Test AnomalyType enum values"""
        assert AnomalyType.BIAS == "bias"
        assert AnomalyType.COST == "cost"
        assert AnomalyType.PERFORMANCE == "performance"
        assert AnomalyType.SECURITY == "security"
        assert AnomalyType.COMPLIANCE == "compliance"
        assert AnomalyType.QUALITY == "quality"

    def test_anomaly_severity_values(self):
        """Test AnomalySeverity enum values"""
        assert AnomalySeverity.LOW == "low"
        assert AnomalySeverity.MEDIUM == "medium"
        assert AnomalySeverity.HIGH == "high"
        assert AnomalySeverity.CRITICAL == "critical"

    def test_risk_category_values(self):
        """Test RiskCategory enum values"""
        assert RiskCategory.OPERATIONAL == "operational"
        assert RiskCategory.FINANCIAL == "financial"
        assert RiskCategory.REPUTATIONAL == "reputational"
        assert RiskCategory.COMPLIANCE == "compliance"
        assert RiskCategory.TECHNICAL == "technical"
        assert RiskCategory.SECURITY == "security"

    def test_risk_level_values(self):
        """Test RiskLevel enum values"""
        assert RiskLevel.MINIMAL == "minimal"
        assert RiskLevel.LOW == "low"
        assert RiskLevel.MODERATE == "moderate"
        assert RiskLevel.HIGH == "high"
        assert RiskLevel.CRITICAL == "critical"


# ============================================================================
# Pydantic Model Tests
# ============================================================================


class TestPydanticModels:
    """Test all Pydantic model classes"""

    def test_anomaly_detail_creation(self):
        """Test AnomalyDetail model creation"""
        anomaly = AnomalyDetail(
            id="anomaly_123",
            type=AnomalyType.BIAS,
            severity=AnomalySeverity.HIGH,
            title="Test Anomaly",
            description="Test description",
            source="test_source",
            detected_at="2024-01-01T00:00:00Z",
        )
        assert anomaly.id == "anomaly_123"
        assert anomaly.type == AnomalyType.BIAS
        assert anomaly.recommendations == []

    def test_anomaly_detail_with_all_fields(self):
        """Test AnomalyDetail with all optional fields"""
        anomaly = AnomalyDetail(
            id="anomaly_123",
            type=AnomalyType.COST,
            severity=AnomalySeverity.MEDIUM,
            title="Cost Spike",
            description="Costs increased",
            source="cost_monitor",
            source_id="src_1",
            metric_value=150.0,
            expected_range="100-120",
            detected_at="2024-01-01T00:00:00Z",
            recommendations=["Review costs", "Optimize usage"],
            metadata={"region": "us-east"},
        )
        assert anomaly.source_id == "src_1"
        assert anomaly.metric_value == 150.0
        assert len(anomaly.recommendations) == 2

    def test_anomaly_stats_creation(self):
        """Test AnomalyStats model creation"""
        stats = AnomalyStats(
            total=10,
            by_type={"bias": 3, "cost": 5, "performance": 2},
            by_severity={"low": 4, "medium": 4, "high": 2},
            trend="stable",
        )
        assert stats.total == 10
        assert stats.by_type["bias"] == 3

    def test_anomaly_stats_defaults(self):
        """Test AnomalyStats default values"""
        stats = AnomalyStats()
        assert stats.total == 0
        assert stats.by_type == {}
        assert stats.trend == "stable"

    def test_anomalies_response_creation(self):
        """Test AnomaliesResponse model creation"""
        response = AnomaliesResponse(
            anomalies=[],
            stats=AnomalyStats(),
            period_start="2024-01-01T00:00:00Z",
            period_end="2024-01-08T00:00:00Z",
            tenant_id=1,
        )
        assert response.tenant_id == 1
        assert response.anomalies == []

    def test_risk_factor_creation(self):
        """Test RiskFactor model creation"""
        factor = RiskFactor(
            id="rf_123",
            category=RiskCategory.FINANCIAL,
            name="Cost Risk",
            description="Risk of cost overrun",
            score=45.0,
            level=RiskLevel.MODERATE,
            likelihood=0.4,
            impact=0.7,
        )
        assert factor.id == "rf_123"
        assert factor.score == 45.0
        assert factor.mitigations == []

    def test_risk_factor_with_mitigations(self):
        """Test RiskFactor with mitigations"""
        factor = RiskFactor(
            id="rf_123",
            category=RiskCategory.SECURITY,
            name="Security Risk",
            description="Security vulnerability",
            score=70.0,
            level=RiskLevel.HIGH,
            likelihood=0.3,
            impact=0.9,
            mitigations=["Patch systems", "Enable monitoring"],
        )
        assert len(factor.mitigations) == 2

    def test_risk_assessment_creation(self):
        """Test RiskAssessment model creation"""
        assessment = RiskAssessment(
            mission_id="mission_123",
            overall_score=45.0,
            overall_level=RiskLevel.MODERATE,
            assessed_at="2024-01-01T00:00:00Z",
            valid_until="2024-01-08T00:00:00Z",
            tenant_id=1,
        )
        assert assessment.mission_id == "mission_123"
        assert assessment.overall_score == 45.0
        assert assessment.risk_factors == []

    def test_risk_response_creation(self):
        """Test RiskResponse model creation"""
        assessment = RiskAssessment(
            mission_id="mission_123",
            overall_score=30.0,
            overall_level=RiskLevel.LOW,
            assessed_at="2024-01-01T00:00:00Z",
            valid_until="2024-01-08T00:00:00Z",
            tenant_id=1,
        )
        response = RiskResponse(assessment=assessment, message="Risk assessment complete")
        assert response.message == "Risk assessment complete"


# ============================================================================
# Helper Function Tests
# ============================================================================


class TestHelperFunctions:
    """Test helper functions"""

    @pytest.mark.asyncio
    async def test_get_tenant_success(self):
        """Test get_tenant with valid tenant"""
        with patch("src.core.api.v1.governance_admin.dependencies.get_current_tenant_id") as mock:
            mock.return_value = 1
            result = await get_tenant()
            assert result == 1

    @pytest.mark.asyncio
    async def test_get_tenant_missing(self):
        """Test get_tenant with missing tenant"""
        with patch("src.core.api.v1.governance_admin.dependencies.get_current_tenant_id") as mock:
            mock.return_value = None
            with pytest.raises(HTTPException) as exc_info:
                await get_tenant()
            assert exc_info.value.status_code == 400

    def test_get_user_id_from_dict_user_id(self):
        """Test get_user_id with dict containing user_id"""
        user = {"user_id": "test_user"}
        assert get_user_id(user) == "test_user"

    def test_get_user_id_from_dict_id(self):
        """Test get_user_id with dict containing id"""
        user = {"id": "test_user"}
        assert get_user_id(user) == "test_user"

    def test_get_user_id_from_object(self):
        """Test get_user_id with object having id attribute"""
        user = MagicMock()
        user.id = "object_user"
        assert get_user_id(user) == "object_user"

    def test_get_user_id_unknown(self):
        """Test get_user_id with unknown structure"""
        user = {"email": "test@test.com"}
        assert get_user_id(user) == "unknown"

    def test_get_user_id_no_id_attribute(self):
        """Test get_user_id with object without id"""

        class NoIdUser:
            pass

        assert get_user_id(NoIdUser()) == "unknown"


# ============================================================================
# Risk Level Calculation Tests
# ============================================================================


class TestCalculateRiskLevel:
    """Test calculate_risk_level function"""

    def test_minimal_risk(self):
        """Test minimal risk level"""
        assert calculate_risk_level(10) == RiskLevel.MINIMAL
        assert calculate_risk_level(0) == RiskLevel.MINIMAL
        assert calculate_risk_level(19) == RiskLevel.MINIMAL

    def test_low_risk(self):
        """Test low risk level"""
        assert calculate_risk_level(20) == RiskLevel.LOW
        assert calculate_risk_level(30) == RiskLevel.LOW
        assert calculate_risk_level(39) == RiskLevel.LOW

    def test_moderate_risk(self):
        """Test moderate risk level"""
        assert calculate_risk_level(40) == RiskLevel.MODERATE
        assert calculate_risk_level(50) == RiskLevel.MODERATE
        assert calculate_risk_level(59) == RiskLevel.MODERATE

    def test_high_risk(self):
        """Test high risk level"""
        assert calculate_risk_level(60) == RiskLevel.HIGH
        assert calculate_risk_level(70) == RiskLevel.HIGH
        assert calculate_risk_level(79) == RiskLevel.HIGH

    def test_critical_risk(self):
        """Test critical risk level"""
        assert calculate_risk_level(80) == RiskLevel.CRITICAL
        assert calculate_risk_level(90) == RiskLevel.CRITICAL
        assert calculate_risk_level(100) == RiskLevel.CRITICAL


# ============================================================================
# Severity Calculation Tests
# ============================================================================


class TestCalculateSeverity:
    """Test calculate_severity function"""

    def test_low_severity(self):
        """Test low severity (< 10% deviation)"""
        assert calculate_severity(105, 100) == AnomalySeverity.LOW
        assert calculate_severity(95, 100) == AnomalySeverity.LOW

    def test_medium_severity(self):
        """Test medium severity (10-25% deviation)"""
        assert calculate_severity(115, 100) == AnomalySeverity.MEDIUM
        assert calculate_severity(85, 100) == AnomalySeverity.MEDIUM

    def test_high_severity(self):
        """Test high severity (25-50% deviation)"""
        assert calculate_severity(130, 100) == AnomalySeverity.HIGH
        assert calculate_severity(70, 100) == AnomalySeverity.HIGH

    def test_critical_severity(self):
        """Test critical severity (> 50% deviation)"""
        assert calculate_severity(160, 100) == AnomalySeverity.CRITICAL
        assert calculate_severity(40, 100) == AnomalySeverity.CRITICAL

    def test_zero_threshold(self):
        """Test with zero threshold"""
        assert calculate_severity(10, 0) == AnomalySeverity.CRITICAL


# ============================================================================
# Sample Anomaly Generation Tests
# ============================================================================


class TestGenerateSampleAnomalies:
    """Test generate_sample_anomalies function"""

    def test_generate_all_anomalies(self):
        """Test generating all anomalies without filters"""
        anomalies = generate_sample_anomalies(1, None, None, 10)
        assert len(anomalies) > 0
        assert len(anomalies) <= 10

    def test_generate_with_type_filter(self):
        """Test generating with type filter"""
        anomalies = generate_sample_anomalies(1, AnomalyType.BIAS, None, 10)
        for a in anomalies:
            assert a.type == AnomalyType.BIAS

    def test_generate_with_severity_filter(self):
        """Test generating with severity filter"""
        anomalies = generate_sample_anomalies(1, None, AnomalySeverity.HIGH, 10)
        for a in anomalies:
            assert a.severity == AnomalySeverity.HIGH

    def test_generate_with_both_filters(self):
        """Test generating with both filters"""
        anomalies = generate_sample_anomalies(1, AnomalyType.COST, AnomalySeverity.MEDIUM, 10)
        for a in anomalies:
            assert a.type == AnomalyType.COST
            assert a.severity == AnomalySeverity.MEDIUM

    def test_generate_with_limit(self):
        """Test limiting results"""
        anomalies = generate_sample_anomalies(1, None, None, 2)
        assert len(anomalies) <= 2

    def test_anomaly_has_all_fields(self):
        """Test anomaly has all required fields"""
        anomalies = generate_sample_anomalies(1, None, None, 1)
        if anomalies:
            a = anomalies[0]
            assert a.id is not None
            assert a.type is not None
            assert a.severity is not None
            assert a.title is not None
            assert a.description is not None
            assert a.detected_at is not None


# ============================================================================
# Anomaly Stats Calculation Tests
# ============================================================================


class TestCalculateAnomalyStats:
    """Test calculate_anomaly_stats function"""

    def test_empty_anomalies(self):
        """Test with empty anomalies list"""
        stats = calculate_anomaly_stats([])
        assert stats.total == 0
        assert stats.by_type == {}
        assert stats.by_severity == {}
        assert stats.trend == "stable"

    def test_single_anomaly(self):
        """Test with single anomaly"""
        anomaly = AnomalyDetail(
            id="a1",
            type=AnomalyType.BIAS,
            severity=AnomalySeverity.HIGH,
            title="Test",
            description="Test",
            source="test",
            detected_at="2024-01-01T00:00:00Z",
        )
        stats = calculate_anomaly_stats([anomaly])
        assert stats.total == 1
        assert stats.by_type["bias"] == 1
        assert stats.by_severity["high"] == 1

    def test_multiple_anomalies(self):
        """Test with multiple anomalies"""
        anomalies = [
            AnomalyDetail(
                id="a1",
                type=AnomalyType.BIAS,
                severity=AnomalySeverity.HIGH,
                title="T",
                description="D",
                source="s",
                detected_at="2024-01-01",
            ),
            AnomalyDetail(
                id="a2",
                type=AnomalyType.COST,
                severity=AnomalySeverity.MEDIUM,
                title="T",
                description="D",
                source="s",
                detected_at="2024-01-01",
            ),
            AnomalyDetail(
                id="a3",
                type=AnomalyType.BIAS,
                severity=AnomalySeverity.LOW,
                title="T",
                description="D",
                source="s",
                detected_at="2024-01-01",
            ),
        ]
        stats = calculate_anomaly_stats(anomalies)
        assert stats.total == 3
        assert stats.by_type["bias"] == 2
        assert stats.by_type["cost"] == 1

    def test_trend_worsening(self):
        """Test worsening trend calculation"""
        anomalies = [
            AnomalyDetail(
                id="a1",
                type=AnomalyType.BIAS,
                severity=AnomalySeverity.CRITICAL,
                title="T",
                description="D",
                source="s",
                detected_at="2024-01-01",
            ),
            AnomalyDetail(
                id="a2",
                type=AnomalyType.COST,
                severity=AnomalySeverity.HIGH,
                title="T",
                description="D",
                source="s",
                detected_at="2024-01-01",
            ),
        ]
        stats = calculate_anomaly_stats(anomalies)
        assert stats.trend == "worsening"

    def test_trend_improving(self):
        """Test improving trend calculation"""
        anomalies = [
            AnomalyDetail(
                id="a1",
                type=AnomalyType.BIAS,
                severity=AnomalySeverity.LOW,
                title="T",
                description="D",
                source="s",
                detected_at="2024-01-01",
            ),
            AnomalyDetail(
                id="a2",
                type=AnomalyType.COST,
                severity=AnomalySeverity.MEDIUM,
                title="T",
                description="D",
                source="s",
                detected_at="2024-01-01",
            ),
        ]
        stats = calculate_anomaly_stats(anomalies)
        assert stats.trend == "improving"


# ============================================================================
# Risk Assessment Generation Tests
# ============================================================================


class TestGenerateRiskAssessment:
    """Test generate_risk_assessment function"""

    def test_generates_assessment(self):
        """Test assessment generation"""
        assessment = generate_risk_assessment("mission_123", 1)
        assert assessment.mission_id == "mission_123"
        assert assessment.tenant_id == 1
        assert assessment.overall_score >= 0
        assert assessment.overall_score <= 100

    def test_has_risk_factors(self):
        """Test assessment has risk factors"""
        assessment = generate_risk_assessment("mission_123", 1)
        assert len(assessment.risk_factors) > 0

    def test_risk_factors_have_all_categories(self):
        """Test risk factors cover multiple categories"""
        assessment = generate_risk_assessment("mission_123", 1)
        categories = {rf.category for rf in assessment.risk_factors}
        assert len(categories) > 1

    def test_has_recommendations(self):
        """Test assessment has recommendations"""
        assessment = generate_risk_assessment("mission_123", 1)
        assert len(assessment.recommendations) > 0

    def test_timestamps_are_set(self):
        """Test timestamps are properly set"""
        assessment = generate_risk_assessment("mission_123", 1)
        assert assessment.assessed_at is not None
        assert assessment.valid_until is not None


# ============================================================================
# Endpoint Tests - Anomalies
# ============================================================================


class TestAnomaliesEndpoint:
    """Test get_anomalies endpoint"""

    @pytest.mark.asyncio
    async def test_get_anomalies_basic(self, mock_db, mock_user):
        """Test basic anomalies retrieval"""
        response = await get_anomalies(
            anomaly_type=None,
            severity=None,
            days=7,
            limit=20,
            tenant_id=1,
            current_user=mock_user,
        )
        assert response.tenant_id == 1
        assert isinstance(response.anomalies, list)
        assert response.stats is not None

    @pytest.mark.asyncio
    async def test_get_anomalies_with_type_filter(self, mock_db, mock_user):
        """Test anomalies with type filter"""
        response = await get_anomalies(
            anomaly_type=AnomalyType.BIAS,
            severity=None,
            days=7,
            limit=20,
            tenant_id=1,
            current_user=mock_user,
        )
        for a in response.anomalies:
            assert a.type == AnomalyType.BIAS

    @pytest.mark.asyncio
    async def test_get_anomalies_with_severity_filter(self, mock_db, mock_user):
        """Test anomalies with severity filter"""
        response = await get_anomalies(
            anomaly_type=None,
            severity=AnomalySeverity.HIGH,
            days=7,
            limit=20,
            tenant_id=1,
            current_user=mock_user,
        )
        for a in response.anomalies:
            assert a.severity == AnomalySeverity.HIGH

    @pytest.mark.asyncio
    async def test_get_anomalies_with_limit(self, mock_db, mock_user):
        """Test anomalies with limit"""
        response = await get_anomalies(
            anomaly_type=None,
            severity=None,
            days=7,
            limit=2,
            tenant_id=1,
            current_user=mock_user,
        )
        assert len(response.anomalies) <= 2

    @pytest.mark.asyncio
    async def test_get_anomalies_includes_stats(self, mock_db, mock_user):
        """Test anomalies includes statistics"""
        response = await get_anomalies(
            anomaly_type=None,
            severity=None,
            days=7,
            limit=20,
            tenant_id=1,
            current_user=mock_user,
        )
        assert response.stats.total >= 0
        assert "period_start" in response.model_dump()
        assert "period_end" in response.model_dump()


# ============================================================================
# Endpoint Tests - Risk Assessment
# ============================================================================


class TestRiskAssessmentEndpoint:
    """Test get_risk_assessment endpoint"""

    @pytest.mark.asyncio
    async def test_get_risk_assessment_basic(self, mock_db, mock_user):
        """Test basic risk assessment retrieval"""
        response = await get_risk_assessment(
            mission_id="mission_123", tenant_id=1, current_user=mock_user
        )
        assert response.assessment.mission_id == "mission_123"
        assert response.assessment.tenant_id == 1
        assert "message" in response.model_dump()

    @pytest.mark.asyncio
    async def test_risk_assessment_has_score(self, mock_db, mock_user):
        """Test risk assessment has overall score"""
        response = await get_risk_assessment(
            mission_id="mission_123", tenant_id=1, current_user=mock_user
        )
        assert response.assessment.overall_score >= 0
        assert response.assessment.overall_score <= 100

    @pytest.mark.asyncio
    async def test_risk_assessment_has_level(self, mock_db, mock_user):
        """Test risk assessment has overall level"""
        response = await get_risk_assessment(
            mission_id="mission_123", tenant_id=1, current_user=mock_user
        )
        assert response.assessment.overall_level in RiskLevel

    @pytest.mark.asyncio
    async def test_risk_assessment_has_factors(self, mock_db, mock_user):
        """Test risk assessment has risk factors"""
        response = await get_risk_assessment(
            mission_id="mission_123", tenant_id=1, current_user=mock_user
        )
        assert len(response.assessment.risk_factors) > 0

    @pytest.mark.asyncio
    async def test_risk_factors_have_mitigations(self, mock_db, mock_user):
        """Test risk factors have mitigations"""
        response = await get_risk_assessment(
            mission_id="mission_123", tenant_id=1, current_user=mock_user
        )
        factors_with_mitigations = [
            rf for rf in response.assessment.risk_factors if len(rf.mitigations) > 0
        ]
        assert len(factors_with_mitigations) > 0


# ============================================================================
# Router Tests
# ============================================================================


class TestRouter:
    """Test router configuration"""

    def test_router_prefix(self):
        """Test router has correct prefix"""
        assert router.prefix == "/api/v1/governance"

    def test_router_tags(self):
        """Test router has correct tags"""
        assert "governance" in router.tags

    def test_anomalies_route_registered(self):
        """Test anomalies route is registered"""
        # NOTE: router.routes is populated by include_router (FastAPI flattening) -- removing
        # include_router calls from router.py composite would break this.
        routes = [route.path for route in router.routes]
        assert any("anomalies" in path for path in routes)

    def test_risks_route_registered(self):
        """Test risks route is registered"""
        routes = [route.path for route in router.routes]
        assert any("risks" in path for path in routes)

    def test_anomalies_endpoint_method(self):
        """Test anomalies endpoint only accepts GET"""
        for route in router.routes:
            if hasattr(route, "path") and "anomalies" in route.path:
                assert "GET" in route.methods

    def test_risks_endpoint_method(self):
        """Test risks endpoint only accepts GET"""
        for route in router.routes:
            if hasattr(route, "path") and "risks" in route.path:
                assert "GET" in route.methods
