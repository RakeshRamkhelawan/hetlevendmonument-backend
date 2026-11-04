# Backend Feature Specification: Noodstop per klant

## Metadata

- Feature ID: BE-NDS-001
- Feature naam: Noodstop per klant (ADR-036 register OP-03)
- Status: gebouwd, Gate 2 ronde 2 verwerkt
- Auteur: bouwsessie noodstop, tak `iter/noodstop-per-klant-2026-10-20`
- Reviewer: code-reviewer, quality-reviewer, security-reviewer (zie `docs/backend/review/review-BE-NDS-001.md`)
- Datum: 2026-10-21
- Gerelateerde router / module: `src/core/api/v1/noodstop/`, `src/core/noodstop/`, `src/core/governance/noodstop_service.py`
- Gerelateerde frontend endpoints: geen (geen frontend in deze dag)
- Gerelateerde database tabellen: `tenant_noodstop` (nieuw)
- Versie: 2

---

## Doel en scope

### Doel

Een beheerder (of het platform) moet een klant in een keer kunnen stilzetten, zodat geen agent
voor die klant nog een actie start. De stand is duurzaam, geldt in elke worker en elk proces, en
elke wijziging staat in het auditlog (wie, wanneer, waarom). Een stand die niet te lezen is telt
als stil (fail-closed).

### In scope

- De tabel, de repository, de service en de API (`GET` en `PUT` voor de eigen klant en voor het platform).
- Elke deur waar een agent een actie start (broker, Council, workflow-engine, actors, scheduler, HITL-goedkeuring).
- De chat (besluit A): `cva_service.chat` en `chat_stream`, copilot (`handle_turn`, HTTP en websocket), de focus-builder-websocket en `AgentChatService`.
- Een architectuurtest die een nieuwe deur zonder controle laat falen.

### Out of scope

- Een lopende actie onderbreken: alleen nieuwe starts worden geweigerd.
- Frontend: er is nog geen scherm voor de noodstop.
- Niet meer out of scope: modelpaden die geen chat zijn staan sinds ronde 3 onder de noodstop (op het punt van de modelaanroep) en worden sinds ronde 4 bij het opstarten van elk proces aangemeld. Zie het reviewdocument.

---

## Build summary

- Nieuw gebouwd: tabel `tenant_noodstop` (migratie `20261020_tenant_noodstop`), model, repository, service, guard, tellers, API, registry, tests.
- Gewijzigd: elke deur uit de inventaris; `eigen_loop` (geeft de run-engine door aan de guard); `DatabaseManager` (kleine-pool-engine); proactieve monitoren (vlag `blijft_draaien_bij_noodstop`).
- Verwijderd: niets.
- Beinvloede bestaande flows: elke tool-uitvoering, Council-beraadslaging, workflow-start, brievenverzending, debiteurenopvolging, CVA-bericht, copilot-chat.

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-NDS-001-A | Guard (`eis_klant_actief`, `eis_chat_actief`, `klant_staat_stil`) | utility | `src/core/noodstop/guard.py` | Nieuw | alle deuren |
| BE-NDS-001-B | Tellers | utility | `src/core/noodstop/metrics.py` | Nieuw | Council, CVA |
| BE-NDS-001-C | Model en repository | model, repository | `src/core/models/tenant_noodstop_models.py`, `src/core/repositories/tenant_noodstop_repository.py` | Nieuw | API |
| BE-NDS-001-D | Service | service | `src/core/governance/noodstop_service.py` | Nieuw | API |
| BE-NDS-001-E | API | router | `src/core/api/v1/noodstop/` | Nieuw | API |
| BE-NDS-001-F | Migratie | alembic | `src/alembic/versions/20261020_tenant_noodstop.py` | Nieuw | - |
| BE-NDS-001-G | Architectuurtest | test | `tests/architecture/test_elke_deur_controleert_de_noodstop.py` | Nieuw | - |

