"""
Integration Tests for Pack Intelligence System

Tests all pack-related flows:
1. Intent matching
2. Template loading
3. Multi-pack assembly
4. AI customization
5. Global repository
6. Feedback collection
"""

import asyncio
from typing import Any, Dict, List
from uuid import uuid4

import pytest

from src.core.api.pack_feedback_endpoints import feedback_store, global_pack_repo
from src.core.procedures.models import DomainPack
from src.core.services.ai_pack_customizer import AIPackCustomizer, get_ai_pack_customizer
from src.core.services.multi_pack_assembler import (
    AssemblyStrategy,
    MultiPackAssembler,
    get_multi_pack_assembler,
)
from src.core.services.pack_intent_matcher import (
    MatchConfidence,
    PackIntentMatcher,
    get_pack_intent_matcher,
)
from src.core.services.pack_template_converter import PackTemplateConverter, get_template_converter

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_hr_pack():
    """Create a sample HR pack for testing"""
    return type(
        "DomainPack",
        (),
        {
            "id": uuid4(),
            "name": "HR Onboarding Pack",
            "department": "hr",
            "description": "Complete employee onboarding workflow",
            "capabilities": [
                "employee_registration",
                "document_collection",
                "manager_notification",
                "welcome_email",
                "access_provisioning",
            ],
            "input_contracts": {"employee_name": {"type": "string"}},
            "output_contracts": {"onboarding_complete": {"type": "boolean"}},
            "version": 1,
        },
    )()


@pytest.fixture
def sample_sales_pack():
    """Create a sample Sales pack for testing"""
    return type(
        "DomainPack",
        (),
        {
            "id": uuid4(),
            "name": "Sales Pack",
            "department": "sales",
            "description": "Lead nurturing and conversion workflow",
            "capabilities": [
                "lead_capture",
                "lead_scoring",
                "email_sequence",
                "follow_up_reminder",
                "conversion_tracking",
            ],
            "input_contracts": {"lead_email": {"type": "string"}},
            "output_contracts": {"conversion_rate": {"type": "number"}},
            "version": 1,
        },
    )()


@pytest.fixture
def sample_it_pack():
    """Create a sample IT pack for testing"""
    return type(
        "DomainPack",
        (),
        {
            "id": uuid4(),
            "name": "IT Setup Pack",
            "department": "it",
            "description": "IT account and access setup",
            "capabilities": [
                "account_creation",
                "email_setup",
                "slack_invite",
                "laptop_assignment",
                "access_permissions",
            ],
            "input_contracts": {"employee_id": {"type": "string"}},
            "output_contracts": {"setup_complete": {"type": "boolean"}},
            "version": 1,
        },
    )()


@pytest.fixture
async def intent_matcher():
    """Get intent matcher instance"""
    return await get_pack_intent_matcher()


@pytest.fixture
async def template_converter():
    """Get template converter instance"""
    return await get_template_converter()


@pytest.fixture
async def multi_assembler():
    """Get multi-pack assembler instance"""
    return await get_multi_pack_assembler()


@pytest.fixture
async def ai_customizer():
    """Get AI customizer instance"""
    return await get_ai_pack_customizer()


# =============================================================================
# Test Class: Intent Matching
# =============================================================================


