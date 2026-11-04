# Backend Feature Specification

## Metadata

- **Feature ID:** BE-CRD-003
- **Feature naam:** Crediteuren dag 3: de agent stelt de betaling voor, een mens keurt goed (vier ogen boven het drempelbedrag), en er komt een SEPA-betaalbestand
- **Status:** Geimplementeerd en onafhankelijk geaccepteerd met beeld (2026-10-26, `D:/tmp/crd-acceptatie3/`); Gate 2 twee rondes GO (zie review-BE-CRD-003). De toets tegen het XSD is groen (2026-10-27), zie "Nog niet klaar" voor wat nog niet gemeten is
- **Auteur:** bouwer (tak `iter/crediteuren-dag3-wip`, bovenop `iter/crediteuren-dag2-wip` efd3a26e)
- **Reviewers:** security-reviewer en code-reviewer (Gate 2, twee rondes, beide GO)
- **Datum:** 2026-10-25
- **Gerelateerde brief:** `docs/agent-briefs/generated/2026-10-24-sprint-dag-crediteuren-dag3-betaalvoorstel-en-betaalbestand.md` (op develop, commit facba464); meetlat Keten F (`docs/meetlat.md`)
- **Gerelateerde frontend:** FE-PGS-039
- **Gerelateerde modules:** `src/core/services/sepa_betaalbestand.py`, `src/core/tool_broker/payment_run_registry.py`, `src/core/als/agents/skills/crediteuren.py` en `manifests/crediteuren.yml`, `src/core/repositories/payable_repository.py`, `src/core/api/v1/payables/betaal_router.py`, `betaal_dependencies.py`, `betaal_schemas.py`, `src/core/api/v1/tool_broker/hitl_router.py`, `src/core/governance/four_eyes.py`, `src/core/auth/approval_rights.py`
- **Database:** geen migratie. Het statusverloop bestond al (`ontvangen`, `gecontroleerd`, `goedgekeurd`, `in_betaalbestand`, `betaald`, `afgewezen`; CHECK-constraint `ck_payables_status`), het voorstel gebruikt de bestaande tabel `hitl_tickets` en het drempelbedrag staat in `Tenant.settings` (JSON).

---

## Doel en scope

### Doel

Een medewerker met schrijfrecht laat de crediteurenagent een betaalvoorstel maken. Een goedkeurder keurt het goed of wijst het af met een reden; boven het drempelbedrag (een factuur OF het totaal van het voorstel) moet iemand anders dan wie het voorstel liet maken goedkeuren (vier ogen). Daarna haalt iemand met het goedkeurrecht het SEPA-betaalbestand op en laadt het zelf in zijn bank. **Er gaat niets naar een bank**: het bestand wordt alleen gemaakt en gedownload.

### Besluit

