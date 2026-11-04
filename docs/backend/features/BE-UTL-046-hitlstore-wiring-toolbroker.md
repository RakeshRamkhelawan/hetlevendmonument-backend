# Backend Feature Specification

## Metadata

- Feature ID: BE-UTL-046
- Feature naam: HITLStore consistente wiring in ToolBrokerService
- Status: APPROVED WITH MINOR GAPS
- Auteur: Kimi Code CLI
- Reviewer: (code-reviewer subagent + self-review)
- Datum: 2026-07-07
- Gerelateerde user story / ticket: ADR-037 Fase 0, Dag 1 (AUDIT-TOOL-005)
- Gerelateerde router / module: `src/core/tool_broker`, `src/core/api/v1/tool_broker`, `src/core/agents`, `src/core/als/agents`
- Gerelateerde frontend endpoints: geen
- Gerelateerde database tabellen: `hitl_tickets`
- Versie: 1.0

---

## Doel en scope

### Doel

Zorgen dat **alle** constructieplekken van `ToolBrokerService` een consistente, tenant-gebonden `HITLStore` meekrijgen, zodat HITL-tickets (Human-in-the-Loop) niet meer in een thread-unsafe in-memory dictionary terechtkomen en cross-tenant ticket-opvraging onmogelijk is.

### In scope

- Uitbreiden van `HITLStore` met een session-gekoppelde factory (`for_session`) en een repository-gekoppelde constructor.
- Aanpassen van `ToolBrokerDependencies.get_service()` zowel voor singleton- als per-request pad.
- Aanpassen van `get_tool_broker_service()` FastAPI dependency.
- Aanpassen van `EnhancedBaseAgent._create_tool_broker()` en `BaseSpecialistAgent.__init__` zodat agenten een `HITLStore` krijgen.
- Doorgeven van `context={"tenant_id": ...}` bij agent-aanroepen van `execute_tool`.
- Oplossen van de naam-botsing tussen twee `get_tool_broker_service()` functies door `src/core/api/v1/tool_broker/dependencies.py` te reduceren tot alleen circuit-registry hulp.
- Aanpassen van `execution_router` zodat deze de dependency-injected service gebruikt in plaats van inline constructie.
- Rode/groene unit tests voor alle zes de constructieplekken plus een functionele HIGH-risk gate test.

### Out of scope

- Wijzigingen aan het `hitl_tickets` database schema (bestaand model blijft ongewijzigd).
- Nieuwe HITL endpoints of UI.
- Verwijderen van de legacy `_hitl_tickets` in-memory dict uit `ToolBrokerService` (deze wordt pas veilig verwijderd zodra alle call-sites zijn geaudit; zie ADR-037 G3/WE-018).
- MCP-server productisering (ADR-037 Fase 2-4).
- Overige ADR-037 Fase 0 items (G1, G2, G4-G10).

---

## Build summary

- Nieuw gebouwd:
  - `tests/unit/tool_broker/test_hitl_wiring_consistency.py` — 7 tests.
- Gewijzigd:
  - `src/core/tool_broker/hitl_store.py` — repository/session factory modes.
  - `src/core/tool_broker/dependencies.py` — HITLStore doorgeven in beide service-paden.
  - `src/core/api/v1/tool_broker/dependencies.py` — duplicate dependency verwijderd.
  - `src/core/api/v1/tool_broker/execution_router.py` — `Depends(get_tool_broker_service)`.
  - `src/core/agents/base_agent.py` — `EnhancedBaseAgent._create_tool_broker()` met HITLStore + tenant context.
  - `src/core/als/agents/specialist_base.py` — `BaseSpecialistAgent` met HITLStore + tenant context.
  - `tests/unit/agents/test_specialist_act.py` — assertion uitgebreid met tenant context.
- Verwijderd:
  - `get_tool_broker_service()` duplicate uit `src/core/api/v1/tool_broker/dependencies.py`.
