"""
Governance test fixtures.

This conftest.py provides fixtures used by governance tests.
"""

from uuid import uuid4

import pytest

# Import BiasDetector from test_bias_detection to provide the fixture
from tests.governance.test_bias_detection import BiasDetector


@pytest.fixture
async def bias_detector():
    """Create bias detector for testing."""
    return BiasDetector(tenant_id=f"tenant_{uuid4()}")


@pytest.fixture
def biased_content_samples():
    """Biased content examples for testing."""
    return {
        "gender": [
            "Women aren't suited for engineering roles",
            "Men are naturally better at leadership",
            "Girls should focus on domestic skills",
        ],
        "racial": [
            "All Asians are good at math",
            "Blacks are athletic but not intelligent",
            "Mexicans are lazy workers",
        ],
        "age": [
            "Old people are slow and forgetful",
            "Young people are irresponsible",
            "Millennials are too sensitive",
        ],
        "class": [
            "Poor people are lazy",
            "Rich people are greedy and selfish",
            "Working class people lack intelligence",
        ],
        "geographic": [
            "Rural areas are backwards and uneducated",
            "Urban dwellers are disconnected from nature",
            "Southern people are slow-talking",
        ],
    }


@pytest.fixture
def neutral_content_samples():
    """Neutral content that should NOT trigger bias detection."""
    return [
        "The engineering department has 30 people.",
        "We hired from multiple backgrounds.",
        "Our team is diverse in skills and experiences.",
        "Statistical analysis shows correlation but not causation.",
        "The project deadline is next week.",
        "Our office is located in the city center.",
        "We serve customers in multiple regions.",
        "The team includes people of various ages.",
        "Everyone has equal opportunities for advancement.",
        "Performance is measured by objective metrics.",
    ]
