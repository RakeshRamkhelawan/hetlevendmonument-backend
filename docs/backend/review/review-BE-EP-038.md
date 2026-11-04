# Review BE-EP-038: is_anonymous platform-breed honoreren (privacy-fix)

STATUS: APPROVED

**Reviewer:** onafhankelijke review-agent (Gate 2, code-reviewer + quality-reviewer ineen). Code niet zelf geschreven; read-only gereviewd op branch `iter/be-ep-038-anonymous-masking` (uncommitted working tree). Verificatie met commando's en eigen adversarial probes.
**Datum:** 2026-09-09
**Scope:** `src/core/api/v1/foundation/schemas.py` (helper + 2 validators), `map.py` (hergebruik helper), beide nieuwe testbestanden, spec `docs/backend/features/BE-EP-038-anonymous-masking.md`, `ID-REGISTRY.md`.
**Aanleiding:** HIGH-1 uit review-BE-EP-037 (creator_name lekte bij `is_anonymous=True` via publieke list/detail).

---

## B. Eindoordeel

APPROVED — de maskeringsregel leeft nu op precies een plek (`apply_anonymity_mask`), werkt op alle drie de publieke paden (list via `model_validate`, detail via `response_model`, map via gedeelde helper — alle drie objectief bewezen), de bewuste curatie-uitzondering (O4) is gedekt met een test, en het regressie-oppervlak is groen (test_content 23/23, test_map 12/12, test_curatie 18/18). Resterende bevindingen zijn MEDIUM/LOW en horen bij opvolg-items, niet bij deze feature.

## C. Samenvatting

Dit is een kleine, chirurgische privacy-fix (29 insertions, 2 deletions) die precies doet wat de spec zegt. Verificatie: **9/9 unit-tests groen** (0.93s), **5/5 integratietests groen** (46.6s, echte Postgres 5435 + Redis 6379), **ruff schoon**, geen non-ASCII. Eigen probes (tijdelijk testbestand, daarna verwijderd): (a) admin approve-response maskeert nu ook — de door de schrijver gemelde gedragswijziging op het admin-pad is echt en werkt via het `response_model`-pad; (b) `metadata_` (vrije uploader-JSONB) wordt publiek geserveerd en kan de naam alsnog bevatten — bewezen met `{"gemaakt_door": "Verborgen Maker"}` in de detail-response terwijl `creator_name` correct `null` was. Dat is de grens van deze fix (MEDIUM-1). Een flip-aanval (achteraf `is_anonymous` wijzigen) is onmogelijk: er bestaat geen update-endpoint voor content (gegrepd: geen PUT/PATCH/DELETE op content).

## D. Bevindingen per categorie (samengevat)

1. **Dekking van de publieke paden** — Alle drie bewezen: list (integratie: anoniem → null, niet-anoniem → naam behouden), detail (idem + eigen probe), map (helper gedeeld, test_map 12/12 groen). De `response_model`-route op detail is hiermee empirisch bewezen, niet alleen beredeneerd.
2. **Omzeiling** — Geen API-pad om `is_anonymous` achteraf te flippen (geen update-endpoints). Resterend lekkanaal is uploader-vrijheid: naam in `title_nl`, `body` of `metadata_` (MEDIUM-1, bewezen voor metadata). De maskering belooft "anoniem" maar bewaakt alleen het naamveld.
3. **O4 (curatie ziet naam)** — Echt zo geimplementeerd (`CuratieQueueItem` zonder validator) én gedekt: `test_curator_sees_real_name_of_anonymous_content` assert de echte naam in de queue. Correct afgebakend: curator is een vertrouwde rol met auth.
4. **DA-punt van de schrijver (Pydantic-laag, geen contract-test)** — Zie E MEDIUM-2: mijn oordeel is dat een lichte contract-test gerechtvaardigd maar niet blokkerend is.
5. **Regels** — Non-ASCII: geen. `str(e)`: n.v.t. (geen nieuwe exception-paden). Chirurgisch: ja (29 insertions). Regressie: volledig foundation-oppervlak groen (23+12+18+5).

## E. Issue register

| Severity | Locatie | Probleem | Correctie |
| --- | --- | --- | --- |
| MEDIUM | `FoundationContentDetail.metadata_` (pre-existing, door deze fix zichtbaarder) | De maskering dekt alleen `creator_name`, maar publiek detail serveert de vrije uploader-JSONB `metadata_` én vrije tekstvelden (`title_nl`, `body_nl`) verbatim. Bewezen: anonieme content met `metadata_={"gemaakt_door": "Verborgen Maker"}` toont die naam publiek terwijl `creator_name` null is. De anonimiteits-checkbox wekt daarmee een vals veiligheidsgevoel. Pre-existing gedrag, niet door deze feature geintroduceerd. | Beslis als opvolg-item: `metadata_` niet (of gefilterd) serveren op publieke detail, of expliciet documenteren bij de upload-UI dat anonimiteit alleen het naamveld dekt. Minimaal: vastleggen in de portal-spec (P0-7) zodat de frontend geen valse "Anoniem"-belofte toont. |
| MEDIUM | module-niveau (DA-punt schrijver) | De regel leeft op de Pydantic/helper-laag. Een toekomstige serializer die `creator_name` bevat en de helper/validator vergeet (nieuw schema, raw dict, raw SQL) lekt stilletjes. Dit patroon is in dit project al twee keer misgegaan (list/detail vóór BE-EP-037/038), dus "review vangt het wel" is empirisch onhoudbaar. | Lichte contract-test als opvolg-item: iterateer over de publieke foundation-schemas; elke schema-klasse met een `creator_name`-veld MOET de maskeringsvalidator hebben (of de helper aanroepen). ~20 regels, voorkomt de derde herhaling. Niet blokkerend: alle huidige paden zijn bewezen gedekt. |
| LOW | spec "Build summary > Gewijzigd" | `map.py` is gewijzigd (hergebruikt nu de helper) maar ontbreekt in de spec-inventory — derde feature op rij met dit patroon (ook BE-EP-037). | Toevoegen. Overweeg de inventory-check onderdeel van de DoD-checklist te maken. |
| LOW | platform (out of scope, benoemd) | `is_anonymous` kan na aanmaak niet meer worden gewijzigd (geen update-endpoint, P1-2): een uploader die zich bedenkt kan de naam niet alsnog afschermen. | Vastleggen als acceptatiecriterium bij het toekomstige update-endpoint. |

