"""Geen client of adres voor DeepSeek (of Qwen) in `src/`, behalve op een benoemde, gedateerde lijst.

**Waarom (brief 2026-10-19, ADR-041 B14).** DeepSeek (China) en Qwen (Alibaba) hebben geen
verwerkersovereenkomst met ons. Elke plek in `src/` die een client voor hen bouwt of hun adres noemt, is een
plek waar klantgegevens kunnen belanden zodra iemand `DEEPSEEK_API_KEY` zet. Gemeten op 2026-10-19: zeven
paden (routering, focus-generator, workflowgenerator, focussuggesties, agentic service, `LocalClient`, twee
agents) stuurden de gebruikersvraag erheen, ook met een Mistralsleutel in de omgeving. Die zijn omgezet naar
`TenantTaalmodel` (`src/core/services/llm/tenant_deur.py`); deze guard houdt het zo.

**Wat hij toetst (AST, geen tekstzoek).**
0. een VERWIJZING (import, naam of attribuut) naar `DeepSeekProvider`/`DeepSeekClient`, niet alleen een aanroep;
1. een tekstconstante met `api.deepseek.com` of een Qwen/Dashscope-adres, buiten docstrings;
2. een aanroep van `DeepSeekProvider(...)` of `DeepSeekClient(...)`;
3. een aanroep met `"deepseek"` of `"qwen"` als providernaam (eerste argument of `provider=`,
   `provider_name=`, `provider_type=`).

**De uitzonderingen** staan in `BEKENDE_UITZONDERINGEN`, met sleutel `bestand::functie` (niet alleen het
bestand: een uitzondering stelt de ene plek vrij waarvoor een reden is opgeschreven), een datum en een reden
PER regel. `test_de_uitzonderingslijst_is_niet_verouderd` faalt zodra een regel niets meer vindt, zodat een
opgeloste uitzondering niet blijft staan.

**Mutatiebewijs:** zie `docs/backend/review/review-BE-LLM-006.md`, sectie "Mutatiebewijs geen-DeepSeek-guard"
(per element van de bewaakte verzameling, in beide richtingen, en binnen een bestand dat al op de lijst staat).
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"

VERBODEN_ADRESSEN = ("api.deepseek.com", "dashscope.aliyuncs.com", "dashscope-intl.aliyuncs.com")
VERBODEN_KLASSEN = {"DeepSeekProvider", "DeepSeekClient", "QwenProvider", "QwenClient"}
VERBODEN_NAMEN = {"deepseek", "qwen"}
PROVIDER_ARGUMENTEN = {"provider", "provider_name", "provider_type"}
#: Aanroepen die een taalmodel BOUWEN of kiezen. Alleen daar telt een providernaam: `ModelCard(provider="DeepSeek")`
#: is een beschrijving in een governancedocument en bouwt niets (gemeten: `governance/model_cards.py`).
FABRIEKEN = {
    "create_llm_client",
    "create_llm_client_from_config",
    "create",
    "create_from_env",
    "get_provider",
    "get_llm_provider",
    "LLMService",
    "LLMProviderFactory",
    "ProviderFactory",
}

#: `bestand::functie` -> (datum, reden). Alleen de ene plek waarvoor een reden staat.
#: Vul deze lijst NIET aan om een rode guard groen te krijgen: gebruik `TenantTaalmodel`.
BEKENDE_UITZONDERINGEN: dict[str, tuple[str, str]] = {
    "src/core/llm/deepseek_provider.py::DeepSeekProvider.__init__": (
        "2026-10-19",
        "de providerklasse zelf (stapel A, adres als standaard); `LLMService.initialize` bouwt hem niet meer",
    ),
    "src/core/llm/llm_client.py::DeepSeekClient.__init__": (
        "2026-10-19",
        "de clientklasse zelf (stapel A); `create_llm_client_from_config` weigert DEEPSEEK sinds deze brief",
    ),
    "src/core/shared/llm_client.py::DeepSeekClient.__init__": (
        "2026-10-19",
        "de clientklasse zelf (gedeelde stapel); `create_llm_client_from_config` weigert DEEPSEEK sinds deze brief",
    ),
    "src/core/services/llm/providers/deepseek.py::DeepSeekProvider._validate_config": (
        "2026-10-19",
        "de providerklasse (stapel B, standaardadres); bereikbaar alleen voor een EIGEN eindpunt van de klant, "
        "nooit via de platformstandaard (`create_from_env` en `for_tenant` weigeren het)",
    ),
    "src/core/als/llm_integration/__init__.py::<module>": (
        "2026-10-19",
        "stapel E: heruitvoer van de klasse; `get_provider('deepseek')` weigert en `LLMAgentAdapter` heeft in "
        "`src/` geen aanroeper",
    ),
    "src/core/services/llm/factory.py::<module>": (
        "2026-10-19",
        "stapel B: de import voor het register; `create_from_env` en `LLMService.for_tenant` weigeren DeepSeek "
        "voor het platform",
    ),
    "src/core/services/llm/factory.py::ProviderFactory": (
        "2026-10-19",
        "stapel B: het register `{'deepseek': DeepSeekProvider}` is nodig voor een EIGEN eindpunt van de klant "
        "(zijn keuze, zijn contract); de platformroute (`create_from_env`) weigert",
    ),
    "src/core/services/llm/providers/__init__.py::<module>": (
        "2026-10-19",
        "stapel B: heruitvoer van de providerklassen",
    ),
    "src/core/als/llm_integration/providers.py::DeepSeekProvider.__init__": (
        "2026-10-19",
        "stapel E (`als/llm_integration`): de klasse met adres; `get_provider('deepseek')` weigert sinds deze "
        "brief en `LLMAgentAdapter` heeft in `src/` geen aanroeper",
    ),
}


def _bestanden() -> list[Path]:
    return sorted(p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts)


def _docstring_knopen(boom: ast.AST) -> set[int]:
    """`id()` van de tekstconstanten die een docstring zijn; die zijn uitleg en geen adres."""
    uit: set[int] = set()
    for knoop in ast.walk(boom):
        if isinstance(knoop, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            eerste = knoop.body[0] if knoop.body else None
            if (
                isinstance(eerste, ast.Expr)
                and isinstance(eerste.value, ast.Constant)
                and isinstance(eerste.value.value, str)
            ):
                uit.add(id(eerste.value))
    return uit


def _naam_van_aanroep(knoop: ast.Call) -> str:
    if isinstance(knoop.func, ast.Name):
        return knoop.func.id
    if isinstance(knoop.func, ast.Attribute):
        return knoop.func.attr
    return ""


def _is_verboden_providernaam(waarde: ast.expr) -> bool:
    """Een tekstconstante `"deepseek"` OF een enumlid `LLMProvider.DEEPSEEK` (Gate 2 ronde 2)."""
    if isinstance(waarde, ast.Attribute):
        return waarde.attr.lower() in VERBODEN_NAMEN
    return (
        isinstance(waarde, ast.Constant)
        and isinstance(waarde.value, str)
        and waarde.value.strip().lower() in VERBODEN_NAMEN
    )


def _vondsten(pad: Path) -> set[str]:
    """`bestand::functie` van elke overtreding in dit bestand.

    Expliciete recursie met een stapel van omsluitende namen: `ast.walk()` vanaf een functieknoop
    onderscheidt een geneste functie niet van zijn ouder, en dan is de sleutel te grof.
    """
    relatief = pad.relative_to(REPO).as_posix()
    boom = ast.parse(pad.read_text(encoding="utf-8"))
    docstrings = _docstring_knopen(boom)
    gevonden: set[str] = set()

    def bezoek(knoop: ast.AST, stapel: list[str]) -> None:
        if isinstance(knoop, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            stapel = [*stapel, knoop.name]
        sleutel = f"{relatief}::{'.'.join(stapel) if stapel else '<module>'}"

        if (
            isinstance(knoop, ast.Constant)
            and isinstance(knoop.value, str)
            and id(knoop) not in docstrings
            and any(adres in knoop.value.lower() for adres in VERBODEN_ADRESSEN)
        ):
            gevonden.add(sleutel)
        # Een VERWIJZING naar de klasse telt ook, niet alleen een aanroep: `provider_class(...)` uit een
        # woordenboek met `DeepSeekProvider` erin bouwde hem (Gate 2 ronde 1, `llm_config.py`).
        if isinstance(knoop, ast.ImportFrom) and any(a.name in VERBODEN_KLASSEN for a in knoop.names):
            gevonden.add(sleutel)
        if isinstance(knoop, ast.Name) and knoop.id in VERBODEN_KLASSEN:
            gevonden.add(sleutel)
        if isinstance(knoop, ast.Attribute) and knoop.attr in VERBODEN_KLASSEN:
            gevonden.add(sleutel)
        if isinstance(knoop, ast.Call):
            naam = _naam_van_aanroep(knoop)
            if naam in VERBODEN_KLASSEN:
                gevonden.add(sleutel)
            if naam in FABRIEKEN:
                eerste = knoop.args[0] if knoop.args else None
                if eerste is not None and _is_verboden_providernaam(eerste):
                    gevonden.add(sleutel)
                for kw in knoop.keywords:
                    if kw.arg in PROVIDER_ARGUMENTEN and _is_verboden_providernaam(kw.value):
                        gevonden.add(sleutel)
        for kind in ast.iter_child_nodes(knoop):
            bezoek(kind, stapel)

    bezoek(boom, [])
    return gevonden


def _alle_vondsten() -> set[str]:
    uit: set[str] = set()
    for pad in _bestanden():
        uit |= _vondsten(pad)
    return uit


def test_geen_nieuwe_client_of_adres_voor_deepseek_of_qwen() -> None:
    nieuw = sorted(v for v in _alle_vondsten() if v not in BEKENDE_UITZONDERINGEN)

    assert nieuw == [], (
        "Een client of adres voor DeepSeek/Qwen buiten de uitzonderingslijst (ADR-041 B14): klantgegevens "
        "mogen er niet heen. Gebruik `TenantTaalmodel(tenant_id)` uit "
        "`src/core/services/llm/tenant_deur.py`. Gevonden: "
        f"{nieuw[:10]}"
    )


def test_de_uitzonderingslijst_is_niet_verouderd() -> None:
    gevonden = _alle_vondsten()

    verouderd = sorted(k for k in BEKENDE_UITZONDERINGEN if k not in gevonden)

    assert verouderd == [], (
        "Deze uitzonderingen vinden niets meer en horen uit de lijst (of de functienaam is veranderd): "
        f"{verouderd}"
    )


def test_elke_uitzondering_heeft_een_datum_en_een_reden() -> None:
    kaal = sorted(
        k
        for k, (datum, reden) in BEKENDE_UITZONDERINGEN.items()
        if not datum.startswith("20") or len(reden.strip()) < 20
    )

    assert kaal == []


def test_controlegroep_de_scanner_ziet_wel_iets() -> None:
    """Zonder deze test is `geen nieuwe overtreding` ook waar als de scanner niets meer leest."""
    assert len(_bestanden()) > 500
