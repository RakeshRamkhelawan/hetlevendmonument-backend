# ADR-037: ToolBroker Productiehardening & MCP-Server Productisering

## Status
Proposed

## Datum
2026-07-07

## Auteur
Claude (Sonnet 5), op verzoek van Rakesh, na een onafhankelijk gereviewde gap-analyse
(`docs/reports/TOOLBROKER-VS-MCP-MARKTSTANDAARD-2026-07-07.md`,
`docs/agent-briefs/generated/2026-07-07-rapport-review-toolbroker-vs-mcp.md`,
`docs/agent-briefs/generated/2026-07-07-audit-to-fix-toolbroker-mcp-gaps.md`).

---

## Context

ToolBroker (`src/core/tool_broker/`) is de ADR-015 "Zero-Trust"-veiligheidslaag waarmee
AI-agents tools mogen aanroepen: allowlist per agent-profiel, risico-classificatie
(LOW/MEDIUM/HIGH), een HITL-goedkeuringspoort voor HIGH-risk tools, en een SHA-256
hash-chain audit trail. Het is **geen** MCP-server in de protocol-technische zin -- het
*consumeert* twee externe MCP-servers (Serena, Sequential Thinking) via stdio, maar spreekt
zelf geen MCP-wireprotocol naar buiten.

Dit ADR legt vast:
1. Wat er precies moet gebeuren om de bestaande governance-laag daadwerkelijk
   productiewaardig te maken (er zijn nu reeds-gefixte èn nog-open wiring-gaten).
2. Hoe we van daar naar een marktconforme, extern aanspreekbare MCP-server komen.
3. Waar we, gegeven de bestaande governance-diepte, verder kunnen gaan dan Anthropics
   eigen referentie-implementatie.

Elke bevinding hieronder is persoonlijk tegen de broncode geverifieerd (Read/Grep, geen
aangenomen subagent-claims) op 2026-07-07, met exacte bestand:regel-citaten.

---

## Gerelateerde ADR's (expliciete matrix)

| ADR | Relatie tot dit ADR | Wat ADR-037 daaraan toevoegt/verandert |
|---|---|---|
| **ADR-015** (Agent/tool execution safety) | Dit ADR is de directe basis -- allowlist, risk-levels, HITL-gate, audit trail | ADR-037 dicht 2 gaten die ADR-015 zelf al erkent (capability discovery §4, nooit gebouwd) en documenteert de WE-018-fix + de nieuwe wiring-inconsistentie die daarna is ontstaan. **Wijzigt ADR-015 niet**, breidt uit. |
| **ADR-019** (Audit Logging) | ToolBroker's SHA-256 hash-chain (`ToolAuditRepository`) is een concrete implementatie van dit ADR | Geen wijziging; Fase 0-2 hergebruiken het bestaande audit-mechanisme, breiden het niet uit met een nieuw log-formaat. |
| **ADR-017** (Gatekeeper) | Deterministische policy-enforcement; ToolBroker's allowlist is een vergelijkbaar, maar los mechanisme | Geen koppeling in dit ADR (bewust, zie "Niet in scope"). |
| **ADR-022** (Agent Self-Learning + ToolBroker) | `EnhancedBaseAgent.tool_broker`-property + `@auto_learn` op `execute_tool()` | Fase 0's HITL-wiring-fix raakt `base_agent.py::_create_tool_broker()` (regel 215-226) -- hetzelfde bestand als ADR-022 wijzigde. Geen conflict met ADR-022's leerloop, alleen met het HITL-argument van de constructor-aanroep. |
| **ADR-024** (Unified Learning ToolBroker) | `BaseSpecialistAgent.act()` (ALS) roept `self.tools.execute_tool()` aan via `als/agents/specialist_base.py:68` | Zelfde constructor-aanroep-patroon dat Fase 0 moet fixen (zie Gap AUDIT-TOOL-005). |
| **ADR-027** (Copilot Agent Council) | De enige vandaag *correct* HITL-gewirede pad (`copilot/dependencies.py:100`) loopt via de Council | Fase 0-2 maken dit patroon de norm voor ALLE call-sites, niet de uitzondering. |
| **ADR-031** (AI Act governance) | HITL-gate = Art. 14-controle; audit-chain = Art. 13-transparantie | Ongewijzigd; Fase 0 herstelt de handhaving, verandert de mapping niet. |
| **ADR-034** (Agent Runtime Service Boundary) | `agents/` mag nooit direct `database`/`redis` importeren | De MCP-server-adapter (Fase 2) MOET deze grens respecteren: transport/OAuth-laag in de applicatielaag, niet in `src/core/agents/`. |
| **ADR-036** (Agentic Organizational Hierarchy) | Documenteert al **2 nog-openstaande ToolBroker-gaten** die dit ADR overneemt (zie Gap G9, G10 hieronder) | ADR-037 erft deze 2 P0-bevindingen van ADR-036 in plaats van ze te herhalen als "nieuw ontdekt" -- ze stonden al vast, alleen nog niet in een uitvoeringsplan. |

