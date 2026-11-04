# Review BE-EP-037: Foundation Portal map/geo-endpoint (bbox)

STATUS: APPROVED

**Reviewer:** onafhankelijke review-agent (Gate 2, code-reviewer + quality-reviewer ineen). Code niet zelf geschreven; read-only gereviewd op branch `iter/p0-4-map-endpoint` (uncommitted working tree). Verificatie met commando's en eigen adversarial probes, niet op aannames.
**Datum:** 2026-09-09
**Scope:** `src/core/api/v1/foundation/map.py` (nieuw), `router.py`, `src/core/shared/public_registry.py`, beide testbestanden, spec `docs/backend/features/BE-EP-037-map-bbox-endpoint.md`, `ID-REGISTRY.md`.

---

## B. Eindoordeel

CHANGES_REQUESTED — één HIGH: het publieke, niet-geauthenticeerde map-endpoint lekt `creator_name` ook voor content waar de uploader expliciet `is_anonymous=True` heeft gezet. Empirisch bewezen met een eigen probe (APPROVED+PUBLIC content met `is_anonymous=True` en `creator_name="Geheime Persoon"` verschijnt met die naam in de bbox-response). De rest van de implementatie is sterk: span-cap, NaN/inf-weerstand, tenant-isolatie en admin-afscherming zijn allemaal objectief geverifieerd. De fix is klein (één conditie in `content_to_feature` + test).

## C. Samenvatting

Verificatie: **16/16 unit-tests groen** (1.08s), **10/10 integratietests groen** (57.2s, echte Postgres 5435 + Redis 6379), **ruff schoon** op alle geraakte bestanden, geen non-ASCII in nieuwe code, geen `str(e)`. Eigen adversarial probes (tijdelijk pytest-bestand, daarna verwijderd): (a) `sw_lat=nan`, `ne_lat=inf`, `-inf..inf`, `1e999` → allemaal 400/422, geen 500, geen data; (b) `/default/foundation/admin/curatie` zonder auth → 401/403/404, de nieuwe registry-entry opent admin dus NIET; (c) anonimiteits-probe → lek bevestigd (HIGH-1). Registry-matcher verder getest: `/foundation/mapbbox` (substring, geen route) wordt ook "public" — latent risico (MEDIUM-1).

De spec is van goede kwaliteit (O1-O9 met redenen, eerlijke open aannames) maar noemt `public_registry.py` niet onder "Gewijzigd" en spec-stap 2 zegt 400 waar out-of-range in werkelijkheid 422 geeft (door de schrijver zelf gemeld, maar niet in de spec verwerkt). De `is_anonymous`-dimensie ontbreekt volledig in de spec — dat is de bron van HIGH-1.

## D. Bevindingen per categorie (samengevat)

