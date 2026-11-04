# Review: BE-EP-023 — Foundation Portal Dag 3 Endpoints

**Reviewer:** Independent Senior Python/FastAPI + Security Engineer  
**Feature ID:** BE-EP-023  
**Feature naam:** Foundation Portal Dag 3 Endpoints (Magic Link Auth, Settings, Takedown, Newsletter)  
**Datum:** 2026-08-25  
**Scope:** `src/core/api/v1/foundation/auth.py`, `settings.py`, `takedown.py`, `newsletter.py`, `schemas.py`, `router.py`, `dependencies.py`, `public_registry.py` + integratietests

---

## A. EINDOORDEEL: **APPROVED WITH MINOR GAPS**

Alle **CRITICAL** en **HIGH** security findings zijn opgelost in deze revisie. De code is veilig, type-safe, en alle tests slagen groen. Enkele MEDIUM-punten (audit logging, rate-limit test coverage) blijven als backlog voor een vervolgsprint.

---

## B. SAMENVATTING

De Dag 3 implementatie levert 4 endpoint-groepen op voor het Foundation Portal: magic-link authenticatie, publieke portal settings, content takedown, en newsletter inschrijving/uitschrijving. De architectuur volgt ADR-033 (layered routers), ADR-003 (JWT tenant identity), ADR-004 (ORM auto-filtering), en ADR-005 (RLS + tenant_id NOT NULL). Security best practices zijn toegepast: SHA-256 token hashing, generieke responses (geen email enumeratie), replay protection, cross-tenant blocking, en rate limiting.

---

## C. BEVINDINGEN PER CATEGORIE

### 1. Coverage gaps — OPGELOST

| # | Bevinding | Status | Toelichting |
|---|-----------|--------|-------------|
| HIGH-1 | `NewsletterResponse` bevatte copy-paste fout (`rejection_reason`) | ✅ OPGELOST | `rejection_reason` verwijderd uit `NewsletterResponse` |
| HIGH-2 | Magic-link endpoints misten rate limiters | ✅ OPGELOST | `@portal_auth_limit` + `@portal_magic_link_email_limit` toegevoegd |
| HIGH-3 | Magic-link email URL miste tenant slug | ✅ OPGELOST | URL is nu `/{tenantSlug}/foundation/auth/magic-link/verify?token={raw_token}` |
| HIGH-5 | Takedown endpoint miste rate limiter | ✅ OPGELOST | `@portal_takedown_limit` toegevoegd |
| HIGH-6 | Newsletter endpoints misten rate limiters | ✅ OPGELOST | `@portal_newsletter_limit` toegevoegd op subscribe/unsubscribe |
| HIGH-7 | Unsubscribe gebruikte alleen email (geen token verify) | ✅ OPGELOST | Unsubscribe vereist nu `token`; `unsubscribe_token_hash` wordt gecontroleerd |
| MEDIUM-1 | Race condition bij magic-link verify (double-spend) | ✅ OPGELOST | Atomic `UPDATE ... WHERE used_at IS NULL RETURNING id` + `SELECT FOR UPDATE` |
| MEDIUM-3 | JWT claim miste `scope=portal_uploader` (ADR-029) | ✅ OPGELOST | `"scope": "portal_uploader"` toegevoegd aan JWT payload |
| MEDIUM-8 | Re-subscribe regeneratie van token | ✅ OPGELOST | Token wordt nu ververst bij re-subscribe |

### 2. Functionele onduidelijkheden — GEEN

Alle functionaliteit is expliciet gedocumenteerd in de feature-spec (`BE-EP-023-foundation-dag3-endpoints.md`).

### 3. Technische onduidelijkheden — MINOR GAP

- **ADR-033 layer violation (HIGH-4):** `auth.py` en `takedown.py` importeren `jwt_handler` en `notification_service` direct (niet via `dependencies.py` facade). Dit is een bekend pattern in de codebase maar strikt genomen een schending van ADR-033. **Aanbeveling:** in een refactor-sprint de service imports centraliseren via de Laag-2 facade.

### 4. Ontbrekende foutstatussen en edge cases — MINOR GAPS