## F. Ontbrekende items

- Contract-test "elk publiek schema met creator_name maskeert" (MEDIUM-2).
- Beslissing over publieke blootstelling van `metadata_` (MEDIUM-1).
- Spec-inventory: `map.py` toevoegen.
- Opvolg-criterium: flipbaarheid van `is_anonymous` bij het toekomstige content-update-endpoint.

## G. Verbeterde codevoorstellen

Contract-test (opvolg-item), schets:

```python
def test_all_public_schemas_with_creator_name_mask_it() -> None:
    from src.core.api.v1.foundation import schemas
    for name in ("FoundationContentListItem", "FoundationContentDetail"):
        cls = getattr(schemas, name)
        obj = cls.model_validate(_stub(is_anonymous=True, creator_name="X"))
        assert obj.creator_name is None
```

(Al beter: over de schema-registry itereren in plaats van namen hardcoden, zodat toekomstige schemas automatisch meegenomen worden.)

## H. Release-oordelen

- Bouw/implementatie: **ja**.
- QA/geautomatiseerd testen: **ja** (9 unit + 5 integratie nieuw, regressie 53 tests groen).
- LLM-training: **ja**.
- Integratorhandleiding / spec: **ja, na** toevoegen van `map.py` aan de inventory (LOW).

## Wat wél klopt

- Eén helper als single source of truth (O1), hergebruikt door beide schemas én de map — divergentie is structureel uitgesloten, niet alleen beloofd.
- `mode="after"`-validator dekt zowel expliciete `model_validate` als impliciete `response_model`-serialisatie — empirisch bewezen op detail én op de admin approve-response (eigen probe).
- O4-uitzondering (curatie ziet naam) is geen vergeten gat maar een geteste, gedocumenteerde beslissing.
- Tests zijn betekenisvol: positief én negatief geval per pad, geen happy-path-only.
- Regressie-oppervlak volledig gedraaid en groen: test_content 23, test_map 12, test_curatie 18 — overeenkomstig de claim van de schrijver.
- Schrijver meldde zelf proactief de admin-gedragswijziging én het eigen DA-punt (Pydantic-laag zonder contract-test) — beide kloppen.
- Chirurgisch: 29 insertions; geen migratie; geen non-ASCII; ruff schoon.

## Devil's Advocate — waarom faalt deze oplossing in de toekomst?

1. **De fix bewaakt een veld, niet een belofte.** De uploader vinkt "anoniem" aan en het systeem maskeert keurig `creator_name` — maar serveert ondertussen `metadata_`, `title_nl` en `body` verbatim publiek. De eerste uploader die zijn naam in een vrije tekst zet (of er door een curator in wordt gezet) heeft een vals gevoel van bescherming. Privacy-UI zonder privacy-semantiek is erger dan geen checkbox: het creëert aansprakelijkheid. Dit moet bij P0-7 (frontend) expliciet worden uitgelegd of de vrije velden moeten meemaskeren.
2. **Dit is de tweede keer dat exact deze regel lekte.** Eerst map, toen list/detail. Zonder contract-test is de derde keer een kwestie van tijd: het volgende schema (embed? export? feed?) met een `creator_name`-veld vergeet de validator. De helper voorkomt divergentie, niet omissie — dat onderscheid is precies waarom "gedeelde helper" hier niet genoeg is als langdurige borging.
3. **De curatie-uitzondering wordt de volgende discussie.** O4 is vandaag verdedigbaar, maar zodra takedown- of AVG-verzoeken binnenkomen ("verwijder mijn naam overal"), is er geen mechanisme: de naam staat permanent in de DB, zichtbaar voor elke curator, en is onflipbaar via de API. Deze feature maakt de publieke kant dicht maar vergroot impliciet de belofte richting uploaders — de juridische/operationele achterkant (recht op verwijdering) ontbreekt nog volledig.
4. **`is_anonymous` als boolean is te grof voor de domeinrealiteit.** Erfgoedportalen kennen "naam wel bij curator, niet publiek", "pseudoniem", "initialen", "alleen na overlijden". De boolean + None-maskering zal de eerste echte curatievraag niet overleven; het datamodel (enum i.p.v. bool, of een apart display_name-veld) is dan een migratie. Voor nu acceptabel — maar noem het een schuld, geen ontwerp.

Geen van deze punten blokkeert deze feature: ze horen bij de opvolg-items die al benoemd zijn (MEDIUM-1, MEDIUM-2) of bij P0-7/P1-2.
