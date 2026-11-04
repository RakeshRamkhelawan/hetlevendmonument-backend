STATUS: APPROVED

# Review BE-BON-001: bonlezer dag 1 (testset, lezer, veldenlaag, meting)

- **Datum:** 2026-10-15
- **Spec:** `docs/backend/features/BE-BON-001-bonlezer-dag1.md`
- **Reviewers:** code-reviewer, quality-reviewer en security-reviewer (subagents, alleen lezen)
- **Bouwer:** sessie sanskritisetu-org-bd (nu -7d), tak `iter/bonlezer1`
- **Rondes:** twee, de maximum voor deze meetcode (afspraak regie 2026-10-15); er is geen derde ronde gehouden

## Gate 2 -- ronde 1 (commit 8bb47f98)

| Reviewer | Oordeel | Bevindingen |
|---|---|---|
| code-reviewer | NO-GO | BLOCKER: `geen_netwerk()` liet het slot staan bij twee verweven threads (gemeten). MAJOR: de veldenlaag raadt het btw-bedrag; een spatie als duizendtal geeft het restant; een minteken gaat verloren; pagina's worden door elkaar gehaald; de totaalkeuze pakt de verkeerde regel; het evidence-document overdrijft. |
| quality-reviewer | NO-GO | BLOCKER: mypy 0 naar 3 fouten in `lezer.py` (type-ignore op de verkeerde plek). MAJOR: C901 in `bouw_bon`. |
| security-reviewer | GO met 4 MAJOR | ReDoS in `_KVKNUMMER` en `_FACTUURNUMMER` (gemeten: 40.000 spaties kosten 20 s); kwadratische rekentijd in `_kies_btwbedrag` en `_groepeer_in_regels`; geen invoerbegrenzing; het netwerkslot is niet thread-veilig en dekt `sendto` niet. |

## Wat ermee gedaan is (commit fcc7d76b en daarna)

- Netwerkslot: teller met lock, `sendto` en `sendmsg` erbij; de docstring noemt het een tripdraad.
- Invoer: `controleer_bestand` (inhoud tegen extensie, bytes, pixels, pagina's, cellen); Docling krijgt
  `max_num_pages`, `max_file_size` en `document_timeout`; foutmeldingen noemen de bestandsnaam niet.
- Veldenlaag: begrensde patronen, afkappen van regels en document, geen raden van btw, spatie-duizendtal
  geeft niets, minteken blijft, pagina's apart, maandafkortingen, woordgrens bij de leverancier.
- Meting: factuurnummer telt alleen over facturen.
- `cast` in plaats van `type: ignore`; `bouw_bon` uitgesplitst; evidence herschreven (OCR-cijfers als
  maat, brontekst als bovengrens, elke oorzaak met gelezen tekst of "niet vastgesteld").
- Elke reparatie kreeg eerst een rode test (28 rood tegen de oude code).

## Gate 2 -- ronde 2 (commit f6b5127b)

| Reviewer | Oordeel | Bevindingen |
|---|---|---|
| code-reviewer | GO | Alle punten uit ronde 1 dicht. MAJOR A: `BTW 21% over 100,00` zonder btw-bedrag gaf het netto bedrag als btw. MAJOR B: `Nog te betalen 0,00` onder `Te betalen 121,00` gaf totaal 0,00. Evidence klopt met code en cache. |
| quality-reviewer | GO | Geen BLOCKER of MAJOR. ruff, C901, pyright 0, mypy 0, Any 7037, ASCII, generator byte-gelijk. MINOR: vier tests met meer dan een controle. |
| security-reviewer | NO-GO op een punt | MAJOR M1: een TIFF met een klein eerste beeld en grote vervolgbeelden omzeilt de pixelgrens (gemeten). ReDoS dicht op 15 patronen. MINOR: slot half geplaatst, `partial_success` niet herkend, TOCTOU en symlink (voor de bedrading). |

## Wat ermee gedaan is (commit 2707cce5)

Alle drie de punten die de klant of de worker raken zijn hersteld, elk met een eerst rode test: elk
frame van een beeld wordt getoetst (en het aantal frames), een lezing met status anders dan `success`
wordt geweigerd (de waarden zijn in de container gemeten), het slot blijft niet staan als het plaatsen
mislukt, een btw-regel met een grondslag zonder btw-bedrag geeft niets, 0% met een bedrag geeft niets,
en `Nog te betalen`, `Reeds`, `Openstaand` en `Resterend` tellen niet als totaal. Er is geen derde
reviewronde gehouden; de reparaties zijn afgedekt met tests en mutatiebewijs, niet met een nieuwe review.

## Wat gemeten is

- Unittests: 307 groen (`tests/unit/bonlezer`); 12 rood tegen de code van voor ronde 2, 28 rood tegen de
  code van voor de reparaties van ronde 1.
- Mutatiebewijs op een kopie van de werkmap (een wegwerp-worktree): 30 mutaties, allemaal rood, controle
  groen; de echte werkmap bleef schoon (`git status`). Eerdere rondes vonden twee overlevende mutaties
  (de grens op bedragen per regel en de KvK-ReDoS, beide gemaskeerd door afkappen); er zijn tests
  bijgekomen en beide zijn nu rood.
- Gates: ruff schoon, C901 schoon, pyright 0 fouten, mypy-audit 0 (geen toename), Any-ratel 7037
  (niet gestegen), de hele `tests/architecture` 7329 groen (op de code van ronde 1), generator
  byte-gelijk.
- Meting in een container zonder netwerk op 2707cce5: datum, totaal en factuurnummer 100%, btw 21%
  100%, btw 9% 93%, leverancier 95%, KvK 95%, btw-nummer 91% (zie het evidence-document).

## Niet gemeten

- Echte foto's en echte bonnen; handschrift; andere talen.
- Dat een echte time-out in Docling ook `partial_success` geeft, en dat de invoergrenzen een echt te
  grote of te lange invoer afbreken.
- Het netwerkslot onder echte Docling-threads en onder een asyncio-lus op Linux.
- De hele `tests/architecture` na ronde 2 (alleen de bonlezer-tests, ruff, pyright, mypy en de Any-ratel
  zijn herhaald; de wijzigingen raken alleen `src/core/als/bonlezer/` en tests).
- De bekende beperkingen van de veldenlaag die het evidence-document noemt.
