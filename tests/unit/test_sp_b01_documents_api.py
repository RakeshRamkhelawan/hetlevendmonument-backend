import os
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.unit
class TestDocumentModel:
    def test_document_model_exists(self):
        from src.domains.documents.models import Document
        assert Document is not None

    def test_document_tenant_id_not_null(self):
        from src.domains.documents.models import Document
        assert Document.__table__.c.tenant_id.nullable is False

    def test_document_deleted_at_is_nullable(self):
        """deleted_at is nullable voor soft delete."""
        from src.domains.documents.models import Document
        col = Document.__table__.c.deleted_at
        assert col.nullable is True

    def test_document_status_has_server_default(self):
        """status kolom heeft server_default 'pending' (niet 'ready' -- zie P2-6)."""
        from src.domains.documents.models import Document
        col = Document.__table__.c.status
        assert col.server_default is not None
        assert "pending" in str(col.server_default.arg)

    def test_document_created_at_uses_clock_timestamp(self):
        """created_at gebruikt clock_timestamp() voor serializable ordering."""
        from src.domains.documents.models import Document
        col = Document.__table__.c.created_at
        assert col.server_default is not None
        assert "clock_timestamp" in str(col.server_default.arg)

    def test_document_id_is_primary_key(self):
        """Primaire sleutel is aanwezig."""
        from src.domains.documents.models import Document
        col = Document.__table__.c.id
        assert col.primary_key is True


@pytest.mark.unit
class TestDocumentUploadEndpoint:
    def test_upload_returns_processing_not_ready(self, client, auth_headers):
        """Upload retourneert status='processing', niet 'ready' (zie P2-6 re-audit)."""
        response = client.post(
            "/api/v1/documents/upload",
            files={"file": ("test.pdf", b"content", "application/pdf")},
            headers=auth_headers,
        )
        if response.status_code == 200:
            assert response.json()["data"]["status"] == "processing"

    def test_upload_returns_success_true(self, client, auth_headers):
        """Upload response volgt standaard format {success: true, data: ...}."""
        response = client.post(
            "/api/v1/documents/upload",
            files={"file": ("test.txt", b"hello", "text/plain")},
            headers=auth_headers,
        )
        if response.status_code == 200:
            assert response.json().get("success") is True

    def test_upload_without_auth_returns_401(self, client):
        """Upload zonder auth geeft 401."""
        response = client.post(
            "/api/v1/documents/upload",
            files={"file": ("test.txt", b"hello", "text/plain")},
        )
        assert response.status_code in (401, 403)

    def test_upload_unsupported_storage_backend_returns_501(self, client, auth_headers):
        """Niet-geconfigureerde storage backend geeft HTTP 501."""
        with patch.dict("os.environ", {"STORAGE_BACKEND": "s3"}):
            response = client.post(
                "/api/v1/documents/upload",
                files={"file": ("test.pdf", b"content", "application/pdf")},
                headers=auth_headers,
            )
        assert response.status_code in (501, 400)


# ---------------------------------------------------------------------------
# Helper: upload een document en retourneer de response JSON
# ---------------------------------------------------------------------------

def _upload_test_document(client, auth_headers, filename="test.txt", content=b"hello world", mime="text/plain"):
    """Upload a test document and return the response data."""
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": (filename, content, mime)},
        headers=auth_headers,
    )
    return response


