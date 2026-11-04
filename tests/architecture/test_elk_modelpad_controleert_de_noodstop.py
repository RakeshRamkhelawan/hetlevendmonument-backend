"""Elk modelpad controleert de noodstop (noodstop per klant, ronde 3; ADR-036 OP-03).

**Het principe.** Bij een stilgezette klant gaat er via GEEN pad klantgegevens naar een taalmodel. De
controle staat daarom OP HET PUNT van de modelaanroep (`src/core/shared/model_deur.py` (poort) en `src/core/noodstop/model_deur.py` (adapter)), niet in de
aanroepers: een nieuw pad dat een bestaande client of dienst gebruikt is dan vanzelf gedekt.

**Wat deze test bewaakt (uit de BRONCODE gelezen, de stub in `tests/conftest.py` verbergt niets).**

1. *Een nieuw modelpad.* Elk bestand in `src/` dat een model-SDK importeert of een modeladres/-pad noemt
   (`SDKS`, `ADRESSEN`; AST, geen docstrings) staat in `INVENTARIS` (gecontroleerd) of in `VRIJGESTELD`
   (met reden: geen klantgegevens, of geen taalmodel). Een nieuw bestand dat in geen van beide staat faalt.
2. *Elke modelmethode.* In een bestand uit `INVENTARIS` is elke methode met een naam uit
   `MODELMETHODEN` bewaakt: `@bewaakt_model_aanroep`/`@bewaakt_model_stroom`, of de klasse erft (ook
   via een ander bestand) van een basis die `bewaak_modelmethoden(cls, (...))` aanroept vanuit
   `__init_subclass__` en die methode noemt, of staat in `VRIJGESTELDE_METHODEN` met reden.
3. *Niet verouderd.* Een regel in `INVENTARIS` of `VRIJGESTELD` die niets meer vindt faalt.
4. *De checker zelf* is getest op nagemaakte bronnen (zie de zelftests onderaan).

**Wat dit NIET bewijst.** Dat elke aanroeper de klant in de context zet: een client zonder expliciete
klant leest de klant uit de context (`get_tenant_id`); staat daar niets, dan is het een systeemtaak en
loopt de aanroep door. Zie de moduledocstring van `model_deur.py`.

**Mutatiebewijs:** zie `docs/backend/review/review-BE-NDS-001.md`, sectie "Ronde 3".
"""

from __future__ import annotations

import ast
import functools
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"

BEWAKERS = {"bewaakt_model_aanroep", "bewaakt_model_stroom"}
HOOK = "bewaak_modelmethoden"

#: Importeert een bestand dit, dan praat het (of kan het praten) met een taalmodel.
SDKS = {
    "google.genai",
    "google.generativeai",
    "anthropic",
    "openai",
    "mistralai",
    "ollama",
    "cohere",
    "litellm",
    "groq",
    "vertexai",
}
#: Noemt een bestand (buiten docstrings) een van deze stukken, dan is het een modeladres of -pad.
ADRESSEN = (
    "chat/completions",
    "/api/chat",
    "/api/generate",
    "/api/embed",
    ":generateContent",
    "api.mistral.ai",
    "api.openai.com",
    "api.anthropic.com",
    "generativelanguage.googleapis.com",
)
#: Methoden die een tekst naar een taalmodel sturen (of een antwoord eruit halen).
MODELMETHODEN = {
    "chat_completion",
    "text_completion",
    "complete_json",
    "generate_response",
    "generate",
    "stream",
    "stream_generate",
    "stream_response",
    "get_embeddings",
    "embed",
    "chat",
    "suggest",
    "generate_embedding",
    "generate_embeddings_batch",
    "generate_with_tools",
    "route_request",
    "execute_request",
    "tekst",
}

