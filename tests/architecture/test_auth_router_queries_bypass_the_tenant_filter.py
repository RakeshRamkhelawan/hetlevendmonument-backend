"""Elke ORM-query in de auth-routers zit in een `TenantFilterBypass` (ADR-036 OP-131).

**Waarom dit een guard nodig heeft.** Verzoeken onder `/api/v1/auth` gaan door de PUBLIEKE
DOORLAAT van de tenant-middleware, en die WIST de tenantcontext (`tenant_middleware.py:344`).
Daar is dus per definitie geen tenant in de ContextVar.

Hier stond dat `/api/v1/auth` in `EXCLUDED_PREFIXES` staat. Dat is ONWAAR en is nagemeten op
2026-09-15: er zijn twee zulke lijsten in `src/` (`tenant_middleware.py:98` =
health/ready/metrics/docs/openapi.json en `rate_limit_middleware.py:219` = health/docs) en in
GEEN van beide staat een auth-pad. De conclusie klopte, het genoemde mechanisme niet. De globale
tenantfilter is fail-secure en plakt dan `WHERE false` aan iedere SELECT. Een query zonder bypass
vindt daar dus NOOIT een rij.

Dat is precies wat er gebeurde: `router_login.py` en `router_registration.py` hadden de bypass wel,
`router_password.py` (3 queries) en `router_token.py` (2) niet. Wachtwoord vergeten, herstellen,
wijzigen en token-validatie waren daardoor stil kapot -- `forgot_password` geeft met opzet altijd
200 terug, dus niemand zag het.

Het gedrag wordt getoetst in `tests/unit/test_auth_endpoints_survive_the_tenant_filter.py`. Die test
dekt de endpoints die vandaag bestaan; deze guard dekt de endpoints van morgen.

**Waarom AST en geen tekstzoektocht.** "Staat het woord TenantFilterBypass in het bestand" is groen
zodra er ergens EEN bypass staat, ook als de nieuwe query erbuiten valt. Deze guard koppelt elke
`db.execute`-aanroep aan de `with`-blokken waar hij daadwerkelijk binnen ligt.

**Mutatietest (2026-08-11, beide richtingen):**

1. De `with TenantFilterBypass():` rond de lookup in `router_password.py:100` weghalen (de query
   laten staan) -> ROOD, met bestand en regelnummer in de melding. Alleen de import weghalen is
   geen geldige mutatie -- dan valt het bestand sowieso om.
2. De andere kant: ongewijzigd -> GROEN, en `test_the_guard_actually_finds_queries` bewaakt dat er
   uberhaupt queries gevonden worden. Zonder die tweede helft is "vind niks en meld niks" een
   geldige oplossing en bewaakt de eerste assertie niets.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import TypeGuard

REPO_ROOT = Path(__file__).resolve().parents[2]
AUTH_DIR = REPO_ROOT / "src" / "core" / "api" / "auth"

#: Blokken waarbinnen een ORM-query op het auth-pad WEL een rij kan vinden.
#:
#: `TenantFilterBypass` zet de filter uit: de query ziet alles. Dat was tot 2026-09-15 de
#: enige mogelijkheid, want voor authenticatie is er geen tenant.
#:
#: `adopt_tenant` (ADR-036 OP-154 stap 2) is het nieuwe en STRIKTERE geval: zodra de
#: gebruiker is vastgesteld, wordt zijn tenant aangenomen en is de query gewoon afgeschermd
#: tot die ene tenant. Dat is geen verzwakking van deze guard maar een aanscherping van de
#: code: waar eerst "zie alles" stond, staat nu "zie precies een tenant". De guard blijft
#: een query BUITEN beide blokken afkeuren -- die vindt namelijk nooit iets.
#:
#: `pre_auth_lookup` stond hier tot 2026-09-16 NIET, met als reden dat queries daarbinnen
#: op `opzoeker` draaien en dus sowieso niet als auth-router-query werden geteld. Die
#: redenering klopte, maar zij maakte deze guard STIL ZWAKKER bij elke omzetting: een
#: omgezette plek verdween uit zijn blikveld in plaats van afgeschermd te worden bevonden.
#: `test_the_guard_actually_finds_queries` -- het vangnet dat juist moet voorkomen dat de
#: assertie hierboven over nul dingen gaat -- liep daardoor op 2026-09-16 rood zodra
#: `forgot_password` was omgezet. Dat is precies hoe dit in dit project eerder misging: een
#: omzetting verving het vocabulaire en de bewaker bleef staan.
#:
#: `opzoeker` telt nu mee als queryontvanger EN `pre_auth_lookup` telt mee als afschermend
#: blok. Het net blijft daarmee even groot terwijl de omzetting doorloopt.
_AFSCHERMENDE_BLOKKEN = frozenset({"TenantFilterBypass", "adopt_tenant", "pre_auth_lookup"})


#: Namen waarop een auth-router een query uitvoert. `opzoeker` staat erbij sinds
#: 2026-09-16: dat is de sessie die `pre_auth_lookup(db)` oplevert. Zonder die naam telde
#: deze guard elke omgezette plek als "verdwenen" in plaats van "afgeschermd", en dat is
#: exact de blindheid die op 2026-09-15 al een keer is gemeten -- toen verdween een
#: omgezette functie uit het blikveld van een andere guard en bleef die stil groen.
_QUERY_ONTVANGERS = frozenset({"db", "session", "opzoeker"})


def _is_session_execute(node: ast.AST) -> TypeGuard[ast.Call]:
    """`<iets>.execute(...)` waarbij `<iets>` een sessienaam uit `_QUERY_ONTVANGERS` is."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "execute"
        and isinstance(func.value, ast.Name)
        and func.value.id in _QUERY_ONTVANGERS
    )