1. **De agent stelt voor, hij betaalt niets.** De HIGH-tool `propose_payment_run` maakt EEN ticket per voorstel met alle facturen die nu aan de beurt zijn: status `ontvangen` of `gecontroleerd`, in euro, van een bekende leverancier met een geldig SEPA-IBAN, die binnen 7 dagen vervallen of al te laat zijn (`HORIZON_DAGEN`), en die niet al in een OPENSTAAND voorstel staan (een `pending` ticket telt alleen mee zolang hij niet is verlopen, een `approved` ticket 15 minuten). Hoogstens 100 regels per voorstel (`MAX_REGELS`); de rest komt in een volgend voorstel. Per regel staat het waarom ("vervalt over 3 dagen", "2 dagen te laat"). De regels komen uit de selectie van het systeem, nooit van een model of een aanroeper (`CrediteurenSkill._prepare_tool_params`). Zonder verantwoordelijke gebruiker doet de agent niets.
2. **Het IBAN in het ticket is gemaskeerd** (de inhoudswachter laat een geldig IBAN in een tool-parameter niet door) en gaat samen met een digest van het hele nummer (`iban_digest`, de eerste 24 hex-tekens van sha256 over `tenant:iban`). Bij goedkeuren moet het IBAN van de leverancier nog dezelfde digest geven.
3. **Goedkeuren is alles of niets.** Na goedkeuren vergelijkt de tool elke regel opnieuw met de database (bestaat de factuur nog, status, bedrag, leverancier, vervaldatum, IBAN-digest) en zet alle facturen met een atomaire UPDATE naar `goedgekeurd` (`PayableRepository.keur_goed_voor_betaling`, de statusvoorwaarde staat in de WHERE). Wijkt er iets af of is een factuur intussen al goedgekeurd, dan draait alles terug en komt er een Nederlandse reden. Dit is de enige weg naar `goedgekeurd`: de gewone statusroute weigert die stap.
4. **Vier ogen boven het drempelbedrag, per factuur OF voor het totaal (besluit regie 2026-10-26: zonder het totaal is honderd keer net onder de drempel een voorstel dat een persoon alleen goedkeurt).** Het drempelbedrag staat in `Tenant.settings["crediteur_betaal_drempel_cents"]`, standaard 250.000 (2.500 EUR; keuze regie 2026-10-24). Een instelling die geen positief geheel getal is valt dicht naar 1 cent (dan vraagt elke betaling vier ogen). De HITL-route beslist het UIT DE DATABASE (`_ticket_eist_vier_ogen` roept `payment_run_registry.vier_ogen_nodig` aan: de bedragen van de facturen in het voorstel en het drempelbedrag van de tenant; fail-secure bij onleesbare of vreemde regels), niet uit de vlag `vier_ogen_vereist` in het ticket; die vlag is alleen voor het scherm. De toets is dezelfde als bij de andere vier-ogenacties: de gebruiker die de agent startte mag het voorstel niet zelf goedkeuren (403, met een auditregel). Daarnaast staat `propose_payment_run` in `FOUR_EYES_ACTIONS` (standaard UIT): een klant kan vier ogen ook voor ELK voorstel aanzetten. **Uitleg van "twee personen":** de eerste is wie het voorstel liet maken, de tweede wie het goedkeurt; een aparte tweede goedkeurstap bestaat niet in de HITL-infrastructuur en is niet gebouwd.
5. **Het betaalbestand is een pain.001.001.09-bestand zonder adres.** Versie: de EPC SCT Customer-to-PSP IG 2025 (EPC132-08) en de Nederlandse richtlijn van de Betaalvereniging werken met de berichtversie van 2019. Bron: https://www.betaalvereniging.nl/en/knowledge-base/standards-in-payments/sepa-implementation-guidelines/. Vanaf 15 november 2026 staat een ongestructureerd adres in EPC-berichten niet meer toe; het bestand heeft geen `PstlAdr`. Bedragen zijn gehele centen en worden als `12.34` geschreven (nooit via een float); namen en toelichtingen worden naar de SEPA-tekenset teruggebracht (accenten weg, geen `//`, geen `/` aan de rand, 70 en 140 tekens). `DbtrAgt` heeft `Othr/Id = NOTPROVIDED` (de EPC-regel voor een bericht zonder BIC).
6. **Het bestand is eenmalig.** Wie het goedkeurrecht heeft (`payables:approve`) geeft de naam en het IBAN van de EIGEN rekening en een uitvoerdatum op (niet in het verleden); de server zet ALLE goedgekeurde facturen van de tenant in een bestand en op `in_betaalbestand`, in een transactie, met een atomaire UPDATE ... RETURNING (`claim_voor_betaalbestand`): een factuur zit in hooguit een bestand, ook als twee mensen tegelijk vragen (de tweede krijgt een lege lijst en een 409). Mislukt het bouwen, dan draait alles terug. Een factuur waarvan de leverancier na de goedkeuring is gewijzigd (`updated_at` na `checked_at`) gaat NIET mee en wordt teruggezet naar `gecontroleerd`, zodat de agent hem opnieuw kan voorstellen en een mens hem opnieuw goedkeurt met het nieuwe IBAN; de overige facturen krijgen wel hun bestand (het antwoord noemt de overgeslagen facturen). Alleen als niets overblijft is er geen bestand (409), en het terugzetten blijft dan staan. Het bestand staat als tekst in het JSON-antwoord (de gedeelde API-client leest elk antwoord als JSON); de browser maakt er de download van. Bericht-id: `CRD` + tijdstempel + 8 hex-tekens.
7. **Waarom eenmalig.** `HITLTicketRepository.approve` vervangt de payload door een digest van de parameters, dus na goedkeuren staan de factuurregels nergens meer. Zonder migratie (de brief verbiedt die zonder STOP) is er geen plek om bij te houden welke facturen bij welk bestand horen, dus het bestand kan niet worden herbouwd. Dat is bewust de veilige kant: een tweede, identiek bestand is een dubbele betaling. Wie het bestand kwijtraakt heeft een ontwerpbesluit nodig (bestand opslaan of een tabel `payment_runs`); gemeld aan de regie.
8. **Logboek.** Voorstel (`payment_run_proposed`), goedkeuring (`payment_run_approved`) en bestand maken (`payment_file_created`) krijgen een auditregel met nummers, aantallen, bedragen en de gebruiker, nooit een IBAN; de regel bij het bestand heeft ook `bestand_sha256` (het bestand zelf wordt niet bewaard) en de overgeslagen facturen. Afwijzen en een geweigerde zelfgoedkeuring loggen via de bestaande HITL-route.
9. **Rechten.** Een voorstel laten maken en het overzicht zien vragen `payables:write` (rol `crediteuren`); goedkeuren, afwijzen en het bestand ophalen vragen `payables:approve` (rol `goedkeurder`). De tool staat in `approval_rights.RECHT_PER_TOOL` en in het permissieprofiel van `crediteuren`; `execute_payment` blijft verboden voor de agent (`denied_actions`).
10. **Agentkaart.** `crediteuren.yml` heeft de tool, de klantregels `betaal_drempel_vier_ogen` en `betaalhorizon_dagen`, en de vakregels "nooit twee keer betalen", "alleen naar het IBAN dat de goedkeurder zag" en "boven de drempel altijd vier ogen".

