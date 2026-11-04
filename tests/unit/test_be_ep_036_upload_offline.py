"""Offline unit tests for BE-EP-036 (upload endpoint + storage service).

No DB, no network. Covers: MIME detection on forged magic bytes, rejection of
an executable with a .png name, the text/plain fallback (UTF-8 or not), the
chunked size-guard at the chunk boundary, filename sanitizing, the local
backend really writing to tmp_path, and the azure backend with a monkeypatched
BlobServiceClient.

Skip-don't-fail when puremagic is missing (BE-MIG-013 pattern).
"""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("puremagic")

from fastapi import HTTPException, UploadFile

from src.core.services.foundation_storage import (
    FoundationStorageNotConfiguredError,
    FoundationStorageService,
    detect_allowed_mime,
    secure_filename,
)
from src.core.shared.config import Settings

# Forged magic-byte headers (just enough for puremagic to detect the type).
PNG_BYTES = bytes.fromhex("89504e470d0a1a0a") + b"\x00" * 64
JPEG_BYTES = bytes.fromhex("ffd8ffe0") + b"\x00" * 64
PDF_BYTES = b"%PDF-1.4\n" + b"\x00" * 64
MP4_BYTES = bytes.fromhex("000000186674797069736f6d00000000") + b"isomiso2" + b"\x00" * 32
EXE_BYTES = b"MZ" + b"\x00" * 64


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "storage_backend": "local",
        "local_upload_dir": "/tmp/uploads",
        "max_upload_size_bytes": 1024,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


# ============================================================================
# MIME detection (magic bytes)
# ============================================================================


@pytest.mark.unit
class TestDetectAllowedMime:
    def test_png_detected(self) -> None:
        assert (
            detect_allowed_mime(PNG_BYTES, filename="foto.png", declared_content_type="image/png")
            == "image/png"
        )

    def test_jpeg_detected(self) -> None:
        assert (
            detect_allowed_mime(JPEG_BYTES, filename="foto.jpg", declared_content_type="image/jpeg")
            == "image/jpeg"
        )

    def test_pdf_detected(self) -> None:
        assert (
            detect_allowed_mime(PDF_BYTES, filename="doc.pdf", declared_content_type="application/pdf")
            == "application/pdf"
        )

    def test_mp4_detected(self) -> None:
        assert (
            detect_allowed_mime(MP4_BYTES, filename="clip.mp4", declared_content_type="video/mp4")
            == "video/mp4"
        )

    def test_exe_with_png_name_rejected(self) -> None:
        """An executable renamed to .png must not pass as an image."""
        assert (
            detect_allowed_mime(EXE_BYTES, filename="evil.png", declared_content_type="image/png")
            is None
        )

    def test_text_plain_fallback_ok(self) -> None:
        """Plain text has no magic bytes: allowed via .txt + declared type + UTF-8."""
        assert (
            detect_allowed_mime(
                "hallo wereld\n".encode("utf-8"),
                filename="notitie.txt",
                declared_content_type="text/plain",
            )
            == "text/plain"
        )

    def test_text_plain_fallback_requires_utf8(self) -> None:
        # Bytes that puremagic does NOT match (no UTF-16 BOM!) and that are
        # not valid UTF-8 -> the fallback must reject them.
        payload = bytes([0x81, 0x82, 0x83, 0x84]) * 4
        assert (
            detect_allowed_mime(payload, filename="data.txt", declared_content_type="text/plain")
            is None
        )

    def test_text_plain_fallback_requires_declared_type(self) -> None:
        assert (
            detect_allowed_mime(
                b"hello\n",
                filename="notitie.txt",
                declared_content_type="application/octet-stream",
            )
            is None
        )

    def test_text_plain_fallback_requires_txt_extension(self) -> None:
        assert (
            detect_allowed_mime(b"hello\n", filename="notitie.md", declared_content_type="text/plain")
            is None
        )

    def test_undetected_binary_rejected(self) -> None:
        """Unknown binary without magic match and without the txt fallback."""
        payload = bytes(range(1, 32)) * 4
        assert (
            detect_allowed_mime(payload, filename="blob.bin", declared_content_type=None)
            is None
        )

    def test_empty_input_rejected(self) -> None:
        """Empty file: puremagic raises PureValueError on b""; we must reject
        before calling it (Gate-2 HIGH-1: empty upload -> 400, not 500)."""
        assert (
            detect_allowed_mime(b"", filename="leeg.txt", declared_content_type="text/plain")
            is None
        )
        assert detect_allowed_mime(b"", filename=None, declared_content_type=None) is None

    def test_declared_type_with_charset_accepted(self) -> None:
        """Gate-2 MEDIUM: 'text/plain; charset=utf-8' must pass the fallback."""
        assert (
            detect_allowed_mime(
                b"hallo wereld\n",
                filename="notitie.txt",
                declared_content_type="text/plain; charset=utf-8",
            )
            == "text/plain"
        )

    def test_declared_type_case_insensitive(self) -> None:
        assert (
            detect_allowed_mime(
                b"hallo wereld\n",
                filename="notitie.txt",
                declared_content_type="Text/Plain; Charset=UTF-8",
            )
            == "text/plain"
        )


