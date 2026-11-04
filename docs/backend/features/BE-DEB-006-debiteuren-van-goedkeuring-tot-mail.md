# Backend Feature Specification

## Metadata

- **Feature ID:** BE-DEB-006
- **Feature naam:** Debiteuren van goedkeuring tot mail -- gemeten met werker en planner, duidelijke melding bij een ongeldig e-mailadres
- **Status:** Geimplementeerd (Gate 2 ronde 1: GO, bevindingen verwerkt, zie review-BE-DEB-006)
- **Auteur:** bouwer debiteuren van goedkeuring tot mail (tak `iter/debiteurenmail`)
- **Reviewer:** security-reviewer (subagent, Gate 2, een ronde)
- **Datum:** 2026-10-22
- **Gerelateerde user story / ticket:** meetlat Keten B (stap 4 tot 6); brief `docs/agent-briefs/generated/2026-10-22-sprint-dag-debiteuren-van-goedkeuring-tot-mail.md`
- **Gerelateerde router / module:** `src/core/api/v1/receivables/schemas.py`; gemeten zonder wijziging: `src/core/tasks/debiteuren_tasks.py`, `src/workers/scheduler.py`
- **Gerelateerde frontend endpoints:** FE-PGS-036
- **Gerelateerde database tabellen:** `receivables`, `outgoing_messages` (alleen gemeten). Geen migratie.

---

## Doel en scope

### Doel

De acceptatie van 2026-10-22 liet na goedkeuren geen mail zien en de factuur bleef op Open. De brief vroeg eerst te meten of de
keten van goedkeuring tot mail werkt, en daarna drie punten van de acceptant op te pakken.

### Gemeten (zonder code te wijzigen)

Goedkeuren schrijft alleen een rij in `outgoing_messages` (status `klaar`). Versturen doet de actor `verstuur_klare_berichten`,
die de planner elke minuut inplant en die de werker uitvoert; pas daarna staat de factuur op `herinnerd`.

Meting op 2026-10-22, lokaal, Redis en Mailpit op de eigen machine, mail naar Mailpit (poort 1025), een bericht uit de
acceptatie als uitgangspunt (bericht 28 voor vordering ACC-1022-1):

1. Planner aan, werker NIET draaiend (de werker was bij de eerste poging door een fout in mijn eigen hulpscript niet gestart):
   na ongeveer vier minuten stond bericht 28 nog op `klaar`, `pogingen=0`, de factuur op `open`. Dat is het "Open, geen mail"
   uit de acceptatie.
2. Planner en werker beide aan: bericht 28 stond op `verzonden` met `pogingen=1`, de factuur op `herinnerd` (zelfde tijdstip als
   `verzonden_op`). In Mailpit stond een mail van `noreply@sanskritisetu.org` met onderwerp "Herinnering: factuur ACC-1022-1".
3. Conclusie: er is geen fout in de keten; zonder werker en planner is "Open, geen mail" verwacht gedrag. Er is daarom geen
   code gewijzigd en geen test voor een oorzaak toegevoegd (de brief eist dat alleen als de mail niet aankomt).

### In scope (gerepareerd)

- Een ongeldig e-mailadres bij een nieuwe of gewijzigde vordering geeft een 422 met per fout het veld, de soort
  `ongeldig_email` en een Nederlandse tekst die zegt waarom (gereserveerd domein zoals `.test`, of een algemene tekst). Het
  adres wordt niet in de melding herhaald.
- `format: email` blijft in het OpenAPI-schema staan en de lengtegrens van 320 tekens blijft gelden (security-review).

### Gemeten, niet in de backend gerepareerd

- **KPI-dashboard "KPI data kon niet worden geladen":** `GET /api/v1/company/dashboard/kpis` bestaat in geen enkele route van de
  backend (795 routes in `/openapi.json`, geen enkele met "kpi") en geeft 404 voor de beheerder en voor het debiteuren-account.
  FE-PGS-014 en de review daarvan noemen dit al: "backend endpoint nog niet gewired". Het eindpunt bouwen is een nieuwe functie
  buiten de grens van de brief. **Besluit regie (6b):** geen eindpunt bouwen, maar het KPI-blok in de frontend verbergen zolang
  de route niet bestaat (controle op 404, niet het blok verwijderen; zie FE-PGS-036). De uitzondering voor een 404 moet weg
  zodra het eindpunt bestaat: dan hoort een 404 weer een melding te geven.