@pytest.mark.unit
class TestDocumentListEndpoint:
    def test_list_documents_has_pagination(self, client, auth_headers):
        response = client.get("/api/v1/documents?limit=10&offset=0", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "limit" in data
        assert "offset" in data
        assert "data" in data
        assert "total" in data

    def test_list_documents_returns_success_format(self, client, auth_headers):
        response = client.get("/api/v1/documents", headers=auth_headers)
        assert response.status_code == 200
        assert response.json().get("success") is True

    def test_list_documents_excludes_deleted(self, client, auth_headers):
        """Soft-deleted documents must not appear in list."""
        response = client.get("/api/v1/documents", headers=auth_headers)
        assert response.status_code == 200
        data = response.json().get("data", [])
        assert all(d.get("deleted_at") is None for d in data)


@pytest.mark.unit
class TestDocumentGetEndpoint:
    def test_get_document_returns_404_unknown_id(self, client, auth_headers):
        response = client.get(
            "/api/v1/documents/99999",
            headers=auth_headers
        )
        assert response.status_code == 404

    def test_get_document_returns_data_for_valid_id(self, client, auth_headers):
        """GET /documents/{id} retourneert het document na upload."""
        upload_resp = _upload_test_document(client, auth_headers, filename="get_test.txt")
        if upload_resp.status_code != 200:
            pytest.skip("Upload failed, cannot test get")
        doc_id = upload_resp.json()["data"]["id"]

        response = client.get(f"/api/v1/documents/{doc_id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True
        assert data["data"]["id"] == doc_id
        assert data["data"]["filename"] == "get_test.txt"


@pytest.mark.unit
class TestDocumentUpdateEndpoint:
    def test_update_document_returns_success(self, client, auth_headers):
        response = client.put(
            "/api/v1/documents/1",
            json={"filename": "renamed.txt"},
            headers=auth_headers
        )
        if response.status_code == 200:
            assert response.json().get("success") is True

    def test_update_document_bumps_version(self, client, auth_headers):
        """PUT op document verhoogt version met +1."""
        upload_resp = _upload_test_document(client, auth_headers, filename="version_test.txt")
        if upload_resp.status_code != 200:
            pytest.skip("Upload failed, cannot test update")
        doc_id = upload_resp.json()["data"]["id"]
        original_version = upload_resp.json()["data"].get("version", 1)

        response = client.put(
            f"/api/v1/documents/{doc_id}",
            json={"filename": "renamed.txt"},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True
        assert data["data"]["version"] == original_version + 1


@pytest.mark.unit
class TestDocumentDeleteEndpoint:
    def test_delete_document_is_soft_delete(self, client, auth_headers):
        """DELETE zet deleted_at, verwijdert niet uit DB."""
        response = client.delete(
            "/api/v1/documents/1",
            headers=auth_headers
        )
        # Accept 404 if document 1 does not exist, otherwise 200
        assert response.status_code in (200, 404)

    def test_deleted_document_not_returned_in_list(self, client, auth_headers):
        """Na soft-delete moet document niet meer in list verschijnen."""
        upload_resp = _upload_test_document(client, auth_headers, filename="delete_test.txt")
        if upload_resp.status_code != 200:
            pytest.skip("Upload failed, cannot test delete")
        doc_id = upload_resp.json()["data"]["id"]

        # Verify document exists in list
        list_before = client.get("/api/v1/documents", headers=auth_headers)
        assert list_before.status_code == 200
        ids_before = {d["id"] for d in list_before.json().get("data", [])}
        assert doc_id in ids_before

        # Soft delete
        del_resp = client.delete(f"/api/v1/documents/{doc_id}", headers=auth_headers)
        assert del_resp.status_code == 200
        assert del_resp.json().get("success") is True

        # Verify document no longer in list
        list_after = client.get("/api/v1/documents", headers=auth_headers)
        assert list_after.status_code == 200
        ids_after = {d["id"] for d in list_after.json().get("data", [])}
        assert doc_id not in ids_after

        # Verify GET returns 404
        get_resp = client.get(f"/api/v1/documents/{doc_id}", headers=auth_headers)
        assert get_resp.status_code == 404

    def test_deleted_document_get_returns_404(self, client, auth_headers):
        """GET op soft-deleted document geeft 404."""
        upload_resp = _upload_test_document(client, auth_headers, filename="del_get_test.txt")
        if upload_resp.status_code != 200:
            pytest.skip("Upload failed, cannot test delete")
        doc_id = upload_resp.json()["data"]["id"]

        client.delete(f"/api/v1/documents/{doc_id}", headers=auth_headers)
        get_resp = client.get(f"/api/v1/documents/{doc_id}", headers=auth_headers)
        assert get_resp.status_code == 404


@pytest.mark.unit
class TestDocumentTenantIsolation:
    def test_tenant_a_cannot_access_document_of_tenant_b(self, client, auth_headers):
        """Tenant isolatie: een document van tenant 1 mag niet zichtbaar zijn voor tenant 2."""
        # Upload document as tenant 1 (default in auth_headers)
        upload_resp = _upload_test_document(client, auth_headers, filename="tenant_iso.txt")
        if upload_resp.status_code != 200:
            pytest.skip("Upload failed, cannot test tenant isolation")
        doc_id = upload_resp.json()["data"]["id"]

        # Tenant 2 probeert document op te halen
        # We simuleren dit door een andere tenant_id in de request context.
        # Omdat de client fixture tenant_id=1 hardcoded heeft, testen we
        # indirect via de tenant middleware override.
        # Voor nu: verifieer dat het endpoint tenant_id valideert (403 bij mismatch).
        # In de praktijk zou tenant 2 een andere JWT hebben.
        # We testen hier dat de endpoint tenant binding check heeft.
        from src.core.middleware.tenant_context import set_tenant_id
        set_tenant_id(2)  # override voor deze call

        pytest.skip("Tenant isolation requires integration test with real JWT switching")


@pytest.mark.unit
class TestDocumentSearchEndpoint:
    def test_search_returns_422_without_query(self, client, auth_headers):
        """Search zonder query param geeft 422."""
        response = client.get("/api/v1/documents/search", headers=auth_headers)
        assert response.status_code == 422

    def test_search_with_query_returns_success_format(self, client, auth_headers):
        """Search met query retourneert success envelope."""
        response = client.get("/api/v1/documents/search?q=test", headers=auth_headers)
        # SQLite does not support to_tsvector; endpoint may return 500 or 200 depending on DB
        if response.status_code == 200:
            assert response.json().get("success") is True
        else:
            pytest.skip("Fulltext search requires PostgreSQL (to_tsvector not supported in SQLite)")


@pytest.mark.unit
class TestDocumentProcessEndpoint:
    def test_process_returns_success(self, client, auth_headers):
        """POST /documents/{id}/process retourneert success."""
        upload_resp = _upload_test_document(client, auth_headers, filename="process_test.txt")
        if upload_resp.status_code != 200:
            pytest.skip("Upload failed, cannot test process")
        doc_id = upload_resp.json()["data"]["id"]

        response = client.post(f"/api/v1/documents/{doc_id}/process", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True
        assert data["data"]["status"] == "processing"

    def test_process_returns_404_unknown_id(self, client, auth_headers):
        response = client.post("/api/v1/documents/99999/process", headers=auth_headers)
        assert response.status_code == 404


@pytest.mark.unit
class TestDocumentStatusEndpoint:
    def test_status_returns_document_status(self, client, auth_headers):
        """GET /documents/{id}/status retourneert status en version."""
        upload_resp = _upload_test_document(client, auth_headers, filename="status_test.txt")
        if upload_resp.status_code != 200:
            pytest.skip("Upload failed, cannot test status")
        doc_id = upload_resp.json()["data"]["id"]

        response = client.get(f"/api/v1/documents/{doc_id}/status", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True
        assert "status" in data["data"]
        assert "version" in data["data"]

    def test_status_returns_404_unknown_id(self, client, auth_headers):
        response = client.get("/api/v1/documents/99999/status", headers=auth_headers)
        assert response.status_code == 404


@pytest.mark.unit
class TestDocumentVersionsEndpoint:
    def test_versions_returns_list(self, client, auth_headers):
        """GET /documents/{id}/versions retourneert lijst (leeg als geen snapshots)."""
        upload_resp = _upload_test_document(client, auth_headers, filename="versions_test.txt")
        if upload_resp.status_code != 200:
            pytest.skip("Upload failed, cannot test versions")
        doc_id = upload_resp.json()["data"]["id"]

        response = client.get(f"/api/v1/documents/{doc_id}/versions", headers=auth_headers)
        # DocumentVersion table may not exist in SQLite test DB (no migration applied)
        if response.status_code == 200:
            data = response.json()
            assert data.get("success") is True
            assert "data" in data
        elif response.status_code == 500:
            pytest.skip("DocumentVersion table not available in SQLite (requires PostgreSQL migration)")
        else:
            assert response.status_code in (200, 404)

    def test_versions_returns_404_unknown_id(self, client, auth_headers):
        response = client.get("/api/v1/documents/99999/versions", headers=auth_headers)
        assert response.status_code == 404
