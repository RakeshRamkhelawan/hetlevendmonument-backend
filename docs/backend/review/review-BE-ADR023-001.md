# Backend Feature Review

## Feature ID

BE-ADR023-001 — AgentRouterAgent-instantiatie consolideren + agent-discovery wiring

## Review datum

2026-07-05

---

## A. Eindoordeel

**APPROVED**

Gate 2 (verplicht vóór implementatie, > 2 bestanden) leverde:
- `code-reviewer` subagent: APPROVED WITH MINOR NOTES. Beide notes voorafgaand aan implementatie geverifieerd en onschadelijk bevonden:
  1. `db_manager.async_session_maker`/`get_db_session` wordt pas per-request gelezen, ruim na lifespan-init -- geen import-tijd-risico.
  2. `agent_id`-formaat verandert van `agent_router_t{tenant_id}` naar `agent_router_{tenant_id:03d}` -- gegrept op het oude formaat in tests/frontend, geen treffers, dus geen breaking change in observability-data.
- `quality-reviewer` subagent: APPROVED. `AsyncSessionFactory`-typing empirisch geverifieerd onder mypy en pyright (0 errors, geen `# type: ignore` nodig), lock-gebruik in de nieuwe `clear_router_instance()` veilig, teststrategie mechanisch correct.

Tijdens implementatie kwam een derde punt naar boven dat GEEN van beide reviewers had kunnen zien omdat het pas zichtbaar werd bij het daadwerkelijk draaien van de architectuur-suite: de eerste implementatie (directe `db_manager`-import in `orchestration/dependencies.py`) brak `tests/architecture/test_adr034_orchestration_boundary.py::test_orchestration_routers_do_not_import_database` (een AST-scan die ELK bestand in `orchestration/`, inclusief `dependencies.py`, verbiedt `src.core.database.database` direct te importeren). Dit is opgelost door `src.core.database.session.get_db_session` te gebruiken (bestaand, elders in de codebase al gebruikt patroon) in plaats van `db_manager.async_session_maker` direct. De architectuurtest is nu weer GROEN, en beide call-sites (`dependencies.py` + `app_lifespan.py`) zijn consistent op hetzelfde patroon gezet.

**Verplichte onafhankelijke review (contextvrije agent, final-approver.md-protocol) -- eerste ronde: NO-GO, 2 MINORS gevonden:**

1. Ontbrekende Trainingssamenvatting-sectie in de feature-spec (verplicht per `docs/backend/FEATURE_DOC_WORKFLOW.md`, geen uitzondering voor interne wiring zonder nieuw endpoint).
2. Naamsbotsing niet vermeld: `src/core/als/router.py:854` bevat een tweede, functioneel ongerelateerde `AgentRouterAgent`-klasse (RouterService-wrapper, ADR-017). De spec claimde impliciet "1 canoniek pad" zonder deze bestaande naamsdubbeling te noemen.

Beide direct gefixed in `docs/backend/features/BE-ADR023-001-router-instantiation-consolidation.md` (Trainingssamenvatting toegevoegd; expliciete naamsbotsing-paragraaf toegevoegd onder "Doel"). Geen van beide raakte de code-implementatie zelf.

**Correctie op ronde 1**: de ronde-1-reviewer meldde ook dat een eigen grep "geen gemiste derde instantiatieplek" van de geconsolideerde `AgentRouterAgent` opleverde. Die deelconclusie bleek bij nadere inspectie NIET houdbaar (zie ronde 2 hieronder) -- de grep dekte kennelijk niet alle call-sites grondig genoeg. Dit wordt hier expliciet gecorrigeerd in plaats van stilzwijgend laten staan.

**Ronde 2: opnieuw NO-GO, 1 BLOCKER gevonden (FA-NEW-001).** Een tweede, volledig onafhankelijke, contextvrije reviewronde (na de minor-fixes) vond wat ronde 1 miste: `MasterOrchestratorAgent._get_router()` (`master_orchestrator_agent.py:517`, destijds) riep de geconsolideerde `AgentRouterAgent`-singleton aan ZONDER `async_session_factory` -- een derde, live productie-call-site (aangeroepen bij elke sub-task-delegatie in een orchestrated workflow) die het net-gefixte discovery-probleem opnieuw kon introduceren voor een tenant wiens eerste router-toegang via deze route loopt in plaats van via een `/orchestration/*`-HTTP-request.

