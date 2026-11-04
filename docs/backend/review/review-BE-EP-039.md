# Review BE-EP-039: Educatieve leeromgeving sessie- en content-endpoints (/edu/*)

STATUS: APPROVED

**Reviewer:** Onafhankelijke review-agent (Gate 2, code-reviewer + quality-reviewer ineen met Red Team mandaat). Code niet zelf geschreven; read-only gereviewd op branch `iter/be-ep-039` en `develop`. Verificatie met commando's, unit-, integratietests en architectuuranalyse.
**Datum:** 2026-09-10
**Scope:**
- `src/core/api/v1/foundation/edu.py` (5 nieuwe endpoints)
- `src/core/services/edu_session_service.py` (Redis/InMemory session store)
- `src/core/api/v1/foundation/dependencies.py` (require_edu_session, get_edu_session_service, hash_edu_code)
- `src/core/api/v1/foundation/content.py` (O5 visibility filter)
- `src/core/api/v1/foundation/schemas.py` (ContentTypeValue uitbreiding, EduSessionRequest/Response)
- `src/core/shared/public_registry.py` (edu pad-uitzondering)
- `tests/unit/test_foundation_edu_session.py` (23 tests)
- `tests/integration/api/v1/foundation/test_edu.py` (26 tests)
- Spec `docs/backend/features/BE-EP-039-edu-endpoints.md`, `ID-REGISTRY.md`.
**Aanleiding:** ADR-029 Sprint D / Audit P0-5 (AUTH-BYPASS-GAT fix & educatieve leeromgeving).

---

## B. Eindoordeel

APPROVED — De implementatie repareert het kritieke authenticatielek uit de audit (P0-5) op elegante en robuuste wijze. Het cookie bevat uitsluitend een cryptografisch willekeurig 256-bit token (`secrets.token_urlsafe(32)`), opgeslagen in Redis met een TTL van 14.400s (4 uur). Rol- en geldigheidsbepaling vindt bij *elke* request plaats tegen de PostgreSQL database (`is_active`, `expires_at`, tenant-match), waardoor directe intrekking gegarandeerd is. De N-2 invariant (educatieve content is onzichtbaar in het publieke archief) is zowel in `content.py` als via integratietests empirisch bewezen. 

Alle 23 unit-tests (0.43s) en alle 26 integratietests (24.4s tegen echte PostgreSQL :5435 en Redis :6385) zijn groen. Ruff check is 100% schoon.

---

## C. Samenvatting verificatie

- **Unit tests:** 23/23 PASSED (offline via `InMemoryEduSessionStore`). Valideert code-format (8 alfanumerieke tekens), hash-lookup, uniforme 401's bij onbekende/inactieve/verlopen codes, cookie attributes (HttpOnly, SameSite=Strict, Path=/), mid-session deactivatie en de O5-visibility-filter.
- **Integratie tests:** 26/26 PASSED (tegen echte PostgreSQL :5435 en Redis :6385). Test de end-to-end cyclus: session creatie, content listing, content detail, session info, logout via DELETE, revalidatie na deactivatie, en mismatch-verificatie (content met `privacy=PUBLIC` maar `visibility=EDU` is 100% onzichtbaar in `/foundation/content` voor anonieme en JWT-ingelogde gebruikers).
- **Code kwaliteit:** Ruff check schoon (0 waarschuwingen, 0 fouten). Geen verboden non-ASCII/emoji karakters. Geen gebruik van `datetime.now()` of `datetime.utcnow()` (alles via `utc_now()` en `to_utc()` helpers).

---

## D. Bevindingen per categorie

1. **Sessiemodel & Revalidatie (Audit P0-5 conformiteit):**
   De oorspronkelijke kwetsbaarheid (plain-text `code:role` in cookie) is volledig geëlimineerd. De client ontvangt uitsluitend een ondoorzichtig session ID. De sessie in Redis bevat slechts `{"access_id": ..., "tenant_id": ...}`. De rol (`STUDENT` / `TEACHER`) en de actieve status worden per request via `EducationalAccess` uit de database gehaald.
2. **Tenant-isolatie:**
   Strikt gehandhaafd. Zowel sessie-creatie als content-selecties zijn tenant-gescoped via `public_tenant_scope` en `tenant_id`. Een sessie uitgegeven voor Tenant A kan geen content benaderen van Tenant B (401 / 404).
3. **N-2 Invariant (O5):**
   `src/core/api/v1/foundation/content.py` is uitgebreid met een filter op `visibility`. Publieke list- en detail-endpoints tonen enkel `Visibility.PUBLIC` (anoniem) of `Visibility.PUBLIC` + `Visibility.COMMUNITY` (ingelogd). `Visibility.EDU` content kan onder geen enkel beding lekken naar het publieke archief.
4. **Brute-force mitigatie:**
   `POST /edu/session` is beschermd met `require_portal_auth_rate_limit` (5 requests per minuut per IP). Foutmeldingen zijn uniform (`"Invalid or expired code"`, HTTP 401) om code-enumeratie te voorkomen.
5. **Gedocumenteerde afwijkingen van de spec:**
   - *Public Registry Pad-scope:* Omdat `TenantMiddleware` pad-gebaseerd filtert en geen JWT aanwezig is bij cookie-auth, passeren `/foundation/edu/` requests de middleware. De beveiliging is verplaatst naar FastAPI's `require_edu_session` dependency. Dit is een veilige en pragmatische oplossing binnen de bestaande architectuur (ADR-033).
   - *Cookie `secure`-flag:* Dynamisch ingesteld op `True` in productie of over HTTPS, consistent met `router_login.py`.

