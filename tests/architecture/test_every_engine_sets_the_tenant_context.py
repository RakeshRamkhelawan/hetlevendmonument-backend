"""Een eigen database-engine omzeilt de tenantcontext (ADR-036 OP-151).

`src/core/database/database.py` zet `app.current_tenant` via een `begin`-event op ZIJN
engine. Dat dekt elke sessie die op die engine draait -- ook `session.py`, de websocket en
de governance-eventhandlers, die zelf niets zetten. Wie een EIGEN engine bouwt valt buiten
die dekking.

Vandaag merkt niemand dat: de applicatie verbindt als tabeleigenaar en PostgreSQL slaat
Row Level Security voor de eigenaar over. Zodra de applicatie de rol `sanskritisetu_app`
gaat gebruiken verandert dat, en wel stil:

    tabel met de veilige policyvorm -> NULLIF('', '')::INTEGER = NULL -> NUL RIJEN
    tabel zonder policy             -> alle tenants zichtbaar

Een achtergrondtaak die niets meer vindt geeft geen foutmelding; hij doet gewoon niets.
Daarom is dit een GROENE guard met een gedateerde uitzonderingslijst en geen rode test:
de bestaande engines omzetten is een ontwerpkeuze (krijgen de workers een BYPASSRLS-rol,
of zetten ze per opdracht een tenant?) die niet in deze sprint thuishoort. Nieuwe engines
worden wel meteen geblokkeerd.

**Mutatiebewijs (2026-08-16), beide richtingen:**
- Tijdelijk bestand `src/core/_proef_engine.py` met `create_async_engine(url)` ->
  `test_no_new_engine_bypasses_the_tenant_context` ROOD met dat pad in de melding.
- Datzelfde bestand met alleen de TEKST `create_async_engine` in een comment en in een
  string -> GROEN. Dat is de tweede richting en de reden dat deze guard de AST leest: een
  substring-zoektocht vindt het woord en niet de aanroep. Dat verschil is hier geen theorie:
  de eerste versie van de uitzonderingslijst was met `grep` samengesteld en bevatte
  `core/workflow/api.py`, waar `create_async_engine(...)` in een DOCSTRING met een
  codevoorbeeld staat (regel 114). `test_the_exceptions_are_not_stale` heeft die fout
  betrapt.
- `src/core/database/vacuum_manager.py` uit de uitzonderingslijst gehaald -> ROOD; terug
  gezet -> GROEN.
- Een verzonnen pad in de uitzonderingslijst -> `test_the_exceptions_are_not_stale` ROOD.
"""

from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src"

_ENGINE_FABRIEKEN = frozenset({"create_engine", "create_async_engine"})

# Mappen die geen applicatieverkeer zijn: migraties draaien bewust met DDL-rechten en
# hebben hun eigen tenant-sentinel (`src/alembic/env.py`), en `src/tests` is testcode.
_BUITEN_BESCHOUWING = ("alembic", "tests")

# De enige engine waarop de tenantcontext gegarandeerd wordt gezet.
_GEDEKT = "core/database/database.py"