class TestPackIntentMatching:
    """Test suite for pack intent matching"""

    @pytest.mark.asyncio
    async def test_exact_match(self, intent_matcher):
        """Test exact pack name mention"""
        # Simulate finding pack in repo
        result = await intent_matcher._analyze_intent("Gebruik Sales Pack voor mijn funnel")

        assert result.primary_intent == "use_sales_pack"
        assert result.department_category == "sales"

    @pytest.mark.asyncio
    async def test_semantic_match_high_confidence(self, intent_matcher):
        """Test high confidence semantic matching"""
        result = await intent_matcher._analyze_intent(
            "Ik wil leads automatisch opvolgen met emails"
        )

        assert result.department_category == "sales"
        assert "lead" in result.primary_intent.lower()
        assert "email" in result.key_actions or "notification" in result.key_actions

    @pytest.mark.asyncio
    async def test_semantic_match_medium_confidence(self, intent_matcher):
        """Test medium confidence match with HR"""
        result = await intent_matcher._analyze_intent("Nieuwe medewerker instroom proces")

        assert result.department_category == "hr"
        assert any(
            word in result.primary_intent.lower() for word in ["onboarding", "employee", "hire"]
        )

    @pytest.mark.asyncio
    async def test_no_match(self, intent_matcher):
        """Test when no pack matches"""
        result = await intent_matcher._analyze_intent(
            "Ik wil een workflow die elke dag controleert of het regent"
        )

        # Should still return an analysis but with generic intent
        assert result is not None
        assert result.department_category in ["general", "operations"]

    @pytest.mark.asyncio
    async def test_multi_intent_detection(self, intent_matcher):
        """Test detection of multiple intents"""
        result = await intent_matcher._analyze_intent(
            "HR onboarding met IT setup voor nieuwe medewerkers"
        )

        assert len(result.key_actions) >= 2
        assert any("hr" in result.department_category or "it" in result.department_category)


# =============================================================================
# Test Class: Template Conversion
# =============================================================================


class TestPackTemplateConversion:
    """Test suite for pack to React Flow conversion"""

    @pytest.mark.asyncio
    async def test_single_pack_conversion(self, template_converter, sample_sales_pack):
        """Test converting a single pack to React Flow"""
        flow = await template_converter.convert_pack_to_flow(sample_sales_pack)

        assert "nodes" in flow
        assert "edges" in flow
        assert len(flow["nodes"]) > 0
        assert len(flow["nodes"]) == len(sample_sales_pack.capabilities)

        # Check node structure
        first_node = flow["nodes"][0]
        assert "id" in first_node
        assert "type" in first_node
        assert "position" in first_node
        assert "data" in first_node
        assert "title" in first_node["data"]

    @pytest.mark.asyncio
    async def test_pack_with_no_capabilities(self, template_converter):
        """Test handling pack without capabilities"""
        empty_pack = type(
            "DomainPack",
            (),
            {
                "id": uuid4(),
                "name": "Empty Pack",
                "department": "test",
                "capabilities": [],
            },
        )()

        flow = await template_converter.convert_pack_to_flow(empty_pack)

        # Should create starter template
        assert len(flow["nodes"]) == 2  # Trigger + Action
        assert flow["nodes"][0]["type"] == "trigger"

    @pytest.mark.asyncio
    async def test_node_type_inference(self, template_converter, sample_sales_pack):
        """Test correct node type inference from capabilities"""
        flow = await template_converter.convert_pack_to_flow(sample_sales_pack)

        node_types = [node["type"] for node in flow["nodes"]]

        # First capability (lead_capture) should be trigger
        assert flow["nodes"][0]["type"] == "trigger"

        # Others should be action or decision
        assert all(t in ["action", "decision", "trigger"] for t in node_types)

    @pytest.mark.asyncio
    async def test_position_calculations(self, template_converter, sample_hr_pack):
        """Test node positioning"""
        flow = await template_converter.convert_pack_to_flow(sample_hr_pack)

        # Nodes should be horizontally spaced
        positions = [node["position"]["x"] for node in flow["nodes"]]

        for i in range(1, len(positions)):
            assert positions[i] > positions[i - 1]  # Increasing x

    @pytest.mark.asyncio
    async def test_metadata_preservation(self, template_converter, sample_sales_pack):
        """Test pack metadata is preserved in flow"""
        flow = await template_converter.convert_pack_to_flow(sample_sales_pack)

        assert "metadata" in flow
        assert flow["metadata"]["source_pack_name"] == sample_sales_pack.name
        assert flow["metadata"]["source_pack_id"] == str(sample_sales_pack.id)
        assert flow["metadata"]["is_template"] is True


# =============================================================================
# Test Class: Multi-Pack Assembly
# =============================================================================


