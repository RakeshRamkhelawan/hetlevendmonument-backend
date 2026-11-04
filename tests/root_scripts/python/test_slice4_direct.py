"""
Slice 4: RetrieverAgent Direct Tests (No Fixtures - Rapid Verification)

Standalone tests to verify core RetrieverAgent logic without pytest infrastructure.
Run with: python test_slice4_direct.py
"""

import asyncio
import sys
from uuid import uuid4


async def test_1_basic_retrieval():
    """Test 1: Basic retrieval returns results."""
    print("\n🧪 Test 1: Basic Retrieval")

    from src.core.agents.capabilities.retriever_agent import RetrieverAgent
    from src.core.agents.capabilities.schemas import RetrieverTask

    agent = RetrieverAgent()
    tenant_id = uuid4()

    task = RetrieverTask(
        query="approval",
        filters={},
        tenant_id=tenant_id,
        max_results=10,
    )

    result = await agent.retrieve(task)

    assert result is not None, "Should have result"
    assert len(result.results) > 0, "Should have retrieved items"
    assert result.total_count > 0, "Should have total count"

    print(f"  ✅ Retrieved {len(result.results)} items (total: {result.total_count})")
    print(f"  ✅ First result type: {result.results[0].source_type}")

    return True


async def test_2_ranking_by_relevance():
    """Test 2: Results ranked by relevance (highest first)."""
    print("\n🧪 Test 2: Ranking By Relevance")

    from src.core.agents.capabilities.retriever_agent import RetrieverAgent
    from src.core.agents.capabilities.schemas import RetrieverTask

    agent = RetrieverAgent()
    tenant_id = uuid4()

    task = RetrieverTask(
        query="invoice approval",
        filters={},
        tenant_id=tenant_id,
        max_results=10,
    )

    result = await agent.retrieve(task)

    if len(result.results) > 1:
        # Check descending order
        for i in range(len(result.results) - 1):
            assert (
                result.results[i].relevance_score >= result.results[i + 1].relevance_score
            ), "Should be sorted descending"

    print("  ✅ Results ranked by relevance")
    for i, r in enumerate(result.results, 1):
        print(f"     {i}. {r.source_type} ({r.relevance_score:.2%}): {r.content[:60]}...")

    return True


async def test_3_respects_max_results():
    """Test 3: Respects max_results limit."""
    print("\n🧪 Test 3: Max Results Limit")

    from src.core.agents.capabilities.retriever_agent import RetrieverAgent
    from src.core.agents.capabilities.schemas import RetrieverTask

    agent = RetrieverAgent()
    tenant_id = uuid4()

    task = RetrieverTask(
        query="the",  # Common word, should match many
        filters={},
        tenant_id=tenant_id,
        max_results=2,
    )

    result = await agent.retrieve(task)

    assert len(result.results) <= 2, "Should not exceed max_results"
    print(f"  ✅ Returned {len(result.results)} results (max: 2)")
    print(f"  ✅ Total available: {result.total_count}")

    return True


async def test_4_source_type_filtering():
    """Test 4: Filters by source_type."""
    print("\n🧪 Test 4: Source Type Filtering")

    from src.core.agents.capabilities.retriever_agent import RetrieverAgent
    from src.core.agents.capabilities.schemas import RetrieverTask

    agent = RetrieverAgent()
    tenant_id = uuid4()

    task = RetrieverTask(
        query="approval",
        filters={"source_type": "kb_article"},
        tenant_id=tenant_id,
        max_results=10,
    )

    result = await agent.retrieve(task)

    # All should be kb_article type
    for r in result.results:
        assert r.source_type == "kb_article", f"Got {r.source_type}, expected kb_article"

    print(f"  ✅ All {len(result.results)} results are kb_article type")
    print(f"  ✅ Filtered from {result.total_count} total matches")

    return True


async def test_5_category_filtering():
    """Test 5: Filters by category metadata."""
    print("\n🧪 Test 5: Category Filtering")

    from src.core.agents.capabilities.retriever_agent import RetrieverAgent
    from src.core.agents.capabilities.schemas import RetrieverTask

    agent = RetrieverAgent()
    tenant_id = uuid4()

    task = RetrieverTask(
        query="approval",
        filters={"category": "finance"},
        tenant_id=tenant_id,
        max_results=10,
    )

    result = await agent.retrieve(task)

    # Check filters applied
    if result.results:
        finance_count = sum(1 for r in result.results if r.metadata.get("category") == "finance")
        assert finance_count > 0, "Should have finance category items"

    print(f"  ✅ Retrieved {len(result.results)} finance items")
    print(f"  ✅ Metadata categories: {set(r.metadata.get('category') for r in result.results)}")

    return True


async def test_6_empty_results_handling():
    """Test 6: Handles empty results."""
    print("\n🧪 Test 6: Empty Results Handling")

    from src.core.agents.capabilities.retriever_agent import RetrieverAgent
    from src.core.agents.capabilities.schemas import RetrieverTask

    agent = RetrieverAgent()
    tenant_id = uuid4()

    task = RetrieverTask(
        query="xyzabc123notarealquery",  # Unlikely to match
        filters={},
        tenant_id=tenant_id,
        max_results=10,
    )

    result = await agent.retrieve(task)

    assert len(result.results) == 0, "Should have no results"
    assert result.total_count == 0, "Total should be 0"

    print("  ✅ Empty query handled gracefully")
    print(f"  ✅ Results: {len(result.results)}, Total: {result.total_count}")

    return True


