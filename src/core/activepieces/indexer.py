import asyncio
import logging
from typing import Any

from src.core.activepieces.catalog_syncer import catalog_syncer
from src.core.memory.memory_manager import resolve_memory_manager
from src.core.types import AgentType

logger = logging.getLogger("tool_indexer")


class ToolIndexer:
    """
    Indexes the tool catalog into Vector Space for semantic searching.
    Allows the AI to find tools based on intention.
    """

    async def index_catalog(self) -> None:
        """
        Reads the catalog and stores each tool as a 'Strategic Memory'.
        """
        catalog = catalog_syncer.load_catalog()
        if not catalog:
            logger.warning("Catalog is empty. Syncing first...")
            catalog = await catalog_syncer.sync_all()

        logger.info(f"Indexing {len(catalog)} tools for semantic search...")

        for tool in catalog:
            # Create a rich description for embedding
            content = f"Tool: {tool['displayName']}. Description: {tool['description']} Category: {tool['category']}."

            # Store in Vector DB as a specialized memory type
            # We use 'strategy' type because tools are strategic assets
            await resolve_memory_manager().store_memory(
                agent_id="SYSTEM",
                memory_type="strategy",
                content={
                    "tool_name": tool["name"],
                    "display_name": tool["displayName"],
                    "description": tool["description"],
                    "type": "activepieces_tool",
                },
                importance_score=1.0,  # Tools are very important
            )

        logger.info("Semantic indexing of tools complete.")


# Singleton
tool_indexer = ToolIndexer()
