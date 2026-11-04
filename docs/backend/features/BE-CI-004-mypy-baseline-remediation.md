# Backend Feature Specification

## Metadata

- Feature ID: BE-CI-004
- Feature naam: mypy 0-baseline herstel (Redis-protocol, optional-import sentinels, ML-fallback stubs)
- Status: ACTIEF
- Auteur: Claude (SP-CI-001 Dag 5)
- Reviewer: code-reviewer subagent (GO/CHANGES_REQUESTED -- zie review-BE-CI-004.md) + quality-reviewer subagent (GO) -- beide vereist per CLAUDE.md Gate 2 (37 bestanden)
- Datum: 2026-07-15
- Gerelateerde user story / ticket: SP-CI-001 (CI Pipeline Herstel), vervolg op dag 4 (BE-CI-003)
- Gerelateerde router / module: 37 bestanden verspreid over `src/core/typing/`, `src/core/copilot/*`,
  `src/core/learning/*`, `src/core/agents/*`, `src/core/services/*`, `src/core/governance/`,
  `src/core/middleware/`, `src/core/api/v1/*`, `src/domains/agentic/*`, `src/workers/`,
  `src/core/database/redis.py`, `src/core/als/llm_integration/`, `src/core/autonomy/`,
  `src/core/infrastructure/`, `src/core/events/`, `src/core/ml/`, `src/core/security/`,
  `src/core/workflow/`
- Gerelateerde frontend endpoints: n.v.t.
- Gerelateerde database tabellen: n.v.t.
- Versie: 1.0

---

## Doel en scope

### Doel

Dag 3+4 loste de Any-type-gate volledig op (331 -> 0). Dag 5 pakt de resterende
mypy-baseline-schending aan: `python scripts/run_mypy_audit.py --fail-on-increase` vergelijkt
elk bestand tegen `mypy-baseline.json` (per-bestand 0, bereikt 2026-06-09, commit 33f3a982).
Bij de start van dag 5 stonden 43 fouten open over 23 bestanden -- accumulatie sinds die
baseline, niet door deze sprint veroorzaakt. Na dag 5: 0 fouten over de volledige `src/`-boom,
met een enkele expliciet beargumenteerde uitzondering (zie "Out of scope").

### In scope

Drie duidelijk te onderscheiden fix-clusters, elk apart geverifieerd:

1. **6 daadwerkelijk ongebruikte `# type: ignore[...]`-comments verwijderd** (bevestigd met de
   EXACTE project-invocatie `mypy src/` -- geen `--ignore-missing-imports`, een eerdere eigen
   fout die tijdig gecorrigeerd werd voor deze fixes werden toegepast):
   `redis_protocol.py:163`, `workflow/worker.py:35`, `council/policies/loader.py:55`,
   `audit/pdf_renderer.py:9`, `middleware/rate_limit_middleware.py:52`, `learning/ppo_trainer.py:38`.

2. **`# type: ignore[type-arg]` toegevoegd op ~24 regels in ~18 bestanden** voor
   `redis.Redis`/`RedisCluster`/`ConnectionPool` generic-subscripting. Empirisch geverifieerd
   (niet aangenomen) dat alle drie deze classes crashen op `typing.get_type_hints()` zodra ze
   geparametriseerd worden -- exact het patroon uit `.claude/rules/code-quality.md`'s
   mei-2026-incident. `black --check` nadien: 8 bestanden hadden herformattering nodig,
   toegepast + opnieuw geverifieerd (geen enkele ignore-comment losgemaakt door de
   her-wrapping -- zie punt 3 voor de ene plek waar dat wel gebeurde).