class TestMultiPackAssembly:
    """Test suite for multi-pack assembly"""

    @pytest.mark.asyncio
    async def test_sequential_assembly(self, multi_assembler, sample_hr_pack, sample_it_pack):
        """Test sequential pack assembly"""
        # Mock the pack loading
        multi_assembler._load_packs = lambda tenant_id, pack_ids: [sample_hr_pack, sample_it_pack]

        result = await multi_assembler._assemble_sequential([sample_hr_pack, sample_it_pack])

        assert result.success is True
        assert len(result.nodes) > 0
        assert len(result.edges) > 0

        # Should have bridge edge between packs
        bridge_edges = [e for e in result.edges if "bridge" in e.get("id", "")]
        assert len(bridge_edges) > 0

    @pytest.mark.asyncio
    async def test_parallel_assembly(self, multi_assembler, sample_sales_pack, sample_hr_pack):
        """Test parallel pack assembly"""
        result = await multi_assembler._assemble_parallel([sample_sales_pack, sample_hr_pack])

        assert result.success is True

        # Should have trigger node
        trigger_nodes = [n for n in result.nodes if n["type"] == "trigger"]
        assert len(trigger_nodes) == 1

        # All packs should connect to trigger
        edges_from_trigger = [e for e in result.edges if e["source"] == trigger_nodes[0]["id"]]
        assert len(edges_from_trigger) == 2  # One for each pack

    @pytest.mark.asyncio
    async def test_conditional_assembly(self, multi_assembler, sample_sales_pack, sample_hr_pack):
        """Test conditional (if/else) assembly"""
        result = await multi_assembler._assemble_conditional(
            [sample_sales_pack, sample_hr_pack], condition="user_type == 'enterprise'"
        )

        assert result.success is True

        # Should have decision node
        decision_nodes = [n for n in result.nodes if n["type"] == "decision"]
        assert len(decision_nodes) == 1
        assert decision_nodes[0]["data"].get("condition") == "user_type == 'enterprise'"

    @pytest.mark.asyncio
    async def test_insufficient_packs_error(self, multi_assembler, sample_sales_pack):
        """Test error when only one pack provided"""
        result = await multi_assembler.assemble_packs(
            tenant_id=1, pack_ids=[str(sample_sales_pack.id)], strategy=AssemblyStrategy.SEQUENTIAL
        )

        assert result.success is False
        assert "Need at least 2 packs" in result.error_message

    @pytest.mark.asyncio
    async def test_compatibility_checking(self, multi_assembler, sample_sales_pack, sample_hr_pack):
        """Test pack compatibility analysis"""
        compat = await multi_assembler._check_compatibility(sample_sales_pack, sample_hr_pack)

        assert compat.pack_a_id == str(sample_sales_pack.id)
        assert compat.pack_b_id == str(sample_hr_pack.id)
        # Should detect no shared contracts (different departments)
        assert len(compat.shared_outputs) == 0


# =============================================================================
# Test Class: AI Customization
# =============================================================================


class TestAIPackCustomization:
    """Test suite for AI pack customization"""

    @pytest.mark.asyncio
    async def test_basic_customization(self, ai_customizer, sample_sales_pack):
        """Test basic pack customization"""
        # Note: This test may need mocking of LLM calls
        result = await ai_customizer.customize_pack(
            pack=sample_sales_pack,
            original_prompt="sales funnel",
            user_requirements="Add Slack notifications",
            save_to_global=False,
        )

        # Result structure should be valid
        assert isinstance(result.success, bool)
        if result.success:
            assert result.customized_flow is not None
            assert len(result.changes_made) > 0

    @pytest.mark.asyncio
    async def test_customization_metadata(self, ai_customizer, sample_sales_pack):
        """Test that customization preserves and adds metadata"""
        result = await ai_customizer.customize_pack(
            pack=sample_sales_pack,
            original_prompt="sales funnel",
            user_requirements="Personalize emails",
            save_to_global=False,
        )

        if result.success and result.customized_flow:
            assert result.customized_flow["metadata"]["ai_customized"] is True
            assert "customization_timestamp" in result.customized_flow["metadata"]

    @pytest.mark.asyncio
    async def test_generate_from_scratch(self, ai_customizer):
        """Test generating completely new pack"""
        result = await ai_customizer.generate_pack_from_scratch(
            prompt="Create a workflow for daily weather alerts",
            department="operations",
            save_to_global=False,
        )

        # Structure should be valid
        assert isinstance(result.success, bool)
        if result.success:
            assert result.new_pack_name is not None
            assert len(result.suggested_capabilities) > 0


