# Backend Feature Specification

## Metadata

- **Feature ID:** BE-DEB-004
- **Feature naam:** Debiteuren rondt zichzelf af -- bankafschrift vinkt betalingen af, eigen escalatietermijn, geen brief na betaling, verloop per factuur
- **Status:** Geimplementeerd (Gate 2 ronde 2 verwerkt, niet opnieuw beoordeeld; zie review-BE-DEB-004)
- **Auteur:** bouwer debiteuren vanzelf afronden (tak `iter/debiteurenaf`)
- **Reviewer:** security-reviewer (subagent, Gate 2, twee rondes)
- **Datum:** 2026-10-20
- **Gerelateerde user story / ticket:** meetlat Keten B; brief `docs/agent-briefs/generated/2026-10-20-sprint-dag-debiteuren-vanzelf-afronden.md`
- **Gerelateerde router / module:** `src/core/api/v1/receivables/` (`afschrift_router.py`, `instellingen_router.py`, `tijdlijn_router.py`, `dependencies.py`), `src/core/services/bankafschrift.py`, `src/core/services/debiteur_tijdlijn.py`, `src/core/governance/debiteuren_instellingen.py`, `src/core/tasks/debiteuren_tasks.py`, `src/core/tool_broker/hitl_store.py`
- **Gerelateerde frontend endpoints:** geen eigen FE-ID in deze dag (schermen: `ReceivablesPage`, `DebiteurenInstellingenPage`, `HITLActionCard`)
- **Gerelateerde database tabellen:** `receivables`, `outgoing_messages`, `tenants.settings` (sleutel `escalatie_na_dagen`), `audit_logs`, `hitl_tickets` (alleen lezen). Geen migratie.
- **Versie:** 1.0

---

## Doel en scope

### Doel

Een medewerker hoeft betalingen niet meer een voor een met de hand af te vinken: een bankafschrift inlezen zet de
betaalde facturen vanzelf op betaald. Elk bedrijf kiest zijn eigen escalatietermijn. Er gaat geen brief meer de deur uit
voor een factuur die al betaald is. Per factuur is te volgen wat er is gebeurd, door wie en wanneer.

### In scope

- `POST /api/v1/receivables/bankafschrift` (`application/xml` of `text/xml` als ruwe inhoud, hoogstens 5 MB): recht
  `receivables:write`, CSRF, 10/min. Alleen geboekte bijschrijvingen (credit) uit een CAMT.053-bestand. Afvinken alleen als
  PRECIES een open, herinnerde of geescaleerde factuur van de EIGEN tenant past op factuurnummer (los woord in de
  omschrijving), bedrag en valuta. Anders staat de bijschrijving als "niet gekoppeld" in het antwoord. Een tweede keer
  hetzelfde afschrift vinkt niets af. Er wordt niets van het afschrift bewaard of gelogd; de auditregel
  `receivable_paid_via_bankstatement` bevat alleen factuurnummer, datum en bron.
- Veilig lezen: geen `DOCTYPE` of `ENTITY` (stdlib `ElementTree`, geen nieuwe dependency), alleen UTF-8, grenzen op
  bytes, tags, regels, bijschrijvingen en diepte, en een plafond op het totale koppelwerk. Een retour (`RtrInf`) of een
  eigen debettransactie binnen een creditregel is geen betaling.
- `GET`/`PUT /api/v1/receivables/settings`: de escalatietermijn (1 tot en met 120 dagen, standaard 14) in
  `tenants.settings`. Lezen met `receivables:read`, wijzigen alleen een beheerder (CSRF, 10/min, auditregel met oud en
  nieuw). De dagelijkse opvolging gebruikt de termijn per tenant.
- Een melding aan de medewerkers met `receivables:propose` als een dossier escaleert (Nederlands, niets naar de debiteur).
- Geen brief na betaling: de verzendlus leest vlak voor het versturen de status opnieuw (rijslot) en annuleert het
  bericht; ook `PATCH` naar betaald annuleert onverstuurde berichten. Zonder migratie: "geannuleerd" is `mislukt` met
  `pogingen = MAX_POGINGEN` en een foutreden met het voorvoegsel "Geannuleerd:".