3. **~40 case-by-case fixes**, elk gelezen en begrepen (niet gescript) per
   `.claude/rules/code-quality.md`'s "never bulk-fix mypy errors"-regel:
   - `cast()` toegevoegd op Redis-protocol-grensvlakken: `redis_protocol.py` (2x, factory-
     functies), `session_manager.py` (1x), `runtime_adapter.py` (2x, `ExecutionResult`),
     `model_registry.py` (2x, `ModelVersion` via forward-ref string-cast omdat de echte
     import alleen onder `TYPE_CHECKING` bestaat), `rate_limiter.py` (1x, `bool`).
   - `aclose()` toegevoegd aan de `AsyncRedisClient`-Protocol in `redis_protocol.py` -- een
     echte runtime-methode die ontbrak in het Protocol (redis-py's async client gebruikt
     `aclose()`, niet alleen `close()`).
   - `# type: ignore[<specifieke code>]` op conditional-import "sentinel"-patronen
     (`X = None` in een `except ImportError:`-tak die een eerder als module/class
     getypeerde naam herbindt): `rbac_service.py` (`Aioredis`, class-sentinel,
     `[misc, assignment]`), `mlflow_integration.py` + `experiment_tracker.py`
     (`mlflow`/`wandb`, module-sentinel, `[assignment]`), `focus_generator.py`
     (`ChatOpenAI`, class-sentinel, `[misc, assignment]`), `ppo_trainer.py`
     (`BaseCallback`, class-sentinel, `[misc, assignment]`, plus een ontbrekende
     `[empty-body]`-ignore op de `learn()`-stub-methode, consistent met de al aanwezige
     ignores op de buurmethodes `predict`/`step`).
   - `mlflow_integration.py`: `self.tracking_uri = tracking_uri or os.getenv(...)` gaf
     `str | None` volgens mypy (mypy narrowt `or`-expressies niet zoals verwacht, ook niet
     met een expliciete `os.getenv(key, str_default)`-aanroep). Opgelost met
     `str(tracking_uri or os.getenv(...))` -- een runtime-no-op (de waarde was al een str)
     die mypy's inferentie naar het juiste type dwingt zonder een ignore-comment nodig te
     hebben.
   - `training_service.py`: `# type: ignore[list-item, return-value]` op de
     `DummyVecEnv([lambda: CustomEnv/CurriculumEnv(...)])`-aanroepen (2x) -- lokale
     `Env`-subclasses matchen niet generiek met gymnasium's `Env[Any, Any]`.
   - `providers.py`: `# type: ignore[attr-defined]` op 3 plekken voor de legacy
     `google.generativeai`-SDK (`configure`, 2x `GenerativeModel`) -- een reeds
     gedeprecieerd fallback-pad achter een `except ImportError`-guard.
   - `experience_replay.py`: `# type: ignore[arg-type]` op 3 `ensure_async(...)`-aanroepen --
     een gedocumenteerde, bekende mypy-beperking in `ensure_async`'s eigen docstring
     (Union[Awaitable[T], T]-TypeVar-inferentie is inherent ambigu voor mypy).
   - `analytics_ingest/dependencies.py`: expliciete `current_user: UserResponse`-annotatie
     toegevoegd (was eerder ongetypeerd `Depends(...)`-argument).
   - `workflow_worker.py`: `# type: ignore[no-untyped-call]` op `StubBroker()`
     (dramatiq heeft geen type-stubs).
   - `core/workflow/worker.py`: `-> AsyncIterator[AsyncSession]`-return-annotatie toegevoegd
     aan een geneste `async def worker_db_session()`-generator (was ongetypeerd).
   - `copilot/council/policies/loader.py`: `# type: ignore[misc]` op de
     `@cached(cache=_POLICY_CACHE)`-decorator -- `cachetools` heeft geen py.typed-marker en
     geen stub-package geinstalleerd (expliciet geverifieerd, niet aangenomen).

### Black-reformattering-detectie (herhaling van dag 3/4-patroon)

