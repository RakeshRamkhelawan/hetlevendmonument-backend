"""Er is EEN toegangsweg naar ActivePieces: `src/core/activepieces/` (ADR-040 B6).

Brief 2026-10-20 (ActivePieces per klant, dag 1).

**Wat er stond.** Naast `ActivePiecesClient` las `src/core/api/v1/focus_builder/agents.py` en
`src/core/services/focus_builder_service.py` zelf de algemene AP-URL uit de config, bouwde met een
eigen `httpx.AsyncClient` een verzoek, en zocht een sleutel (`activepieces_api_key`) die in de
config helemaal niet bestaat -- het verzoek ging dus ZONDER inlog. Een tweede pad naast de client
is een pad dat de verbinding per klant (B3) en de stappencontrole (wfb-dag1) omzeilt.

**Wat deze guard toetst.** Buiten `src/core/activepieces/` mag in `src/` geen code:

1. een AP-instelling uit de config lezen (`activepieces_api_url`, `_email`, `_password`,
   `_api_key`, `_pilot_*`), als attribuut of als tekst voor `getattr`; en
2. in een bestand dat `httpx`/`aiohttp`/`requests` importeert een URL naar `activepieces` of een
   omgevingsvariabele `ACTIVEPIECES_*`/`AP_SERVICE_*` als tekst gebruiken. Een logregel of omschrijving
   die het woord noemt telt niet: de eerste versie toetste het kale woord en gaf daarmee een
   handvol valse treffers in `focus_builder/service.py` en `openai_compatible.py`.

De unit van meten is de functie: de sleutel van de uitzonderingslijst is `bestand::functie`, niet
het bestand (zie quality-gates.md, aanscherping 2026-09-18). Docstrings tellen niet mee.

**Mutatiebewijs (2026-10-20), beide richtingen, een regel per element van de benoemde verzameling.**
De verzameling is `AP_CONFIGNAMEN` plus de AP-tekst in een http-bestand; elk element heeft een eigen
test hieronder met een tijdelijke bronboom (`tmp_path`), en de echte boom wordt niet gemuteerd:

- `test_een_config_instelling_buiten_het_pakket_wordt_betrapt[<naam>]`: een mutatie per naam in
  `AP_CONFIGNAMEN` (6x), als attribuut.
- `test_een_getattr_met_een_ap_instelling_wordt_betrapt`: dezelfde naam als tekst.
- `test_een_httpx_aanroep_naar_ap_buiten_het_pakket_wordt_betrapt`: het oorspronkelijke defect
  (httpx plus een AP-URL), voor httpx, aiohttp en requests.
- `test_dezelfde_aanroep_binnen_het_pakket_wordt_niet_betrapt`: de andere richting; zonder deze
  is "verbied alles" een geldige oplossing.
- `test_een_uitzondering_geldt_voor_een_functie_niet_voor_het_bestand`: een tweede functie in een
  bestand dat al op de lijst staat wordt wel betrapt (de valkuil van OP-258).
- `test_de_naam_in_een_docstring_telt_niet_mee`: de legitieme lezer van een toelichting.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TOEGESTAAN_PAKKET = "src/core/activepieces/"

AP_CONFIGNAMEN = (
    "activepieces_api_url",
    "activepieces_email",
    "activepieces_password",
    "activepieces_api_key",
    "activepieces_pilot_tenant_ids",
    "activepieces_pilot_project_id",
)
HTTP_MODULES = ("httpx", "aiohttp", "requests")

# Gedateerd (2026-10-20), met een reden per regel. De sleutel is bestand::functie.
KNOWN_BUITEN_HET_PAKKET: dict[str, str] = {
    "src/core/monitoring/health_checks.py::HealthChecker.check_focus_builder": (
        "Platformbrede bereikbaarheidsvraag (GET /health, zonder inlog, zonder tenantdata). "
        "Geen verbinding van een klant en geen pad naar flows of verbindingen."
    ),
    "src/core/config/unified_config.py::UnifiedConfig._inject_secrets_from_manager": (
        "De configuratiedefinitie zelf noemt de namen van de geheimen. Lezen doet alleen "
        "`ap_verbinding_voor`; dag 2 vervangt dit door de versleutelde opslag per klant."
    ),
}


def _docstring_knopen(boom: ast.AST) -> set[int]:
    """`id()` van elke Constant die de docstring is van een module, klasse of functie."""
    knopen: set[int] = set()
    for node in ast.walk(boom):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            eerste = node.body[0] if node.body else None
            if (
                isinstance(eerste, ast.Expr)
                and isinstance(eerste.value, ast.Constant)
                and isinstance(eerste.value.value, str)
            ):
                knopen.add(id(eerste.value))
    return knopen


def _wijst_naar_activepieces(tekst: str) -> bool:
    """Een URL of een omgevingsvariabele naar ActivePieces -- geen logregel of omschrijving."""
    klein = tekst.lower()
    if "activepieces" in klein and "://" in klein:
        return True
    return tekst.startswith(("ACTIVEPIECES_", "AP_SERVICE_"))


def _importeert_http(boom: ast.AST) -> bool:
    for node in ast.walk(boom):
        if isinstance(node, ast.Import):
            if any(alias.name.split(".")[0] in HTTP_MODULES for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] in HTTP_MODULES:
                return True
    return False


def _functie_overtredingen(boom: ast.Module) -> set[str]:
    """Qualnamen (`Klasse.methode`, `<module>`) van de plekken die de regel overtreden."""
    http = _importeert_http(boom)
    docstrings = _docstring_knopen(boom)
    gevonden: set[str] = set()

    def loop(node: ast.AST, pad: tuple[str, ...]) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            pad = (*pad, node.name)
        naam = ".".join(pad) if pad else "<module>"
        if isinstance(node, ast.Attribute) and node.attr in AP_CONFIGNAMEN:
            gevonden.add(naam)
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in docstrings:
                tekst = node.value
                if tekst in AP_CONFIGNAMEN:
                    gevonden.add(naam)
                elif http and _wijst_naar_activepieces(tekst):
                    gevonden.add(naam)
        for kind in ast.iter_child_nodes(node):
            loop(kind, pad)

    loop(boom, ())
    return gevonden


def vind_overtredingen(root: Path) -> set[str]:
    """`bestand::functie` voor elke overtreding onder `root/src`, buiten het toegestane pakket."""
    gevonden: set[str] = set()
    for pad in sorted((root / "src").rglob("*.py")):
        relatief = pad.relative_to(root).as_posix()
        if relatief.startswith(TOEGESTAAN_PAKKET):
            continue
        try:
            boom = ast.parse(pad.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for functie in _functie_overtredingen(boom):
            gevonden.add(f"{relatief}::{functie}")
    return gevonden


def _schrijf(root: Path, relatief: str, tekst: str) -> None:
    doel = root / relatief
    doel.parent.mkdir(parents=True, exist_ok=True)
    doel.write_text(tekst, encoding="utf-8")


def test_buiten_het_pakket_roept_niets_activepieces_aan() -> None:
    nieuw = vind_overtredingen(REPO_ROOT) - set(KNOWN_BUITEN_HET_PAKKET)

    assert not nieuw, (
        "Er is een tweede toegangsweg naar ActivePieces: "
        + ", ".join(sorted(nieuw))
        + ". Ga via `src.core.activepieces.client.ActivePiecesClient` met de verbinding van de "
        "tenant (`ap_verbinding_voor`), zodat B3 en de stappencontrole gelden."
    )


def test_de_uitzonderingslijst_is_niet_verouderd() -> None:
    gevonden = vind_overtredingen(REPO_ROOT)

    verouderd = sorted(sleutel for sleutel in KNOWN_BUITEN_HET_PAKKET if sleutel not in gevonden)

    assert not verouderd, (
        "Deze uitzondering is opgelost of hernoemd en hoort uit de lijst: " + ", ".join(verouderd)
    )


def test_elke_uitzondering_heeft_een_reden() -> None:
    zonder = [sleutel for sleutel, reden in KNOWN_BUITEN_HET_PAKKET.items() if not reden.strip()]

    assert not zonder


@pytest.mark.parametrize("naam", AP_CONFIGNAMEN)
def test_een_config_instelling_buiten_het_pakket_wordt_betrapt(tmp_path: Path, naam: str) -> None:
    _schrijf(
        tmp_path,
        "src/core/overig/slecht.py",
        f"def lees(config):\n    return config.{naam}\n",
    )

    assert vind_overtredingen(tmp_path) == {"src/core/overig/slecht.py::lees"}


def test_een_getattr_met_een_ap_instelling_wordt_betrapt(tmp_path: Path) -> None:
    _schrijf(
        tmp_path,
        "src/core/overig/slecht.py",
        'def lees(config):\n    return getattr(config, "activepieces_api_key", None)\n',
    )

    assert vind_overtredingen(tmp_path) == {"src/core/overig/slecht.py::lees"}


@pytest.mark.parametrize("module", HTTP_MODULES)
def test_een_httpx_aanroep_naar_ap_buiten_het_pakket_wordt_betrapt(
    tmp_path: Path, module: str
) -> None:
    _schrijf(
        tmp_path,
        "src/core/overig/slecht.py",
        f"import {module}\n\n"
        "async def haal():\n"
        '    return await x.get("http://activepieces:80/api/v1/app-connections")\n',
    )

    assert vind_overtredingen(tmp_path) == {"src/core/overig/slecht.py::haal"}


def test_dezelfde_aanroep_binnen_het_pakket_wordt_niet_betrapt(tmp_path: Path) -> None:
    _schrijf(
        tmp_path,
        "src/core/activepieces/client.py",
        "import httpx\n\n"
        "def haal(config):\n"
        '    return config.activepieces_api_url, "http://activepieces:80/api/v1"\n',
    )

    assert vind_overtredingen(tmp_path) == set()


def test_een_tekst_over_activepieces_zonder_http_module_wordt_niet_betrapt(tmp_path: Path) -> None:
    _schrijf(
        tmp_path,
        "src/core/overig/netjes.py",
        'def naam():\n    return "activepieces"\n',
    )

    assert vind_overtredingen(tmp_path) == set()


def test_de_naam_in_een_docstring_telt_niet_mee(tmp_path: Path) -> None:
    _schrijf(
        tmp_path,
        "src/core/overig/netjes.py",
        "import httpx\n\n"
        "def haal():\n"
        '    """Praat NIET met activepieces; zie activepieces_api_url."""\n'
        "    return 1\n",
    )

    assert vind_overtredingen(tmp_path) == set()


def test_een_uitzondering_geldt_voor_een_functie_niet_voor_het_bestand(tmp_path: Path) -> None:
    _schrijf(
        tmp_path,
        "src/core/overig/gemengd.py",
        "import httpx\n\n"
        "def toegestaan():\n"
        '    return "http://activepieces/health"\n\n'
        "def nieuw_en_slecht():\n"
        '    return "http://activepieces/flows"\n',
    )

    gevonden = vind_overtredingen(tmp_path)
    toegestaan = {"src/core/overig/gemengd.py::toegestaan"}

    assert gevonden - toegestaan == {"src/core/overig/gemengd.py::nieuw_en_slecht"}