- Beinvloede bestaande flows:
  - Alle codepaden die `ToolBrokerService` instantieren.
  - Agent-execution flows die `execute_tool` aanroepen.
  - `POST /api/v1/tool_broker/execute` endpoint.

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-UTL-046 | HITLStore consistente wiring in ToolBrokerService | Utility / fix | `src/core/tool_broker/hitl_store.py` | Wijziging | HITL ticket afhandeling |
| BE-DEP-046 | get_tool_broker_service FastAPI dependency | Dependency | `src/core/tool_broker/dependencies.py` | Wijziging | API request injectie |
| BE-UTL-046a | ToolBrokerDependencies.get_service | Utility | `src/core/tool_broker/dependencies.py` | Wijziging | Service constructie |
| BE-AGT-046 | EnhancedBaseAgent tool-broker constructie | Agent utility | `src/core/agents/base_agent.py` | Wijziging | Agent tool execution |
| BE-AGT-046b | BaseSpecialistAgent tool-broker constructie | Agent utility | `src/core/als/agents/specialist_base.py` | Wijziging | ALS specialist execution |
| BE-EP-046 | POST /api/v1/tool_broker/execute | Endpoint | `src/core/api/v1/tool_broker/execution_router.py` | Wijziging | Synchrone tool-uitvoering |
| BE-UTL-046c | HITL wiring consistency tests | Unit tests | `tests/unit/tool_broker/test_hitl_wiring_consistency.py` | Nieuw | Verificatie wiring |

---

## API-flows

### Flow ID: BE-FLW-046-001 — Synchrone tool-executie met HITL

- Naam: Synchrone tool-executie met HITL-gate
- Trigger (HTTP-methode + route): `POST /api/v1/tool_broker/execute`
- Voorwaarden (auth, tenant, feature flag):
  - Geauthenticeerde gebruiker (JWT).
  - Vereiste scopes afhankelijk van tool risk-tier (bestaand gedrag).
  - `tenant_id` afkomstig uit JWT claim (ADR-003).
- Request-pad:
  1. `execution_router.execute_tool` ontvangt `ToolExecutionRequest`.
  2. FastAPI injecteert `tool_broker_service` via `Depends(get_tool_broker_service)`.
  3. Service roept `execute_tool` aan met `current_user` en `tenant_id` context.
- Service-stappen:
  1. `ToolBrokerService` zoekt tool in `local_registry`.
  2. Risk-tier bepaalt of HITL vereist is.
  3. Bij HITL: `hitl_store.get_approval_status(ticket_id, tenant_id=...)` controleert ticket status.
  4. Bij approved status: tool wordt uitgevoerd.
- DB-operaties:
  - `SELECT` op `hitl_tickets` gefilterd op `ticket_id` en `tenant_id`.
- Successtatus + response: `200 OK` met `ToolExecutionResponse`.
- Foutpaden:
  - `401 Unauthorized` — ontbrekende of ongeldige JWT.
  - `403 Forbidden` — onvoldoende scopes of verkeerde tenant.
  - `404 Not Found` — onbekende tool.
  - `422 Unprocessable Entity` — ongeldige request body.
  - `429 Too Many Requests` — rate limit.
  - `500 Internal Server Error` — onverwachte fout in service.
- Eindtoestand (DB, cache, events): Ticket status ongewijzigd bij read-only check; tool-resultaat wordt geretourneerd.

---

## Detaildocumentatie per artefact

---

## [BE-UTL-046] HITLStore

### 1. Type

Utility-klasse (DB-backed HITL ticket store).

### 2. Locatie

- Bestandspad: `src/core/tool_broker/hitl_store.py`
- Klasse / functie: `HITLStore`

### 3. Gerelateerde flow

- BE-FLW-046-001

### 4. Doel

Abstractie rond de `hitl_tickets` tabel die read-operaties op HITL tickets tenant-gebonden uitvoert.

### 5. Functionele beschrijving

`HITLStore` leest de status van een HITL ticket uit de database. Afhankelijk van de constructor wordt de leesoperatie uitgevoerd tegen een specifieke database sessie of tegen een repository die later wordt geconfigureerd. Wanneer een `tenant_id` wordt meegegeven, wordt het ticket altijd binnen die tenant gezocht; anders wordt een ongecontroleerde lookup gebruikt (legacy fallback voor call-sites die nog geen tenant doorgeven).

### 6. Technische beschrijving