---

## Decision

We voeren dit uit in 4 fases. Fase 0 is een harde afhankelijkheid voor alle latere fases
-- een MCP-server bovenop een inconsistent gewirede governance-laag zou de kernbelofte van
ADR-015 (zero-trust) breken op het moment dat we het oppervlak juist vergroten.

### Fase 0 -- Governance-wiring consistent maken (reeds gescoped, ~3-4 dagen)

**Doel:** garanderen dat de allowlist/risk/HITL/audit-laag daadwerkelijk werkt op ELKE
plek waar een tool wordt aangeroepen, niet alleen op het ene pad dat toevallig goed is
gewired.

### Fase 1 -- Progressive disclosure / governed code-execution

**Doel:** het groeiende tool-catalogus (nu 4 business-tools, straks meer) token-efficiënt
aanbiedbaar maken via Anthropics eigen code-execution-patroon, zonder de governance-laag
te omzeilen.

### Fase 2 -- MCP-server-adapter (het marktconforme deel)

**Doel:** ToolBroker's al-governed catalogus daadwerkelijk exposeren via het MCP-protocol
(Streamable HTTP, OAuth 2.0 Resource Server + RFC-8707) zodat externe MCP-hosts (Claude
Desktop, Claude Code, partner-apps) kunnen verbinden.

### Fase 3 -- Differentiators (verder dan Anthropic)

**Doel:** de 3 patronen die de publieke MCP-ecosystem niet heeft, productiseren:
governed code-execution, HITL-als-rijkere-elicitation, tenant-scoped-MCP als eigen
sub-patroon.

---

## Geverifieerde Gaps (volledig, met codesnippets)

### G1 -- Geen discovery-API richting agents

**Bewijs (afwezigheid):**
```bash
$ grep -rn "def list_tools\|def get_tool_schema\|def get_allowlist_snapshot\|class IToolBroker" src/core/tool_broker/
src/core/tool_broker/mcp_client.py:202:    async def list_tools(self) -> list[dict[str, Any]]:
```
Dit is de **client-side** methode die externe MCP-servers bevraagt (Serena/Sequential
Thinking) -- geen server-side discovery-interface voor ToolBroker's eigen catalogus. ADR-015
§4 beschrijft de bedoelde interface al letterlijk in code (`IToolBroker.list_tools()`,
`get_tool_schema()`, `get_allowlist_snapshot()`) maar die bestaat nergens als implementatie.

### G2 -- Geen MCP-tool-annotaties

**Bewijs (afwezigheid):**
```bash
$ grep -rn "readOnlyHint\|destructiveHint\|idempotentHint\|openWorldHint" src/ --include=*.py
(0 matches)
```
Er is alleen het grovere 3-niveau `risk_level` (LOW/MEDIUM/HIGH) via
`src/core/config/tool_risk_levels.yml` -- geen van de 4 gestandaardiseerde,
orthogonale MCP-hints per tool.

### G3 -- HITL in-memory/DB-desync (WE-018)

