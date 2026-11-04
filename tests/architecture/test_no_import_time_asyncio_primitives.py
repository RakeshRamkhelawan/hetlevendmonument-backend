"""Architecture test: geen asyncio-primitieven die bij import worden aangemaakt.

Achtergrond (gevonden 2026-08-01 tijdens de BE-AGT-038-gate):
Een trage test in `critique_store` bracht `src/core/agents/critique_store.py:51` aan het
licht:

    _lock: asyncio.Lock = asyncio.Lock()

NB -- die trage test bleek een ANDERE oorzaak te hebben: `store()` raakt de database via
twee paden en de test mockte er maar een, waarna de retry-backoff 56,8s kostte. Dat is
apart opgelost. De lock was daarmee destijds geen BEWEZEN storing, alleen een latent
defect -- de eerste versie van dit bestand beweerde het oorzakelijke verband wel; dat was
een aanname die de meting niet overleefde.

**Alsnog empirisch bewezen (2026-08-27, ADR-036 OP-16-impactanalyse), niet aangenomen.**
`asyncio.Lock` bindt zich sinds Python 3.10 niet meer bij AANMAKEN aan een loop --
SEQUENTIEEL hergebruik over loops heen (elke pytest-test zijn eigen loop) is daardoor geen
probleem, gemeten op Python 3.13. Het gevaar zit in GELIJKTIJDIG gebruik vanuit twee ECHTE
event loops in twee verschillende threads: de tweede loop hangt dan voor altijd op de
acquire. Dat is precies dramatiq's threadingmodel (`docker-compose.yml`: `--threads 4`/
`--threads 2`), en `critique_store.py` werd via `CriticMixin` bereikt vanuit
agent-uitvoering die op elke workerthread kan lopen -- zie
`tests/unit/agents/test_critique_store_cross_thread_lock.py` voor de reproductie en de fix
(`threading.Lock` i.p.v. `asyncio.Lock`).

Deze test blokkeert NIEUWE gevallen. Van de oorspronkelijke vijf zijn er drie opgelost
(2026-08-27): `critique_store.py` (threading.Lock, zie hierboven), `activepieces/client.py`
(de gevlagde `_lock` bleek nergens gebruikt -- verwijderd) en
`infrastructure/async_optimizations.py` (`ConnectionPoolManager` is zelf ongebruikte code,
maar de kritieke secties bevatten `await` -- lazy `asyncio.Lock` in plaats van
`threading.Lock`, want die zou de loop blokkeren tijdens de await). De resterende twee
(`redis.py`, `rate_limiter.py`) beschermen een LOOP-GEBONDEN resource (een connectiepool)
en hebben al een eigen, correcte mitigatie (OP-156: de lock/pool wordt vervangen zodra de
lopende loop verandert) -- een "swap bij nieuwe loop"-patroon dat voor `critique_store.py`'s
ECHT gedeelde dict NIET veilig zou zijn geweest (het zou mutual exclusion stilletjes
opgeven voor een race in plaats van een hang).

Twee van de vijf zijn destijds door deze AST-scan gevonden en niet door een grep vooraf --
dat is precies waarom de guard AST-gebaseerd is en niet regex-gebaseerd.
"""

import ast
from pathlib import Path

SRC_ROOT = Path("src")

# Primitieven die zich aan de event loop binden op het moment van aanmaken.
LOOP_BOUND = {"Lock", "Event", "Queue", "Semaphore", "BoundedSemaphore", "Condition"}

# Bestaande gevallen per 2026-08-01. Formaat: "pad:regelnummer" -> reden.
# Wegwerken = OP-16 (Fase D): lazy aanmaken binnen de draaiende loop.
KNOWN_IMPORT_TIME_PRIMITIVES = {
    "src/core/database/redis.py": (
        "module-level _redis_pool_lock; beschermt de pool-creatie, in productie een loop"
    ),
    "src/core/governance/rate_limiter.py": (
        "module-level _redis_limiter_lock; zelfde patroon als redis.py"
    ),
}


