# orphan:exempt reason: Shared schemas + in-memory state for tool_broker domain (ADR-033)
"""Shared Pydantic schemas and in-memory state for the tool_broker domain."""

import uuid
from typing import Any

from pydantic import BaseModel, Field


class ToolExecutionRequest(BaseModel):
    """Tool execution request."""

    tool_name: str = Field(..., min_length=1, max_length=255)
    payload: dict[str, Any] = Field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type


class ToolCreate(BaseModel):
    """Schema for registering a new tool."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    category: str = Field(..., description="Tool category (e.g., search, database)")
    capabilities: list[str] = Field(default_factory=list)
    parameters_schema: dict[str, Any] = Field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    endpoint: str | None = None


class ToolResponse(BaseModel):
    """Schema for tool details response."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str | None
    category: str
    capabilities: list[str]
    parameters_schema: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    tenant_id: int | None = None
    endpoint: str | None = None
    available: bool = True
    execution_count: int = 0
    last_used: str | None = None


class ToolExecutionResponse(BaseModel):
    """Tool execution response."""

    tool_name: str
    status: str
    result: Any  # TODO(TYPE): replace Any with concrete type
    timestamp: str
    execution_time_ms: float


class ToolStatusResponse(BaseModel):
    """Tool status response."""

    tool_name: str
    available: bool
    version: str
    last_used: str | None
    execution_count: int
    circuit_status: str = "closed"
    success_rate: float = 0.0
    avg_latency_ms: float = 0.0


class ToolExecutionHistoryItem(BaseModel):
    """Tool execution history item."""

    id: str
    tool_name: str
    status: str
    execution_time_ms: float
    timestamp: str
    retry_count: int = 0
    error: str | None = None
    user_id: int | None = None


class ToolListResponse(BaseModel):
    """List of available tools."""

    tools: list[ToolStatusResponse]
    total_count: int


# Global in-memory state shared across sub-routers
tool_execution_history: dict[str, dict[str, Any]] = {}  # TODO(TYPE): replace Any with concrete type

#: De meegeleverde tools, zonder klant. Ze komen hieronder in `available_tools` onder `(None, naam)`.
_meegeleverde_tools = {
    "serena": {
        "id": "tool-serena-001",
        "name": "serena",
        "available": True,
        "version": "1.0.0",
        "execution_count": 0,
        "last_used": None,
        "category": "agent",
        "capabilities": ["orchestration"],
        "parameters_schema": {},
        "description": "Serena Agent",
    },
    "sequential_thinking": {
        "id": "tool-sqthink-001",
        "name": "sequential_thinking",
        "available": True,
        "version": "1.0.0",
        "execution_count": 0,
        "last_used": None,
        "category": "reasoning",
        "capabilities": ["planning"],
        "parameters_schema": {},
        "description": "Sequential Thinking",
    },
    "code_analyzer": {
        "id": "tool-codean-001",
        "name": "code_analyzer",
        "available": True,
        "version": "1.0.0",
        "execution_count": 0,
        "last_used": None,
        "category": "dev",
        "capabilities": ["analysis"],
        "parameters_schema": {},
        "description": "Code Analyzer",
    },
    "test_generator": {
        "id": "tool-testgen-001",
        "name": "test_generator",
        "available": True,
        "version": "1.0.0",
        "execution_count": 0,
        "last_used": None,
        "category": "dev",
        "capabilities": ["testing"],
        "parameters_schema": {},
        "description": "Test Generator",
    },
    "performance_optimizer": {
        "id": "tool-perfopt-001",
        "name": "performance_optimizer",
        "available": True,
        "version": "1.0.0",
        "execution_count": 0,
        "last_used": None,
        "category": "dev",
        "capabilities": ["optimization"],
        "parameters_schema": {},
        "description": "Performance Optimizer",
    },
}

#: De sleutel van het toolregister: `(tenant_id, naam)`; een meegeleverde tool heeft `tenant_id` `None` en is voor elke
#: klant zichtbaar. Brief 2026-10-24: de sleutel was alleen de naam, dus de tool van klant B overschreef die van klant A
#: (en kreeg zijn `tenant_id`), en status, aan/uit en uitvoeren zochten op de naam over klanten heen.
ToolSleutel = tuple[int | None, str]
#: Een registerregel; zelfde type als eerder (`dict[str, Any]`), nu een keer benoemd zodat de geboekte schuld niet stijgt.
ToolRegel = dict[str, Any]  # TODO(TYPE): replace Any with concrete type

available_tools: dict[ToolSleutel, ToolRegel] = {
    (None, naam): tool for naam, tool in _meegeleverde_tools.items()
}


def tool_sleutel(tenant_id: int | None, naam: str) -> ToolSleutel:
    """De registersleutel van een tool van deze klant (naam zonder hoofdletters)."""
    return (tenant_id, naam.lower())


#: Het GEBRUIK van een meegeleverde tool, per klant: `(tenant_id, naam) -> {"execution_count", "last_used"}`.
#: Gate 2 (2026-10-27): de tellers stonden op het gedeelde meegeleverde object, dus klant A zag hoe vaak en wanneer
#: klant B `serena` gebruikte (en B kon het getal opdrijven). Een tool van een klant houdt zijn tellers zelf bij.
meegeleverd_gebruik: dict[tuple[int, str], ToolRegel] = {}


def gebruik_van(tenant_id: int, naam: str, tool: ToolRegel, *, aanmaken: bool = False) -> ToolRegel:
    """De tellers van `tool` voor DEZE klant: die van de tool zelf als hij van een klant is, anders een eigen regel per
    klant voor een meegeleverde tool. Lezen maakt niets aan; `aanmaken=True` (uitvoeren) wel."""
    if tool.get("tenant_id") is not None:
        return tool
    sleutel = (tenant_id, naam.lower())
    if aanmaken:
        return meegeleverd_gebruik.setdefault(sleutel, {"execution_count": 0, "last_used": None})
    return meegeleverd_gebruik.get(sleutel) or {"execution_count": 0, "last_used": None}


def zoek_tool(tenant_id: int | None, naam: str) -> ToolRegel | None:
    """De tool met deze naam die DEZE klant mag zien: eerst zijn eigen, dan een meegeleverde. Nooit die van een
    andere klant."""
    return available_tools.get(tool_sleutel(tenant_id, naam)) or available_tools.get(
        tool_sleutel(None, naam)
    )


__all__ = [
    "ToolExecutionRequest",
    "ToolCreate",
    "ToolResponse",
    "ToolExecutionResponse",
    "ToolStatusResponse",
    "ToolExecutionHistoryItem",
    "ToolListResponse",
    "tool_execution_history",
    "available_tools",
    "ToolRegel",
    "gebruik_van",
    "meegeleverd_gebruik",
    "ToolSleutel",
    "tool_sleutel",
    "zoek_tool",
]