# Modules met een EIGEN engine, gedateerd 2026-08-16, met de reden per regel. Elke regel
# hoort bij ADR-036 OP-153: voor de omschakeling naar de applicatierol moet per module
# beslist zijn of hij een tenantcontext zet of een rol met BYPASSRLS krijgt.
KNOWN_ZONDER_TENANTCONTEXT: dict[str, str] = {
    "core/services/foundation_leerlingantwoorden.py": (
        "nachtelijke job levendmonument-opschonen (BE-EP-055/056): eigen engine op de "
        "eigenaar-verbinding, draait buiten de API. Zet de tenantcontext zelf, per tenant een "
        "transactie met set_config('app.current_tenant'); bewaakt door "
        "tests/unit/test_be_ep_056_accounts_opschonen.py."
    ),
    "core/api/dependencies.py": "synchrone engine voor een legacy-dependency -- OP-153",
    "core/container.py": "DI-container bouwt een tweede engine naast db_manager -- OP-153",
    "core/database/bypass_session.py": (
        "BEWUST een eigen engine: de aparte verbinding voor het pre-authenticatiepad, naar een "
        "rol met BYPASSRLS die NIET aan de applicatierol is gegrant -- OP-154. Tenantcontext is "
        "hier niet van toepassing: de rol omzeilt per definitie elke policy, en het pad draait "
        "voordat er een tenant bekend is."
    ),
    "core/database/connection.py": "synchrone engine, leest DATABASE_URL zelf -- OP-153",
    "core/database/domain_isolation.py": "engine per domein voor schema-scheiding -- OP-153",
    "core/database/pool_config.py": "alternatieve poolimplementatie naast db_manager -- OP-153",
    "core/database/query_optimizer.py": "synchrone engine voor EXPLAIN-analyse -- OP-153",
    "core/database/read_replica.py": "primary- en replica-engine voor leesverkeer -- OP-153",
    "core/database/retry_utils.py": "synchrone engine met eigen retry-logica -- OP-153",
    "core/database/vacuum_manager.py": "onderhoudstaak, draait tenant-overstijgend -- OP-153",
    "core/learning/worker.py": "worker verwerkt opdrachten van alle tenants -- OP-153",
    "domains/agentic/seeds/seeder.py": "seed-script, draait buiten een verzoek -- OP-153",
    "ensure_demo_user.py": "opstartscript, draait buiten een verzoek -- OP-153",
    "scripts/dr_test_runner.py": "hersteltest, draait buiten een verzoek -- OP-153",
    "workers/workflow_worker.py": "worker verwerkt opdrachten van alle tenants -- OP-153",
}


def _bouwt_een_engine(boom: ast.AST) -> bool:
    """True zodra er ergens in de module een engine-fabriek wordt AANGEROEPEN.

    Op de AST en niet op de tekst: `create_async_engine` in een comment, een docstring of
    een foutmelding is geen engine. Een `def create_engine(...)` evenmin -- alleen een
    `ast.Call` telt.
    """
    for knoop in ast.walk(boom):
        if not isinstance(knoop, ast.Call):
            continue
        doel = knoop.func
        naam = (
            doel.id
            if isinstance(doel, ast.Name)
            else doel.attr
            if isinstance(doel, ast.Attribute)
            else None
        )
        if naam in _ENGINE_FABRIEKEN:
            return True
    return False


@lru_cache(maxsize=1)
def _scan() -> tuple[frozenset[str], tuple[str, ...]]:
    """Eenmalig over `src/`; vier tests delen het resultaat.

    Zonder cache leest deze module 2291 bestanden vier keer. Een test die de hele boom
    inleest heeft eerder een xdist-worker omgelegd, en dan meldt pytest een willekeurige
    ANDERE test als FAILED (ADR-036 OP-19).

    Geeft ook de bestanden terug die NIET te parsen waren. Die stil overslaan is precies
    hoe een guard groen blijft over een gat: een module met een BOM leest Python zelf wel
    en zou dan onzichtbaar zijn voor de scan.
    """
    gevonden: set[str] = set()
    onleesbaar: list[str] = []
    for bestand in _SRC.rglob("*.py"):
        relatief = bestand.relative_to(_SRC).as_posix()
        if relatief.split("/")[0] in _BUITEN_BESCHOUWING:
            continue
        try:
            boom = ast.parse(bestand.read_text(encoding="utf-8-sig"))
        except (SyntaxError, UnicodeDecodeError, OSError) as fout:
            onleesbaar.append(f"{relatief}: {type(fout).__name__}")
            continue
        if _bouwt_een_engine(boom):
            gevonden.add(relatief)
    return frozenset(gevonden), tuple(sorted(onleesbaar))


def _modules_met_een_eigen_engine() -> set[str]:
    return set(_scan()[0])


