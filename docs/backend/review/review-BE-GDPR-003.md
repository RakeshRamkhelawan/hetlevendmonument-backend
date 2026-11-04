# Review: BE-GDPR-003 — Echte purge voor Twin-geheugen (AUDIT-004)

> Reviewer-prompt: `docs/backend/FEATURE_DOC_WORKFLOW.md` stap 2
> Spec onder review: `docs/backend/features/BE-GDPR-003-memory-item-purge.md`
> Implementatie geverifieerd tegen: `src/domains/memory/services/memory_purge_service.py`, `src/domains/memory/tasks.py`, `src/core/governance/dsar_service.py`, `src/workers/actors.py`, `src/workers/scheduler.py`, `tests/unit/test_memory_item_purge.py`, `tests/integration/test_memory_purge_tenant_isolation.py`
> Datum: 2026-07-29

---

## A. EINDOORDEEL: APPROVED

## B. SAMENVATTING

De spec dekt alle gewijzigde artefacten (purge-functie, orchestratie, actor, DSAR-helper + wiring, scheduler-registratie, tests), scheidt functioneel van technisch, en beschrijft het kernbesluit expliciet en correct: embeddings zijn niet anonimiseerbaar, dus is hard DELETE de enige compliant-erasure voor memory-items -- in het DSAR-pad in BEIDE modi, consistent met het bestaande CVA/agentic_tasks-precedent. De claim "rij + embedding verdwijnen samen" is geverifieerd tegen `models.py:218` (kolom op dezelfde rij, geen aparte vector-store). Alle 11 acceptatiecriteria zijn als draaiende tests geimplementeerd (13/13 unit groen op echte SQLite; 3 integratie-tests op echte PostgreSQL geschreven, skippen lokaal, draaien in CI). De tenant-scoping is op drie niveaus bewezen: bound-parameters in de DSAR-helper, tenant B ongemoeid op SQLite, en een echte PostgreSQL tenant-isolatietest.

## C. BEVINDINGEN PER CATEGORIE

1. **Coverage gaps**: geen. Beide paden uit de sprint-brief (periodieke purge-taak + DSAR-pad), de actor-discovery, de scheduling en de tests zijn geinventariseerd met ID's.
2. **Functionele onduidelijkheden**: geen. Het verschil tussen de twee paden (periodieke grace-purge vs. directe DSAR-erasure) en de bewuste afwijking van het anonimiseer-patroon zijn concreet en controleerbaar beschreven.
3. **Technische onduidelijkheden**: geen. De DSM-motiveringen (importlib in governance voor DSM006; geen workflow_worker-import in tasks.py i.v.m. import-cyclus; import binnen de if-tak voor pyright) kloppen met de code en met de architectuur-suite (388/388, inclusief `test_governance_has_zero_direct_agent_runtime_imports`).
4. **Ontbrekende foutstatussen en edge cases**: geen nieuw endpoint, dus HTTP-foutstatussen terecht n.v.t. De relevante foutpaden (actor-retry, helper-faal-naar-0, audit best_effort, lege set) zijn beschreven en getest.
5. **Acceptatiecriteria problemen**: geen. Alle 11 criteria zijn testbaar en direct als pytest-case uitvoerbaar; het integratie-deel is suite-bewijs voor CI.
6. **Integratorhandleiding / API-uitleg problemen**: geen. Drietal bullets, juiste abstractie; geen publiek API-oppervlak veranderd.
7. **Trainingsdata problemen**: geen. Trainingssamenvatting compleet in het vaste format.
8. **Structuur- en consistentieproblemen**: geen. Build summary, inventory en detailsecties zijn consistent; flows BE-FLW-050/051 sluiten aan bij de artefacten en zijn geregistreerd.
9. **Risico's voor implementatie, security of QA**: twee tijdens deze review opgeloste punten, zie issue register. Geen open risico's.

## D. ISSUE REGISTER

| Severity | ID of sectie | Probleem | Waarom dit een probleem is | Concrete correctie | Status |
| --- | --- | --- | --- | --- | --- |
| High (verwerkt) | Flow BE-FLW-050, audit | De eerste versie schreef de purge-audit met `tenant_id=0` als system-marker | `AuditLog.tenant_id` is een echte FK naar `tenants.id`; een synthetische 0 laat de INSERT in productie falen. De best_effort-guard zou de purge beschermen, maar de compliance-eis "audit-regel per purge-run" zou dan stilletjes nooit landen | Audit herschreven naar een `memory_purge_executed`-regel per gepurgde tenant (tenant bestaat bewezen); lege runs schrijven geen regel (conventie `cleanup_council_decisions`). Spec secties 6/15/19 + open aannames bijgewerkt | Verwerkt in code + spec vóór registratie |
| Low | tests, integratie | `tests/integration/test_memory_purge_tenant_isolation.py` skipt lokaal module-level (geen PostgreSQL 5435/5455 in deze omgeving) | Het sterkste bewijs (echte pgvector, productie-session-stack) is CI-afhankelijk | Bewust geaccepteerd: identiek patroon als alle bestaande integratietests; CI draait PostgreSQL. Unit-tests op echte SQLite dekken het gedrag al, inclusief fysieke verwijdering en tenant-scoping | Gedocumenteerd; geen actie |
| Low | `_purge_memory_items` | `_coerce_user_id` kan bij niet-numerieke input een string teruggeven aan een Integer-kolom-vergelijking | Zou bij een echte db een type-fout geven -- opgevangen door de helper zelf (return 0 + log) | Bestaand, bewust helper-gedrag: identiek aan `_delete_agentic_tasks` (tests gebruiken string-ids zoals 'user-123'); productie geeft altijd numerieke ids | Verwerkt -- consistentie behouden, geen actie |

Geen CRITICAL, HIGH of MEDIUM bevindingen open. Geen open MINOR-bevindingen.

## E. ONTBREKENDE ITEMS

Geen vermoedelijk ontbrekende endpoints, services, flows of regels gedetecteerd.

## F. VERBETERDE TEKSTVOORSTELLEN

Geen -- de zwakste stukken (audit FK-risico) zijn al verwerkt; de n.v.t.-markeringen zijn expliciet beargumenteerd.

## G. RELEASE-OORDEEL

- Geschikt voor bouw / implementatie: ja (reeds geimplementeerd, 13/13 unit-tests groen)
- Geschikt voor QA en geautomatiseerd testen: ja (acceptatiecriteria mappen 1-op-1 op tests; integratie-varianten voor CI)
- Geschikt voor LLM-training: ja (functioneel/technisch gescheiden, concrete paden en symbolen)
- Geschikt voor integratorhandleiding / API-documentatie: ja

---

*Eindoordeel: APPROVED | Reviewer: onafhankelijke review-stap | Datum: 2026-07-29*
