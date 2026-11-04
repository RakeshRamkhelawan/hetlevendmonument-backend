STATUS: APPROVED

# Review BE-EP-035 -- Agent control endpoints (pause, resume, restart)

**Scope:** `src/core/api/v1/management/agents_router.py`,
`src/core/api/management_endpoints.py`,
`tests/unit/api/test_pause_agent_pauses_or_fails_loud.py`,
`tests/architecture/test_agent_control_endpoints_do_not_fake_success.py`

**Reviewer:** onafhankelijke code-reviewer, zonder context en zonder aannames. De reviewer kreeg
alleen de branch en de basis, geen uitleg over doel of afwegingen, en had de opdracht te
beoordelen wat de code DOET en niet wat een commit-boodschap of docstring BEWEERT.

**Rondes:** twee. Ronde 1 op de eerste fix, ronde 2 op de correcties uit ronde 1.

**Omgeving:** Python 3.13, pytest 8.4.2, FastAPI 0.121.1, Windows 11, project-venv.

---

## A. Eindoordeel

**APPROVED**, na verwerking van alle bevindingen uit beide rondes.

## B. Samenvatting

De wijziging doet wat een fail-loud-fix hoort te doen: de zes handlers weigeren, de OpenAPI is
eerlijk, en beide bereikbare mount-paden zijn geraakt. De inhoudelijke zwakte zat niet in de
productiecode maar in de BORGING: de eerste guard toetste drie letterlijke succeswaarden en liet
daarmee vier ontsnappingsvormen groen, en twee tests asserteerden iets dat niet kon falen. Dat is
het patroon dat dit project vaker heeft betrapt -- de fix was goed, het bewijs van de fix niet.

## C. Bevindingen per categorie

### 1. Coverage gaps

Geen na ronde 2. De guard itereert over een expliciet benoemde verzameling van zes handlers en
er is een mutatieregel per element EN per ontsnappingsvorm.

### 2. Functionele onduidelijkheden

Geen. Het gedrag is een constante weigering; er is geen tak die anders kan lopen.

### 3. Technische onduidelijkheden

Opgelost in ronde 2: de docstring van de unittest schreef de default van 30 seconden toe aan
`agent_runner.py:39`. Die regel geeft de waarde alleen DOOR. De twee echte bronnen zijn
`agent_circuit_breaker.py:31` en `agent_runner.py:18`. Een onbewezen of onjuiste
oorzaakstoeschrijving in een toelichting is in dit project expliciet verboden, en dit was er een.

### 4. Ontbrekende foutstatussen en edge cases

Geen. 401, 403, 422 en 501 zijn beschreven en de eerste drie komen uit ongewijzigde dependencies.

### 5. Acceptatiecriteria-problemen

Opgelost. De criteria zijn nu geformuleerd als mutaties met een gemeten uitkomst, niet als
eigenschappen.

### 6. Integratorhandleiding

Aangevuld met het gemeten platformgedrag dat de foutcode op `body.detail.error.code` terechtkomt
en niet op `body.error.code`. Zonder die notitie zou een integrator de gedocumenteerde
projectvorm volgen en de code nooit vinden.

### 7. Trainingsdata

In orde.

### 8. Structuur- en consistentieproblemen

Opgelost in ronde 2: de OpenAPI-beschrijving stond zes keer letterlijk in twee bestanden en was
Nederlands terwijl de rest van de OpenAPI in dezelfde routers Engels is. Nu een gedeelde
constante `UNAVAILABLE_RESPONSES` in de helper-module, in het Engels.

### 9. Risico's voor implementatie, security of QA

Het enige resterende risico is bewust en opgeschreven: een handler met een eigen responsmodel
telt voor de guard als "effect" en zou groen blijven. Dat gat wordt afgedekt door de unittest die
voor alle zes handlers hard op 501 asserteert.

---

## D. Issue register