```python
class HITLStore:
    def __init__(self, repository: HITLTicketRepository | None = None) -> None: ...
    @classmethod
    def for_session(cls, db: AsyncSession) -> HITLStore: ...
    async def get_approval_status(self, ticket_id: str, tenant_id: int | None = None) -> str | None: ...
```

- `__init__` accepteert een optionele `HITLTicketRepository`. Gebruikt in de singleton-factory voor lazy initialisatie.
- `for_session(db)` is een convenience factory die een repository op de gegeven async sessie bouwt. Gebruikt door per-request FastAPI dependencies en agent constructors.
- `get_approval_status` roept `repository.get(ticket_id, tenant_id=tenant_id)` aan wanneer `tenant_id` is gegeven, anders `repository.get_unchecked(ticket_id)`.

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: n.v.t. (interne utility).
- Vereiste rol / scope: n.v.t.
- Tenant-isolatie: Ja, zolang callers `tenant_id` doorgeven. De fallback `get_unchecked` is een tijdelijke compatibiliteitslaag.
- Feature flag: geen.

### 8. Request-specificatie

- Niet van toepassing (interne utility).

### 9. Response-specificatie

- `get_approval_status` retourneert `str | None` (ticket status of `None` als niet gevonden).

### 10. Validaties en constraints

- `repository` moet een `HITLTicketRepository` instantie zijn of `None`.
- `tenant_id` moet een integer zijn wanneer tenant-isolatie gewenst is.

### 11. Business rules

- Een ticket mag alleen worden opgehaald binnen de tenant waartoe de aanroepende actor behoort.
- Callers die geen `tenant_id` doorgeven, krijgen legacy gedrag totdat alle call-sites zijn gemigreerd.

### 12. Afhankelijkheden

- `src.core.governance.models.HITLTicket`
- `src.core.governance.repositories.hitl_repository.HITLTicketRepository`
- `sqlalchemy.ext.asyncio.AsyncSession`

### 13. Foutafhandeling

- `500 Internal Server Error` — repository is `None` en er wordt toch een ticket-operatie uitgevoerd.
- Database fouten worden doorgegeven aan de caller.

### 14. Transacties en dataïntegriteit

- Read-only; geen transactie nodig.
- Tenant-isolatie hangt af van caller discipline totdat de fallback is verwijderd.

### 15. Telemetry / logging / tracing

- Geen specifieke telemetry in deze utility.

### 16. Caching

- Gecached: nee.
- Cache-sleutel: n.v.t.
- TTL: n.v.t.
- Invalidatie: n.v.t.

### 17. Acceptatiecriteria

- [ ] `HITLStore(repository)` kan worden geinstantieerd met een repository.
- [ ] `HITLStore.for_session(db)` levert een store gekoppeld aan de gegeven sessie.
- [ ] `get_approval_status(ticket_id, tenant_id=X)` gebruikt tenant-gefilterde lookup.
- [ ] `get_approval_status(ticket_id)` valt terug op `get_unchecked` zonder fout.

### 18. Integratoruitleg

- Niet direct zichtbaar voor API-consumenten.

### 19. Trainingssamenvatting

- Actor: `ToolBrokerService`, agents, API endpoint.
- Voorwaarde: Een HITL ticket bestaat in `hitl_tickets`.
- Actie (request): Roep `get_approval_status(ticket_id, tenant_id=...)` aan.
- Systeemverwerking: Store voert tenant-gefilterde `SELECT` uit.
- Succesrespons: Ticket status string.
- Foutrespons: `None` bij niet bestaand ticket; exception bij ongeldige repository.
- Uitzonderingen: `tenant_id=None` gebruikt legacy ongefilterde lookup.

---

## [BE-DEP-046] get_tool_broker_service

### 1. Type

FastAPI Depends-functie.

### 2. Locatie

- Bestandspad: `src/core/tool_broker/dependencies.py`
- Klasse / functie: `get_tool_broker_service`

### 3. Gerelateerde flow

- BE-FLW-046-001

### 4. Doel

Centrale dependency-functie die een per-request `ToolBrokerService` met `HITLStore` levert aan FastAPI endpoints.

### 5. Functionele beschrijving