---

## API-flows

### Flow ID: BE-FLW-NDS-001

- Naam: eigen klant stilzetten of opheffen
- Trigger: `PUT /api/v1/noodstop` met `{"is_stilgezet": bool, "reden": str}`
- Voorwaarden: beheerder van de klant (JWT), CSRF-token, limiet 10 per minuut. De klant komt uit de JWT; een `tenant_id` in de body geeft 422.
- Service-stappen: een voorwaardelijke upsert (`set_stand`); bij opheffen de auditregel in dezelfde transactie, dan commit; bij zetten commit, dan de auditregel best-effort.
- DB-operaties: `INSERT ... ON CONFLICT (tenant_id) DO UPDATE ... WHERE NOT (is_stilgezet AND changed_by_platform)` (voor het platform zonder `WHERE`); een rij in `audit_logs` (`noodstop_changed`).
- Successtatus + response: 200 `{"success": true, "data": {is_stilgezet, reden, changed_at, door_platform}}`.
- Foutpaden: 403 `NOODSTOP_DOOR_PLATFORM` (het platform heeft de stop gezet); 503 `NOODSTOP_NIET_OPGEHEVEN` (de auditregel van de opheffing mislukte: de stop blijft staan); 404 `KLANT_NIET_GEVONDEN`; 403 niet-beheerder.
- Eindtoestand: een rij per klant; de guard leest hem bij elke controle.

### Flow ID: BE-FLW-NDS-002

- Naam: platform zet een andere klant stil of heft op
- Trigger: `PUT /api/v1/platform/klanten/{tenant_id}/noodstop` (idem body)
- Voorwaarden: platformsuperuser; de doelklant staat in het pad. De service zet de tenantcontext om (`adopt_tenant`), anders weigert de RLS (gemeten).
- Overig: zoals BE-FLW-NDS-001; een platformstop kan alleen het platform wijzigen.

### Flow ID: BE-FLW-NDS-003

- Naam: een deur controleert de stand
- Trigger: elke agentactie of chatbeurt
- Stappen: `eis_klant_actief(tenant_id)` leest `tenant_noodstop` (geen cache). Alleen een expliciet `False` laat door. Een stilgezette of onleesbare klant geeft `KlantStilgezet`, en elke deur weigert op zijn manier met een Nederlandse melding.
- Verbinding: in een actor-run de poolloze engine van de run achter een semafoor (4); anders een engine met een kleine eigen pool (2 + 2 overloop, wachttijd 5 s) per event loop.

---

## Detaildocumentatie per artefact

### [BE-NDS-001-A] Guard

- Meldingen: `MELDING_STIL`, `MELDING_ONBEKEND` (acties), `MELDING_CHAT_STIL` ("De agents van jouw organisatie staan tijdelijk stil. Neem contact op met je beheerder."), `MELDING_CHAT_ONBEKEND` (chat).
- Fail-closed: geen of ongeldig klant-id, databasefout of ander antwoord dan `False` geeft een weigering.
- De lezer `_lees_stand` is de enige naad voor tests; de rest draait echt.

### [BE-NDS-001-D] Service

- Platformslot: beslist in de schrijfstap (voorwaardelijke upsert), niet in een leesstap ervoor. Een weigering geeft `NoodstopDoorPlatformGezet`.
- Opheffen is fail-closed op de auditregel (`NoodstopAuditMislukt`); zetten blijft best-effort.

### [BE-NDS-001-F] Migratie

- `20261020_tenant_noodstop`, `down_revision` `20261014_pack_activations`. Additief: tabel, unieke `tenant_id`, controle op `reden` (1 tot 500 tekens), vreemde sleutels, RLS-beleid `rls_tenant_noodstop_tenant_isolation`. De `downgrade()` verwijdert de tabel. Raakt geen bestaande data.

### Deuren (zie de architectuurtest voor de volledige lijst)