Tijdens verificatie na black's herformattering (8 bestanden hadden `black --line-length 100`
nodig) werd een derde black-detachement-geval gevonden in `pdf_renderer.py`: een
pre-existing, reeds-te-lange regel (`return cast(bytes, weasyprint.HTML(...).write_pdf())`,
122 tekens, ongerelateerd aan deze diff's eigen wijziging op een andere regel in hetzelfde
bestand) werd door black over 3 regels gewrapt, waarbij het bestaande
`# pyright: ignore[reportPossiblyUnboundVariable]`-commentaar op de verkeerde
(sluit-haakjes-)regel terechtkwam in plaats van op de regel met `weasyprint`. Dit veroorzaakte
een ECHTE nieuwe pyright-fout (bevestigd via `python scripts/run_pyright_audit.py
--fail-on-increase` voor en na). Gefixed door de aanroep te herstructureren zodat het
ignore-commentaar op de regel met `weasyprint` blijft staan, ongeacht toekomstige
re-wrapping. Geverifieerd: 0 pyright-fouten voor dit bestand na de fix.

**Correctie (2026-07-15, na de verplichte onafhankelijke review):** deze detectie was
NIET volledig -- de eigen verificatie tijdens deze dag miste 2 aanvullende, echte nieuwe
pyright-fouten in `src/core/learning/ppo_trainer.py`, gemaskeerd doordat dit bestand al
baseline-headroom had (3 toegestane fouten, 2 aanwezig na de regressie -- de audit-tool
signaleert daarom geen "toename"). Beide zijn dezelfde black-detachement-faalklasse:
1. Regel 100 (`class MemoryAugmentedCallback(BaseCallback):`): het verwijderen van de
   "voor mypy unused" `# type: ignore[misc]` (onderdeel van deze diff's Task 1) verwijderde
   tegelijk pyright's blanket-suppressie van een andere, echte fout
   (`reportGeneralTypeIssues: Argument to class must be a base class`) -- pyright
   interpreteert de haakjes-inhoud van een `# type: ignore[...]` niet, dus elke
   bracketed-ignore onderdrukt ALLE pyright-diagnoses op die regel, ongeacht de specifieke
   mypy-code erin.
2. Regel 27 (`from stable_baselines3.common.vec_env import (DummyVecEnv, ...)`): black
   wrapte deze import over 3 regels, waarbij het bestaande
   `# pyright: ignore[reportAssignmentType]` op de sluitende-haakjes-regel terechtkwam i.p.v.
   op de regel met `DummyVecEnv` zelf -- identiek patroon aan `pdf_renderer.py` hierboven.

Gevonden door de onafhankelijke Final-Approver-review (niet door de oorspronkelijke Gate-2
review of de eigen verificatie), via een directe parent-commit-vs-child-commit
per-bestand/per-regel-diff van de volledige pyright-JSON-output (canonical scope), NIET via
`run_pyright_audit.py --fail-on-increase` alleen (die tool maskeerde de regressie door de
baseline-headroom). Beide GEFIXED (2026-07-15): regel 100 kreeg een specifiek-gecodeerde
`# pyright: ignore[reportGeneralTypeIssues]`; regel 27's ignore-comment verhuisde naar de
juiste regel. Geverifieerd met een directe parent-vs-child pyright-diff: dit waren de ENIGE
2 nieuwe fouten in de volledige 37-bestanden-diff -- na de fix toont de diff 0 verschillen
t.o.v. de parent-commit.

### Out of scope

- `src/core/governance/dsar_service.py` (3 resterende mypy-fouten,
  `ConversationMemory`-argumenttype-mismatch x2 + een dict-vs-CVAConversation-mismatch x1):
  BEWUST NIET gefixed. Dit bestand is gisteren (2026-07-13) gewijzigd door een gelijktijdig
  lopende, aparte GDPR-sprintiteratie (`iter/dag7-gdpr`, commit `17fa1e5e`) die actief
  hetzelfde codepad ontwikkelt. Aanraken zou een echte git-commit-race riskeren
  (zie project-geheugen `valkuil_parallel_iteration_commit_race.md`). Geverifieerd via
  `git log`/`git blame` dat dit de enige overgebleven mypy-schending is na deze dag se werk.
- `src/core/copilot/conversation_memory.py`: draagt 1 pre-existing `# type: ignore[type-arg]`
  op de constructor, toegevoegd tijdens een eerdere Task-2-batch (voor de GDPR-eigendoms-
  conflict ontdekt werd). Triviale comment-only wijziging, geen functionele impact; niet
  teruggedraaid omdat het een correcte, geisoleerde fix is die niets van de GDPR-sprint's
  eigen werk raakt.
- 2 pre-existing pyright-fouten (`events_router.py` x2, `audit_endpoints.py` x1): bevestigd
  via `git blame` dat deze bestanden voor deze diff niet zijn aangeraakt (laatste wijziging
  resp. 2026-07-14 en 2026-07-10, beide door Rakesh direct, ongerelateerd aan SP-CI-001).
  `pyright-baseline.json` bevat geen entry voor deze bestanden (default 0), dus elke
  bestaande fout wordt door de audit-tool als "toename" gerapporteerd -- zelfde
  baseline-gat-patroon als de mypy-tool eerder liet zien voor `dsar_service.py`.
- Het daadwerkelijk vervangen van `Any`/`dict[str, Any]` door concrete types -- buiten
  scope van een mypy-baseline-herstel-dag, zie dag 3/4 voor dezelfde afweging.
- De 3 pip-audit CVE's (pyasn1/chromadb/ecdsa) die tijdens deze dag zichtbaar werden in
  PR #148's CI-run: apart gescoped als SP-CI-001 dag 6 (zie sprint-opstarten-brief).

---

## Build summary

- Gewijzigd: 37 bestanden onder `src/` -- typing-only wijzigingen (ignore-comments met
  specifieke codes, `cast()`-aanroepen, 1 Protocol-methode-toevoeging, 2
  return-type-annotaties, 1 parameter-type-annotatie, 1 `str()`-wrap voor mypy-narrowing),
  gevolgd door `black --line-length 100` op 8 bestanden die her-formattering nodig hadden.
- Nieuw gebouwd: geen.
- Verwijderd: 6 daadwerkelijk-ongebruikte `# type: ignore[...]`-comments.
- Beinvloede bestaande flows: geen functionele wijziging -- bevestigd door beide Gate-2-
  subagents onafhankelijk (zie review-BE-CI-004.md): elke `cast()` is een runtime-no-op,
  elke ignore-comment onderdrukt uitsluitend een type-checker-diagnose, geen enkele
  control-flow/auth/tenant_id/SQL-aanroep is gewijzigd.

---

## Verificatie

```bash
python scripts/run_mypy_audit.py --fail-on-increase
# -> Total errors: 3; Baseline errors: 0; Files with errors: 1
#    ERROR: src/core/governance/dsar_service.py: 0 -> 3 (+3)
#    (bewust buiten scope, zie hierboven -- dit bestand zit niet in de 37 gewijzigde bestanden)

python scripts/run_pyright_audit.py --fail-on-increase
# -> Errors: 7; Warnings: 11
#    ERROR: events_router.py: 0 -> 2, audit_endpoints.py: 0 -> 1
#    (beide bevestigd pre-existing via git blame, buiten de 37 gewijzigde bestanden)

black --check --line-length 100 <37 gewijzigde bestanden>
# -> idempotent na toegepaste herformattering (8 bestanden opnieuw geformatteerd + geverifieerd)

ruff check <37 gewijzigde bestanden>
# -> All checks passed!

python -m py_compile <37 gewijzigde bestanden>
# -> alle 37 slagen
```

Gate 2 (code-reviewer + quality-reviewer, beiden onafhankelijk, parallel gedraaid):
zie `review-BE-CI-004.md` voor het volledige verdict en de bevindingen.

---

## Trainingssamenvatting

- Actor: CI/CD-onderhouder (Rakesh) die `python scripts/run_mypy_audit.py --fail-on-increase`
  draait als onderdeel van de lokale pre-push-hook of de CI-pipeline.
- Voorwaarde: de codebase bevat 43 mypy-fouten over 23 bestanden t.o.v. de 0-baseline
  (`mypy-baseline.json`), geaccumuleerd sinds de baseline op 2026-06-09 werd bereikt.
- Actie: de onderhouder draait de audit-tool.
- Systeemreactie: v66r de fix toont het commando `ERROR: mypy errors increased in these
  files: ...` en exit-code 1; na de fix toont het `OK: No files increased their mypy error
  count.` (op de 3 bewust-buiten-scope `dsar_service.py`-fouten na, die apart en zichtbaar
  gerapporteerd blijven totdat de GDPR-iteratie ze afrondt).
- Succes: `run_mypy_audit.py --fail-on-increase` retourneert exit-code 0 voor alle 37
  gewijzigde bestanden; de CI-pyright/mypy-stap kan op termijn `continue-on-error: true`
  verliezen zodra `dsar_service.py` ook is opgelost.
- Fout: als een toekomstige wijziging een van de 37 bestanden opnieuw laat regresseren, faalt
  de audit-tool opnieuw met een specifieke per-bestand foutmelding (bestand + delta), zodat de
  regressie direct herleidbaar is naar de veroorzakende commit.
- Uitzonderingen: `dsar_service.py` (GDPR-sprint-eigendom, 3 fouten, expliciet uitgesloten) en
  de 2 pre-existing pyright-fouten in `events_router.py`/`audit_endpoints.py` (buiten deze
  37 bestanden, ongerelateerd aan deze fix).

## Open aannames

- Zelfde als dag 3/4: concrete vervanging van `Any`/`dict[str, Any]` per module vereist een
  aparte type-ontwerp-sprint.
- `dsar_service.py`'s 3 resterende fouten worden opgepakt zodra de GDPR-iteration klaar is
  met dat bestand, of in een expliciet volgende SP-CI-001-dag als Rakesh dat zo beslist.

## Open vragen

- Moet `continue-on-error: true` op de mypy-stap in `.github/workflows/ci-feature.yml`
  verwijderd worden nu de baseline (op 3 GDPR-gerelateerde fouten na) genuine 0 is? Voorstel
  voor Rakesh: wachten tot `dsar_service.py` is opgelost, dan de stap echt hard maken.
- De 3 pip-audit CVE's (pyasn1/chromadb/ecdsa) zijn zichtbaar geworden op PR #148 (fork-sync);
  bevestiging gevraagd dat dit exact de dag-6-scope is uit de sprint-opstarten-brief.

## Risico's

- Laag: uitsluitend typing-only wijzigingen, 0 nieuwe mypy/pyright-fouten t.o.v. de
  pre-dag-5-staat (geverifieerd met exacte baseline-audit-tools, niet met een losse
  `mypy src/`-aanroep die de baseline-context mist).
- `conversation_memory.py`'s pre-existing wijziging (1 regel) raakt een bestand dat een
  parallelle sprintiteratie actief onderhoudt -- laag risico (comment-only, geen
  logica-wijziging) maar wel expliciet gemeld aan Rakesh voor transparantie.

---

## QA-checks

- [x] mypy-baseline: 0 nieuwe fouten over de 37 gewijzigde bestanden (3 resterende, bewust
      buiten scope, in een niet-gewijzigd bestand)
- [x] pyright: 0 nieuwe fouten over de 37 gewijzigde bestanden (3 resterende, pre-existing,
      in niet-gewijzigde bestanden)
- [x] black/ruff: alle groen, idempotent
- [x] Elke toegevoegde `# type: ignore`/`# pyright: ignore` draagt een specifieke code (geen
      enkele naakte ignore) -- expliciet geverifieerd door quality-reviewer
- [x] Geen secrets/tenant_id/auth/SQL-logica geraakt -- expliciet geverifieerd door beide
      Gate-2-subagents
- [x] ASCII-only in alle wijzigingen

---

## Definition of Done

- [x] Fix is aangebracht (43 mypy-fouten -> 0 over 37 bestanden, 3 bewust buiten scope)
- [x] Gate 2: code-reviewer + quality-reviewer subagents, parallel gedraaid (zie
      review-BE-CI-004.md)
- [ ] Geen nieuwe regressies (volledige pytest-suite: zie final-approver-brief dag 5)
- [x] black --check idempotent over alle 37 bestanden
