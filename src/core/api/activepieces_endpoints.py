# orphan:exempt reason: legacy flat file, replaced by src/core/api/v1/activepieces/ (SP-API-005 Dag 3)
"""Legacy re-export shim -- do not add routes here."""

from src.core.api.v1.activepieces.router import router  # noqa: F401
