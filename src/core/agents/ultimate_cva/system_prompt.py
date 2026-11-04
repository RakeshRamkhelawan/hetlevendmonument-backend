"""
Ultimate CVA - Master System Prompt
Tenant-agnostic Platform Guardian Copilot
"""

from datetime import datetime, timezone
from typing import Any, Optional

"""
Ultimate CVA - Master System Prompt
Tenant-agnostic Platform Guardian Copilot
"""


# =============================================================================
# STANDARD PROMPT (Gemini, GPT-4, Llama)
# Structure: Context -> Tools -> Strict JSON ReAct Loop
# =============================================================================
STANDARD_PROMPT_TEMPLATE = """
You are the Platform Guardian Copilot for a multi-tenant SaaS platform.

Your name is "CVA" (Conversational Virtual Assistant).
Your role: Proactive, trustworthy, pragmatically "CEO-like".

## Platform Context
- Platform: {platform_name}
- Tenant ID: {tenant_id}
- Domain: {tenant_domain}
- Time: {current_time_iso}

## User Context (CRITICAL)
- Language: {user_language}
- Route: {current_route}
- Page Context: {page_context}

## Tools
You can use these tools. Only use them if necessary.
{tools_description_block}

## Instructions
1. Analyze the user request.
2. Check if you can answer directly or need a tool.
3. Answer the user's specific question DIRECTLY. Do not start with a generic introduction unless explicitly asked who you are.
4. OUTPUT ONLY A SINGLE JSON OBJECT.

## JSON Strict Structure
{{
  "thought_process": "Your internal reasoning steps.",
  "plan": ["Step 1", "Step 2..."],
  "action": "tool_name_or_null",
  "action_params": {{ "param": "value" }},
  "message": "Final answer to user in {user_language}. Markdown allowed.",
  "confidence": 0.9
}}
"""

# =============================================================================
# REASONER PROMPT (DeepSeek R1, o1)
# Structure: Goal -> Tools -> JSON Output
# optimized for models that already do "Chain of Thought" internally.
# We remove the redundant "thought_process" field requirement.
# =============================================================================
REASONER_PROMPT_TEMPLATE = """
You are the CVA Copilot.

GOAL: Solve the user's request efficiently using available tools.

## Context
- Tenant: {tenant_id} ({tenant_domain})
- Route: {current_route}
- Time: {current_time_iso}

## Tools
{tools_description_block}

## Output Requirement
You must output your final answer as a VALID JSON object.
Do not output markdown code blocks. Just the raw JSON.
The first non-whitespace character of your response MUST be `{{`.

JSON Structure:
{{
  "action": "tool_name_or_null",
  "action_params": {{ ... }},
  "message": "The response to the user ({user_language}).",
  "plan": ["Brief list of steps taken/to-take"]
}}
"""


def build_tools_description_block(tool_definitions: list[dict[str, Any]]) -> str:  # TODO(TYPE): replace Any with concrete type
    lines: list[str] = []
    for tool in tool_definitions:
        name = tool.get("name")
        desc = tool.get("description", "")
        lines.append(f"- {name}: {desc}")
    return "\n".join(lines)


def get_system_prompt(
    *,
    platform_name: str,
    tenant_id: str,
    tenant_domain: str = "generic SME",
    user_language: str = "en",
    current_route: str = "/",
    page_context: str = "",
    tool_definitions: list[dict[str, Any]] | None = None,  # TODO(TYPE): replace Any with concrete type
    cva_mode: str = "REACTIVE",
    model_id: str = "unknown",  # New param
) -> str:
    """
    Build the adaptive system prompt.
    """
    tool_definitions = tool_definitions or []
    tools_block = build_tools_description_block(tool_definitions)
    current_time = datetime.now(timezone.utc).isoformat()

    # Select Template
    is_reasoner = (
        "reasoner" in model_id.lower() or "o1" in model_id.lower() or "deepseek" in model_id.lower()
    )

    template = REASONER_PROMPT_TEMPLATE if is_reasoner else STANDARD_PROMPT_TEMPLATE

    return template.format(
        platform_name=platform_name,
        tenant_id=tenant_id,
        tenant_domain=tenant_domain,
        user_language=user_language,
        current_route=current_route,
        page_context=page_context or "None",
        current_time_iso=current_time,
        tools_description_block=tools_block,
        cva_mode=cva_mode,
        # Standard prompt extras
        mode_instructions="Active Mode: " + cva_mode,
        platform_tools_short_summary="",
    )



class SystemPromptBuilder:
    """Thin wrapper around the module-level get_system_prompt function."""

    def build(self, **kwargs: Any) -> str:
        return get_system_prompt(**kwargs)
