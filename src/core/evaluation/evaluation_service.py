"""
Evaluation Service - Automated RAG Evaluation Framework
Integrates with ragchecker to measure Correctness, Faithfulness, and Relevance.
Persists results to PostgreSQL for auditing and dashboarding.
"""

import asyncio
import importlib
import threading
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, cast

from prometheus_client import Counter, Summary
from sqlalchemy import func, select

from src.core.config.unified_config import config
from src.core.database.database import db_manager
from src.core.exceptions.exceptions import SanskritiError
from src.core.models.evaluation_models import EvaluationResult
from src.core.shared.production_logging import SafeLogger

logger = SafeLogger(__name__)

#: De tenant van de evaluatie die nu draait. `asyncio.to_thread` kopieert de context mee, dus de synchrone
#: wrapper van ragchecker ziet de tenant van `evaluate_rag_response` (brief 2026-10-20, ADR-041 B14).
_EVALUATIE_TENANT: ContextVar[int | None] = ContextVar("evaluatie_tenant", default=None)

# Prometheus Metrics
RAG_FAITHFULNESS = Summary(
    "rag_faithfulness_score", "Faithfulness score of RAG responses", ["tenant_id"]
)
RAG_RELEVANCE = Summary("rag_relevance_score", "Relevance score of RAG responses", ["tenant_id"])
RAG_CONTEXT_PRECISION = Summary(
    "rag_context_precision", "Context precision of retriever", ["tenant_id"]
)
RAG_QUALITY_GATE_FAILURES = Counter(
    "rag_quality_gate_failures_total",
    "Number of times quality gate failed",
    ["tenant_id", "metric"],
)
RAG_EVAL_LATENCY = Summary(
    "rag_evaluation_latency_ms", "Latency of evaluation pipeline in ms", ["tenant_id"]
)


