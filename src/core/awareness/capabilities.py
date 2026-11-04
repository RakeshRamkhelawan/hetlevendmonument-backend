"""
Capabilities Awareness Service
Aggegator for system capabilities (native agents and ActivePieces integrations)
to provide context for the CVA/LLM.
"""

import logging
from typing import Any

from src.core.activepieces.schemas import PieceRead
from src.core.agents.agent_registry import AgentRegistry
from src.core.awareness.features import SystemFeatureRegistry

logger = logging.getLogger(__name__)


class CapabilitiesRegistry:
    """
    Registry that aggregates capabilities from all sources.
    """

    @staticmethod
    def _format_activepieces_summary(pieces: list[PieceRead]) -> list[str]:
        """Helper to format ActivePieces summary"""
        summary_lines: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        if not pieces:
            return summary_lines

        summary_lines.append("### Integration Agents (ActivePieces):")
        pieces_by_cat: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for piece in pieces:
            cat = piece.categories[0] if piece.categories else "Other"
            if cat not in pieces_by_cat:
                pieces_by_cat[cat] = []
            pieces_by_cat[cat].append(piece)

        for cat, cat_pieces in pieces_by_cat.items():
            summary_lines.append(f"**{cat}**:")
            piece_summaries = [p.display_name for p in cat_pieces]
            summary_lines.append(
                ", ".join(piece_summaries[:10])
                + (f" (+{len(piece_summaries) - 10} more)" if len(piece_summaries) > 10 else "")
            )

        return summary_lines

    @staticmethod
    async def get_all_capabilities_summary() -> str:
        """
        Get a markdown formatted summary of all available agents and their capabilities.
        """
        summary_lines: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # 0. System Features (Self-Awareness)
        try:
            summary_lines.append(SystemFeatureRegistry.get_all_features_summary())
            summary_lines.append("")
        except Exception as e:
            logger.error(f"Failed to fetch system features: {e}")

        # 1. Native Agents
        try:
            native_agents = await AgentRegistry.list_agents()  # type: ignore[attr-defined]
            if native_agents:
                summary_lines.append("### Native Agents:")
                for agent in native_agents:
                    desc = agent.description or "No description"
                    summary_lines.append(f"- **{agent.name}** ({agent.agent_id}): {desc}")
        except Exception as e:
            logger.error(f"Failed to fetch native agents for capabilities summary: {e}")
            summary_lines.append("- (Native agents unavailable due to error)")

        summary_lines.append("")

        # 2. ActivePieces Integrations
        try:
            from src.core.activepieces.service import ActivePiecesService

            ap_service = ActivePiecesService()
            pieces = await ap_service.get_all_pieces()
            summary_lines.extend(CapabilitiesRegistry._format_activepieces_summary(pieces))

        except Exception as e:
            logger.error(f"Failed to fetch ActivePieces for capabilities summary: {e}")
            summary_lines.append("- (ActivePieces integrations unavailable)")

        return "\n".join(summary_lines)


# Global helper
async def get_capabilities_context() -> str:
    return await CapabilitiesRegistry.get_all_capabilities_summary()