- **Het zakelijke dashboard voor een medewerker debiteuren:** naast de KPI-aanroep (404) geven `/api/v1/agents/stats` en
  `/api/v1/workflows/stats` een 403 voor dat account; de pagina toonde dat als rode Engelse kaart "Error loading dashboard data."
  Gerepareerd in de frontend (FE-PGS-036): een 403 is geen storing maar een ontbrekend recht, dus geen rode melding. De
  backend is niet gewijzigd.
- **Een voorstel dat door de Co-Pilot-raad wordt geblokkeerd (OPEN, oorzaak niet vastgesteld):** tijdens de acceptatie gaf het
  voorstel voor ACC-1022-4 drie keer (ACC-1022-2 een keer) de melding "Er is geen herinnering klaargezet: Council-verdict blocked:
  De Co-Pilot kan deze actie niet uitvoeren." Gemeten in het backendlog: ComplianceOfficer, PrivacyOfficer, SecurityOfficer en
  EthicsOfficer keurden goed; de RiskOfficer gaf na 600 ms een veto met de reden `TIMEOUT` ("Fail-secure blocked due to TIMEOUT"),
  waarmee het hele besluit `blocked` werd. De RiskOfficer roept `shadow_ceo.assess` en `risk_register.actor_track_record` aan
  (`src/core/copilot/council/members/risk_officer.py`); het beleid geeft elke functionaris een eigen tijdlimiet
  (`src/core/copilot/council/policies/default.yaml`). Daarna draaiden werker en planner weer en hetzelfde voorstel lukte bij
  de eerste poging. Dat is een correlatie van een paar pogingen, geen bewezen oorzaak: een koude eerste aanroep na een herstart,
  belasting van de machine of een afhankelijkheid van werker en planner zijn alle drie niet uitgesloten. Gevolg voor een klant:
  een voorstel kan tijdelijk worden geblokkeerd met een Engelse melding. Niet onderzocht en niet gerepareerd (buiten de brief).

### Out of scope

- Het KPI-eindpunt zelf; een unieke index tegen dubbel voorstellen (zie BE-DEB-005).

---

## Technische beschrijving

### Architectuur

`KlantEmail = Annotated[str, AfterValidator(_controleer_email), Field(json_schema_extra={"format": "email"})]`.
`_controleer_email` roept `pydantic.networks.validate_email` aan (de functie die `EmailStr` zelf gebruikt, dus dezelfde
controle en dezelfde genormaliseerde uitkomst) en zet een fout om in `PydanticCustomError("ongeldig_email", <tekst>)`. De
keuze tussen de twee Nederlandse teksten leest een deel van de Engelse reden van de bibliotheek ("special-use or reserved");
de Engelse tekst zelf gaat nooit naar de klant.

### Foutafhandeling

FastAPI geeft de standaard 422: `detail` is een lijst met `loc`, `msg` en `type`. De app registreert geen eigen handler voor
validatiefouten (`register_validation_handlers` bestaat maar wordt nergens aangeroepen).

## Acceptatiecriteria

- Een adres op `.test` geeft 422, soort `ongeldig_email`, een Nederlandse tekst die het e-mailadres noemt en het gereserveerde
  deel; de Engelse bibliotheektekst staat er niet in.
- Een adres zonder apenstaart geeft dezelfde soort met een Nederlandse tekst.
- Een gewoon adres wordt toegevoegd (201) en genormaliseerd zoals voorheen (`Klant@Bedrijf.NL` wordt `Klant@bedrijf.nl`).
- Het OpenAPI-schema noemt het veld een e-mailadres (aanmaken en wijzigen) en houdt `maxLength` 320.

Tests: `tests/integration/test_debiteuren_van_goedkeuring_tot_mail.py` (13), `tests/architecture/test_actie_omschrijving_spiegelt_four_eyes.py` (4).

## Trainingssamenvatting

### Een debiteur toevoegen met een ongeldig e-mailadres

