# Review BE-EP-036: Foundation Portal upload-endpoint + storage-service

STATUS: APPROVED

**Reviewer:** onafhankelijke review-agent (Gate 2, code-reviewer + quality-reviewer ineen). Code niet zelf geschreven; read-only gereviewd. Verificatie met commando's, niet op aannames.
**Datum:** 2026-09-09
**Scope:** working tree (uncommitted) — `src/core/api/v1/foundation/upload.py`, `src/core/services/foundation_storage.py`, wijzigingen in `dependencies.py` / `router.py` / `schemas.py` / `content.py` / `config.py` / `requirements-base.txt` / `ID-REGISTRY.md`, beide testbestanden, spec `docs/backend/features/BE-EP-036-upload-endpoint-storage.md`.

---

## B. Eindoordeel

CHANGES_REQUESTED — twee HIGH-bevindingen blokkeren merge: (1) een leeg bestand (0 bytes) crasht het endpoint met een onbehandelde `puremagic.PureValueError` -> HTTP 500, objectief aangetoond met een eigen adversarial run; (2) de azure-backend slaat een SAS-URL met 7-dagen-expiry permanent op in `content.file_url`, waardoor op de productie-backend elke upload na een week een dode URL heeft zonder regeneratiepad. Beide zijn klein te fixen. De rest van de implementatie is bovengemiddeld zorgvuldig (zie "Wat wel klopt").

## C. Samenvatting

De spec is eerlijk (de 50 MB-afwijking van ADR-029 is bewust gedocumenteerd) en de implementatie dekt de 12-stappen-flow en O1-O10 grotendeels. Verificatie: **24/24 unit-tests groen** (`tests/unit/test_be_ep_036_upload_offline.py`, 0.45s), **8/8 integratietests groen** (`tests/integration/api/v1/foundation/test_upload.py`, 42.7s, tegen echte Postgres 5435 + Redis 6379), **ruff schoon** op alle geraakte bestanden, **import-linter 9 kept / 0 broken** (Contract 1 slaagt; `upload.py` valt als niet-`*.router`-module buiten de glob maar volgt het facade-patroon correct via `dependencies.py`). Eigen adversarial runs: rate limiter engage werkelijk (11e request -> 429), exe-met-`.png`-naam geweigerd, `../../escape.png` lekt niet in het storage-pad, maar **leeg bestand -> onbehandelde exception** en **`text/plain; charset=utf-8` ten onrechte geweigerd**.

De twee HIGH's zijn geen randgevallen: een leeg bestand uploaden is triviaal en het SAS-expiry-probleem raakt structureel de productie-flow (azure is de bedoelde productie-backend; de local-backend is alleen dev/test).

## D. Bevindingen per categorie (samengevat)

1. **Security** — Kern is sterk: magic bytes op inhoud (niet op filename/declared type), object-key volledig server-side (traversal onmogelijk), cap gehandhaafd vóór volledige allocatie (chunked, abort bij cap+1), SAS read-only + tijdsbegrensd, cross-tenant 403 vóór content-lookup, geen `str(e)` in responses, audit-metadata zonder inhoud/PII. Zwaktes: existence-oracle binnen tenant (MEDIUM-2), `text/plain`-fallback met exacte content-type-match (MEDIUM-4), polyglot-restrisico (LOW), filename op DEBUG gelogd (LOW).
2. **Correctheid** — Leeg bestand -> 500 (HIGH-1, aangetoond). SAS-URL met expiry permanent in DB (HIGH-2). Audit vóór commit in dezelfde transactie, afwijkend van spec-stap 11 en patroon #3 (MEDIUM-1). Chunk-teller heeft **geen** off-by-one: exact cap toegestaan, cap+1 -> 413, unit-getest op de chunk-grens. Commit/flush-volgorde is atomair maar spec-afwijkend. Sessie-lifecycle correct (commit in `get_db` na return, geverifieerd in `database.py:503-515`).
3. **Architectuur** — ADR-033-facade nageleefd: `upload.py` importeert services/governance uitsluitend via `dependencies.py`; `__all__` uitgebreid; import-linter groen. `get_foundation_storage`-cache is veilig (settings zijn zelf ook gecached; tests overriden de dependency). Response-schema consistent met module-conventie (`response_model`, geen `{"success": ...}`-wrapper). Azure SDK via `asyncio.to_thread` — event loop blijft vrij; lazy import correct.
4. **Tests** — 24 unit + 8 integratie, betekenisvol (niet alleen happy path: 401/403 cross-tenant/403 niet-eigenaar/404/413/400 allemaal integratie-getest; magic-bytes-vervalsingen unit-getest). Gaten: geen test voor leeg bestand (had HIGH-1 gevangen), geen test dat de rate limiter op `create_content` engage (de N-4-fix is ongetest, MEDIUM-3), geen 503-test op endpoint-niveau, geen end-to-end `text/plain`-test.
5. **Regels** — Geen non-ASCII/emoji in nieuwe code (gescand). `datetime.now(timezone.utc)` overal tz-aware. Geen `str(e)` in HTTP-details of logs (`exc_info=True` gebruikt). `puremagic==2.2.0` exact gepind, `azure-storage-blob>=12.24.0,<13.0` als range — onderling inconsistent, repo kent beide stijlen (LOW).

