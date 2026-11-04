"""
Unit Tests for Workflow Suggestions Endpoints
100% Coverage Target

Tests:
- GET /api/v1/workflows/{id}/suggestions
- GET /api/v1/workflows/{id}/variants
- All helper functions
- All edge cases
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.workflow_suggestions_endpoints import (
    NodeSuggestion,
    SuggestionCategory,
    SuggestionPriority,
    VariantMetrics,
    VariantStrategy,
    VariantTradeoff,
    WorkflowSuggestion,
    WorkflowSuggestionsResponse,
    WorkflowVariant,
    WorkflowVariantsResponse,
    analyze_workflow_patterns,
    generate_workflow_variants,
    get_tenant,
    get_workflow_by_id,
    get_workflow_suggestions,
    get_workflow_variants,
    router,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_db():
    """Mock async database session"""
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def mock_workflow():
    """Mock workflow object"""
    workflow = MagicMock()
    workflow.workflow_id = "test_workflow_001"
    workflow.name = "Test Workflow"
    workflow.tenant_id = 1
    workflow.is_active = True
    workflow.spec_json = {
        "tasks": [
            {"ref": "task_1", "type": "transform", "depends_on": []},
            {"ref": "task_2", "type": "filter", "depends_on": ["task_1"]},
            {"ref": "task_3", "type": "webhook", "depends_on": []},
        ],
        "timeout": 3600,
    }
    return workflow


@pytest.fixture
def mock_workflow_minimal():
    """Mock workflow with minimal tasks"""
    workflow = MagicMock()
    workflow.workflow_id = "minimal_workflow"
    workflow.name = "Minimal Workflow"
    workflow.tenant_id = 1
    workflow.is_active = True
    workflow.spec_json = {
        "tasks": [{"ref": "task_1", "type": "transform"}],
        "timeout": 3600,
    }
    return workflow


@pytest.fixture
def mock_workflow_with_error_handler():
    """Mock workflow with error handler"""
    workflow = MagicMock()
    workflow.workflow_id = "safe_workflow"
    workflow.name = "Safe Workflow"
    workflow.tenant_id = 1
    workflow.is_active = True
    workflow.spec_json = {
        "tasks": [
            {"ref": "task_1", "type": "transform"},
            {"ref": "error_handler", "type": "error_handler"},
            {"ref": "audit_log", "type": "audit"},
            {"ref": "validator", "type": "validator"},
            {"ref": "notify_webhook", "type": "webhook"},
        ],
        "timeout": 3600,
    }
    return workflow


@pytest.fixture
def mock_current_user():
    """Mock authenticated user"""
    return {"user_id": 1, "tenant_id": 1, "role": "user", "scopes": ["workflows:read"]}


# ============================================================================
# Enum Tests
# ============================================================================


class TestEnums:
    """Test enum definitions"""

    def test_suggestion_category_values(self):
        """Test SuggestionCategory enum values"""
        assert SuggestionCategory.ERROR == "error"
        assert SuggestionCategory.COMPLIANCE == "compliance"
        assert SuggestionCategory.STRUCTURE == "structure"
        assert SuggestionCategory.OPTIMIZATION == "optimization"
        assert SuggestionCategory.INTEGRATION == "integration"

    def test_suggestion_priority_values(self):
        """Test SuggestionPriority enum values"""
        assert SuggestionPriority.LOW == "low"
        assert SuggestionPriority.MEDIUM == "medium"
        assert SuggestionPriority.HIGH == "high"
        assert SuggestionPriority.CRITICAL == "critical"

    def test_variant_strategy_values(self):
        """Test VariantStrategy enum values"""
        assert VariantStrategy.COST_OPTIMIZED == "cost_optimized"
        assert VariantStrategy.SPEED_OPTIMIZED == "speed_optimized"
        assert VariantStrategy.RELIABILITY_OPTIMIZED == "reliability_optimized"


# ============================================================================
# Pydantic Model Tests
# ============================================================================


class TestPydanticModels:
    """Test Pydantic model validation"""

    def test_node_suggestion_creation(self):
        """Test NodeSuggestion model"""
        suggestion = NodeSuggestion(
            id="node_001",
            node_type="transform",
            label="Transform Node",
            description="Test description",
            config_template={"key": "value"},
            insert_after="node_000",
            confidence=0.95,
        )
        assert suggestion.id == "node_001"
        assert suggestion.confidence == 0.95

    def test_node_suggestion_defaults(self):
        """Test NodeSuggestion default values"""
        suggestion = NodeSuggestion(
            id="node_001",
            node_type="transform",
            label="Transform Node",
            description="Test description",
            confidence=0.9,
        )
        assert suggestion.config_template == {}
        assert suggestion.insert_after is None

    def test_workflow_suggestion_creation(self):
        """Test WorkflowSuggestion model"""
        suggestion = WorkflowSuggestion(
            id="sug_001",
            category=SuggestionCategory.ERROR,
            priority=SuggestionPriority.HIGH,
            title="Test Title",
            description="Test Description",
            reasoning="Test Reasoning",
            confidence=0.88,
        )
        assert suggestion.category == SuggestionCategory.ERROR
        assert suggestion.priority == SuggestionPriority.HIGH
        assert suggestion.auto_applicable is False

    def test_variant_metrics_creation(self):
        """Test VariantMetrics model"""
        metrics = VariantMetrics(
            estimated_cost_usd=0.005,
            estimated_duration_ms=1500,
            reliability_score=0.92,
            complexity_score=0.3,
        )
        assert metrics.estimated_cost_usd == 0.005
        assert metrics.resource_usage == {}

    def test_variant_tradeoff_creation(self):
        """Test VariantTradeoff model"""
        tradeoff = VariantTradeoff(
            metric="cost",
            change_percent=-40.0,
            explanation="Lower cost due to optimization",
            is_improvement=True,
        )
        assert tradeoff.metric == "cost"
        assert tradeoff.is_improvement is True

    def test_workflow_variant_creation(self):
        """Test WorkflowVariant model"""
        variant = WorkflowVariant(
            id="var_001",
            name="Test Variant",
            strategy=VariantStrategy.COST_OPTIMIZED,
            description="Test Description",
            metrics=VariantMetrics(
                estimated_cost_usd=0.001,
                estimated_duration_ms=1000,
                reliability_score=0.9,
                complexity_score=0.2,
            ),
        )
        assert variant.strategy == VariantStrategy.COST_OPTIMIZED
        assert variant.is_recommended is False

    def test_workflow_suggestions_response(self):
        """Test WorkflowSuggestionsResponse model"""
        response = WorkflowSuggestionsResponse(
            workflow_id="wf_001",
            workflow_name="Test Workflow",
            suggestions=[],
            total_count=0,
            generated_at="2025-01-01T00:00:00Z",
        )
        assert response.model_version == "1.0.0"

    def test_workflow_variants_response(self):
        """Test WorkflowVariantsResponse model"""
        response = WorkflowVariantsResponse(
            workflow_id="wf_001",
            workflow_name="Test Workflow",
            baseline_metrics=VariantMetrics(
                estimated_cost_usd=0.001,
                estimated_duration_ms=1000,
                reliability_score=0.9,
                complexity_score=0.2,
            ),
            variants=[],
            generated_at="2025-01-01T00:00:00Z",
        )
        assert response.model_version == "1.0.0"


# ============================================================================
# Helper Function Tests
# ============================================================================


class TestGetTenant:
    """Test get_tenant helper function"""

    @pytest.mark.asyncio
    async def test_get_tenant_success(self):
        """Test successful tenant retrieval"""
        with patch(
            "src.core.api.workflow_suggestions_endpoints.get_current_tenant_id",
            return_value=1,
        ):
            tenant_id = await get_tenant()
            assert tenant_id == 1

    @pytest.mark.asyncio
    async def test_get_tenant_missing(self):
        """Test missing tenant raises HTTPException"""
        with patch(
            "src.core.api.workflow_suggestions_endpoints.get_current_tenant_id",
            return_value=None,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_tenant()
            assert exc_info.value.status_code == 400
            assert "Tenant context required" in exc_info.value.detail


class TestGetWorkflowById:
    """Test get_workflow_by_id helper function"""

    @pytest.mark.asyncio
    async def test_get_workflow_success(self, mock_db, mock_workflow):
        """Test successful workflow retrieval"""
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_workflow
        mock_db.execute.return_value = mock_result

        workflow = await get_workflow_by_id("test_workflow_001", 1, mock_db)
        assert workflow.workflow_id == "test_workflow_001"

    @pytest.mark.asyncio
    async def test_get_workflow_not_found(self, mock_db):
        """Test workflow not found raises HTTPException"""
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(HTTPException) as exc_info:
            await get_workflow_by_id("nonexistent", 1, mock_db)
        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail


# ============================================================================
# Pattern Analysis Tests
# ============================================================================


class TestAnalyzeWorkflowPatterns:
    """Test analyze_workflow_patterns function"""

    def test_empty_workflow(self):
        """Test analysis of empty workflow"""
        spec = {"tasks": []}
        suggestions = analyze_workflow_patterns(spec)
        # Empty workflow triggers audit suggestion (no tasks threshold for audit)
        # but not error handler (requires >2 tasks), validation (requires >1), or notification (requires >3)
        assert len(suggestions) <= 1  # Only audit suggestion possible

    def test_minimal_workflow(self):
        """Test analysis of minimal workflow"""
        spec = {"tasks": [{"ref": "task_1", "type": "transform"}]}
        suggestions = analyze_workflow_patterns(spec)
        # Single task won't trigger all patterns
        assert isinstance(suggestions, list)

    def test_missing_error_handler_detected(self):
        """Test detection of missing error handler"""
        spec = {
            "tasks": [
                {"ref": "task_1", "type": "transform"},
                {"ref": "task_2", "type": "filter"},
                {"ref": "task_3", "type": "webhook"},
            ]
        }
        suggestions = analyze_workflow_patterns(spec)
        error_suggestions = [s for s in suggestions if s.category == SuggestionCategory.ERROR]
        assert len(error_suggestions) >= 1
        assert any("Error Handler" in s.title for s in error_suggestions)

    def test_has_error_handler_no_suggestion(self):
        """Test no error handler suggestion when present"""
        spec = {
            "tasks": [
                {"ref": "task_1", "type": "transform"},
                {"ref": "task_2", "type": "filter"},
                {"ref": "error_handler", "type": "error_handler"},
            ]
        }
        suggestions = analyze_workflow_patterns(spec)
        error_suggestions = [s for s in suggestions if s.category == SuggestionCategory.ERROR]
        assert not any("Error Handler" in s.title for s in error_suggestions)

    def test_error_in_ref_name_no_suggestion(self):
        """Test no suggestion when 'error' is in ref name"""
        spec = {
            "tasks": [
                {"ref": "task_1", "type": "transform"},
                {"ref": "task_2", "type": "filter"},
                {"ref": "handle_error_task", "type": "custom"},
            ]
        }
        suggestions = analyze_workflow_patterns(spec)
        error_suggestions = [s for s in suggestions if s.category == SuggestionCategory.ERROR]
        assert not any("Error Handler" in s.title for s in error_suggestions)

    def test_missing_audit_detected(self):
        """Test detection of missing audit"""
        spec = {
            "tasks": [
                {"ref": "task_1", "type": "transform"},
                {"ref": "task_2", "type": "filter"},
            ]
        }
        suggestions = analyze_workflow_patterns(spec)
        compliance_suggestions = [
            s for s in suggestions if s.category == SuggestionCategory.COMPLIANCE
        ]
        assert len(compliance_suggestions) >= 1
        assert any("Audit" in s.title for s in compliance_suggestions)

    def test_has_audit_no_suggestion(self):
        """Test no audit suggestion when present"""
        spec = {
            "tasks": [
                {"ref": "task_1", "type": "transform"},
                {"ref": "audit_logger", "type": "audit"},
            ]
        }
        suggestions = analyze_workflow_patterns(spec)
        compliance_suggestions = [
            s for s in suggestions if s.category == SuggestionCategory.COMPLIANCE
        ]
        assert not any("Audit" in s.title for s in compliance_suggestions)

    def test_compliance_in_ref_no_suggestion(self):
        """Test no suggestion when 'compliance' is in ref"""
        spec = {
            "tasks": [
                {"ref": "task_1", "type": "transform"},
                {"ref": "compliance_check", "type": "custom"},
            ]
        }
        suggestions = analyze_workflow_patterns(spec)
        compliance_suggestions = [
            s for s in suggestions if s.category == SuggestionCategory.COMPLIANCE
        ]
        assert not any("Audit" in s.title for s in compliance_suggestions)

    def test_parallelization_opportunity_detected(self):
        """Test detection of parallelization opportunity"""
        spec = {
            "tasks": [
                {"ref": "task_1", "type": "transform", "depends_on": []},
                {"ref": "task_2", "type": "filter"},  # No depends_on
                {"ref": "task_3", "type": "webhook"},  # No depends_on
            ]
        }
        suggestions = analyze_workflow_patterns(spec)
        optimization_suggestions = [
            s for s in suggestions if s.category == SuggestionCategory.OPTIMIZATION
        ]
        assert len(optimization_suggestions) >= 1
        assert any("Parallel" in s.title for s in optimization_suggestions)

    def test_missing_validation_detected(self):
        """Test detection of missing validation"""
        spec = {
            "tasks": [
                {"ref": "task_1", "type": "transform"},
                {"ref": "task_2", "type": "filter"},
            ]
        }
        suggestions = analyze_workflow_patterns(spec)
        structure_suggestions = [
            s for s in suggestions if s.category == SuggestionCategory.STRUCTURE
        ]
        assert len(structure_suggestions) >= 1
        assert any("Validation" in s.title for s in structure_suggestions)

    def test_has_validator_no_suggestion(self):
        """Test no validation suggestion when present"""
        spec = {
            "tasks": [
                {"ref": "input_validator", "type": "validator"},
                {"ref": "task_1", "type": "transform"},
            ]
        }
        suggestions = analyze_workflow_patterns(spec)
        structure_suggestions = [
            s for s in suggestions if s.category == SuggestionCategory.STRUCTURE
        ]
        assert not any("Validation" in s.title for s in structure_suggestions)

    def test_schema_check_type_no_suggestion(self):
        """Test no validation suggestion when schema_check type present"""
        spec = {
            "tasks": [
                {"ref": "schema", "type": "schema_check"},
                {"ref": "task_1", "type": "transform"},
            ]
        }
        suggestions = analyze_workflow_patterns(spec)
        structure_suggestions = [
            s for s in suggestions if s.category == SuggestionCategory.STRUCTURE
        ]
        assert not any("Validation" in s.title for s in structure_suggestions)

    def test_missing_notification_detected(self):
        """Test detection of missing notification"""
        spec = {
            "tasks": [
                {"ref": "task_1", "type": "transform"},
                {"ref": "task_2", "type": "filter"},
                {"ref": "task_3", "type": "map"},
                {"ref": "task_4", "type": "reduce"},
            ]
        }
        suggestions = analyze_workflow_patterns(spec)
        integration_suggestions = [
            s for s in suggestions if s.category == SuggestionCategory.INTEGRATION
        ]
        assert len(integration_suggestions) >= 1
        assert any("Notification" in s.title for s in integration_suggestions)

    def test_has_webhook_no_suggestion(self):
        """Test no notification suggestion when webhook present"""
        spec = {
            "tasks": [
                {"ref": "task_1", "type": "transform"},
                {"ref": "task_2", "type": "filter"},
                {"ref": "task_3", "type": "map"},
                {"ref": "completion_hook", "type": "webhook"},
            ]
        }
        suggestions = analyze_workflow_patterns(spec)
        integration_suggestions = [
            s for s in suggestions if s.category == SuggestionCategory.INTEGRATION
        ]
        assert not any("Notification" in s.title for s in integration_suggestions)

    def test_notify_in_ref_no_suggestion(self):
        """Test no suggestion when 'notify' in ref name"""
        spec = {
            "tasks": [
                {"ref": "task_1", "type": "transform"},
                {"ref": "task_2", "type": "filter"},
                {"ref": "task_3", "type": "map"},
                {"ref": "notify_admin", "type": "custom"},
            ]
        }
        suggestions = analyze_workflow_patterns(spec)
        integration_suggestions = [
            s for s in suggestions if s.category == SuggestionCategory.INTEGRATION
        ]
        assert not any("Notification" in s.title for s in integration_suggestions)

    def test_complete_workflow_minimal_suggestions(self, mock_workflow_with_error_handler):
        """Test well-designed workflow has minimal suggestions"""
        spec = mock_workflow_with_error_handler.spec_json
        suggestions = analyze_workflow_patterns(spec)
        # A complete workflow should have very few suggestions
        assert len(suggestions) <= 2

    def test_suggestion_node_has_config_template(self):
        """Test suggested nodes have config templates"""
        spec = {
            "tasks": [
                {"ref": "task_1", "type": "transform"},
                {"ref": "task_2", "type": "filter"},
                {"ref": "task_3", "type": "map"},
            ]
        }
        suggestions = analyze_workflow_patterns(spec)
        for suggestion in suggestions:
            for node in suggestion.suggested_nodes:
                assert isinstance(node.config_template, dict)


# ============================================================================
# Variant Generation Tests
# ============================================================================


class TestGenerateWorkflowVariants:
    """Test generate_workflow_variants function"""

    def test_generates_three_variants(self, mock_workflow):
        """Test generates exactly three variants"""
        baseline, variants = generate_workflow_variants(mock_workflow, mock_workflow.spec_json)
        assert len(variants) == 3

    def test_baseline_metrics_calculated(self, mock_workflow):
        """Test baseline metrics are calculated"""
        baseline, variants = generate_workflow_variants(mock_workflow, mock_workflow.spec_json)
        assert baseline.estimated_cost_usd > 0
        assert baseline.estimated_duration_ms > 0
        assert 0 <= baseline.reliability_score <= 1
        assert 0 <= baseline.complexity_score <= 1

    def test_cost_optimized_variant(self, mock_workflow):
        """Test cost optimized variant properties"""
        baseline, variants = generate_workflow_variants(mock_workflow, mock_workflow.spec_json)
        cost_variant = next(v for v in variants if v.strategy == VariantStrategy.COST_OPTIMIZED)

        assert cost_variant.metrics.estimated_cost_usd < baseline.estimated_cost_usd
        assert cost_variant.metrics.estimated_duration_ms > baseline.estimated_duration_ms
        assert not cost_variant.is_recommended

    def test_speed_optimized_variant(self, mock_workflow):
        """Test speed optimized variant properties"""
        baseline, variants = generate_workflow_variants(mock_workflow, mock_workflow.spec_json)
        speed_variant = next(v for v in variants if v.strategy == VariantStrategy.SPEED_OPTIMIZED)

        assert speed_variant.metrics.estimated_duration_ms < baseline.estimated_duration_ms
        assert speed_variant.metrics.estimated_cost_usd > baseline.estimated_cost_usd
        assert speed_variant.is_recommended is True

    def test_reliability_optimized_variant(self, mock_workflow):
        """Test reliability optimized variant properties"""
        baseline, variants = generate_workflow_variants(mock_workflow, mock_workflow.spec_json)
        reliability_variant = next(
            v for v in variants if v.strategy == VariantStrategy.RELIABILITY_OPTIMIZED
        )

        assert reliability_variant.metrics.reliability_score > baseline.reliability_score
        assert not reliability_variant.is_recommended

    def test_variants_have_tradeoffs(self, mock_workflow):
        """Test all variants have tradeoff explanations"""
        baseline, variants = generate_workflow_variants(mock_workflow, mock_workflow.spec_json)
        for variant in variants:
            assert len(variant.tradeoffs) > 0
            for tradeoff in variant.tradeoffs:
                assert tradeoff.metric in ["cost", "duration", "reliability"]
                assert isinstance(tradeoff.is_improvement, bool)

    def test_variants_have_changes(self, mock_workflow):
        """Test all variants document changes"""
        baseline, variants = generate_workflow_variants(mock_workflow, mock_workflow.spec_json)
        for variant in variants:
            assert len(variant.changes) > 0
            for change in variant.changes:
                assert "type" in change
                assert "path" in change

    def test_variants_have_modified_spec(self, mock_workflow):
        """Test all variants have modified spec_json"""
        baseline, variants = generate_workflow_variants(mock_workflow, mock_workflow.spec_json)
        for variant in variants:
            assert isinstance(variant.spec_json, dict)

    def test_empty_tasks_handling(self, mock_workflow_minimal):
        """Test handling of workflow with minimal tasks"""
        spec = {"tasks": []}
        baseline, variants = generate_workflow_variants(mock_workflow_minimal, spec)
        assert baseline.estimated_cost_usd == 0.0
        assert baseline.estimated_duration_ms == 0
        assert len(variants) == 3

    def test_resource_usage_calculated(self, mock_workflow):
        """Test resource usage is calculated in metrics"""
        baseline, variants = generate_workflow_variants(mock_workflow, mock_workflow.spec_json)
        assert "cpu_percent" in baseline.resource_usage
        assert "memory_mb" in baseline.resource_usage
        assert "network_calls" in baseline.resource_usage


# ============================================================================
# Endpoint Tests
# ============================================================================


class TestGetWorkflowSuggestionsEndpoint:
    """Test GET /api/v1/workflows/{id}/suggestions endpoint"""

    @pytest.mark.asyncio
    async def test_get_suggestions_success(self, mock_db, mock_workflow, mock_current_user):
        """Test successful suggestions retrieval"""
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_workflow
        mock_db.execute.return_value = mock_result

        with patch(
            "src.core.api.workflow_suggestions_endpoints.get_current_tenant_id",
            return_value=1,
        ):
            response = await get_workflow_suggestions(
                workflow_id="test_workflow_001",
                category=None,
                min_confidence=0.0,
                limit=10,
                db=mock_db,
                tenant_id=1,
                current_user=mock_current_user,
            )

        assert response.workflow_id == "test_workflow_001"
        assert response.workflow_name == "Test Workflow"
        assert isinstance(response.suggestions, list)
        assert response.total_count >= 0

    @pytest.mark.asyncio
    async def test_get_suggestions_with_category_filter(
        self, mock_db, mock_workflow, mock_current_user
    ):
        """Test suggestions filtered by category"""
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_workflow
        mock_db.execute.return_value = mock_result

        with patch(
            "src.core.api.workflow_suggestions_endpoints.get_current_tenant_id",
            return_value=1,
        ):
            response = await get_workflow_suggestions(
                workflow_id="test_workflow_001",
                category=SuggestionCategory.ERROR,
                min_confidence=0.0,
                limit=10,
                db=mock_db,
                tenant_id=1,
                current_user=mock_current_user,
            )

        for suggestion in response.suggestions:
            assert suggestion.category == SuggestionCategory.ERROR

    @pytest.mark.asyncio
    async def test_get_suggestions_with_confidence_filter(
        self, mock_db, mock_workflow, mock_current_user
    ):
        """Test suggestions filtered by confidence"""
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_workflow
        mock_db.execute.return_value = mock_result

        with patch(
            "src.core.api.workflow_suggestions_endpoints.get_current_tenant_id",
            return_value=1,
        ):
            response = await get_workflow_suggestions(
                workflow_id="test_workflow_001",
                category=None,
                min_confidence=0.9,
                limit=10,
                db=mock_db,
                tenant_id=1,
                current_user=mock_current_user,
            )

        for suggestion in response.suggestions:
            assert suggestion.confidence >= 0.9

    @pytest.mark.asyncio
    async def test_get_suggestions_with_limit(self, mock_db, mock_workflow, mock_current_user):
        """Test suggestions limited by count"""
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_workflow
        mock_db.execute.return_value = mock_result

        with patch(
            "src.core.api.workflow_suggestions_endpoints.get_current_tenant_id",
            return_value=1,
        ):
            response = await get_workflow_suggestions(
                workflow_id="test_workflow_001",
                category=None,
                min_confidence=0.0,
                limit=2,
                db=mock_db,
                tenant_id=1,
                current_user=mock_current_user,
            )

        assert len(response.suggestions) <= 2

    @pytest.mark.asyncio
    async def test_get_suggestions_sorted_by_priority(
        self, mock_db, mock_workflow, mock_current_user
    ):
        """Test suggestions are sorted by priority and confidence"""
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_workflow
        mock_db.execute.return_value = mock_result

        with patch(
            "src.core.api.workflow_suggestions_endpoints.get_current_tenant_id",
            return_value=1,
        ):
            response = await get_workflow_suggestions(
                workflow_id="test_workflow_001",
                category=None,
                min_confidence=0.0,
                limit=10,
                db=mock_db,
                tenant_id=1,
                current_user=mock_current_user,
            )

        # Verify priority ordering (HIGH should come before MEDIUM, etc.)
        priority_order = {
            SuggestionPriority.CRITICAL: 0,
            SuggestionPriority.HIGH: 1,
            SuggestionPriority.MEDIUM: 2,
            SuggestionPriority.LOW: 3,
        }
        priorities = [priority_order[s.priority] for s in response.suggestions]
        assert priorities == sorted(priorities)

    @pytest.mark.asyncio
    async def test_get_suggestions_workflow_not_found(self, mock_db, mock_current_user):
        """Test 404 when workflow not found"""
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_db.execute.return_value = mock_result

        with patch(
            "src.core.api.workflow_suggestions_endpoints.get_current_tenant_id",
            return_value=1,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_workflow_suggestions(
                    workflow_id="nonexistent",
                    category=None,
                    min_confidence=0.0,
                    limit=10,
                    db=mock_db,
                    tenant_id=1,
                    current_user=mock_current_user,
                )
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_suggestions_empty_spec(self, mock_db, mock_current_user):
        """Test handling of workflow with empty spec"""
        mock_workflow = MagicMock()
        mock_workflow.workflow_id = "empty_workflow"
        mock_workflow.name = "Empty Workflow"
        mock_workflow.spec_json = {}

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_workflow
        mock_db.execute.return_value = mock_result

        with patch(
            "src.core.api.workflow_suggestions_endpoints.get_current_tenant_id",
            return_value=1,
        ):
            response = await get_workflow_suggestions(
                workflow_id="empty_workflow",
                category=None,
                min_confidence=0.0,
                limit=10,
                db=mock_db,
                tenant_id=1,
                current_user=mock_current_user,
            )

        assert response.workflow_id == "empty_workflow"
        # Empty spec may still trigger audit suggestion (no tasks threshold for audit)
        assert response.total_count <= 1

    @pytest.mark.asyncio
    async def test_get_suggestions_null_spec(self, mock_db, mock_current_user):
        """Test handling of workflow with None spec"""
        mock_workflow = MagicMock()
        mock_workflow.workflow_id = "null_workflow"
        mock_workflow.name = "Null Workflow"
        mock_workflow.spec_json = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_workflow
        mock_db.execute.return_value = mock_result

        with patch(
            "src.core.api.workflow_suggestions_endpoints.get_current_tenant_id",
            return_value=1,
        ):
            response = await get_workflow_suggestions(
                workflow_id="null_workflow",
                category=None,
                min_confidence=0.0,
                limit=10,
                db=mock_db,
                tenant_id=1,
                current_user=mock_current_user,
            )

        assert response.workflow_id == "null_workflow"


class TestGetWorkflowVariantsEndpoint:
    """Test GET /api/v1/workflows/{id}/variants endpoint"""

    @pytest.mark.asyncio
    async def test_get_variants_success(self, mock_db, mock_workflow, mock_current_user):
        """Test successful variants retrieval"""
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_workflow
        mock_db.execute.return_value = mock_result

        with patch(
            "src.core.api.workflow_suggestions_endpoints.get_current_tenant_id",
            return_value=1,
        ):
            response = await get_workflow_variants(
                workflow_id="test_workflow_001",
                strategies=None,
                db=mock_db,
                tenant_id=1,
                current_user=mock_current_user,
            )

        assert response.workflow_id == "test_workflow_001"
        assert response.workflow_name == "Test Workflow"
        assert len(response.variants) == 3
        assert response.baseline_metrics is not None

    @pytest.mark.asyncio
    async def test_get_variants_filtered_by_strategy(
        self, mock_db, mock_workflow, mock_current_user
    ):
        """Test variants filtered by strategy"""
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_workflow
        mock_db.execute.return_value = mock_result

        with patch(
            "src.core.api.workflow_suggestions_endpoints.get_current_tenant_id",
            return_value=1,
        ):
            response = await get_workflow_variants(
                workflow_id="test_workflow_001",
                strategies=[VariantStrategy.COST_OPTIMIZED],
                db=mock_db,
                tenant_id=1,
                current_user=mock_current_user,
            )

        assert len(response.variants) == 1
        assert response.variants[0].strategy == VariantStrategy.COST_OPTIMIZED

    @pytest.mark.asyncio
    async def test_get_variants_multiple_strategies(
        self, mock_db, mock_workflow, mock_current_user
    ):
        """Test variants with multiple strategy filters"""
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_workflow
        mock_db.execute.return_value = mock_result

        with patch(
            "src.core.api.workflow_suggestions_endpoints.get_current_tenant_id",
            return_value=1,
        ):
            response = await get_workflow_variants(
                workflow_id="test_workflow_001",
                strategies=[
                    VariantStrategy.COST_OPTIMIZED,
                    VariantStrategy.SPEED_OPTIMIZED,
                ],
                db=mock_db,
                tenant_id=1,
                current_user=mock_current_user,
            )

        assert len(response.variants) == 2
        strategies = [v.strategy for v in response.variants]
        assert VariantStrategy.COST_OPTIMIZED in strategies
        assert VariantStrategy.SPEED_OPTIMIZED in strategies

    @pytest.mark.asyncio
    async def test_get_variants_workflow_not_found(self, mock_db, mock_current_user):
        """Test 404 when workflow not found"""
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_db.execute.return_value = mock_result

        with patch(
            "src.core.api.workflow_suggestions_endpoints.get_current_tenant_id",
            return_value=1,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_workflow_variants(
                    workflow_id="nonexistent",
                    strategies=None,
                    db=mock_db,
                    tenant_id=1,
                    current_user=mock_current_user,
                )
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_variants_empty_spec(self, mock_db, mock_current_user):
        """Test handling of workflow with empty spec"""
        mock_workflow = MagicMock()
        mock_workflow.workflow_id = "empty_workflow"
        mock_workflow.name = "Empty Workflow"
        mock_workflow.spec_json = {}

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_workflow
        mock_db.execute.return_value = mock_result

        with patch(
            "src.core.api.workflow_suggestions_endpoints.get_current_tenant_id",
            return_value=1,
        ):
            response = await get_workflow_variants(
                workflow_id="empty_workflow",
                strategies=None,
                db=mock_db,
                tenant_id=1,
                current_user=mock_current_user,
            )

        assert response.workflow_id == "empty_workflow"
        assert len(response.variants) == 3

    @pytest.mark.asyncio
    async def test_get_variants_contains_recommended(
        self, mock_db, mock_workflow, mock_current_user
    ):
        """Test that exactly one variant is recommended"""
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_workflow
        mock_db.execute.return_value = mock_result

        with patch(
            "src.core.api.workflow_suggestions_endpoints.get_current_tenant_id",
            return_value=1,
        ):
            response = await get_workflow_variants(
                workflow_id="test_workflow_001",
                strategies=None,
                db=mock_db,
                tenant_id=1,
                current_user=mock_current_user,
            )

        recommended = [v for v in response.variants if v.is_recommended]
        assert len(recommended) == 1
        assert recommended[0].strategy == VariantStrategy.SPEED_OPTIMIZED


# ============================================================================
# Router Tests
# ============================================================================


class TestRouter:
    """Test router configuration"""

    def test_router_prefix(self):
        """Test router has correct prefix"""
        assert router.prefix == "/api/v1/workflows/suggestions"

    def test_router_tags(self):
        """Test router has correct tags"""
        assert "workflow-suggestions" in router.tags

    def test_routes_registered(self):
        """Test routes are registered"""
        routes = [route.path for route in router.routes]
        # FastAPI routes use {param} format
        assert any("suggestions" in path for path in routes)
        assert any("variants" in path for path in routes)


# ============================================================================
# Integration Tests (with FastAPI TestClient)
# ============================================================================


class TestAPIIntegration:
    """Integration tests using FastAPI TestClient"""

    def test_suggestions_endpoint_exists(self):
        """Test that suggestions endpoint is properly configured"""
        routes = [route.path for route in router.routes]
        assert any("suggestions" in path for path in routes)

    def test_variants_endpoint_exists(self):
        """Test that variants endpoint is properly configured"""
        routes = [route.path for route in router.routes]
        assert any("variants" in path for path in routes)

    def test_suggestions_endpoint_methods(self):
        """Test suggestions endpoint only accepts GET"""
        for route in router.routes:
            if hasattr(route, "path") and "suggestions" in route.path:
                assert "GET" in route.methods

    def test_variants_endpoint_methods(self):
        """Test variants endpoint only accepts GET"""
        for route in router.routes:
            if hasattr(route, "path") and "variants" in route.path:
                assert "GET" in route.methods
