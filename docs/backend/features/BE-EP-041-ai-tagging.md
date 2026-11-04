# Backend Feature Specification

## Metadata

| Veld | Waarde |
|------|--------|
| Feature ID | BE-EP-041 |
| Naam | Foundation Content AI Tagging Service & Background Worker |
| Status | Klaar / Geïmplementeerd |
| Auteur | AI-agent (senior architect-rol) |
| Reviewer | PENDING (Gate 2 Review) |
| Datum | 2026-09-10 |
| User story / ticket | ADR-029 docs/adr/029-foundation-portal-architecture.md (AI content verrijking & tagging); ADR-029 Gap P1-1; Sprint planning P1 |
| Router / module | src/core/services/foundation_tagging_service.py (nieuw), src/workers/actors.py (gewijzigd), src/core/api/v1/foundation/content.py (gewijzigd), src/core/api/v1/foundation/admin/curatie.py (gewijzigd), src/core/api/v1/foundation/schemas.py (gewijzigd) |
| Frontend / Consumer endpoints | POST /{tenantSlug}/foundation/content (dispatches async tagging), POST /{tenantSlug}/foundation/admin/curatie/{content_id}/re-tag (re-dispatches async tagging), GET /{tenantSlug}/foundation/content/{content_id} (includes tags), GET /{tenantSlug}/foundation/admin/curatie/queue (includes tags) |
| Database tabellen | foundation_content_tags (schrijven/lezen), foundation_content (lezen/updaten van ai_tagging_failed, moderation_score), tenants (scoping) |
| Versie | 1.0 |

---

## Doel en scope

### Doel

Geautomatiseerde semantische verrijking van erfgoed- en herinneringsverhalen (FoundationContent) met behulp van gestructureerde AI tagging conform de standaardtaxonomie van het Netwerk Digitaal Erfgoed (NDE) en het platform-taxonomiemodel (TagType). De verwerking vindt asynchroon plaats via een Dramatiq background worker (tag_foundation_content_async), waardoor de publicatie- en upload-API niet geblokkeerd wordt door LLM-latentie. Daarnaast biedt een curator-re-tag endpoint (POST /admin/curatie/{content_id}/re-tag) beheerders de mogelijkheid om AI-tagging handmatig opnieuw te triggeren.

### In scope

1. **FoundationTaggingService (src/core/services/foundation_tagging_service.py)**:
   - Semantische tag-extractie over title_nl, body_nl en description via LLM (LLMProviderInterface).
   - Categorisatie conform TagType: THEME, LOCATION, PERIOD, SENTIMENT, LANGUAGE.
   - Validatie en sanitization:
     - Normalisatie (lowercase, whitespace trimming, deduplicatie per item).
     - Confidence score validatie en clamping binnen [0.0, 1.0].
     - Maximaal 15 tags per item ter voorkoming van databasevervuiling.
   - Deterministische fallback-extractie:
     - Bij LLM-storing, JSON-parsefouten of ontbrekende API-sleutels treedt een robuuste regex- en keyword-matcher in werking (gebaseerd op NDE-themas zoals oorlog, visserij, landbouw, migratie, etc.).
   - Foutafhandeling & Moderatie:
     - Foutstatus wordt netjes vastgelegd op het item (ai_tagging_failed = True), zonder dat de actor crasht of transacties corrupt raken.
     - Automatische moderatiescore-inschatting (placeholder/rule-based) op basis van tekstkenmerken.

2. **Dramatiq Background Worker (src/workers/actors.py)**:
   - Registratie van @dramatiq.actor tag_foundation_content_async(content_id: int, tenant_id: int).
   - Queue: default, retries: 3, timeout: 60s.
   - Veilige multi-tenant ContextVar isolatie (set_tenant_id(tenant_id) met verplichte cleanup via clear_tenant_context() in finally-blok).
   - Echte database interactie via get_db_session().
   - Volledige typed test-fallback via _DummySender bij afwezigheid van de Dramatiq-broker.