### API

| Route | Recht | Wat |
|---|---|---|
| `GET /api/v1/payables/betaalvoorstel` | `payables:write` | wat de agent nu zou voorstellen; legt niets vast |
| `POST /api/v1/payables/betaalvoorstel` | `payables:write` | de agent legt een voorstel voor (ticket); 201 bij een ticket, 200 bij niets te betalen, 409 met een reden bij een mislukking |
| `POST /api/v1/payables/betaalbestand` | `payables:approve` | het SEPA-bestand van alle goedgekeurde facturen; 409 met een Nederlandse tekst bij een weigering |

Geen `tenant_id` in een verzoek (`extra="forbid"` geeft 422). De tenant komt uit de JWT-context.

## Nog niet klaar

- **De toets tegen het XSD** (`tests/integration/test_pain001_valideert_tegen_xsd.py`) is op 2026-10-27 groen (7 tests, waarvan twee die het schema juist een foutief bestand laten weigeren; omdraaien van `NbOfTxs` en `CtrlSum` in `PmtInf` maakt 4 van de 7 rood). Het schemabestand komt niet van iso20022.org zelf (403 voor een script) maar is byte-voor-byte gelijk in vijf onafhankelijke projecten (OCA/bank-payment, hbci4java, php-sepa-xml, python-sepaxml, sepa.js; sha256 05440a7e84f695e7dbc6677082f43623cd7393881b76a5e8d648ae21d7d728e3). Wie het officiele bestand van iso20022.org heeft, kan het een-op-een vervangen; de test moet dan groen blijven.
- Niet gemeten: dat een bank het bestand inleest (banken kunnen strenger zijn dan het schema).

## Bewust laten liggen

