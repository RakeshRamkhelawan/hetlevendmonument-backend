# Code Review: BE-EP-054 BagIt-archiefexport

**Feature ID:** `BE-EP-054`
**Reviewers:** Gate 2, twee onafhankelijke agents (code-reviewer, quality-reviewer), elk twee rondes
**Datum:** 2026-11-01
**STATUS: APPROVED WITH MINOR GAPS**

---

## Ronde 1: NO-GO (beide)

Tenant-isolatie en BagIt-formaat goedgekeurd; geblokkeerd op foutafhandeling, geheugen en tests.

| Bevinding | Ernst | Verwerkt |
|---|---|---|
| Azure/OS-fouten niet ingepakt; een tenant brak de wekelijkse lus voor alle volgende | HIGH | Opslag pakt in als `FoundationStorageError`, `BagError` -> `ArchiveExportError`, worker vangt per tenant `(ArchiveExportError, SQLAlchemyError)`; test met twee tenants |
| Pakket in opslag zonder rij bij mislukte flush | HIGH | `export()` verwijdert het pakket bij `SQLAlchemyError` op flush; test |
| Geen endpointtests / tenant-isolatie ongetest | HIGH | `test_foundation_archive_endpoints.py`: 403 x3, 404 + SQL-tenantfilter, curatorrol, 429, 500 vaste tekst, 409 |
| Geheugen/DoS, synchrone POST | HIGH/MEDIUM | Grens 512 MiB (vooraf op `file_size_bytes` en na inlezen), 429 binnen 1 minuut, advisory lock per tenant |
| Overschrijven bij gelijke bag-naam | MEDIUM | uuid8 in de objectnaam; test |
| Blobnaam uit URL ongecontroleerd (andere tenant leesbaar) | MEDIUM | `_object_name`: container, unquote, geen `..`/backslash, prefix + tenant-segment; `read_bytes`/`delete_archive` eisen `tenant_id`; tests incl. terugsprong naar BESTAAND bestand |
| `size_bytes` 32-bit | MEDIUM | `BigInteger` in model en migratie |
| Exacte locatie bij anonieme inzending | MEDIUM | afgerond op 2 decimalen; test in beide richtingen |
| CheckConstraint niet in model; tegenstrijdige naamregels | LOW | beide opgelost |
| XSS-popup: `/\` als ander domein; revokeObjectURL te vroeg | LOW | regex + test; setTimeout |

## Ronde 2: GO (beide)

Nagekomen en direct verwerkt: opruimen van het pakket bij een mislukte COMMIT (endpoint en
worker, `FoundationArchiveService.discard`, twee tests), advisory lock tegen gelijktijdige
verzoeken, guard dat elke archiefroute `require_curator` heeft, SQL-tenanttest op de lijst.

## Mutatiebewijs (kopie als terugweg, 2026-11-01)

Elk uitgezet -> minstens een test rood: tenantcontrole opslag, padcontrole (`..`), uuid in
objectnaam, tenant-match endpoints, tenantfilter download, wachttijd, worker vangt geen
DB-fout, afronden anoniem, verweesd pakket na flush, omvanggrens, opruimen na commit
(endpoint), opruimen na commit (taak). Kern: zes mutaties in `foundation_bagit.verify_bag`.

## Bewust open (minor gaps)

- Volledige export in het geheugen en download in een keer: goed voor de demo-omvang, voor
  productie met veel video streamen of een tijdelijke Azure-leeslink.
- `_upload_local` schrijft niet via een tijdelijk bestand; een crash kan een half bestand
  zonder rij achterlaten.
- Opruimen van oude pakketten na een AVG-verwijderverzoek: onderdeel van het AVG-pakket.
- Endpointtests zijn unit-tests met gemockte sessie; geen integratietest tegen PostgreSQL
  (geen test-Postgres op deze machine).

## Devil's Advocate

Het grootste resterende risico is niet de code maar de omvang: de grens van 512 MiB is een
aanname over een stichtingscollectie. Groeit die met video, dan faalt de export netjes in
plaats van de werker onderuit te halen, maar dan is er ook geen archief meer totdat er
gestreamd wordt. Dat moet in de productieplanning staan, niet pas opduiken bij de eerste
mislukte zondag.
