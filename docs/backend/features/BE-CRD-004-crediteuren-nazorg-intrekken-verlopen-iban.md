# Backend Feature Specification

## Metadata

- **Feature ID:** BE-CRD-004
- **Feature naam:** Crediteuren nazorg: een goedkeuring is in te trekken, niets blijft stil liggen, een IBAN hoort bij een leverancier, en de goedkeurder leest waarom een uitvoering niet lukte
- **Status:** Geimplementeerd; Gate 2 en acceptatie met beeld: zie review-BE-CRD-004
- **Auteur:** bouwer (tak `iter/crediteuren-nazorg`, bovenop `iter/crediteuren-dag3-wip` 5f38e972)
- **Reviewers:** code-reviewer, quality-reviewer en security-reviewer (Gate 2)
- **Datum:** 2026-10-27
- **Gerelateerde brief:** `docs/agent-briefs/generated/2026-10-27-sprint-dag-crediteuren-nazorg.md` (op develop, commit 3ab31d76); meetlat Keten F (`docs/meetlat.md`)
- **Gerelateerde frontend:** FE-PGS-040
- **Gerelateerde modules:** `src/core/tool_broker/uitvoerredenen.py`, `src/core/tool_broker/payment_run_registry.py`, `src/core/tool_broker/payables_registry.py`, `src/core/tool_broker/hitl_store.py`, `src/core/api/v1/tool_broker/hitl_router.py`, `src/core/repositories/payable_repository.py`, `src/core/api/v1/payables/betaal_router.py`, `src/core/als/agents/skills/crediteuren.py`, `src/core/als/bonlezer/factuur.py`
- **Database:** geen migratie. Een IBAN is per tenant uniek in de APPLICATIE (`SupplierRepository._controleer_iban_vrij`), bewust niet met een unieke index: een index kan falen op bestaande dubbele rijen en is een migratie (interlock). Twee gelijktijdige invoeren met hetzelfde IBAN kunnen er dus allebei doorheen; het betaalbestand weigert die situatie zelf nog een keer.

---

## Doel en scope

### Doel

Vier gaten uit de meting van 2026-10-27 (op `5f38e972`) dichten, zodat een klant het crediteurenproces kan gebruiken zonder dat er iets stil blijft liggen of verkeerd wordt betaald.

### Besluit

1. **Een mislukte uitvoering na goedkeuren heeft een vaste Nederlandse reden.** Een tool die na goedkeuren faalt geeft naast zijn eigen tekst een `reden_code` (`payment_run_registry.py`, `payables_registry.py`). De goedkeurroute geeft nooit de tool-tekst terug (die kan payload-inhoud bevatten, OP-29) maar zoekt de code op in `uitvoerredenen.UITVOERREDENEN` en geeft de vaste zin als `execution_message`. `execution_error` blijft `tool_failure`; een onbekende of ontbrekende code geeft geen zin (het scherm valt terug op de algemene uitleg). In het logboek staat de code: `approved_execution_failed:tool_failure:<code>`.
2. **Een goedgekeurde factuur is in te trekken zolang hij in geen betaalbestand zit.** `POST /api/v1/payables/{id}/intrekken` met een verplichte reden (minstens 10 tekens): status `goedgekeurd` naar `afgewezen`, een atomaire UPDATE met `status = 'goedgekeurd'` in de WHERE (`PayableRepository.trek_goedkeuring_in`). Een factuur die intussen in een bestand kwam wordt niet aangeraakt (409 met de uitleg dat het bestand eenmalig is). Een factuur van een andere tenant bestaat niet (404). Auditregel `payable_withdrawn` met de reden (persoonsgegevens gemaskeerd).
3. **Een goedgekeurd betaalvoorstel is in te trekken zolang het betaalbestand nog niet is gemaakt.** `POST /api/v1/payables/betaalvoorstel/intrekken` met `ticket_ref` en reden: de facturen van het voorstel gaan terug naar `gecontroleerd` en komen vrij voor een nieuw voorstel. **Welke facturen bij het voorstel horen staat in het ticket zelf** (`_betaalrun_facturen`, gezet in `_voer_uit` in dezelfde transactie als het goedkeuren), niet in het auditlog: dat is een verslag en best-effort. `HITLTicketRepository.approve` laat van de payload alleen een digest over, dus zonder deze sleutel zou niet te zeggen zijn welke facturen een goedgekeurd voorstel waren. Een `_`-sleutel telt niet mee in de goedkeurbinding en staat niet in `tool_input`. Een voorstel van voor deze functie heeft de sleutel niet en wordt geweigerd met de uitleg dat de facturen een voor een zijn in te trekken. Auditregel `payment_run_withdrawn`.
4. **Alleen met het goedkeurrecht.** Beide routes vragen `payables:approve` (`vereis_goedkeurrecht`: procesbevoegdheid, ADR-039, niet de beheerdersrol), naast `payables:read`.
5. **Niets blijft stil liggen.** (a) Een `pending` ticket voorbij zijn termijn telt als verlopen op het moment van LEZEN (`hitl_store._ticket_to_dict` toont `expired`), ook als de uurlijkse opruimtaak nog niet draaide; goedkeuren weigerde dat al (`expires_at` in de WHERE). (b) Taak 0 van de brief, gemeten: de scheduler met de job `hitl_ticket_cleanup` (elk uur op :15) draait wel in de uitrol (`docker-compose.yml:287-293`, `docker-compose.prod.yml:198-201`, `docker-compose.dev.yml:138`, `cd-production.yml` en `cd-staging.yml`); niet gemeten of die containers nu draaien. De verouderde docstring in `hitl_repository.py` is rechtgezet. (c) Een nieuw betaalvoorstel na een niet op tijd beoordeeld voorstel krijgt de zin "eerder voorgelegd, niet op tijd beoordeeld" (alleen als het LAATSTE voorstel van de tenant verlopen is; na het opruimen is de payload leeg, dus de facturen zijn niet te vergelijken). (d) Een verlopen leveranciersticket laat de koppeling van de upload los (`crediteuren.py::_laat_verlopen_ticket_los`): de upload wordt opnieuw beoordeeld, het nieuwe ticket zegt dat het eerder is voorgelegd; een bestandje `.verlopen` naast de claim onthoudt dat. Een ticket dat nog open is houdt de upload vast (`al_verwerkt`).
6. **Een IBAN hoort bij een leverancier (per tenant).** `SupplierRepository.add` en `update_iban` weigeren een IBAN dat binnen dezelfde tenant al bij een andere leverancier hoort (Nederlandse melding met de naam van die leverancier; hoofdletters en spaties tellen niet). Hetzelfde IBAN in een andere tenant mag. Het betaalbestand weigert facturen van twee verschillende leveranciers met hetzelfde IBAN (409, de namen staan in de melding, er wordt niets betaald en de facturen blijven goedgekeurd).

