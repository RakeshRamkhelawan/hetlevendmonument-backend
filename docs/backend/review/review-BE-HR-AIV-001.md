STATUS: APPROVED

# Review BE-HR-AIV-001: uitleg per opleidingsvoorstel (AI-verordening voor de pilot)

- **Datum:** 2026-10-14
- **Spec:** `docs/backend/features/BE-HR-AIV-001-uitleg-per-voorstel.md`
- **Reviewers:** code-reviewer, quality-reviewer en doc-reviewer (subagents, alleen lezen, op een patch)
- **Bouwer:** sessie sanskritisetu-org-bd, tak `iter/aipilot`

## Gate 2 -- eerste ronde

| Reviewer | Oordeel | Bevindingen |
|---|---|---|
| code-reviewer | voorwaardelijk GO | MAJOR: de uitleg zei "onder het gevraagde niveau" ook als het huidige niveau de eis nu haalt. MINOR: het vereiste niveau is het MAX over alle functies; `Any` in de repository; geen test op een e-mailadres in de eigen lijst. |
| quality-reviewer | GO | MINOR: titel van de uitleg was een `<p>` en geen kop; inspringing van het Fragment; `Any` zonder TODO. ruff, bandit, ASCII-scan en geheimenscan schoon; Any-ratel gelijk (7037). |
| doc-reviewer | NO-GO | BLOCKER: bewering over bewaartermijnen onjuist (er is een standaardtermijn van 7 jaar), "alleen de eerste ziektedag" onjuist (ook de datum van de probleemanalyse), dezelfde onware zin in de uitleg. MAJOR: auditregel is "best effort", rolnaam en vier-ogen-standaard onnauwkeurig, wie de opleiding kiest ontbrak, hash-algoritme deels gesleuteld. |

## Wat ermee gedaan is

- De uitleg heeft een aparte tak als het huidige niveau de eis haalt; zonder nieuwe beoordeling beweert de
  tekst niet meer dat het niveau toen lager was (herreview). De uitleg zegt wie de opleiding koos en gebruikt
  "is voorgesteld" voor een al beslist voorstel. Tests: zes tests op de tekst, elk rood gezien.
- De titel van de uitleg is een `<h3>`.
- Alle klantteksten herschreven op de bevindingen; elke bewering is tegen de code gelezen.
- De MAX-beperking en de publieke bereikbaarheid van de statische teksten staan in het spec.

## Gate 2 -- herreview

| Reviewer | Oordeel | Open |
|---|---|---|
| code-reviewer | GO | MINOR: het vereiste niveau is het MAX (bewust, in het spec); de zin "gekozen door een medewerker van personeelszaken" vooronderstelt dat `created_by` gevuld is (alleen de router maakt voorstellen en vult hem altijd). |
| doc-reviewer | NO-GO op twee punten, daarna door de bouwer gerepareerd | MAJOR 1: het IP-adres is achter een proxy mogelijk dat van de proxy; MAJOR 2: de hashketen belooft "verandering achteraf zichtbaar" terwijl een regel bij een storing zonder controlegetal kan worden opgeslagen. Beide zijn in de teksten verwerkt, evenals de kleine punten. Er is geen derde reviewronde (ronde-cap op eigen artefacten). |

## Wat gemeten is

- Integratietests op echte Postgres: 52 groen (uitlegtests en het bestaande dag-2-bestand).
- Architectuurguard op de klantteksten: 35 groen; tien mutaties (zes op de code, vier op de guard) allemaal rood gezien met een groene controle na terugzetten.
- vitest Personeel 54 groen; `tsc` en `eslint` schoon; ruff schoon; pyright 0; Any-ratel 7037; mypy alleen de twee bestaande fouten van develop.

## Niet gemeten

- De acceptatie met beeld (de draaiende pagina).
- De nauwkeurigheid van de voorstellen en vooringenomenheid.
- Of het IP-adres in de pilotomgeving dat van de persoon is.
- Wat een verwijderverzoek na 30 dagen precies met alle HR-gegevens en auditregels doet.
- De juridische juistheid van de klantteksten: dat toetst een jurist, zoals de kop van elke tekst zegt.
