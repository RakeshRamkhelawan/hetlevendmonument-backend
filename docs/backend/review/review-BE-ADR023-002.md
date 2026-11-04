# Backend Feature Review

## Feature ID

BE-ADR023-002 — Redis-cache cross-worker wiring op AgentRouterAgent/MasterOrchestratorAgent

## Review datum

2026-07-06

---

## A. Eindoordeel

**APPROVED**

Gate 2 (verplicht vóór implementatie, > 2 bestanden) leverde:

- `code-reviewer` subagent: **APPROVED WITH MINOR NOTES**. Bevestigde dat de "wire alle 4 call-sites in één keer"-aanpak proportioneel en geleerd was van Dag 1 (niet een scope-uitbreiding tijdens de review, maar vooraf al vastgelegd in de rode Dag-2-tests). Vond 1 reeel regressierisico (zie quality-reviewer, hieronder overlappend) en 1 concrete verbetering: fail-graceful `try/except` rond `await get_redis_client()` in `dependencies.py`, naar het precedent in `src/core/api/v1/agentic/dependencies.py::get_adaptation_service()`. **Overgenomen**: nieuwe `_get_redis_client_fail_graceful()`-helper.
- `quality-reviewer` subagent: **CHANGES_REQUESTED** (eerste ronde). Vond een reeel, mechanisch regressierisico: 3 bestaande testbestanden (`test_orchestration_dependencies.py`, `test_dependencies_router_consolidation.py`, en -- door de code-reviewer aangevuld -- `test_master_orchestrator_instantiation_consolidation.py`) riepen `dependencies.get_agent_router()`/`get_master_orchestrator()` synchroon aan zonder `await`. Na de geplande `async def`-conversie zouden deze tests stil verkeerd falen (coroutine i.p.v. object). **Opgelost vóór implementatie**: alle 3 bestanden geconverteerd naar `async def` + `await` + gemockte `get_redis_client`.

Beide reviewers bevestigden onafhankelijk: geen andere gemiste productie-call-site, geen ADR-034-schending, geen tenant-isolatie-risico.

**Verplichte onafhankelijke review (contextvrije agent, final-approver.md-protocol) -- eerste ronde: NO-GO, 1 BLOCKER (FA-001).** Ondanks correcte DI-wiring op alle 4 call-sites en groene tests, vond de onafhankelijke reviewer via `inspect.getsource(AgentRouterAgent.route)` dat `route()` `_redis_cache_tier` NERGENS raadpleegde of beschreef -- de tier werd geconstrueerd maar nooit gebruikt op het daadwerkelijke routeringspad. De bestaande integratietest riep `_redis_cache_tier.get()`/`set()` rechtstreeks aan (bewijst dat de tier tegen Redis werkt) maar omzeilde daarmee precies het gedrag dat bewezen moest worden. De review-doc bevatte op dat moment een feitelijk onjuiste kernclaim ("de cross-worker routing-cache is nu functioneel bewezen").

**Fix**: `route()` kreeg een nieuwe tier 1.5 (Redis-lookup tussen in-memory-cache en DB-discovery) plus een `_remember_route()`-helper die elke succesvolle routeringsbeslissing ook naar Redis schrijft. De integratietest is herschreven om door `route()` zelf te gaan, met "worker 2" die bewust geen enkele andere resolutieroute heeft (geen manifest, geen discovery, geen LLM) zodat een succesvol resultaat alleen via de gedeelde Redis-tier kan komen. 4 nieuwe unit-tests in `tests/unit/test_agent_router_agent.py` dekken het tier-1.5-gedrag expliciet.

---

## B. Samenvatting

De feature sluit het tweede van drie ADR-023-productiegaten (SP-ADR023-002 Dag 2): de cross-worker Redis-routing-cache was nooit actief omdat geen enkele caller `redis_client` doorgaf aan de singleton-factory. Anders dan Dag 1 (dat 3 reviewrondes nodig had om alle call-sites te vinden) is vandaag vooraf, tijdens de planningsfase, al de volledige lijst van 4 bekende live call-sites geidentificeerd en in één samenhangende wijziging gewired -- rechtstreeks toepassen van de les uit Dag 1's herhaalde NO-GO's.

---

## C. Bevindingen per categorie

### 1. Coverage gaps

Was aanwezig, nu gesloten: de eerste implementatie wirede `redis_client` correct maar `route()` gebruikte de tier niet (FA-001). Na de fix zijn alle 4 call-sites gewired EN daadwerkelijk functioneel, bewezen door een integratietest die door `route()` zelf gaat.

### 2. Functionele onduidelijkheden

Geen.

### 3. Regressies

Geen. Volledige gerichte regressie (`tests/unit/agents/`, `tests/unit/api/orchestration/`, `tests/architecture/`, `tests/unit/test_agent_router_agent.py`, na de FA-001-fix): 890 passed, 0 failed. De eerder pre-existing `test_dsm006_ar_governance_fan_out.py`-failure is tussentijds door ongerelateerd werk (commit `c953bb0b`) opgelost -- geverifieerd door de ronde-2-reviewer, niet door dit werk zelf.

Het door de quality-reviewer gevonden regressierisico (3 sync-tests die zouden breken door de `async def`-conversie) is proactief opgelost vóór implementatie -- geen enkele test brak als gevolg van deze wijziging.

### 4. Architectuur / ADR-naleving

- ADR-005 (tenant-isolatie): bevestigd met een ECHTE Redis-integratietest (`test_redis_route_cache_tier_isolates_tenants`), niet alleen een string-formaat-aanname.
- ADR-034 (agent_runtime service boundary): `redis_client` bereikt `MasterOrchestratorAgent`/`AgentRouterAgent` uitsluitend via dependency-injection vanuit de applicatielaag (`dependencies.py`, `app_lifespan.py`, `api/main.py`) -- geen enkel bestand in `src/core/agents/` importeert `src.core.database.redis` zelf.
- ADR-023 sectie 4: de cross-worker routing-cache is nu functioneel bewezen (niet alleen "een kwarg wordt doorgegeven") via een integratietest met een echte, gedeelde Redis-instantie.

### 5. Harde-grens-naleving (Rakesh-beslissing 2026-07-05, nog van kracht)

`git diff --stat develop -- src/core/services/llm/ src/core/llm/fallback_chain.py src/core/shared/config.py docker-compose.prod.yml src/core/tasks/ src/domains/tasks/` is leeg, zowel vóór als na implementatie. AGENTIC-COPILOT-TAAKBEHEER-2026-07 (dat parallel op dezelfde werkkopie draait) is op geen enkel moment geraakt.

---

## D. Actiepunten

Geen open CRITICAL of HIGH bevindingen. Geen actiepunten voor Rakesh.