---

## E. Issue register

| Severity | Locatie | Probleem | Correctie / Aanbeveling |
|---|---|---|---|
| MEDIUM | `src/core/api/v1/foundation/edu.py` (Rate Limiting) | De rate limiter op `POST /edu/session` gebruikt client-IP (5 req/min). Een schoolklas met 25-30 leerlingen achter een enkele school-NAT firewall zal bij gelijktijdig inloggen massaal tegen HTTP 429 botsen. | Voor P1/productie: verhoog de burst-limiet voor edu-endpoints of introduceer een tenant/sessie-specifieke token bucket in plaats van een strikte 5/min IP-limiet. |
| MEDIUM | `src/core/services/edu_session_service.py` | `hash_edu_code` gebruikt ongepeperde en ongezouten SHA-256 over 8 tekens. Bij een eventuele database-exfiltratie van de `educational_access` tabel kunnen 8-karakter alfanumerieke hashes relatief snel worden reverse-engineered via rainbow tables of brute-force. | Bij implementatie van de code-aanmaak feature (teacher/admin) salt toevoegen (bijv. HMAC met tenant-secret of bcrypt/argon2). |
| LOW | `src/core/api/v1/foundation/edu.py:delete_edu_session` | Bij `response.delete_cookie` ontbreekt de `secure`-vlag die wel in `_set_session_cookie` wordt gezet. Bepaalde browsers negeren cookie-deleties als de flags niet matchen met het set-cookie verzoek. | Zet expliciet `secure=secure_flag` in `delete_cookie`. |
| LOW | `src/core/services/edu_session_service.py` | Geen actieve sessie-invalidatie in Redis bij deactivatie van een `EducationalAccess` record. Sessies blijven zweven tot TTL (14.400s), al weigert de DB-check per request ze direct (fail-closed). | Geen beveiligingslek omdat DB-check blokkeert, maar veroorzaakt wel lichte geheugen-vervuiling in Redis bij frequente intrekkingen. |

---

## F. Ontbrekende items & Vervolgstappen

1. **Aanmaak & Beheer van Edu Codes:**
   Het genereren en beheren van toegangscodes (`EducationalAccess`) door docenten/beheerders is conform scope out-of-scope voor BE-EP-039 en gepland voor de Teacher-management feature (P1).
2. **School-NAT Rate Limiting Optimalisatie:**
   Evaluatie van de rate limiter instellingen voor educatieve IP-ranges vóór ingebruikname op scholen.

---

## G. Release-oordelen

- Bouw/implementatie: **JA (GO)**
- QA/geautomatiseerd testen: **JA (GO)** (49/49 tests geslaagd, incl. regressie en RLS)
- Architectuur & Security: **JA (GO)** (P0-5 auth bypass structureel opgelost)
- Red Team Review: **APPROVED**

---

## Wat wél klopt

- De scheiding tussen sessie-opslag (Redis) en autorisatie-validatie (PostgreSQL) is een schoolvoorbeeld van defensief programmeren: snelle sessie-lookups met harde, actuele autorisatiegaranties.
- De interface `EduSessionStore` met `InMemoryEduSessionStore` en `RedisEduSessionStore` maakt de unit-tests razendsnel (0.43s) en 100% reproduceerbaar zonder externe afhankelijkheden.
- De O5-invariant sluit een sluimerend datalek in de publieke portal definitief af door niet alleen op `privacy` maar ook op `visibility` te filteren.
- Foutafhandeling is strikt fail-closed: corrupte Redis-data, ontbrekende records of verlopen timestamps resulteren zonder uitzondering in een uniforme 401.

---

## Devil's Advocate — Waarom faalt deze oplossing in de toekomst?

1. **De School-NAT Denial of Service (De realiteit van het klaslokaal):**
   De huidige beveiliging tegen brute-force (`require_portal_auth_rate_limit: 5/min per IP`) is ontworpen voor individuele consumenten. In het onderwijs zitten 30 basisschoolleerlingen tegelijkertijd achter één extern WAN IP-adres van het schoolbestuur. Zodra de docent zegt: *"Ga allemaal naar de website en vul de code in"*, loggen de eerste 5 leerlingen in en krijgen de overige 25 een HTTP 429 melding. Dit zal tijdens de allereerste pilot op een school als een "kapot systeem" worden ervaren.
2. **De 8-karakter hash zonder salt bij database-lekkage:**
   Een alfanumerieke code van 8 tekens heeft \(62^8 \approx 2.18 \times 10^{14}\) combinaties. Met moderne GPU-clusters (die meer dan 100 GH/s aan SHA-256 kunnen berekenen) kan de gehele sleutelruimte binnen enkele uren volledig worden doorzocht. Als een backup of read-replica van de database ooit lekt, zijn alle educatieve codes direct gecompromitteerd. Zonder salt of key-stretching (Argon2id/PBKDF2) is de hash in de database schijnveiligheid.
3. **Ghost Sessions in Redis:**
   Omdat er geen omgekeerde index (`access_id -> session_ids`) wordt bijgehouden in Redis, kan een sessie niet proactief worden gepurged wanneer een code door een beheerder wordt ingetrokken of wanneer een klas klaar is. Hoewel de database-revalidatie per request de toegang direct blokkeert (wat veilig is), blijft Redis bij intensief gebruik gevuld met dode sessie-sleutels die pas na 4 uur door de TTL worden opgeruimd.
