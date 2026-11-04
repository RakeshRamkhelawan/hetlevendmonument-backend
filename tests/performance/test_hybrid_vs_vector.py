"""
Performance Comparison: Pure Vector vs Pure BM25 vs Hybrid Search

Measures:
1. Latency (P95)
2. Retrieval Quality (MRR - Mean Reciprocal Rank)
3. Throughput (QPS)
"""

import asyncio
import logging
import os
import sys
import time
from typing import Any, Dict, List

import numpy as np

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.core.knowledge.knowledge_manager import knowledge_manager
from src.core.search.bm25_service import bm25_service
from src.core.search.hybrid_search import HybridSearchConfig, hybrid_search

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("performance_test")

# Golden dataset: Query -> Expected Doc ID
GOLDEN_DATASET = {
    "Taj Mahal architecture marble": "doc_1",
    "Varanasi ancient city Ganges": "doc_2",
    "Classical Indian dance Bharatanatyam": "doc_3",
    "Ayurveda traditional medicine herbs": "doc_4",
    "Mughal empire history Akbar": "doc_5",
    "Vedic period Sanskrit texts": "doc_6",
    "Himalayas spiritual retreat yoga": "doc_7",
    "Indian spices curry cooking": "doc_8",
    "Yoga breathing pranayama benefits": "doc_9",
    "Diwali festival of lights victory": "doc_10",
}

CORPUS = [
    {
        "id": "doc_1",
        "content": "The Taj Mahal is an ivory-white marble mausoleum on the south bank of the Yamuna river in Agra. It was commissioned in 1632 by the Mughal emperor Shah Jahan to house the tomb of his favorite wife, Mumtaz Mahal.",
    },
    {
        "id": "doc_2",
        "content": "Varanasi is a city on the banks of the Ganges in Uttar Pradesh, India. A holiest of the seven sacred cities in Hinduism and Jainism, it played a central role in the development of Buddhism.",
    },
    {
        "id": "doc_3",
        "content": "Bharatanatyam is a major form of Indian classical dance that originated in Tamil Nadu. It is one of the eight widely recognized Indian classical dance forms.",
    },
    {
        "id": "doc_4",
        "content": "Ayurveda is an ancient system of medicine with historical roots in the Indian subcontinent. Global and modernized practices derived from Ayurveda traditions are a type of alternative medicine.",
    },
    {
        "id": "doc_5",
        "content": "The Mughal Empire was an early-modern empire in South Asia. For some two centuries, it stretched from the outer fringes of the Indus basin in the west, northern Afghanistan in the northwest, and Kashmir in the north.",
    },
    {
        "id": "doc_6",
        "content": "The Vedic period, or Vedic age, is the period in the late Bronze Age and early Iron Age of the history of India when the Vedas were composed in the northern Indian subcontinent.",
    },
    {
        "id": "doc_7",
        "content": "The Himalayas are a mountain range in Asia separating the plains of the Indian subcontinent from the Tibetan Plateau. Many peaks are sacred in Hinduism and Buddhism.",
    },
    {
        "id": "doc_8",
        "content": "Indian cuisine consists of a variety of regional and traditional cuisines native to the Indian subcontinent. Spices like turmeric, cumin, and coriander are essential.",
    },
    {
        "id": "doc_9",
        "content": "Yoga is a group of physical, mental, and spiritual practices or disciplines which originated in ancient India. Pranayama is the practice of breath control.",
    },
    {
        "id": "doc_10",
        "content": "Diwali is the Hindu festival of lights, with variations celebrated in other Indian religions. It symbolizes the spiritual victory of light over darkness.",
    },
]


async def setup_environment():
    """Initialize engines and index corpus"""
    logger.info("Setting up environment...")

    # 1. Initialize Knowledge Manager (Vector)
    if not knowledge_manager._initialized:
        await knowledge_manager.initialize()

    # 2. Build BM25 Index
    await bm25_service.build_index(tenant_id=1, documents=CORPUS, persist=False)

    # 3. Add to Vector Index
    # Since we use mock embedding in tests, we just need to ensure the retrieval engine has the docs
    for doc in CORPUS:
        # Generate a dummy embedding (384 dim for our mock)
        embedding = np.random.rand(384).astype(np.float32)
        # Manually inject into VectorIndex to avoid full DB setup
        from datetime import datetime, timezone

        from src.core.knowledge.retrieval_engine import KnowledgeEntry, KnowledgeType

        entry = KnowledgeEntry(
            content=doc["content"],
            knowledge_type=KnowledgeType.FACTUAL,
            metadata={"source": "benchmark"},
            tags=[],
            created_at=datetime.now(timezone.utc),
        )
        await knowledge_manager.retrieval_engine.index_entry(doc["id"], embedding, entry)


async def measure_mrr(method: str, config: HybridSearchConfig = None) -> float:
    """Calculate Mean Reciprocal Rank for a given method"""
    rr_scores = []

    for query, expected_id in GOLDEN_DATASET.items():
        if method == "hybrid":
            results = await hybrid_search(1, query, top_k=10, config=config)
            ids = [r.document_id for r in results]
        elif method == "bm25":
            raw_res = await bm25_service.search(1, query, top_k=10)
            ids = [r[0]["id"] for r in raw_res]
        elif method == "vector":
            from src.core.knowledge.retrieval_engine import SearchQuery

            res = await knowledge_manager.retrieval_engine.search(
                SearchQuery(query=query, limit=10)
            )
            ids = [r.entry_id for r in res]
        else:
            ids = []

        try:
            rank = ids.index(expected_id) + 1
            rr_scores.append(1.0 / rank)
        except ValueError:
            rr_scores.append(0.0)

    return np.mean(rr_scores)


async def measure_latency(method: str, config: HybridSearchConfig = None) -> Dict[str, float]:
    """Measure P50 and P95 latency"""
    latencies = []
    num_runs = 5

    for _ in range(num_runs):
        for query in GOLDEN_DATASET.keys():
            start = time.perf_counter()
            if method == "hybrid":
                await hybrid_search(1, query, top_k=10, config=config)
            elif method == "bm25":
                await bm25_service.search(1, query, top_k=10)
            elif method == "vector":
                from src.core.knowledge.retrieval_engine import SearchQuery

                await knowledge_manager.retrieval_engine.search(SearchQuery(query=query, limit=10))

            latencies.append((time.perf_counter() - start) * 1000)

    return {
        "p50": np.percentile(latencies, 50),
        "p95": np.percentile(latencies, 95),
        "avg": np.mean(latencies),
    }


async def run_comparison():
    await setup_environment()

    print("\n" + "=" * 60)
    print("SEARCH PERFORMANCE COMPARISON")
    print("=" * 60)
    print(f"{'Method':<15} | {'MRR':<8} | {'Avg (ms)':<8} | {'P95 (ms)':<8}")
    print("-" * 60)

    methods = [
        ("Pure Vector", "vector", None),
        ("Pure BM25", "bm25", None),
        ("Hybrid (RRF)", "hybrid", HybridSearchConfig(fusion_method="rrf")),
        (
            "Hybrid (Wgt)",
            "hybrid",
            HybridSearchConfig(fusion_method="weighted", alpha=0.5),
        ),
    ]

    for label, method_type, config in methods:
        mrr = await measure_mrr(method_type, config)
        lat = await measure_latency(method_type, config)
        print(f"{label:<15} | {mrr:<8.4f} | {lat['avg']:<8.2f} | {lat['p95']:<8.2f}")

    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(run_comparison())
