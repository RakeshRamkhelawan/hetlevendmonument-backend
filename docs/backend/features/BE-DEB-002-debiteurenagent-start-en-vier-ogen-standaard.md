# Backend Feature Specification

## Metadata

- **Feature ID:** BE-DEB-002
- **Feature naam:** Debiteurenagent dag 3 -- agent starten, vier ogen als standaard en instelbaar, rijslot
- **Status:** Geimplementeerd
- **Auteur:** bouwer debiteurenagent dag 3
- **Reviewer:** code-reviewer + security-reviewer (subagents, Gate 2)
- **Datum:** 2026-10-05
- **Gerelateerde user story / ticket:** meetlat scenario 5; brief `docs/agent-briefs/generated/2026-10-05-sprint-dag-debiteurenagent-dag-3-scherm-en-start.md`
- **Gerelateerde router / module:** `src/core/api/v1/receivables/router.py`, `src/core/api/v1/tool_broker/four_eyes_router.py`, `src/core/governance/four_eyes.py`, `src/core/als/agents/skills/dunning.py`, `src/core/tool_broker/receivables_registry.py`
- **Gerelateerde frontend endpoints:** FE-PGS-032
- **Gerelateerde database tabellen:** `tenants.settings` (sleutel `four_eyes_actions`), `receivables`, `outgoing_messages`
- **Versie:** 1.0

---

## Doel en scope

### Doel

Een medewerker kan de debiteurenagent per factuur een herinnering laten klaarzetten; die wacht
op goedkeuring. Een nieuwe omgeving krijgt de vier-ogen-standaard uit ADR-039, en een beheerder
kan die per actie wijzigen.

### In scope

- `POST /api/v1/receivables/reminder-proposals` (`receivable_ids` 1-20, `kind`): schrijfrecht,
  CSRF, 10/min. Tenant uit de JWT, de ingelogde gebruiker wordt de aanvrager in het ticket.
  Zonder taalmodel; elke factuur loopt door `act()` (sjabloon, Council, HITL-vloer).
- Vier-ogen-standaard bij aanmaken (registratie, tenantbeheer, servicelaag, single-tenant
  opstart): AAN voor HR-tools, betalen, IBAN, afboeken, incasso; UIT voor herinneringen.
- `GET`/`PUT /api/v1/tools/hitl/four-eyes`: lezen iedereen in de tenant, wijzigen alleen
  beheerder, auditregel `four_eyes_settings_changed` met oud en nieuw.
- `recipient_name` in de briefparameters; `SELECT ... FOR UPDATE` en opnieuw renderen uit de
  vergrendelde rij in het verstuurpad.

### Out of scope

- Bestaande tenants krijgen de standaard NIET (zou datamigratie of stille betekeniswijziging zijn;
  open vraag aan Rakesh). SMTP. `/packs/execute` repareren.

## Technische beschrijving

### Architectuur

Router -> `receivables/dependencies.py::start_reminder_proposals` -> catalogus ->
`DunningSkill.propose_reminders`. De standaard staat in `rbac_models.py`
(`with_four_eyes_defaults`), omdat de aanmaakpaden in database/auth/services zitten en een
import uit governance daar een DSM-grens breekt (gemeten met de architecture-tests).

### Foutafhandeling

Onbekende actienaam: 400 zonder de invoer terug. Niet-beheerder: 403. Factuur buiten de tenant:
per factuur `niet_gelukt`. Gewijzigde debiteur na goedkeuring: niets verstuurd, nieuwe
goedkeuring nodig.

## Acceptatiecriteria

- Een voorstel maakt per factuur precies een ticket met de knopdrukker als aanvrager.
- Een nieuwe tenant heeft de standaardlijst; een bestaande blijft ongewijzigd.
- Alleen een beheerder wijzigt vier ogen; een andere tenant wordt niet geraakt.

## Trainingssamenvatting

### Een herinnering laten voorstellen

- Actor: medewerker debiteuren
- Voorwaarde: ingelogd met schrijfrecht, factuur staat open
- Actie: drukt op "Herinnering voorstellen"
- Systeemreactie: de agent zet de brief klaar; er komt een goedkeurverzoek op /hitl
- Succes: melding "wacht op goedkeuring"
- Fout: melding met de reden; er is geen brief klaargezet
- Uitzonderingen: factuur betaald of van een ander bedrijf: geen verzoek

### Vier ogen instellen

- Actor: beheerder
- Voorwaarde: ingelogd als beheerder
- Actie: zet per actie vier ogen aan of uit en slaat op
- Systeemreactie: instelling bewaard, regel in het logboek
- Succes: "Opgeslagen."
- Fout: geen beheerder: "Opslaan is niet gelukt"
- Uitzonderingen: onbekende actie wordt geweigerd

## Regressierisico's

- Tickets van voor dag 3 hebben geen `recipient_name` en worden bij uitvoeren geweigerd
  (veilig; opnieuw laten goedkeuren).

## Nazorg scenario 5 (2026-10-05, tak fix/na-scenario5)

- **Live melden van elk nieuw ticket.** `HITLTicketRepository.create` meldt elk ticket na de
  commit op kanaal `hitl:{tenant_id}` van het ticket (`_meld_na_commit` ->
  `hitl_notifier.broadcast_new_ticket`, in best_effort). Geldt voor elk pad: debiteurenagent,
  ToolBroker, `POST /hitl/request`. Een rollback meldt niets. De losse aanroep in
  `tool_broker/router.py` is weg. Bewijs: `tests/integration/test_een_nieuw_ticket_komt_live_binnen.py`
  (echte websocket-client, PostgreSQL), guard `tests/architecture/test_elk_nieuw_hitl_ticket_wordt_gemeld.py`.
- **Geen standaardtenant in de websocketlaag.** `ConnectionManager.connect` weigert een token
  zonder bruikbare `tenant_id` met 1008; een verbinding zonder token hoort bij geen tenant. De
  claim wordt overal gelezen met `websocket_auth.tenant_from_claim` (positief geheel getal).
  Guard: `tests/architecture/test_websocket_kiest_geen_standaardtenant.py`.

Niet gedekt: een ticket dat in een ander proces (Dramatiq-worker) wordt aangemaakt, bereikt de
websockets van het API-proces niet; vandaag maakt geen worker een nieuw ticket aan.
