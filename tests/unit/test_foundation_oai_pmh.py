"""Unit tests for BE-EP-040 OAI-PMH metadata harvesting service and XML builder.

Offline: no database, no network calls. Validates OAI-PMH v2.0 protocol rules,
XML serialization with Dublin Core (oai_dc), resumptionToken exclusivity,
datestamp granularity checks, and error response generation.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import pytest

from src.core.services.oai_pmh_service import (
    OAI_DC_NAMESPACE,
    OAI_NAMESPACE,
    XSI_NAMESPACE,
    OaiPmhError,
    OaiPmhErrorCode,
    OaiPmhService,
    OaiRecord,
    OaiResumptionToken,
    sanitize_for_xml,
    validate_oai_parameters,
)
from src.core.shared.public_registry import PublicEndpointRegistry


# ============================================================================
# XML Sanitization & Unicode Helpers
# ============================================================================


class TestXmlSanitization:
    @pytest.mark.unit
    def test_strips_illegal_control_characters(self) -> None:
        raw_text = "Verhaal met \x00 null byte en \x08 backspace en \x1b escape"
        clean = sanitize_for_xml(raw_text)
        assert "\x00" not in clean
        assert "\x08" not in clean
        assert "\x1b" not in clean
        assert clean == "Verhaal met  null byte en  backspace en  escape"

    @pytest.mark.unit
    def test_preserves_allowed_whitespace(self) -> None:
        allowed = "Regel 1\tTab\nRegel 2\r\nRegel 3"
        clean = sanitize_for_xml(allowed)
        assert clean == allowed

    @pytest.mark.unit
    def test_handles_none_or_empty(self) -> None:
        assert sanitize_for_xml(None) == ""
        assert sanitize_for_xml("") == ""


# ============================================================================
# Parameter Validation & OAI-PMH 2.0 Protocol Rules
# ============================================================================


class TestParameterValidation:
    @pytest.mark.unit
    def test_missing_verb_returns_bad_verb(self) -> None:
        error = validate_oai_parameters(params={})
        assert error is not None
        assert error.code == OaiPmhErrorCode.BAD_VERB

    @pytest.mark.unit
    def test_unknown_verb_returns_bad_verb(self) -> None:
        error = validate_oai_parameters(params={"verb": "InvalidVerb"})
        assert error is not None
        assert error.code == OaiPmhErrorCode.BAD_VERB

    @pytest.mark.unit
    def test_resumption_token_exclusivity(self) -> None:
        """Section 3.5: resumptionToken is exclusive; combining with other args is badArgument."""
        params = {
            "verb": "ListRecords",
            "resumptionToken": "valid_token_xyz",
            "metadataPrefix": "oai_dc",  # ILLEGAL when resumptionToken is present!
        }
        error = validate_oai_parameters(params=params)
        assert error is not None
        assert error.code == OaiPmhErrorCode.BAD_ARGUMENT
        assert "exclusive" in error.message.lower()

    @pytest.mark.unit
    def test_resumption_token_alone_with_verb_is_valid(self) -> None:
        params = {
            "verb": "ListRecords",
            "resumptionToken": "valid_token_xyz",
        }
        error = validate_oai_parameters(params=params)
        assert error is None

    @pytest.mark.unit
    def test_get_record_requires_identifier_and_prefix(self) -> None:
        # Missing identifier
        err1 = validate_oai_parameters(params={"verb": "GetRecord", "metadataPrefix": "oai_dc"})
        assert err1 is not None and err1.code == OaiPmhErrorCode.BAD_ARGUMENT

        # Missing metadataPrefix
        err2 = validate_oai_parameters(params={"verb": "GetRecord", "identifier": "oai:test:1"})
        assert err2 is not None and err2.code == OaiPmhErrorCode.BAD_ARGUMENT

    @pytest.mark.unit
    def test_unsupported_metadata_prefix_returns_cannot_disseminate(self) -> None:
        err = validate_oai_parameters(
            params={"verb": "GetRecord", "identifier": "oai:test:1", "metadataPrefix": "marc21"}
        )
        assert err is not None
        assert err.code == OaiPmhErrorCode.CANNOT_DISSEMINATE_FORMAT

    @pytest.mark.unit
    def test_granularity_mismatch_returns_bad_argument(self) -> None:
        """Section 3.3.1: from and until must have identical granularity."""
        params = {
            "verb": "ListRecords",
            "metadataPrefix": "oai_dc",
            "from": "2026-09-01",  # day granularity
            "until": "2026-09-10T12:00:00Z",  # second granularity
        }
        error = validate_oai_parameters(params=params)
        assert error is not None
        assert error.code == OaiPmhErrorCode.BAD_ARGUMENT
        assert "granularity" in error.message.lower()

    @pytest.mark.unit
    def test_from_later_than_until_returns_bad_argument(self) -> None:
        params = {
            "verb": "ListRecords",
            "metadataPrefix": "oai_dc",
            "from": "2026-09-15",
            "until": "2026-09-10",
        }
        error = validate_oai_parameters(params=params)
        assert error is not None
        assert error.code == OaiPmhErrorCode.BAD_ARGUMENT
        assert "earlier" in error.message.lower() or "chronological" in error.message.lower()

    @pytest.mark.unit
    def test_unexpected_extra_arguments_returns_bad_argument(self) -> None:
        params = {
            "verb": "Identify",
            "extraParam": "hack",
        }
        error = validate_oai_parameters(params=params)
        assert error is not None
        assert error.code == OaiPmhErrorCode.BAD_ARGUMENT


# ============================================================================
# XML Document Generation (OAI-PMH Envelope & Dublin Core)
# ============================================================================


class TestOaiXmlBuilder:
    @pytest.fixture
    def service(self) -> OaiPmhService:
        return OaiPmhService(base_url="https://api.levendmonument.nl/default/foundation/oai-pmh")

    @pytest.mark.unit
    def test_envelope_structure_and_namespaces(self, service: OaiPmhService) -> None:
        xml_bytes = service.build_identify_response(
            repository_name="Levend Monument Archief",
            admin_email="archief@levendmonument.nl",
            earliest_datestamp="2026-01-01T00:00:00Z",
        )
        root = ET.fromstring(xml_bytes)

        # Check root tag and namespace
        assert root.tag == f"{{{OAI_NAMESPACE}}}OAI-PMH"
        assert root.find(f"{{{OAI_NAMESPACE}}}responseDate") is not None
        request_el = root.find(f"{{{OAI_NAMESPACE}}}request")
        assert request_el is not None
        assert request_el.attrib.get("verb") == "Identify"

        identify_el = root.find(f"{{{OAI_NAMESPACE}}}Identify")
        assert identify_el is not None
        assert (
            identify_el.find(f"{{{OAI_NAMESPACE}}}repositoryName").text
            == "Levend Monument Archief"
        )
        assert identify_el.find(f"{{{OAI_NAMESPACE}}}protocolVersion").text == "2.0"
        assert identify_el.find(f"{{{OAI_NAMESPACE}}}deletedRecord").text == "transient"
        assert (
            identify_el.find(f"{{{OAI_NAMESPACE}}}granularity").text
            == "YYYY-MM-DDThh:mm:ssZ"
        )

    @pytest.mark.unit
    def test_error_response_contains_error_tag(self, service: OaiPmhService) -> None:
        err = OaiPmhError(
            code=OaiPmhErrorCode.BAD_ARGUMENT,
            message="Invalid arguments supplied",
        )
        xml_bytes = service.build_error_response(
            error=err,
            params={"verb": "ListRecords"},
        )
        root = ET.fromstring(xml_bytes)
        assert root.tag == f"{{{OAI_NAMESPACE}}}OAI-PMH"
        err_el = root.find(f"{{{OAI_NAMESPACE}}}error")
        assert err_el is not None
        assert err_el.attrib.get("code") == "badArgument"
        assert err_el.text == "Invalid arguments supplied"

    @pytest.mark.unit
    def test_record_dublin_core_mapping_and_anonymity(self, service: OaiPmhService) -> None:
        # 1. Normal named record
        rec1 = OaiRecord(
            identifier="oai:default:101",
            datestamp="2026-09-10T12:00:00Z",
            title="Herinnering aan de Plantage",
            creator="Jan Jansen",
            description="Een verhaal over vroeger",
            date_recorded="1975",
            content_type="story",
            rights="CC BY-NC-SA 4.0",
            location_name="Paramaribo",
            is_anonymous=False,
            is_deleted=False,
        )
        xml_bytes1 = service.build_get_record_response(rec1)
        root1 = ET.fromstring(xml_bytes1)
        dc_el1 = root1.find(f".//{{{OAI_DC_NAMESPACE}}}dc")
        assert dc_el1 is not None

        creators = [e.text for e in dc_el1.findall(".//{http://purl.org/dc/elements/1.1/}creator")]
        assert "Jan Jansen" in creators

        rights = [e.text for e in dc_el1.findall(".//{http://purl.org/dc/elements/1.1/}rights")]
        assert "CC BY-NC-SA 4.0" in rights

        # 2. Anonymous record: creator MUST NOT be leaked (BE-EP-038)
        rec2 = OaiRecord(
            identifier="oai:default:102",
            datestamp="2026-09-10T12:00:00Z",
            title="Verborgen geschiedenis",
            creator="Geheime Schrijver",
            description="Geheim",
            date_recorded="1980",
            content_type="story",
            rights="CC BY-NC-SA 4.0",
            location_name=None,
            is_anonymous=True,
            is_deleted=False,
        )
        xml_bytes2 = service.build_get_record_response(rec2)
        root2 = ET.fromstring(xml_bytes2)
        dc_el2 = root2.find(f".//{{{OAI_DC_NAMESPACE}}}dc")
        assert dc_el2 is not None
        creators2 = [e.text for e in dc_el2.findall(".//{http://purl.org/dc/elements/1.1/}creator")]
        assert "Geheime Schrijver" not in creators2
        assert len(creators2) == 0 or creators2[0] in (None, "Anoniem")

    @pytest.mark.unit
    def test_deleted_record_has_deleted_header_and_no_metadata(
        self, service: OaiPmhService
    ) -> None:
        rec = OaiRecord(
            identifier="oai:default:999",
            datestamp="2026-09-10T14:00:00Z",
            title="Verwijderd record",
            creator="Niemand",
            description="N.v.t.",
            date_recorded=None,
            content_type="story",
            rights="CC BY-NC-SA 4.0",
            location_name=None,
            is_anonymous=False,
            is_deleted=True,
        )
        xml_bytes = service.build_get_record_response(rec)
        root = ET.fromstring(xml_bytes)

        header_el = root.find(f".//{{{OAI_NAMESPACE}}}header")
        assert header_el is not None
        assert header_el.attrib.get("status") == "deleted"

        # Crucial OAI-PMH rule: deleted records must NOT have a <metadata> block
        assert root.find(f".//{{{OAI_NAMESPACE}}}metadata") is None


# ============================================================================
# ResumptionToken Encoding & Decodering
# ============================================================================


class TestResumptionTokenHandling:
    @pytest.fixture
    def service(self) -> OaiPmhService:
        return OaiPmhService(base_url="https://api.levendmonument.nl/default/foundation/oai-pmh")

    @pytest.mark.unit
    def test_resumption_token_roundtrip(self, service: OaiPmhService) -> None:
        token_obj = OaiResumptionToken(
            cursor=100,
            last_id=500,
            last_created_at="2026-09-01T10:00:00Z",
            metadata_prefix="oai_dc",
            set_spec=None,
            from_date=None,
            until_date=None,
        )
        token_str = service.encode_resumption_token(token_obj)
        assert isinstance(token_str, str)
        assert len(token_str) > 0

        decoded = service.decode_resumption_token(token_str)
        assert decoded.cursor == 100
        assert decoded.last_id == 500
        assert decoded.last_created_at == "2026-09-01T10:00:00Z"
        assert decoded.metadata_prefix == "oai_dc"

    @pytest.mark.unit
    def test_tampered_resumption_token_fails(self, service: OaiPmhService) -> None:
        valid_token = service.encode_resumption_token(
            OaiResumptionToken(
                cursor=100,
                last_id=500,
                last_created_at="2026-09-01T10:00:00Z",
                metadata_prefix="oai_dc",
                set_spec=None,
                from_date=None,
                until_date=None,
            )
        )
        tampered = valid_token[:-4] + "XXXX"
        with pytest.raises(OaiPmhError) as exc_info:
            service.decode_resumption_token(tampered)
        assert exc_info.value.code == OaiPmhErrorCode.BAD_RESUMPTION_TOKEN


# ============================================================================
# Public Registry Check
# ============================================================================


class TestPublicRegistryOaiPmh:
    @pytest.mark.unit
    def test_oai_pmh_path_is_public(self) -> None:
        path = "/default/foundation/oai-pmh"
        assert PublicEndpointRegistry.is_public(path) is True
