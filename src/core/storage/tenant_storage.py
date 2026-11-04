"""Tenant-scoped storage adapters with backward-compatible test helpers."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any


class PathTraversalError(ValueError):
    """Raised when a tenant storage path is unsafe."""


@dataclass(slots=True)
class StorageObject:
    """Metadata describing a stored object."""

    path: str
    tenant_id: int
    size: int
    created_at: datetime
    modified_at: datetime
    content_type: str = "application/octet-stream"


class LocalTenantStorage:
    """File-based tenant-scoped storage with a compatibility CRUD API."""

    def __init__(self, base_path: str = "./storage/tenant_data") -> None:
        self._base = Path(base_path)
        self._base.mkdir(parents=True, exist_ok=True)

    def _tenant_dir(self, tenant_id: int | str) -> Path:
        path = self._base / str(tenant_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _validate_path(self, path: str) -> str:
        if not path or "\x00" in path:
            raise PathTraversalError("Path must be non-empty and must not contain null bytes")

        if re.match(r"^[A-Za-z]:[\\/]", path):
            raise PathTraversalError("Absolute paths are not allowed")

        normalized = PurePosixPath(path)
        if normalized.is_absolute() or normalized.drive:
            raise PathTraversalError("Absolute paths are not allowed")

        parts = normalized.parts
        if not parts or any(part in {"", ".", ".."} for part in parts):
            raise PathTraversalError("Path traversal is not allowed")

        return normalized.as_posix()

    def _resolve_tenant_path(self, tenant_id: int | str, path: str) -> Path:
        safe_path = self._validate_path(path)
        full_path = self._tenant_dir(tenant_id) / Path(safe_path)
        full_path.parent.mkdir(parents=True, exist_ok=True)
        return full_path

    def _build_storage_object(
        self,
        tenant_id: int,
        path: str,
        file_path: Path,
        content_type: str,
    ) -> StorageObject:
        stats = file_path.stat()
        created_at = datetime.fromtimestamp(stats.st_ctime, tz=timezone.utc)
        modified_at = datetime.fromtimestamp(stats.st_mtime, tz=timezone.utc)
        return StorageObject(
            path=path,
            tenant_id=tenant_id,
            size=stats.st_size,
            created_at=created_at,
            modified_at=modified_at,
            content_type=content_type,
        )

    async def store(
        self,
        tenant_id: int,
        path: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> StorageObject:
        safe_path = self._validate_path(path)
        file_path = self._resolve_tenant_path(tenant_id, safe_path)
        file_path.write_bytes(data)
        return self._build_storage_object(tenant_id, safe_path, file_path, content_type)

    async def retrieve(self, tenant_id: int, path: str) -> bytes:
        safe_path = self._validate_path(path)
        file_path = self._tenant_dir(tenant_id) / Path(safe_path)
        if not file_path.exists() or not file_path.is_file():
            raise FileNotFoundError(str(file_path))
        return file_path.read_bytes()

    async def list(self, tenant_id: int) -> list[StorageObject]:
        tenant_dir = self._tenant_dir(tenant_id)
        objects: list[StorageObject] = []
        for file_path in tenant_dir.rglob("*"):
            if file_path.is_file():
                relative_path = file_path.relative_to(tenant_dir).as_posix()
                objects.append(
                    self._build_storage_object(
                        tenant_id,
                        relative_path,
                        file_path,
                        "application/octet-stream",
                    )
                )
        return sorted(objects, key=lambda item: item.path)

    async def delete(self, tenant_id: int, path: str) -> None:
        safe_path = self._validate_path(path)
        file_path = self._tenant_dir(tenant_id) / Path(safe_path)
        if not file_path.exists() or not file_path.is_file():
            raise FileNotFoundError(str(file_path))
        file_path.unlink()

    async def exists(self, tenant_id: int, path: str) -> bool:
        safe_path = self._validate_path(path)
        return (self._tenant_dir(tenant_id) / Path(safe_path)).is_file()

    def write_json(self, tenant_id: int | str, key: str, data: Any) -> Path:  # TODO(TYPE): replace Any with concrete type
        file_path = self._tenant_dir(tenant_id) / f"{key}.json"
        file_path.write_text(json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8")
        return file_path

    def read_json(self, tenant_id: int | str, key: str, default: Any = None) -> Any:
        file_path = self._tenant_dir(tenant_id) / f"{key}.json"
        if not file_path.exists():
            return default
        return json.loads(file_path.read_text(encoding="utf-8"))


class S3TenantStorage:
    """Minimal in-memory S3-compatible stub for tests and wiring."""

    def __init__(self, bucket: str, prefix: str = "") -> None:
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self._objects: dict[str, tuple[bytes, str, datetime]] = {}

    def _get_key(self, tenant_id: int, path: str) -> str:
        safe_path = PurePosixPath(path).as_posix().lstrip("/")
        prefix_parts = [part for part in [self.prefix, str(tenant_id), safe_path] if part]
        return "/".join(prefix_parts)

    async def store(
        self,
        tenant_id: int,
        path: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> StorageObject:
        now = datetime.now(timezone.utc)
        key = self._get_key(tenant_id, path)
        self._objects[key] = (data, content_type, now)
        return StorageObject(
            path=path,
            tenant_id=tenant_id,
            size=len(data),
            created_at=now,
            modified_at=now,
            content_type=content_type,
        )

    async def retrieve(self, tenant_id: int, path: str) -> bytes:
        key = self._get_key(tenant_id, path)
        if key not in self._objects:
            raise FileNotFoundError(key)
        return self._objects[key][0]

    async def list(self, tenant_id: int) -> list[StorageObject]:
        prefix = self._get_key(tenant_id, "")
        results: list[StorageObject] = []
        for key, (data, content_type, modified_at) in self._objects.items():
            if not key.startswith(prefix):
                continue
            relative_path = key[len(prefix) :].lstrip("/")
            results.append(
                StorageObject(
                    path=relative_path,
                    tenant_id=tenant_id,
                    size=len(data),
                    created_at=modified_at,
                    modified_at=modified_at,
                    content_type=content_type,
                )
            )
        return sorted(results, key=lambda item: item.path)

    async def delete(self, tenant_id: int, path: str) -> None:
        key = self._get_key(tenant_id, path)
        if key not in self._objects:
            raise FileNotFoundError(key)
        del self._objects[key]

    async def exists(self, tenant_id: int, path: str) -> bool:
        return self._get_key(tenant_id, path) in self._objects


_STORAGE_SINGLETON: LocalTenantStorage | S3TenantStorage | None = None


def get_storage(backend: str = "local", **kwargs: Any) -> LocalTenantStorage | S3TenantStorage:
    """Return a singleton tenant storage backend."""

    global _STORAGE_SINGLETON
    if _STORAGE_SINGLETON is None:
        if backend == "s3":
            _STORAGE_SINGLETON = S3TenantStorage(**kwargs)
        else:
            base_path = kwargs.get("base_path", "./storage/tenant_data")
            _STORAGE_SINGLETON = LocalTenantStorage(base_path)
    return _STORAGE_SINGLETON


def reset_storage() -> None:
    """Reset the cached storage singleton for tests."""

    global _STORAGE_SINGLETON
    _STORAGE_SINGLETON = None


__all__ = [
    "LocalTenantStorage",
    "PathTraversalError",
    "S3TenantStorage",
    "StorageObject",
    "get_storage",
    "reset_storage",
]