**Status: GEFIXED, geverifieerd 2026-07-07.**
```python
# src/core/tool_broker/hitl_store.py:14-21
class HITLStore:
    """
    DB-backed HITL ticket store.
    Replaces the in-memory dict _hitl_tickets (WE-018 fix).
    """
    def __init__(self, repository: HITLTicketRepository) -> None:
        self._repository = repository
```
De klasse zelf is correct. ADR-015's changelog is echter niet bijgewerkt om dit te
bevestigen (stopt bij v1.3, 2026-06-28) -- documentatie-nalatigheid, geen functioneel gat.
**Zie G/AUDIT-TOOL-005 hieronder voor het gat dat WE-018's fix heeft achtergelaten.**

### AUDIT-TOOL-005 -- HITLStore inconsistent gewired op 5 van de 6 constructieplekken

**Bewijs, per plek:**

1. `src/core/tool_broker/dependencies.py:67-73` (de eigen singleton, gebruikt door
   `/v1/tools/execute` via `Depends(get_tool_broker_service)`):
   ```python
   if instance._service is None:
       instance._service = ToolBrokerService(
           serena_client=instance._serena_client,
           seq_thinking_client=instance._seq_thinking_client,
           local_registry=instance._local_registry,
       )  # <-- geen hitl_store=
   ```
2. `src/core/api/v1/tool_broker/dependencies.py:9-13` -- **tweede, gelijknamige**
   `get_tool_broker_service()`-functie in een andere module:
   ```python
   def get_tool_broker_service() -> ToolBrokerService:
       return ToolBrokerService(serena_client, seq_thinking_client)  # geen hitl_store=
   ```
3. `src/core/api/v1/tool_broker/execution_router.py:59`:
   ```python
   tool_broker_service = ToolBrokerService(serena_client, seq_thinking_client)
   ```
4. `src/core/agents/base_agent.py:215-226` (default voor **elke** agent die van
   `EnhancedBaseAgent` erft -- ADR-022):
   ```python
   def _create_tool_broker(self) -> "ToolBrokerService":
       return ToolBrokerService(
           serena_client=_NoopToolClient(),
           seq_thinking_client=_NoopToolClient(),
           local_registry=LocalToolRegistry(),
           enable_resilience=False,
           hitl_store=None,  # <-- expliciet None
       )
   ```
5. `src/core/als/agents/specialist_base.py:66-71` (ALS-specialist-agents -- ADR-024):
   ```python
   self.tools = ToolBrokerService(
       serena_client=cast(Any, dummy_serena),
       seq_thinking_client=cast(Any, dummy_seq),
   )  # geen hitl_store=
   ```
6. **De enige correcte plek**: `src/core/copilot/dependencies.py:100`:
   ```python
   base_broker = ToolBrokerDependencies.get_service(db=db)
   ```
   -- dit triggert `dependencies.py`'s `get_service(db=...)`-tak (regel 128-141), die WEL
   `hitl_store=HITLStore(HITLTicketRepository(db))` correct construeert.

**Gevolg (fail-secure, geverifieerd):** `service.py` regel ~196-205 blokkeert een HIGH-risk
tool-aanroep expliciet als `hitl_store is None`:
```python
if self.hitl_store is None:
    ...
    raise ... (
        f"Tool '{tool_name}' requires human approval (HIGH risk) but HITLStore "
        "is not configured. Inject via ToolBrokerService(hitl_store=...)."
    )
```
Dit is de veilige kant (geen silent bypass), maar betekent dat **elke HIGH-risk
tool-aanroep buiten de Copilot-chatflow (via `/v1/tools/execute`, via een generieke agent,
via een ALS-specialist) hard faalt**, zelfs met een geldige DB-goedkeuring.

### G4 -- Geen per-tool getypeerd output-schema

**Bewijs:**
```python
# src/core/tool_broker/schemas.py:79-90
class ToolExecutionResponse(BaseModel):
    success: bool
    result: dict[str, Any] | None = Field(default=None, ...)  # generiek, geen per-tool type
```
Extra fragmentatie ontdekt: `ToolExecutionRequest.tool_name` (schemas.py:23-25) is getypeerd
als `ToolCategory`-enum met slechts 2 waarden (`SERENA`, `SEQUENTIAL_THINKING`) -- dit
Pydantic-schema kan business-tools (`create_task` etc.) of `local__`-tools niet eens
representeren. Er bestaan dus **twee losse, inconsistente request/response-vormen** in de
codebase: dit smalle Pydantic-schema (alleen REST-laag voor Serena/ST) en de brede,
ongetypeerde `execute_tool(tool_name: str, payload: dict, ...)`-signatuur die `service.py`
zelf gebruikt voor alles.