1. **Scrape-oppervlak** — Span-cap 2.0° is echt afgedwongen op BEIDE assen, op de echte request, met 2.0-exact toegestaan (unit) en daarboven 400 (integratie). NaN/inf/1e999 worden afgewezen (FastAPI-parsing + `validate_bbox` als tweede verdediging; eigen probe). Restbypass: vele kleine bboxen onder de 60/min/IP-limiter — de in-memory limiter (per Gunicorn-worker) is de enige rem op totale dump-volume (LOW, bekend patroon uit BE-EP-036-review).
2. **Privacy** — Filter-volgorde en NULL-gedrag correct: COMMUNITY, PENDING, REJECTED en content zonder lat/lng komen niet mee (6 exclusion-cases integratie-getest). MAAR: `creator_name` wordt onvoorwaardelijk meegestuurd, ook bij `is_anonymous=True` (HIGH-1). Verder geen extra velden: de integratietest assert de volledige properties-dict op gelijkheid — geen `file_url`, `body`, `uploader_id` of `email`.
3. **Tenant-isolatie** — Expliciete `tenant_id`-WHERE bovenop `public_tenant_scope`; cross-tenant-content komt niet mee (integratie-getest). Registry-entry opent admin niet (probe). Matcher is echter substring-gebaseerd (MEDIUM-1).
4. **Correctheid GeoJSON** — `[lng, lat]`-volgorde correct en integratie-getest; `type: FeatureCollection/Feature/Point` correct; `total` = aantal features in de response (O3-semantiek; bij de cap kan de frontend "precies 500" niet van "meer dan 500" onderscheiden — LOW).
5. **Regels** — Facade-patroon nageleefd (imports via `dependencies.py`), rate limiter heeft `Request`-parameter en correcte decorator-volgorde, geen non-ASCII, geen `str(e)`, geen audit-log voor publieke read (O9 consistent met patroon #3 dat audit voor mutaties geldt).

## E. Issue register

| Severity | Locatie | Probleem | Correctie |
| --- | --- | --- | --- |
| HIGH | `map.py:75` (`content_to_feature`) | `creator_name` wordt onvoorwaardelijk meegestuurd, ook als `content.is_anonymous=True`. Empirisch bewezen: probe met `is_anonymous=True` + `creator_name="Geheime Persoon"` retourneert die naam op het publieke, niet-geauthenticeerde endpoint. Het model-veld `is_anonymous` (`foundation_content.py:137`, default False, door uploader zetbaar via create) wordt nergens in serialisatie gehonoreerd — ook niet in content list/detail (pre-existing), maar dit endpoint is bulk-scrapebaar zonder login. Spec O8 noemt `creator_name` als bedoeld-publiek zonder `is_anonymous` te noemen. | In `content_to_feature`: `creator_name=None if content.is_anonymous else content.creator_name`. Integratietest toevoegen (anonieme content → naam afwezig). Leg vast dat detail/list hetzelfde lek hebben als opvolg-ID (aparte fix, breder dan deze feature). Spec O8 aanvullen met de anonimiteitsregel. |
| MEDIUM | `public_registry.py:90-92` | Substring-match `"/foundation/map" in path`: elk toekomstig pad met die substring (bijv. `/foundation/mapbox-config`, `/foundation/map/admin-kaart` zonder letterlijke "/admin/") wordt stilletjes publiek. Bewezen: `/default/foundation/mapbbox` → `is_public=True`. De admin-bescherming hangt aan de "/admin/"-substring-guard, niet aan route-niveau-auth. Pre-existing patroon (`/foundation/content` maakt zelfs het upload-pad registry-public — endpoint-auth vangt dat op, maar QuotaMiddleware wordt ook overgeslagen), deze entry verbreedt het. | Match exact op pad-segmenten (bijv. `path.split("/")[3] == "map"`) of documenteer + test dat alleen `/map/bbox` bedoeld is. Minimaal een registry-unit-test die `/foundation/admin/...` en lookalikes uitsluit. Niet blokkerend: admin-guard werkt vandaag (probe). |
| LOW | `map.py:131-134` | `total == len(features)`: bij de 500-cap kan de frontend niet zien dat er méér matches waren; O3 claimt dat `total` de frontend "kan waarschuwen bij de cap" maar het signaal is "waarschijnlijk meer", niet zeker. | Documenteer als bewust ("total >= aantal getoond"), of voeg `capped: true` toe via een `LIMIT 501`-truc. |
| LOW | Spec vs `map.py:89-92` | Spec-flow stap 2 impliceert 400 voor validatie; out-of-range coördinaten geven 422 via `Query(ge=, le=)` (schrijver meldde dit zelf, maar de spec is niet bijgewerkt). | Spec-stap aanpassen: "out-of-range → 422 (FastAPI Query-validatie), ordering/span → 400". |
| LOW | Spec "Build summary" | `src/core/shared/public_registry.py` ontbreekt onder "Gewijzigd", terwijl het een auth-relevante wijziging is (anonieme toegang). | Toevoegen aan de spec; dit is precies het soort wijziging dat in een inventory thuishoort. |
| LOW | Architectuur (pre-existing, herbevestigd) | Anti-scrape is per-call begrensd maar niet in totaalvolume: 60/min/IP in-memory per worker. Een geduldige scraper met N IP's dumpt alles. | Vastleggen als hardening-item (dagcap of Redis-limiter); consistent met dezelfde LOW uit review-BE-EP-036. |

## F. Ontbrekende items

- Test voor `is_anonymous=True` op het map-endpoint (had HIGH-1 gevangen).
- Unit-test voor de registry-matcher (admin-uitsluiting + substring-lookalikes).
- NaN/inf-test in de eigen testsuite (nu alleen als review-probe bewezen).
- Opvolg-ID voor het platform-brede `is_anonymous`-lek in content list/detail.
- Spec-updates: 422-vermelding, public_registry in de inventory, anonimiteitsregel in O8.

## G. Verbeterde codevoorstellen

`map.py`:

```python
"properties": {
    "id": content.id,
    "title_nl": content.title_nl,
    "type": content.type.value,
    # Respecteer de anonimiteitsvoorkeur van de uploader (Gate-2 HIGH-1).
    "creator_name": None if content.is_anonymous else content.creator_name,
    "category": content.category,
},
```

Spec O8, toevoegen: "`creator_name` is publiek TENZIJ `is_anonymous=True`; dan wordt `null` gestuurd. Dezelfde regel geldt (opvolg-ID) voor content list/detail."

## H. Release-oordelen

- Bouw/implementatie: **nee** (HIGH-1: privacy-lek op publiek endpoint).
- QA/geautomatiseerd testen: **deels** (sterke basis; anonimiteit en registry-matcher ongetest).
- LLM-training: **pas na fix**.
- Integratorhandleiding / spec: **ja, na correctie** van O8, de 422-vermelding en de inventory.

## Wat wél klopt

- Span-cap 2.0° echt afgedwongen op beide assen op de echte request; 2.0 exact toegestaan, erboven 400; NaN/inf/1e999 afgewezen zonder 500 (4 eigen probes).
- Fail-safe privacy-filters: COMMUNITY/PENDING/REJECTED/NULL-geo uitgesloten, met 6 exclusion-cases integratie-getest; lege bbox → lege FeatureCollection.
- Tenant-isolatie dubbel (expliciete WHERE + scope) en cross-tenant integratie-getest; admin-paden NIET anoniem (eigen probe: 401/403/404).
- GeoJSON correct: [lng, lat]-volgorde, types, en properties exact de O8-set — de test assert de volledige dict, dus extra velden hadden rood gegeven.
- Resultaat-cap getest met 501 seeded items → exact 500.
- Rate limiter met `Request`-param en correcte decorator-volgorde; geen audit-log voor publieke read (consistent).
- 16 unit + 10 integratie groen; ruff schoon; geen non-ASCII; geen `str(e)`; antimeridiaan expliciet afgewezen met duidelijke melding.
- Schrijver heeft zijn afwijkingen (registry-toevoeging, 422, `str | None`-signatuur) zelf proactief gemeld — dat versnelde de review.

## Devil's Advocate — waarom faalt deze oplossing in de toekomst?

1. **`is_anonymous` is een dode kolom.** Ook als HIGH-1 in `map.py` wordt gefixt, lekken content list en detail de naam van anonieme uploaders vrolijk verder. De echte fix hoort in de serialisatie-laag (of een model-validator); zolang die er niet is, herhaalt elke nieuwe endpoint deze fout. De fix moet dus niet alleen in `map.py` landen maar een platform-regel worden — anders is dit over twee endpoints weer terug.
2. **De substring-registry is een landmijn.** De eerste toekomstige `/foundation/map*`- of `/foundation/content*`-variant die auth nodig heeft, is stilletjes publiek. Niemand merkt het tot een pentest of een incident, want de endpoint-auth moet het dan alleen opvangen — en vergeten auth op een "registry-publiek" pad is de klassieke cascade.
3. **De anti-scrape-rem is schijnzekerheid.** 2° × 500 × 60/min × N workers × M IP's — een geduldige scraper dumpt de volledige publieke dataset. Voor een monumentenportaal met gevoelige erfgoeddata (Ketikoti-context) is "traag scrapen" geen bescherming; het is alleen een kostenverhoger. Als scrape-bescherming er echt toe doet, hoort er een volumecap of algemene afsprakenlaag bij — nu staat die nergens, ook niet als opvolgpunt.
4. **`total` traint de frontend op een vals signaal.** Bij de eerste tenant met >500 punten binnen 2° toont de kaart "500" alsof dat de werkelijkheid is. Silent data loss in de UI, en de NFR-claim (<150 ms p95) is nergens gemeten — de bereikscan zonder ruimtelijke index is een aannname die bij de eerste grote tenant omvalt.

Deze punten zijn klein te fixen of vast te leggen; de structuur eronder (fail-safe filters, dubbele tenant-isolatie, zuivere validatie) is degelijk.

---

## Addendum — Herreview 2026-09-09 (ronde 2, onafhankelijk, met commando's geverifieerd)

HERREVIEW-OORDEEL: **APPROVED**.

Verificatie gedraaid: **17/17 unit-tests groen** (1.22s), **12/12 integratietests groen** (66.5s, echte Postgres 5435 + Redis 6379) — exact zoals geclaimd — en **ruff schoon** op de geraakte bestanden. Elke claim is daarnaast in de code zelf geverifieerd, niet op testnamen vertrouwd.

Per bevinding:

1. **HIGH-1 (is_anonymous lekt creator_name) — OPGELOST.** `content_to_feature` maskeert nu (`map.py:78`: `None if content.is_anonymous else content.creator_name`). De integratietest is echt end-to-end: hij zet de vlag + naam vóór `add`/`flush` en assert `creator_name is None` in de HTTP-response (geen stale-object-artifact). Eigen adversarial probes op de functie: `creator_name=None + is_anonymous=False` → `None` (geen crash), `"Naam" + is_anonymous=True` → `None`, lege string + False → ongemoeid. Geen omzeiling gevonden. Spec O8 is bijgewerkt met de anonimiteitsregel én benoemt expliciet dat list/detail het lek nog hebben als apart opvolg-item — de bewuste scope-afbakening van de schrijver is daarmee gedocumenteerd in plaats van stil.
2. **LOW (total-semantiek) — OPGELOST.** `LIMIT 501` + `has_more: bool` in de response (`map.py:128-142`). Cap-test dekt 501→500+`has_more=true`; below-cap-test dekt `has_more=false`. De door mij gevraagde boundary was niet gedekt: eigen probe met **exact 500** matches in de DB → `total=500, has_more=False` — correct. Spec O3 en flow-stappen 4-5 zijn consistent bijgewerkt.
3. **content.py-lek (list/detail/CuratieQueueItem) — BEVESTIGD, BEWUST NIET GEFIXT, ACCEPTABEL als opvolg-item.** Zelf geverifieerd via code-lezing: `FoundationContentDetail` en `FoundationContentListItem` bevatten `creator_name` zonder masking; `CuratieQueueItem` idem (daar is het minder erg: curator-only). Dit mag niet verdwijnen: het MOET als opvolg-ID in de sprint-tracker/registry landen, want het is een platform-regel, geen endpoint-fix.

**Nog open (bewust, geen blokkers):**
- MEDIUM-1 (substring-matching `public_registry`): niet aangepakt deze ronde; de admin-guard werkt vandaag (probe in ronde 1), maar de landmijn blijft liggen. Aanbeveling: opvolg-item met registry-unit-test.
- LOW: spec documenteert de 422-bij-out-of-range nog steeds niet (flow-stap 2 noemt alleen ge/le-validatie, geen statuscode).
- LOW: `public_registry.py` ontbreekt nog steeds in de spec-inventory onder "Gewijzigd" — opvallend juist omdat het een auth-relevante wijziging is.
- LOW: totale scrape-volume heeft alleen de in-memory per-worker limiter als rem (consistent met BE-EP-036-review).

**Devil's Advocate — geactualiseerd.** Punt 1 uit ronde 1 (dode `is_anonymous`-kolom op DIT endpoint) is weg: de masking zit erin, is getest, en de spec codificeert de regel. Wat blijft: (2) de substring-registry-landmijn — ongemoeid, eerste toekomstige `/foundation/map*`-variant met auth is stilletjes publiek; (3) anti-scrape als kostenverhoger, geen bescherming; (4) het platform-lek in list/detail leeft voort tot het opvolg-item is gedaan — als dat item verzandt, is de net gewonnen consistentie op de kaart weer weg via twee andere publieke endpoints. Nieuw: `has_more` lost de cap-ambiguiteit op, maar introduceert een silent-contract met de frontend — als het prototype `has_more` niet consumeert, blijft de kaart bij >500 punten alsnog "compleet" liegen; verifieer dit bij de P0-7/frontend-aansluiting.

Release-oordelen bijgewerkt: bouw/implementatie **ja**; QA **ja**; LLM-training **ja**; spec **ja, na** opname van de 422-vermelding en de registry-entry in de inventory (beide LOW, mogen meeliften met het opvolg-item).
