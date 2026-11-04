"""Tests for FileUploadService S3 backend — no-any-return fixes."""

import pytest
from unittest.mock import MagicMock, patch

from src.core.services.file_upload_service import S3StorageBackend


@pytest.fixture
def s3_backend() -> S3StorageBackend:
    """Provide S3StorageBackend with mocked boto3."""
    # Ook S3_AVAILABLE patchen, niet alleen boto3. De backend bewaakt zichzelf met die
    # module-vlag ("if not S3_AVAILABLE: raise RuntimeError") en die staat op False zodra
    # boto3 ontbreekt -- dan slaat de constructor af voordat de gemockte boto3 iets doet.
    # boto3 staat in GEEN requirements-bestand en in geen van beide lockfiles; hij zit
    # alleen toevallig in sommige ontwikkelaars-venvs. Deze test slaagde daardoor lokaal en
    # faalde in CI met "boto3 not installed". De S3-backend is bewust optioneel, dus de test
    # hoort niet af te hangen van wat er toevallig geinstalleerd is.
    with (
        patch("src.core.services.file_upload_service.boto3"),
        patch("src.core.services.file_upload_service.S3_AVAILABLE", True),
    ):
        backend = S3StorageBackend(
            bucket_name="test-bucket",
            region="us-east-1",
            access_key="test_key",
            secret_key="test_secret",
        )
        backend.s3 = MagicMock()
        return backend


class TestS3StorageBackendDownload:
    """Test S3StorageBackend.download method."""

    @pytest.mark.asyncio
    async def test_download_returns_bytes_when_file_found(
        self, s3_backend: S3StorageBackend
    ) -> None:
        """Happy path: download returns bytes when file exists."""
        file_id = "test-file-123"
        expected_content = b"test file content"

        # Mock S3 list and get responses
        s3_backend.s3.list_objects_v2.return_value = {
            "Contents": [{"Key": "uploads/2026/05/test-file-123.pdf"}]
        }
        mock_body = MagicMock()
        mock_body.read.return_value = expected_content
        s3_backend.s3.get_object.return_value = {"Body": mock_body}

        result = await s3_backend.download(file_id)

        assert isinstance(result, bytes)
        assert result == expected_content

    @pytest.mark.asyncio
    async def test_download_returns_none_when_file_not_found(
        self, s3_backend: S3StorageBackend
    ) -> None:
        """Unhappy path: download returns None when file doesn't exist."""
        file_id = "nonexistent-file"

        s3_backend.s3.list_objects_v2.return_value = {"Contents": []}

        result = await s3_backend.download(file_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_download_returns_none_on_client_error(
        self, s3_backend: S3StorageBackend
    ) -> None:
        """Unhappy path: download returns None on S3 error."""
        # Het symbool uit de service zelf, niet uit botocore: dat is precies wat de
        # productiecode vangt, en het valt terug op Exception als botocore ontbreekt.
        # Een harde botocore-import maakt de test afhankelijk van een optionele library
        # die in geen requirements-bestand staat.
        from src.core.services.file_upload_service import ClientError

        file_id = "test-file-123"

        error_response = {"Error": {"Code": "NoSuchBucket"}}
        s3_backend.s3.list_objects_v2.side_effect = ClientError(error_response, "ListObjectsV2")

        result = await s3_backend.download(file_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_download_result_is_bytes_or_none(self, s3_backend: S3StorageBackend) -> None:
        """User behavioral test: download result can be used as bytes."""
        file_id = "test-file"
        test_bytes = b"content"

        s3_backend.s3.list_objects_v2.return_value = {
            "Contents": [{"Key": "uploads/2026/05/test-file.txt"}]
        }
        mock_body = MagicMock()
        mock_body.read.return_value = test_bytes
        s3_backend.s3.get_object.return_value = {"Body": mock_body}

        result = await s3_backend.download(file_id)

        # Verify result is bytes and can be used as such
        if result is not None:
            assert isinstance(result, bytes)
            assert len(result) > 0


class TestS3StorageBackendGetUrl:
    """Test S3StorageBackend.get_url method."""

    @pytest.mark.asyncio
    async def test_get_url_returns_presigned_url_when_file_found(
        self, s3_backend: S3StorageBackend
    ) -> None:
        """Happy path: get_url returns presigned URL when file exists."""
        file_id = "test-file-123"
        expected_url = (
            "https://s3.amazonaws.com/bucket/uploads/2026/05/test-file-123.pdf?signature=..."
        )

        s3_backend.s3.list_objects_v2.return_value = {
            "Contents": [{"Key": "uploads/2026/05/test-file-123.pdf"}]
        }
        s3_backend.s3.generate_presigned_url.return_value = expected_url

        result = await s3_backend.get_url(file_id)

        assert isinstance(result, str)
        assert result == expected_url
        assert result.startswith("https://")

    @pytest.mark.asyncio
    async def test_get_url_returns_none_when_file_not_found(
        self, s3_backend: S3StorageBackend
    ) -> None:
        """Unhappy path: get_url returns None when file doesn't exist."""
        file_id = "nonexistent-file"

        s3_backend.s3.list_objects_v2.return_value = {"Contents": []}

        result = await s3_backend.get_url(file_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_url_returns_none_on_client_error(self, s3_backend: S3StorageBackend) -> None:
        """Unhappy path: get_url returns None on S3 error."""
        # Het symbool uit de service zelf, niet uit botocore: dat is precies wat de
        # productiecode vangt, en het valt terug op Exception als botocore ontbreekt.
        # Een harde botocore-import maakt de test afhankelijk van een optionele library
        # die in geen requirements-bestand staat.
        from src.core.services.file_upload_service import ClientError

        file_id = "test-file-123"

        error_response = {"Error": {"Code": "AccessDenied"}}
        s3_backend.s3.list_objects_v2.side_effect = ClientError(error_response, "ListObjectsV2")

        result = await s3_backend.get_url(file_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_url_respects_expires_in_parameter(
        self, s3_backend: S3StorageBackend
    ) -> None:
        """Test that get_url passes ExpiresIn parameter to presigned URL."""
        file_id = "test-file"
        expires_in = 7200  # 2 hours

        s3_backend.s3.list_objects_v2.return_value = {
            "Contents": [{"Key": "uploads/2026/05/test-file.txt"}]
        }
        s3_backend.s3.generate_presigned_url.return_value = "https://s3.amazonaws.com/..."

        await s3_backend.get_url(file_id, expires_in=expires_in)

        # Verify generate_presigned_url was called with correct ExpiresIn
        call_args = s3_backend.s3.generate_presigned_url.call_args
        assert call_args is not None
        assert call_args[1]["ExpiresIn"] == expires_in

    @pytest.mark.asyncio
    async def test_get_url_result_is_string_or_none(self, s3_backend: S3StorageBackend) -> None:
        """User behavioral test: get_url result can be used as URL."""
        file_id = "test-file"
        test_url = "https://bucket.s3.amazonaws.com/uploads/file"

        s3_backend.s3.list_objects_v2.return_value = {
            "Contents": [{"Key": "uploads/2026/05/test-file.txt"}]
        }
        s3_backend.s3.generate_presigned_url.return_value = test_url

        result = await s3_backend.get_url(file_id)

        # Verify result is string and can be used as URL
        if result is not None:
            assert isinstance(result, str)
            assert "http" in result