async def test_7_metadata_preserved():
    """Test 7: Metadata preserved in results."""
    print("\n🧪 Test 7: Metadata Preservation")

    from src.core.agents.capabilities.retriever_agent import RetrieverAgent
    from src.core.agents.capabilities.schemas import RetrieverTask

    agent = RetrieverAgent()
    tenant_id = uuid4()

    task = RetrieverTask(
        query="approval",
        filters={},
        tenant_id=tenant_id,
        max_results=10,
    )

    result = await agent.retrieve(task)

    assert len(result.results) > 0, "Should have results"

    for r in result.results:
        assert isinstance(r.metadata, dict), "Metadata should be dict"
        assert len(r.metadata) > 0, "Metadata should not be empty"

    print(f"  ✅ All {len(result.results)} results have metadata")
    print(f"  ✅ Sample metadata: {result.results[0].metadata}")

    return True


async def test_8_relevance_scored():
    """Test 8: All results have relevance scores."""
    print("\n🧪 Test 8: Relevance Scoring")

    from src.core.agents.capabilities.retriever_agent import RetrieverAgent
    from src.core.agents.capabilities.schemas import RetrieverTask

    agent = RetrieverAgent()
    tenant_id = uuid4()

    task = RetrieverTask(
        query="invoice approval process",
        filters={},
        tenant_id=tenant_id,
        max_results=10,
    )

    result = await agent.retrieve(task)

    assert len(result.results) > 0, "Should have results"

    for r in result.results:
        assert 0.0 <= r.relevance_score <= 1.0, "Score should be 0.0-1.0"

    print(f"  ✅ All {len(result.results)} results have valid scores (0.0-1.0)")
    print(
        f"  ✅ Score range: {min(r.relevance_score for r in result.results):.2%} - {max(r.relevance_score for r in result.results):.2%}"
    )

    return True


async def test_9_result_structure():
    """Test 9: Result structure complete."""
    print("\n🧪 Test 9: Result Structure Completeness")

    from src.core.agents.capabilities.retriever_agent import RetrieverAgent
    from src.core.agents.capabilities.schemas import RetrieverTask

    agent = RetrieverAgent()
    tenant_id = uuid4()

    task = RetrieverTask(
        query="approval",
        filters={},
        tenant_id=tenant_id,
        max_results=10,
    )

    result = await agent.retrieve(task)

    # Check result structure
    assert hasattr(result, "results"), "Should have results"
    assert hasattr(result, "total_count"), "Should have total_count"
    assert isinstance(result.results, list), "Results should be list"
    assert isinstance(result.total_count, int), "Total count should be int"

    # Check each result structure
    for r in result.results:
        assert hasattr(r, "source_id"), "Result should have source_id"
        assert hasattr(r, "source_type"), "Result should have source_type"
        assert hasattr(r, "content"), "Result should have content"
        assert hasattr(r, "relevance_score"), "Result should have relevance_score"
        assert hasattr(r, "metadata"), "Result should have metadata"

    print("  ✅ RetrieverResult structure valid")
    print(f"  ✅ RetrievalResult structure valid (x{len(result.results)})")

    return True


async def test_10_input_validation():
    """Test 10: Input validation works."""
    print("\n🧪 Test 10: Input Validation")

    from src.core.agents.capabilities.retriever_agent import RetrieverAgent
    from src.core.agents.capabilities.schemas import RetrieverTask

    agent = RetrieverAgent()

    # Test missing tenant_id
    try:
        task = RetrieverTask(
            query="test",
            filters={},
            tenant_id=None,
            max_results=10,
        )
        await agent.retrieve(task)
        assert False, "Should raise ValueError"
    except (ValueError, TypeError):
        print("  ✅ Missing tenant_id caught")

    # Test invalid max_results
    try:
        task = RetrieverTask(
            query="test",
            filters={},
            tenant_id=uuid4(),
            max_results=0,  # Invalid
        )
        await agent.retrieve(task)
        assert False, "Should raise ValueError"
    except ValueError:
        print("  ✅ Invalid max_results caught")

    # Test missing query
    try:
        task = RetrieverTask(
            query=None,
            filters={},
            tenant_id=uuid4(),
            max_results=10,
        )
        await agent.retrieve(task)
        assert False, "Should raise ValueError"
    except (ValueError, TypeError):
        print("  ✅ Missing query caught")

    return True


# ============================================================================
# TEST RUNNER
# ============================================================================


async def run_all_tests():
    """Run all direct tests."""
    tests = [
        test_1_basic_retrieval,
        test_2_ranking_by_relevance,
        test_3_respects_max_results,
        test_4_source_type_filtering,
        test_5_category_filtering,
        test_6_empty_results_handling,
        test_7_metadata_preserved,
        test_8_relevance_scored,
        test_9_result_structure,
        test_10_input_validation,
    ]

    print("\n" + "=" * 70)
    print("SLICE 4: RETRIEVER AGENT - DIRECT TESTS")
    print("=" * 70)

    passed = 0
    failed = 0

    for test_func in tests:
        try:
            result = await test_func()
            if result:
                passed += 1
        except Exception as e:
            failed += 1
            print(f"\n  ❌ FAILED: {str(e)}")
            import traceback

            traceback.print_exc()

    print("\n" + "=" * 70)
    print(f"RESULTS: {passed}/{len(tests)} PASSED")
    print("=" * 70)

    if failed == 0:
        print("\n✅ GREEN PHASE CONFIRMED - All tests passing!")
        return 0
    else:
        print(f"\n❌ {failed} test(s) failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(run_all_tests())
    sys.exit(exit_code)