#: Bestanden die een model aanroepen of de deur ernaartoe zijn: elke modelmethode is bewaakt.
INVENTARIS: dict[str, str] = {
    "src/core/services/llm/tenant_deur.py": "de ene deur (TenantTaalmodel): expliciete klant",
    "src/core/services/llm/service.py": "LLMService (stapel B): expliciete klant via for_tenant",
    "src/core/services/llm/base.py": "basis van stapel B: __init_subclass__ bewaakt elke provider",
    "src/core/services/llm/providers/deepseek.py": "stapel B, via de basis",
    "src/core/services/llm/providers/gemini.py": "stapel B, via de basis",
    "src/core/services/llm/providers/mistral.py": "stapel B, via de basis",
    "src/core/services/llm/providers/ollama.py": "stapel B, via de basis",
    "src/core/services/llm/providers/openai_compatible.py": "stapel B, via de basis",
    "src/core/llm/llm_client.py": "basis van stapel A: __init_subclass__ bewaakt elke client",
    "src/core/llm/deepseek_provider.py": "stapel A, via de basis",
    "src/core/llm/gemini_provider.py": "stapel A, via de basis",
    "src/core/llm/mistral_provider.py": "stapel A, via de basis",
    "src/core/llm/ollama_provider.py": "stapel A, via de basis",
    "src/core/llm/production_llm_client.py": "stapel A, via de basis",
    "src/core/llm/llm_service.py": "LLMService (stapel A): losse bewaking",
    "src/core/llm/llm_config.py": "GuaranteedLLMService: losse bewaking",
    "src/core/llm/fallback_chain.py": "terugvalketen: losse bewaking",
    "src/core/llm/local_provider.py": "lokaal model via de OpenAI-vorm: losse bewaking",
    "src/core/llm/ollama_client.py": "Ollama-client: losse bewaking",
    "src/core/shared/llm_client.py": "basis van de gedeelde stapel: __init_subclass__",
    "src/core/als/llm_integration/providers.py": "stapel E: __init_subclass__ op de basis",
    "src/core/learning/interfaces/llm_provider.py": "leerproviders: losse bewaking op suggest",
    "src/core/knowledge/embedding_service.py": "embeddings via een extern model: losse bewaking",
    "src/core/agents/router_agent_service.py": "routering via een model: losse bewaking",
    "src/core/strategy/llm_client.py": "strategieclient: bewaakt vooraan (anders een namaakantwoord)",
    "src/core/workflow/providers.py": "workflow-LLM-provider: losse bewaking",
}

#: Bestanden met een SDK of modeladres waar GEEN klantgegevens naartoe gaan, of die geen taalmodel zijn.
VRIJGESTELD: dict[str, str] = {
    "src/core/llm/intelligent_router.py": "alleen configuratie met adressen; roept niets aan",
    "src/core/monitoring/health_checks.py": "gezondheidscontrole: GET op de modellijst, geen klantgegevens",
    "src/core/services/setup_service.py": "sleutelcontrole bij installatie: GET op de modellijst, geen klantgegevens",
    "src/core/typing/optional_imports.py": "hulpmodule voor optionele imports; roept niets aan",
}

#: (bestand, klasse, methode) -> reden. Een modelmethode die zelf geen model aanroept.
VRIJGESTELDE_METHODEN: dict[tuple[str, str, str], str] = {
    ("src/core/services/llm/tenant_deur.py", "TenantTaalmodel", "complete_json"): (
        "delegeert naar `chat_completion` van dezelfde deur, die bewaakt is"
    ),
    ("src/core/workflow/providers.py", "ProductionLLMProvider", "embed"): (
        "placeholder die een lege lijst teruggeeft; roept geen model aan"
    ),
    ("src/core/workflow/providers.py", "FakeLLMProvider", "generate"): "namaak voor tests",
    ("src/core/workflow/providers.py", "FakeLLMProvider", "embed"): "namaak voor tests",
    ("src/core/learning/interfaces/llm_provider.py", "MockSuggestionProvider", "suggest"): (
        "namaak zonder model"
    ),
}


#: Bronnen die een zelftest onder een verzonnen pad registreert (er is dan geen bestand).
_OVERRIDE: dict[str, ast.Module] = {}


@functools.lru_cache(maxsize=None)
def _boom_uit_bestand(pad: str) -> ast.Module:
    return ast.parse((ROOT / pad).read_text(encoding="utf-8"))


