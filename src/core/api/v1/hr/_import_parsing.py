"""Gedeelde bestand-parsing voor de hr-import-endpoints (BE-AGT-060, Fase 3 dag 3).

Bewust met een `_`-prefix: interne helper voor de twee import-routers in dit domein, geen
publiek onderdeel van het `hr`-domein.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Callable, Mapping, Sequence
from typing import TypeVar

from fastapi import UploadFile
from pydantic import BaseModel, ValidationError as PydanticValidationError

from src.core.exceptions.exceptions import ValidationError
from src.core.repositories.hr_import_types import ImportRowError

from .schemas import MAX_IMPORT_ROWS, ImportRowErrorResponse

#: 5 MiB -- een bestand van MAX_IMPORT_ROWS (500) rijen past hier ruim binnen.
MAX_UPLOAD_BYTES = 5 * 1024 * 1024

_CSV_CONTENT_TYPES = {"text/csv", "application/vnd.ms-excel", "application/csv"}
_JSON_CONTENT_TYPES = {"application/json"}

_SchemaT = TypeVar("_SchemaT", bound=BaseModel)
_RowT = TypeVar("_RowT")


async def read_upload(file: UploadFile) -> bytes:
    """Leest een upload met een harde bovengrens -- geen onbegrensde `await file.read()`."""
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValidationError(
            f"Bestand is groter dan {MAX_UPLOAD_BYTES} bytes", error_code="FILE_TOO_LARGE"
        )
    return content


def parse_import_file(
    content: bytes, content_type: str | None
) -> tuple[Sequence[Mapping[str, object]], int]:
    """Zet ruwe bestand-bytes om in een lijst rijen (dicts), CSV of JSON.

    `Sequence[Mapping[str, object]]`, niet `list[dict[str, Any]]`: een CSV-rij is
    `dict[str, str]`, een JSON-rij kan elke waarde bevatten -- `object` is hier het eerlijke
    type (de waarden worden nooit rechtstreeks gebruikt, alleen doorgegeven aan Pydantic's
    `model_validate`, die `Any` accepteert). `Sequence`/`Mapping` (covariant) i.p.v.
    `list`/`dict` (invariant) is nodig omdat de CSV-tak concreter is dan de JSON-tak en beide
    anders niet naar dezelfde returntype zouden passen (code-review BE-AGT-060 dag 3 na-
    verificatie: `Any` hier gaf een `[unused-ignore]`-fout omdat mypy er zelf niets op te
    melden had -- de Any-gate wilde alleen een acknowledgement, geen echte mypy-fout).

    Gooit `ValidationError` (400) op elke STRUCTURELE fout (onleesbaar bestand, onbekend
    content-type, 0 rijen, of meer dan `MAX_IMPORT_ROWS`) -- dat treft de hele aanvraag, in
    tegenstelling tot een individuele-rij-fout die de repository-laag als `row_errors`
    rapporteert zonder de rest van de batch te blokkeren.

    Retourneert (rijen, row_offset). `row_offset` is het 1-based bestandsrijnummer van de
    EERSTE datarij, zoals een gebruiker het in Excel ziet: 2 voor CSV (rij 1 is de header die
    `csv.DictReader` al heeft verbruikt voor dit hier draait), 1 voor JSON (geen headerregel).
    Zonder dit was elk gerapporteerde `row_index` voor een CSV-upload een-op-een te laag t.o.v.
    het sprint-plan's eigen contract (code-review BE-AGT-060 dag 3, finding 1).
    """
    normalized_type = (content_type or "").split(";")[0].strip().lower()

    if normalized_type in _JSON_CONTENT_TYPES:
        try:
            parsed = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
            # RecursionError: diep-genest JSON (bv. duizenden geneste arrays) laat json.loads
            # niet netjes falen met JSONDecodeError maar met RecursionError -- empirisch
            # bevestigd, geen aanname (security-review BE-AGT-060 dag 3, finding 3).
            raise ValidationError(f"Kon het JSON-bestand niet lezen: {exc}") from exc
        if not isinstance(parsed, list):
            raise ValidationError("JSON-bestand moet een array van objecten zijn")
        rows = parsed
        row_offset = 1
    elif normalized_type in _CSV_CONTENT_TYPES or normalized_type == "":
        try:
            text = content.decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(text))
            rows = list(reader)
        except (UnicodeDecodeError, csv.Error) as exc:
            # csv.Error: een enkel veld voorbij Python's ingebouwde field_size_limit (128 KiB)
            # laat list(reader) falen, ook ver onder MAX_UPLOAD_BYTES -- empirisch bevestigd.
            raise ValidationError(f"Kon het CSV-bestand niet lezen: {exc}") from exc
        row_offset = 2
    else:
        raise ValidationError(
            f"Onbekend bestandstype: {content_type!r}. Gebruik CSV of JSON.",
            error_code="UNSUPPORTED_FILE_TYPE",
        )

    if len(rows) == 0:
        raise ValidationError("Het bestand bevat geen rijen")
    if len(rows) > MAX_IMPORT_ROWS:
        raise ValidationError(
            f"Het bestand heeft {len(rows)} rijen, maximaal {MAX_IMPORT_ROWS} per import -- "
            "splits het bestand in kleinere batches",
            error_code="TOO_MANY_ROWS",
        )
    return rows, row_offset


def validate_rows(
    raw_rows: Sequence[Mapping[str, object]],
    schema_cls: type[_SchemaT],
    to_row: Callable[[_SchemaT], _RowT],
    row_offset: int = 1,
) -> tuple[list[_RowT], list[int], list[ImportRowErrorResponse]]:
    """Valideert elke ruwe rij tegen `schema_cls`, bouwt er met `to_row` een repository-
    dataclass van.

    `row_offset` is het bestandsrijnummer van `raw_rows[0]` (zie `parse_import_file`) -- 2 voor
    CSV, 1 voor JSON.

    Retourneert (geldige rijen, hun ORIGINELE bestandsrijnummer, validatiefouten). De
    repository krijgt straks ALLEEN de geldige rijen -- zijn eigen `row_errors` tellen dan
    vanaf 1 over die GEFILTERDE lijst, niet over het oorspronkelijke bestand. `remap_
    repository_errors` hieronder zet dat 1-based positie-in-de-gefilterde-lijst-cijfer terug
    om naar het bestandsrijnummer via de tweede returnwaarde hier.
    """
    valid_rows: list[_RowT] = []
    original_indices: list[int] = []
    errors: list[ImportRowErrorResponse] = []

    for index, raw_row in enumerate(raw_rows, start=row_offset):
        try:
            validated = schema_cls.model_validate(raw_row)
        except PydanticValidationError as exc:
            first_error = exc.errors()[0]
            field = ".".join(str(part) for part in first_error.get("loc", ()))
            errors.append(
                ImportRowErrorResponse(
                    row_index=index, message=f"{field}: {first_error.get('msg', str(exc))}"
                )
            )
            continue
        valid_rows.append(to_row(validated))
        original_indices.append(index)

    return valid_rows, original_indices, errors


def remap_repository_errors(
    repo_errors: list[ImportRowError], original_indices: list[int]
) -> list[ImportRowErrorResponse]:
    """Zet de repository's `row_errors` (1-based over de GEFILTERDE rijenlijst) terug om naar
    het bestandsrijnummer via `original_indices` (positie i in de gefilterde lijst hoort bij
    `original_indices[i]` in het oorspronkelijke bestand)."""
    return [
        ImportRowErrorResponse(
            row_index=original_indices[error.row_index - 1], message=error.message
        )
        for error in repo_errors
    ]
