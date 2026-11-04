"""Triage: welke schrijfacties kunnen ZONDER tenantcontext draaien? (ADR-036 OP-153/155)

WAAROM DIT SCRIPT BESTAAT
-------------------------
Row Level Security leest de klant uit de PostgreSQL-instelling `app.current_tenant`.
Die wordt gezet door de `Engine.begin`-listener in `src/core/database/database.py:118`,
en die leest hem op zijn beurt uit de ContextVar (`get_tenant_id()`). Staat de ContextVar
leeg, dan zet de listener een LEGE waarde -- bewust, want een lege waarde geeft via
`NULLIF(..., '')` nul rijen in plaats van de klant van het vorige verzoek.

Gemeten 2026-09-15 op PostgreSQL 15.19, als niet-eigenaar, zonder klantcontext:

    SELECT  -> 0 rijen        (STIL)
    INSERT  -> foutmelding    (LUID)
    UPDATE  -> UPDATE 0       (STIL)
    DELETE  -> DELETE 0       (STIL)

Drie van de vier melden zich dus NIET bij de omschakeling naar de rol
`sanskritisetu_app`. Dat is precies waarom deze triage met de hand niet houdbaar is.

WAT HET SCRIPT WEL EN NIET DOET
-------------------------------
Het is een TRIAGE, geen bewijs. Het zoekt kandidaten en print per kandidaat het PAD van
instappunt naar schrijfactie, zodat je elke regel kunt natrekken. De classificatie werkt
op MODULE-niveau (de importgraaf), niet op functieniveau: een module die vanuit een
achtergrondtaak bereikbaar is, wordt gemeld ook als alleen een andere functie in die
module dat pad neemt.

Die fout gaat bewust EEN kant op -- liever een vals positief dan een gemist stil
schrijfpad. Reken er dus op dat er valse positieven in staan; `core/services/rbac_service.py`
was er op 2026-09-16 een (zijn eigen sessie zit in een FastAPI-dependency, dus op het
verzoekpad staat de context al). Meet per GEVAL voor je iets aanpast.

GEBRUIK
-------
    python scripts/triage_tenantcontext_schrijfpaden.py            # de open kandidaten
    python scripts/triage_tenantcontext_schrijfpaden.py --alles    # ook wat gedekt is
    python scripts/triage_tenantcontext_schrijfpaden.py --json     # machineleesbaar
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import json
import sys
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = _REPO_ROOT / "src"

#: Methodes op een sessie die de database WIJZIGEN. `commit` staat er niet bij: die
#: schrijft niets eigens, hij bevestigt wat `add`/`execute` al heeft klaargezet, en hij
#: komt zo vaak voor dat elke module erdoor zou oplichten.
_SCHRIJF_METHODES = frozenset({"add", "add_all", "delete", "merge"})

#: Alleen aanroepen OP een sessie tellen. Gemeten 2026-09-16 over heel `src/`: van de 519
#: aanroepen van die vier methodes staan er 519 op 152 verschillende ontvangers, en de
#: grote meerderheid daarvan is geen sessie -- `visited.add()`, `self._redis.delete()`,
#: en 39 keer `@router.delete(...)`, want een route-decorator is syntactisch ook een
#: aanroep van `.delete()`. Zonder deze filter meet je vooral verzamelingen en Redis.
_SESSIE_NAMEN = frozenset({"db", "session", "sess", "db_session", "async_session", "uow"})

#: Constructors die een schrijvend statement bouwen (`update(X).values(...)`).
_SCHRIJF_CONSTRUCTORS = frozenset({"update", "insert", "delete"})

#: SQL-werkwoorden die een tabel WIJZIGEN, gezocht in RAUWE SQL: `db.execute(text("..."))`.
#:
#: Dit is het tweede vocabulaire, en het ontbreken ervan heeft op 2026-09-17 staging
#: plat gelegd. `src/core/database/seed.py` schrijft uitsluitend met rauwe SQL
#: (`session.execute(text("INSERT INTO users ..."))`) en heeft nul ORM-aanroepen:
#:
#:     grep -cE "\.add\(|\.add_all\(|\.merge\(|\.delete\(" src/core/database/seed.py  ->  0
#:
#: Dat bestand was voor deze triage dus volledig onzichtbaar, terwijl het bij het
#: OPSTARTEN draait -- buiten elk verzoek, dus zonder klantcontext. Gevolg na de
#: omschakeling naar `sanskritisetu_app`: de INSERT werd geweigerd en de applicatie
#: startte niet meer op. Een triage die maar EEN van de twee vocabulaires kent, geeft
#: een lege uitslag die als "niets gevonden" wordt gelezen.
_RUWE_SQL_WERKWOORDEN = frozenset({"INSERT", "UPDATE", "DELETE", "MERGE", "TRUNCATE", "COPY"})

#: Aanroepen die de klantcontext zetten. Staat er een in de module, dan neemt die module
#: de verantwoordelijkheid zelf -- en is hij geen doorgeefluik meer in de graaf.
_ZET_CONTEXT = frozenset(
    {"set_tenant_id", "adopt_tenant", "require_tenant_id", "TenantFilterBypass", "pre_auth_lookup"}
)

#: Kandidaten die NAGEMETEN vals positief zijn. Reden per regel, gedateerd.
#:
#: Ze blijven in de uitvoer staan (in een eigen kopje), want stil wegfilteren is precies
#: hoe een echte bevinding later onzichtbaar wordt. Ze tellen alleen niet mee als "open".
_KNOWN_VALS_POSITIEF: dict[str, str] = {
    "src/core/governance/services/audit_service.py": (
        "Gemeld via `copilot/api/contest_service.py`, dat een instappunt is omdat het een "
        "dramatiq-actor bevat. Die actor doet echter alleen `logger.info` en raakt de "
        "database niet; het databasewerk in `submit_contest` loopt over het verzoekpad. De "
        "sleutel hier is bewust de GEMELDE module en niet het instappunt -- op 2026-09-16 "
        "stond hier eerst het instappunt, en die regel greep dus nooit -- 2026-09-16."
    ),
    "src/core/evaluation/evaluation_service.py": (
        "Alleen bereikbaar via de importgraaf van `src/scripts/verify_ollama_cva.py`, een "
        "handmatig verificatiescript voor de CVA-agent dat geen evaluaties draait "
        "-- 2026-09-16."
    ),
    # De vier hieronder komen alle vier via `src.core.container`, de DI-registratie die per
    # ontwerp zowat alles importeert. Een pad DOOR die module zegt niets over een echte
    # aanroepketen. Per stuk nagemeten op 2026-09-16: alle vier krijgen hun sessie van de
    # aanroeper, en hun werkelijke aanroepers zijn FastAPI-routers.
    "src/core/ai/adaptive_learning_engine.py": (
        "`AdaptiveLearningEngine` wordt alleen binnen zijn eigen module aangemaakt "
        "(:1019, :1029), telkens met een `db_session` van de aanroeper -- 2026-09-16."
    ),
    "src/core/company/company_service.py": (
        "Aangemaakt vanuit `api/v1/company/router.py:38` en vanuit de container; beide "
        "verzoekpaden -- 2026-09-16."
    ),
    "src/core/company/department_service.py": (
        "Aangemaakt vanuit `department_router.py:34` en `department_individual_router.py:37` "
        "en vanuit de container; alle drie verzoekpaden -- 2026-09-16."
    ),
    "src/core/database/unit_of_work.py": (
        "Krijgt de sessie in `__init__` van de aanroeper en opent er zelf geen -- 2026-09-16."
    ),
}

#: Decorators die een functie tot HTTP-route maken.
_ROUTE_DECORATORS = frozenset({"get", "post", "put", "patch", "delete", "head", "options"})


@dataclass
class Module:
    """Wat we van een bronbestand hebben gemeten."""

    naam: str
    pad: Path
    invoer: set[str] = field(default_factory=set)
    schrijft: list[tuple[int, str]] = field(default_factory=list)
    zet_context: bool = False
    is_route: bool = False
    instappunt: str | None = None


def _module_naam(pad: Path) -> str:
    rel = pad.relative_to(_REPO_ROOT).with_suffix("")
    delen = list(rel.parts)
    if delen[-1] == "__init__":
        delen.pop()
    return ".".join(delen)


def _tenant_tabellen() -> set[str]:
    """De tabellen met een `tenant_id`, uit de ORM-metadata zelf -- niet uit een lijst.

    Een handmatige lijst loopt achter zodra iemand een model toevoegt; de metadata niet.
    """
    sys.path.insert(0, str(_REPO_ROOT))
    # De modellen importeren print bij het laden naar stdout ("pyotp not installed",
    # "Generated JWT secret"). Dat maakte `--json` onparseerbaar; vandaar de omleiding
    # naar stderr, waar diagnostiek hoort.
    with contextlib.redirect_stdout(sys.stderr):
        import src.core.database.import_all_models  # noqa: F401  (vult de metadata)
        from src.core.database.database import Base

    return {t.name for t in Base.metadata.tables.values() if "tenant_id" in t.c}


def _is_sessie(knoop: ast.expr) -> bool:
    """Ziet deze ontvanger eruit als een databasesessie?

    Op naam, want een AST kent geen types. Dat is een benadering met een bekende richting:
    een sessie die anders heet wordt gemist. Gemeten over `src/` dekken deze namen 233 van
    de 519 aanroepen, en de overige 286 zijn verzamelingen, Redis-clients en
    route-decorators -- geen daarvan raakt de database.
    """
    if isinstance(knoop, ast.Name):
        return knoop.id.lower() in _SESSIE_NAMEN
    if isinstance(knoop, ast.Attribute):
        kaal = knoop.attr.lstrip("_").lower()
        return kaal in _SESSIE_NAMEN
    return False


def _sql_beginwoord(knoop: ast.expr) -> str | None:
    """Het eerste SQL-woord van een letterlijke tekst, of None als het er geen is.

    Dekt de twee vormen waarin rauwe SQL in deze codebase staat:

        text("UPDATE users SET ...")                 -> ast.Constant
        text(f"INSERT INTO users ({col_list}) ...")  -> ast.JoinedStr

    Een f-string begint met een letterlijk stuk zodra het werkwoord er hardgecodeerd
    staat, en dat is bij elke rauwe schrijfactie in `src/` zo -- het werkwoord zelf komt
    nooit uit een variabele. Begint de tekst WEL met een variabele, dan geeft deze functie
    None: dan is er niets te lezen en is een vals negatief eerlijker dan een gok.
    """
    if isinstance(knoop, ast.Constant):
        return knoop.value.strip().split()[0].upper() if isinstance(knoop.value, str) else None
    if isinstance(knoop, ast.JoinedStr):
        for deel in knoop.values:
            if isinstance(deel, ast.Constant) and isinstance(deel.value, str):
                woorden = deel.value.strip().split()
                return woorden[0].upper() if woorden else None
            return None  # begint met een interpolatie -- niets te lezen
    return None


def _ruwe_sql_schrijfactie(node: ast.Call) -> str | None:
    """Is dit `<sessie>.execute(text("INSERT ..."))`? Zo ja: het werkwoord.

    Alleen op een ontvanger die op een sessie lijkt (`_is_sessie`), met dezelfde bekende
    richting als daar: een sessie die anders heet wordt gemist.
    """
    doel = node.func
    if not isinstance(doel, ast.Attribute) or doel.attr != "execute":
        return None
    if not _is_sessie(doel.value) or not node.args:
        return None

    eerste = node.args[0]
    # `text("...")` is de enige vorm waarin rauwe SQL hier de sessie in gaat, maar een
    # kale string is ook geldig SQLAlchemy, dus beide worden gelezen.
    if isinstance(eerste, ast.Call) and isinstance(eerste.func, ast.Name):
        if eerste.func.id != "text" or not eerste.args:
            return None
        eerste = eerste.args[0]

    woord = _sql_beginwoord(eerste)
    return woord if woord in _RUWE_SQL_WERKWOORDEN else None


def _decorator_namen(node: ast.AST) -> set[str]:
    namen: set[str] = set()
    for dec in getattr(node, "decorator_list", []):
        doel = dec.func if isinstance(dec, ast.Call) else dec
        if isinstance(doel, ast.Attribute):
            namen.add(doel.attr)
        elif isinstance(doel, ast.Name):
            namen.add(doel.id)
    return namen


def _lees_module(pad: Path) -> Module | None:
    bron = pad.read_text(encoding="utf-8", errors="replace")
    try:
        boom = ast.parse(bron)
    except (SyntaxError, ValueError):
        return None

    mod = Module(naam=_module_naam(pad), pad=pad)
    eigen_pakket = mod.naam.rsplit(".", 1)[0]

    for node in ast.walk(boom):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("src."):
                    mod.invoer.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relatieve import -- los hem op tegen het eigen pakket
                basis = eigen_pakket
                for _ in range(node.level - 1):
                    basis = basis.rsplit(".", 1)[0]
                wortel = f"{basis}.{node.module}" if node.module else basis
            elif node.module and node.module.startswith("src."):
                wortel = node.module
            else:
                continue
            mod.invoer.add(wortel)
            for alias in node.names:
                mod.invoer.add(f"{wortel}.{alias.name}")
        elif isinstance(node, ast.Call):
            doel = node.func
            if isinstance(doel, ast.Attribute):
                if doel.attr in _SCHRIJF_METHODES and _is_sessie(doel.value):
                    mod.schrijft.append((node.lineno, f"{ast.unparse(doel.value)}.{doel.attr}()"))
                elif (werkwoord := _ruwe_sql_schrijfactie(node)) is not None:
                    mod.schrijft.append(
                        (node.lineno, f"{ast.unparse(doel.value)}.execute(rauwe {werkwoord})")
                    )
                elif doel.attr in _ZET_CONTEXT:
                    mod.zet_context = True
            elif isinstance(doel, ast.Name):
                if doel.id in _SCHRIJF_CONSTRUCTORS and node.args:
                    mod.schrijft.append((node.lineno, f"{doel.id}(...)"))
                elif doel.id in _ZET_CONTEXT:
                    mod.zet_context = True
        elif isinstance(node, ast.Name) and node.id in _ZET_CONTEXT:
            mod.zet_context = True
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            decs = _decorator_namen(node)
            if decs & _ROUTE_DECORATORS:
                mod.is_route = True
            if "actor" in decs or "workflow_actor" in decs:
                mod.instappunt = "dramatiq-actor"

    if mod.instappunt is None:
        mod.instappunt = _bepaal_instappunt(mod, bron)
    return mod


def _bepaal_instappunt(mod: Module, bron: str) -> str | None:
    """Welk soort instappunt is deze module zelf, als hij er een is?

    Alleen instappunten die BUITEN het verzoekpad draaien tellen: daar staat de
    ContextVar leeg tenzij de code hem zelf zet.
    """
    if mod.is_route or "FastAPI(" in bron:
        # De ASGI-applicatie zelf. Die heeft een `if __name__`-blok voor een losse start,
        # maar alles erachter draait op het VERZOEKpad, waar de middleware de context
        # zet. Zonder deze uitzondering telt `src/main.py` als achtergrond-instappunt en
        # is via zijn importgraaf de halve codebase "bereikbaar buiten het verzoekpad":
        # gemeten 2026-09-16 leverde dat 154 kandidaten op in plaats van een bruikbare
        # lijst. Precies twee modules in `src/` vallen hieronder (`src/main.py` en
        # `src/core/api/main.py`); de andere 50 met een `if __name__`-blok niet.
        return None
    rel = mod.pad.relative_to(_REPO_ROOT).as_posix()
    if rel.startswith("src/tests/"):
        # 15 testbestanden die BINNEN `src/` staan. `pyproject.toml` zet
        # `testpaths = ["tests"]`, dus de poort verzamelt ze niet en er wordt niets mee
        # gedeployed. Zonder deze uitzondering trekken ze productiemodules de lijst in
        # als "los script" (gemeten: `workflow/engine.py` en `domain_pack_repository.py`).
        return None
    if rel.startswith("src/workers/"):
        return "worker"
    if "/jobs/" in rel or rel.endswith("_job.py"):
        return "achtergrondtaak"
    if rel.endswith("src/core/app_lifespan.py"):
        return "opstarten"
    if "__main__" in bron and "if __name__" in bron:
        return "los script"
    return None


def _bouw_graaf() -> dict[str, Module]:
    modules: dict[str, Module] = {}
    for pad in sorted(_SRC.rglob("*.py")):
        if "__pycache__" in pad.parts:
            continue
        mod = _lees_module(pad)
        if mod is not None:
            modules[mod.naam] = mod
    return modules


def _bereik(modules: dict[str, Module]) -> dict[str, tuple[str, list[str]]]:
    """Breedte-eerst vanaf elk niet-verzoek-instappunt; onthoud het KORTSTE pad.

    Het kortste pad is wat de uitvoer bruikbaar maakt: je kunt het met de hand nalopen.
    Modules die zelf de context zetten zijn een muur -- daarachter is het probleem weg.
    """
    bereikt: dict[str, tuple[str, list[str]]] = {}
    rij: deque[tuple[str, str, list[str]]] = deque()

    for naam, mod in modules.items():
        if mod.instappunt:
            bereikt[naam] = (mod.instappunt, [naam])
            if not mod.zet_context:
                rij.append((naam, mod.instappunt, [naam]))

    while rij:
        huidig, soort, pad = rij.popleft()
        for doel in modules[huidig].invoer:
            # Een `from x import y` levert zowel "x" als "x.y" op; pak wat bestaat.
            kandidaat = doel if doel in modules else doel.rsplit(".", 1)[0]
            if kandidaat not in modules or kandidaat in bereikt:
                continue
            nieuw = [*pad, kandidaat]
            bereikt[kandidaat] = (soort, nieuw)
            if not modules[kandidaat].zet_context:
                rij.append((kandidaat, soort, nieuw))

    return bereikt


def main() -> int:
    ontleder = argparse.ArgumentParser(
        description="Triage van schrijfpaden zonder tenantcontext (ADR-036 OP-153/155)."
    )
    ontleder.add_argument("--alles", action="store_true", help="toon ook de gedekte modules")
    ontleder.add_argument("--json", action="store_true", dest="als_json")
    args = ontleder.parse_args()

    tabellen = _tenant_tabellen()
    modules = _bouw_graaf()
    bereikt = _bereik(modules)

    open_gevallen: list[dict[str, object]] = []
    vals_positief: list[dict[str, object]] = []
    gedekt: list[dict[str, object]] = []
    for naam, mod in sorted(modules.items()):
        if not mod.schrijft:
            continue
        rij: dict[str, object] = {
            "module": naam,
            "bestand": mod.pad.relative_to(_REPO_ROOT).as_posix(),
            "schrijfacties": [{"regel": r, "wat": w} for r, w in mod.schrijft],
        }
        bestand = str(rij["bestand"])
        if naam in bereikt and not mod.zet_context:
            soort, pad = bereikt[naam]
            rij["instappunt"] = soort
            rij["pad"] = pad
            if bestand in _KNOWN_VALS_POSITIEF:
                rij["reden"] = _KNOWN_VALS_POSITIEF[bestand]
                vals_positief.append(rij)
            else:
                open_gevallen.append(rij)
        else:
            rij["reden"] = (
                "zet zelf de klantcontext" if mod.zet_context else "alleen via het verzoekpad"
            )
            gedekt.append(rij)

    if args.als_json:
        print(
            json.dumps(
                {
                    "open": open_gevallen,
                    "vals_positief": vals_positief,
                    "gedekt": gedekt,
                    "tenant_tabellen": len(tabellen),
                },
                indent=2,
            )
        )
        return 0

    gezien = {str(r["bestand"]) for r in vals_positief}
    verouderd = sorted(set(_KNOWN_VALS_POSITIEF) - gezien)
    if verouderd and not args.als_json:
        print("LET OP -- deze regels in _KNOWN_VALS_POSITIEF grijpen niet meer:")
        for b in verouderd:
            print(f"  {b}")
        print("Opgelost of hernoemd? Haal de regel weg, anders dekt hij later iets anders af.")
        print()

    print(f"Tenant-tabellen volgens de ORM-metadata: {len(tabellen)}")
    print(f"Modules met een schrijfactie: {len(open_gevallen) + len(gedekt)}")
    print(f"  bereikbaar buiten het verzoekpad, zonder eigen context: {len(open_gevallen)}")
    print(f"  nagemeten vals positief: {len(vals_positief)}")
    print(f"  gedekt: {len(gedekt)}")
    print()
    print("=== KANDIDATEN -- meet per geval, dit is een triage en geen bewijs ===")
    for rij in open_gevallen:
        acties = rij["schrijfacties"]
        assert isinstance(acties, list)
        pad = rij["pad"]
        assert isinstance(pad, list)
        print(f"\n{rij['bestand']}   [{rij['instappunt']}]")
        for actie in acties[:6]:
            print(f"    regel {actie['regel']}: {actie['wat']}")
        if len(acties) > 6:
            print(f"    ... nog {len(acties) - 6}")
        print("    pad: " + " -> ".join(pad))

    if args.alles:
        print("\n=== GEDEKT ===")
        for rij in gedekt:
            print(f"{rij['bestand']}: {rij['reden']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