## E. Issue register

| Severity | Locatie | Probleem | Correctie |
| --- | --- | --- | --- |
| HIGH | `foundation_storage.py:110` + `upload.py:125` | `puremagic.magic_string(b"")` gooit `PureValueError("Input was empty")` bij een leeg bestand. `detect_allowed_mime` vangt dat niet; het endpoint vangt alleen storage-exceptions. Resultaat: HTTP 500 op triviaal triggerbare input. Aangetoond: `detect_allowed_mime(b"", filename="n.txt", declared_content_type="text/plain")` -> unhandled raise. De unit-test `test_empty_file_reads_empty` dekt alleen `_read_capped`, niet de detectie erachter. | Vroeg afbreken: `if not data: return None` (lege upload -> 400), of `PureValueError` vangen in `detect_allowed_mime`. Voeg unit- + integratietest "empty file -> 400" toe. Overweeg meteen minimum-size 1 byte. |
| HIGH | `foundation_storage.py:209-217` + `upload.py:161` | Azure-backend retourneert `{blob_url}?{sas}` met `expiry = now + 7 dagen` en het endpoint slaat die URL permanent op als `content.file_url`. Na 7 dagen is elke opgeslagen URL dood; er is geen regeneratiepad (download/serveer-endpoint is bewust out of scope). Productie draait straks op azure: alle portal-media worden na een week onbereikbaar via de DB-referentie. | Sla de kale blob-URL of alleen de object-key op en genereer de SAS op het moment van serveren (dat hoort dan bij P0-7), of leg expliciet vast dat `file_url` alleen de blob-key bevat en pas het serveer-design hierop aan. Minimaal: spec + code-commentaar + follow-up-ID, want dit is een spec-designfout (O5), niet alleen een code-bug. |
| MEDIUM | `upload.py:164-191` vs `documents/upload_router.py:128-150` | Audit draait **voor** de commit, in dezelfde transactie als de content-update. Spec-stap 11 en backend-patroon #3 schrijven "audit via `best_effort` **na commit**" voor; het referentiepatroon commit 2x expliciet vóór `best_effort`. Gevolg bij een audit-failure die `log_event` wél laat ontsnappen (het vangt `Exception` breed, dus zeldzaam): `best_effort` roept `session.rollback()` aan en rolt de geflushte content-update mee terug — bestand staat al op storage, DB wijst er niet naar, client kreeg 200. Latente inconsistentie + spec-afwijking. | Commit de content-update expliciet (`await session.commit()`) vóór het `best_effort`-blok, zoals `upload_router.py`, of gebruik een aparte sessie voor de audit. Pas spec-stap 10/11 aan op de werkelijke volgorde. |
| MEDIUM | `upload.py:105-119` | Existence-oracle: content-lookup (404) gaat vóór autorisatie (403). Een same-tenant portal-user zonder rechten kan content-IDs enumereren: 403 = bestaat, 404 = bestaat niet — ook voor PENDING content van anderen. IDs zijn sequentiele ints, dus enumeratie is triviaal. Spec schrijft deze volgorde zelf voor (stappen 5-6); het is dus ook een spec-bevinding. | Uniform 404 voor "bestaat niet" en "geen toegang", of autorisatie op rol eerst en uploader-check gecombineerd met de lookup. Minimaal bewust documenteren als geaccepteerd risico. |
| MEDIUM | `content.py:143-157` + tests | De meegepakte N-4-fix (rate limiter op `create_content`) heeft geen enkele test die bewijst dat de limiter engage. De decorator no-opt **stilletjes** als er geen `Request`-parameter is (`shared/rate_limiter.py:109-110`); een toekomstige refactor die `request` verwijdert schakelt limiting ongemerkt uit. Eigen test toonde dat het mechanisme werkt (11e request -> 429), maar niets in de suite bewaakt de koppeling. | Integratietest: 11x POST `/content` vanaf hetzelfde IP -> laatste 429. Idem voor `/upload` (nu indirect gedekt, niet expliciet). |
| MEDIUM | `foundation_storage.py:117-121` | `text/plain`-fallback eist `declared_content_type == "text/plain"` exact. Een client die `text/plain; charset=utf-8` stuurt (gangbaar) krijgt 400 voor een legitimiem tekstbestand — aangetoond met eigen run. | Parse het media-type (`split(";")[0].strip().lower()`) vóór de vergelijking. Voeg test toe met charset-variant. |
| LOW | `shared/rate_limiter.py:76` (pre-existing) | `portal_public_write_limit` gebruikt de **in-memory** limiter: per Gunicorn-worker. Bij N workers is de effectieve limiet ~10xN per IP. Pre-existing patroon, maar voor een upload-endpoint met 50 MB per request betekent dat 500 MB/min/IP bij 10 workers. | Vastleggen als hardening-item (Redis-backed limiter); niet blokkerend voor deze feature, wel benoemen in de spec onder "Open aannames". |
| LOW | `config.py:162` + `upload.py:122` | Endpoint-cap (50 MB) == middleware-cap (50 MB). Multipart-overhead zorgt dat een bestand van ~50 MB al bij `max_body_size_middleware` sterft; de endpoint-cap is aan de bovenkant onbereikbaar. Cosmetisch, maar de gedocumenteerde "50 MB toegestaan" is in de praktijk "iets minder dan 50 MB". | Documenteer, of zet de endpoint-cap enkele KB onder de middleware-cap. |
| LOW | `foundation_storage.py:77-93` | `secure_filename("..")` retourneert `".."`. Nu ongevaarlijk (de gesanitiseerde naam komt nooit in het object-key-pad), maar latent gevaarlijk: `documents/upload_router.py` gebruikt `safe_name` wél in een bestandspad (geprefixt met `doc.id_`, dus daar veilig). Een toekomstige consumer die dit vergeet, erft een traversal-primitief. | Filter ook zuivere punten-reeksen: `if set(safe) <= {"."}: return "unnamed"` (of strip leading dots). |
| LOW | `foundation_storage.py:159-164` | Client-controlled filename (kan een persoonsnaam bevatten) wordt op DEBUG gelogd. Geen lek op INFO+, maar wel PII in logs zodra DEBUG aan staat. | Log alleen lengte/hash van de naam, of laat `name=` weg (de naam heeft geen functie in de key). |
| LOW | tests | Geen test voor: 503-pad (backend niet geconfigureerd) op endpoint-niveau; end-to-end `text/plain`; her-upload over bestaande `file_url` (oud object blijft als orphan op azure staan — storage-leak). | Minimaal de 503-test; de rest als opvolgpunten. |
| LOW | `requirements-base.txt:91-92` | `puremagic==2.2.0` exact gepind, `azure-storage-blob>=12.24.0,<13.0` als range — twee stijlen naast elkaar in hetzelfde blok. | Een stijl kiezen (repo gebruikt overwegend ranges met bovengrens). |