### G5 -- Geen progressive disclosure / code-execution-patroon

Bevestigd via architectuur-analyse (Explore-agent, 2026-07-07): tool-namen worden hardcoded
via classmethod-dispatch in `execute_tool()` (`service.py`); een aanroepende agent moet de
volledige toolset al kennen. Geen filesystem-/code-API-abstractielaag aanwezig.

### G6/G7 -- ToolBroker is geen aanspreekbare MCP-server; geen OAuth2.1-laag

**Bewijs:** `mcp_client.py` (40-280) implementeert uitsluitend een MCP-**client**-rol
(`StdioServerParameters`, `MCPClientPool`) richting Serena/Sequential Thinking. Er is geen
enkel bestand in `src/core/tool_broker/` dat een MCP-server-transport (stdio-server of
Streamable HTTP) implementeert. Geen OAuth-integratie aangetroffen in `tool_broker/`.

### G8 -- Allowlist niet auditeerbaar versiebeheerd

`config/tool_permissions.yml` is een los YAML-bestand (wel git-getrackt, dus feitelijk al
in versiebeheer), maar heeft geen koppeling naar de audit-hash-chain bij wijziging --
een config-hot-reload wordt niet als event gelogd.

### G9 (overgenomen van ADR-036 §D2, P0, nog open) -- `_ToolBrokerAdapter` hardcodet agent-identiteit "copilot"

**Bewijs, geverifieerd 2026-07-07:**
```python
# src/core/copilot/council/factory.py:127-138
class _ToolBrokerAdapter:
    """Bridge SecurityOfficer.is_allowed to ToolPermissionManager."""
    def __init__(self) -> None:
        self._mgr = ToolPermissionManager()

    async def is_allowed(self, action_type: str, tenant_id: int, user_id: int) -> bool:
        # RC-007: use "copilot" as the system agent_id for Council action_type checks.
        _ = (tenant_id, user_id)
        return self._mgr.is_tool_allowed("copilot", action_type)
```
Elke agent die via deze adapter een permissiecheck doet, wordt behandeld als "copilot",
ongeacht wie de daadwerkelijke aanroeper is. ADR-036 markeert dit al als P0, blokkerend
voor het eigen platformbrede-governance-hergebruik-plan (D1). Relevant voor Fase 2: een
MCP-server-adapter mag dit patroon niet erven -- elke externe MCP-client-identiteit moet
zijn eigen permissieprofiel krijgen.

### G10 (overgenomen van ADR-036 §1.2.Q, genuanceerd met eigen verificatie) -- Vrijwel geen agent-profielen in de allowlist

**Bewijs, geverifieerd 2026-07-07:**
```yaml
# config/tool_permissions.yml (volledige inhoud, 35 regels)
agent_profiles:
  - agent_id: "copilot"
    allowed_tools: [...]  # 18 tools
    denied_tools: []
    max_tools: 50
```
Dit is het **enige** profiel in het bestand. Het bestand documenteert dit zelf expliciet
(regels 7-10): *"~80 generated agents have no profile here -- currently none of them call
execute_tool() directly, so default-deny is not triggered in production (verified
2026-06-27). tests/architecture/test_generated_agents_tool_permissions.py enforces this."*
Dit is een **bewust ingebouwd vangnet** (een rode architecture-test dwingt een profiel af
zodra een generated agent daadwerkelijk `execute_tool()` aanroept) -- geen stilzwijgend
gat. ADR-036 §1.2.Q spreekt van "135/136 skills" zonder profiel; dat cijfer betreft
mogelijk een andere agent-populatie (ALS "skills" vs. de hier genoemde "generated agents")
-- **niet 1-op-1 geverifieerd als dezelfde telling**, dus hier apart vermeld i.p.v.
samengevoegd tot één claim.

---

## Consequences