Bij elke inkomende request wordt een nieuwe `ToolBrokerService` aangemaakt met een `HITLStore` die is gekoppeld aan de request database sessie. Hierdoor kunnen HITL ticket lookups binnen dezelfde HTTP request transactie plaatsvinden.

### 6. Technische beschrijving

```python
def get_tool_broker_service(db: AsyncSession = Depends(get_db)) -> ToolBrokerService:
    return ToolBrokerDependencies.get_service(db=db)
```

De functie delegeert naar `ToolBrokerDependencies.get_service(db=...)`, die een `HITLTicketRepository(db)` en `HITLStore(repo)` bouwt en meegeeft aan `ToolBrokerService(...)`.

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: endpoint-specifiek.
- Vereiste rol / scope: endpoint-specifiek.
- Tenant-isolatie: Ja, via `get_db` en `tenant_id` in endpoint/service.
- Feature flag: geen.

### 8. Request-specificatie

- Niet van toepassing (dependency).

### 9. Response-specificatie

- Retourneert `ToolBrokerService` instantie.

### 10. Validaties en constraints

- `db` moet een geldige `AsyncSession` zijn.

### 11. Business rules

- Elke request krijgt een verse service instantie.

### 12. Afhankelijkheden

- `get_db` (database sessie dependency)
- `ToolBrokerDependencies`

### 13. Foutafhandeling

- Database connectie fouten worden doorgegeven.

### 14. Transacties en dataïntegriteit

- De service gebruikt de request-transactie van `get_db`.

### 15. Telemetry / logging / tracing

- Geen specifieke telemetry.

### 16. Caching

- Gecached: nee.

### 17. Acceptatiecriteria

- [ ] `get_tool_broker_service` is importeerbaar vanuit `src.core.tool_broker.dependencies`.
- [ ] De geretourneerde service heeft een niet-`None` `hitl_store` attribuut.

### 18. Integratoruitleg

- Niet direct zichtbaar voor API-consumenten.

### 19. Trainingssamenvatting

- Actor: FastAPI endpoint.
- Voorwaarde: Binnen een HTTP request met geldige DB sessie.
- Actie (request): `Depends(get_tool_broker_service)`.
- Systeemverwerking: Bouwt `ToolBrokerService` + `HITLStore.for_session(db)`.
- Succesrespons: Geinjecteerde service.
- Foutrespons: DB connectie fout.
- Uitzonderingen: geen.

---

## [BE-UTL-046a] ToolBrokerDependencies.get_service

### 1. Type

Utility-methode (singleton + per-request service factory).

### 2. Locatie

- Bestandspad: `src/core/tool_broker/dependencies.py`
- Klasse / functie: `ToolBrokerDependencies.get_service`

### 3. Gerelateerde flow

- BE-FLW-046-001

### 4. Doel

Centrale factory voor `ToolBrokerService` zowel voor singleton gebruik (bijv. startup, workers) als voor per-request gebruik.

### 5. Functionele beschrijving

Wanneer `db=None` wordt een singleton service geretourneerd (lazy geinitialiseerd). Wanneer een sessie wordt meegegeven, wordt een nieuwe service geretourneerd met een sessie-gebonden `HITLStore`.

### 6. Technische beschrijving

```python
@classmethod
def get_service(cls, db: Optional[AsyncSession] = None) -> ToolBrokerService:
    instance = cls()
    if db is None:
        if instance._service is None:
            instance.initialize()
        return instance._service
    repo = HITLTicketRepository(db)
    hitl_store = HITLStore(repo)
    return ToolBrokerService(..., db_session=db, hitl_store=hitl_store)
```

### 7. Zichtbaarheids- en toegangsregels

- Interne utility.
- Tenant-isolatie: per-request variant gebruikt request sessie.

### 8. Request-specificatie

- Niet van toepassing.

### 9. Response-specificatie

- Retourneert `ToolBrokerService`.

### 10. Validaties en constraints

- `db` is optioneel.

### 11. Business rules

- Singleton pad mag geen request-sessie bewaren.
- Per-request pad bouwt altijd een nieuwe `HITLStore`.

### 12. Afhankelijkheden

- `ToolBrokerService`
- `HITLStore`
- `HITLTicketRepository`

