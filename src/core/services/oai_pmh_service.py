"""OAI-PMH metadata harvesting service and XML builder (BE-EP-040, ADR-029).

Implements Open Archives Initiative Protocol for Metadata Harvesting (OAI-PMH) v2.0:
- XML responses conforming to http://www.openarchives.org/OAI/2.0/OAI-PMH.xsd
- Dublin Core metadata container (oai_dc)
- Strict parameter validation (exclusivity of resumptionToken, granularity matching)
- Keyset-based resumptionToken with HMAC tampering protection
- XML 1.0 Unicode sanitization (stripping illegal ASCII control chars)
- Soft-deleted items emitted as <header status="deleted">
- Anonymity masking (BE-EP-038)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, cast

from src.core.shared.datetime_utils import to_utc, utc_now

OAI_NAMESPACE = "http://www.openarchives.org/OAI/2.0/"
OAI_DC_NAMESPACE = "http://www.openarchives.org/OAI/2.0/oai_dc/"
DC_NAMESPACE = "http://purl.org/dc/elements/1.1/"
XSI_NAMESPACE = "http://www.w3.org/2001/XMLSchema-instance"

OAI_SCHEMA_LOCATION = (
    "http://www.openarchives.org/OAI/2.0/ "
    "http://www.openarchives.org/OAI/2.0/OAI-PMH.xsd"
)
OAI_DC_SCHEMA_LOCATION = (
    "http://www.openarchives.org/OAI/2.0/oai_dc/ "
    "http://www.openarchives.org/OAI/2.0/oai_dc.xsd"
)

# XML 1.0 illegal control characters regex:
# Allowed: \t (0x09), \n (0x0A), \r (0x0D), 0x20-0xD7FF, 0xE000-0xFFFD
_ILLEGAL_XML_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# ISO 8601 regex for day (YYYY-MM-DD) and seconds (YYYY-MM-DDThh:mm:ssZ)
_DATE_DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATE_SEC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

PAGE_SIZE = 100
TOKEN_TTL_SECONDS = 86_400  # 24 hours


class OaiPmhErrorCode(str, Enum):
    BAD_VERB = "badVerb"
    BAD_ARGUMENT = "badArgument"
    CANNOT_DISSEMINATE_FORMAT = "cannotDisseminateFormat"
    ID_DOES_NOT_EXIST = "idDoesNotExist"
    NO_RECORDS_MATCH = "noRecordsMatch"
    BAD_RESUMPTION_TOKEN = "badResumptionToken"
    NO_SET_HIERARCHY = "noSetHierarchy"
    NO_METADATA_FORMATS = "noMetadataFormats"


class OaiPmhError(Exception):
    def __init__(self, code: OaiPmhErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class OaiRecord:
    identifier: str
    datestamp: str
    title: str
    creator: str | None
    description: str | None
    date_recorded: str | None
    content_type: str | None
    rights: str | None
    location_name: str | None
    is_anonymous: bool
    is_deleted: bool
    set_specs: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class OaiResumptionToken:
    cursor: int
    last_id: int
    last_created_at: str
    metadata_prefix: str
    set_spec: str | None = None
    from_date: str | None = None
    until_date: str | None = None
    complete_list_size: int | None = None
    expires_at: int | None = None


def sanitize_for_xml(text: str | None) -> str:
    """Remove characters prohibited by the XML 1.0 specification."""
    if not text:
        return ""
    return _ILLEGAL_XML_CHARS_RE.sub("", text)


def validate_oai_parameters(params: dict[str, str]) -> OaiPmhError | None:
    """Validate OAI-PMH request parameters strictly according to v2.0 specification."""
    verb = params.get("verb")
    if not verb:
        return OaiPmhError(
            OaiPmhErrorCode.BAD_VERB,
            "Missing required verb argument.",
        )

    valid_verbs = {
        "Identify",
        "ListMetadataFormats",
        "ListSets",
        "GetRecord",
        "ListIdentifiers",
        "ListRecords",
    }
    if verb not in valid_verbs:
        return OaiPmhError(
            OaiPmhErrorCode.BAD_VERB,
            f"Value '{verb}' is not a valid OAI-PMH verb.",
        )

    # Check resumptionToken exclusivity (Section 3.5)
    resumption_token = params.get("resumptionToken")
    if resumption_token is not None:
        other_params = {k: v for k, v in params.items() if k not in ("verb", "resumptionToken")}
        if other_params:
            return OaiPmhError(
                OaiPmhErrorCode.BAD_ARGUMENT,
                "resumptionToken is an exclusive argument and cannot be combined with other parameters.",
            )
        return None

    # Allowed argument lists per verb
    allowed_args_per_verb = {
        "Identify": {"verb"},
        "ListMetadataFormats": {"verb", "identifier"},
        "ListSets": {"verb", "resumptionToken"},
        "GetRecord": {"verb", "identifier", "metadataPrefix"},
        "ListIdentifiers": {"verb", "metadataPrefix", "from", "until", "set", "resumptionToken"},
        "ListRecords": {"verb", "metadataPrefix", "from", "until", "set", "resumptionToken"},
    }

    allowed = allowed_args_per_verb[verb]
    for key in params:
        if key not in allowed:
            return OaiPmhError(
                OaiPmhErrorCode.BAD_ARGUMENT,
                f"Unexpected argument '{key}' for verb '{verb}'.",
            )

    # Verb-specific required parameters
    if verb == "GetRecord":
        if not params.get("identifier"):
            return OaiPmhError(OaiPmhErrorCode.BAD_ARGUMENT, "Missing required argument: identifier.")
        if not params.get("metadataPrefix"):
            return OaiPmhError(OaiPmhErrorCode.BAD_ARGUMENT, "Missing required argument: metadataPrefix.")

    if verb in ("ListIdentifiers", "ListRecords") and resumption_token is None:
        if not params.get("metadataPrefix"):
            return OaiPmhError(OaiPmhErrorCode.BAD_ARGUMENT, "Missing required argument: metadataPrefix.")

    # Check metadataPrefix value
    metadata_prefix = params.get("metadataPrefix")
    if metadata_prefix and metadata_prefix != "oai_dc":
        return OaiPmhError(
            OaiPmhErrorCode.CANNOT_DISSEMINATE_FORMAT,
            f"Unsupported metadataPrefix '{metadata_prefix}'. Only 'oai_dc' is supported.",
        )

    # Check datestamp granularities (Section 3.3.1)
    from_date = params.get("from")
    until_date = params.get("until")

    from_is_day = bool(from_date and _DATE_DAY_RE.match(from_date))
    from_is_sec = bool(from_date and _DATE_SEC_RE.match(from_date))
    until_is_day = bool(until_date and _DATE_DAY_RE.match(until_date))
    until_is_sec = bool(until_date and _DATE_SEC_RE.match(until_date))

    if from_date and not (from_is_day or from_is_sec):
        return OaiPmhError(OaiPmhErrorCode.BAD_ARGUMENT, "Invalid 'from' datestamp syntax.")

    if until_date and not (until_is_day or until_is_sec):
        return OaiPmhError(OaiPmhErrorCode.BAD_ARGUMENT, "Invalid 'until' datestamp syntax.")

    if from_date and until_date:
        if (from_is_day != until_is_day) or (from_is_sec != until_is_sec):
            return OaiPmhError(
                OaiPmhErrorCode.BAD_ARGUMENT,
                "Arguments 'from' and 'until' must have the same granularity.",
            )
        # Parse comparison
        from_dt = _parse_oai_datestamp(from_date)
        until_dt = _parse_oai_datestamp(until_date)
        if from_dt and until_dt and from_dt > until_dt:
            return OaiPmhError(
                OaiPmhErrorCode.BAD_ARGUMENT,
                "'from' datestamp must be earlier than or equal to 'until' datestamp.",
            )

    return None


def _parse_oai_datestamp(datestr: str) -> datetime | None:
    try:
        if _DATE_DAY_RE.match(datestr):
            return datetime.strptime(datestr, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if _DATE_SEC_RE.match(datestr):
            return datetime.strptime(datestr, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    return None


class OaiPmhService:
    """Builder for OAI-PMH v2.0 XML responses."""

    def __init__(self, base_url: str, secret_key: str | None = None) -> None:
        self.base_url = base_url
        self._secret = (
            secret_key or os.getenv("JWT_SECRET_KEY") or "oai_pmh_default_secret_key"
        ).encode("utf-8")

    def _create_root(
        self,
        verb: str | None = None,
        params: dict[str, str] | None = None,
    ) -> ET.Element:
        root = ET.Element(
            f"{{{OAI_NAMESPACE}}}OAI-PMH",
            {
                f"{{{XSI_NAMESPACE}}}schemaLocation": OAI_SCHEMA_LOCATION,
            },
        )
        # Register prefixes for pretty/standard namespace output
        ET.register_namespace("", OAI_NAMESPACE)
        ET.register_namespace("xsi", XSI_NAMESPACE)
        ET.register_namespace("oai_dc", OAI_DC_NAMESPACE)
        ET.register_namespace("dc", DC_NAMESPACE)

        # responseDate: current UTC timestamp
        resp_date = ET.SubElement(root, f"{{{OAI_NAMESPACE}}}responseDate")
        resp_date.text = utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")

        # request element
        req_attrs: dict[str, str] = {}
        if verb:
            req_attrs["verb"] = verb
        if params:
            for k, v in params.items():
                if k != "verb" and v:
                    req_attrs[k] = v

        request_el = ET.SubElement(root, f"{{{OAI_NAMESPACE}}}request", req_attrs)
        request_el.text = self.base_url
        return root

    def _render_xml(self, root: ET.Element) -> bytes:
        raw = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        return cast(bytes, raw)

    def encode_resumption_token(self, token: OaiResumptionToken) -> str:
        """Encode a resumption token into a signed URL-safe base64 string."""
        now_ts = int(utc_now().timestamp())
        expires = token.expires_at or (now_ts + TOKEN_TTL_SECONDS)
        payload = {
            "c": token.cursor,
            "id": token.last_id,
            "t": token.last_created_at,
            "mp": token.metadata_prefix,
            "s": token.set_spec,
            "f": token.from_date,
            "u": token.until_date,
            "cls": token.complete_list_size,
            "exp": expires,
        }
        json_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        sig = hmac.new(self._secret, json_bytes, hashlib.sha256).digest()[:16]
        packed = sig + json_bytes
        return base64.urlsafe_b64encode(packed).decode("ascii").rstrip("=")

    def decode_resumption_token(self, token_str: str) -> OaiResumptionToken:
        """Decode and verify a resumption token."""
        pad = len(token_str) % 4
        if pad:
            token_str += "=" * (4 - pad)
        try:
            raw = base64.urlsafe_b64decode(token_str.encode("ascii"))
            if len(raw) < 17:
                raise ValueError("Token too short")
            sig, json_bytes = raw[:16], raw[16:]
            expected_sig = hmac.new(self._secret, json_bytes, hashlib.sha256).digest()[:16]
            if not hmac.compare_digest(sig, expected_sig):
                raise ValueError("Invalid signature")

            data = json.loads(json_bytes.decode("utf-8"))
            now_ts = int(utc_now().timestamp())
            if data.get("exp", 0) < now_ts:
                raise ValueError("Token expired")

            return OaiResumptionToken(
                cursor=int(data["c"]),
                last_id=int(data["id"]),
                last_created_at=str(data["t"]),
                metadata_prefix=str(data["mp"]),
                set_spec=data.get("s"),
                from_date=data.get("f"),
                until_date=data.get("u"),
                complete_list_size=data.get("cls"),
                expires_at=data.get("exp"),
            )
        except Exception as exc:
            raise OaiPmhError(
                OaiPmhErrorCode.BAD_RESUMPTION_TOKEN,
                f"The resumptionToken is invalid or expired: {exc}",
            ) from exc

    def build_identify_response(
        self,
        repository_name: str,
        admin_email: str,
        earliest_datestamp: str,
    ) -> bytes:
        root = self._create_root(verb="Identify")
        identify_el = ET.SubElement(root, f"{{{OAI_NAMESPACE}}}Identify")

        ET.SubElement(identify_el, f"{{{OAI_NAMESPACE}}}repositoryName").text = sanitize_for_xml(
            repository_name
        )
        ET.SubElement(identify_el, f"{{{OAI_NAMESPACE}}}baseURL").text = self.base_url
        ET.SubElement(identify_el, f"{{{OAI_NAMESPACE}}}protocolVersion").text = "2.0"
        ET.SubElement(identify_el, f"{{{OAI_NAMESPACE}}}adminEmail").text = sanitize_for_xml(
            admin_email
        )
        ET.SubElement(identify_el, f"{{{OAI_NAMESPACE}}}earliestDatestamp").text = (
            earliest_datestamp
        )
        ET.SubElement(identify_el, f"{{{OAI_NAMESPACE}}}deletedRecord").text = "transient"
        ET.SubElement(identify_el, f"{{{OAI_NAMESPACE}}}granularity").text = (
            "YYYY-MM-DDThh:mm:ssZ"
        )
        return self._render_xml(root)

    def build_list_metadata_formats_response(
        self,
        identifier: str | None = None,
    ) -> bytes:
        params = {"identifier": identifier} if identifier else None
        root = self._create_root(verb="ListMetadataFormats", params=params)
        list_el = ET.SubElement(root, f"{{{OAI_NAMESPACE}}}ListMetadataFormats")

        fmt = ET.SubElement(list_el, f"{{{OAI_NAMESPACE}}}metadataFormat")
        ET.SubElement(fmt, f"{{{OAI_NAMESPACE}}}metadataPrefix").text = "oai_dc"
        ET.SubElement(fmt, f"{{{OAI_NAMESPACE}}}schema").text = (
            "http://www.openarchives.org/OAI/2.0/oai_dc.xsd"
        )
        ET.SubElement(fmt, f"{{{OAI_NAMESPACE}}}metadataNamespace").text = OAI_DC_NAMESPACE
        return self._render_xml(root)

    def build_list_sets_response(self) -> bytes:
        root = self._create_root(verb="ListSets")
        list_el = ET.SubElement(root, f"{{{OAI_NAMESPACE}}}ListSets")

        sets = [
            ("story", "Verhalen"),
            ("audio", "Geluidsopnamen"),
            ("video", "Video's"),
            ("photo", "Fotografie"),
            ("document", "Documenten"),
        ]
        for spec, name in sets:
            set_el = ET.SubElement(list_el, f"{{{OAI_NAMESPACE}}}set")
            ET.SubElement(set_el, f"{{{OAI_NAMESPACE}}}setSpec").text = spec
            ET.SubElement(set_el, f"{{{OAI_NAMESPACE}}}setName").text = name

        return self._render_xml(root)

    def _append_record_element(self, parent: ET.Element, record: OaiRecord) -> None:
        rec_el = ET.SubElement(parent, f"{{{OAI_NAMESPACE}}}record")

        # <header>
        header_attrs: dict[str, str] = {}
        if record.is_deleted:
            header_attrs["status"] = "deleted"

        header_el = ET.SubElement(rec_el, f"{{{OAI_NAMESPACE}}}header", header_attrs)
        ET.SubElement(header_el, f"{{{OAI_NAMESPACE}}}identifier").text = record.identifier
        ET.SubElement(header_el, f"{{{OAI_NAMESPACE}}}datestamp").text = record.datestamp
        for s in record.set_specs:
            ET.SubElement(header_el, f"{{{OAI_NAMESPACE}}}setSpec").text = s

        # If deleted, no metadata block per OAI-PMH v2.0
        if record.is_deleted:
            return

        # <metadata>
        metadata_el = ET.SubElement(rec_el, f"{{{OAI_NAMESPACE}}}metadata")
        dc_el = ET.SubElement(
            metadata_el,
            f"{{{OAI_DC_NAMESPACE}}}dc",
            {f"{{{XSI_NAMESPACE}}}schemaLocation": OAI_DC_SCHEMA_LOCATION},
        )

        # Dublin Core fields
        ET.SubElement(dc_el, f"{{{DC_NAMESPACE}}}title").text = sanitize_for_xml(record.title)

        # Anonymity masking (BE-EP-038)
        if not record.is_anonymous and record.creator:
            ET.SubElement(dc_el, f"{{{DC_NAMESPACE}}}creator").text = sanitize_for_xml(
                record.creator
            )

        if record.description:
            ET.SubElement(dc_el, f"{{{DC_NAMESPACE}}}description").text = sanitize_for_xml(
                record.description
            )
        if record.date_recorded:
            ET.SubElement(dc_el, f"{{{DC_NAMESPACE}}}date").text = sanitize_for_xml(
                record.date_recorded
            )
        if record.content_type:
            ET.SubElement(dc_el, f"{{{DC_NAMESPACE}}}type").text = sanitize_for_xml(
                record.content_type
            )
        if record.identifier:
            ET.SubElement(dc_el, f"{{{DC_NAMESPACE}}}identifier").text = record.identifier
        if record.rights:
            ET.SubElement(dc_el, f"{{{DC_NAMESPACE}}}rights").text = sanitize_for_xml(
                record.rights
            )
        if record.location_name:
            ET.SubElement(dc_el, f"{{{DC_NAMESPACE}}}coverage").text = sanitize_for_xml(
                record.location_name
            )

        ET.SubElement(dc_el, f"{{{DC_NAMESPACE}}}language").text = "nl"

    def build_get_record_response(self, record: OaiRecord) -> bytes:
        root = self._create_root(
            verb="GetRecord",
            params={"identifier": record.identifier, "metadataPrefix": "oai_dc"},
        )
        get_rec_el = ET.SubElement(root, f"{{{OAI_NAMESPACE}}}GetRecord")
        self._append_record_element(get_rec_el, record)
        return self._render_xml(root)

    def build_list_identifiers_response(
        self,
        records: list[OaiRecord],
        params: dict[str, str],
        resumption_token_str: str | None = None,
        complete_list_size: int | None = None,
        cursor: int | None = None,
    ) -> bytes:
        root = self._create_root(verb="ListIdentifiers", params=params)
        list_el = ET.SubElement(root, f"{{{OAI_NAMESPACE}}}ListIdentifiers")

        for r in records:
            header_attrs: dict[str, str] = {}
            if r.is_deleted:
                header_attrs["status"] = "deleted"
            header_el = ET.SubElement(list_el, f"{{{OAI_NAMESPACE}}}header", header_attrs)
            ET.SubElement(header_el, f"{{{OAI_NAMESPACE}}}identifier").text = r.identifier
            ET.SubElement(header_el, f"{{{OAI_NAMESPACE}}}datestamp").text = r.datestamp
            for s in r.set_specs:
                ET.SubElement(header_el, f"{{{OAI_NAMESPACE}}}setSpec").text = s

        if resumption_token_str is not None:
            token_attrs: dict[str, str] = {}
            if complete_list_size is not None:
                token_attrs["completeListSize"] = str(complete_list_size)
            if cursor is not None:
                token_attrs["cursor"] = str(cursor)
            token_el = ET.SubElement(list_el, f"{{{OAI_NAMESPACE}}}resumptionToken", token_attrs)
            token_el.text = resumption_token_str

        return self._render_xml(root)

    def build_list_records_response(
        self,
        records: list[OaiRecord],
        params: dict[str, str],
        resumption_token_str: str | None = None,
        complete_list_size: int | None = None,
        cursor: int | None = None,
    ) -> bytes:
        root = self._create_root(verb="ListRecords", params=params)
        list_el = ET.SubElement(root, f"{{{OAI_NAMESPACE}}}ListRecords")

        for r in records:
            self._append_record_element(list_el, r)

        if resumption_token_str is not None:
            token_attrs: dict[str, str] = {}
            if complete_list_size is not None:
                token_attrs["completeListSize"] = str(complete_list_size)
            if cursor is not None:
                token_attrs["cursor"] = str(cursor)
            token_el = ET.SubElement(list_el, f"{{{OAI_NAMESPACE}}}resumptionToken", token_attrs)
            token_el.text = resumption_token_str

        return self._render_xml(root)

    def build_error_response(
        self,
        error: OaiPmhError,
        params: dict[str, str] | None = None,
    ) -> bytes:
        verb = params.get("verb") if params else None
        root = self._create_root(verb=verb, params=params)
        err_el = ET.SubElement(
            root,
            f"{{{OAI_NAMESPACE}}}error",
            {"code": error.code.value},
        )
        err_el.text = sanitize_for_xml(error.message)
        return self._render_xml(root)
