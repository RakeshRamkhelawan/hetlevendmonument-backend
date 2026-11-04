"""
SC-4.1: API Versioning Setup
Provides versioned API routing for backward compatibility.
"""

import logging
from enum import Enum
from typing import Any, Optional, Union, cast
from collections.abc import Sequence

from fastapi import APIRouter, FastAPI

logger = logging.getLogger(__name__)

# Type alias for APIRouter tags (matches FastAPI's expected type)
TagsType = Optional[list[str | Enum]]


class APIVersionManager:
    """
    SC-4.1: Manages API versioning for the application.

    Supports:
    - URL path versioning (/api/v1/, /api/v2/)
    - Header versioning (X-API-Version)
    - Deprecation notices
    """

    def __init__(self, app: FastAPI, default_version: str = "v1") -> None:
        self.app = app
        self.default_version = default_version
        self.versions: dict[str, APIRouter] = {}
        self.deprecated_versions: list[str] = []

    def create_version(
        self,
        version: str,
        prefix: str | None = None,
        deprecated: bool = False,
        sunset_date: str | None = None,
    ) -> APIRouter:
        """
        Create a new API version router.

        Args:
            version: Version string (e.g., "v1", "v2")
            prefix: Custom prefix (default: /api/{version})
            deprecated: Mark this version as deprecated
            sunset_date: Date when this version will be removed

        Returns:
            APIRouter for this version
        """
        if version in self.versions:
            return self.versions[version]

        prefix = prefix or f"/api/{version}"

        tags: list[str] = [f"API {version.upper()}"]
        if deprecated:
            tags.append("Deprecated")
            self.deprecated_versions.append(version)

        router = APIRouter(
            prefix=prefix,
            tags=cast(TagsType, tags),
            responses={
                404: {"description": "Not found"},
                500: {"description": "Internal server error"},
            },
        )

        # Note: Deprecation headers are added at the app level, not router level
        # Store deprecation info for middleware to use
        if deprecated:
            router._is_deprecated = True  # type: ignore[attr-defined]
            router._sunset_date = sunset_date  # type: ignore[attr-defined]

        self.versions[version] = router
        logger.info(f"Created API version: {version} (deprecated: {deprecated})")

        return router

    def include_all_versions(self) -> None:
        """Include all version routers in the app."""
        for version, router in self.versions.items():
            self.app.include_router(router)
            logger.info(f"Included API {version}")

    def get_version_info(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get information about available API versions."""
        return {
            "default_version": self.default_version,
            "available_versions": list(self.versions.keys()),
            "deprecated_versions": self.deprecated_versions,
            "current_version": self.default_version,
        }


# Convenience function for creating versioned routers
def create_versioned_router(
    version: str = "v1", prefix: str = "", tags: Sequence[str] | None = None
) -> APIRouter:
    """
    Create a router for a specific API version.

    Usage:
        router = create_versioned_router("v1", prefix="/users", tags=["Users"])

        @router.get("/")
        async def list_users():
            ...
    """
    full_prefix = f"/api/{version}{prefix}"
    router_tags: list[str] = list(tags) if tags is not None else [f"{version.upper()} API"]
    return APIRouter(prefix=full_prefix, tags=cast(TagsType, router_tags))


# Pre-configured routers for common versions
v1_router = create_versioned_router("v1")
v2_router = create_versioned_router("v2")
