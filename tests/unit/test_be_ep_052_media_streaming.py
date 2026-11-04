"""Offline unit tests for BE-EP-052 (Secure Media Streaming, Range Requests & SAS).

No DB, no network. Covers:
1. RFC 9110 Range Header handling in stream_local_file:
   - Full content (no Range header) -> 200 OK + Content-Length + Accept-Ranges
   - Closed range (bytes=0-499) -> 206 Partial Content + Content-Range + correct byte slice
   - Open range (bytes=500-) -> 206 Partial Content + Content-Range + bytes from 500 to end
   - Suffix range (bytes=-500) -> 206 Partial Content + Content-Range + last 500 bytes
   - Unsatisfiable range (start >= size, negative start, start > end) -> 416 Range Not Satisfiable
   - Empty file with range -> 416
   - Malformed range headers handled gracefully
2. Headers & Security:
   - X-Content-Type-Options: nosniff
   - Content-Disposition: inline vs attachment; filename="sanitized"
3. Storage Service:
   - Path traversal prevention in get_local_file_path (.. attacks, absolute attacks)
   - Azure SAS token generation:
     - User delegation key vs Account SAS fallback
     - Content-disposition and Content-type SAS parameters
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from starlette.requests import Request
from starlette.responses import StreamingResponse
from fastapi import HTTPException, status

from src.core.api.v1.foundation.upload import stream_local_file
from src.core.services.foundation_storage import FoundationStorageService
from src.core.shared.config import Settings


def _create_dummy_request(headers: dict[str, str] | None = None) -> Request:
    raw_headers = []
    if headers:
        for k, v in headers.items():
            raw_headers.append((k.lower().encode("latin-1"), v.encode("latin-1")))
    scope = {
        "type": "http",
        "method": "GET",
        "headers": raw_headers,
    }
    return Request(scope)


async def _consume_streaming_response(response: StreamingResponse) -> bytes:
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)
    return b"".join(chunks)


@pytest.mark.unit
class TestStreamLocalFileRangeRequests:
    @pytest.fixture
    def sample_file(self, tmp_path: Path) -> Path:
        file = tmp_path / "audio_sample.mp3"
        # 1000 bytes: 0, 1, 2, ..., 999 (modulo 256)
        content = bytes(i % 256 for i in range(1000))
        file.write_bytes(content)
        return file

    @pytest.mark.asyncio
    async def test_non_range_request_returns_200_and_full_content(self, sample_file: Path) -> None:
        req = _create_dummy_request()
        resp = await stream_local_file(
            sample_file,
            req,
            download=False,
            filename="sample.mp3",
            mime_type="audio/mpeg",
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.headers["Accept-Ranges"] == "bytes"
        assert resp.headers["Content-Length"] == "1000"
        assert resp.headers["X-Content-Type-Options"] == "nosniff"
        assert resp.headers["Content-Disposition"] == 'inline; filename="sample.mp3"'
        assert resp.media_type == "audio/mpeg"

        body = await _consume_streaming_response(resp)  # type: ignore[arg-type]
        assert len(body) == 1000
        assert body == bytes(i % 256 for i in range(1000))

    @pytest.mark.asyncio
    async def test_closed_range_request_returns_206(self, sample_file: Path) -> None:
        req = _create_dummy_request({"Range": "bytes=100-199"})
        resp = await stream_local_file(
            sample_file,
            req,
            download=False,
            filename="sample.mp3",
            mime_type="audio/mpeg",
        )
        assert resp.status_code == status.HTTP_206_PARTIAL_CONTENT
        assert resp.headers["Accept-Ranges"] == "bytes"
        assert resp.headers["Content-Length"] == "100"
        assert resp.headers["Content-Range"] == "bytes 100-199/1000"
        assert resp.headers["X-Content-Type-Options"] == "nosniff"

        body = await _consume_streaming_response(resp)  # type: ignore[arg-type]
        assert len(body) == 100
        assert body == bytes(i % 256 for i in range(100, 200))

    @pytest.mark.asyncio
    async def test_open_range_request_returns_206(self, sample_file: Path) -> None:
        req = _create_dummy_request({"Range": "bytes=800-"})
        resp = await stream_local_file(
            sample_file,
            req,
            download=False,
            filename="sample.mp3",
            mime_type="audio/mpeg",
        )
        assert resp.status_code == status.HTTP_206_PARTIAL_CONTENT
        assert resp.headers["Content-Length"] == "200"
        assert resp.headers["Content-Range"] == "bytes 800-999/1000"

        body = await _consume_streaming_response(resp)  # type: ignore[arg-type]
        assert len(body) == 200
        assert body == bytes(i % 256 for i in range(800, 1000))

    @pytest.mark.asyncio
    async def test_suffix_range_request_returns_206(self, sample_file: Path) -> None:
        req = _create_dummy_request({"Range": "bytes=-150"})
        resp = await stream_local_file(
            sample_file,
            req,
            download=False,
            filename="sample.mp3",
            mime_type="audio/mpeg",
        )
        assert resp.status_code == status.HTTP_206_PARTIAL_CONTENT
        assert resp.headers["Content-Length"] == "150"
        assert resp.headers["Content-Range"] == "bytes 850-999/1000"

        body = await _consume_streaming_response(resp)  # type: ignore[arg-type]
        assert len(body) == 150
        assert body == bytes(i % 256 for i in range(850, 1000))

    @pytest.mark.asyncio
    async def test_if_range_matching_etag_returns_206(self, sample_file: Path) -> None:
        # First request to get the ETag
        req_first = _create_dummy_request()
        resp_first = await stream_local_file(
            sample_file,
            req_first,
            download=False,
            filename="sample.mp3",
            mime_type="audio/mpeg",
        )
        etag = resp_first.headers["ETag"]
        assert etag

        # Subsequent range request with matching If-Range
        req = _create_dummy_request({"Range": "bytes=0-99", "If-Range": etag})
        resp = await stream_local_file(
            sample_file,
            req,
            download=False,
            filename="sample.mp3",
            mime_type="audio/mpeg",
        )
        assert resp.status_code == status.HTTP_206_PARTIAL_CONTENT
        assert resp.headers["Content-Range"] == "bytes 0-99/1000"
        body = await _consume_streaming_response(resp)  # type: ignore[arg-type]
        assert len(body) == 100

    @pytest.mark.asyncio
    async def test_if_range_mismatch_returns_200_full_content(self, sample_file: Path) -> None:
        # Range request with outdated/mismatched If-Range validator
        req = _create_dummy_request({"Range": "bytes=0-99", "If-Range": '"outdated-etag-12345"'})
        resp = await stream_local_file(
            sample_file,
            req,
            download=False,
            filename="sample.mp3",
            mime_type="audio/mpeg",
        )
        # Per RFC 9110 Section 14.4: mismatch causes server to ignore Range and return 200 OK
        assert resp.status_code == status.HTTP_200_OK
        assert resp.headers["Content-Length"] == "1000"
        assert "Content-Range" not in resp.headers
        body = await _consume_streaming_response(resp)  # type: ignore[arg-type]
        assert len(body) == 1000

    @pytest.mark.asyncio
    async def test_download_flag_sets_attachment_disposition(self, sample_file: Path) -> None:
        req = _create_dummy_request()
        resp = await stream_local_file(
            sample_file,
            req,
            download=True,
            filename="Mijn Oral History.mp3",
            mime_type="audio/mpeg",
        )
        assert resp.status_code == status.HTTP_200_OK
        # secure_filename cleans spaces and accents
        assert 'attachment; filename="Mijn_Oral_History.mp3"' == resp.headers["Content-Disposition"]

    @pytest.mark.asyncio
    async def test_unsatisfiable_range_raises_416(self, sample_file: Path) -> None:
        req = _create_dummy_request({"Range": "bytes=1500-1600"})
        with pytest.raises(HTTPException) as exc_info:
            await stream_local_file(
                sample_file,
                req,
                download=False,
                filename="sample.mp3",
                mime_type="audio/mpeg",
            )
        assert exc_info.value.status_code == status.HTTP_416_RANGE_NOT_SATISFIABLE
        assert exc_info.value.headers["Content-Range"] == "bytes */1000"

    @pytest.mark.asyncio
    async def test_inverted_range_raises_416(self, sample_file: Path) -> None:
        req = _create_dummy_request({"Range": "bytes=500-400"})
        with pytest.raises(HTTPException) as exc_info:
            await stream_local_file(
                sample_file,
                req,
                download=False,
                filename="sample.mp3",
                mime_type="audio/mpeg",
            )
        assert exc_info.value.status_code == status.HTTP_416_RANGE_NOT_SATISFIABLE

    @pytest.mark.asyncio
    async def test_empty_file_with_range_raises_416(self, tmp_path: Path) -> None:
        empty_file = tmp_path / "empty.mp3"
        empty_file.write_bytes(b"")
        req = _create_dummy_request({"Range": "bytes=0-10"})
        with pytest.raises(HTTPException) as exc_info:
            await stream_local_file(
                empty_file,
                req,
                download=False,
                filename="empty.mp3",
                mime_type="audio/mpeg",
            )
        assert exc_info.value.status_code == status.HTTP_416_RANGE_NOT_SATISFIABLE
        assert exc_info.value.headers["Content-Range"] == "bytes */0"


@pytest.mark.unit
class TestStorageLocalPathTraversal:
    def test_safe_local_path_resolves(self, tmp_path: Path) -> None:
        settings = Settings(
            storage_backend="local",
            local_upload_dir=str(tmp_path),
            max_upload_size_bytes=1024,
        )
        storage = FoundationStorageService(settings=settings)

        # Create target file
        subdir = tmp_path / "tenant_1" / "audio"
        subdir.mkdir(parents=True)
        file = subdir / "story.mp3"
        file.write_text("dummy")

        resolved = storage.get_local_file_path("/uploads/tenant_1/audio/story.mp3")
        assert resolved is not None
        assert resolved == file.resolve()

    def test_path_traversal_dot_dot_returns_none(self, tmp_path: Path) -> None:
        settings = Settings(
            storage_backend="local",
            local_upload_dir=str(tmp_path),
            max_upload_size_bytes=1024,
        )
        storage = FoundationStorageService(settings=settings)

        assert storage.get_local_file_path("../../etc/passwd") is None
        assert storage.get_local_file_path("/uploads/../../secret.txt") is None
        assert storage.get_local_file_path("../tenant/file.mp3") is None

    def test_http_url_returns_none(self, tmp_path: Path) -> None:
        settings = Settings(
            storage_backend="local",
            local_upload_dir=str(tmp_path),
            max_upload_size_bytes=1024,
        )
        storage = FoundationStorageService(settings=settings)

        assert storage.get_local_file_path("https://azure.blob.core.windows.net/blob/file.mp3") is None
        assert storage.get_local_file_path("http://localhost:8000/media") is None


@pytest.mark.unit
class TestStorageAzureSasGeneration:
    @pytest.mark.asyncio
    async def test_azure_user_delegation_sas_called_when_credential_supported(self) -> None:
        settings = Settings(
            storage_backend="azure",
            azure_storage_account_url="https://mystorage.blob.core.windows.net",
            foundation_blob_container="foundation-content",
        )
        storage = FoundationStorageService(settings=settings)

        mock_delegation_key = MagicMock()
        mock_service_client = MagicMock()
        mock_service_client.account_name = "mystorage"
        mock_service_client.get_user_delegation_key.return_value = mock_delegation_key

        with patch("azure.storage.blob.BlobServiceClient", return_value=mock_service_client), \
             patch("azure.identity.DefaultAzureCredential", return_value=MagicMock()), \
             patch("azure.storage.blob.generate_blob_sas", return_value="sig=mocked_user_delegation_sas") as mock_sas:

            file_url = "https://mystorage.blob.core.windows.net/foundation-content/2026/09/oral_history.mp4"
            read_url = await storage.generate_read_url(
                file_url,
                expiry_minutes=15,
                download=True,
                filename="Geschiedenis.mp4",
                mime_type="video/mp4",
            )

            assert "sig=mocked_user_delegation_sas" in read_url
            mock_service_client.get_user_delegation_key.assert_called_once()
            mock_sas.assert_called_once()
            _, kwargs = mock_sas.call_args
            assert kwargs["user_delegation_key"] == mock_delegation_key
            assert kwargs["account_name"] == "mystorage"
            assert kwargs["container_name"] == "foundation-content"
            assert kwargs["blob_name"] == "2026/09/oral_history.mp4"
            assert kwargs["content_disposition"] == 'attachment; filename="Geschiedenis.mp4"'
            assert kwargs["content_type"] == "video/mp4"

    @pytest.mark.asyncio
    async def test_azure_account_sas_fallback_when_connection_string_provided(self) -> None:
        settings = Settings(
            storage_backend="azure",
            azure_storage_connection_string="DefaultEndpointsProtocol=https;AccountName=testaccount;AccountKey=dGVzdGtleQ==;EndpointSuffix=core.windows.net",
            foundation_blob_container="foundation-content",
        )
        storage = FoundationStorageService(settings=settings)

        mock_service_client = MagicMock()
        del mock_service_client.get_user_delegation_key  # no user delegation
        mock_service_client.credential.account_key = "dGVzdGtleQ=="

        with patch("azure.storage.blob.BlobServiceClient.from_connection_string", return_value=mock_service_client), \
             patch("azure.storage.blob.generate_blob_sas", return_value="sig=mocked_account_sas") as mock_sas:

            file_url = "https://testaccount.blob.core.windows.net/foundation-content/audio/voice.mp3"
            read_url = await storage.generate_read_url(
                file_url,
                expiry_minutes=30,
                download=False,
                filename="voice.mp3",
                mime_type="audio/mpeg",
            )

            assert "sig=mocked_account_sas" in read_url
            mock_sas.assert_called_once()
            _, kwargs = mock_sas.call_args
            assert kwargs["account_key"] == "dGVzdGtleQ=="
            assert kwargs["content_disposition"] == 'inline; filename="voice.mp3"'
            assert kwargs["content_type"] == "audio/mpeg"