def test_no_new_engine_bypasses_the_tenant_context() -> None:
    """Een nieuwe eigen engine is geblokkeerd tot er een bewuste keuze over is gemaakt."""
    onverwacht = sorted(
        _modules_met_een_eigen_engine() - {_GEDEKT} - set(KNOWN_ZONDER_TENANTCONTEXT)
    )

    assert not onverwacht, (
        f"{len(onverwacht)} module(s) bouwen een eigen database-engine:\n"
        + "\n".join(f"  - src/{pad}" for pad in onverwacht)
        + "\n\nZo'n engine draait buiten `db_manager` en daarmee buiten de plek waar de "
        "tenant in de ContextVar wordt gezet.\n"
        # Hier stond: "Sessies op zo'n engine krijgen GEEN `app.current_tenant`." Dat is
        # ONWAAR en is gemeten op 2026-09-15 (ADR-036 OP-154): `_zet_tenantcontext` in
        # `src/core/database/database.py:118` luistert op de KLASSE `Engine`, dus hij vuurt
        # ook op een vreemde engine. Gemeten op een losse `create_async_engine`:
        # `current_setting('app.current_tenant', true)` gaf `''` -- gezet, niet afwezig.
        # Het echte risico is dus niet "geen instelling" maar een LEGE instelling: via
        # `NULLIF(..., '')` levert dat nul rijen onder `sanskritisetu_app`, zonder
        # foutmelding. De uitkomst klopte, de opgegeven oorzaak niet.
        "Onder de rol `sanskritisetu_app` draaien zij daardoor met een LEGE tenantcontext "
        "en leveren zij nul rijen op, zonder foutmelding.\n"
        "Gebruik `db_manager` (src/core/database/database.py), of zet een regel in "
        "KNOWN_ZONDER_TENANTCONTEXT met de reden en het OP-nummer erbij."
    )


def test_the_exceptions_are_not_stale() -> None:
    """Een module die geen eigen engine meer bouwt MOET uit de lijst.

    Zonder deze helft blijft de lijst staan nadat het probleem is opgelost, en dan dekt hij
    stilletjes een nieuwe overtreding af die toevallig hetzelfde pad heeft.
    """
    met_engine = _modules_met_een_eigen_engine()
    verdwenen = sorted(pad for pad in KNOWN_ZONDER_TENANTCONTEXT if pad not in met_engine)

    assert not verdwenen, (
        f"Deze modules staan in KNOWN_ZONDER_TENANTCONTEXT maar bouwen geen eigen engine "
        f"(meer): {verdwenen}. Haal ze uit de lijst."
    )


def test_the_guarded_engine_is_still_the_guarded_one() -> None:
    """`database.py` moet zelf wel een engine bouwen; anders bewaakt de guard een fictie."""
    assert _GEDEKT in _modules_met_een_eigen_engine(), (
        f"src/{_GEDEKT} bouwt geen engine meer. De uitzondering `_GEDEKT` klopt dan niet "
        "en de guard laat de echte engine ongemoeid."
    )


def test_every_file_was_actually_read() -> None:
    """Een bestand dat de scan niet kon lezen is een gat, geen detail."""
    onleesbaar = _scan()[1]

    assert not onleesbaar, (
        f"De scan kon {len(onleesbaar)} bestand(en) niet parsen: {list(onleesbaar)}. "
        "Zolang die worden overgeslagen kan er een engine in staan die deze guard nooit "
        "ziet."
    )


def test_the_guard_is_not_vacuous() -> None:
    """Een lege scan maakt de guard trivially groen."""
    gevonden = _modules_met_een_eigen_engine()

    assert len(gevonden) >= 15, (
        f"Slechts {len(gevonden)} modules met een engine gevonden; op 2026-08-30 waren het "
        f"er 15, waarvan 14 zonder tenantcontext (2026-08-16: 16 -- dat getal was te hoog, "
        f"zie ADR-036 OP-153). Leest de scan `src/` wel? ({_SRC})"
    )
