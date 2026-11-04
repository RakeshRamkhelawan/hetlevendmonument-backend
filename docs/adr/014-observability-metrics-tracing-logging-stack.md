# ADR-014: Observability - Metrics, Tracing & Logging Stack

## Status

Accepted

## Context

In een gedistribueerd systeem met AI-agenten is het onmogelijk om fouten te reproduceren zonder diepgaande telemetrie. We moeten weten:

- Welke tenant een fout genereerde.
- Welke LLM call leidde tot een vertraging (Tracing).
- Hebben we budget-overschrijdingen op AI-tokens?

## Decision

We implementeren een volledige **OpenTelemetry (OTel)** compatibele stack.

### 1. Tracing (Jaeger)

Elke inkomende request krijgt een `trace_id` die wordt doorgegeven aan:

- FastAPI handlers.
- Dramatiq workers (via message headers).
- LLM provider wrappers.

### 2. Metrics (Prometheus)

We exporteren de volgende kritieke SLI's:

| Metriek | Label | Gebruik |
| :--- | :--- | :--- |
| `request_latency_seconds` | `service`, `tenant_id` | SLO monitoring |
| `llm_token_usage_total` | `provider`, `tenant_id` | Billing & Budgeting |
| `worker_queue_depth` | `queue_name` | Auto-scaling triggers |

### 3. Structured Logging (JSON)

Logs worden geschreven in JSON-formaat voor eenvoudige aggregatie (bijv. in ELK of Grafana Loki).

```json
{
  "timestamp": "...",
  "level": "ERROR",
  "message": "LLM Timeout",
  "tenant_id": "...",
  "trace_id": "...",
  "component": "agent_worker"
}
```

## Consequences

- **Positive**:
  - Real-time inzicht in de kosten en performance per tenant.
  - "Needle in a haystack" debugging: Volg een actie van de frontend via de API naar de worker en terug.
- **Negative**:
  - Storage overhead: Traces en logs kunnen GB's aan data genereren.
- **Notes**:
  - We gebruiken een `O11yMiddleware` in FastAPI om automatisch `trace_id` en `tenant_id` aan elke log-line toe te voegen.

---

## Azure Log Analytics — implementatie (2026-05-26)

In het kader van het build-stack security programma (ADR-030, finding F-18) is Azure
Log Analytics geimplementeerd als gecentraliseerde logging-laag naast de bestaande
OTel-stack. Beide coexisteren: OTel/Jaeger/Prometheus dekken tracing en metrics;
Log Analytics dekt gecentraliseerde log-aggregatie en lange-termijnretentie.

### Workspaces

| Workspace | Regio | Omgeving |
|-----------|-------|----------|
| `sanskriti-logs-prd` | West Europe | Productie |
| `sanskriti-logs-stg` | North Europe | Staging |

### Retentie en capaciteit

- **Retentie:** 365 dagen. Grondslag: GDPR Art. 6(1)(f) (legitiem belang voor
  incident-onderzoek en audittrail-integriteit). Langer dan 365 dagen vereist
  expliciete herbeoordeling van de verwerkingsgrondslag.
- **Capacity cap:** 1 GB/dag. Bij overschrijding worden logs stilzwijgend afgekapt
  zonder foutmelding. Dit is een **GDPR Artikel 33-risico**: een gemist security-incident
  kan niet worden gerapporteerd als de betreffende logs zijn afgekapt. Actie: verhogen
  naar 5 GB/dag zodra productieverkeer bekend is. Monitoring via
  `_LogOperation | where OperationStatus == "Throttled"`.

### Log-formaat

Logs worden in JSON geschreven met de volgende verplichte velden:

```json
{
  "timestamp": "2026-05-26T14:32:00.000Z",
  "level": "ERROR",
  "message": "LLM provider timeout",
  "tenant_id": "42",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "component": "agent_worker"
}
```

Velden `tenant_id` en `trace_id` zijn verplicht voor elke log-regel die een request
of agent-actie beschrijft. Afwezigheid van `tenant_id` op een log-regel die
persoonsgegevens verwerkt is een GDPR-bevinding.

### KQL-querypatronen

Gebruik `parse_json(Log)` voor field matching, niet `contains` op de ruwe string.
`contains` op JSON-tekst faalt bij veldnamen die als prefix van andere veldnamen
voorkomen (bijv. `trace_id` vs `parent_trace_id`).

```kql
// GOED — parse_json voor exacte field matching
ContainerLog
| extend parsed = parse_json(Log)
| where parsed.tenant_id == "42"
| where parsed.level == "ERROR"
| project TimeGenerated, parsed.message, parsed.trace_id

// FOUT — string contains is fragiel
ContainerLog
| where Log contains '"tenant_id":"42"'
```

