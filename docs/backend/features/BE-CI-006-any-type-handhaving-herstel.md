# Backend Feature Specification

## Metadata

- Feature ID: BE-CI-006
- Feature naam: Any-type handhaving herstel -- de gate vuurde nergens en de teller was niet reproduceerbaar
- Status: ACTIEF
- Auteur: Claude
- Reviewer: zelfreview per bestand. Gate 2 vraagt hier een code-reviewer en een
  quality-reviewer subagent; de sessie draaide met de instructie geen subagents te starten.
  Dit is een bewuste, benoemde afwijking en geen vergetelheid -- zie "Openstaand" onderaan.
- Datum: 2026-08-13
- Gerelateerde user story / ticket: vervolg op BE-CI-002 en BE-CI-003 (SP-CI-001 dag 3/4)
- Gerelateerde router / module: `scripts/scan_any_usage.py`, `scripts/check_any_gate.py`,
  `scripts/inject_any_todos.py`, `frontend/scripts/check-any-gate.mjs`,
  `.github/workflows/ci-feature.yml`, `scripts/hooks/pre-commit`, `.pre-commit-config.yaml`
- Gerelateerde frontend endpoints: n.v.t.
- Gerelateerde database tabellen: n.v.t.
- Versie: 1.0

---

## Doel en scope

### Doel

De vraag was een "ratel" bouwen die het aantal `Any`'s alleen omlaag laat gaan. Die ratel
bestond al sinds mei/juni. Onderzoek op develop leverde op dat hij op drie punten niet
werkte, en elk van die drie is ernstiger dan een ontbrekende ratel.

**1. Er handhaafde niets, nergens.**

De CI-stap "Any-type gate" stond er sinds mei en heeft geen enkel bestand gecontroleerd.
Drie onafhankelijke oorzaken, alle drie lokaal gereproduceerd:

- `ci-feature.yml` zette nergens `fetch-depth`, dus de runner haalt precies een commit op en
  `origin/develop` bestaat daar niet. `git diff origin/develop...HEAD` faalde, `|| true`
  slikte de fout op, `CHANGED` werd leeg en de stap meldde "skipping" -- groen, in elk
  event-type.
- Ook met een geldige ref is `origin/develop...HEAD` bij een push naar develop een leeg
  bereik, en al het werk gaat rechtstreeks naar develop.
- De frontend-stap draaide met `working-directory: frontend` maar met de pathspec
  `frontend/src/**/*.ts`. Vanuit die cwd matcht dat nul bestanden, en de paden die het script
  wel kreeg verdwenen in een lege `catch {}`.

Lokaal was het niet beter. `.git/hooks/pre-commit` was een handgeschreven, **untracked**
bash-script uit december 2025 dat alleen Alembic-migraties valideerde. `scripts/hooks/`
bevatte alleen een `pre-push`, en `ci-local-fast.sh` (de pre-push-gate) heeft de any-gate
nooit gehad. `pre-commit install` was nooit gedraaid, dus alle hooks in
`.pre-commit-config.yaml` -- inclusief `any-type-gate` -- stonden zeven maanden op papier.

De baseline-monitor die het net had moeten zijn draaide alleen op `schedule` en
`workflow_dispatch`, en cron draait op de default branch `main` terwijl al het werk naar
develop gaat. Precies het patroon dat bovenaan diezelfde workflow al beschreven staat voor
de mypy-drift.

**2. De meting was niet reproduceerbaar.**

Tijdens het onderzoek verschoof het getal onder handen: 34 -> 36 violations, 168 -> 170
usages, op een working tree die bit-voor-bit gelijk was aan HEAD en waarin geen enkel
`.py`-bestand in een uur was aangeraakt. De nieuwkomer was `src/workers/workflow_worker.py`
(tracked, niet genegeerd, mtime van acht uur eerder). Drie bewezen mechanismen:

- `scan_file()` had `except Exception: return []`. Een bestand dat niet gelezen kan worden
  telde stil als nul. Aangetoond: een niet-bestaand pad, een directory en een binair bestand
  gaven alle drie `[]` zonder enig signaal. Deze repo staat in OneDrive met PINNED-attributen;
  hydratatie is precies zo'n transiente leesfout.
- `get_candidate_files()` shelde uit naar `grep -rl` met `timeout=60` en ving met
  `except Exception` ook `TimeoutExpired`, waarna het stil terugviel op een `rglob`-walk over
  een andere bestandsset. Onder belasting gaf dezelfde boom dus een ander totaal.
