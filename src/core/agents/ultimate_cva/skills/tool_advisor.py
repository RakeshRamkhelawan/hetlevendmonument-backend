from typing import Any

from src.core.memory.memory_manager import resolve_memory_manager


class ToolAdvisor:
    """
    Agent Skill: Recommends tools based on user goals.
    """

    async def suggest_tools(self, goal: str, limit: int = 3) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """
        Performs semantic search to find the best tools for a goal.
        """
        # Query the 'strategy' memory where we indexed our tools
        memories = await resolve_memory_manager().query_memories(
            agent_id="SYSTEM", memory_types=["strategy"], top_k=limit
        )

        suggestions: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for mem in memories:
            content = mem["content"]
            # Only pick tools, not other strategic memories
            if content.get("type") == "activepieces_tool":
                suggestions.append(
                    {
                        "name": content["display_name"],
                        "description": content["description"],
                        "score": mem["importance_score"],  # Simplified for demo
                    }
                )

        return suggestions


# Singleton
tool_advisor = ToolAdvisor()