### Secret management

`workspacePrimarySharedKey` wordt **nooit** als Bicep-output of in git gezet.
ARM deployment history is plaintext en toegankelijk voor iedereen met
`Microsoft.Resources/deployments/read`-rechten op de resource group.

Ophalen:

```bash
az monitor log-analytics workspace get-shared-keys \
  --resource-group sanskritisetu-prod \
  --workspace-name sanskriti-logs-prd \
  --query primarySharedKey -o tsv
```

Bij het bijwerken van de Log Analytics-verbinding in een Azure Container App
(`az containerapp env update`) herstart de Container App Environment. Plan deze
operatie buiten productie-piekuren.

### Context Engine Observability (toegevoegd 2026-05-27)

De `AIContextEngine` introduceert nieuwe operationele surfaces die gemeten en gealert moeten worden:

**Nieuwe Prometheus metrics**:

| Metriek | Type | Labels | Gebruik |
|---|---|---|---|
| `context_engine_turns_total` | Counter | `tenant_id`, `surface` | Totale verrijkte turns per AI surface |
| `context_engine_retrieval_seconds` | Histogram | `source` (docs/registry/twin/memory) | P95 retrieval latency per bron |
| `context_engine_cache_hit_total` | Counter | `cache_tier` (memory/redis/none) | Cache hit rate voor retrieval |
| `context_engine_cache_miss_total` | Counter | `cache_tier` | Cache miss rate |
| `context_engine_truncation_total` | Counter | `tenant_id`, `surface` | Aantal turns waarbij context is getruncate |
| `context_engine_degraded_mode_total` | Counter | `tenant_id`, `reason` | Aantal turns in degraded mode (bron down) |
| `search_cross_tenant_leakage_detected_total` | Counter | `source` (bm25/vector) | **Moet altijd 0 zijn** — security incident als > 0 |
| `capability_registry_sync_seconds` | Histogram | — | UnifiedCapabilityRegistry refresh latency |
| `platform_knowledge_index_age_seconds` | Gauge | — | Tijd sinds laatste index rebuild |

**Nieuwe Grafana alert rules**:

| Alert | Severity | Trigger | Actie |
|---|---|---|---|
| `ContextEngineP95LatencyHigh` | warning | `context_engine_retrieval_seconds{source="vector"} > 0.5s` | Check vector store load; overweeg ANN index |
| `ContextEngineDegradedModeSpike` | warning | `context_engine_degraded_mode_total > 10/5min` | Eén of meer bronnen down; check health endpoints |
| `SearchCrossTenantLeakage` | **critical** | `search_cross_tenant_leakage_detected_total > 0` | Onmiddellijk onderzoek; mogelijk data breach |
| `PlatformKnowledgeIndexStale` | warning | `platform_knowledge_index_age_seconds > 86400` | Index rebuild is uitgevallen; deploy of cron check |

**Nieuwe tracing spans**:
- `context_engine.enrich` — parent span voor volledige verrijking
- `context_engine.retrieve.{source}` — per bron (docs, registry, twin, memory)
- `context_engine.pack` — token budget + truncation
- `context_engine.inject` — prompt injectie

### Relatie tot OTel-stack

Log Analytics is een **bridge** naar de volledige OTel-stack die in dit ADR is
gedefinieerd. De architectuur is:

```text
Applicatie (structurele JSON logs)
    |
    +---> Log Analytics (gecentraliseerd, 365d retentie, KQL)
    |
    +---> OTel Collector (toekomst: traces naar Jaeger, metrics naar Prometheus)
```

In de productie-MVP-fase stuurt de applicatie logs naar Log Analytics via de
Azure Container Apps log-routing. De OTel Collector wordt toegevoegd als de
tracing-infrastructuur (Jaeger) actief is (post-MVP).

## Changelog

- **2026-05-26** — Azure Log Analytics sectie toegevoegd na build-stack security
  programma (ADR-030 F-18); dual workspace, retentie-beleid, GDPR-grondslag,
  KQL-querypatronen, secret management procedure gedocumenteerd.
  Originele opmaakfouten (MD022, MD032, MD007, MD058, MD031) hersteld.
- **2026-05-27** — Context Engine Observability sectie toegevoegd; 9 nieuwe metrics, 4 alert rules, tracing span specificatie voor AIContextEngine retrieval pipeline.

## Changelog

- **2026-05-26** — Azure Log Analytics sectie toegevoegd na build-stack security
  programma (ADR-030 F-18); dual workspace, retentie-beleid, GDPR-grondslag,
  KQL-querypatronen, secret management procedure gedocumenteerd.
  Originele opmaakfouten (MD022, MD032, MD007, MD058, MD031) hersteld.
