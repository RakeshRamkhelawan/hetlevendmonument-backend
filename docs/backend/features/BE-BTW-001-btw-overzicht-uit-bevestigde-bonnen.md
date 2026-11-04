# Backend Feature Specification

## Metadata

- **Feature ID:** BE-BTW-001
- **Feature naam:** Btw-overzicht per kwartaal uit bevestigde bonnen -- stap 2 van Zero-Admin Bookkeeping werkt
- **Status:** Gereed op code en meting (Gate 2 in uitvoering, zie de review); de acceptatie met beeld van de draaiende applicatie is NIET door de bouwer gedaan
- **Auteur:** bouwsessie btwoverzicht
- **Reviewer:** code-reviewer, quality-reviewer en security-reviewer (subagents, Gate 2)
- **Datum:** 2026-10-19
- **Gerelateerde user story / ticket:** brief `docs/agent-briefs/generated/2026-10-19-sprint-dag-btw-overzicht-uit-bevestigde-bonnen.md` (pakket `mkb.zero_admin`); Rakesh, 2026-10-19: "prima" op het voorstel om het btw-overzicht als volgende stap te bouwen
- **Gerelateerde router / module:** `src/core/api/v1/bonnen/btw_router.py`, `src/core/als/bonlezer/btw_overzicht.py`, `src/core/als/agents/skills/vatcompliance.py`, `src/core/api/v1/agentic/agentic_domain_router.py`
- **Gerelateerde frontend endpoints:** `GET /api/v1/bonnen/btw-overzicht`, `GET /api/v1/bonnen/btw-overzicht.csv`, `POST /api/v1/agentic/packs/execute`
- **Gerelateerde database tabellen:** geen (GEEN migratie, GEEN tabel)
- **Versie:** 1.0

## Doel en scope

### Doel

Een klant ziet per kwartaal de voorbelasting (rubriek 5b) per tarief uit de bonnen die hij zelf heeft bevestigd,
controleert het en neemt het zelf op in zijn aangifte. Stap 2 van pakket `mkb.zero_admin` (BTW-aangifte
voorbereiden) gebruikt hetzelfde overzicht en slaagt.

### In scope

- `GET /api/v1/bonnen/btw-overzicht?kwartaal=2026-Q3` en `.csv` (`receipts:read`), tenant uit de JWT. Zonder
  `kwartaal` het lopende kwartaal; een ongeldig kwartaal is een 422 met een Nederlandse tekst.
- Het overzicht: kwartaal, periode, rubriek ("Voorbelasting", 5b), aantal bevestigde bonnen, aantal met een
  aandachtspunt ("Controleren"), aantal dubbele bevestigingen dat niet is meegeteld, voorbelasting per tarief (9,
  21, overig) en het totaal.
- Scherm: op `/bonnen` een blok "Btw-overzicht" met kwartaalkeuze (lopend en vier vorige), de bedragen met een
  decimale komma, de uitleg "Dit is een overzicht van de btw op uw bevestigde bonnen. Controleer het en neem het zelf
  op in uw aangifte." en een download (CSV, veilig zoals de bevestigde-bonnen-export).
- Pakket: `vatcompliance` bedraad (`_PILOT_WIRED_AGENT_IDS`) met `execute_with_manifest_prompt`; de uitslag toont
  kwartaal, voorbelasting per tarief en het aantal bonnen, of verwijst naar het scherm Bonnen bij een kwartaal zonder
  bevestigde bonnen (geslaagd met 0).

### Buiten scope

- Niets indienen bij de Belastingdienst, geen omzetkant (omzetbelasting komt niet uit bonnen), geen advies, geen
  externe dienst, geen migratie, geen tabel.
- Stap 3 van het pakket en alles buiten het btw-overzicht.

## Besluiten van de bouwer (aannames, niet van Rakesh)

- **Het kwartaal volgt de bondatum**, niet het moment van bevestigen. Grenzen inclusief; "het lopende kwartaal"
  rekent in UTC.