- Actor: medewerker debiteuren
- Voorwaarde: ingelogd met schrijfrecht
- Actie: voegt een debiteur toe met een adres dat niet bestaat of niet kan (bijvoorbeeld op `.test`, of zonder apenstaart)
- Systeemreactie: er wordt niets aangemaakt; de API antwoordt 422 met veld, soort en een Nederlandse tekst
- Succes: het scherm zegt welk veld en waarom (zie FE-PGS-036)
- Fout: een adres langer dan 320 tekens geeft de soort `string_too_long`, geen serverfout
- Uitzonderingen: een gewoon adres met hoofdletters in de domeinnaam wordt genormaliseerd opgeslagen

### Van goedkeuring tot mail

- Actor: goedkeurder
- Voorwaarde: er staat een voorstel klaar; de achtergrondwerker en de planner draaien
- Actie: keurt de herinnering goed
- Systeemreactie: er staat een klaar bericht; binnen ongeveer een minuut verstuurt de werker het
- Succes: de mail staat bij de klant (afzender `noreply@sanskritisetu.org`) en de factuur staat op `herinnerd`
- Fout: draaien werker of planner niet, dan blijft het bericht op `klaar` en de factuur op `open`; er verdwijnt niets
- Uitzonderingen: een mislukte verzending krijgt een nieuwe poging (het aantal pogingen staat op het bericht)

## Acceptatie (2026-10-22, onafhankelijke acceptant, met beeld)

Opstelling: backend, Vite, Dramatiq-werker en planner uit deze worktree (0c120873 plus de scrollreparatie hieronder), Redis en
Mailpit lokaal, drie accounts in dezelfde tenant. Beelden: `D:	mp
azorg-accewijs\mail-punt*.png` en
`herkeuring2-*.png` (buiten de repo). Eindoordeel: **GOEDGEKEURD MET OPMERKINGEN**.

| Punt | Uitslag |
|---|---|
| 1. Van goedkeuring tot mail | Vordering ACC-1022-3 toegevoegd en voorgesteld, door de goedkeurder goedgekeurd om 17:31:20; na ongeveer 45 seconden stond er een mail in Mailpit (afzender `noreply@sanskritisetu.org`, ontvanger `testklant@example.com`, onderwerp "Herinnering: factuur ACC-1022-3", Nederlandse tekst, bedrag en vervaldatum kloppen) en de factuur stond op Herinnerd ("Herinnerd op 22-10-2026"). WERKT |
| 2. Geschiedenis op /hitl | Bovenste regel: Goedgekeurd, "Een herinnering of aanmaning versturen", aangevraagd door en besloten door met e-mailadres, datum "22 okt 2026, 17:31". Geen ticketnummer en geen `send_payment_reminder` in de ingeklapte regel; na uitklappen "Ticketnummer: hitl_...". WERKT |
| 3. Melding bij een ongeldig veld | Een adres op `.test`: "Toevoegen is niet gelukt. Het e-mailadres is niet geldig: het deel na de apenstaart is een gereserveerde naam (zoals .test) die niet voor e-mail bestaat." Een adres zonder apenstaart wordt door de browser zelf tegengehouden (veld van type e-mail, tekst hangt van de browsertaal af); de eigen melding van de applicatie ("Gebruik een adres zoals naam@bedrijf.nl.") is alleen gezien met de browsercontrole uit. WERKT |
| 4. Menu | Beheerder: Debiteuren en Instellingen debiteuren, geen Goedkeuringen; goedkeurder: Goedkeuringen. Bij de beheerder kwam de bevestiging uit de paginastructuur en niet uit het beeld. WERKT |

Bevinding 1 van de acceptant (de melding stond bovenaan terwijl het formulier ongeveer 3800 px lager staat, dus een klant zag
niets gebeuren) is gerepareerd: de pagina scrolt naar het meldingenblok zodra er een melding komt (test eerst rood, commit
31a7c642). Herkeuring met beeld: de foutmelding en de bevestiging "Debiteur toegevoegd." komen in beeld. De melding staat
daarbij strak tegen de bovenrand van het venster.

Opmerkingen van de acceptant, niet opgepakt (buiten de brief):