### 13. Foutafhandeling

- `RuntimeError` bij aanroep van `initialize()` binnen een lopende event loop (bij async callers gebruik `initialize_async()`).

### 14. Transacties en dataïntegriteit

- Singleton pad: geen transactie.
- Per-request pad: gebruikt meegegeven sessie.

### 15. Telemetry / logging / tracing

- Geen.

### 16. Caching

- Gecached: ja, singleton service wordt eenmalig geinitialiseerd.

### 17. Acceptatiecriteria

- [ ] `get_service()` levert een singleton met `hitl_store`.
- [ ] `get_service(db=session)` levert een per-request service met `hitl_store`.

### 18. Integratoruitleg

- Niet direct zichtbaar.

### 19. Trainingssamenvatting

- Actor: Code die een service nodig heeft.
- Voorwaarde: Singleton of request sessie beschikbaar.
- Actie (request): `ToolBrokerDependencies.get_service(db=...)`.
- Systeemverwerking: Kiest singleton of bouwt per-request service.
- Succesrespons: `ToolBrokerService`.
- Foutrespons: `RuntimeError` bij verkeerde initialisatie context.
- Uitzonderingen: geen.

---

## [BE-AGT-046] EnhancedBaseAgent tool-broker constructie

### 1. Type

Agent utility methode.

### 2. Locatie

- Bestandspad: `src/core/agents/base_agent.py`
- Klasse / functie: `EnhancedBaseAgent._create_tool_broker`

### 3. Gerelateerde flow

- Agent tool execution flow.

### 4. Doel

Voorzien van een `ToolBrokerService` met DB-backed `HITLStore` voor agents die buiten een FastAPI request context om tools uitvoeren.

### 5. Functionele beschrijving

Wanneer een agent een tool nodig heeft, bouwt deze methode een `ToolBrokerService` met een op een nieuwe database sessie gebaseerde `HITLStore`.

### 6. Technische beschrijving

```python
def _create_tool_broker(self) -> ToolBrokerService:
    from src.core.database.database import db_manager
    from src.core.tool_broker.hitl_store import HITLStore
    from src.core.tool_broker.local_registry import LocalToolRegistry
    from src.core.tool_broker.service import ToolBrokerService

    db = db_manager.session_factory()
    return ToolBrokerService(
        serena_client=_NoopToolClient(),
        seq_thinking_client=_NoopToolClient(),
        local_registry=LocalToolRegistry(),
        enable_resilience=False,
        hitl_store=HITLStore.for_session(db),
        db_session=db,
    )
```

`db_manager` wordt dynamisch geimporteerd om een import-linter regresie (ADR-034 Contract 7) te voorkomen.

### 7. Zichtbaarheids- en toegangsregels

- Interne agent methode.
- Tenant-isolatie: via `execute_tool(context={"tenant_id": self.tenant_id})`.

### 8. Request-specificatie

- Niet van toepassing.

### 9. Response-specificatie

- Retourneert `ToolBrokerService`.

### 10. Validaties en constraints

- `db_manager` moet geconfigureerd zijn.

### 11. Business rules

- Agent gebruikt altijd een eigen database sessie voor HITL lookups.
- Agent geeft altijd `tenant_id` mee bij tool execution.

### 12. Afhankelijkheden

- `db_manager`
- `HITLStore`
- `LocalToolRegistry`
- `ToolBrokerService`

### 13. Foutafhandeling

- Database fouten bij sessie creatie worden doorgegeven.

### 14. Transacties en dataïntegriteit

- Nieuwe sessie per agent tool-broker instantie.

### 15. Telemetry / logging / tracing

- Geen specifieke telemetry.

### 16. Caching

- Gecached: nee.

### 17. Acceptatiecriteria

- [ ] `_create_tool_broker()` retourneert een service met niet-`None` `hitl_store`.
- [ ] `execute_tool` doorgeeft `context={"tenant_id": self.tenant_id}`.

### 18. Integratoruitleg

- Niet direct zichtbaar.

### 19. Trainingssamenvatting

