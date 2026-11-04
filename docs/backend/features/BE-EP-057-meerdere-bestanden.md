# Feature-spec: BE-EP-057 Meerdere bestanden per verhaal (ADR-029)

**ID:** `BE-EP-057`
**Onderwerp:** Tot 10 bestanden per verhaal; curator bekijkt een inzending voor de beoordeling; iPhone-video
**Aanmaakdatum:** 2026-11-03
**Status:** Gebouwd met unit-, mutatie- en componenttests; migratie `20261103b_adr029_content_bestanden`
**Sprint / Context:** Demo subsidiegever november 2026; vervolg op BE-EP-056

---

## 1. Doel & Context

Een verteller heeft vaak meer dan een foto of opname bij een verhaal. Tot nu toe kon er een bestand
mee. Daarnaast bleek dat een curator een nieuwe inzending niet kon openen: *Bekijken* in het
curatiescherm opent `/item/{id}`, en die route gaf alleen goedgekeurde verhalen terug.

## 2. Ontwerp

- Het **eerste** bestand blijft op `foundation_content.file_url` staan. Alle bestaande code
  (lijsten, kaart, sitemap, OAI-PMH, curatie) blijft zo ongewijzigd werken.
- **Extra** bestanden komen in de nieuwe tabel `foundation_content_bestanden` (`volgorde` 2, 3, ...),
  met `tenant_id` en Row Level Security (zelfde policy als de andere foundation-tabellen).
- **Upload**: `POST /content/{id}/upload?extra=true` voegt een bestand toe. Zonder hoofdbestand
  wordt het het hoofdbestand. Zonder `extra` vervangt een upload het hoofdbestand (ongewijzigd).
- **Ophalen**: `GET /content/{id}/bestanden/{bestand_id}/media` met dezelfde opties als `/media`
  (`redirect`, `stream`, `download`).
- **Detail**: `GET /content/{id}` geeft `bestanden: [{id, volgorde, file_mime, file_size_bytes}]`.

## 3. Beveiliging

- Een extra bestand ophalen gaat door **dezelfde** controle als het hoofdbestand
  (`verify_content_media_access`: status, zichtbaarheid, privacy, educatiesessie). Het bestand moet
  bij dit verhaal EN deze tenant horen; anders 404.
- Maximaal 10 bestanden per verhaal (`MAX_BESTANDEN_PER_VERHAAL`); gecontroleerd VOOR het bestand
  wordt ingelezen of opgeslagen (409).
- Een inzender kan alleen extra bestanden toevoegen zolang het verhaal in behandeling is. Zo komt er
  niets ongezien bij een goedgekeurd verhaal. Een curator of beheerder kan dat ook daarna (409 anders).
- Twee gelijktijdige uploads met dezelfde volgorde: de unieke sleutel (`content_id`, `volgorde`)
  houdt de tweede tegen (409, opnieuw proberen).
- `GET /content/{id}` voor een verhaal dat niet goedgekeurd is: alleen voor een curator of beheerder
  van de eigen tenant, of de inzender zolang het in behandeling of afgewezen is. Anderen krijgen de
  bestaande 404. Educatie-items blijven via deze route onbereikbaar (audit N-2).
- Het portaal laadt de bestanden van een niet-openbaar verhaal via een tijdelijke, ondertekende URL
  die met het inlogtoken wordt opgevraagd (een img/audio/video-tag stuurt geen token mee).
- Afspelen met `stream=true` op externe opslag (Azure): doorsturen (307) naar een tijdelijke URL;
  de blobopslag ondersteunt zelf Range-verzoeken. Voorheen gaf dit op productie 404, waardoor een
  goedgekeurde video of opname niet afspeelde (gevonden bij de telefoontest van 2026-11-03).
- Metadata (GPS) wordt bij elk bestand verwijderd zoals in BE-EP-056; nu ook voor iPhone-video
  (`video/quicktime`, `.mov`) en XMP in `uuid`-blokken.

## 4. Onderdelen

| Onderdeel | Bestand |
|---|---|
| Model en grens | `src/core/models/foundation_content.py` (`FoundationContentBestand`, `MAX_BESTANDEN_PER_VERHAAL`) |
| Migratie | `src/alembic/versions/20261103b_adr029_content_bestanden.py` (puur toevoegend, RLS) |
| Upload en ophalen | `src/core/api/v1/foundation/upload.py` (`extra`, `get_content_bestand_media`, `_lever_media`) |
| Detail en toegang | `src/core/api/v1/foundation/content.py` (`get_content`), `schemas.py` (`FoundationBestandItem`) |
| Archiefexport | `src/core/services/foundation_archive_service.py` (`origineel-2`, `origineel-3`, ...) |
| Video | `src/core/services/foundation_storage.py` (`video/quicktime`, `uuid`) |
| Portaal | `BestandKiezer.tsx` (meerdere), `SubmitStory.tsx` (na elkaar uploaden, mislukte opnieuw), `VerhaalMedia.tsx`, `ContentDetail.tsx`, `api/client.ts` |

## 5. Uitrol

Migratie draaien (`levendmonument-migratie`) en daarna `levendmonument-dbrollen`, zodat de
applicatierol rechten op de nieuwe tabel krijgt. Daarna API en portaal.

## 6. Tests

| Test | Bewaakt |
|---|---|
| `tests/unit/test_be_ep_057_meerdere_bestanden.py` | par. 3: volgorde, hoofdbestand blijft, grens, status, ophalen met dezelfde controle, query op verhaal en tenant, toegang tot niet-goedgekeurde verhalen, archief, .mov en XMP |
| `portal/src/__tests__/VerhaalInsturen.test.tsx` | meerdere bestanden na elkaar, alleen mislukte opnieuw, maximaal 10 |
| `portal/src/__tests__/VerhaalMedia.test.tsx` | extra bestanden op volgorde, tijdelijke URL voor niet-openbare verhalen, axe |

**Mutatiebewijs** (2026-11-03): elke regel is weggehaald en de bijbehorende test werd rood:
inzender voegt toe na beoordeling; geen grens van 10; telling zonder tenantfilter; ophalen zonder
filter op verhaal; ophalen zonder tenantfilter; ophalen zonder toegangscontrole; detail voor een
curator of inzender van een andere tenant; inzender ziet een offline gehaald verhaal; iedereen ziet
een niet-goedgekeurd verhaal; archief zonder extra bestanden; archief zonder tenantfilter; .mov niet
toegestaan; .mov niet opgeschoond; XMP (`uuid`) niet gewist. 15 van 15 rood.

## 7. Bekende beperkingen

- Een los extra bestand verwijderen of de volgorde wijzigen kan nog niet (alleen het hele verhaal).
- Een verhaal verwijderen is een zachte verwijdering (status `removed`); de extra bestanden blijven
  dan, net als het hoofdbestand, in de opslag staan.