class LowQualityResponseError(SanskritiError):
    """Raised when a RAG response fails the quality gate"""

    def __init__(self, details: dict[str, Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        super().__init__(
            message="RAG response failed quality gate requirements",
            error_code="LOW_QUALITY_RESPONSE",
            status_code=422,
            details=details,
        )


@dataclass
class QualityGateConfig:
    """Configuration for quality gate thresholds"""

    min_faithfulness: float = field(default_factory=lambda: config.eval_min_faithfulness)
    min_precision: float = field(default_factory=lambda: config.eval_min_precision)
    min_context_precision: float = field(default_factory=lambda: config.eval_min_context_precision)
    block_on_failure: bool = field(default_factory=lambda: config.eval_block_on_low_quality)


@dataclass
class EvaluationMetrics:
    """RAG Evaluation Metrics"""

    correctness: float = 0.0
    faithfulness: float = 0.0
    relevance: float = 0.0
    precision: float = 0.0
    recall: float = 0.0
    context_precision: float = 0.0
    latency_ms: float = 0.0


@dataclass
class EvaluationRun:
    """Results of a single evaluation run (API representation)"""

    id: int
    tenant_id: int
    timestamp: datetime
    query: str
    response: str
    retrieved_contexts: list[str]
    metrics: EvaluationMetrics
    metadata: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type


class EvaluationService:
    """
    Service for running and managing RAG evaluations.
    Uses ragchecker for precise linguistic and factual verification.
    """

    def __init__(self) -> None:
        self._initialized = False
        self.checker: Any = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_thread_id: int | None = None
        logger.info("Evaluation Service instance created")

    async def initialize(self) -> bool:
        """Initialize evaluation engines (ragchecker, LLM judges)"""
        if self._initialized:
            return True

        try:
            self._loop = asyncio.get_running_loop()
            self._loop_thread_id = threading.get_ident()
            from ragchecker import RAGChecker

            # Use model from global config
            model = config.eval_model

            self.checker = RAGChecker(
                extractor_name=f"google/{model}",
                checker_name=f"google/{model}",
                custom_llm_api_func=self._custom_llm_wrapper,
            )

            self._initialized = True
            logger.info("Evaluation Service (ragchecker) initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Evaluation Service: {e}")
            return False

    def _custom_llm_wrapper(self, prompts: list[str]) -> list[str]:
        """Synchronous wrapper for async LLMService to be used by ragchecker."""
        if not self._loop:
            raise RuntimeError("EvaluationService not initialized with an event loop")

        # Het model van de TENANT van deze evaluatie. Hier stond het platformmodel met een vast Google-model
        # (`gemini-1.5-flash`), ook voor een klant die Mistral of een eigen model koos.
        tenant_id = _EVALUATIE_TENANT.get()
        if tenant_id is None:
            raise RuntimeError("evaluatie zonder tenant: het taalmodel van een klant is niet te bepalen")
        # Dynamisch: `evaluation` (domain_pack) mag niet statisch terug naar `services` (agent_runtime); zie
        # `test_dsm014_agt_rt_no_laag_circulars`.
        tenant_deur = importlib.import_module("src.core.services.llm.tenant_deur")
        taalmodel = tenant_deur.TenantTaalmodel(tenant_id)

        async def batch_generate() -> list[str]:
            tasks = [taalmodel.generate_response(p) for p in prompts]
            responses = await asyncio.gather(*tasks)
            return [r.get("content", "") for r in responses]

        # Avoid deadlock when the synchronous wrapper is invoked from the same
        # thread that is already running the captured event loop.
        if self._loop_thread_id == threading.get_ident():
            result_holder: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
            error_holder: dict[str, BaseException] = {}

            def run_in_worker_thread() -> None:
                worker_loop = asyncio.new_event_loop()
                try:
                    asyncio.set_event_loop(worker_loop)
                    result_holder["result"] = worker_loop.run_until_complete(batch_generate())
                except BaseException as exc:
                    error_holder["error"] = exc
                finally:
                    worker_loop.close()
                    asyncio.set_event_loop(None)

            worker = threading.Thread(target=run_in_worker_thread, daemon=True)
            worker.start()
            worker.join()

            if "error" in error_holder:
                raise error_holder["error"]

            return cast(list[str], result_holder.get("result", []))

        future = asyncio.run_coroutine_threadsafe(batch_generate(), self._loop)
        return future.result()

    async def evaluate_rag_response(
        self,
        tenant_id: int,
        query: str,
        response: str,
        contexts: list[str],
        reference_answer: str = "",
        metadata: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        quality_config: QualityGateConfig | None = None,
    ) -> EvaluationRun:
        """Run a full evaluation pipeline on a RAG triplet and persist result."""
        if not self._initialized:
            await self.initialize()

        logger.info(f"Evaluating RAG response for tenant {tenant_id}")
        start_time = time.perf_counter()
        tid_str = str(tenant_id)

        try:
            # 1. Run ragchecker evaluation
            from ragchecker import RAGResult, RAGResults
            from ragchecker.container import RetrievedDoc

            retrieved_docs = [
                RetrievedDoc(doc_id=f"ctx_{i}", text=ctx) for i, ctx in enumerate(contexts)
            ]

            rag_result = RAGResult(
                query_id=str(int(time.time())),
                query=query,
                gt_answer=reference_answer or "No reference provided",
                response=response,
                retrieved_context=retrieved_docs,
            )

            results_container = RAGResults(results=[rag_result])

            # Blocking call in thread pool
            tenant_token = _EVALUATIE_TENANT.set(tenant_id)
            try:
                eval_results = await asyncio.to_thread(
                    self.checker.evaluate,
                    results_container,
                    metrics=["precision", "recall", "faithfulness"],
                )
            finally:
                _EVALUATIE_TENANT.reset(tenant_token)

            if hasattr(eval_results, "metrics"):
                m = eval_results.metrics.get("overall_metrics", {})
            elif isinstance(eval_results, dict):
                m = eval_results.get("overall_metrics", {})
            else:
                m = {}
            latency = (time.perf_counter() - start_time) * 1000

            # Record Prometheus Metrics
            RAG_FAITHFULNESS.labels(tenant_id=tid_str).observe(m.get("faithfulness", 0.0))
            RAG_RELEVANCE.labels(tenant_id=tid_str).observe(m.get("precision", 0.0))
            RAG_CONTEXT_PRECISION.labels(tenant_id=tid_str).observe(m.get("context_precision", 0.0))
            RAG_EVAL_LATENCY.labels(tenant_id=tid_str).observe(latency)

            # 2. Check Quality Gate
            gate_passed = True
            gate_details: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
            if quality_config:
                gate_passed, gate_details = self.check_quality_gate(m, quality_config)
                if not gate_passed:
                    for metric, detail in gate_details.items():
                        if not detail["passed"]:
                            RAG_QUALITY_GATE_FAILURES.labels(tenant_id=tid_str, metric=metric).inc()

            # 3. Persist to Database
            async with db_manager.get_session() as session:
                meta = metadata or {}
                meta.update({"gate_passed": gate_passed, "gate_details": gate_details})

                db_result = EvaluationResult(
                    tenant_id=tenant_id,
                    query=query,
                    response=response,
                    contexts=contexts,
                    reference_answer=reference_answer,
                    faithfulness=m.get("faithfulness", 0.0),
                    precision=m.get("precision", 0.0),
                    recall=m.get("recall", 0.0),
                    context_precision=m.get("context_precision", 0.0),
                    latency_ms=latency,
                    model_name=config.eval_model,
                    metadata_=meta,
                )
                session.add(db_result)
                await session.commit()
                await session.refresh(db_result)

                eval_run = self._map_to_run(db_result)

                # 4. Handle blocking
                if quality_config and quality_config.block_on_failure and not gate_passed:
                    logger.error(f"Blocking low quality response for tenant {tenant_id}")
                    raise LowQualityResponseError(details=gate_details)

                return eval_run

        except LowQualityResponseError:
            raise
        except Exception as e:
            logger.error(f"Evaluation pipeline failed: {e}")
            raise RuntimeError(f"Failed to evaluate RAG response: {str(e)}")

    def check_quality_gate(
        self, metrics: dict[str, float], config: QualityGateConfig
    ) -> tuple[bool, dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Evaluate if metrics meet the threshold requirements."""
        details: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        passed = True
        checks = [
            ("faithfulness", config.min_faithfulness),
            ("precision", config.min_precision),
            ("context_precision", config.min_context_precision),
        ]
        for metric_name, threshold in checks:
            val = metrics.get(metric_name, 0.0)
            status = val >= threshold
            details[metric_name] = {
                "value": val,
                "threshold": threshold,
                "passed": status,
            }
            if not status:
                passed = False
                logger.warning(f"Quality Gate FAILED for {metric_name}: {val:.2f} < {threshold}")
        if passed:
            logger.info("Quality Gate PASSED")
        return passed, details

    async def get_run_results(self, run_id: int) -> EvaluationRun | None:
        """Retrieve results of a specific evaluation run from database"""
        async with db_manager.get_session() as session:
            result = await session.get(EvaluationResult, run_id)
            if result:
                return self._map_to_run(result)
        return None

    async def get_tenant_stats(self, tenant_id: int) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Calculate aggregate stats for a tenant using database queries"""
        async with db_manager.get_session() as session:
            stmt = select(
                func.count(EvaluationResult.id).label("count"),
                func.avg(EvaluationResult.faithfulness).label("avg_faith"),
                func.avg(EvaluationResult.precision).label("avg_prec"),
                func.avg(EvaluationResult.recall).label("avg_rec"),
                func.avg(EvaluationResult.context_precision).label("avg_ctx_prec"),
                func.avg(EvaluationResult.latency_ms).label("avg_latency"),
            ).where(EvaluationResult.tenant_id == tenant_id)
            res = await session.execute(stmt)
            stats = res.mappings().one()
            if stats["count"] == 0:
                return {"status": "no_data", "tenant_id": tenant_id}
            return {
                "tenant_id": tenant_id,
                "total_runs": stats["count"],
                "avg_faithfulness": float(stats["avg_faith"] or 0),
                "avg_precision": float(stats["avg_prec"] or 0),
                "avg_recall": float(stats["avg_rec"] or 0),
                "avg_context_precision": float(stats["avg_ctx_prec"] or 0),
                "avg_latency_ms": float(stats.get("avg_latency") or 0),
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }

    def _map_to_run(self, db_result: EvaluationResult) -> EvaluationRun:
        """Helper to map DB model to API dataclass"""
        return EvaluationRun(
            id=db_result.id,
            tenant_id=db_result.tenant_id,
            timestamp=db_result.created_at or datetime.now(timezone.utc),
            query=db_result.query,
            response=db_result.response,
            retrieved_contexts=db_result.contexts or [],
            metrics=EvaluationMetrics(
                faithfulness=db_result.faithfulness or 0.0,
                precision=db_result.precision or 0.0,
                recall=db_result.recall or 0.0,
                context_precision=db_result.context_precision or 0.0,
                latency_ms=db_result.latency_ms or 0.0,
            ),
            metadata=db_result.metadata_ or {},
        )


# Global singleton instance
evaluation_service = EvaluationService()