- De pathspec was ambigu: hetzelfde getal is 8392 met `src/` en 8386 met `src/**/*.py`.

Een gate op exacte gelijkheid bovenop deze scanner produceert rode builds zonder oorzaak.
Daarom is de meting eerst gerepareerd en de ratel daarna.

**3. De teller was met een commentaarregel te verlagen.**

`scan_any_usage.py` beschouwde een regel met `# TODO(TYPE)` als legitiem en telde hem daarna
helemaal niet meer mee, en `scripts/inject_any_todos.py --apply` plakt precies dat comment
achter de regel. Zo "losten" BE-CI-002 en BE-CI-003 in juli 331 violations op en noteerden
"volledige src/ nu 0 violations", terwijl er nu 8392 van die markers in de codebase staan.

### Scope

In scope: de meting betrouwbaar maken, de handhaving daadwerkelijk aansluiten (CI en lokaal),
de twee tellers scheiden, de ratel strikt maken, de 40 ongeboekte `Any`'s boeken en beide
baselines vastleggen.

Buiten scope: het afbouwen van de 7892 geboekte `Any`'s. Dit levert een teller die niet meer
kan weglopen; het wegwerken van de schuld is apart werk per domein, gekoppeld aan functioneel
werk. Ook buiten scope: mypy of pyright aanraken (baseline 0, gepind op 2.3.0) en het
koppelen van het pre-commit framework (zie "Bewuste afweging").

---

## Gemeten stand

| Wat | Voor | Na |
| --- | --- | --- |
| `Any` zonder acknowledgement (`--mode violations`) | 36 in src, 4 in scripts | 0 |
| Geboekte `Any` (`--mode acknowledged`) | 7856 | 7892 |
| Expliciete `any` in `frontend/src` | 472 | 472 |
| Wat `docs/any_type_baseline.json` beweerde | 0, van 2026-06-25 | 7892, mode + scope vastgelegd |
| CI-stappen die de gate uitvoeren | 0 | 4 blokkerend (2 backend, 2 frontend) |
| Lokale hooks die de gate uitvoeren | 0 | 1, tracked |

Het getal 1015 uit de oorspronkelijke vraagstelling is met geen enkele projecteigen meting te
reproduceren.

---

## Implementatie

### Twee tellers uit een codepad

`LEGITIMATE_PATTERNS` is gesplitst:

- `STRUCTURAL_PATTERNS` -- `Any` is hier de juiste annotatie en blijft dat (`*args: Any`,
  `**kwargs: Any`, `Callable[..., Any]`, `typing.cast`, `isinstance`, `Protocol`,
  `@abstractmethod`, `overload`, de dunders, `Any = None`). Telt in geen van beide getallen.
- `ACKNOWLEDGEMENT_PATTERNS` -- bewust geboekte schuld (`# TODO.*Any`, `# FIXME.*Any`,
  `# HACK.*Any`, `# type: ignore`, `-> Any #`, `# replace.*Any.*type`). Telt **wel** mee.

`scan_file()` geeft nu alle niet-structurele regels terug met een `acknowledged`-vlag, en
`select(usages, mode)` is het enige punt waar de twee getallen uit elkaar gaan. Ze komen uit
dezelfde scan en kunnen dus niet uit elkaar lopen.

Waarom het ratel-getal `acknowledged` is en niet een ruwe telling van alle `Any`-regels: die
ruwe telling (7808 in een tussenmeting) is een artefact. Ze telt regels in plaats van
voorkomens -- `def f(a: Any, b: Any) -> Any` telt als 1 van de 3 -- en de patronen matchen op
de hele regel, dus elke regel met het woord `Protocol` erin valt weg. Als gate onbruikbaar.
`acknowledged` is niet met een comment te verlagen: een marker weghalen zonder de annotatie te
fixen maakt het een violation, en die gate staat op 0.

### Determinisme

- Leesfouten zijn nu een `UnreadableFileError` met pad en oorzaak.
- Bestandsontdekking via `git ls-files -z --full-name` met `check=True`, uitgevoerd met
  `cwd=repo_root()`. Geen terugval: een tweede codepad betekent een tweede getal. Untracked en
  genegeerde bestanden vallen daarmee weg, wat lokaal en CI gelijktrekt.
- Dezelfde telfunctie schrijft de baseline en controleert hem, dus de pathspec-ambiguiteit kan
  per definitie niet meer optreden.