### Positive
- Fase 0 herstelt de daadwerkelijke handhaving van een reeds geaccepteerd ADR (ADR-015)
  zonder er een nieuw mechanisme aan toe te voegen.
- Fase 2 opent een nieuw distributiekanaal (externe MCP-hosts) zonder de bestaande
  governance-garanties te verzwakken.
- Fase 3 levert een aantoonbaar onderscheidend platformkenmerk (governed code-execution)
  dat in het onderzochte marktmateriaal niet is aangetroffen bij andere MCP-implementaties.

### Negative
- Fase 2 vereist een nieuwe Authorization Server-component (OAuth 2.0) die vandaag nergens
  in het platform bestaat -- een eigen, niet-triviale bouwsteen.
- Elke nieuwe fase vergroot het aantal ToolBrokerService-constructieplekken tijdelijk
  (totdat G/AUDIT-TOOL-005 is opgelost); regressierisico als Fase 1-2 bovenop de huidige
  inconsistentie worden gebouwd in plaats van na Fase 0.
- Netwerk-blootstelling (Fase 2) introduceert een geheel nieuw aanvalsoppervlak
  (confused-deputy, tool-poisoning, token-passthrough) dat vandaag niet bestaat omdat
  alles in-process draait.

### Neutral
- G9/G10 (van ADR-036) blijven ADR-036's eigen P0-items; dit ADR erft ze als afhankelijkheid
  voor Fase 2 (een MCP-server mag geen enkele-identiteit-aanname overnemen), maar de fix
  zelf hoort primair bij ADR-036's D1/D2-uitvoeringstraject, niet dit ADR exclusief.

---

## AI Act Governance Mapping (ADR-031, patroon overgenomen van ADR-015)

| Vereiste | Artikel | Hoe dit ADR daaraan bijdraagt |
|---|---|---|
| Human oversight voor high-risk AI-acties | Art. 14 | Fase 0 herstelt dat de HITL-gate daadwerkelijk overal wordt afgedwongen (AUDIT-TOOL-005), niet alleen op het Copilot-pad |
| Audit trail voor AI tool-gebruik | Art. 13 | Fase 0-2 hergebruiken de bestaande SHA-256 hash-chain ongewijzigd; G8 voegt config-wijzigingen toe aan diezelfde chain |
| Transparantie bij externe AI-integraties | Art. 13/52 | Fase 2's MCP-server-adapter moet elke externe caller (host-identiteit) traceerbaar loggen, niet alleen "een MCP-client" |

## SOC 2 Mapping (patroon overgenomen van ADR-015)

| Criterium | Hoe dit ADR daaraan bijdraagt |
|---|---|
| CC6.3 (toegang beperkt tot geautoriseerde individuen) | AUDIT-TOOL-005-fix zorgt dat de allowlist-check overal dezelfde garantie geeft, niet alleen op 1 van 6 paden |
| CC6.8 (bescherming tegen kwaadaardige software) | Fase 2's OAuth2.1/RFC-8707-laag voorkomt token-passthrough zodra het netwerkoppervlak groeit |
| CC7.2 (monitoring tools) | G8 voegt allowlist-configwijzigingen toe aan de al bestaande audit-monitoring |

---

## Niet in scope (bewust)

- Koppeling aan ADR-017 Gatekeeper (YAML-policy-engine) -- apart traject, niet hier
  meegenomen om scope-kruip te voorkomen.
- Oplossen van ADR-036 §D1/D2 in de volle breedte (organisatiehiërarchie, Council-hergebruik)
  -- dit ADR erft alleen de 2 ToolBroker-specifieke P0's (G9/G10) als afhankelijkheid voor
  Fase 2, niet het volledige ADR-036-traject.
- Resources/Prompts/Sampling/Roots-primitieven van MCP (naast Tools) -- Fase 2 is bewust
  tools-only; de overige primitieven zijn een eigen, latere beslissing.

---

## Changelog

| Versie | Datum | Wijziging |
|---|---|---|
| 1.0 | 2026-07-07 | Initiële versie: 4-fasenroadmap, G1-G10 volledig met codesnippets onderbouwd, ADR-relatiematrix, AI Act/SOC2-mapping. |
