import operator
from typing import Annotated, Any, NotRequired, Optional, TypedDict

from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    """The graph state for the agentic workflow."""

    input: str
    #: De tenant van het verzoek (uit de JWT). De focus-generator kiest daarmee het taalmodel van de klant.
    tenant_id: NotRequired[int]
    chat_history: list[BaseMessage]
    intermediate_steps: Annotated[list[tuple[Any, ...]], operator.add]  # TODO(TYPE): replace Any with concrete type
    focus_flow: dict[str, Any] | None  # Resulting React Flow JSON  # TODO(TYPE): replace Any with concrete type
