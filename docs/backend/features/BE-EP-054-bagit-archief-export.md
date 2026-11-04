# Feature-spec: BE-EP-054 BagIt-archiefexport (ADR-029 Cat 4)

**ID:** `BE-EP-054`
**Onderwerp:** Wekelijkse en handmatige archiefexport van de publieke collectie als BagIt 1.0-pakket (RFC 8493) met Dublin Core per item
**Aanmaakdatum:** 2026-11-01
**Status:** Gebouwd, unit- en architectuurtests; niet getest tegen een echte PostgreSQL of Azure Blob (zie "Niet gemeten")
**Sprint / Context:** Livegang Levend Monument, markt-review 2026-09-24 blokkade 9 (SUMS Cat 4 "duurzame toegankelijkheid")

---

## 1. Doel & Context

ADR-029 belooft dat gepubliceerde erfgoeditems periodiek als BagIt-pakket naar een extern
digitaal archief kunnen. Tot 2026-11-01 bestond daar niets van (`grep bagit src/` = 0). Deze
feature maakt per portaal een volledige momentopname van alles wat publiek is, slaat die op,
legt een controlegetal vast en laat beheerders het pakket downloaden.

**Bewuste afwijking van ADR-029:** ADR-029 noemt "nieuwe/gewijzigde items". Elke export is hier
een VOLLEDIGE momentopname. Dat is een bovenverzameling, laat ook zien wat niet meer publiek is,
en is los op te nemen zonder stapellogica bij het archief.

## 2. Onderdelen

| Onderdeel | Bestand | Wat |
|---|---|---|
| Pakketformaat (puur) | `src/core/services/foundation_bagit.py` | `build_bag()` bouwt een deterministisch zip-bestand; `verify_bag()` rekent een pakket na (manifest, tagmanifest, compleetheid, Payload-Oxum) |
| Dienst | `src/core/services/foundation_archive_service.py` | selectie, AVG-masking, bestanden ophalen, opslaan, rij vastleggen, teruglezen met controlegetal |
| Opslag | `src/core/services/foundation_storage.py` | `upload_archive()` (sleutel `foundation-archief/<tenant>/<bag>.zip`), `read_bytes()` (lokaal en Azure), `mime_extension()` |
| Model | `src/core/models/foundation_content.py::FoundationArchiveExport` | tabel `foundation_archive_exports` |
| Migratie | `src/alembic/versions/20261102_adr029_archief_exports.py` | nieuwe tabel + RLS-policy, werkende `downgrade()` |
| Achtergrondtaak | `src/workers/actors.py::export_foundation_archives` | alle actieve tenants met portaalinstellingen, per tenant met tenantcontext |
| Schema | `src/workers/scheduler.py` | zondag 02:15 UTC, id `export_foundation_archives` |
| API | `src/core/api/v1/foundation/admin/archief.py` | zie par. 3 |
| Portaal | `portal/src/components/ArchiefExportPanel.tsx`, tab "Archief" in `AdminCuratie.tsx` | knop, lijst, download |

## 3. API-contract

Alle drie: `require_curator` (curator of admin) en tenant-match (403 bij een gebruiker van een
andere tenant).

- `POST /api/v1/{tenantSlug}/foundation/admin/archief/exports` -> 201 `ArchiveExportItem`.
  500 met vaste tekst als de export mislukt; dan is er niets opgeslagen en geen rij geschreven
  (ook bij een mislukte commit wordt het pakket weer verwijderd). 429 als er binnen een minuut
  al een export van deze tenant is; gelijktijdige verzoeken wachten op elkaar via
  `pg_advisory_xact_lock(54, tenant_id)`.
  Auditregel `foundation_archive_export_created` (best effort).
- `GET /api/v1/{tenantSlug}/foundation/admin/archief/exports?limit=50&offset=0` ->
  `ArchiveExportListResponse` (`items`, `total`, `limit`, `offset`), nieuwste eerst.
- `GET /api/v1/{tenantSlug}/foundation/admin/archief/exports/{id}/download` -> `application/zip`,
  header `X-Content-SHA256`. 404 als de export niet van deze tenant is; 409 als het bestand
  ontbreekt of niet meer overeenkomt met het vastgelegde controlegetal.

## 4. Pakketindeling