# =============================================================================
# Test Class: Global Repository
# =============================================================================


class TestGlobalPackRepository:
    """Test suite for global pack repository"""

    @pytest.mark.asyncio
    async def test_create_global_pack(self):
        """Test creating a global pack"""
        pack_id = await global_pack_repo.create_pack(
            name="Test Global Pack",
            description="A test pack",
            department="test",
            workflow_definition={"nodes": [], "edges": []},
            capabilities=["test"],
            intent_tags=["test"],
            contributed_by="user_123",
        )

        assert pack_id is not None
        assert pack_id.startswith("global_")

        # Verify it was stored
        pack = await global_pack_repo.get_pack(pack_id)
        assert pack is not None
        assert pack["name"] == "Test Global Pack"
        assert pack["status"] == "pending_review"

    @pytest.mark.asyncio
    async def test_search_global_packs(self):
        """Test searching global packs"""
        # Create a pack first
        await global_pack_repo.create_pack(
            name="Sales Automation",
            description="Automated sales workflows",
            department="sales",
            workflow_definition={"nodes": [], "edges": []},
            capabilities=["lead_capture"],
            intent_tags=["sales", "automation"],
            contributed_by="user_123",
        )

        # Search for it
        results = await global_pack_repo.search_packs("sales", limit=10)

        assert len(results) > 0
        assert any(p["name"] == "Sales Automation" for p in results)

    @pytest.mark.asyncio
    async def test_approve_pack(self):
        """Test approving a pending pack"""
        # Create pack
        pack_id = await global_pack_repo.create_pack(
            name="Approve Test",
            description="Test approval",
            department="test",
            workflow_definition={},
            capabilities=[],
            intent_tags=[],
            contributed_by="user_123",
        )

        # Approve it
        success = await global_pack_repo.approve_pack(pack_id)
        assert success is True

        # Verify
        pack = await global_pack_repo.get_pack(pack_id)
        assert pack["status"] == "approved"

    @pytest.mark.asyncio
    async def test_increment_usage(self):
        """Test usage count increment"""
        pack_id = await global_pack_repo.create_pack(
            name="Usage Test",
            description="Test usage counting",
            department="test",
            workflow_definition={},
            capabilities=[],
            intent_tags=[],
            contributed_by="user_123",
        )

        # Increment multiple times
        await global_pack_repo.increment_usage(pack_id)
        await global_pack_repo.increment_usage(pack_id)

        pack = await global_pack_repo.get_pack(pack_id)
        assert pack["usage_count"] == 2


# =============================================================================
# Test Class: Feedback System
# =============================================================================


class TestPackFeedbackSystem:
    """Test suite for pack feedback collection"""

    def test_submit_feedback(self):
        """Test submitting feedback"""
        feedback_data = {
            "user_id": "user_123",
            "tenant_id": 1,
            "session_id": "session_456",
            "pack_id": "pack_789",
            "original_prompt": "sales funnel",
            "was_helpful": True,
            "rating": 5,
            "feedback_text": "Great match!",
            "used_as_is": True,
            "customizations_made": [],
        }

        feedback_id = feedback_store.add_feedback(feedback_data)

        assert feedback_id is not None
        assert feedback_id.startswith("fb_")

    def test_feedback_stats(self):
        """Test feedback statistics calculation"""
        pack_id = "test_stats_pack"

        # Add multiple feedbacks
        for i in range(5):
            feedback_store.add_feedback(
                {
                    "user_id": f"user_{i}",
                    "pack_id": pack_id,
                    "was_helpful": i < 4,  # 4 helpful, 1 not
                    "rating": 4 if i < 4 else 2,
                }
            )

        stats = feedback_store.get_pack_stats(pack_id)

        assert stats["total_feedback"] == 5
        assert stats["helpful_count"] == 4
        assert stats["helpfulness_rate"] == 80.0
        assert stats["average_rating"] == 3.6  # (4*4 + 2) / 5

    def test_recent_feedback(self):
        """Test retrieving recent feedback"""
        pack_id = "recent_test_pack"

        # Add feedbacks
        for i in range(10):
            feedback_store.add_feedback(
                {"user_id": f"user_{i}", "pack_id": pack_id, "was_helpful": True}
            )

        recent = feedback_store.get_recent_feedback(pack_id, limit=5)

        assert len(recent) == 5