| Severity | ID of sectie | Probleem | Waarom dit een probleem is | Correctie | Status |
| --- | --- | --- | --- | --- | --- |
| High | guard, `_refuses()`-uitzondering | De guard kende drie letterlijke succeswaarden en had een uitzondering voor handlers die "weigeren". Vier vormen glipten er groen doorheen, waaronder een validatie-`raise` naast een succes-return. | Precies de vorm die de guard moet vangen (bevestiging zonder effect) bleef onopgemerkt. De guard gaf vals vertrouwen. | Uitzondering geheel verwijderd; `_nodes_inside_raises()` en `_is_exception_constructor()` toegevoegd zodat een `raise`-tak niet als effect telt; `REFUSING_CALL_NAMES` uitgesloten van effecten. Twaalf synthetische regelgevallen toegevoegd die de regel zelf toetsen. | Opgelost |
| Medium | `test_pause_agent_pauses_or_fails_loud.py:192-196` | Substring-matching: `"hold" in "threshold"` is waar, en `"queue" in "dequeue"` ook. | Een toekomstige handler met een lokale `threshold` faalt met de melding dat er een echt mechanisme is bijgekomen. Een regel met valse positieven wordt uitgezet, niet gevolgd. | Vergelijking op TOKENS (splitsen op `_`), met `pause_store` als exacte naam. Gemeten: `threshold` en `dequeue` geven nu leeg, een echte breker/redis/pause_store nog steeds een treffer. | Opgelost |
| Low | `test_pause_agent_pauses_or_fails_loud.py`, breker-asserties | `AgentCircuitBreaker` opbouwen en `get_state()` voor en na vergelijken kan niet falen: de handler heeft geen referentie naar die breker. | Een assertie die zijn eigen invoer aan beide kanten verzint bewijst alleen determinisme. Een docstring die dat eerlijk opschrijft maakt hem niet nuttig. | Asserties en de bijbehorende dubbels verwijderd; alleen de structurele toets blijft over. De docstring legt beide verwijderrondes vast. | Opgelost |
| Low | beide routers | Zes identieke `responses={501: ...}`-blokken, in het Nederlands terwijl de rest van de OpenAPI Engels is. | Een correctie had op vijf plekken vergeten kunnen worden; een tweetalige specificatie belast de clientontwikkelaar. | Gedeelde constante `UNAVAILABLE_RESPONSES`, Engels. | Opgelost |
| Low | beide routers | Returntype `-> dict[str, str]` op zes handlers die nooit terugkeren. | Het type liegt over het contract en verbergt voor de typechecker dat er geen returnpad is. | `-> NoReturn`, met `response_model=None` (gemeten op FastAPI 0.121.1: zonder die vlag weigert de route te laden). | Opgelost |
| Low | `agent_control_unavailable.py` | Geen auditspoor bij een geweigerde besturingsactie. | Een reviewer moet kunnen zien waarom dat verdedigbaar is; alleen constateren is niet genoeg. | De reden staat nu in de docstring: een 501 is geen autorisatiebesluit (de aanroeper is al door de scope-check) en geen gegevensmutatie, dus geen van beide dingen die de ADR-019-keten vastlegt. | Opgelost |

---

## E. Ontbrekende items

Geen.

## F. Verbeterde tekstvoorstellen

Verwerkt in de spec zelf.

## G. Release-oordeel

- Geschikt voor implementatie: ja, de implementatie is af.
- Geschikt voor QA en geautomatiseerd testen: ja. 42 tests over de guard en de unittest, groen.
- Geschikt voor LLM-training: ja.
- Geschikt voor integratorhandleiding: ja, inclusief de afwijkende plek van de foutcode.

---

## Gemeten bewijs

| Meting | Uitkomst |
| --- | --- |
| `pytest tests/unit/api/test_pause_agent_pauses_or_fails_loud.py tests/architecture/test_agent_control_endpoints_do_not_fake_success.py` | 42 passed |
| Mutatie "validatie-raise naast een succes-return" op `pause_agent` | ROOD (1 failed, 23 passed) |
| Mutatie "weigering in EEN tak, succes in de andere" | ROOD (1 failed, 23 passed) |
| Mutatie "oude body terug" | ROOD (1 failed, 23 passed) |
| Tegenrichting "LEGITIEM: echt werk plus succes" | GROEN (24 passed) |
| Herstel na de mutatiereeks, bestand byte-identiek | 24 passed |
| `ruff check` op de vijf aangeraakte bestanden | All checks passed |
| `mypy` op de drie src-bestanden | Success: no issues found in 3 source files |
| `pyright` met expliciete bestandsargumenten | 0 errors, 0 warnings |
| Byte-scan op non-ASCII en regels > 100 tekens | 0 en 0 in alle vijf bestanden |

*Reviewer: onafhankelijke code-reviewer (Gate 2) | Datum: 2026-08-31*
