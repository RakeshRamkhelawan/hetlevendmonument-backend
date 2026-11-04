import logging
from typing import Any, Dict, List

from sqlalchemy import text

from src.core.database.database import db_manager

logger = logging.getLogger(__name__)


class TraceOrchestrator:
    """
    Constructs a Directed Acyclic Graph (DAG) of agent interactions
    from the signal audit logs. Compatible with React-Flow.
    """

    async def get_execution_trace(self, correlation_id: str, tenant_id: int) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Builds nodes and edges for a specific execution trace.
        """
        async with db_manager.get_session() as db:
            stmt = text(
                """
                SELECT source_agent, target_agents, tier, signal_id, timestamp
                FROM signal_audit_log
                WHERE correlation_id = :correlation_id AND tenant_id = :tenant_id
                ORDER BY timestamp ASC
            """
            )
            result = await db.execute(
                stmt, {"correlation_id": correlation_id, "tenant_id": tenant_id}
            )
            rows = result.all()

        nodes: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        edges: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        seen_agents = set()

        for source, targets, tier, sig_id, ts in rows:
            # 1. Create source node
            if source not in seen_agents:
                nodes.append(
                    {
                        "id": source,
                        "data": {"label": source.replace("_", " ").title()},
                        "position": {"x": 0, "y": 0},  # Frontend will auto-layout
                    }
                )
                seen_agents.add(source)

            # 2. Create edges and target nodes
            # target_agents is a JSONB list
            if targets:
                for target in targets:
                    if target not in seen_agents:
                        nodes.append(
                            {
                                "id": target,
                                "data": {"label": target.replace("_", " ").title()},
                                "position": {"x": 0, "y": 0},
                            }
                        )
                        seen_agents.add(target)

                    edges.append(
                        {
                            "id": f"e-{sig_id}-{target}",
                            "source": source,
                            "target": target,
                            "label": tier,
                            "animated": True,
                        }
                    )

        return {"nodes": nodes, "edges": edges}
