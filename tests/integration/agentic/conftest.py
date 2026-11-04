"""
Agentic Domain Integration Test Fixtures

Provides isolated, consistent fixtures for agentic domain tests.
Ensures proper database session alignment with integration_client.
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agentic.models import PromptTemplate


@pytest_asyncio.fixture
async def agentic_template(postgres_session: AsyncSession) -> PromptTemplate:
    """
    Create a test prompt template for agentic tests.

    Uses postgres_session directly to ensure database session
    alignment with integration_client fixture.
    """
    template = PromptTemplate(
        name="Agentic Test Template",
        system_prompt="System Prompt for Testing",
        version="1.0",
    )
    postgres_session.add(template)
    await postgres_session.flush()
    await postgres_session.refresh(template)
    return template