## F. Ontbrekende items

- Test "leeg bestand -> 400" (had HIGH-1 gevangen vóór review).
- Test dat de rate limiter op `create_content` engage (N-4 is nu een onbewezen fix).
- Regeneratie- of serveer-strategie voor verlopen SAS-URL's (hangt samen met P0-7; moet als expliciet follow-up-ID in de registry, niet alleen in "Open aannames").
- Opname van de in-memory-limiter-caveat in de spec (nu nergens benoemd).
- Endpoint-niveau 503-test en text/plain end-to-end test.

## G. Verbeterde codevoorstellen

`foundation_storage.py`:

```python
def detect_allowed_mime(data, *, filename, declared_content_type):
    if not data:
        return None  # empty upload: no magic bytes, no fallback -> 400
    matches = puremagic.magic_string(data)
    ...
    declared = (declared_content_type or "").split(";")[0].strip().lower()
    if filename is not None and filename.lower().endswith(".txt") and declared == "text/plain":
        ...
```

`upload.py` (audit na commit, conform patroon #3):

```python
session.add(content)
await session.flush()
await session.commit()  # patroon #3: audit pas nadat de wijziging duurzaam is

async with best_effort("foundation content file upload audit", db_session=session):
    ...
```

Spec (nieuwe open aanname + follow-up): "`file_url` bevat op de azure-backend een SAS-URL met 7-dagen-expiry; regeneratie/servering is onderdeel van P0-7-design (follow-up-ID aanmaken). Rate limiting is in-memory per worker; Redis-backed limiter is P1-hardening."

## H. Release-oordelen

- Bouw/implementatie: **nee** (HIGH-1: 500 op leeg bestand; HIGH-2: dode file_url's op productie-backend na 7 dagen).
- QA/geautomatiseerd testen: **deels** (sterke basis, maar de N-4-fix en het empty-pad ongetest).
- LLM-training: **pas na fix**.
- Integratorhandleiding / spec: **ja, na correctie** van stap 11 (audit-volgorde) en toevoeging SAS-caveat.

## Wat wél klopt

- MIME-validatie op echte inhoud: exe met `.png`-naam geweigerd (unit + integratie), PNG/JPEG/PDF/MP4-magic gedetecteerd, onbekende binaries zonder fallback geweigerd.
- Path traversal onmogelijk: object-key is volledig server-side (`foundation/<int>/<int>/<uuid4><mime-ext>`); unit-test bewijst dat `../../escape.png` nergens in URL of pad terugkomt; `tenant_id`/`content_id` zijn ints.
- Size-guard: chunked (1 MiB), abort bij cap+1, exact cap toegestaan (unit-getest op de chunk-grens, geen off-by-one); middleware-cap consistent gekozen en afwijking van ADR-029 (50 vs 100 MB) eerlijk gedocumenteerd.
- Rate limiter engage werkelijk (eigen run: 10x ok, daarna 429); `Request`-parameter aanwezig op beide endpoints; decorator-volgorde correct (`@router.post` boven `@portal_public_write_limit`).
- Autorisatie-volgorde cross-tenant correct: tenant-mismatch 403 vóór content-lookup; unauthenticated 401; 8 integratietests groen tegen echte Postgres/Redis.
- Audit-metadata bevat alleen sha256/mime/size/content_id — geen bestandsinhoud, geen PII; HTTP-details zonder `str(e)`; exceptions met `exc_info=True`.
- ADR-033-facade correct: `upload.py` importeert storage/rate-limiter/audit via `dependencies.py`; `__all__` bijgewerkt; import-linter 9 kept / 0 broken.
- Ruff schoon op alle geraakte bestanden; geen non-ASCII/emoji in nieuwe code (gescand); `datetime.now(timezone.utc)` overal tz-aware; azure SDK synchroon werk via `asyncio.to_thread`; lazy azure-import.
- Spec is ongewoon eerlijk over eigen zwaktes (text/plain-fallback, account-key SAS, 50 MB-afwijking) — dat maakte deze review sneller, maar maskeert HIGH-2 niet.

## Devil's Advocate — waarom faalt deze oplossing in de toekomst?

1. **SAS-expiry is een tijdbom in de database.** Over drie maanden gaat P0-7 (frontend) live. Elk eerder geüpload bestand heeft dan een dode `file_url`. Dat presenteert als "data weg" — supporttickets, paniek, en een haastige migratie waarin iemand de SAS "even" op 10 jaar zet of de container publiek maakt. De P1-hardening (user-delegation SAS) is vastgelegd maar heeft geen eigenaar of datum; uitgestelde security-work verdwijnt structureel.
2. **In-memory rate limiting verdampt bij schaal.** De eerste keer dat er meer Gunicorn-workers bijkomen (of een herstart-golf), verviervoudigt de effectieve upload-limiet stilletjes. Niemand merkt het tot een abuse-incident; de limiter is niet gedekt door een test die het gedrag in productie-topologie bewaakt.
3. **De audit-in-transactie-afwijking wordt het nieuwe patroon.** Deze code wordt het copy-paste-voorbeeld voor de volgende drie upload-achtige endpoints. Zodra een toekomstige audit-aanroep iets doet dat `log_event` niet intern vangt, rolt `best_effort` de primaire wijziging mee terug: het bestand staat op storage, de DB niet, en de client heeft een 200 met een `file_url` die nergens heen wijst. Dat is een stille integriteitsbreuk die pas bij een audit-reconciliatie opvalt.
4. **Magic bytes zijn een header-check, geen inhoudsanalyse.** De eerste polyglot (geldige PNG-header + appended script — vandaag aangetoond dat die passeert) plus een toekomstig serveer-endpoint met een verkeerde `Content-Disposition` of een te breed `Content-Type` is stored XSS op het portal. Virusscanning staat in "Out of scope", niet in een backlog met datum.
5. **De `text/plain`-fallback is de toekomstige achterdeur.** Zodra een legitieme client met `charset` wordt afgewezen (vandaag reproduceerbaar), is de verleiding groot de declaratie-check te "fixen" door hem weg te halen in plaats van te parsen. Op dat moment accepteert het endpoint elke UTF-8-binaire met een `.txt`-naam — inclusief gemaskeerde scripts — zonder dat een test rood wordt, want die test bestaat niet.

Deze punten zijn grotendeels met kleine correcties af te dekken (zie E en G); de structuur eronder (facade, tenant-isolatie, chunked guard) is degelijk.

---

## Addendum — Herreview 2026-09-09 (ronde 2, onafhankelijk, met commando's geverifieerd)

HERREVIEW-OORDEEL: **APPROVED**.

Verificatie gedraaid: **27/27 unit-tests groen** (0.46s), **35/35 integratietests groen** (`test_upload.py` + `test_content.py`, 155.5s, echte Postgres 5435 + Redis 6379) — exact zoals de schrijver claimde — en **ruff schoon** op alle geraakte bestanden. Elke fix-claim is bovendien in de code zelf geverifieerd, niet alleen via testnamen.

Per bevinding:

1. **HIGH-1 (leeg bestand -> 500) — OPGELOST.** `detect_allowed_mime` breekt nu vroeg af (`if not data: return None`, `foundation_storage.py:107-110`); `upload.py:134-138` vertaalt dat naar 400. Unit-test `test_empty_input_rejected` + integratietest `test_upload_empty_file_rejected` aanwezig en groen. Eigen adversarial run: `detect_allowed_mime(b"", ...)` retourneert nu `None` (voorheen unhandled `PureValueError`).
2. **HIGH-2 (SAS-expiry in file_url) — OPGELOST.** `_upload_azure` retourneert nu `blob_client.url` zonder token (`foundation_storage.py:210-213`); `generate_blob_sas`/`BlobSasPermissions` zijn volledig uit de service verdwenen (grep: geen restanten). Unit-test `test_upload_returns_canonical_url` assert expliciet `"sig=" not in url`. Spec O5, flow-stap 9 en "Open aannames" zijn consistent bijgewerkt, inclusief de eerlijke caveat dat `file_url` tot het serveer-endpoint (P1/P0-7) niet direct downloadbaar is. Dat is een betere foutpositie dan een stille tijdbom: het faalt zichtbaar en bij ontwerp, niet na 7 dagen in productie.
3. **MEDIUM-1 (audit voor commit) — OPGELOST in code, met kanttekening.** `upload.py:178` commit nu expliciet vóór het `best_effort`-blok, met `content_pk` vooraf gecaptureerd (post-commit expiry correct afgedekt). Een audit-failure kan de gecommitte update niet meer raken — de rollback in `best_effort` treft hooguit de nieuwe, lege transactie. **Kanttekening (LOW, nieuw):** `test_upload_audit_failure_still_succeeds` is een valse sentinel — hij assert alleen 200 + bestand op disk, niet dat `content.file_url` in de DB gepersisteerd is. De oude, buggy code (zonder commit) zou deze test ook hebben gehaald. De fix is daarom op code-niveau geverifieerd, niet op test-niveau. Correctie (niet blokkerend): laat de test na de response de content herladen en `file_url` asserten.
4. **MEDIUM-2 (existence-oracle) — OPGELOST.** Niet-eigenaar/niet-curator krijgt nu dezelfde 404 als niet-bestaande content (`upload.py:111-123`). `test_upload_not_found_and_unauthorized_are_identical` vergelijkt de volledige error-envelope minus timestamp en is groen. Beide paden doorlopen identieke auth- en query-stappen vóór de raise; het resterende timing-verschil is verwaarloosbaar. De 403 blijft correct voor cross-tenant (aparte, eerdere check — dat lekt niets over content-IDs).
5. **MEDIUM-3 (N-4 ongetest) — OPGELOST.** `test_create_content_11th_request_gets_429` in `test_content.py` doet 10x 201 + 11e -> 429 vanaf hetzelfde IP; groen gedraaid. Dit bewaakt nu ook de stille no-op-modus van de decorator (geen `Request`-param = geen limiting).
6. **MEDIUM-4 (charset exact-match) — OPGELOST.** Declared type wordt genormaliseerd (`split(";")[0].strip().lower()`, `foundation_storage.py:119`). Eigen adversarial runs: `TEXT/PLAIN;charset=UTF-8` (geen spatie, hoofdletters) -> geaccepteerd; `text/plain;charset=iso-8859-1` -> geaccepteerd. Unit-test `test_declared_type_with_charset_accepted` + end-to-end `test_upload_text_plain_end_to_end` groen.

**Nog open (allen LOW, geen blokkers; bewust niet mee-eist in ronde 1):** in-memory rate limiter per worker (hardening-item); endpoint-cap == middleware-cap; `secure_filename("..") == ".."` (latent); filename op DEBUG gelogd; geen 503-test op endpoint-niveau; pin-stijl `puremagic==2.2.0` vs range. Plus nieuw: de valse-sentinel-audit-test hierboven. Aanbeveling: deze als opvolgpunten in de sprint-tracker opnemen.

**Devil's Advocate — geactualiseerd.** Punten 1, 3 en 5 uit ronde 1 zijn weggepoetst: de SAS-tijdbom is weg (canonieke URL), de audit-volgorde is conform patroon #3, en de charset-val is gedicht mét test. Wat blijft: (2) de in-memory limiter verdampt nog steeds stilletjes bij multi-worker-schaling — nu wél bewaakt per endpoint, niet per topologie; (4) polyglot-restrisico blijft inherent aan header-sniffing en wordt pas reëel zodra het serveer-endpoint (P1) een `Content-Disposition`/`Content-Type` moet kiezen — dat endpoint moet de gedetecteerde MIME uit de DB gebruiken en nooit sniffing toestaan, en dit moet in diens spec als acceptatiecriterium. Nieuw risico: de canonieke blob-URL vereist een private container; als het serveer-endpoint uitblijft of de container ooit publiek wordt gezet "om snel te kunnen tonen", is er geen enkele toegangscontrole meer op portal-media — leg dit vast als harde eis in de P1-serveer-spec.

Release-oordelen bijgewerkt: bouw/implementatie **ja**; QA **ja** (met de valse-sentinel-test als bekende zwakte); LLM-training **ja**; spec/integratorhandleiding **ja**.