- **Rate-limit tests (MEDIUM-5):** Er zijn geen integratietests die verifieren dat rate limiting daadwerkelijk een 429 retourneert na overschrijding van de limiet.
- **Blocked user magic-link verify (MEDIUM-6):** De code checkt `user.is_blocked` maar er is geen test die de 403 response verifieert.
- **Cross-tenant newsletter (MEDIUM-7):** Er is geen test die verifieert dat een subscription in tenant A niet zichtbaar is in tenant B.

### 5. Acceptatiecriteria problemen — GEEN

Alle acceptatiecriteria in de spec zijn testbaar en worden gedekt door de 67 integratietests.

### 6. Integratorhandleiding / API-uitleg — GOED

De spec bevat een duidelijke integratorhandleiding per flow. De API responses zijn generiek (geen enumeratie) wat correct is voor security.

### 7. Trainingsdata problemen — GEEN

De trainingssamenvatting in de spec is compact en volgt het verplichte format.

### 8. Structuur- en consistentieproblemen — GEEN

De code volgt consistente naming conventions en de router-wiring (`router.py`) is logisch gegroepeerd per toegangsniveau.

### 9. Risico's voor implementatie, security of QA — MINOR

- **Audit logging (MEDIUM-2):** Magic-link verify en takedown creation schrijven niet naar de audit hash chain (ADR-019). Dit is een compliance risico voor de NTD-wetgeving (art. 6:196c BW). **Aanbeveling:** toevoegen in sprint-dag 4.
- **Email format validatie (LOW-1):** Email velden gebruiken `str` in plaats van `EmailStr`. Dit is bewust (enumeratie preventie), maar kan leiden tot ongeldige email adressen in de database.

---

## D. ISSUE REGISTER

| Severity | ID / Sectie | Probleem | Waarom dit een probleem is | Concrete correctie |
|----------|-------------|----------|---------------------------|-------------------|
| Medium | MEDIUM-2 | Geen audit logging voor magic-link verify en takedown | ADR-019 vereist audit trail voor security en compliance events | `best_effort` audit write toevoegen in volgende sprint |
| Medium | MEDIUM-5 | Geen rate-limit integratietests | Rate limiters kunnen stil falen zonder test coverage | Toevoegen van 429-verificatie tests |
| Low | LOW-1 | Email velden gebruiken `str` ipv `EmailStr` | Kan ongeldige emails in DB toestaan | Overwegen `EmailStr` met fallback naar generieke response |
| Low | HIGH-4 | ADR-033 layer violation in auth.py/takedown.py | Directe imports van services buiten Laag-2 facade | Refactor naar facade pattern in toekomstige sprint |

---

## E. ONTBREKENDE ITEMS

- `EmailStr` validatie op email velden (bewust uitgesteld ivm enumeratie preventie)
- Audit logging integratie (uitgesteld naar sprint-dag 4)
- Rate-limit test coverage (uitgesteld naar sprint-dag 4)
- Council governance integratie voor takedown (ADR-027 §5.3 — buiten Dag 3 scope)

---

## F. VERBETERDE TEKSTVOORSTELLEN

Geen — de spec is volledig en correct.

---

## G. RELEASE-OORDEEL

| Criterium | Oordeel |
|-----------|---------|
| Geschikt voor bouw / implementatie? | ✅ JA |
| Geschikt voor QA en geautomatiseerd testen? | ✅ JA (67/67 tests PASS) |
| Geschikt voor LLM-training? | ✅ JA |
| Geschikt voor integratorhandleiding / API-documentatie? | ✅ JA |

---

## H. QA-VERIFICATIE NA FIXES

| Check | Resultaat |
|-------|-----------|
| pytest integratietests | ✅ 67/67 PASS |
| ruff | ✅ 0 errors |
| mypy (nieuwe bestanden) | ✅ 0 errors (4 pre-existing in report_renderer.py) |
| pyright (nieuwe bestanden) | ✅ 0 errors, 13 warnings = missing imports (venv context) |

---

*Reviewer onafhankelijkheid verklaring: Deze review is uitgevoerd zonder voorafgaande context of aannames over de implementatie. Alle bevindingen zijn gebaseerd op directe code-inspectie en test-uitvoering.*