def _boom(pad: str) -> ast.Module:
    return _OVERRIDE.get(pad) or _boom_uit_bestand(pad)


def _is_stub(f: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Abstract of een leeg geraamte (`pass`, `...`, alleen `raise`): roept zelf geen model aan."""
    if any(_decorator_naam(d) == "abstractmethod" for d in f.decorator_list):
        return True
    for s in f.body:
        if isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant):
            continue  # docstring of `...`
        if isinstance(s, (ast.Pass, ast.Raise)):
            continue
        if isinstance(s, ast.If) and isinstance(s.test, ast.Constant) and s.test.value is False:
            continue
        return False
    return True


def _alle_bestanden() -> list[str]:
    uit = []
    for p in sorted(SRC.rglob("*.py")):
        rel = p.relative_to(ROOT).as_posix()
        if "/tests/" in rel or "__pycache__" in rel:
            continue
        uit.append(rel)
    return uit


def _docstrings(boom: ast.AST) -> set[int]:
    uit: set[int] = set()
    for n in ast.walk(boom):
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            eerste = n.body[0] if n.body else None
            if (
                isinstance(eerste, ast.Expr)
                and isinstance(eerste.value, ast.Constant)
                and isinstance(eerste.value.value, str)
            ):
                uit.add(id(eerste.value))
    return uit


def heeft_modelbewijs(bron: str) -> bool:
    """Importeert de bron een model-SDK, of noemt hij (buiten docstrings) een modeladres of -pad?"""
    boom = ast.parse(bron)
    doc = _docstrings(boom)
    for n in ast.walk(boom):
        if isinstance(n, ast.Import):
            if any(a.name in SDKS or a.name.split(".")[0] in SDKS for a in n.names):
                return True
        elif isinstance(n, ast.ImportFrom) and n.module:
            if n.module in SDKS or n.module.split(".")[0] in SDKS:
                return True
            if any(f"{n.module}.{a.name}" in SDKS for a in n.names):
                return True
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in doc:
            if any(a in n.value for a in ADRESSEN):
                return True
    return False


@functools.lru_cache(maxsize=None)
def _bestanden_met_modelbewijs() -> frozenset[str]:
    tekens = tuple(SDKS) + ADRESSEN
    uit = set()
    for pad in _alle_bestanden():
        bron = (ROOT / pad).read_text(encoding="utf-8")
        if any(t in bron for t in tekens) and heeft_modelbewijs(bron):
            uit.add(pad)
    return frozenset(uit)


# --- wie erft van wie, en welke basis bewaakt welke methoden -------------------------------------


def _module_naar_pad(module: str) -> str | None:
    p = module.replace(".", "/")
    for kandidaat in (f"{p}.py", f"{p}/__init__.py"):
        if (ROOT / kandidaat).is_file():
            return kandidaat
    return None


def _decorator_naam(d: ast.expr) -> str:
    kern = d.func if isinstance(d, ast.Call) else d
    if isinstance(kern, ast.Name):
        return kern.id
    if isinstance(kern, ast.Attribute):
        return kern.attr
    return ""


def _hook_namen(klasse: ast.ClassDef) -> set[str]:
    """Methodenamen die `__init_subclass__` van deze klasse bewaakt (via `bewaak_modelmethoden`)."""
    uit: set[str] = set()
    for f in klasse.body:
        if isinstance(f, ast.FunctionDef) and f.name == "__init_subclass__":
            for n in ast.walk(f):
                if (
                    isinstance(n, ast.Call)
                    and _decorator_naam(n) == HOOK
                    and len(n.args) >= 2
                    and isinstance(n.args[1], (ast.Tuple, ast.List, ast.Set))
                ):
                    uit |= {
                        e.value
                        for e in n.args[1].elts
                        if isinstance(e, ast.Constant) and isinstance(e.value, str)
                    }
    return uit


def _vind_klasse(pad: str, naam: str, diepte: int = 0) -> tuple[str, ast.ClassDef] | None:
    """De klassedefinitie van `naam` zoals `pad` hem ziet (zelf gedefinieerd of geimporteerd)."""
    if diepte > 6:
        return None
    boom = _boom(pad)
    for n in boom.body:
        if isinstance(n, ast.ClassDef) and n.name == naam:
            return pad, n
    for n in ast.walk(boom):
        if isinstance(n, ast.ImportFrom) and (n.module or n.level):
            for a in n.names:
                if (a.asname or a.name) == naam:
                    if n.level:  # `from .x import Y`: relatief aan de map van dit bestand
                        basis = Path(pad).parent
                        for _ in range(n.level - 1):
                            basis = basis.parent
                        volledig = ".".join(basis.parts + ((n.module,) if n.module else ()))
                    else:
                        volledig = n.module or ""
                    doel = _module_naar_pad(volledig)
                    if doel:
                        return _vind_klasse(doel, a.name, diepte + 1)
    return None


def _bewaakte_namen_via_bases(pad: str, klasse: ast.ClassDef, diepte: int = 0) -> set[str]:
    """Methodenamen die de voorouders van `klasse` bij het aanmaken van de subklasse bewaken."""
    if diepte > 8:
        return set()
    uit: set[str] = set()
    for b in klasse.bases:
        naam = b.id if isinstance(b, ast.Name) else b.attr if isinstance(b, ast.Attribute) else ""
        gevonden = _vind_klasse(pad, naam) if naam else None
        if gevonden is None:
            continue
        bpad, bklasse = gevonden
        uit |= _hook_namen(bklasse)
        uit |= _bewaakte_namen_via_bases(bpad, bklasse, diepte + 1)
    return uit


def onbewaakte_methoden(pad: str, boom: ast.Module | None = None) -> list[str]:
    """`klasse.methode` voor elke modelmethode in `pad` zonder bewaking (decorator of hook)."""
    if boom is not None:
        _OVERRIDE[pad] = boom
    boom = _boom(pad)
    slecht: list[str] = []
    for klasse in (n for n in ast.walk(boom) if isinstance(n, ast.ClassDef)):
        via_basis = _bewaakte_namen_via_bases(pad, klasse)
        for f in klasse.body:
            if not isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if f.name not in MODELMETHODEN or _is_stub(f):
                continue
            if any(_decorator_naam(d) in BEWAKERS for d in f.decorator_list):
                continue
            if f.name in via_basis:
                continue
            if (pad, klasse.name, f.name) in VRIJGESTELDE_METHODEN:
                continue
            slecht.append(f"{klasse.name}.{f.name}")
    return slecht


# --- de tests -----------------------------------------------------------------------------------


def test_elk_bestand_met_een_model_staat_in_de_inventaris() -> None:
    onbekend = sorted(_bestanden_met_modelbewijs() - set(INVENTARIS) - set(VRIJGESTELD))
    assert not onbekend, (
        f"Nieuw modelpad zonder classificatie: {onbekend}. Laat de aanroep lopen langs een bewaakte "
        "basis of deur (`model_deur.py`) en voeg het bestand toe aan INVENTARIS; stuurt het geen "
        "klantgegevens, voeg het dan toe aan VRIJGESTELD met de reden."
    )


def test_elke_modelmethode_in_de_inventaris_is_bewaakt() -> None:
    fouten = {
        pad: onbewaakt for pad in sorted(INVENTARIS) if (onbewaakt := onbewaakte_methoden(pad))
    }
    assert not fouten, (
        f"Modelmethoden zonder de noodstopcontrole: {fouten}. Zet `@bewaakt_model_aanroep` erop, "
        "of laat de klasse erven van een basis die hem bewaakt."
    )


def test_inventaris_en_vrijstellingen_zijn_niet_verouderd() -> None:
    bewijs = _bestanden_met_modelbewijs()
    weg = sorted(p for p in (*INVENTARIS, *VRIJGESTELD) if not (ROOT / p).is_file())
    assert not weg, f"Bestand bestaat niet meer: {weg}"
    verouderd_vrij = sorted(p for p in VRIJGESTELD if p not in bewijs)
    assert not verouderd_vrij, f"Geen modelbewijs meer in {verouderd_vrij}; haal ze uit VRIJGESTELD"
    zonder_methode = sorted(
        p
        for p in INVENTARIS
        if p not in bewijs
        and not any(
            isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in MODELMETHODEN
            for n in ast.walk(_boom(p))
        )
        and not any(
            isinstance(n, ast.FunctionDef) and n.name == "__init_subclass__"
            for n in ast.walk(_boom(p))
        )
    )
    assert not zonder_methode, f"Geen modelmethode meer in {zonder_methode}; haal ze uit INVENTARIS"
    assert all(r.strip() for r in (*INVENTARIS.values(), *VRIJGESTELD.values()))
    assert not (set(INVENTARIS) & set(VRIJGESTELD))


def test_de_basisklassen_bewaken_hun_subklassen() -> None:
    """De vier stapels: de basis roept `bewaak_modelmethoden` aan vanuit `__init_subclass__`."""
    verwacht = {
        ("src/core/services/llm/base.py", "LLMProvider"): {"generate", "stream", "get_embeddings"},
        ("src/core/llm/llm_client.py", "LLMClient"): {"chat_completion", "text_completion"},
        ("src/core/shared/llm_client.py", "LLMClient"): {"chat_completion", "text_completion"},
        ("src/core/als/llm_integration/providers.py", "LLMProvider"): {"generate"},
    }
    for (pad, naam), minimaal in verwacht.items():
        gevonden = _vind_klasse(pad, naam)
        assert gevonden is not None, (pad, naam)
        assert minimaal <= _hook_namen(gevonden[1]), f"{pad}::{naam} bewaakt zijn subklassen niet"


# --- zelftests van de checker ------------------------------------------------------------------


def _checker_op(bron: str) -> list[str]:
    return onbewaakte_methoden("src/zelftest.py", ast.parse(bron))


def test_checker_ziet_een_onbewaakte_modelmethode() -> None:
    bron = "class A:\n    async def generate(self):\n        return await x()\n"
    assert _checker_op(bron) == ["A.generate"]


def test_checker_accepteert_een_decorator() -> None:
    bron = "class A:\n    @bewaakt_model_aanroep\n    async def generate(self):\n        return await x()\n"
    assert _checker_op(bron) == []


def test_checker_accepteert_een_decorator_met_een_andere_decorator_erbij() -> None:
    bron = "class A:\n    @x\n    @bewaakt_model_stroom\n    async def stream(self):\n        yield 1\n"
    assert _checker_op(bron) == []


def test_checker_negeert_een_leeg_geraamte_en_een_abstracte_methode() -> None:
    bron = (
        "class A:\n"
        "    async def generate(self):\n"
        "        pass\n"
        "    @abstractmethod\n"
        "    async def chat(self):\n"
        "        return await x()\n"
        "    async def embed(self):\n"
        "        raise NotImplementedError\n"
    )
    assert _checker_op(bron) == []


def test_checker_negeert_een_methode_die_geen_modelmethode_is() -> None:
    assert _checker_op("class A:\n    async def opruimen(self):\n        pass\n") == []


def test_checker_ziet_een_modelmodule_aan_een_sdk_import() -> None:
    assert heeft_modelbewijs("def f():\n    import openai\n")
    assert heeft_modelbewijs("from google.genai import types\n")
    assert not heeft_modelbewijs("import json\n")


def test_checker_ziet_een_modeladres_maar_geen_docstring() -> None:
    assert heeft_modelbewijs('URL = "https://api.mistral.ai/v1"\n')
    assert heeft_modelbewijs('def f(b):\n    return f"{b}/chat/completions"\n')
    assert not heeft_modelbewijs('"""Praat met /chat/completions."""\n')


def test_checker_een_hook_zonder_die_methode_telt_niet() -> None:
    bron = (
        "class Basis:\n"
        "    def __init_subclass__(cls):\n"
        '        bewaak_modelmethoden(cls, ("chat",))\n'
        "class Kind(Basis):\n"
        "    async def generate(self):\n"
        "        return await x()\n"
    )
    # `generate` staat niet in de hook van de basis: de checker moet hem melden.
    assert "Kind.generate" in _checker_op(bron)