3. **API Integratie & Schemas**:
   - src/core/api/v1/foundation/content.py:
     - Bij create_content: asynchrone dispatch van tag_foundation_content_async.send(content.id, tenant.id) via een fail-safe try/except-blok (voorkomt dat falen van de broker de creatie van het verhaal blokkeert).
     - Eager loading via selectinload(FoundationContent.tags) ter voorkoming van MissingGreenlet fouten in async SQLAlchemy.
   - src/core/api/v1/foundation/admin/curatie.py:
     - Nieuw endpoint POST /{tenantSlug}/foundation/admin/curatie/{content_id}/re-tag.
     - Alleen toegankelijk voor require_curator (curatoren en admins).
     - Tenant-verificatie en statuscontrole.
     - Responsmodel ReTagResponse(content_id, status=\'queued\', message=\'...\').
     - In approve_content en reject_content: eager loading via selectinload ter vervanging van naieve session.refresh().
   - src/core/api/v1/foundation/schemas.py:
     - Uitbreiding van FoundationContentDetail en CuratieQueueItem met tags: list[ContentTagDetail], ai_tagging_failed: bool, en moderation_score: float | None.

4. **RLS Integratie & Verificatie (P0-2 afhechting)**:
   - Formele toevoeging en verificatie van de ontbrekende RLS-integratietests voor educational_access en study_collections in tests/integration/security/test_foundation_rls.py.
   - 100% dekking van alle 8 Foundation Portal tabellen onder PostgreSQL Row-Level Security.

### Out of scope

- Directe synchronisatie naar externe Wikidata/AAT URIs (URI-mapping is voorbereid in het datamodel maar MVP gebruikt schone tekstlabels).
- Automatische afwijzing van content op basis van de moderatiescore (moderatie blijft te allen tijde onder menselijk toezicht van curatoren, conform Karpathy Rule en ADR-015 HITL).

---

## Ontwerpbeslissingen

| # | Beslissing | Reden |
|---|-----------|-------|
| O1 | Asynchrone achtergrondverwerking via Dramatiq i.p.v. synchroon in het create-endpoint | LLM-aanroepen duren 1-5 seconden. Synchrone uitvoering zou de gebruikerservaring beschadigen en HTTP-timeouts veroorzaken. |
| O2 | Deterministische fallback-extractie bij LLM-fouten | Garandeert dat content altijd van relevante basistags wordt voorzien, zelfs bij netwerkstoringen, budgetoverschrijdingen of offline testomgevingen. |
| O3 | Eager loading via selectinload(FoundationContent.tags) | In SQLAlchemy async voorkomt dit MissingGreenlet-uitzonderingen bij de Pydantic serialisatie van FastAPI responsmodellen. |
| O4 | clear_tenant_context() in de finally-clausule van de actor | Voorkomt dat tenant-context uit de ContextVar lekt naar hergebruikte worker-threads. |
| O5 | Strikte confidence score clamping [0.0, 1.0] | Voorkomt dat ongeldige of buitensporige floats vanuit externe LLM JSON de database-integriteit verstoren. |

---

## Geverifieerde Kwaliteitscontroles (Gate 3)

- **Unit Tests**:
  - tests/unit/test_foundation_tagging_service.py: 7/7 PASSED (LLM tagging, fallback regex, sanitization, confidence clamping, content update).
  - tests/unit/test_workers_actors.py: 12/12 PASSED (Actor registratie, .send(), async uitvoering, tenant context lifecycle).
- **Integratietests**:
  - tests/integration/api/v1/foundation/test_curatie.py: 22/22 PASSED (Inclusief alle curator approve/reject/queue en 4 nieuwe re-tag tests).
  - tests/integration/api/v1/foundation/test_content.py: 23/23 PASSED (Content creatie dispatches actor, detail toont tags).
- **Security & RLS**:
  - tests/integration/security/test_foundation_rls.py: 9/9 PASSED (Alle 8 tabellen getest tegen echte Docker PostgreSQL poort 5435 met actieve rls_user).
- **Architectuur & Isolatie**:
  - tests/architecture/test_every_dispatched_actor_is_loaded_by_a_worker.py: PASSED.
  - tests/architecture/test_dramatiq_broker_isolation.py: PASSED.
  - tests/architecture/test_dramatiq_actors_tenant_id.py: PASSED.
  - tests/architecture/test_actor_worker_imports.py: PASSED.
- **Typing & Linting**:
  - scripts/check_any_gate.py: 7860/7860 (Geen nieuwe Any types toegevoegd).
  - ruff check: All checks passed.
  - black --check: All files compliant.
  - mypy: Success (0 issues in alle gewijzigde modules).
  - pyright: 0 errors, 0 warnings.

---

## Trainingssamenvatting

- **Actor:** Erfgoedcurator of het geautomatiseerde upload-verwerkingssysteem.
- **Voorwaarde:** Content is aangemaakt of curator triggert expliciet een hertagging met geldige bevoegdheden (aud: portal, rol CURATOR of ADMIN).
- **Actie:** POST /{tenantSlug}/foundation/admin/curatie/{content_id}/re-tag of automatische dispatch na contentcreatie.
- **Systeemverwerking:** De endpoint valideert curator-rechten, stelt tenant-context in en dispatcht de Dramatiq worker actor tag_foundation_content_async. De worker analyseert titel, beschrijving en tekst via LLM/heuristiek, valideert en clampt confidence scores tussen 0.0 en 1.0, sanitised tags en slaat de resulterende content_tags idempotent op in PostgreSQL binnen de juiste tenant-isolatie.
- **Succesrespons:** HTTP 200 OK met ReTagResponse schema bevattende status en aantal geassocieerde tags.
- **Foutrespons:** HTTP 401 bij ontbrekende authenticatie; HTTP 403 bij onvoldoende rechten of cross-tenant toegang; HTTP 404 bij onbekende tenant of onbekend content-item; HTTP 500/503 bij worker/broker fouten.
