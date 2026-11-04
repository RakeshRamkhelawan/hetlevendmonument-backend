# Backend Feature Specification

## Metadata

- **Feature ID:** BE-DEB-001
- **Feature naam:** Debiteurenagent dag 2 -- tools, goedkeuring volgens ADR-039, handmatige invoer
- **Status:** Geimplementeerd (backend); scherm en startroute volgen op dag 3
- **Auteur:** bouwer debiteurenagent dag 2
- **Reviewer:** code-reviewer + security-reviewer (subagents, Gate 2)
- **Datum:** 2026-10-05
- **Gerelateerde user story / ticket:** meetlat scenario 5; brief `docs/agent-briefs/generated/2026-10-05-sprint-dag-debiteurenagent-dag-2-tools-en-goedkeuring.md`
- **Gerelateerde router / module:** `src/core/api/v1/receivables/router.py`, `src/core/api/v1/tool_broker/hitl_router.py`, `src/core/tool_broker/receivables_registry.py`, `src/core/als/agents/skills/dunning.py`
- **Gerelateerde frontend endpoints:** geen (dag 3)
- **Gerelateerde database tabellen:** `outgoing_messages` (nieuw, RLS), `receivables` (twee CHECKs), `tenants.settings` (sleutel `four_eyes_actions`)
- **Versie:** 1.0

---

## Doel en scope

### Doel

De debiteurenagent kan openstaande facturen lezen en een herinnering of aanmaning klaarzetten.
Klaarzetten gaat altijd langs een mens; die ziet wat er gebeurt, aan wie en met welke tekst.
Goedkeuren maakt precies dat ene bericht, afkeuren maakt niets. Wie mag beslissen volgt
ADR-039: zelf beslissen mag, tenzij de tenant vier ogen aanzet of een agent de aanvrager is.

### In scope

- Tools `list_receivables` (MEDIUM, zonder naam/adres) en `send_payment_reminder` (HIGH, schrijft
  EEN rij in `outgoing_messages`, geen SMTP), profiel `dunning`, manifest `hitl`.
- Brieftekst uit een sjabloon in code; de agent vult de brief in VOOR het ticket.
- Vier-ogen-instelling per tenant per actie (`tenants.settings.four_eyes_actions`, standaard uit).
- `POST`/`GET`/`PATCH /api/v1/receivables` voor handmatige invoer.

### Out of scope

- Scherm, goedkeurkaart en route om de agent te starten (dag 3).
- Echte verzending per e-mail; upsert bij een tweede import; bedragdrempel per goedkeurder.

---

## Technische beschrijving

### Architectuur

`DunningSkill._prepare_tool_params` haalt de brief op via `ReceivablesToolRegistry.preview_payment_reminder`
en overschrijft wat het model voor ontvanger, onderwerp en tekst schreef. Daarna Council per
actie; de hitl-vloer (`specialist_base._floor_applies_to`) tilt bij een niet-Annex-III skill alleen
HIGH-acties naar een ticket. Goedkeuren via `/api/v1/tools/hitl/approve` verzilvert het ticket in
de broker (binding op exact deze parameters) en de registry rendert opnieuw en vergelijkt voor hij
schrijft. `outgoing_messages.hitl_ticket_ref` is uniek.

### Foutafhandeling

Een tool die zelf faalt geeft `success: false` zonder payloadwaarden in de melding; databasefouten
worden gelogd met type en `exc_info`, nooit met de SQL-tekst.

---

## Acceptatiecriteria

- Scenario-5-test groen met vier ogen uit en aan (`tests/integration/scenarios/test_scenario_5_betalingsherinnering.py`).
- Isolatietest API groen (`tests/integration/api/test_receivables_api_is_confined_to_its_tenant.py`).
- `alembic heads` = 1, downgrade/upgrade op een wegwerpdatabase geslaagd.

---

## Trainingssamenvatting

### Een herinnering goedkeuren

- Actor: medewerker debiteuren (beheerder binnen de tenant)
- Voorwaarde: er staat een factuur open; de agent heeft een ticket aangemaakt
- Actie: de medewerker leest ontvanger, onderwerp en tekst in het ticket en keurt goed
- Systeemreactie: precies een bericht in de uitgaande post, factuur op `herinnerd`, logregel `hitl_decision` met tijdstip
- Succes: het antwoord meldt `executed: true`
- Fout: de debiteur is intussen gewijzigd; de tool weigert en er gaat niets uit
- Uitzonderingen: met vier ogen aan mag de aanvrager niet zelf goedkeuren (403); een collega wel

### Een herinnering afkeuren

- Actor: medewerker debiteuren
- Voorwaarde: een openstaand ticket
- Actie: afkeuren met een reden
- Systeemreactie: geen bericht, logregel `hitl_decision` met tijdstip
- Succes: de uitgaande post blijft leeg
- Fout: een ticket van een ander bedrijf bestaat niet (404)
- Uitzonderingen: een door een agent aangevraagd ticket kan de aanvrager nooit zelf beslissen

---

## Regressierisico's

- De hitl-vloer is verfijnd: bij Annex III blijft alles een ticket, daarbuiten alleen HIGH.
- Twee bestaande tests ("een beheerder keurt zijn eigen verzoek nooit goed") gelden nu alleen met vier ogen aan.
