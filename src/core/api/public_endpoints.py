# orphan:exempt reason: legacy shim -- PublicEndpointRegistry verplaatst naar src/core/shared/public_registry.py
# Re-export voor backward-compat met bestaande imports (SP-API-009 Dag 2)
from src.core.shared.public_registry import PublicEndpointRegistry  # noqa: F401