Broker `execute_tool`, Council `deliberate`, engine `execute_workflow` en `execute_task`, actor `execute_workflow_step`, CVA-actor, brievenverzender, debiteurenopvolging, proactieve scheduler, HITL-goedkeuring, en de chats (CVA, copilot, focus-builder, agentic).

- Workflow-engine: een stop of onleesbare stand zet de uitvoering NIET op FAILED; hij blijft PENDING of RUNNING en wordt hervat (voltooide taken worden overgeslagen).
- CVA-actor: een bericht voor een stilgezette klant wordt weggegooid, geteld (`noodstop_cva_berichten_weggegooid_total`) en gelogd (`noodstop_cva_bericht_weggegooid`, zonder tekst of afzender).
- Proactieve monitoren: `consent_expiry` en `audit_anomaly` draaien door (`blijft_draaien_bij_noodstop`); de Council weigert wat eruit voortkomt (teller `noodstop_geweigerd_total{deur="council"}`).

---

## Foutcodes en configuratie

| Code | Status | Betekenis |
| --- | --- | --- |
| NOODSTOP_DOOR_PLATFORM | 403 | stop van het platform; klant mag niet wijzigen |
| NOODSTOP_NIET_OPGEHEVEN | 503 | opheffing niet in het logboek vastgelegd |
| KLANT_NIET_GEVONDEN | 404 | onbekende klant |
| NOODSTOP_BEHEERDER_VEREIST / NOODSTOP_PLATFORM_VEREIST | 403 | rechten |

Limieten: `noodstop_read_limit` 60 per minuut, `noodstop_write_limit` 10 per minuut. Poolgrootte, overloop, wachttijd en semafoor staan als constanten in `guard.py`.

## Tests

`tests/unit/noodstop/`, `tests/architecture/test_elke_deur_controleert_de_noodstop.py`, `tests/integration/test_noodstop_per_klant_api.py`, `test_noodstop_bewaard_en_gedeeld.py`, `test_noodstop_platform_onder_rls.py`, `test_noodstop_platformslot_race.py`.

## Ronde 3: de modeldeur

Zie docs/backend/review/review-BE-NDS-001.md, secties Ronde 3 en Ronde 4, de poort src/core/shared/model_deur.py en de adapter src/core/noodstop/model_deur.py. Bij een stilgezette klant gaat er via geen enkel pad iets naar een taalmodel; de controle staat op het punt van de aanroep, expliciet per klant of uit de tenantcontext. Ronde 4 en 5: de adapter wordt door elk procesopstartpunt (app, workers, scheduler) geladen met `from src.core.noodstop import model_deur  # noqa: F401`; zonder registratie blijft de deur dicht.

## DSM: elke nieuwe agent_runtime-rand moet met een vermindering komen

De noodstoptak zit in agent_runtime op Ce 258 en Ca 212, dus instabiliteit I = 258/(258+212) = 0,549, tegen de vaste grens I <= 0,55 (`test_agent_runtime_instability_grade_a_plus`). De marge is daarmee ongeveer een rand: nog een nieuwe uitgaande agent_runtime-rand (een import naar een andere bak, ook een `import x`, dat telt de meter sinds `9cc83edc`) maakt I groter dan 0,55 en zet die test rood. Een nieuwe rand moet dus samen met een vermindering komen (een rand die weggaat, of een afhankelijkheid die achter een facade verdwijnt); het Ce-plafond mag niet zomaar mee omhoog. Elke rand sinds 247 staat per bestand, regel en reden in `RANDEN_SINDS_247` in `tests/architecture/test_dsm_008_reclassification.py`, en de core_api-randen sinds 568 in `RANDEN_SINDS_568` in `tests/architecture/test_dsm_grade_a_plus.py`. Besluit regie 2026-10-23: de marge is geaccepteerd.

---

## Trainingssamenvatting

### Een beheerder zet de eigen klant stil