```text
<bag>/bagit.txt                      BagIt-Version: 1.0, UTF-8
<bag>/bag-info.txt                   Source-Organization, Contact-Email, Bagging-Date, Payload-Oxum, ...
<bag>/manifest-sha256.txt, manifest-sha512.txt
<bag>/tagmanifest-sha256.txt, tagmanifest-sha512.txt
<bag>/data/index.json                overzicht van alle items
<bag>/data/items/<id>/metadata.json  alle velden + tags + bestandscontrolegetallen
<bag>/data/items/<id>/dc.xml         oai_dc (Dublin Core)
<bag>/data/items/<id>/tekst.md       de tekst, als die er is
<bag>/data/items/<id>/bestanden/origineel.<ext>
```

Bag-naam: `levendmonument-<slug>-<YYYYMMDDTHHMMSSZ>`.

## 5. Selectie en AVG

- Alleen `status=APPROVED`, `privacy=PUBLIC`, `visibility=PUBLIC`, van deze tenant.
- `creator` leeg bij `is_anonymous`.
- Geen e-mailadressen of uploader-gegevens.
- Uit het vrije JSONB-veld `metadata` alleen de sleutels `fictief`, `periode`, `bronnen`.
- Kan een bestand niet worden gelezen, dan faalt de hele export (geen half pakket).
- Bij een anonieme inzending gaat de locatie afgerond mee (2 decimalen, circa 1 km).
- Grens: 512 MiB aan bestanden per export (`MAX_PAYLOAD_BYTES`), vooraf getoetst op de
  vastgelegde bestandsgrootte en na het inlezen.
- Opslag leest alleen objecten onder `foundation/<tenant>/` of `foundation-archief/<tenant>/`
  van de eigen tenant; objectnamen van archieven krijgen een uuid tegen overschrijven.

## 6. Trainingssamenvatting

- **Actor:** curator of beheerder van een portaal; of de wekelijkse planner.
- **Voorwaarde:** ingelogd met de rol curator of admin, bij de eigen stichting.
- **Actie:** klikt op "Maak nu een archiefexport" in Beheer > Archief.
- **Systeemreactie:** bouwt het pakket, rekent het na, slaat het op, toont het in de lijst.
- **Succes:** een regel met datum, aantal items, grootte en controlegetal; downloaden levert een zip die een BagIt-validator goedkeurt.
- **Fout:** "De archiefexport is mislukt. Er is niets opgeslagen." (bijv. een ontbrekend bestand).
- **Uitzonderingen:** download geeft een foutmelding als het bestand in de opslag is veranderd of weg is.

## 7. Gemeten

- `tests/unit/test_foundation_bagit.py`: 16 tests. Mutatiebewijs (2026-11-01, kopie als terugweg):
  compleetheidscontrole uit, hashvergelijking uit, Payload-Oxum-controle uit, tagmanifest niet
  gecontroleerd, padcontrole uit, ontbrekend bestand niet gemeld -> elk minstens een test rood.
- Onafhankelijk: Library of Congress `bagit-python` 1.9.0 `Bag.validate()` keurt een pakket uit
  `build_bag` goed en keurt hetzelfde pakket met een gewijzigde payloadbyte af.
- `tests/unit/test_foundation_archive_service.py`: selectie (SQL-voorwaarden), masking, bestand
  mee, onleesbaar bestand -> geen opslag, controlegetal bij teruglezen.

## 8. Gate 2

Twee reviewers, twee rondes; ronde 1 NO-GO, ronde 2 GO. Zie `docs/backend/review/review-BE-EP-054.md`.

## 9. Niet gemeten

- Migratie tegen een echte PostgreSQL (geen test-Postgres actief op 2026-11-01).
- `read_bytes()` tegen echte Azure Blob Storage.
- De wekelijkse taak end-to-end in een draaiende worker.
- Het pakket wordt in het geheugen gebouwd en in een keer gedownload; voor een grote
  collectie met video is streamen of een tijdelijke Azure-leeslink nodig.
- Bewaartermijn van oude pakketten: na een verwijderverzoek (AVG art. 17) blijft het item in
  eerdere pakketten staan. Opruimen van oude pakketten is nog niet gebouwd (onderdeel van het
  AVG-pakket).