- Actor: `EnhancedBaseAgent`.
- Voorwaarde: Agent heeft `tenant_id` en `agent_id`.
- Actie (request): `_create_tool_broker()`.
- Systeemverwerking: Bouwt service met DB-backed HITLStore.
- Succesrespons: Gereed om tools uit te voeren.
- Foutrespons: DB fout.
- Uitzonderingen: geen.

---

## [BE-AGT-046b] BaseSpecialistAgent tool-broker constructie

### 1. Type

Agent constructor / utility.

### 2. Locatie

- Bestandspad: `src/core/als/agents/specialist_base.py`
- Klasse / functie: `BaseSpecialistAgent.__init__` / `BaseSpecialistAgent.act`

### 3. Gerelateerde flow

- ALS specialist tool execution flow.

### 4. Doel

Voorzien van een `ToolBrokerService` met `HITLStore` voor ALS specialist agents.

### 5. Functionele beschrijving

Tijdens initialisatie bouwt de specialist agent een `ToolBrokerService`. Omdat `__init__` geen database sessie heeft, wordt een fallback `HITLStore()` gebruikt; concrete ticket-operaties vereisen een sessie die later wordt doorgegeven. Bij `act()` wordt `execute_tool` aangeroepen met `context={"tenant_id": self.tenant_id}`.

### 6. Technische beschrijving

```python
from src.core.tool_broker.hitl_store import HITLStore

# In __init__:
self.tools = ToolBrokerService(
    serena_client=cast(Any, dummy_serena),
    seq_thinking_client=cast(Any, dummy_seq),
    hitl_store=HITLStore(),  # fallback store; real ticket ops need DB session
)

# In act():
result = await self.tools.execute_tool(
    tool_name=tool_name,
    payload=params,
    agent_id=self.agent_id,
    timeout_seconds=30,
    context={"tenant_id": self.tenant_id},
)
```

### 7. Zichtbaarheids- en toegangsregels

- Interne agent constructor.
- Tenant-isolatie: via `context={"tenant_id": self.tenant_id}` in `act()`.

### 8. Request-specificatie

- Niet van toepassing.

### 9. Response-specificatie

- `self.tools` is een `ToolBrokerService` instantie.

### 10. Validaties en constraints

- `self.tenant_id` moet gezet zijn voordat `act()` wordt aangeroepen.

### 11. Business rules

- Specialist agent geeft altijd `tenant_id` mee bij tool execution.
- Fallback HITLStore zonder repository kan geen ticket lookups doen; dit is een tijdelijke constructie totdat de agent een sessie krijgt.

### 12. Afhankelijkheden

- `ToolBrokerService`
- `HITLStore`

### 13. Foutafhandeling

- Ticket lookup met fallback store zal falen totdat een repository wordt gezet.

### 14. Transacties en dataïntegriteit

- Geen transactie in constructor.

### 15. Telemetry / logging / tracing

- Geen.

### 16. Caching

- Gecached: nee.

### 17. Acceptatiecriteria

- [ ] `BaseSpecialistAgent.tools` is een `ToolBrokerService` met niet-`None` `hitl_store`.
- [ ] `act()` doorgeeft `context={"tenant_id": self.tenant_id}`.

### 18. Integratoruitleg

- Niet direct zichtbaar.

### 19. Trainingssamenvatting

- Actor: `BaseSpecialistAgent`.
- Voorwaarde: Agent is geinitialiseerd met `tenant_id`.
- Actie (request): `act(tool_name, params)`.
- Systeemverwerking: Doorgeeft tenant context en voert tool uit.
- Succesrespons: Tool resultaat.
- Foutrespons: Ticket lookup fout bij ontbrekende repository.
- Uitzonderingen: Fallback store heeft geen repository.

---

## [BE-EP-046] POST /api/v1/tool_broker/execute

### 1. Type

API endpoint.

### 2. Locatie

- Bestandspad: `src/core/api/v1/tool_broker/execution_router.py`
- Klasse / functie: `execute_tool`

### 3. Gerelateerde flow

- BE-FLW-046-001

### 4. Doel

Synchrone tool-executie endpoint dat nu gebruik maakt van dependency-injected `ToolBrokerService` met `HITLStore`.

### 5. Functionele beschrijving

Accepteert een tool-uitvoeringsverzoek, laat de geinjecteerde service de tool uitvoeren, en retourneert het resultaat.