- `GET /api/v1/receivables/{id}/tijdlijn`: aangemaakt, voorgesteld door, goedgekeurd of afgekeurd door, klaargezet,
  verzonden of niet verstuurd (met reden), geescaleerd, betaald; met datum en naam (e-mailadres van de medewerker). De
  vrije notitie van een afkeuring staat afgekapt op 200 tekens. Geen brieftekst, geen adres van de debiteur.
- Een auditregel `receivable_reminder_proposed` per voorstel dat op goedkeuring wacht.
- De HITL-kaart toont de aanvrager met e-mailadres (`requested_by_email`, geen kaal nummer) en noemt de raadstekst een
  "Advies van de Co-Pilot" in plaats van "Reden".
- Rechtenmelding in het Nederlands voor `receivables:read`, `:write` en `:propose` (`RECHT_MELDINGEN`).

### Out of scope

- Een bankkoppeling via internet (alleen een bestand), betalen, crediteuren, een echte status "geannuleerd" (vraagt een
  migratie), een werkelijke naam in plaats van het e-mailadres (de gebruiker heeft geen naamveld).

## Technische beschrijving

### Architectuur

Routers -> `receivables/dependencies.py` (facade, lazy `importlib` voor services en governance: ADR-033 en het DSM-plafond
`test_dsm006_ar_governance_fan_out.py`, want `src/core/services` telt als agent_runtime) -> `services/bankafschrift.py`
(zuiver: bytes in, uitslag uit, een terugroep die afvinkt) -> `ReceivableRepository`. De frontend-client stuurt een
`Blob` ongewijzigd met zijn eigen inhoudstype; een formulier is vermeden omdat de server de inhoud dan in een tijdelijk
bestand zet.

### Gelijktijdigheid

Afvinken neemt een rijslot met een verse rij (`with_for_update` plus `populate_existing`: zonder dat laat een rij die de
sessie al kent de OUDE status staan en doet het slot niets), in oplopende id-volgorde. Een deadlock (40P01) of
lock-timeout (55P03) geeft 409 in het Nederlands (de foutcode is gemeten met een echte deadlock). Het koppelen draait in een
thread; het plafond op het koppelwerk is 500.000 vergelijkingen. Alle schrijvers van `tenants.settings` (termijn, vier ogen, uitleg, en
`TenantService.update_tenant`) nemen hetzelfde slot, anders overschrijft een oude kopie de wijziging van een ander.
`update_tenant` (`PUT /api/v1/tenants/{id}`, beheerder van de eigen tenant) zette `settings` als geheel terug en wiste daarmee
vier ogen (een ontbrekende sleutel betekent UIT) en de termijn; `behoud_beheerde_instellingen` laat die sleutels nu staan
tenzij ze uitdrukkelijk worden meegegeven.

### Foutafhandeling

Ongeldig of kwaadaardig bestand: 422 met een Nederlandse melding die niets uit het bestand herhaalt; te groot: 413; ander
inhoudstype: 415; te veel werk: 422 `TE_VEEL_WERK`, voordat er iets is afgevinkt. Onmogelijke termijn: 422; geen
beheerder: 403.

## Acceptatiecriteria

- Een afschrift met bijschrijvingen die precies op een factuur passen, zet die op betaald met de datum uit het afschrift;
  de rest staat "niet gekoppeld" met omschrijving. Een tweede keer inlezen vinkt niets af.
- Een factuur van een andere tenant wordt nooit afgevinkt, ook niet met hetzelfde nummer en bedrag.
- Een bestand met `DOCTYPE`, te veel tags of bijschrijvingen, of te veel koppelwerk wordt geweigerd zonder dat iets is
  afgevinkt.
- Tenant met termijn 7 escaleert na 7 dagen, met 21 niet; 0 en 121 worden geweigerd.
- Dezelfde persoon met de rollen `debiteuren` en `goedkeurder` kan zijn eigen voorstel niet goedkeuren (vier ogen aan).

## Trainingssamenvatting

### Een bankafschrift inlezen