### API

| Route | Recht | Wat |
|---|---|---|
| `POST /api/v1/payables/{payable_id}/intrekken` | `payables:approve` | trek een goedgekeurde factuur in; body `{"reden": "..."}` (10 tot 500 tekens); 404 als de factuur niet van deze tenant is; 409 als hij niet goedgekeurd is of al in een betaalbestand zit |
| `POST /api/v1/payables/betaalvoorstel/intrekken` | `payables:approve` | trek een goedgekeurd voorstel in; body `{"ticket_ref": "...", "reden": "..."}`; 404 onbekend ticket; 409 als het geen goedgekeurd voorstel met bekende facturen is, al is ingetrokken of het bestand al is gemaakt |
| `POST /api/v1/tools/hitl/approve` | (bestaand) | het antwoord heeft nu `execution_message`: de vaste Nederlandse zin bij een mislukte uitvoering |

Geen `tenant_id` in een verzoek (`extra="forbid"`). De tenant komt uit de JWT-context.

## Wat dit NIET doet

Geen afboeken (dag 4), geen migratie, de goedkeurder kiest geen andere leverancier (afkeuren en opnieuw voorleggen blijft de weg), geen nieuwe schermen buiten de bestaande crediteurenkaarten, de geschiedenis en de wachtrij.

## Bewust laten liggen

| Punt | Reden |
|---|---|
| Twee gelijktijdige invoeren met hetzelfde IBAN | geen unieke index (geen migratie); het betaalbestand weigert het zelf nog een keer |
| Een voorstel van voor deze wijziging heeft geen `_betaalrun_facturen` | het is niet in een keer in te trekken; de facturen zijn een voor een in te trekken |
| De verlopen-zin hoort alleen bij het laatste voorstel | de facturen van een opgeruimd ticket zijn niet meer te vergelijken |
| Het `.verlopen`-bestandje blijft staan na een latere goedkeuring | de zin blijft dan op een volgend ticket van die upload staan; dat is waar ("eerder voorgelegd") |

## Niet gemeten

- Dat de scheduler-containers NU draaien (alleen dat de uitrol ze bevat).
- Echte gelijktijdigheid met meerdere API-workers (de atomaire UPDATE is getoetst met een proces).
- Een bank en een telefoonscherm.

## Trainingssamenvatting

### Een goedgekeurde factuur intrekken

- Actor: een gebruiker met het goedkeurrecht (`payables:approve`)
- Voorwaarde: de factuur heeft status Goedgekeurd en zit in geen betaalbestand
- Actie: op de pagina Crediteuren "Intrekken" kiezen, een reden van minstens 10 tekens invullen en bevestigen
- Systeemreactie: de factuur wordt Afgewezen en komt niet meer in een voorstel of bestand; een auditregel met de reden
- Succes: de melding "Factuur ... is ingetrokken en afgewezen."
- Fout: zit de factuur al in een betaalbestand, dan weigert de server met die uitleg (het bestand is eenmalig)
- Uitzonderingen: zonder goedkeurrecht is er geen knop en weigert de server (403)

### Een goedgekeurd betaalvoorstel intrekken

- Actor: een gebruiker met het goedkeurrecht
- Voorwaarde: het voorstel is goedgekeurd en het betaalbestand is nog niet gemaakt
- Actie: in de Geschiedenis van de goedkeuringen het voorstel openen en "Goedkeuring intrekken" kiezen met een reden
- Systeemreactie: de facturen van het voorstel worden weer Gecontroleerd en kunnen opnieuw worden voorgesteld
- Succes: "Het betaalvoorstel is ingetrokken. N facturen zijn vrijgegeven ..."
- Fout: is het bestand al gemaakt, dan kan het niet meer (de server zegt dat het bestand eenmalig is)

### De uitvoering lukt niet na goedkeuren

- Actor: de goedkeurder
- Voorwaarde: tussen het voorstel en het goedkeuren veranderde een factuur of het IBAN van een leverancier
- Actie: het voorstel goedkeuren
- Systeemreactie: er wordt niets goedgekeurd; het scherm zegt in een vaste zin waarom en wat er nu gebeurt
- Succes: de goedkeurder weet dat de facturen opnieuw worden voorgelegd
- Fout: bij een onbekende reden staat er de algemene tekst
