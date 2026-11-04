"""ActivePieces integration package.

Keep package initialization defensive: several call sites only need the client
or service and should not fail because optional repository modules are absent.
"""

from src.core.activepieces.client import ActivePiecesClient
from src.core.activepieces.service import ActivePiecesService
from src.core.activepieces.validator import (
    ConnectionValidator,
    FlowValidator,
    PieceValidator,
    validate_connection,
    validate_flow,
    validate_react_flow,
)

__all__ = [
    "ActivePiecesClient",
    "ActivePiecesService",
    "FlowValidator",
    "ConnectionValidator",
    "PieceValidator",
    "validate_flow",
    "validate_react_flow",
    "validate_connection",
]

try:
    from src.core.activepieces.repositories import (
        ActivePiecesConnectionRepository,
        ActivePiecesFlowRepository,
        ActivePiecesFlowRunRepository,
        ActivePiecesSyncLogRepository,
    )

    __all__.extend(
        [
            "ActivePiecesFlowRepository",
            "ActivePiecesConnectionRepository",
            "ActivePiecesFlowRunRepository",
            "ActivePiecesSyncLogRepository",
        ]
    )
except ModuleNotFoundError:
    pass