| Punt | Reden |
|---|---|
| Het bestand kan niet opnieuw worden gemaakt | zie besluit 7; een ontwerpbesluit over opslag is aan de regie |
| Een afwijs- of herbeoordeelpad voor een goedgekeurde factuur op het scherm | OPGELOST in de nazorg (BE-CRD-004): een goedgekeurde factuur en een goedgekeurd voorstel zijn in te trekken, met reden en goedkeurrecht |
| Ontvangen facturen komen ook in een voorstel | zo staat de brief en de regie heeft het bevestigd (2026-10-26) |
| De Nederlandse reden bij een mislukte uitvoering bereikt de goedkeurder niet | OPGELOST in de nazorg (BE-CRD-004): een vaste Nederlandse zin per code, `execution_message` |
| Het eigen IBAN en de naam worden bij elk bestand opgegeven en nergens bewaard | een bankrekening per klant instellen hoort bij het inrichtscherm voor koppelingen (Keten H) |
| Het horizon van 7 dagen en de grens van 100 regels zijn vaste waarden | nog niet per klant instelbaar |
| Welke bank welke pain.001-versie accepteert | NIET gemeten; open punt voor het inrichten van de pilotklant (de bankspecificatie) |
| Het drempelbedrag heeft nog geen scherm | de waarde staat in `Tenant.settings`; een beheerroute volgt in de nazorg |
| Een HIGH-ticket verloopt na 4 uur (`_SLA_HOURS`) | OPGELOST in de nazorg (BE-CRD-004): telt als verlopen bij het lezen en wordt opnieuw voorgelegd; er blijft geen melding of escalatie bij verlopen (niet gevraagd) |

## Niet gemeten

- Dat een bank het bestand inleest.
- Echte gelijktijdigheid met meerdere API-workers (de atomaire UPDATE is getoetst met twee gelijktijdige aanvragen in een proces).
- Een telefoonscherm en een schermlezer.

## Trainingssamenvatting

### De agent stelt een betaling voor

- Actor: de crediteurenagent, gestart door een gebruiker met `payables:write`
- Voorwaarde: er staan facturen met status `ontvangen` of `gecontroleerd` die binnen 7 dagen vervallen of te laat zijn, van leveranciers met een geldig SEPA-IBAN
- Actie: de gebruiker kiest "Betaalvoorstel laten maken"; de agent kiest `propose_payment_run`
- Systeemreactie: een ticket in de goedkeurwachtrij met alle facturen, het totaal, het waarom per regel en of vier ogen geldt; er wordt niets betaald of goedgekeurd
- Succes: het voorstel wacht op een goedkeurder
- Fout: zonder verantwoordelijke gebruiker doet de agent niets; zonder facturen geeft het antwoord "niets te betalen"
- Uitzonderingen: een factuur in een openstaand voorstel komt niet in een tweede voorstel; een leverancier zonder geldig IBAN wordt overgeslagen met een reden

### Een goedkeurder beslist over het voorstel

- Actor: een gebruiker met `payables:approve`
- Voorwaarde: er staat een voorstel in de wachtrij; zit er een factuur boven het drempelbedrag in, dan is de goedkeurder een ander dan wie het voorstel liet maken
- Actie: keurt goed, of keurt af met een reden van minstens 10 tekens
- Systeemreactie: bij goedkeuren gaan alle facturen naar `goedgekeurd` of geen enkele (bij een gewijzigde factuur of IBAN); bij afkeuren blijft alles onbetaald en kunnen de facturen opnieuw worden voorgesteld
- Succes: de facturen zijn goedgekeurd, met een auditregel
- Fout: de eigen aanvrager boven het drempelbedrag krijgt 403; een gewijzigd voorstel krijgt een Nederlandse reden
- Uitzonderingen: een verlopen voorstel (4 uur) kan niet meer worden goedgekeurd

### Het betaalbestand ophalen

- Actor: een gebruiker met `payables:approve`
- Voorwaarde: er zijn goedgekeurde facturen
- Actie: vult de naam en het IBAN van de eigen rekening en de uitvoerdatum in en kiest "Betaalbestand downloaden"
- Systeemreactie: een pain.001-bestand met alle goedgekeurde facturen wordt gedownload; de facturen staan daarna op `in_betaalbestand`; er gaat niets naar een bank
- Succes: het bestand is gedownload en bewaard door de gebruiker, die het zelf in de bank laadt
- Fout: zonder goedgekeurde facturen, met een ongeldig eigen IBAN, een uitvoerdatum in het verleden of een gewijzigde leverancier weigert de server (409) en blijven de facturen `goedgekeurd`
- Uitzonderingen: een tweede verzoek vindt niets meer, want een factuur zit in hooguit een bestand