- `scan_any_usage.py` negeerde zijn argumenten en schreef altijd
  `any_usage_scan_report.md` in de repo-root, ook bij `--help`. Nu argparse met een optionele
  `--report PATH`.

### De ratel

`--baseline` faalt bij **elke** afwijking, omhoog en omlaag. Dalen is net zo goed een fout:
zolang de baseline hoger staat kan het getal ongemerkt terugkruipen, en dat was letterlijk de
oude "INFO: consider updating the baseline"-tak. De baseline legt `mode` en `scan_dirs` vast en
weigert een vergelijking met een andere teller of scope. Alleen `total` wordt hard vergeleken;
`per_file` dient om bij een afwijking te tonen welk bestand bewoog -- zonder dat is een
verschil op bijna 8000 niet te debuggen.

### CI

`fetch-depth: 0` op beide gate-jobs. De basis komt per event uit de juiste bron
(`pull_request.base.sha` bij een PR, `github.event.before` bij een push). Is er geen bruikbare
basis of is het bereik leeg, dan volgt een **volledige scan** in plaats van een stille
`exit 0` -- fail-closed. De frontend-stap draait vanaf de repo-root.

Let op de asymmetrie in de terugval: de backend gebruikt `--fail` over de hele boom (de
violations-baseline is 0), de frontend de ratel (472 bestaande `any`'s, dus een volledige
`--fail`-scan zou altijd rood zijn). Dat is tijdens het bouwen gemeten en gecorrigeerd; zonder
dat onderscheid zou de frontend-job permanent falen.

### Bewuste afweging: het pre-commit framework blijft ongekoppeld

`.pre-commit-config.yaml` alsnog koppelen zou black, isort **en** ruff-format aanzetten op elke
gestagede file onder `src/`, `tests/` en `scripts/`. Volgens `.claude/rules/quality-gates.md` is
ongeveer een derde van `src/` nooit geformatteerd, dus die formatters herschrijven regels die de
committer niet heeft aangeraakt -- precies de onreviewbare diff die daar verboden wordt. Er
werkte tijdens deze wijziging ook een tweede iteratie in dezelfde working copy, die daar
ongevraagd in mee zou gaan.

In plaats daarvan is `scripts/hooks/pre-commit` toegevoegd (tracked, geinstalleerd door
`install-hooks.sh`): any-gate backend, any-gate frontend, en de Alembic-validatie uit het oude
untracked script. De kop van `.pre-commit-config.yaml` legt vast dat het bestand niet gekoppeld
is en waarom.

---

## Verificatie

| Wat | Uitkomst |
| --- | --- |
| Stabiliteit: 3 identieke runs op een onveranderde boom | 36/36/36 en 7774/7774/7774 |
| Ratel omhoog (baseline lager) | rood |
| Ratel omlaag (baseline hoger) | rood, met "GEDAALD" |
| Ratel gelijk | groen |
| Baseline zonder `mode` | rood |
| Baseline met andere scope | rood |
| Scope-normalisatie `src` vs `src/` | groen (was rood, gecorrigeerd) |
| Onleesbaar bestand | `UnreadableFileError`, geen lager getal |
| CI-shell: BASE_SHA leeg / onbereikbaar / geldig | terugval, terugval, diff-pad |
| CI-shell mutatie: kale `Any` in het diff-pad | non-zero |
| pre-commit hook: kale `Any` gestaged | commit geblokkeerd met ANN-ANY-melding |
| pre-commit hook: geboekte `Any` gestaged | commit gaat door |
| Architecture-guard, 5 mutaties | alle 5 rood; onveranderd 10 groen |
| ruff / mypy / pyright | schoon / 0 / 0 errors |
| Gerichte tests (tool_broker + scripts) | 257 passed |

---

## Trainingssamenvatting

### Flow 1 -- een ontwikkelaar committeert een nieuwe bare `Any`

- Actor: ontwikkelaar (of AI-assistent) die code committeert
- Voorwaarde: `bash scripts/install-hooks.sh` is een keer gedraaid
- Actie: `git commit` met een gestaged bestand onder `src/` of `scripts/` dat een
  `x: Any` bevat zonder `# TODO(TYPE)` of `# type: ignore`
- Systeemreactie: `scripts/hooks/pre-commit` roept `check_any_gate.py --fail` op de
  gestagede bestanden en breekt de commit af met de regel, het regelnummer en drie
  fix-opties
- Succes: de commit gaat door zodra het type concreet is gemaakt of de schuld expliciet
  geboekt is
