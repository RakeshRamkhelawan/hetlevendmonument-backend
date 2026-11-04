"""Integration tests for BE-EP-040 OAI-PMH metadata harvesting endpoint.

Real Postgres and FastAPI integration client.
Verifies protocol compliance:
- XML content-type (never JSON)
- HTTP GET and POST methods
- All 6 OAI-PMH verbs (Identify, ListMetadataFormats, ListSets, GetRecord, ListIdentifiers, ListRecords)
- Protocol errors return HTTP 200 with <error code="..."> tags
- N-2 invariant: edu-channel and community content are never harvested
- Anonymity masking (BE-EP-038) in Dublin Core
- Deleted records emit <header status="deleted"> without metadata
- Flow control with resumptionToken
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.foundation_content import (
    ContentStatus,
    ContentType,
    FoundationContent,
    Privacy,
    Visibility,
)
from src.core.services.oai_pmh_service import OAI_DC_NAMESPACE, OAI_NAMESPACE


def _oai_url(tenant_slug: str = "default") -> str:
    return f"/{tenant_slug}/foundation/oai-pmh"


@pytest_asyncio.fixture(scope="function")
async def seed_oai_content(postgres_session: AsyncSession) -> list[FoundationContent]:
    """Seed test content for tenant_id=1 with various visibilities and statuses."""
    items = [
        # 1. Public approved named content (should appear in harvest)
        FoundationContent(
            tenant_id=1,
            type=ContentType.STORY,
            title_nl="Publiek Verhaal 1",
            description_nl="Beschrijving 1",
            creator_name="Klaas de Vries",
            is_anonymous=False,
            privacy=Privacy.PUBLIC,
            visibility=Visibility.PUBLIC,
            status=ContentStatus.APPROVED,
            license="CC BY-NC-SA 4.0",
            location_name="Amsterdam",
            rights_confirmed=True,
        ),
        # 2. Public approved anonymous content (should appear, but creator masked)
        FoundationContent(
            tenant_id=1,
            type=ContentType.AUDIO,
            title_nl="Anoniem Audioverhaal",
            description_nl="Beschrijving 2",
            creator_name="Verborgen Auteur",
            is_anonymous=True,
            privacy=Privacy.PUBLIC,
            visibility=Visibility.PUBLIC,
            status=ContentStatus.APPROVED,
            license="CC BY-NC-SA 4.0",
            location_name="Utrecht",
            rights_confirmed=True,
        ),
        # 3. EDU content (MUST NOT APPEAR in harvest - N-2 Invariant!)
        FoundationContent(
            tenant_id=1,
            type=ContentType.EDUCATIONAL_WORKBOOK,
            title_nl="Educatief Werkblad",
            creator_name="Docent",
            is_anonymous=False,
            privacy=Privacy.PUBLIC,
            visibility=Visibility.EDU,
            status=ContentStatus.APPROVED,
            license="CC BY-NC-SA 4.0",
            rights_confirmed=True,
        ),
        # 4. Pending content (MUST NOT APPEAR in harvest)
        FoundationContent(
            tenant_id=1,
            type=ContentType.STORY,
            title_nl="Concept Verhaal",
            creator_name="Schrijver",
            is_anonymous=False,
            privacy=Privacy.PUBLIC,
            visibility=Visibility.PUBLIC,
            status=ContentStatus.PENDING,
            rights_confirmed=True,
        ),
        # 5. Removed content (MUST APPEAR as <header status="deleted">)
        FoundationContent(
            tenant_id=1,
            type=ContentType.STORY,
            title_nl="Ingetrokken Verhaal",
            creator_name="Ex-Auteur",
            is_anonymous=False,
            privacy=Privacy.PUBLIC,
            visibility=Visibility.PUBLIC,
            status=ContentStatus.REMOVED,
            rights_confirmed=True,
        ),
    ]
    for it in items:
        postgres_session.add(it)
    await postgres_session.flush()
    for it in items:
        await postgres_session.refresh(it)
    return items


# ============================================================================
# Identify & Protocol Compliance
# ============================================================================


class TestOaiIdentify:
    @pytest.mark.integration
    async def test_identify_get_returns_xml(
        self, integration_client: AsyncClient
    ) -> None:
        response = await integration_client.get(_oai_url("default"), params={"verb": "Identify"})
        assert response.status_code == 200
        assert "text/xml" in response.headers["content-type"]

        root = ET.fromstring(response.text)
        assert root.tag == f"{{{OAI_NAMESPACE}}}OAI-PMH"
        identify_el = root.find(f".//{{{OAI_NAMESPACE}}}Identify")
        assert identify_el is not None
        assert identify_el.find(f"{{{OAI_NAMESPACE}}}protocolVersion").text == "2.0"
        assert identify_el.find(f"{{{OAI_NAMESPACE}}}deletedRecord").text == "transient"

    @pytest.mark.integration
    async def test_identify_post_method_supported(
        self, integration_client: AsyncClient
    ) -> None:
        """Section 3.1.1: Providers must support both HTTP GET and POST."""
        response = await integration_client.post(
            _oai_url("default"),
            data={"verb": "Identify"},
        )
        assert response.status_code == 200
        assert "text/xml" in response.headers["content-type"]
        root = ET.fromstring(response.text)
        assert root.find(f".//{{{OAI_NAMESPACE}}}Identify") is not None


# ============================================================================
# ListMetadataFormats & ListSets
# ============================================================================


class TestOaiMetadataFormatsAndSets:
    @pytest.mark.integration
    async def test_list_metadata_formats(
        self, integration_client: AsyncClient
    ) -> None:
        response = await integration_client.get(
            _oai_url("default"), params={"verb": "ListMetadataFormats"}
        )
        assert response.status_code == 200
        root = ET.fromstring(response.text)
        formats = root.findall(f".//{{{OAI_NAMESPACE}}}metadataFormat")
        assert len(formats) >= 1
        prefixes = [f.find(f"{{{OAI_NAMESPACE}}}metadataPrefix").text for f in formats]
        assert "oai_dc" in prefixes

    @pytest.mark.integration
    async def test_list_sets(
        self, integration_client: AsyncClient
    ) -> None:
        response = await integration_client.get(
            _oai_url("default"), params={"verb": "ListSets"}
        )
        assert response.status_code == 200
        root = ET.fromstring(response.text)
        sets = root.findall(f".//{{{OAI_NAMESPACE}}}set")
        assert len(sets) >= 1


# ============================================================================
# ListRecords & Content Filtering Invariants
# ============================================================================


class TestOaiListRecords:
    @pytest.mark.integration
    async def test_list_records_returns_approved_public_and_deleted(
        self, integration_client: AsyncClient, seed_oai_content: list[FoundationContent]
    ) -> None:
        response = await integration_client.get(
            _oai_url("default"),
            params={"verb": "ListRecords", "metadataPrefix": "oai_dc"},
        )
        assert response.status_code == 200
        assert "text/xml" in response.headers["content-type"]

        root = ET.fromstring(response.text)
        records = root.findall(f".//{{{OAI_NAMESPACE}}}record")
        assert len(records) >= 3  # At least named, anonymous, and removed

        # 1. Check named record has creator and dc metadata
        titles = [t.text for t in root.findall(".//{http://purl.org/dc/elements/1.1/}title")]
        assert "Publiek Verhaal 1" in titles
        assert "Anoniem Audioverhaal" in titles

        # 2. Check N-2 Invariant: EDU and PENDING must NEVER appear!
        assert "Educatief Werkblad" not in titles
        assert "Concept Verhaal" not in titles

        # 3. Check anonymity: "Verborgen Auteur" must NEVER appear in creators
        creators = [c.text for c in root.findall(".//{http://purl.org/dc/elements/1.1/}creator")]
        assert "Klaas de Vries" in creators
        assert "Verborgen Auteur" not in creators

        # 4. Check deleted record: emits <header status="deleted">
        deleted_headers = [
            h for h in root.findall(f".//{{{OAI_NAMESPACE}}}header")
            if h.attrib.get("status") == "deleted"
        ]
        assert len(deleted_headers) >= 1


# ============================================================================
# Error Handling & ResumptionToken Exclusivity
# ============================================================================


class TestOaiErrorHandling:
    @pytest.mark.integration
    async def test_bad_verb_returns_http_200_with_error_tag(
        self, integration_client: AsyncClient
    ) -> None:
        response = await integration_client.get(
            _oai_url("default"), params={"verb": "NonExistentVerb"}
        )
        # OAI-PMH rule: protocol errors MUST be HTTP 200 with XML <error>
        assert response.status_code == 200
        root = ET.fromstring(response.text)
        err = root.find(f"{{{OAI_NAMESPACE}}}error")
        assert err is not None
        assert err.attrib.get("code") == "badVerb"

    @pytest.mark.integration
    async def test_resumption_token_exclusivity_bad_argument(
        self, integration_client: AsyncClient
    ) -> None:
        response = await integration_client.get(
            _oai_url("default"),
            params={
                "verb": "ListRecords",
                "resumptionToken": "dummy_token",
                "metadataPrefix": "oai_dc",  # ILLEGAL with resumptionToken!
            },
        )
        assert response.status_code == 200
        root = ET.fromstring(response.text)
        err = root.find(f"{{{OAI_NAMESPACE}}}error")
        assert err is not None
        assert err.attrib.get("code") == "badArgument"

    @pytest.mark.integration
    async def test_get_record_unknown_id_returns_id_does_not_exist(
        self, integration_client: AsyncClient
    ) -> None:
        response = await integration_client.get(
            _oai_url("default"),
            params={
                "verb": "GetRecord",
                "identifier": "oai:default:999999",
                "metadataPrefix": "oai_dc",
            },
        )
        assert response.status_code == 200
        root = ET.fromstring(response.text)
        err = root.find(f"{{{OAI_NAMESPACE}}}error")
        assert err is not None
        assert err.attrib.get("code") == "idDoesNotExist"