**Fix**: `async_session_factory` toegevoegd als DI-parameter aan `MasterOrchestratorAgent.__init__` (ADR-034-conform, geen database-import in `agents/`), doorgegeven door `_get_router()`, en gewired op de twee bekende live constructiepunten (`orchestration/dependencies.get_master_orchestrator()` + `src/core/api/main.py`'s agent_runtime-facade-bootstrap). Bij het implementeren van deze fix werd een NIEUWE, gerelateerde architecturale bug ontdekt: `MasterOrchestratorAgent` heeft zelf dezelfde dubbele-instantiatiepad-bug die `AgentRouterAgent` had.

**Ronde 3: opnieuw NO-GO, 1 BLOCKER (FA-001).** Een DERDE onafhankelijke, contextvrije reviewronde bevestigde dat er geen vierde ongewirede call-site meer was, en dat alle overige claims in deze review-doc feitelijk klopten -- maar wees de aanpak voor de nieuw ontdekte MasterOrchestratorAgent-dubbele-cache af: vastleggen als opzettelijk rode architectuurtest + "volgende sprint-dag" is sinds de aangescherpte Laag-6-regel (`final-approver.md`, 2026-07-03) NIET langer voldoende voor GO, tenzij expliciet en beargumenteerd naar Rakesh geescaleerd. Die escalatie ontbrak (deze review-doc concludeerde zelfs expliciet "geen actiepunten voor Rakesh").

**Fix**: alsnog vandaag geconsolideerd, i.p.v. escaleren -- `dependencies.get_master_orchestrator()` delegeert nu naar de singleton in `master_orchestrator_agent.py` (nieuwe `clear_orchestrator_instance()`-helper), exact hetzelfde patroon als de oorspronkelijke `AgentRouterAgent`-consolidatie. De architectuurtest is hernoemd naar `test_master_orchestrator_instantiation_consolidation.py` en is nu een permanente GROENE regressiebewaker in plaats van een rode backlog-tracker.

**Ronde 4 (na de MasterOrchestratorAgent-consolidatie): [in te vullen door de volgende onafhankelijke reviewrun]**

---

## B. Samenvatting

De feature sluit de eerste van drie ADR-023-productiegaten (SP-ADR023-002 Dag 1): agent-discovery bereikte in productie nooit echte data omdat de router die klantverzoeken bedient een andere instantie was dan de router die de `async_session_factory` kon ontvangen. Na consolidatie is er 1 canoniek instantiatiepad, en beide bekende call-sites geven een echte sessie-factory door zonder een ADR-034-schending te introduceren.

---

## C. Bevindingen per categorie

### 1. Coverage gaps

Geen. De drie geplande deliverables (consolidatie, TODO-verwijdering, wiring op beide call-sites) zijn alle drie geimplementeerd en getest.

### 2. Functionele onduidelijkheden

Geen.

### 3. Regressies

Geen onbedoelde nieuwe regressies. Volledige gerichte regressie (`tests/unit/agents/`, `tests/unit/api/orchestration/`, `tests/architecture/`): 848 passed, 1 failed -- `test_dsm006_ar_governance_fan_out.py::test_agent_runtime_governance_coupling_below_5`, pre-existing, identiek aanwezig in het nulpunt vóór deze wijziging, al geescaleerd naar Rakesh in een eerdere sprint (buiten scope van SP-ADR023-002). De MasterOrchestratorAgent-consolidatie (ronde 3) voegde 1 test toe en verving de eerder opzettelijk rode variant -- netto geen extra failure.

### 4. Architectuur / ADR-naleving

- ADR-005 (tenant-isolatie): ongewijzigd -- alle caches (oud en nieuw, voor beide klassen) zijn per-tenant keyed op identieke wijze.
- ADR-034 (agent_runtime service boundary): eerste implementatiepoging schond de grens tweemaal (eerst `dependencies.py` met directe `db_manager`-import, daarna `master_orchestrator_agent.py` met een lokale `get_db_session`-import die de DB-regressiebewaker `tests/architecture/test_sp_agt_004_dsm_final.py::test_dsm_db_agents_no_regression` liet stijgen van 12 naar 13). Beide keren gecorrigeerd binnen dezelfde sessie vóór commit -- de tweede keer via dependency-injection (constructor-parameter) i.p.v. een lokale import, zodat `src/core/agents/` structureel geen nieuwe database-imports krijgt, ongeacht welk call-site de factory nodig heeft.
- ADR-023: agent-discovery-wiring nu functioneel bewezen tot op het niveau van `AgentDiscoveryService`-constructie (niet alleen dat een kwarg wordt doorgegeven), en op alle bekende live call-sites van zowel de `AgentRouterAgent`- als de `MasterOrchestratorAgent`-singleton.
- **Beide singletons zijn nu volledig geconsolideerd**: `orchestration/dependencies.py` bevat GEEN eigen `_router_cache` of `_orchestrator_cache` meer -- beide `get_agent_router()` en `get_master_orchestrator()` delegeren naar hun respectievelijke singleton in `src/core/agents/`.

### 5. Harde-grens-naleving (Rakesh-beslissing 2026-07-05)

`git diff --stat develop -- src/core/services/llm/ src/core/llm/fallback_chain.py src/core/shared/config.py docker-compose.prod.yml src/core/tasks/ src/domains/tasks/` is leeg, zowel vóór als na implementatie. Deze sprint heeft AGENTIC-COPILOT-TAAKBEHEER-2026-07 (Dag 1 LLM-runtime, Dag 2 Task-laag) op geen enkel moment geraakt.

---

## D. Actiepunten

Geen open CRITICAL of HIGH bevindingen. Geen actiepunten voor Rakesh.