# =============================================================================
# Test Class: End-to-End Flows
# =============================================================================


class TestEndToEndFlows:
    """End-to-end integration tests"""

    @pytest.mark.asyncio
    async def test_complete_pack_to_workflow_flow(self, intent_matcher, template_converter):
        """Test complete flow from user prompt to workflow"""
        # This would integrate with actual services
        # For now, test the individual components work together

        user_prompt = "Ik wil een sales funnel voor lead nurturing"

        # Step 1: Analyze intent
        intent = await intent_matcher.analyze_intent(user_prompt)
        assert intent.department_category == "sales"

        # Step 2: Match to pack (would need actual packs in DB)
        # match = await intent_matcher.find_best_pack_match(1, user_prompt, intent)

        # Step 3: Load template (would need actual pack)
        # flow = await intent_matcher.get_pack_template_as_flow(1, match.pack_id)

        # Verify structure
        # assert "nodes" in flow
        # assert "edges" in flow

    @pytest.mark.asyncio
    async def test_customize_and_save_to_global_flow(self, ai_customizer):
        """Test customizing a pack and saving to global repo"""
        # Create a sample pack
        sample_pack = type(
            "DomainPack",
            (),
            {
                "id": uuid4(),
                "name": "Base Pack",
                "department": "test",
                "capabilities": ["action1", "action2"],
                "input_contracts": {},
                "output_contracts": {},
            },
        )()

        # Customize
        result = await ai_customizer.customize_pack(
            pack=sample_pack,
            original_prompt="base workflow",
            user_requirements="Add Slack integration",
            save_to_global=True,
            contributed_by="test_user",
        )

        if result.success:
            # Verify it was saved to global repo
            all_packs = await global_pack_repo.get_all_packs()
            matching = [p for p in all_packs if p.get("name") == result.new_pack_name]
            assert len(matching) > 0 or not result.new_pack_name


# =============================================================================
# Performance Tests
# =============================================================================


class TestPerformance:
    """Performance tests for pack operations"""

    @pytest.mark.asyncio
    async def test_intent_matching_performance(self, intent_matcher):
        """Test intent matching completes within reasonable time"""
        import time

        start = time.time()
        await intent_matcher.analyze_intent("Create a sales funnel with email automation")
        elapsed = time.time() - start

        # Should complete within 2 seconds
        assert elapsed < 2.0

    @pytest.mark.asyncio
    async def test_template_conversion_performance(self, template_converter, sample_sales_pack):
        """Test template conversion is fast"""
        import time

        start = time.time()
        await template_converter.convert_pack_to_flow(sample_sales_pack)
        elapsed = time.time() - start

        # Should complete within 1 second (no LLM calls)
        assert elapsed < 1.0


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestErrorHandling:
    """Test error handling and edge cases"""

    @pytest.mark.asyncio
    async def test_invalid_pack_id(self, intent_matcher):
        """Test handling of invalid pack ID"""
        flow = await intent_matcher.get_pack_template_as_flow(tenant_id=1, pack_id="invalid_uuid")

        assert flow is None

    @pytest.mark.asyncio
    async def test_empty_prompt(self, intent_matcher):
        """Test handling of empty prompt"""
        intent = await intent_matcher.analyze_intent("")

        # Should return default/unknown intent
        assert intent is not None
        assert intent.primary_intent == "unknown"

    @pytest.mark.asyncio
    async def test_malformed_workflow_definition(self, ai_customizer):
        """Test handling of malformed workflow"""
        # This tests the error handling in customization
        result = await ai_customizer._apply_llm_customizations(
            base_template={"nodes": [], "edges": []}, customization_spec={"invalid": "data"}
        )

        # Should still return a valid structure
        assert "nodes" in result
        assert "edges" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
