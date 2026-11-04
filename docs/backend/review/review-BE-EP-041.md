# Code & Quality Review: BE-EP-041 AI Content Tagging Service & Background Worker
 
STATUS: APPROVED
 
## Metadata

| Veld | Waarde |
|------|--------|
| Feature ID | BE-EP-041 / BE-SVC-018 |
| Feature Naam | Foundation Content AI Tagging Service & Background Worker |
| Reviewer | Red Team / Shadow CEO AI Reviewer |
| Status | APPROVED / GO (met Devil\'s Advocate opvolgpunten) |
| Datum | 2026-09-10 |
| Getoetste commits / wijzigingen | src/core/services/foundation_tagging_service.py, src/workers/actors.py, src/core/api/v1/foundation/content.py, src/core/api/v1/foundation/admin/curatie.py, src/core/api/v1/foundation/schemas.py, 	ests/unit/test_foundation_tagging_service.py, 	ests/unit/test_workers_actors.py, 	ests/integration/api/v1/foundation/test_curatie.py, 	ests/integration/security/test_foundation_rls.py |

---

## 1. Doel van de Review

Toetsing van de implementatie van ADR-029 Gap P1-1 (AI Content Tagging Service & Background Worker) en de afronding van P0-2 (RLS-integratietests voor educational_access en study_collections) conform de projectrichtlijnen (CLAUDE.md / AGENTS.md), de 3 Quality Gates en het Red Team Mandaat.

---

## 2. Toetsing van de Quality Gates

### Gate 1: Scope & Architectuur
- **Asynchrone Ontkoppeling**: De tagging workflow blokkeert de openbare submit-flow niet; create_content vuurt een Dramatiq background job af binnen een fail-safe context.
- **Multi-Tenancy & Isolatie**: De background worker stelt de tenant-context in via set_tenant_id en ruimt deze gegarandeerd op in een inally-blok via clear_tenant_context().
- **Eager Loading**: MissingGreenlet-uitzonderingen in FastAPI/SQLAlchemy async worden voorkomen door consistente selectinload(FoundationContent.tags).
- **Status**: PASSED.

### Gate 2: Code Kwaliteit & Beveiliging
- **Row-Level Security (RLS)**: De integratietests dekken nu alle 8 tabellen van de Foundation Portal (inclusief educational_access en study_collections). Alle 9 tests slagen tegen de echte Postgres-instantie.
- **Autorisatie & RBAC**: Het re-tag endpoint (POST /admin/curatie/{content_id}/re-tag) vereist 
equire_curator en verifieert tenant-eigenaarschap via public_tenant_scope.
- **Status**: PASSED.

### Gate 3: Statische Analyse & Tests
- **Tests**: 76 relevante unit-, integratie- en architectuurtests zijn 100% groen (61.23s).
- **Mypy & Pyright**: 0 fouten, 0 waarschuwingen.
- **Any-Gate**: Baseline exact behouden op 7860 (geen nieuw Any-type geïntroduceerd, TaggingActorResult strikt getypt via TypedDict).
- **Ruff & Black**: 100% compliant.
- **Status**: PASSED.

---

## 3. Red Team Mandaat: Devil\'s Advocate Analyse

Waarom en hoe kan deze oplossing in de toekomst falen in productie?

1. **LLM Quota & Batch Upload Denial-of-Service**:
   - *Risico*: Als een beheerder via een toekomstige CSV/Excel-importfunctie of een harvesting-script 5.000 verhalen tegelijk uploadt, spawnt het systeem 5.000 Dramatiq jobs die gelijktijdig LLM-aanroepen doen. Zonder concurrency rate limiter of token bucket per tenant lopen API-keys van OpenAI/Anthropic/DeepSeek direct tegen HTTP 429 quota-limieten aan.
   - *Aanbeveling*: Introduceer een dedicated Dramatiq worker-queue met strikte concurrency caps (bijv. max 2 gelijktijdige LLM calls per worker) of exponentiële backoff bij 429 statuscodes.

2. **Tag Drift & Gebrek aan Canonieke Thesaurus-Binding**:
   - *Risico*: Hoewel tags worden gemapt naar TagType, genereert het LLM vrije strings (bijv. \'bevrijding\', \'de bevrijding\', \'bevrijdingsdag\', \'1945 bevrijding\'). Zonder een strikte referentiethesaurus (zoals de NDE Erfgoedthesaurus / GTAA) leidt dit na 10.000 verhalen tot extreme taxonomie-fragmentatie.
   - *Aanbeveling*: Bouw in Fase 2 een reconciliatie-stap (thesaurus-linker) die LLM-termen mapt naar preferred terms en NDE URI\'s.

3. **Silent Failure vs. Retry Vermoeidheid**:
   - *Risico*: Bij een blijvende fout zet de service i_tagging_failed = True en keert terug naar fallback tags. Hoewel dit voorkomt dat de queue vastloopt, kan een storing in de LLM provider ertoe leiden dat duizenden verhalen \'stil\' met inferieure basistags worden gevuld zonder dat er een alert afgaat in Sentry/Prometheus.
   - *Aanbeveling*: Voeg een Prometheus-teller toe voor oundation_tagging_fallback_total zodat monitoring alarm slaat als het fallback-percentage boven 5% stijgt.

---

## 4. Eindoordeel

**Verdict: APPROVED / GO**
De implementatie lost ADR-029 Gap P1-1 en de openstaande RLS-integratie van P0-2 volledig en chirurgisch op. De code is robuust, getypeerd, getest en voldoet aan alle project- en veiligheidsregels.