- Actor: medewerker debiteuren
- Voorwaarde: ingelogd met schrijfrecht; het afschrift is gedownload als CAMT.053 (XML)
- Actie: kiest het bestand bij "Bankafschrift inlezen"
- Systeemreactie: facturen die precies passen staan op betaald; de rest staat "niet gekoppeld"
- Succes: "N facturen afgevinkt als betaald" met de lijst
- Fout: "Het bankafschrift kon niet worden ingelezen" (ander formaat, te groot, te veel werk)
- Uitzonderingen: een bijschrijving zonder factuurnummer of met een ander bedrag wordt nooit afgevinkt

### Het verloop van een factuur bekijken

- Actor: medewerker met leesrecht
- Voorwaarde: de factuur staat in de lijst
- Actie: drukt op "Verloop"
- Systeemreactie: de gebeurtenissen met datum en naam
- Succes: de lijst staat onder de factuur
- Fout: "Het verloop kon niet worden geladen"
- Uitzonderingen: een medewerker die niet meer bestaat staat er als "een gebruiker die niet meer bestaat"

### De escalatietermijn instellen

- Actor: beheerder
- Voorwaarde: ingelogd als beheerder
- Actie: vult het aantal dagen in en slaat op
- Systeemreactie: termijn bewaard, regel in het logboek
- Succes: "Opgeslagen: een dossier escaleert na N dagen zonder betaling."
- Fout: buiten 1 tot en met 120: "Kies een aantal dagen van 1 tot en met 120."
- Uitzonderingen: geen beheerder: "Opslaan is niet gelukt"

## Acceptatie (2026-10-21, onafhankelijke acceptant, met beeld)

Oordeel: GOEDGEKEURD MET OPMERKINGEN; elke stap van voorstel tot escalatie liep. Beelden: `D:	mp\debiteurenaf-acccceptatie\`
(buiten de repo). Wat de acceptatie opleverde en wat ik ermee deed:

- **Opgepakt (eigen onderdeel):** een bijschrijving die twee facturen noemde ("Facturen F-4 en F-5") werd aan een gekoppeld
  doordat de andere met de hand op betaald stond. Nu geldt: past een bijschrijving OOK bij een al betaalde factuur, dan niet
  afvinken (een verkeerde afvinking stopt de opvolging). "1 bijschrijvingen" is enkelvoud. Een brief die bij betalen is
  geannuleerd staat niet meer als "datum onbekend" (het tijdstip van betalen). De weigering bij het wijzigen van de termijn is
  Nederlands.
- **Gemeld, niet opgepakt (bestond al of valt buiten de brief):** `/hitl` toont geen besloten tickets (de tabbladen Goedgekeurd
  en Afgekeurd zijn altijd leeg), waardoor "Advies van de Co-Pilot" op een besloten kaart niet te zien is; het goedkeuren van
  een voorstel voor een inmiddels betaalde factuur geeft de melding `tool_failure`; na "Herinnering voorstellen" blijft de
  knop staan (dubbel voorstellen niet uitgesloten); het meldingenscherm is Engels; de zijbalk toont "Debiteuren",
  "Goedkeuringen" en "Instellingen debiteuren" niet vanzelf (de pagina is alleen via de URL bereikbaar).
- **Niet getoetst:** een beheerder zonder voorstelrecht (er was geen account), dubbel voorstellen.

## Regressierisico's

- De Nederlandse rechtenmelding verving een Engelse tekst voor drie rechten; tests die de oude tekst toetsten zijn
  aangepast. Een client die op die tekst matcht, breekt.
- Het voorstel schrijft nu een auditregel met een `user_id`; een test die een gebruiker verwijdert na een voorstel
  loopt vast op de sleutel (twee scenariotests deactiveren nu in plaats van verwijderen).

## Niet gemeten

- Gelijktijdigheid met twee echte verbindingen tegelijk (de test bootst de verse-rij-situatie na in een sessie).
- Het geheugen van 200.000 tags. De rekentijd van het slechtste geval op het plafond (500.000 vergelijkingen) is gemeten: 0,5 tot 1,1 s, in een thread (zie review-BE-DEB-004).
- De tijdlijn met een auditregel van een andere tenant op dezelfde resource (alle queries filteren op tenant; een test
  daarvoor ontbreekt).