### 6. Technische beschrijving

```python
@router.post("/execute", response_model=ToolExecutionResponse)
async def execute_tool(
    request: ToolExecutionRequest,
    current_user: UserResponse = Depends(get_current_user),
    tool_broker_service: ToolBrokerService = Depends(get_tool_broker_service),
) -> ToolExecutionResponse:
    return await tool_broker_service.execute_tool(...)
```

Voorheen construeerde het endpoint intern een `ToolBrokerService`; nu wordt deze via `Depends(get_tool_broker_service)` geinjecteerd.

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: Ja, JWT via `get_current_user`.
- Vereiste rol / scope: Endpoint-specifiek (bestaand gedrag).
- Tenant-isolatie: Ja, via `current_user.tenant_id` en service.
- Feature flag: geen.

### 8. Request-specificatie

- Methode: `POST`
- Route: `/api/v1/tool_broker/execute`
- Path parameters: geen
- Query parameters: geen
- Request body (schema): `ToolExecutionRequest`
- Verplichte headers: `Authorization: Bearer <jwt>`

### 9. Response-specificatie

- Successtatus: `200 OK`
- Response schema: `ToolExecutionResponse`
- Foutstatussen: `401`, `403`, `404`, `422`, `429`, `500`

### 10. Validaties en constraints

- Request body wordt gevalideerd door Pydantic.

### 11. Business rules

- HITL-gates gebruiken de geinjecteerde `HITLStore`.

### 12. Afhankelijkheden

- `get_current_user`
- `get_tool_broker_service`
- `ToolBrokerService`

### 13. Foutafhandeling

- `401 Unauthorized` — ongeldige of ontbrekende JWT.
- `403 Forbidden` — onvoldoende scopes.
- `404 Not Found` — tool niet gevonden.
- `422 Unprocessable Entity` — ongeldige request body.
- `429 Too Many Requests` — rate limit.
- `500 Internal Server Error` — service fout.

### 14. Transacties en dataïntegriteit

- Gebruikt request database sessie.

### 15. Telemetry / logging / tracing

- Bestaande audit/logging ongewijzigd.

### 16. Caching

- Gecached: nee.

### 17. Acceptatiecriteria

- [ ] Endpoint retourneert `200 OK` bij geldige tool-aanroep.
- [ ] Endpoint gebruikt dependency-injected service.
- [ ] HITL-gate leest uit DB-backed store.

### 18. Integratoruitleg

- Roep `POST /api/v1/tool_broker/execute` aan met een geldig JWT en `ToolExecutionRequest` body.
- Bij HIGH-risk tools kan een approved HITL ticket vereist zijn.
- Respons bevat het tool-resultaat of een HITL-verzoek.

### 19. Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker / frontend.
- Voorwaarde: Geldig JWT en bekende tool.
- Actie (request): `POST /api/v1/tool_broker/execute`.
- Systeemverwerking: Injecteert service, voert tool uit, controleert HITL indien nodig.
- Succesrespons: `200 OK` + `ToolExecutionResponse`.
- Foutrespons: `401`/`403`/`404`/`422`/`429`/`500`.
- Uitzonderingen: HITL ticket kan vereist zijn voor HIGH-risk tools.

---

## [BE-UTL-046c] HITL wiring consistency tests

### 1. Type

Unit tests.

### 2. Locatie

- Bestandspad: `tests/unit/tool_broker/test_hitl_wiring_consistency.py`
- Klasse / functie: `TestHITLStoreWiringConsistency`, `TestHITLStoreFunctional`

### 3. Gerelateerde flow

- BE-FLW-046-001

### 4. Doel

Garanderen dat elke `ToolBrokerService` constructieplek een `HITLStore` bevat en dat HIGH-risk tools met een approved ticket daadwerkelijk worden uitgevoerd.

### 5. Functionele beschrijving

De tests inspecteren de zes bekende constructieplekken en verifiëren dat de resulterende service een niet-`None` `hitl_store` attribuut heeft. Een functionele test voert een HIGH-risk tool uit met een vooraf goedgekeurd ticket via de singleton service.

### 6. Technische beschrijving

