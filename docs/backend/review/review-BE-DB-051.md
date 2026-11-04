STATUS: APPROVED WITH NOTES

# Review BE-DB-051 -- de schadelijke schemadrift-gevallen

| | |
|---|---|
| **Feature** | BE-DB-051 |
| **Branch** | `iter/schemadrift` |
| **Commits** | `8c5acd64` |
| **Datum** | 2026-10-24 |
| **Eindoordeel** | APPROVED WITH NOTES -- geen open CRITICAL of HIGH |

---

## 1. Verloop

Gate 2 met een code-reviewer (read-only, niets gedraaid), een ronde, eindoordeel GO. Het
oordeel is niet zonder meer overgenomen: de twee opmerkingen die iets te meten gaven, zijn zelf
gemeten of verwerkt.

## 2. Bevindingen van de reviewer en wat ermee gedaan is

| Opmerking | Ernst | Afhandeling |
|---|---|---|
| Downgrade-tests gebruikten `downgrade -1`; een latere migratie op develop laat ze stilletjes iets anders toetsen | MEDIUM | verwerkt: vaste revisie `20261020_tenant_ap_verbindingen`; 9 integratietests groen |
| De opruimstap van de job draait nu voor het eerst echt en is niet tegen het ketenschema bewezen | MEDIUM | verwerkt: `test_cleanup_old_aggregations_slaagt_op_het_ketenschema`, groen |
| Het mutatiebewijs van de unittest stond als "nog te draaien" | LOW | gedaan: schakelaar aan -> 3 rood en de schakelaartest groen; schakelaar teruggezet |
| Rijen in `governance_risk_entries` met enum-NAMEN zouden na de modelwijziging een 500 geven op het lijst-endpoint | LOW, niet gemeten | open: zie hieronder |
| `bind.execute` in `downgrade()` werkt niet in offline-modus | LOW | aanvaard; een downgrade met voorwaarden op data kan niet offline |

## 3. Open, met naam

- Het aantal rijen in `governance_risk_entries` op staging en productie is niet gemeten (geen
  Azure-toegang). Er is in de code geen enkel schrijfpad gevonden, en via asyncpg kon een insert
  nooit slagen, dus de verwachting is nul. Meet voor de uitrol:
  `SELECT count(*) FROM governance_risk_entries`.
- Of een externe planner de aggregatiejob op naam aanroept, is niet nagegaan.

## 4. Eindoordeel

**APPROVED WITH NOTES.** De wijziging verruimt alleen en laat bij een downgrade nooit data
verloren gaan. Het uitschakelen van de aggregatiejob is een besluit van de regie en een
bewuste, gemelde functionaliteitsbeperking, geen verborgen fout.
