"""
Semantic Router - Rajasic Layer (Layer 3)

Context-aware routing using vector embeddings and similarity search.
Part of the Vedische Guna routing architecture.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sqlalchemy import text

from src.core.als.enterprise.departments.department_orchestrator import Department
from src.core.database.session import get_db_session
from src.core.semantic_router.embedders.ollama_embedder import OllamaEmbedder

logger = logging.getLogger(__name__)


@dataclass
class RoutingDecision:
    """Result of a semantic routing decision."""

    department: Department | None
    confidence: float
    similar_routes: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    used_guna: str = "rajasic"  # Always rajasic for semantic router

    def is_confident(self, threshold: float = 0.75) -> bool:
        """Check if routing decision meets confidence threshold."""
        return self.confidence >= threshold and self.department is not None


class SanskritiSemanticRouter:
    """
    Rajasic Router - Dynamisch, context-aware, adaptief.

    Uses vector embeddings to find semantically similar tasks and routes
    based on historical success patterns.

    Attributes:
        embedder: Embedding provider (Ollama)
        tenant_id: Current tenant for isolation
        similarity_threshold: Minimum cosine similarity for routing
    """

    def __init__(
        self,
        tenant_id: int,
        embedder: OllamaEmbedder,
        similarity_threshold: float = 0.75,
        top_k: int = 5,
    ) -> None:
        self.tenant_id = tenant_id
        self.embedder = embedder
        self.similarity_threshold = similarity_threshold
        self.top_k = top_k
        self._initialized = False

        logger.info(
            f"SemanticRouter initialized (tenant={tenant_id}, threshold={similarity_threshold})"
        )

    async def initialize(self) -> None:
        """Verify embedder is ready."""
        if not await self.embedder.health_check():
            logger.warning("Ollama embedder not healthy, semantic routing may fail")
        else:
            logger.info("[OK] SemanticRouter ready")

        self._initialized = True

    async def route(
        self,
        task: str,
        task_description: str = "",
        available_prana: dict[Department, int] | None = None,
    ) -> RoutingDecision:
        """
        Route task using semantic similarity.

        Args:
            task: Task name/type
            task_description: Additional context
            available_prana: Current prana budget per department

        Returns:
            RoutingDecision with department and confidence
        """
        if not self._initialized:
            await self.initialize()

        # Combine task and description for embedding
        full_query = f"{task} {task_description}".strip()

        try:
            # 1. Generate embedding
            query_embedding = await self.embedder.embed(full_query)

            # 2. Find similar routes from database
            similar_routes = await self._find_similar_routes(query_embedding)

            if not similar_routes:
                logger.debug(f"No similar routes found for: {task[:50]}...")
                return RoutingDecision(
                    department=None,
                    confidence=0.0,
                    similar_routes=[],
                )

            # 3. Weight by success rate and similarity
            weighted_departments = self._weight_departments(similar_routes)

            # 4. Check prana budget if provided
            if available_prana:
                weighted_departments = self._filter_by_prana(weighted_departments, available_prana)

            if not weighted_departments:
                logger.debug("No departments with sufficient prana")
                return RoutingDecision(
                    department=None,
                    confidence=0.0,
                    similar_routes=similar_routes,
                )

            # 5. Select best department
            best_dept_name, confidence = weighted_departments[0]

            try:
                best_department = Department(best_dept_name)
            except ValueError:
                logger.warning(f"Unknown department: {best_dept_name}")
                return RoutingDecision(
                    department=None,
                    confidence=0.0,
                    similar_routes=similar_routes,
                )

            logger.info(
                f"[ROUTED] Rajasic route: '{task[:30]}...' -> {best_department.value} "
                f"(confidence: {confidence:.2f})"
            )

            return RoutingDecision(
                department=best_department,
                confidence=confidence,
                similar_routes=similar_routes[:3],  # Top 3 for debugging
            )

        except Exception as e:
            logger.error(f"Semantic routing failed: {e}")
            return RoutingDecision(
                department=None,
                confidence=0.0,
                similar_routes=[],
            )

    async def _find_similar_routes(
        self,
        query_embedding: np.ndarray[Any, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """
        Find similar routes using pgvector cosine similarity.

        Returns list of routes with similarity scores.
        """
        # Convert numpy array to list for PostgreSQL
        embedding_list = query_embedding.tolist()

        async with get_db_session() as db:
            # Use pgvector's <=> operator for cosine distance
            # (1 - cosine_similarity = cosine_distance)
            result = await db.execute(
                text(
                    """
                    SELECT
                        route_name,
                        department,
                        utterance,
                        1 - (embedding <=> :embedding_vec) as similarity,
                        success_count,
                        failure_count
                    FROM semantic_routes
                    WHERE tenant_id = :tenant_id
                      AND embedding IS NOT NULL
                    ORDER BY embedding <=> :embedding_vec
                    LIMIT :top_k
                """
                ),
                {
                    "tenant_id": self.tenant_id,
                    "embedding_vec": str(embedding_list),  # pgvector expects array string
                    "top_k": self.top_k,
                },
            )

            rows = result.fetchall()

            routes: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            for row in rows:
                similarity = float(row[3])
                if similarity >= self.similarity_threshold:
                    routes.append(
                        {
                            "route_name": row[0],
                            "department": row[1],
                            "utterance": row[2],
                            "similarity": similarity,
                            "success_count": row[4],
                            "failure_count": row[5],
                        }
                    )

            return routes

    def _weight_departments(
        self, similar_routes: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    ) -> list[tuple[str, float]]:  # TODO(TYPE): replace Any with concrete type
        """
        Weight departments by similarity and success rate.

        Formula: weight = similarity * (success_rate + 0.1)
        """
        dept_scores: dict[str, list[float]] = {}

        for route in similar_routes:
            dept = route["department"]
            similarity = route["similarity"]

            # Calculate success rate
            total = route["success_count"] + route["failure_count"]
            if total > 0:
                success_rate = route["success_count"] / total
            else:
                success_rate = 0.5  # Neutral for new routes

            # Weighted score
            score = similarity * (success_rate + 0.1)

            if dept not in dept_scores:
                dept_scores[dept] = []
            dept_scores[dept].append(score)

        # Average scores per department
        weighted = [(dept, float(np.mean(scores))) for dept, scores in dept_scores.items()]

        # Sort by score descending
        weighted.sort(key=lambda x: x[1], reverse=True)

        return weighted

    def _filter_by_prana(
        self,
        weighted_depts: list[tuple[str, float]],
        available_prana: dict[Department, int],
    ) -> list[tuple[str, float]]:
        """
        Filter departments by available prana.

        Rajasic routing requires 25+ prana.
        """
        filtered: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for dept_name, score in weighted_depts:
            try:
                dept = Department(dept_name)
                if available_prana.get(dept, 0) >= 25:
                    filtered.append((dept_name, score))
            except ValueError:
                continue

        return filtered

    async def learn(
        self,
        task: str,
        correct_department: Department,
        was_successful: bool = True,
    ) -> None:
        """
        Learn from routing outcome - update success/failure counts.

        This is how the Rajasic layer becomes wiser over time.
        """
        try:
            # Generate embedding for the task
            embedding = await self.embedder.embed(task)
            embedding_list = embedding.tolist()

            async with get_db_session() as db:
                # Upsert route with feedback
                await db.execute(
                    text(
                        """
                        INSERT INTO semantic_routes
                            (tenant_id, route_name, department, utterance, embedding,
                             success_count, failure_count)
                        VALUES
                            (:tenant_id, :route_name, :dept, :utterance, :embedding,
                             :success, :failure)
                        ON CONFLICT (tenant_id, route_name, utterance)
                        DO UPDATE SET
                            success_count = semantic_routes.success_count + :success,
                            failure_count = semantic_routes.failure_count + :failure,
                            updated_at = CURRENT_TIMESTAMP
                    """
                    ),
                    {
                        "tenant_id": self.tenant_id,
                        "route_name": f"route_{correct_department.value}",
                        "dept": correct_department.value,
                        "utterance": task[:1000],  # Truncate if needed
                        "embedding": str(embedding_list),
                        "success": 1 if was_successful else 0,
                        "failure": 0 if was_successful else 1,
                    },
                )
                await db.commit()

            action = "success" if was_successful else "failure"
            logger.debug(f"Learned from {action}: {task[:50]}... -> {correct_department.value}")

        except Exception as e:
            logger.error(f"Failed to learn from feedback: {e}")

    async def get_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get routing statistics for this tenant."""
        async with get_db_session() as db:
            result = await db.execute(
                text(
                    """
                    SELECT
                        COUNT(*) as total_routes,
                        COUNT(DISTINCT department) as unique_depts,
                        SUM(success_count) as total_successes,
                        SUM(failure_count) as total_failures
                    FROM semantic_routes
                    WHERE tenant_id = :tenant_id
                """
                ),
                {"tenant_id": self.tenant_id},
            )

            row = result.fetchone()

            total = (row[2] + row[3]) if row else 0
            success_rate = (row[2] / total) if row and total > 0 else 0

            return {
                "total_routes": row[0] if row else 0,
                "unique_departments": row[1] if row else 0,
                "total_successes": row[2] if row else 0,
                "total_failures": row[3] if row else 0,
                "success_rate": success_rate,
            }
