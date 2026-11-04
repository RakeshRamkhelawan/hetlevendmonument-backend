"""
Corrective RAG (CRAG) Agent Wrapper
Encapsulates the LangGraph CRAG workflow into a standard Agent interface.
"""

import logging
from typing import TYPE_CHECKING, Any, Generic, TypeVar, TypedDict, cast
from collections.abc import Callable

if TYPE_CHECKING:
    from src.core.agents.crag_graph import GraphState

logger = logging.getLogger(__name__)


class CRAGInput(TypedDict):
    """Input contract for the Corrective RAG agent."""

    query: str
    tenant_id: int


class CRAGResult(TypedDict):
    """Output contract for the Corrective RAG agent."""

    answer: str
    sources: list[dict[str, object]]
    web_search_triggered: bool
    original_query: str


T = TypeVar("T")


class _LazyProxy(Generic[T]):
    """Proxy that instantiates the real object on first attribute access."""

    def __init__(self, factory: Callable[[], T]) -> None:
        self._factory = factory
        self._instance: T | None = None

    def _get_instance(self) -> T:
        if self._instance is None:
            self._instance = self._factory()
        return self._instance

    def __getattr__(self, name: str) -> Any:
        return getattr(self._get_instance(), name)

    def __call__(self, *args: object, **kwargs: object) -> Any:
        return self._get_instance()(*args, **kwargs)  # type: ignore[operator]

    def __repr__(self) -> str:
        if self._instance is None:
            return f"_LazyProxy({self._factory.__qualname__}, not initialized)"
        return repr(self._instance)

    @property
    def __class__(self) -> type:
        return cast(type, self._get_instance().__class__)

    @__class__.setter
    def __class__(self, value: type) -> None:
        pass


class CorrectiveRAGAgent:
    """
    Agent that executes the Corrective RAG workflow.
    It combines retrieval, grading, optional web search, and generation.
    """

    def __init__(self) -> None:
        """Initialize the CRAG agent and compile the graph."""
        from src.core.agents.crag_graph import create_crag_graph

        self.graph = create_crag_graph()
        self._initialized = True
        logger.info("CorrectiveRAGAgent initialized and graph compiled.")

    async def ainvoke(
        self,
        input_data: CRAGInput,
    ) -> CRAGResult:
        """
        Execute the CRAG workflow asynchronously.

        Args:
            input_data: dict containing 'query' (str) and 'tenant_id' (int).

        Returns: dict containing 'generation', 'documents', and other metadata.
        """
        if not self._initialized:
            raise RuntimeError("CorrectiveRAGAgent not initialized")

        query = input_data.get("query")
        tenant_id = input_data.get("tenant_id")

        if not query or tenant_id is None:
            raise ValueError("Input data must contain 'query' and 'tenant_id'")

        # Types are guaranteed by CRAGInput contract
        query_str: str = query
        tenant_id_int: int = tenant_id

        logger.info(f"CRAG Agent processing query: '{query_str}' for tenant {tenant_id_int}")

        # Initialize graph state with proper GraphState type
        initial_state: "GraphState" = {
            "query": query_str,
            "tenant_id": tenant_id_int,
            "documents": [],
            "web_search_needed": False,
            "generation": "",
            "metadata": {},
        }

        # Execute graph
        try:
            final_state = await self.graph.ainvoke(initial_state)

            return CRAGResult(
                answer=final_state.get("generation", ""),
                sources=final_state.get("documents", []),
                web_search_triggered=final_state.get("web_search_needed", False),
                original_query=final_state.get("query", query),
            )
        except Exception as e:
            logger.error(f"CRAG Agent execution failed: {e}")
            raise RuntimeError(f"CRAG workflow failed: {str(e)}")


def get_corrective_rag_agent() -> CorrectiveRAGAgent:
    """Factory function for CorrectiveRAGAgent."""
    return CorrectiveRAGAgent()
