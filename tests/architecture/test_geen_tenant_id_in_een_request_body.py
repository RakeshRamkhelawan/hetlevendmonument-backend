"""`tenant_id` komt nooit uit een request body -- repo-breed (ADR-036 OP-259).

CLAUDE.md NOOIT-lijst: "NOOIT tenant_id uit request body accepteren".

WAT HIER MIS WAS
----------------
Deze regel staat bovenaan de NOOIT-lijst, maar werd op 2026-09-18 door precies twee dingen
bewaakt, en allebei keken ze de verkeerde kant op:

1. `tests/architecture/test_webhook_payload_no_tenant_id.py` toetste EEN klasse
   (`WebhookPayload`) in EEN bestand (`src/core/activepieces/schemas.py`). Die klasse had
   nul importeurs. De guard stond groen en bewaakte een dode klasse.
2. De CI-stap "NOOIT-lijst: tenant-id-in-body gate" in `ci-feature.yml` scande
   `src/api/`, `src/routers/` en `src/schemas/`. Gemeten: de laatste twee BESTAAN NIET en
   `src/api/` bevat drie bestanden. De werkelijke API staat in `src/core/api/` --
   honderden bestanden, nooit gescand. De stap meldde dus altijd groen. Daar kwam bij dat
   CI sinds het opzeggen van het GitHub-abonnement helemaal niet meer draait.

Gevonden met deze scan: `ExecutionEvent` in
`src/core/api/webhooks/activepieces_handler.py` droeg een `tenant_id`-veld en stond als
request body op twee webhook-endpoints. Het werd niet VERTROUWD -- de klant kwam uit de
opgeslagen flow -- maar het veld werd wel geaccepteerd en in drie logregels gebruikt.
Verwijderd in dezelfde commit als deze guard.

HOE DEZE GUARD REQUEST VAN RESPONSE ONDERSCHEIDT
------------------------------------------------
Een Pydantic-model met `tenant_id` is pas een overtreding als het als REQUEST BODY wordt
gebruikt: als parameter-annotatie in een functie met een `@router.post/put/patch/delete`
-decorator, ZONDER een `Depends()`, `Query()`, `Path()`, `Header()`, `Cookie()`, `Form()`,
`File()` of `Security()` als default. Response-modellen mogen `tenant_id` gewoon hebben en
worden dus niet geteld.

Dat onderscheid is niet cosmetisch. De eerste versie van deze scan telde elke parameter mee
en kwam op 276 "schendingen" -- vrijwel allemaal `current_user: UserResponse`, een
dependency. Met de uitsluiting blijven er 2 over, en die waren echt. Een getal van 276 had
niemand serieus genomen; dat is hoe een guard nutteloos wordt zonder fout te zijn.

MUTATIEBEWIJS (2026-09-18, beide richtingen, een regel per bewaakt element)
--------------------------------------------------------------------------
    `tenant_id` terug in `ExecutionEvent` (request body van een POST)   -> ROOD
    `tenant_id` in een NIEUW model dat als POST-body dient              -> ROOD
    datzelfde model als `Depends()`-parameter                           -> GROEN
    datzelfde model als `response_model` / returnwaarde                 -> GROEN
    ongemuteerd                                                         -> GROEN
"""

from __future__ import annotations

import ast
from pathlib import Path

_WORTEL = Path(__file__).resolve().parents[2]
_BRON = _WORTEL / "src"

#: Methoden die een request body kunnen dragen.
_BODY_METHODEN = frozenset({"post", "put", "patch", "delete"})

#: Defaults die aangeven dat een parameter GEEN request body is.
_GEEN_BODY = frozenset({"Depends", "Query", "Path", "Header", "Cookie", "Form", "File", "Security"})

#: Gedateerde uitzonderingen, met een reden PER regel. Leeg op 2026-09-18.
KNOWN_TENANT_ID_IN_BODY: dict[str, str] = {}


def _naam_van(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Subscript):
        return _naam_van(node.value)
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _bomen() -> dict[Path, ast.Module]:
    bomen: dict[Path, ast.Module] = {}
    for pad in _BRON.rglob("*.py"):
        if pad.relative_to(_WORTEL).as_posix().startswith("src/alembic"):
            continue
        try:
            # utf-8-sig: `api/domain_packs.py` begint met een BOM.
            bomen[pad] = ast.parse(pad.read_text(encoding="utf-8-sig"))
        except (SyntaxError, UnicodeDecodeError):
            continue
    return bomen