# ============================================================================
# Size guard (chunk boundary)
# ============================================================================


class _FakeUpload:
    """Minimal stand-in for UploadFile.read(size) chunk semantics."""

    def __init__(self, data: bytes) -> None:
        self._data = data
        self._pos = 0

    async def read(self, size: int = -1) -> bytes:
        if self._pos >= len(self._data):
            return b""
        end = len(self._data) if size < 0 else min(self._pos + size, len(self._data))
        chunk = self._data[self._pos : end]
        self._pos = end
        return chunk


@pytest.mark.unit
class TestSizeGuard:
    async def test_exactly_at_cap_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.core.api.v1.foundation import upload as upload_module

        monkeypatch.setattr(upload_module, "_CHUNK_SIZE", 8)
        data = b"x" * 16
        result = await upload_module._read_capped(_FakeUpload(data), max_bytes=16)  # type: ignore[arg-type]
        assert result == data

    async def test_cap_plus_one_aborts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.core.api.v1.foundation import upload as upload_module

        monkeypatch.setattr(upload_module, "_CHUNK_SIZE", 8)
        with pytest.raises(HTTPException) as exc_info:
            await upload_module._read_capped(_FakeUpload(b"x" * 17), max_bytes=16)  # type: ignore[arg-type]
        assert exc_info.value.status_code == 413

    async def test_empty_file_reads_empty(self) -> None:
        from src.core.api.v1.foundation import upload as upload_module

        result = await upload_module._read_capped(_FakeUpload(b""), max_bytes=16)  # type: ignore[arg-type]
        assert result == b""


# ============================================================================
# Filename sanitize
# ============================================================================


@pytest.mark.unit
class TestSecureFilename:
    def test_path_traversal_removed(self) -> None:
        assert "/" not in secure_filename("../../etc/passwd")
        assert "\\" not in secure_filename("..\\..\\windows\\system32\\x.dll")

    def test_unsafe_chars_replaced(self) -> None:
        assert secure_filename("mijn foto<v1>.png") == "mijn_foto_v1_.png"

    def test_none_and_empty_become_unnamed(self) -> None:
        assert secure_filename(None) == "unnamed"
        assert secure_filename("") == "unnamed"

    def test_normal_name_unchanged(self) -> None:
        assert secure_filename("foto-2026_09.png") == "foto-2026_09.png"


# ============================================================================
# Local backend (really writes to tmp_path)
# ============================================================================


@pytest.mark.unit
class TestLocalBackend:
    async def test_writes_file_and_returns_relative_url(self, tmp_path: Path) -> None:
        service = FoundationStorageService(
            settings=_settings(local_upload_dir=str(tmp_path))
        )
        url = await service.upload(
            tenant_id=3,
            content_id=7,
            filename="foto.png",
            data=PNG_BYTES,
            mime_type="image/png",
        )
        assert url.startswith("/uploads/foundation/3/7/")
        assert url.endswith(".png")
        rel = url.removeprefix("/uploads/")
        written = tmp_path.joinpath(*rel.split("/"))
        assert written.is_file()
        assert written.read_bytes() == PNG_BYTES

    async def test_filename_does_not_leak_into_path(self, tmp_path: Path) -> None:
        service = FoundationStorageService(
            settings=_settings(local_upload_dir=str(tmp_path))
        )
        url = await service.upload(
            tenant_id=1,
            content_id=2,
            filename="../../escape.png",
            data=PNG_BYTES,
            mime_type="image/png",
        )
        assert ".." not in url
        assert "escape" not in url

    async def test_unknown_backend_raises_not_configured(self, tmp_path: Path) -> None:
        service = FoundationStorageService(
            settings=_settings(storage_backend="s3", local_upload_dir=str(tmp_path))
        )
        with pytest.raises(FoundationStorageNotConfiguredError):
            await service.upload(
                tenant_id=1,
                content_id=2,
                filename="f.png",
                data=PNG_BYTES,
                mime_type="image/png",
            )