def _opens_the_bypass(with_node: ast.With | ast.AsyncWith) -> bool:
    """Toetst de AANROEP `TenantFilterBypass()`, niet de naam ergens in de regel."""
    for item in with_node.items:
        call = item.context_expr
        if isinstance(call, ast.Call):
            func = call.func
            naam = (
                func.id
                if isinstance(func, ast.Name)
                else func.attr
                if isinstance(func, ast.Attribute)
                else ""
            )
            if naam in _AFSCHERMENDE_BLOKKEN:
                return True
    return False


def _unguarded_queries(tree: ast.AST) -> list[int]:
    """Regelnummers van `db.execute`-aanroepen die buiten elk bypass-blok liggen."""
    gevonden: list[int] = []

    def loop(node: ast.AST, binnen_bypass: bool) -> None:
        for kind in ast.iter_child_nodes(node):
            nu = binnen_bypass
            if isinstance(kind, (ast.With, ast.AsyncWith)) and _opens_the_bypass(kind):
                nu = True
            if not nu and _is_session_execute(kind):
                gevonden.append(kind.lineno)
            loop(kind, nu)

    loop(tree, False)
    return gevonden


def _all_queries(tree: ast.AST) -> list[int]:
    return [n.lineno for n in ast.walk(tree) if _is_session_execute(n)]


def _auth_router_files() -> list[Path]:
    return sorted(AUTH_DIR.glob("router*.py"))


def test_every_auth_router_query_sits_inside_a_bypass() -> None:
    """Een query zonder bypass op dit prefix levert per definitie nul rijen op."""
    overtredingen: list[str] = []
    for pad in _auth_router_files():
        tree = ast.parse(pad.read_text(encoding="utf-8"))
        for regel in _unguarded_queries(tree):
            overtredingen.append(f"{pad.relative_to(REPO_ROOT).as_posix()}:{regel}")

    assert not overtredingen, (
        "Deze ORM-queries in de auth-routers staan niet in een `TenantFilterBypass`:\n  "
        + "\n  ".join(overtredingen)
        + "\n\nVerzoeken onder `/api/v1/auth` gaan door de publieke doorlaat van de "
        "tenant-middleware, en die WIST de tenantcontext -- er is daar dus geen tenant in de "
        "ContextVar. De fail-secure tenantfilter geeft zo'n query `WHERE false` mee en er "
        "wordt NOOIT een rij gevonden, meestal zonder foutmelding. Zet de query in een "
        "`with TenantFilterBypass():` met de reden erbij, of -- beter, als de gebruiker al "
        "is vastgesteld -- in `async with adopt_tenant(db, <tenant van die gebruiker>):`."
    )


def test_the_guard_actually_finds_queries() -> None:
    """De tweede richting: zonder queries om te vinden bewaakt de assertie hierboven niets."""
    totaal = sum(
        len(_all_queries(ast.parse(pad.read_text(encoding="utf-8"))))
        for pad in _auth_router_files()
    )

    assert totaal >= 8, (
        f"Slechts {totaal} ORM-queries gevonden in {[p.name for p in _auth_router_files()]}. Op "
        "2026-08-11 waren het er 8 (login 3, password 3, token 2). Is de detectie stuk of zijn de "
        "routers verplaatst? Zolang dit niet klopt, is de guard hierboven stil groen."
    )