def _is_loop_bound_call(node: ast.AST) -> bool:
    """`asyncio.Lock()` en soortgelijke aanroepen herkennen."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr in LOOP_BOUND:
        value = func.value
        return isinstance(value, ast.Name) and value.id == "asyncio"
    return False


def _find_import_time_primitives(tree: ast.AST) -> list[int]:
    """Regelnummers van primitieven op module- of classniveau.

    Bewust NIET door functie- en methodebodies: daarbinnen wordt het primitief pas
    aangemaakt als de functie draait, en dan is er een echte loop. Alleen aanmaken bij
    import (moduleniveau) of bij klassedefinitie (classniveau) is het probleem.

    Let op de valkuil in de implementatie: `ast.walk()` op een samengestelde statement
    (`if`, `try`, `with`) duikt WEL functiebodies in. Een `async def main()` binnen een
    `if __name__ == "__main__":`-blok wordt dan ten onrechte gemeld. Daarom een expliciete
    recursie die functiebodies op elke diepte overslaat, in plaats van ast.walk met een
    filter erachter. Dezelfde fout is eerder gemaakt in de dramatiq-broker-guard.
    """
    hits: list[int] = []
    skip = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)

    def walk_outside_functions(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, skip):
                continue  # alles binnen een functie draait later, op een echte loop
            if _is_loop_bound_call(child):
                hits.append(getattr(child, "lineno", 0))
            walk_outside_functions(child)  # ClassDef-bodies vallen hier bewust wel onder

    walk_outside_functions(tree)
    return hits


def _scan_src() -> tuple[dict[str, list[int]], list[str], int]:
    """(treffers per bestand, parse-fouten, aantal gescand)."""
    found: dict[str, list[int]] = {}
    fouten: list[str] = []
    gescand = 0
    for path in sorted(SRC_ROOT.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        except (OSError, SyntaxError, UnicodeDecodeError) as exc:
            fouten.append(f"{path.as_posix()}: {exc}")
            continue
        gescand += 1
        hits = _find_import_time_primitives(tree)
        if hits:
            found[path.as_posix()] = hits
    return found, fouten, gescand


def test_the_scan_actually_scans_files() -> None:
    """Vangnet: een onleesbaar/onparseerbaar bestand mag deze guard niet blind maken."""
    _, fouten, gescand = _scan_src()
    assert gescand >= 1500, (
        f"Slechts {gescand} bestanden gescand onder {SRC_ROOT} -- dat lijkt een (bijna) "
        "lege boom. Deze guard controleert dan vrijwel niets."
    )
    assert not fouten, (
        "Deze bestanden konden niet gelezen/geparsed worden en zijn NIET gecontroleerd op "
        "een import-time asyncio-primitief:\n" + "\n".join(f"  - {f}" for f in fouten)
    )


def test_no_new_import_time_asyncio_primitives() -> None:
    """Een nieuw asyncio-primitief op module- of classniveau is niet toegestaan."""
    found, _fouten, _gescand = _scan_src()
    new = {p: lines for p, lines in found.items() if p not in KNOWN_IMPORT_TIME_PRIMITIVES}

    assert not new, (
        "Nieuw asyncio-primitief dat bij import wordt aangemaakt. Zo'n object bindt zich "
        "aan de event loop die op dat moment bestaat; draait de code later op een andere "
        "loop, dan hangt het zonder foutmelding (zie critique_store, OP-16).\n"
        "Maak het primitief aan binnen de draaiende loop -- lazy in de methode die het "
        "nodig heeft, of in een async init.\n"
        + "\n".join(f"  - {p}: regel(s) {lines}" for p, lines in sorted(new.items()))
    )


def test_known_import_time_primitives_are_not_stale() -> None:
    """Een uitzondering die is opgelost moet uit de lijst -- anders rot hij dicht."""
    found, _fouten, _gescand = _scan_src()
    stale = [
        f"{path} ({reason})"
        for path, reason in KNOWN_IMPORT_TIME_PRIMITIVES.items()
        if path not in found
    ]

    assert not stale, (
        "KNOWN_IMPORT_TIME_PRIMITIVES is verouderd -- haal deze regels weg "
        "(OP-16 is dan deels af):\n" + "\n".join(f"  - {s}" for s in stale)
    )