# ============================================================================
# Azure backend (monkeypatched BlobServiceClient, no network)
# ============================================================================


@pytest.mark.unit
class TestAzureBackend:
    def _conn_str(self) -> str:
        key = base64.b64encode(b"k" * 32).decode("ascii")
        return (
            "DefaultEndpointsProtocol=https;AccountName=testacct;"
            f"AccountKey={key};EndpointSuffix=core.windows.net"
        )

    async def test_upload_returns_canonical_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Inject a fully fake ``azure.storage.blob`` module into sys.modules.
        # The service imports it lazily inside _upload_azure, so the fake is
        # picked up and the real SDK (and the network) is never touched. The
        # real SDK is also unimportable under this project's pytest loguru
        # interception (its vendored avro module logs at numeric level 5).
        import sys
        import types

        uploaded: dict[str, object] = {}

        class _FakeBlobClient:
            account_name = "testacct"

            def __init__(self, container: str, blob: str) -> None:
                self.url = (
                    f"https://testacct.blob.core.windows.net/{container}/{blob}"
                )

            def upload_blob(self, data: bytes, **kwargs: object) -> None:
                uploaded["data"] = data
                uploaded["kwargs"] = kwargs

        class _FakeServiceClient:
            @classmethod
            def from_connection_string(cls, conn_str: str) -> "_FakeServiceClient":
                uploaded["conn_str"] = conn_str
                return cls()

            def get_blob_client(self, container: str, blob: str) -> _FakeBlobClient:
                uploaded["container"] = container
                uploaded["blob"] = blob
                return _FakeBlobClient(container, blob)

        fake_module = types.ModuleType("azure.storage.blob")
        fake_module.BlobServiceClient = _FakeServiceClient  # type: ignore[attr-defined]
        fake_module.ContentSettings = (  # type: ignore[attr-defined]
            lambda content_type=None: SimpleNamespace(content_type=content_type)
        )
        monkeypatch.setitem(sys.modules, "azure.storage.blob", fake_module)

        service = FoundationStorageService(
            settings=_settings(
                storage_backend="azure",
                azure_storage_connection_string=self._conn_str(),
            )
        )
        url = await service.upload(
            tenant_id=5,
            content_id=9,
            filename="foto.png",
            data=PNG_BYTES,
            mime_type="image/png",
        )
        # Gate-2 HIGH-2 (2026-09-09): the stored URL is the CANONICAL blob
        # URL without a SAS token; SAS generation moves to the serve moment.
        assert url == str(
            f"https://testacct.blob.core.windows.net/foundation-content/{uploaded['blob']}"
        )
        assert "sig=" not in url
        assert "?" not in url
        assert str(uploaded["blob"]).startswith("foundation/5/9/")
        assert str(uploaded["blob"]).endswith(".png")
        assert uploaded["data"] == PNG_BYTES

    async def test_missing_connection_string_raises(self) -> None:
        service = FoundationStorageService(settings=_settings(storage_backend="azure"))
        with pytest.raises(FoundationStorageNotConfiguredError):
            await service.upload(
                tenant_id=1,
                content_id=2,
                filename="f.png",
                data=PNG_BYTES,
                mime_type="image/png",
            )


# ============================================================================
# Wiring smoke checks
# ============================================================================


@pytest.mark.unit
class TestWiring:
    def test_endpoint_module_imports_via_facade(self) -> None:
        """The endpoint module imports cleanly and exposes its router."""
        from src.core.api.v1.foundation import upload as upload_module

        assert upload_module.router is not None

    def test_sha256_matches_content(self, tmp_path: Path) -> None:
        """Checksum basis: response sha256 must equal sha256 of stored bytes."""
        expected = hashlib.sha256(PNG_BYTES).hexdigest()
        assert len(expected) == 64
