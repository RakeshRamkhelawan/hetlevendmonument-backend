# dsm:exempt reason: legacy flat-file CVA entry point -- Strangler Fig migratie gepland SP-DSM-003
from src.core.api.v1.cva.chat_router import chat_endpoint, chat_router as router  # noqa: F401
from src.core.api.v1.cva.legacy_router import legacy_router  # noqa: F401

# Compatibility re-export for legacy test patches
try:
    from src.core.copilot.council.factory import build_council  # noqa: F401
except Exception:
    build_council = None  # type: ignore[assignment]