def _modellen_met_tenant_id(bomen: dict[Path, ast.Module]) -> dict[str, str]:
    """{klassenaam: bestand:regel} voor elk BaseModel met een `tenant_id`-veld."""
    gevonden: dict[str, str] = {}
    for pad, boom in bomen.items():
        for knoop in ast.walk(boom):
            if not isinstance(knoop, ast.ClassDef):
                continue
            basen = {
                b.id if isinstance(b, ast.Name) else getattr(b, "attr", "") for b in knoop.bases
            }
            if "BaseModel" not in basen:
                continue
            for stmt in knoop.body:
                if (
                    isinstance(stmt, ast.AnnAssign)
                    and isinstance(stmt.target, ast.Name)
                    and stmt.target.id == "tenant_id"
                ):
                    gevonden[knoop.name] = f"{pad.relative_to(_WORTEL).as_posix()}:{stmt.lineno}"
    return gevonden


def _schendingen() -> dict[str, str]:
    """{bestand:regel functie(param: Model): reden} voor elke tenant_id in een request body."""
    bomen = _bomen()
    modellen = _modellen_met_tenant_id(bomen)
    gevonden: dict[str, str] = {}

    for pad, boom in bomen.items():
        for knoop in ast.walk(boom):
            if not isinstance(knoop, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            methoden: set[str] = set()
            for decorator in knoop.decorator_list:
                doel = decorator.func if isinstance(decorator, ast.Call) else decorator
                if isinstance(doel, ast.Attribute):
                    methoden.add(doel.attr)
            if not (methoden & _BODY_METHODEN):
                continue

            argumenten = list(knoop.args.args) + list(knoop.args.kwonlyargs)
            defaults: list[ast.expr | None] = (
                [None] * (len(knoop.args.args) - len(knoop.args.defaults))
                + list(knoop.args.defaults)
                + list(knoop.args.kw_defaults)
            )
            for argument, default in zip(argumenten, defaults):
                if argument.annotation is None:
                    continue
                model = _naam_van(argument.annotation)
                if model not in modellen:
                    continue
                if isinstance(default, ast.Call):
                    functie = default.func
                    naam = (
                        functie.id
                        if isinstance(functie, ast.Name)
                        else getattr(functie, "attr", "")
                    )
                    if naam in _GEEN_BODY:
                        continue
                # `Annotated[X, Depends(...)]` is evenmin een body.
                if (
                    isinstance(argument.annotation, ast.Subscript)
                    and _naam_van(argument.annotation.value) == "Annotated"
                ):
                    gedumpt = ast.dump(argument.annotation)
                    if any(n in gedumpt for n in _GEEN_BODY):
                        continue
                sleutel = (
                    f"{pad.relative_to(_WORTEL).as_posix()}:{knoop.lineno} "
                    f"{knoop.name}({argument.arg}: {model})"
                )
                gevonden[sleutel] = f"model gedefinieerd op {modellen[model]}"
    return gevonden


def test_geen_tenant_id_in_een_request_body() -> None:
    """De NOOIT-regel, repo-breed en over de ECHTE API-map."""
    gevonden = _schendingen()
    nieuw = {k: v for k, v in gevonden.items() if k not in KNOWN_TENANT_ID_IN_BODY}

    assert not nieuw, (
        "Deze endpoints accepteren `tenant_id` in hun REQUEST BODY, wat CLAUDE.md "
        f"verbiedt: {nieuw}. De tenant hoort uit de JWT-claim te komen (ADR-003), en bij "
        "een webhook uit de eigenaar van de resource in de database -- nooit uit de payload."
    )


def test_de_uitzonderingen_zijn_niet_verouderd() -> None:
    """Een uitzondering die is opgelost MOET uit de lijst."""
    gevonden = _schendingen()
    verdwenen = [k for k in KNOWN_TENANT_ID_IN_BODY if k not in gevonden]

    assert not verdwenen, f"Niet langer een schending, haal uit de lijst: {verdwenen}"


def test_de_scan_vindt_uberhaupt_modellen_en_endpoints() -> None:
    """Zonder deze helft is een kapotte scan niet van een schone repo te onderscheiden.

    Dit is de tegenrichting van deze guard: hij kan groen staan omdat er niets mis is, of
    omdat hij niets ziet. Alleen het tweede is een defect, en alleen deze test merkt het.
    """
    bomen = _bomen()
    assert len(bomen) > 500, f"slechts {len(bomen)} bronbestanden gelezen -- scan is stuk"

    modellen = _modellen_met_tenant_id(bomen)
    assert len(modellen) > 20, (
        f"slechts {len(modellen)} modellen met tenant_id gevonden. Response-modellen mogen "
        "dat veld hebben en er zijn er tientallen; vindt de scan er bijna geen, dan werkt "
        "de klasse-detectie niet meer."
    )
