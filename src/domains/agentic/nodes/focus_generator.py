import json
import logging
from typing import Any, cast

from src.core.services.llm.tenant_deur import TenantTaalmodel
from src.domains.agentic.graph.state import AgentState

logger = logging.getLogger(__name__)

# Het taalmodel is de keuze van de TENANT (ADR-041 B14): `TenantTaalmodel(tenant_id)`. Hier stond een
# module-level `ChatOpenAI` naar api.deepseek.com, gebouwd bij het importeren en dus voor elke klant gelijk,
# met de gebruikersvraag als inhoud. Per verzoek een tenant, geen module-level client.

SYSTEM_PROMPT = """You are a React Flow graph generator.
Your task is to convert the user's request into a JSON object representing a React Flow graph.
The output MUST be a valid JSON object with the following structure:
{
    "focus_flow": {
        "graph": {
            "nodes": [
                { "id": "1", "type": "trigger", "data": { "label": "..." }, "position": { "x": 0, "y": 0 } },
                ...
            ],
            "edges": [
                { "id": "e1-2", "source": "1", "target": "2" },
                ...
            ]
        }
    }
}
Generate ONLY JSON. No markdown formatting.
Available node types: 'trigger', 'action', 'condition', 'loop'.
"""


async def focus_generator_node(
    state: AgentState,
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Node that generates a React Flow graph with the language model of the request's tenant.

    De tenant komt uit de state (`state["tenant_id"]`, gezet door de websocket uit de JWT). Ontbreekt hij,
    dan is dat een fout en GEEN reden voor een platformmodel: de vraag van de gebruiker is klantgegevens.
    """
    user_input = state.get("input", "")
    tenant_id = state.get("tenant_id")

    if tenant_id is None:
        logger.error("focus_generator_node zonder tenant in de state: niet uitgevoerd")
        return {
            "focus_flow": {
                "graph": {"nodes": [], "edges": []},
                "error": "Geen tenant bij dit verzoek; het taalmodel kan niet worden gekozen.",
            }
        }

    try:
        content = await TenantTaalmodel(tenant_id).tekst(
            user_input, systeem=SYSTEM_PROMPT, temperature=0.3
        )

        # Clean markdown code blocks if present (models sometimes add them despite instructions)
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        return cast(dict[str, object], json.loads(content.strip()))

    except Exception as e:
        logger.error("LLM Generation Error (tenant %s): %s", tenant_id, type(e).__name__, exc_info=True)
        # Een veilige foutstatus in plaats van een crash of een ander model
        return {"focus_flow": {"graph": {"nodes": [], "edges": []}, "error": str(e)}}
