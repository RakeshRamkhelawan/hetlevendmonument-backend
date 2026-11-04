"""
Slice 4: RetrieverAgent Implementation (GREEN Phase - Minimal Code)

Knowledge base retrieval agent that searches and ranks knowledge items
for context during procedure execution.

Responsibilities:
- Query knowledge base
- Score relevance
- Rank results
- Apply filters
- Enforce tenant isolation
"""

import logging
from typing import Any
from uuid import UUID

from src.core.agents.capabilities.schemas import RetrievalResult, RetrieverResult, RetrieverTask

logger = logging.getLogger(__name__)


class RetrieverAgent:
    """
    Knowledge base retrieval agent for context retrieval during execution.

    Searches knowledge base, scores relevance, ranks results, and provides
    context for procedure execution.
    """

    # Mock knowledge base for development
    MOCK_KB = [
        {
            "source_id": "550e8400-e29b-41d4-a716-446655440001",
            "source_type": "kb_article",
            "content": "Invoice approval requires manager sign-off and proper documentation. Amount thresholds determine routing logic. Always verify vendor details before approval.",
            "metadata": {
                "category": "finance",
                "author": "admin",
                "version": 1,
                "created": "2025-01-01",
            },
        },
        {
            "source_id": "550e8400-e29b-41d4-a716-446655440002",
            "source_type": "procedure",
            "content": "Step 1: Check invoice amount and vendor. Step 2: Route to manager if amount > $1000. Step 3: Manager reviews and approves. Step 4: Record in system.",
            "metadata": {
                "category": "workflow",
                "steps": 4,
                "duration_minutes": 15,
            },
        },
        {
            "source_id": "550e8400-e29b-41d4-a716-446655440003",
            "source_type": "template",
            "content": "Invoice approval email template. Subject: Invoice Approval Required. Body: Include invoice number, amount, date, and vendor details. Request response within 24 hours.",
            "metadata": {"category": "template", "format": "email", "version": 2},
        },
        {
            "source_id": "550e8400-e29b-41d4-a716-446655440004",
            "source_type": "policy",
            "content": "Invoice Approval Policy: All invoices must be approved before payment. Amounts under $500 require department manager approval. Amounts $500-$5000 require director approval. Amounts over $5000 require CFO approval.",
            "metadata": {"category": "policy", "effective": "2025-01-01"},
        },
        {
            "source_id": "550e8400-e29b-41d4-a716-446655440005",
            "source_type": "guide",
            "content": "Step-by-step guide to approving invoices: 1. Access invoice system. 2. Search by vendor name or invoice number. 3. Review invoice details. 4. Check against PO. 5. Approve or reject. 6. Add comments if needed.",
            "metadata": {"category": "guide", "level": "beginner"},
        },
        {
            "source_id": "550e8400-e29b-41d4-a716-446655440006",
            "source_type": "kb_article",
            "content": "Payment processing workflow for approved invoices. After approval, invoices are queued for payment. Payment terms depend on vendor contracts. Standard payment windows are 30 days.",
            "metadata": {
                "category": "finance",
                "author": "admin",
                "version": 1,
            },
        },
        {
            "source_id": "550e8400-e29b-41d4-a716-446655440007",
            "source_type": "kb_article",
            "content": "Compliance requirements for invoice approval. All approvals must be documented. Avoid conflicts of interest. Report suspicious invoices. Maintain audit trail.",
            "metadata": {"category": "compliance", "author": "legal"},
        },
    ]

    def __init__(self) -> None:
        """Initialize RetrieverAgent."""
        logger.info("RetrieverAgent initialized")

    async def retrieve(self, task: RetrieverTask) -> RetrieverResult:
        """
        Retrieve knowledge items matching the query.

        Args:
            task: RetrieverTask with query, filters, and constraints

        Returns:
            RetrieverResult with ranked knowledge items

        Raises:
            ValueError: If task validation fails
        """
        # Validate input
        self._validate_task(task)

        logger.info(f"Retrieval started for query: '{task.query}' (tenant: {task.tenant_id})")

        # Search knowledge base
        search_results = self._search(task.query)

        # Apply filters
        filtered_results = self._apply_filters(search_results, task.filters)

        # Score relevance
        scored_results = self._score_relevance(task.query, filtered_results)

        # Rank by relevance (descending)
        ranked_results = sorted(scored_results, key=lambda x: x["relevance_score"], reverse=True)

        # Apply max_results limit
        limited_results = ranked_results[: task.max_results]

        # Format results
        retrieval_results = [
            RetrievalResult(
                source_id=UUID(r["source_id"]),
                source_type=r["source_type"],
                content=r["content"],
                relevance_score=r["relevance_score"],
                metadata=r["metadata"],
            )
            for r in limited_results
        ]

        result = RetrieverResult(
            results=retrieval_results,
            total_count=len(ranked_results),
        )

        logger.info(
            f"Retrieval completed: {len(result.results)} results returned (total: {result.total_count})"
        )

        return result

    def _validate_task(self, task: RetrieverTask) -> None:
        """Validate task input."""
        if not task.query:
            raise ValueError("query is required")

        if not task.tenant_id:
            raise ValueError("tenant_id is required")

        if not (1 <= task.max_results <= 100):
            raise ValueError("max_results must be 1-100")

        logger.debug("Task validation passed")

    def _search(self, query: str) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """
        Search knowledge base for matching items.

        Args:
            query: Search query

        Returns: List[Any] of matching knowledge items  # TODO(TYPE): replace Any with concrete type
        """
        query_lower = query.lower()
        query_words = set(query_lower.split())

        matches: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for item in self.MOCK_KB:
            content_lower = str(item["content"]).lower()

            # Simple matching: check if any query word appears in content
            if any(word in content_lower for word in query_words):
                matches.append(item.copy())

        logger.debug(f"Search found {len(matches)} matches for query: {query}")

        return matches

    def _apply_filters(
        self, results: list[dict[str, Any]], filters: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """
        Apply filters to results.

        Args:
            results: Search results
            filters: Filters to apply

        Returns:
            Filtered results
        """
        if not filters:
            return results

        filtered = results

        # Filter by source_type
        if "source_type" in filters:
            source_type = filters["source_type"]
            filtered = [r for r in filtered if r["source_type"] == source_type]

        # Filter by category in metadata
        if "category" in filters:
            category = filters["category"]
            filtered = [r for r in filtered if r["metadata"].get("category") == category]

        logger.debug(f"Filters applied: {len(filtered)} results remain")

        return filtered

    def _score_relevance(self, query: str, results: list[dict[str, Any]]) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """
        Score relevance of results to query.

        Args:
            query: Search query
            results: Knowledge items

        Returns:
            Results with relevance scores
        """
        query_lower = query.lower()
        query_words = set(query_lower.split())

        scored: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for item in results:
            content_lower = item["content"].lower()

            # Count matching words
            matching_words = sum(1 for w in query_words if w in content_lower)

            # Calculate relevance (0.0-1.0)
            if query_words:
                relevance = min(1.0, matching_words / len(query_words))
            else:
                relevance = 0.0

            # Boost for exact phrase match
            if query_lower in content_lower:
                relevance = min(1.0, relevance + 0.2)

            item_copy = item.copy()
            item_copy["relevance_score"] = max(0.0, min(1.0, relevance))

            scored.append(item_copy)

        return scored


__all__ = ["RetrieverAgent"]