- Fout: de commit wordt geweigerd met exit 1 en de melding `[ANN-ANY GATE]`
- Uitzonderingen: structurele gevallen (`*args: Any`, `**kwargs: Any`,
  `Callable[..., Any]`, protocols, `@abstractmethod`, `overload`) worden nooit geweigerd

### Flow 2 -- iemand lost geboekte schuld op

- Actor: ontwikkelaar die een `Any` vervangt door een concreet type
- Voorwaarde: het bestand staat in de scope `src/` of `scripts/`
- Actie: de marker verdwijnt samen met de `Any`, en de wijziging wordt gepusht
- Systeemreactie: de ratel-stap meet een LAGER getal dan `docs/any_type_baseline.json` en
  faalt met "GEDAALD", plus het commando om de nieuwe stand vast te leggen
- Succes: `check_any_gate.py --mode acknowledged --write-baseline docs/any_type_baseline.json`
  klikt de winst vast; de verlaging is daarna een reviewbare regel in de diff
- Fout: zolang de baseline niet is bijgewerkt blijft CI rood -- bewust, want een niet
  vastgeklikte daling laat het getal ongemerkt terugkruipen
- Uitzonderingen: geen. Ook een daling vereist een expliciete boeking

### Flow 3 -- CI kan de diff-basis niet bepalen

- Actor: GitHub Actions, bij een schedule-run, een `workflow_dispatch` of een push waarvan
  de basis-commit niet bereikbaar is
- Voorwaarde: `BASE_SHA` is leeg of verwijst naar een commit die niet in de runner staat
- Actie: de stap "Any-type gate" start
- Systeemreactie: de stap valt terug op een VOLLEDIGE scan (backend) of op de ratel
  (frontend), en meldt dat expliciet in de log
- Succes: de scan slaagt en de stap is groen omdat er daadwerkelijk gecontroleerd is
- Fout: de scan vindt een violation en de stap is rood
- Uitzonderingen: geen. De stap mag nooit succesvol eindigen zonder te hebben gecontroleerd
  -- dat was de oude `exit 0` en de reden dat de gate maanden onzichtbaar niets deed

---

## Wat de CI-runs hebben opgeleverd (bijgewerkt 2026-08-13)

De eerste twee runs op develop leverden twee bevindingen op die met een enkele machine niet te
vinden waren. Beide zijn gerepareerd; de details staan in de review.

- **De teller hing af van de Python-minorversie.** Run 31682177276 zette mijn eigen ratel rood:
  baseline 7896, gemeten 7892. `tokenize` deelt f-strings vanaf 3.12 anders op dan op 3.11, en
  de stringdetectie voegde alleen de regels toe waar een token begon. Twee interpreters op
  dezelfde boom gaven 9 tegen 5 Any-regels in `agent_factory.py`. De runner had gelijk.
  Baseline nu 7892, identiek op 3.10 en 3.13.
- **De frontend-gate miste `any` aan het regeleinde in CRLF-bestanden.** De patronen eindigen
  op `$` zonder m-vlag; 1884 bestanden onder `frontend/src` hebben lokaal CRLF. Vandaag nul
  instanties, dus lokaal en CI gaven beide 472 -- toeval, geen garantie.

En het doel is gehaald: de log van run 31682177276 zegt `Geen gewijzigde Python-bronbestanden
in 724d96f2...HEAD; volledige scan als vangnet.` De basis-commit was bereikbaar en het lege
bereik leidde tot een echte volledige scan. De oude stap had daar "skipping" gemeld en groen
gestaan. Op run 31684116372 zijn beide ratel-stappen en pyright groen.

## Openstaand

- **Gate 2 subagent-review is NIET gehaald.** Drie pogingen op 2026-08-13; alle zes subagents
  stierven op een API-fout (twee keer 529, daarna een sessielimiet tot 14:00). De review in
  `docs/backend/review/review-BE-CI-006.md` is een zelfreview en dat is volgens CLAUDE.md
  onvoldoende voor deze omvang. Moet opnieuw voor de merge naar `main`.
- **Een failure op develop die niet van deze wijziging is.** Run 31684116372 faalde op
  `tests/unit/workers/test_worker_initialiseert_de_database.py` met een
  `subprocess.TimeoutExpired` na 600s. Dat bestand hoort bij de OP-136-commits van een
  parallelle iteratie; de enige aanraking van `src/workers/` hier zijn twee commentaarregels.
- **De 7892 afbouwen** is niet gedaan en hoort per domein aan functioneel werk gekoppeld te
  worden.