- **Standaardkwartaal is het LOPENDE kwartaal** (de brief liet dit open). Het scherm laat het vorige kwartaal met een keuze zien.
- **Afronding:** elk tarief is de som van de exacte `Decimal`-bedragen, daarna op de cent half omhoog (van nul af);
  het totaal is de som van de afgeronde delen, zodat het scherm optelt. Een uitkomst van min nul komt nooit als
  `-0.00` naar buiten. De aangifte zelf rondt af op hele euro's; dat is aan de klant.
- **Tarieven:** 9 en 21 apart (ook als `09` is geschreven), elk ander tarief onder `overig`.
- **Dezelfde bon telt een keer:** twee bevestigingen met dezelfde `sha256` tellen als een; de LAATSTE bevestiging
  telt (wie een fout ziet en opnieuw bevestigt, verbetert zich; besluit regie 2026-10-19), de rest wordt als
  `aantal_dubbel` gemeld. Binnen het gekozen kwartaal en binnen een tenant.
- **Wat niet aan het schema voldoet** (geen getal, onbekend veld) wordt overgeslagen en nooit geraden.
- **Een creditnota** (negatieve bedragen) wordt afgetrokken; het aandachtspunt "btw groter dan het totaal"
  vergelijkt absolute waarden.

## Trainingssamenvatting

### Het btw-overzicht van een kwartaal bekijken

- **Actor:** een ingelogde gebruiker met `receipts:read`.
- **Voorwaarde:** bonnen zijn gelezen en door een medewerker bevestigd (scherm Bonnen).
- **Actie:** op `/bonnen` bij "Btw-overzicht" een kwartaal kiezen; eventueel "Btw-overzicht downloaden (CSV)".
- **Systeemreactie:** de server telt de bevestigde bonnen van het kwartaal van de eigen tenant en toont de
  voorbelasting per tarief, het totaal, het aantal bonnen en eventuele aandachtspunten of dubbele bonnen.
- **Succes:** de bedragen staan er met een decimale komma; de CSV bevat de bonnen van het kwartaal en onderaan de totalen.
- **Fout:** 422 bij een ongeldig kwartaal; 403 zonder `receipts:read`; 429 bij te veel aanroepen; de melding "Het
  btw-overzicht kon niet worden geladen." als het ophalen mislukt.
- **Uitzondering:** een kwartaal zonder bevestigde bonnen toont "In dit kwartaal zijn nog geen bevestigde bonnen.
  Bevestig uw bonnen hierboven; ze tellen dan mee." en geen download.

## Open punten

- De afrondingsregel en het standaardkwartaal zijn aannames van de bouwer.
- Dubbele bonnen worden alleen herkend met dezelfde `sha256`; twee foto's van dezelfde bon zijn twee bestanden en tellen beide.
- Het overzicht leest de BEVESTIGDE VELDEN (`<bon>.bevestigd.json`), niet de bon zelf. Die velden blijven tot het
  einde van het kwartaal van de bondatum plus 3 maanden (besluit Rakesh 2026-10-17, "optie 2"); alleen de bon en
  zijn metabestand gaan na 30 dagen weg. Een bon van 40 dagen oud, bevestigd in het lopende kwartaal, telt dus nog
  mee (test `TestDeBevestigdeVeldenBlijvenNaTienEnDertigDagen`). Een eerdere versie van deze spec schreef ten
  onrechte "30 dagen"; gemeten in `opruimen.py` (`bewaar_tot`, `ruim_bevestigd_op`).
- Productie: de uploadmap staat nog niet in `docker-compose.prod.yml` of Azure; voor deploy te regelen.

## Regressierisico's

- `router.py` van `bonnen` hangt een sub-router in vóór `/{bestand_id}`; een vaste route die na `/{bestand_id}` komt, wordt als bon-id gelezen.
- `agentic_domain_router.py`: de samenvatting per agent is een vaste mapping met een vormcontrole per agent.
