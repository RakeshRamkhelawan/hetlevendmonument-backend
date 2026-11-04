"""Wie BINNEN een bypass-blok leest, schrijft niet DAARBUITEN (ADR-036 OP-154).

**Wat hier stukgaat, en waarom het stil gebeurt.** OP-154 zet het pre-authenticatiepad op
een EIGEN databaseverbinding, omdat de applicatierol zonder tenantcontext nul rijen ziet.
Zodra dat gebeurt, hoort een object dat binnen het bypass-blok is gelezen bij die ANDERE
sessie. Wordt het daarna buiten het blok gewijzigd en opgeslagen op de gewone
applicatiesessie, dan draait die UPDATE onder de applicatierol zonder tenantcontext.

Gemeten op 2026-09-15 tegen PostgreSQL 15.19, met de policy-vorm uit
`src/alembic/versions/20260522_add_rls_core_tables.py:38-43`:

    UPDATE users SET hashed_password=... WHERE email=...   ->  0 rijen geraakt
    commit()                                               ->  slaagt, geen foutmelding
    werkelijk opgeslagen waarde                            ->  nog steeds de oude

Dat is geen foutmelding en geen 500. De gebruiker krijgt HTTP 200 en zijn wachtwoord is
niet veranderd. Precies dat patroon bewaakt deze guard.

**Waarom een GROENE guard met uitzonderingslijst en geen rode test.** De acht bekende
gevallen zijn vandaag niet kapot -- de applicatie verbindt nog als tabeleigenaar, dus de
tenantcontext doet er nog niet toe. Een rode test zou elke merge van iedereen blokkeren
voor een probleem dat pas bij stap 3 van OP-154 ontstaat. Zie de uitzonderingsparagraaf in
`.claude/rules/quality-gates.md`; aan alle vier eisen is voldaan (OP-154 staat in ADR-036
met fase en prioriteit, de lijst is gedateerd met een reden per regel, de staleness-test
bestaat, en het mutatiebewijs staat hieronder).

**Wat deze guard NIET ziet -- lees dit voordat je de lijst voor volledig houdt.** Hij
koppelt een schrijfaanroep aan een ontvanger die `db`/`session`/`db_session`/`async_session`
heet (of `self.<die naam>`). NIET gevonden worden:

- een schrijf via een HELPERFUNCTIE die zelf de sessie meekrijgt;
- een schrijf via een REPOSITORY-object (`repo.opslaan(...)`);
- een sessie onder een andere naam (`conn`, `s`, `uow.session`);
- `db.execute()` met een SQL-string die wordt OPGEBOUWD in plaats van letterlijk
  meegegeven -- die kan deze guard niet beoordelen en raadt hij bewust niet.

De lijst hieronder is dus een ONDERGRENS, geen inventaris. Dat is gemeten en niet geschat:
een eerdere versie van dezelfde telling gaf tien treffers, waarvan er vier
`redis_client.delete()` bleken -- geen databaseschrijf. Filteren op de ontvanger bracht het
terug naar zes, en de guard zelf vond er daarna acht (twee in `workers/actors.py` die uit
de handmatige telling waren gevallen).

Een eerdere versie miste bovendien `db.execute(update(...))` -- juist het idioom dat
`.claude/rules/backend-patterns.md` regel 6 voorschrijft, en dus de vorm die een omzetting
in stap 2 het waarschijnlijkst oplevert. Dat is gemeten op synthetische functies en
gerepareerd; zie `SCHRIJF_CONSTRUCTORS`. De guard was daarmee groen op precies het scenario
waarvoor hij als anker is gebouwd.

**Mutatiebewijs (2026-09-15), EEN REGEL PER ELEMENT van de bewaakte verzameling.**
Gemuteerd is telkens de PRODUCTIECODE, met een kopie als terugweg (nooit
`git checkout --`), en daarna teruggezet:

**Herzien na de Gate 2-review van 2026-09-15.** De eerste versie van dit bewijs mat
uitsluitend het weghalen van een regel uit `KNOWN_...`. Dat toont dat de guard een BEKENDE
plek vindt, maar niet dat hij het PATROON herkent -- en juist dat was stuk: na de omzetting
naar `pre_auth_lookup`/`adopt_tenant` zag hij de vijf auth-plekken helemaal niet meer. Het
bewijs hieronder muteert daarom de PRODUCTIECODE en zet het oorspronkelijke OP-154-geval
terug (lezen binnen het blok, schrijven erbuiten), EEN MUTATIE PER OMGEZETTE PLEK:

1. `router_password.py::reset_password` -- schrijf buiten het blok -> ROOD.
2. `router_password.py::change_password` -- idem -> ROOD.
3. `router_login.py::login` -- schrijf na `pre_auth_lookup`, voor `adopt_tenant` -> ROOD.
4. `router_login.py::get_or_create_lockout_record` -- schrijf na het blok -> ROOD.
5. `auth_service.py::authenticate_user` -- schrijf buiten beide blokken -> ROOD.
6. De drie nog niet omgezette elementen uit `KNOWN_...` (seeder + twee opruimtaken), elk
   apart uit de lijst gehaald -> `test_geen_nieuwe_gevallen` ROOD.
7. Andere richting -- een NIEUW geval: in `router_registration.py::register` een
   `db.commit()` na het bypass-blok gezet -> `test_geen_nieuwe_gevallen` ROOD met precies
   die functie erbij. Zonder deze helft bewaakt de guard alleen de acht die er al staan.
8. Andere richting -- een OPGELOST geval: in `seed_templates.py` het bypass-blok weggehaald
   -> `test_lijst_is_niet_verouderd` ROOD ("staat in de lijst maar wordt niet meer
   gevonden"). Zonder deze helft kan een opgeloste regel eeuwig blijven staan.
9. Legitiem geval mag NIET blijven hangen: een functie met een bypass-blok en ZONDER
    schrijf erbuiten wordt niet gemeld -> GROEN op de ongewijzigde boom.
10. De SCHRIJFVORMEN zijn apart getoetst op synthetische functies, in beide richtingen:
    `commit`, `add`, `merge`, `execute(update(...))`, `execute(update(..).where(..).values(..))`,
    `execute(text("UPDATE ..."))` en `self.db.execute(insert(...))` worden BETRAPT;
    `execute(select(...))`, `execute(select(..).where(..))`, `execute(text("SELECT 1"))` en
    `redis_client.delete()` NIET. Zonder die tweede helft zou "meld alles" een geldige
    oplossing zijn.
11. `test_de_meting_is_niet_leeg` bewaakt dat er uberhaupt bypass-blokken gevonden worden;
    zonder die helft is "vind niets, meld niets" een geldige oplossing.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import TypeGuard

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"

# Namen waaronder een SQLAlchemy-sessie in deze codebase wordt doorgegeven.
SESSIE_NAMEN = frozenset({"db", "session", "db_session", "async_session"})

# Methodes die een wijziging op die sessie zetten of vastleggen.
SCHRIJF_METHODES = frozenset({"commit", "flush", "add", "add_all", "delete", "merge"})

# Core-constructors die van een `execute(...)` een SCHRIJF maken. Zonder deze mist de guard
# `await db.execute(update(User)...)` -- en dat is nu juist het idioom dat
# `.claude/rules/backend-patterns.md` regel 6 voorschrijft, en dus de vorm die een
# omzetting in stap 2 het waarschijnlijkst oplevert. Gemeten 2026-09-15 op synthetische
# functies: zonder deze uitbreiding werd `execute(update(...))` GEMIST en bleef de guard
# groen op precies het scenario waarvoor hij als anker is gebouwd.
SCHRIJF_CONSTRUCTORS = frozenset({"update", "insert", "delete"})

# Eerste woord van een ruwe SQL-string die een schrijf is.
SCHRIJF_SQL_WOORDEN = ("update", "insert", "delete", "truncate")

# Gedateerd 2026-09-15. Reden PER REGEL, zoals quality-gates.md eist.
# Deze gevallen zijn vandaag niet kapot: de applicatie verbindt nog als tabeleigenaar.
# Ze breken op het moment dat OP-154 stap 3 de DATABASE_URL omzet, en worden in stap 2
# omgezet zodat lezen en schrijven allebei binnen de bypass-sessie gebeuren.
KNOWN_LEEST_BINNEN_SCHRIJFT_BUITEN: dict[tuple[str, str], str] = {
    # OMGEZET 2026-09-15 (OP-154 stap 2): `router_login.py::get_or_create_lockout_record`.
    # OMGEZET 2026-09-15 (OP-154 stap 2): `router_login.py::login`.
    # OMGEZET 2026-09-15 (OP-154 stap 2): `router_password.py::change_password`.
    # OMGEZET 2026-09-15 (OP-154 stap 2): `router_password.py::reset_password`. Stond hier
    # als "het gemeten geval: herstel meldt succes en slaat niets op". Leest nu via
    # `pre_auth_lookup` (alleen id en tenant_id), neemt daarna de tenant aan en laadt en
    # schrijft op de gewone sessie. De regel is verwijderd omdat `test_lijst_is_niet_verouderd`
    # hem anders rood maakt -- dat is precies de bedoeling van die test, en hij heeft het
    # bij deze omzetting ook echt gedaan.
    # OMGEZET 2026-09-15 (OP-154 stap 2): `auth_service.py::authenticate_user`. Het deel na
    # het vaststellen van de gebruiker staat nu in `_voltooi_authenticatie`, dat binnen
    # `adopt_tenant(...)` draait.
    # --- Toegevoegd 2026-09-16 (OP-153). Alle drie NAGEMETEN en onschuldig: het gaat om
    # een `commit()` of om een schrijf naar `tenants`, en `tenants` heeft geen
    # afschermingsregel (gemeten op de ketendatabase: `relrowsecurity = f`, nul policies).
    #
    # Waarom ze toch gemeld worden: de guard rekent `commit` tot de schrijfacties, en dat
    # is terecht. `session.add(x)` stuurt namelijk nog geen SQL -- SQLAlchemy voert de
    # INSERT pas uit bij de flush die `commit()` veroorzaakt. Staat de add BINNEN een
    # aangenomen klant en de commit erbuiten, dan draait juist die INSERT zonder context.
    # Dat is op 2026-09-16 echt gebeurd in `run_seeds.py` en daar hersteld. Deze drie zijn
    # het andere geval: het schrijfwerk zelf is al uitgevoerd binnen het blok, of het raakt
    # een tabel zonder regel.
    (
        "src/core/learning/worker.py",
        "_verwijder_per_tenant",
    ): "Alleen de `commit()` na de lus staat buiten het blok. De DELETEs draaien binnen "
    "`adopt_tenant` via `session.execute(...)` en sturen hun SQL dus meteen; de commit "
    "bevestigt alleen -- OP-153, nagemeten 2026-09-16.",
    (
        "src/core/services/tenant_service.py",
        "create_tenant",
    ): "De gemelde regels zijn het aanmaken van de KLANT zelf (`add` + `commit` op "
    "`tenants`), en dat hoort buiten een klantcontext: de klant bestaat op dat moment nog "
    "niet en `tenants` heeft geen afschermingsregel -- OP-153, nagemeten 2026-09-16. Het "
    "echte geval in deze functie (prana-budget binnen `best_effort` zonder aangenomen "
    "klant) is op 2026-09-16 hersteld, gevonden door deze guard.",
    (
        "src/ensure_demo_user.py",
        "ensure_demo_user",
    ): "Zelfde als hierboven: de gemelde regels maken de demoklant aan in `tenants`. Alles "
    "wat daarna volgt (rol, rechten, gebruiker) staat in `_zorg_voor_rol_en_gebruiker` en "
    "draait binnen `adopt_tenant` -- OP-153, nagemeten 2026-09-16.",
    (
        "src/core/company/seed_templates.py",
        "seed_platform_templates",
    ): "Seeder, geen verzoekpad; commit buiten de bypass -- OP-154 stap 2.",
    (
        "src/workers/actors.py",
        "_run_stale_task_cleanup",
    ): "Markeert taken FAILED in de bypass, commit erbuiten; de metriek telt dan een aantal "
    "dat niet is weggeschreven -- OP-154 stap 2.",
    (
        "src/workers/actors.py",
        "cleanup_expired_hitl_tickets",
    ): "Repository schrijft in de bypass, commit erbuiten -- OP-154 stap 2.",
}


#: Blokken die een query op een pre-authenticatiepad afschermen OF ontschermen. Alle drie
#: markeren "hier is bewust iets met de tenantcontext aan de hand", en een schrijf die
#: BUITEN zo'n blok valt terwijl er binnen gelezen is, is het patroon dat stil faalt.
#:
#: **`pre_auth_lookup` en `adopt_tenant` stonden hier eerst NIET in, en dat maakte deze
#: guard blind.** Gemeten 2026-09-15 door de Gate 2-review en daarna door mij herhaald: na
#: het omzetten van de vijf auth-plekken naar het nieuwe vocabulaire verdwenen ze uit de
#: gevonden verzameling -- niet omdat het patroon was opgelost, maar omdat deze functie
#: alleen `TenantFilterBypass` herkende. Het OORSPRONKELIJKE OP-154-geval terugzetten in
#: `reset_password` (lezen binnen, `user.hashed_password = ...` + `commit()` erbuiten) liet
#: alle drie de architecture-guards GROEN. De roodheid die ik als bewijs van de omzetting
#: had gemeld, betekende dus "wordt niet meer begrepen" in plaats van "is opgelost".
#:
#: Dit is de derde keer in dit project dat een omzetting het vocabulaire verving en de
#: bewaker liet staan. Wie hier een naam toevoegt of hernoemt: draai het mutatiebewijs
#: opnieuw (`python scripts/bewijs_op154_guard.py`), anders koopt de hernoeming stilte.
AFSCHERMENDE_BLOKKEN = frozenset({"TenantFilterBypass", "pre_auth_lookup", "adopt_tenant"})


def _opent_de_bypass(with_node: ast.With | ast.AsyncWith) -> bool:
    """Toetst de AANROEP, niet de naam ergens op de regel.

    Zelfde vorm als `test_auth_router_queries_bypass_the_tenant_filter.py`. Een
    tekstzoektocht zou een vermelding in een comment of docstring al laten meetellen.
    """
    for item in with_node.items:
        aanroep = item.context_expr
        if isinstance(aanroep, ast.Call):
            functie = aanroep.func
            naam = (
                functie.id
                if isinstance(functie, ast.Name)
                else functie.attr
                if isinstance(functie, ast.Attribute)
                else ""
            )
            if naam in AFSCHERMENDE_BLOKKEN:
                return True
    return False


def _is_een_sessie(doel: ast.expr) -> bool:
    """`db`, `session`, maar ook `self.db`."""
    if isinstance(doel, ast.Name):
        return doel.id in SESSIE_NAMEN
    if isinstance(doel, ast.Attribute):
        return doel.attr in SESSIE_NAMEN
    return False


def _execute_is_een_schrijf(node: ast.Call) -> bool:
    """`db.execute(update(...))`, `db.execute(text("UPDATE ..."))` en varianten.

    Toetst de STRUCTUUR van het eerste argument, niet de tekst van de regel: een
    `select()` met het woord "update" in een kolomnaam is geen schrijf, en een comment
    evenmin.
    """
    if not node.args:
        return False
    arg = node.args[0]

    if isinstance(arg, ast.Call):
        # De WORTEL van de aanroepketen, niet de buitenste schakel. `update(User).values(...)`
        # en `update(User).where(...).values(...)` zijn de normale vorm; wie alleen naar de
        # buitenste `.values`/`.where` kijkt, mist ze allebei. Gemeten 2026-09-15: precies
        # die twee bleven ongezien tot deze lus erbij kwam.
        wortel: ast.expr = arg
        while isinstance(wortel, ast.Call) and isinstance(wortel.func, ast.Attribute):
            wortel = wortel.func.value
        doel = wortel.func if isinstance(wortel, ast.Call) else wortel
        naam = (
            doel.id
            if isinstance(doel, ast.Name)
            else doel.attr
            if isinstance(doel, ast.Attribute)
            else ""
        )
        if naam in SCHRIJF_CONSTRUCTORS:
            return True
        # `text("UPDATE ...")` -- alleen bij een LETTERLIJKE string. Een opgebouwde
        # string kan deze guard niet beoordelen en wordt bewust niet geraden.
        if naam == "text" and arg.args and isinstance(arg.args[0], ast.Constant):
            waarde = arg.args[0].value
            if isinstance(waarde, str):
                return waarde.lstrip().lower().startswith(SCHRIJF_SQL_WOORDEN)
    return False


def _is_sessie_schrijf(node: ast.AST) -> TypeGuard[ast.Call]:
    """Een aanroep die op een sessie iets WIJZIGT of vastlegt."""
    if not isinstance(node, ast.Call):
        return False
    functie = node.func
    if not isinstance(functie, ast.Attribute) or not _is_een_sessie(functie.value):
        return False
    if functie.attr in SCHRIJF_METHODES:
        return True
    if functie.attr == "execute":
        return _execute_is_een_schrijf(node)
    return False


def _leest_binnen_schrijft_buiten(functie: ast.FunctionDef | ast.AsyncFunctionDef) -> list[int]:
    """Regelnummers van schrijfaanroepen BUITEN een bypass-blok, in een functie die er wel een heeft.

    Expliciete recursie en geen `ast.walk`: `ast.walk` vlakt de boom af, waardoor het
    onderscheid "binnen of buiten het with-blok" juist verdwijnt -- de fout uit
    `valkuil_ast_walk_duikt_functiebodies_in`.
    """
    heeft_bypass = False
    buiten: list[int] = []

    def loop(node: ast.AST, binnen_bypass: bool) -> None:
        nonlocal heeft_bypass
        for kind in ast.iter_child_nodes(node):
            nu = binnen_bypass
            if isinstance(kind, (ast.With, ast.AsyncWith)) and _opent_de_bypass(kind):
                heeft_bypass = True
                nu = True
            # Een geneste functiedefinitie heeft een eigen sessie-levensduur en wordt
            # als eigen functie beoordeeld, niet als onderdeel van deze.
            if isinstance(kind, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not nu and _is_sessie_schrijf(kind):
                buiten.append(kind.lineno)
            loop(kind, nu)

    loop(functie, False)
    return buiten if heeft_bypass else []


def _scan_bronboom() -> tuple[dict[tuple[str, str], list[int]], int]:
    """Geeft de gevonden gevallen plus het aantal functies MET een bypass-blok."""
    gevonden: dict[tuple[str, str], list[int]] = {}
    functies_met_bypass = 0

    for pad in sorted(SRC_DIR.rglob("*.py")):
        tekst = pad.read_text(encoding="utf-8", errors="ignore")
        # De prefilter MOET dezelfde verzameling kennen als `_opent_de_bypass`. Stond hier
        # alleen `TenantFilterBypass`, dan werd een bestand met uitsluitend het nieuwe
        # vocabulaire overgeslagen voordat de AST-toets eraan toekwam -- de tweede helft van
        # de blindheid die op 2026-09-15 is gemeten.
        if not any(naam in tekst for naam in AFSCHERMENDE_BLOKKEN):
            continue
        try:
            boom = ast.parse(tekst)
        except SyntaxError:  # pragma: no cover - src moet parsebaar zijn
            continue
        relatief = pad.relative_to(REPO_ROOT).as_posix()
        for knoop in ast.walk(boom):
            if not isinstance(knoop, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            regels = _leest_binnen_schrijft_buiten(knoop)
            if regels:
                gevonden[(relatief, knoop.name)] = regels
            # Losse telling van functies met een bypass-blok, voor de leegte-toets.
            for sub in ast.walk(knoop):
                if isinstance(sub, (ast.With, ast.AsyncWith)) and _opent_de_bypass(sub):
                    functies_met_bypass += 1
                    break

    return gevonden, functies_met_bypass


def test_geen_nieuwe_gevallen() -> None:
    """Een NIEUWE plek die binnen leest en buiten schrijft wordt geblokkeerd."""
    gevonden, _ = _scan_bronboom()
    nieuw = {
        sleutel: regels
        for sleutel, regels in gevonden.items()
        if sleutel not in KNOWN_LEEST_BINNEN_SCHRIJFT_BUITEN
    }
    assert not nieuw, (
        "Nieuwe plek(ken) die BINNEN een TenantFilterBypass lezen en DAARBUITEN schrijven:\n"
        + "\n".join(
            f"  {bestand}::{naam}() -> regel(s) {regels}"
            for (bestand, naam), regels in sorted(nieuw.items())
        )
        + "\n\nZet lezen en schrijven allebei binnen hetzelfde bypass-blok. Onder de "
        "applicatierol raakt die schrijf anders nul rijen zonder foutmelding (ADR-036 OP-154)."
    )


def test_lijst_is_niet_verouderd() -> None:
    """Een geval dat is opgelost MOET uit de lijst -- anders rot die dicht."""
    gevonden, _ = _scan_bronboom()
    verdwenen = [
        sleutel for sleutel in KNOWN_LEEST_BINNEN_SCHRIJFT_BUITEN if sleutel not in gevonden
    ]
    assert not verdwenen, (
        "Deze staan in KNOWN_LEEST_BINNEN_SCHRIJFT_BUITEN maar worden niet meer gevonden:\n"
        + "\n".join(f"  {bestand}::{naam}()" for bestand, naam in sorted(verdwenen))
        + "\n\nOpgelost? Haal de regel uit de lijst. Verplaatst of hernoemd? Werk de regel bij."
    )


def test_de_meting_is_niet_leeg() -> None:
    """Zonder deze toets is 'vind niets, meld niets' een geldige oplossing."""
    _, functies_met_bypass = _scan_bronboom()
    assert functies_met_bypass >= 20, (
        f"Slechts {functies_met_bypass} functies met een TenantFilterBypass-blok gevonden. "
        "Dat is te weinig om geloofwaardig te zijn: de guard meet waarschijnlijk niets meer "
        "(hernoemde klasse, verplaatste map, kapotte AST-toets)."
    )