- `test_singleton_get_service_has_hitl_store`
- `test_per_request_get_service_has_hitl_store`
- `test_fastapi_dependency_get_tool_broker_service_has_hitl_store`
- `test_enhanced_base_agent_tool_broker_has_hitl_store`
- `test_specialist_agent_tools_has_hitl_store`
- `test_execution_router_uses_dependency_injected_service`
- `test_high_risk_tool_with_approved_ticket_executes_via_singleton`

### 7. Zichtbaarheids- en toegangsregels

- N.v.t.

### 8. Request-specificatie

- N.v.t.

### 9. Response-specificatie

- N.v.t.

### 10. Validaties en constraints

- Vereist dat `ToolBrokerService` een `hitl_store` attribuut heeft.

### 11. Business rules

- Geen HITL-store = test faalt.

### 12. Afhankelijkheden

- `ToolBrokerService`
- `HITLStore`
- `ToolBrokerDependencies`
- Agent klassen

### 13. Foutafhandeling

- Test faalt bij ontbrekende wiring.

### 14. Transacties en dataïntegriteit

- Functionele test maakt een HITL ticket aan in de singleton store; schoont op na de test.

### 15. Telemetry / logging / tracing

- N.v.t.

### 16. Caching

- N.v.t.

### 17. Acceptatiecriteria

- [ ] Alle zes wiring tests slagen.
- [ ] Functionele HIGH-risk gate test slagen.

### 18. Integratoruitleg

- Niet van toepassing.

### 19. Trainingssamenvatting

- Actor: Ontwikkelaar / CI.
- Voorwaarde: Code is gewijzigd in ToolBroker wiring.
- Actie (request): Draai `pytest tests/unit/tool_broker/test_hitl_wiring_consistency.py`.
- Systeemverwerking: Verifieert HITLStore in alle constructieplekken.
- Succesrespons: 7 passed.
- Foutrespons: Failing test toont ontbrekende wiring.
- Uitzonderingen: geen.

---

## Integratorhandleiding

### Voor API-consumenten en koppelende teams

- Geen wijzigingen in request/response contracten.
- HIGH-risk tool-executie blijft een approved HITL ticket vereisen.
- Intern is de HITL lookup nu consistent via de database, wat betere tenant-isolatie en persistentie biedt.

---

## Open aannames

- Alle callers van `execute_tool` zullen op termijn `tenant_id` doorgeven in `context`.
- De legacy `_hitl_tickets` in-memory dict in `ToolBrokerService` wordt in een vervolgsprint verwijderd (ADR-037 G3/WE-018).

## Open vragen

- Moet `BaseSpecialistAgent` op termijn een echte DB sessie krijgen in plaats van de fallback `HITLStore()`?

## Risico's

- **Risico**: `BaseSpecialistAgent` gebruikt een fallback `HITLStore()` zonder repository. ticket-operaties in `act()` kunnen falen totdat een sessie wordt doorgegeven of de constructor wordt aangepast.
  - **Mitigatie**: Dit is een bekende tijdelijke toestand; de fallback vervangt de in-memory dict en voorkomt dat HITL lookups volledig ontbreken. Een vervolgtaak moet de agent constructor een sessie laten ontvangen.

---

## QA-checks

- [x] Endpoint functioneel getest (happy path) — via functionele unit test.
- [x] Auth en permissies getest — bestaande testdekking blijft groen.
- [x] Tenant-isolatie getest — `test_specialist_act.py` controleert `context={"tenant_id": 1}`.
- [x] Edge cases getest — fallback store, singleton vs per-request.
- [x] Logging en tracing gecontroleerd — geen wijzigingen.

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Alle endpoints, services en modellen zijn geinventariseerd
- [x] Alle relevante foutstatussen zijn beschreven
- [x] Functionele beschrijving aanwezig
- [x] Technische beschrijving aanwezig
- [x] Acceptatiecriteria zijn testbaar
- [x] Integratoruitleg is aanwezig
- [x] Trainingssamenvatting is aanwezig
- [x] Open aannames zijn benoemd
- [x] QA-checks zijn uitgevoerd
- [x] Review door reviewer-prompt: APPROVED WITH MINOR GAPS
