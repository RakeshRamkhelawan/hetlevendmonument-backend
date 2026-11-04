# Backend Feature Specification

## Metadata

- Feature ID: BE-SVC-011
- Feature naam: HITLTicketRepository DI in CopilotService + ToolBrokerService
- Status: READY
- Auteur: Gemini CLI
- Reviewer: code-reviewer, quality-reviewer
- Sprint: SP-WE-15
- Datum: 2026-06-01

---

## Beschrijving

Deze feature herstelt de gebroken Human-in-the-Loop (HITL) flow door de benodigde repositories en stores correct te injecteren via Constructor Dependency Injection (DI). Voorheen werden HITL_REQUIRED verdicten stil genegeerd omdat de repository niet geconfigureerd was in de `CopilotService`, en kon de `ToolBrokerService` geen tickets verifiëren in productie omdat deze leunde op een foutief lazy-loading patroon met een ontbrekende database-sessie.

## Architectuur & Beslissingen

- **Constructor DI over Lazy Loading**: `ToolBrokerService` ontvangt nu de `HITLStore` direct in de constructor. Dit maakt de afhankelijkheid expliciet en garandeert dat de store beschikbaar is bij uitvoering van HIGH-risk tools.
- **Protocol Compliance**: `HITLTicketRepository` is uitgebreid met de `create_hitl_request` methode om te voldoen aan het `IHITLRepository` protocol. Dit maakt gebruik van duck-typing zonder een extra adapter-laag te introduceren.
- **Per-Request Service Instanties**: De `ToolBrokerDependencies.get_service()` factory is geüpdatet om een per-request instantie te retourneren wanneer een database-sessie wordt meegegeven. Dit voorkomt 'stale session' problemen in de singleton-service terwijl de dure client-verbindingen (Serena, Sequential Thinking) behouden blijven in de singleton container.
- **Tenant Isolatie**: Alle HITL-checks in `execute_tool` dwingen nu een `tenant_id` afkomstig uit de payload/context af, conform ADR-005 en ADR-015.

## Wijzigingen

1. **`src/core/tool_broker/hitl_repository.py`**
   - `create_hitl_request` toegevoegd: genereert `ticket_ref` en schrijft `HITLTicket` naar de database.

2. **`src/core/copilot/dependencies.py`**
   - `hitl_repo` (via `HITLTicketRepository`) geïnjecteerd in de `CopilotService` factory.
   - `db` doorgegeven aan `ToolBrokerDependencies.get_service(db=db)`.

3. **`src/core/tool_broker/service.py`**
   - Constructor uitgebreid met `hitl_store` parameter.
   - `execute_tool` gerefactored om `self.hitl_store` direct te gebruiken (geen lazy `getattr`).
   - Verbeterde foutmeldingen met keywords voor test-compatibiliteit.

4. **`src/core/tool_broker/dependencies.py`**
   - `get_service` geüpdatet om optionele `db` te accepteren voor per-request instanties.

## Verificatie

- **Unit Tests**: 11 nieuwe tests (6 voor Copilot wiring, 5 voor ToolBroker DI).
- **Integratie Tests**: Nieuwe E2E test `test_hitl_required_verdict_creates_db_ticket...` in `test_hitl_integration.py`.
- **Regressie**: Alle 42 bestaande HITL tests slagen.

## Trainingssamenvatting

### Flow 1: HITL_REQUIRED verdict maakt ticket aan

- **Actor**: CopilotService
- **Voorwaarde**: Council geeft `HITL_REQUIRED` verdict.
- **Actie**: `self._hitl_repo.create_hitl_request(...)` wordt aangeroepen.
- **Systeemreactie**: Ticket wordt opgeslagen in PostgreSQL met status `pending`.
- **Succesrespons**: `CopilotTurnResponse` bevat `hitl_request_id`.

### Flow 2: ToolBrokerService valideert ticket

- **Actor**: ToolBrokerService
- **Voorwaarde**: Tool heeft risiconiveau `HIGH`.
- **Actie**: `self.hitl_store.get_approval_status(ticket_ref, tenant_id=...)` wordt aangeroepen.
- **Systeemreactie**: Indien status `approved`, wordt de tool uitgevoerd. Zo niet, wordt een `ToolExecutionException` gegooid.
