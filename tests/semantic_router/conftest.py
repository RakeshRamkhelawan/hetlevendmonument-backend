"""
Fixtures for Semantic Router tests.

These tests use REAL:
- Database (with pgvector)
- Ollama embeddings (local model)
- No mocks for core functionality
"""

import asyncio
import os

import pytest
import pytest_asyncio

from src.core.als.enterprise.departments.department_orchestrator import Department
from src.core.als.enterprise.departments.deterministic_router import DeterministicRouter
from src.core.semantic_router.embedders.ollama_embedder import OllamaEmbedder
from src.core.semantic_router.hybrid_router import GunaRouter
from src.core.semantic_router.router import SanskritiSemanticRouter


@pytest_asyncio.fixture
async def ollama_embedder():
    """Real Ollama embedder for tests."""
    embedder = OllamaEmbedder(
        model="nomic-embed-text", base_url=os.getenv("OLLAMA_URL", "http://localhost:11434")
    )

    # Check if Ollama is available
    if not await embedder.health_check():
        pytest.skip("Ollama not available - skipping tests that require embeddings")

    yield embedder

    await embedder.close()


@pytest_asyncio.fixture
async def semantic_router(ollama_embedder, db_session):
    """Real semantic router with database."""
    router = SanskritiSemanticRouter(
        tenant_id=1, embedder=ollama_embedder, similarity_threshold=0.7, top_k=5
    )
    await router.initialize()
    return router


@pytest.fixture
def deterministic_router():
    """Deterministic router (no external deps)."""
    return DeterministicRouter()


@pytest_asyncio.fixture
async def guna_router(ollama_embedder):
    """Full GunaRouter with all layers."""
    semantic = SanskritiSemanticRouter(
        tenant_id=1, embedder=ollama_embedder, similarity_threshold=0.7
    )
    await semantic.initialize()

    deterministic = DeterministicRouter()

    return GunaRouter(tenant_id=1, deterministic_router=deterministic, semantic_router=semantic)


@pytest.fixture
def sample_tasks():
    """Sample tasks for testing."""
    return {
        "finance_invoice": {
            "task": "Process vendor invoice",
            "description": "Invoice #12345 from Acme Corp for $5000",
            "expected_department": Department.FINANCE,
        },
        "hr_hiring": {
            "task": "Review job applications",
            "description": "Screen candidates for senior developer position",
            "expected_department": Department.HR,
        },
        "security_threat": {
            "task": "Investigate security alert",
            "description": "Potential breach detected in production logs",
            "expected_department": Department.IT_SECURITY,
        },
        "product_feature": {
            "task": "Design new dashboard",
            "description": "Create UX mockups for analytics dashboard",
            "expected_department": Department.PRODUCT_INNOVATION,
        },
        "unknown_quantum": {
            "task": "Implement quantum encryption",
            "description": "Research post-quantum cryptography methods",
            "expected_department": None,  # Ambiguous
        },
    }


@pytest.fixture
def prana_budgets():
    """Sample prana budgets for testing."""
    return {
        Department.FINANCE: 10000,
        Department.HR: 10000,
        Department.IT_SECURITY: 10000,
        Department.PRODUCT_INNOVATION: 10000,
        Department.SALES_MARKETING: 10000,
        Department.OPERATIONS_SUPPLY_CHAIN: 10000,
        Department.STRATEGY: 10000,
        Department.LEGAL_COMPLIANCE: 10000,
        Department.CUSTOMER_EXPERIENCE: 10000,
        Department.DATA_AI_GOVERNANCE: 10000,
    }


@pytest.fixture
def depleted_prana():
    """Depleted prana budgets for unhappy path testing."""
    return {
        Department.FINANCE: 5,  # Below Rajasic threshold (25)
        Department.HR: 5,
        Department.IT_SECURITY: 5,
        Department.PRODUCT_INNOVATION: 5,
    }