- Actor: beheerder van de klant (ingelogd, met CSRF-token).
- Voorwaarde: de beheerder heeft het recht; de klant komt uit de JWT, nooit uit de aanvraag; een `tenant_id` in de body geeft 422; hoogstens 10 wijzigingen per minuut.
- Actie: `PUT /api/v1/noodstop` met `{"is_stilgezet": true, "reden": "<tekst van 1 tot 500 tekens>"}`.
- Systeemreactie: de stand van de klant wordt bewaard, wie en wanneer komen in het auditlog, en vanaf de volgende deur start geen agent van deze klant nog een actie.
- Succes: 200 met `is_stilgezet`, `reden`, `changed_at` en `door_platform`; elke volgende agentactie of chatbeurt van de klant krijgt een Nederlandse weigering.
- Fout: 403 `NOODSTOP_BEHEERDER_VEREIST` voor een niet-beheerder; 404 `KLANT_NIET_GEVONDEN` als de klant niet bestaat; wijzigingen boven de limiet van 10 per minuut worden geweigerd.
- Uitzonderingen: een lopende actie wordt niet onderbroken, alleen nieuwe starts worden geweigerd; een workflow wordt niet op FAILED gezet maar blijft wachten en wordt na het opheffen hervat; CVA-berichten voor een stilgezette klant worden weggegooid, geteld en gelogd.

### Het platform zet een klant stil, en de klant kan dat niet opheffen

- Actor: platformbeheerder (superuser van het platform).
- Voorwaarde: de doelklant staat in het pad; de service zet de tenantcontext om, anders weigert de rijbeveiliging.
- Actie: `PUT /api/v1/platform/klanten/{tenant_id}/noodstop` met dezelfde body.
- Systeemreactie: dezelfde stand en hetzelfde auditlog, met de markering dat het platform de stop heeft gezet.
- Succes: 200; de beheerder van de klant ziet `door_platform: true`.
- Fout: 403 `NOODSTOP_PLATFORM_VEREIST` voor wie geen platformbeheerder is; 404 `KLANT_NIET_GEVONDEN`; een beheerder van de klant die een platformstop probeert op te heffen krijgt 403 `NOODSTOP_DOOR_PLATFORM`.
- Uitzonderingen: het platformslot wordt beslist in de schrijfstap zelf (een voorwaardelijke upsert), dus twee gelijktijdige aanvragen kunnen het slot niet omzeilen; een opheffing zonder vastgelegde auditregel faalt met 503 `NOODSTOP_NIET_OPGEHEVEN` en de stop blijft staan.

### Een agent of een gebruiker probeert iets te starten voor een stilgezette klant

- Actor: een agent, een workflow, een geplande taak of een gebruiker in een chat voor de klant.
- Voorwaarde: de klant staat stil, of de stand is niet te lezen.
- Actie: elke deur (broker, Council, workflow-engine, actors, scheduler, HITL-goedkeuring, chats en elke modelaanroep) roept eerst `eis_klant_actief` of `eis_chat_actief` aan, via de ene ingang `src/core/services/noodstop_toegang.py`.
- Systeemreactie: de controle leest de stand zonder cache; alleen een expliciete `False` laat door; een stilgezette of onleesbare klant geeft `KlantStilgezet`, waarna de deur op zijn eigen manier weigert met een melding die de klant begrijpt.
- Succes: er gaat geen taalmodelaanroep, geen toolaanroep en geen brief uit voor deze klant.
- Fout: bij een databasefout of een ongeldig klant-id weigert de deur ook (fail-closed).
- Uitzonderingen: de compliancemonitoren (`consent_expiry` en `audit_anomaly`) blijven draaien en wat eruit voortkomt wordt door de Council geweigerd; een aanroep zonder klant en zonder tenant in de context geldt als systeemtaak (bekende beperking, zie de review); een nieuw procesopstartpunt dat de modeldeur niet laadt weigert elke bewaakte aanroep.
