"""
Phase 3 Procedures Module
Implements domain packs, procedure metadata, executions, and observability
"""

import sys

_module = sys.modules[__name__]
if __name__ == "core.procedures":
    sys.modules.setdefault("src.core.procedures", _module)
elif __name__ == "src.core.procedures":
    sys.modules.setdefault("core.procedures", _module)

from typing import Any

from .ai_quality_repository import AIQualityEventRepository
from .domain_pack_repository import DomainPackRepository
from .models import AIQualityEvent, DomainPack, ProcedureExecution, ProcedureMetadata
from .procedure_execution_repository import ProcedureExecutionRepository
from .procedures_repository import ProcedureMetadataRepository
from .schemas import (
    AIQualityEventCreate,
    AIQualityEventRead,
    DomainPackCreate,
    DomainPackRead,
    DomainPackUpdate,
    ProcedureExecutionCreate,
    ProcedureExecutionRead,
    ProcedureExecutionStatusUpdate,
    ProcedureMetadataCreate,
    ProcedureMetadataRead,
    ProcedureMetadataUpdate,
    ProcedureRead,
)

__all__ = [
    # Models
    "DomainPack",
    "ProcedureMetadata",
    "ProcedureExecution",
    "AIQualityEvent",
    # Schemas
    "DomainPackCreate",
    "DomainPackRead",
    "DomainPackUpdate",
    "ProcedureMetadataCreate",
    "ProcedureMetadataUpdate",
    "ProcedureMetadataRead",
    "ProcedureRead",
    "ProcedureExecutionCreate",
    "ProcedureExecutionRead",
    "ProcedureExecutionStatusUpdate",
    "AIQualityEventCreate",
    "AIQualityEventRead",
    # Repositories
    "DomainPackRepository",
    "ProcedureMetadataRepository",
    "ProcedureExecutionRepository",
    "AIQualityEventRepository",
]