- De kolom Actie in de Geschiedenis wordt bij een venster van ongeveer 1300 px afgekapt ("Een h...").
- Uitgeklapt staan in de Geschiedenis "Agent: unknown" en "Aangevraagd door: <gebruikersnummer>" terwijl de ingeklapte regel het
  e-mailadres toont; de volgorde van oude besluiten is niet strikt op datum.
- Op een factuur met status Herinnerd staat de knop weer "Herinnering voorstellen" in plaats van "Aanmaning voorstellen"; niet
  duidelijk of dat zo bedoeld is.
- De kaart van een wachtende aanvraag toont nog `send_payment_reminder`, "dunning" en het ticketnummer (de brief ging over de
  Geschiedenis).

Op verzoek van de regie (6b) zijn daarna ook deze vier opmerkingen gerepareerd, plus het KPI-blok bij een 404, in
commits 73ef6c43, bb7b264a en c6bee628 (rode tests eerst, zie FE-PGS-036 en review-FE-PGS-036): de kaart en de geschiedenis in
gewone taal, geen agent-id of gebruikersnummer, geen voorstelknop op een herinnerde factuur, de actie niet meer afgekapt.

Laatste acceptatieronde (stack vers herstart, met beeld): eerst AFGEKEURD, omdat een voorstel werd geblokkeerd door de
Co-Pilot-raad (zie "Gemeten", RiskOfficer-timeout) en het zakelijke dashboard voor een medewerker debiteuren een rode Engelse
kaart toonde (403 op de agent- en workflowcijfers). Het tweede is gerepareerd; na een herstart van werker en planner lukte het
voorstel. Herkansing: **GOEDGEKEURD**. De wachtende kaart toont "Een herinnering of aanmaning versturen", "Debiteurenagent" en
geen zichtbaar ticketnummer en geen regel `unknown`; de geschiedenis is bij een venster van ongeveer 1300 px niet afgekapt en
heeft geen `Agent: unknown` en geen gebruikersnummer; een herinnerde factuur heeft geen voorstelknop (Open wel, Geescaleerd
"Aanmaning voorstellen"); het zakelijke dashboard toont voor een medewerker debiteuren geen rode kaart. Het afkeuren van het
nieuwe voorstel (ticket `hitl_4afb4e6eaaa84b35`) werkte. Opmerking van de acceptant: voor die rol blijft het dashboard bijna leeg
(geen KPI-kaarten en geen Dagelijks Overzicht), zonder uitleg aan de klant; voor de beheerder staan de kaarten "Total
Executions" en "Completed Today" zonder getal en met Engelse labels. Niet opgepakt.

## Bewust laten liggen

| Punt | Reden |
|---|---|
| Het KPI-eindpunt bestaat niet | Nieuwe functie; het blok is verborgen bij een 404 (besluit regie). Zodra het eindpunt er is moet die uitzondering weg. |
| De geschiedenis toont de besloten tickets zonder tabbladen Goedgekeurd/Afgekeurd | Niet vastgesteld of dat al zo was voor deze dag; de besloten tickets zijn wel zichtbaar. |
| Bij een object als `detail` is `error.message` "[object Object]" (LOW, security-review ronde 2) | Zo was het al vooraf: de oorspronkelijke code gaf het object ook aan `new Error`. Niet aangeraakt. |
| De RiskOfficer-timeout (zie "Gemeten") | Oorzaak niet vastgesteld; buiten de brief. |

## Regressierisico's

- Een client die het OpenAPI-schema gebruikt ziet `format: email` nog steeds (hersteld na de security-review, met een test).
- De keuze van de Nederlandse tekst leest een deel van de Engelse bibliotheektekst. Verandert de bibliotheek die tekst, dan
  valt een gereserveerd domein terug op de algemene tekst; de test voor het gereserveerde domein wordt dan rood.

## Niet gemeten

- Of werker en planner in staging en productie draaien (alleen lokaal gemeten, in Docker Compose staan ze als aparte diensten).
- Het gedrag van de verzending bij een mislukte SMTP-verbinding (de bestaande tests van `verstuur_klare_berichten` dekken dat;
  hier niet opnieuw gemeten).
- Of de e-mailvalidatie bij NFC- of IDN-normalisatie een adres langer dan 320 tekens kan maken (gemeld door de reviewer, niet
  uitgezocht).
