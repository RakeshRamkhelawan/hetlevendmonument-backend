STATUS: APPROVED

# Review BE-BTW-001: btw-overzicht per kwartaal uit bevestigde bonnen

- **Datum:** 2026-10-19
- **Spec:** `docs/backend/features/BE-BTW-001-btw-overzicht-uit-bevestigde-bonnen.md`
- **Reviewers:** code-reviewer, quality-reviewer en security-reviewer (subagents, alleen lezen)
- **Bouwer:** bouwsessie btwoverzicht, tak `iter/btwoverzicht`
- **Rondes:** twee; er is geen derde ronde gehouden

## Gate 2 -- ronde 1

Bevindingen die zijn opgepakt (eerst rode tests, dan de reparatie, commit 1e1cdbcb): dezelfde bon twee keer
bevestigd telde dubbel (nu een keer, gemeld als `aantal_dubbel`); een tarief als `09` telde als overig; een
bestand dat niet aan het schema voldoet werd meegerekend (nu overgeslagen); een uitkomst van min nul kwam als
`-0.00` naar buiten; een creditnota gaf onterecht het aandachtspunt Controleren; een `assert` in de CSV-route;
niet-ASCII tekens in een test.

## Gate 2 -- ronde 2 (commit 1e1cdbcb)

| Reviewer | Oordeel | Opmerkingen |
|---|---|---|
| security-reviewer | GO | Geen kritiek, hoog of middel. LAAG: bij een dubbele bon telt de EERSTE bevestiging, niet de beste; LAAG: ontdubbelen alleen binnen het gekozen kwartaal. Beide deterministisch en zichtbaar via `aantal_dubbel`. |

Daarna (besluit regie 2026-10-19): bij een dubbele bon telt nu de LAATSTE bevestiging in plaats van de eerste
(rode test eerst, dan de reparatie). Het ontdubbelen per kwartaal blijft zoals het was: een ander geval (de
medewerker koos zelf twee data), met een test die het vastlegt. Verder rechtgezet: de spec zei ten onrechte dat
bevestigde bonnen 30 dagen blijven; het overzicht leest de bevestigde velden, die tot het einde van het kwartaal
van de bondatum plus 3 maanden blijven. Een test met een bon van 40 dagen oud, na de opruiming, bewijst dat.

## Mutatiebewijs

12 mutaties, allemaal rood (`mut6.log` en `mut6b.log` in `D:\Dev\ss-backup-avgc-2026-10-13`, in een
wegwerp-worktree; map weg, gecontroleerd).
