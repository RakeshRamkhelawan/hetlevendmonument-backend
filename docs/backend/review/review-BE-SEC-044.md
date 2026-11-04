# Review BE-SEC-044 -- Drie defecten die niets meldden

| | |
|---|---|
| **Feature** | BE-SEC-044 |
| **Branch** | `fix/fase0-defecten` |
| **Commits** | `9d54ac3d`, `e3597ace`, `14db6caf` |
| **Datum** | 2026-08-17 |
| **Eindoordeel** | APPROVED WITH MINOR GAPS -- geen open CRITICAL of HIGH |

---

## 1. Verloop

Deze drie zijn niet gevonden door een review of een foutmelding, maar door het uitputtend
nameten van zes beweringen uit een dagbrief die ik van reviewers had overgenomen zonder ze
te verifieren. Vier van die zes bleken onjuist; onderweg vielen deze drie defecten op.

Dat is de belangrijkste observatie van deze ronde: **het narekenen van andermans
conclusies leverde meer op dan het onderwerp waarvoor het narekenen bedoeld was.**

## 2. Twee onware oorzaken die in de code stonden

Beide zijn door meting weerlegd, geen van beide was ooit nagemeten toen ze werden
opgeschreven:

1. De uitsluiting van de calendar-actors in `src/workers/actors.py:42-44` motiveerde
   zichzelf met een importcyclus die `DATABASE_URL` bij import vereist. `actors.py` zit in
   datzelfde pakket, dus die keten liep sowieso al -- gemeten: alle drie de modules laden
   samen zonder fout.
2. De fail-secure tak van de tenantfilter maakte ALLE tabellen leeg, inclusief tabellen
   zonder `tenant_id`. Dat is nooit als bewuste keuze gedocumenteerd; het was een
   divergentie met de tak drie regels lager.

## 3. Twee fouten in mijn eigen guards, betrapt door het mutatiebewijs

**De actor-guard was te grof.** Ik had twee instappunten hardgecodeerd en miste daarmee de
tweede workercontainer (`docker-compose.yml:353`). Vijf van de zeven bevindingen waren
vals-positief. Opgelost door de instappunten uit de compose-bestanden te lezen -- meteen
futureproof, want een nieuwe workercontainer telt nu vanzelf mee. Tweede correctie: een
actornaam kan in twee modules staan, dus de guard houdt een verzameling per naam bij.

**De allowlist-guard was hol en is verwijderd.** Ik wilde de retentie-allowlist aan de
daadwerkelijke uitvoering koppelen, want dat was wat D3 misleidend maakte. Bij het
mutatiebewijs bleven twee mutaties die rood hadden moeten worden groen: de guard toetste
of de tabelnaam voorkomt in een BESTAND met minstens een ingeplande actor, en
`retention_cleanup.py` bevat ze allemaal. Verwijderd in plaats van laten staan.

Dat is de tweede keer in twee dagen dat een guard van mij hol bleek, en beide keren was de
oorzaak dezelfde: te grof gekoppeld. De eerste keer was het een docstring die werd
meegelezen, nu een bestand in plaats van een functie.

## 4. Wat OPENSTAAT

| Nr | Wat | Borging |
|---|---|---|
| D2b | `core/workflow/api.py:22` stuurt naar een actor uit een dubbele module die niet wordt gedeployd | gedateerde uitzondering + staleness-test |
| -- | de allowlist-belofte is niet machinaal geborgd | geen; expliciet vermeld in de feature-doc |

## 5. Bewijs

```
9d54ac3d   4 tests, 2 rood voor de fix; 689 groen gericht
e3597ace   guard vond 7, waarvan 5 vals-positief door eigen fout; na correctie 2 echt
14db6caf   KNOWN_UNSCHEDULED nu leeg; 10 groen
samen      15689 passed / 0 failed, pyright 0, mypy 0, ruff schoon
```

## 6. Eindoordeel

**APPROVED WITH MINOR GAPS.** Drie actieve defecten weg, elk met een meting voor en na.
Twee ervan konden alleen bestaan omdat er nooit een melding komt wanneer iets niet
gebeurt; daar zijn nu guards voor die nieuwe gevallen blokkeren.
