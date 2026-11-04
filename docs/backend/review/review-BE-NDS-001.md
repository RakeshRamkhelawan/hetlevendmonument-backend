STATUS: APPROVED

Besluit regie (sessie sanskritisetu-org-4f), 2026-10-25: noodstop goedgekeurd op `42c7b906`. Onderbouwing: Gate 2 in vier rondes (hieronder) en de gerichte hertoets door een security-reviewer op de facade `noodstop_toegang.py` en de migratievolgorde (2026-10-24, GO op beide onderwerpen; zie de sectie Afronding onderaan).

# Review BE-NDS-001: noodstop per klant (ADR-036 OP-03)

Spec: `docs/backend/features/BE-NDS-001-noodstop-per-klant.md`

## Gate 2, ronde 1 (CHANGES_REQUESTED op fef84ee0)

Besluiten van de gebruiker: A (chat valt onder de noodstop), B (compliance-monitoren draaien door), C (weggegooide CVA-berichten tellen en loggen).

| # | Bevinding | Afhandeling | Test |
|---|-----------|-------------|------|
| 1 | `volg_debiteuren_op_async` omzeilde de noodstop | Per kandidaat `klant_staat_stil`; dossier blijft `herinnerd`; inventaris per bestand::functie | `tests/unit/noodstop/test_debiteuren_opvolgen_deur.py`, `tests/architecture/test_elke_deur_controleert_de_noodstop.py` |
| 2 | Race met platformslot | Voorwaardelijke upsert (`ON CONFLICT DO UPDATE ... WHERE`); 0 rijen geeft `NoodstopDoorPlatformGezet` | `tests/integration/test_noodstop_platformslot_race.py` |
| 3 | Poolloze engine per controle (~109 ms mediaan) | Gedeelde kleine pool per event loop; actorpad gebruikt eigen run-engine achter een semafoor | `tests/unit/noodstop/test_guard_verbinding.py`; meting: mediaan 108,7 ms naar 16,3 ms |
| 4 | `KlantStilgezet` zette de workflow definitief op FAILED | Aparte `except`, uitvoering blijft PENDING/RUNNING en wordt hervat | `tests/unit/noodstop/test_deur_workflow_engine.py` |
| 5 | Opheffen zonder harde audit | Auditregel in dezelfde transactie, fail-closed (`NoodstopAuditMislukt`, HTTP 503) | `tests/unit/noodstop/test_noodstop_service_opheffen.py` |
| 6 | Council-weigering zonder teller | Teller `noodstop_geweigerd_total{deur="council"}` en logregel | `tests/unit/noodstop/test_deuren_broker_council.py` |
| 7 | `_roept_controle_aan` te slap | Controle moet voor de eerste actie staan, niet in except/finally/dode tak; 7 zelftests | architectuurtest |
| A | Chat | Guards in cva_service, copilot, agentic chat_service, agent endpoint, focus-builder websocket | `tests/unit/noodstop/test_chat_deuren.py` |
| B | Monitoren | `blijft_draaien_bij_noodstop` op consent_expiry en audit_anomaly, met reden | `tests/unit/noodstop/test_monitoren_compliance_draaien_door.py` |
| C | CVA | Teller + logregel + best_effort auditregel per weggegooid bericht | `tests/unit/noodstop/test_cva_weggegooid_geteld.py` |

## Bekende beperkingen

- Modelpaden die geen chat zijn (focus_suggestion_service, workflow_generator_service, crag_graph, agents, focus_generator en de rest) staan sinds ronde 3 onder dezelfde noodstop, op het punt van de modelaanroep (zie Ronde 3). Sinds ronde 4 wordt de controle geladen door elk procesopstartpunt met een `from ... import` op modulenivo (zie Ronde 4 en 5). Restrisico: een client zonder expliciete klant en zonder tenant in de context (een actor die `set_tenant_id` niet aanroept) loopt door als systeemtaak.
- Een lopende actie wordt niet onderbroken; de noodstop werkt vanaf de volgende deur.
- Teller is een totaal per deur; per klant staan alleen de auditregels.
- Een uitvoering die niemand hervat blijft RUNNING (de toestandsmachine heeft geen weg terug naar PENDING).
- CVA-berichten worden weggegooid, niet in de wachtrij gezet.
- Latentie in het actorpad is niet gemeten.

## Open

Niets meer openstaand voor deze feature. De rondes 2 tot en met 5 staan hieronder; de afronding van 2026-10-24 en het besluit van de regie staan in de sectie Afronding onderaan.
## DSM-plafonds (bewuste verschuiving)

- agent_runtime Ce 245 -> 247 en core_api fan-out 565 -> 566: elke chat-ingang moet de stand zelf controleren (besluit A); een facade zou de rand alleen verbergen. De hulpfunctie voor weggegooide CVA-berichten staat in src/core/noodstop/weggegooid.py zodat de actor geen extra governance-rand krijgt (agent_runtime -> governance blijft 9).
- ADR-036 open-items: 74 voor, 74 na (netto 0, OP-03 blijft OPEN).


## Ronde 3: geen klantgegevens naar een taalmodel bij een stilgezette klant (besluit van de gebruiker)

Het principe van besluit A geldt breed. De controle staat daarom op het punt van de modelaanroep en niet in de aanroepers. Code: de poort `src/core/shared/model_deur.py` (decorators en haken, alleen standaardbibliotheek) en de adapter `src/core/noodstop/model_deur.py` (de echte controle). De klant is expliciet (`noodstop_tenant_id` van `TenantTaalmodel` en `LLMService.for_tenant`) of komt uit de tenantcontext. Zonder klant is het een systeemtaak en loopt de aanroep door. Met een klant maar zonder leesbare stand weigert de aanroep (fail-closed). Elke weigering is geteld (`noodstop_geweigerd_total{deur="model"}`) en gelogd.

Controleplekken:

| Stapel | Plek | Hoe |
|---|---|---|
| B `services/llm` | `LLMProvider` (base.py) | `__init_subclass__` bewaakt generate, stream, get_embeddings van elke provider |
| B | `LLMService` (service.py) en `TenantTaalmodel` (tenant_deur.py) | expliciete klant, `for_tenant` zet `noodstop_tenant_id` |
| A `llm` | `LLMClient` (llm_client.py) | `__init_subclass__` voor chat_completion, text_completion, complete_json, generate_response, chat, stream_response, en de basis-`generate_response` |
| gedeelde stapel | `LLMClient` (shared/llm_client.py) | `__init_subclass__` |
| E `als` | `LLMProvider` (als/llm_integration/providers.py) | `__init_subclass__` op generate |
| los | fallback-keten, embeddings, leerproviders, lokaal model, Ollama-client, routering, LLMService (A), GuaranteedLLMService, strategieclient, workflow-provider | `@bewaakt_model_aanroep` |

Architectuurtest: `tests/architecture/test_elk_modelpad_controleert_de_noodstop.py`. Een bestand met een model-SDK of modeladres dat in geen inventaris of vrijstelling staat faalt, en elke modelmethode in een geinventariseerd bestand moet bewaakt zijn.

Vrijgesteld (geen klantgegevens of geen taalmodel): intelligent_router.py (alleen adressen in configuratie), monitoring/health_checks.py en services/setup_service.py (GET op de modellijst), typing/optional_imports.py.

Overhead gemeten: mediaan 9,1 ms, p95 14,2 ms per bewaakte aanroep (eerste aanroep in een proces 233 ms, bouw van de kleine pool). Geen cache.

Beperking: een client zonder expliciete klant en zonder tenant in de context wordt als systeemtaak behandeld. Een actor die geen `set_tenant_id` aanroept en een stapel-A-, gedeelde of E-client gebruikt, is dus niet gedekt; de agentdeur en `TenantTaalmodel` zijn dat wel. Ook niet gedekt: een zoekdienst (Tavily in crag_graph), die geen taalmodel is.

Ook in ronde 3: de pin in `test_agentic_alembic_chain_complete.py` stond nog op de vorige head (ronde 1 voegde de migratie toe); bijgewerkt naar 20261020_tenant_noodstop.


## Ronde 4: de adapter wordt bij het opstarten geladen (optie A, blokkade P3)

- De poort laadde de adapter eerst zelf met `importlib` (een tekenreeks-import). De DSM-meter ziet die rand niet, terwijl hij echt is, en dat botste met de Gate 2-lijn van BE-LLM-004 in `LLMService.for_tenant`. De `importlib`-import is uit `src/core/shared/model_deur.py` verwijderd.
- Elk procesopstartpunt importeert nu de adapter op modulenivo (in ronde 4 als `import src.core.noodstop.model_deur`, sinds ronde 5 als `from src.core.noodstop import model_deur`): `src/main.py` (app), `src/workers/workflow_worker.py` (dramatiq-broker; `src.workers.actors` draait in hetzelfde proces), `src/workers/scheduler.py`, `src/core/learning/worker.py` en `src/core/als/bonlezer/worker.py`.
- Zonder registratie weigert de poort elke bewaakte aanroep met `ModelDeurNietBeschikbaar` (fail-closed), ook zonder klant. Een nieuw opstartpunt dat de import vergeet, faalt dus hard in plaats van stil open te staan.
- Architectuurtest `tests/architecture/test_modeldeur_adapter_wordt_bij_het_opstarten_geladen.py`: (1) elk opstartpunt uit Dockerfile, compose, entrypoint-scripts en CD-workflows importeert de adapter op modulenivo (of staat in `GELADEN_DOOR` met reden); (2) de poort gebruikt geen `importlib`, `import_module` of `__import__`.
- Samengevoegd met `origin/develop` (`d054a114`, BE-LLM-007). De nieuwe `TenantTaalmodel`-vormen (`text_completion`, `generate`, `generate_with_tools`) zijn bewaakt of lopen via een bewaakte methode.
- Migratievolgorde: `20261020_tenant_noodstop` hangt nu aan `20261020_tenant_ap_verbindingen`; `alembic heads` geeft een kop.
- Nieuwe modelpaden uit develop (BE-LLM-007) zijn ingedeeld en bewaakt door de architectuurtest: `TenantTaalmodel.text_completion`, `generate_with_tools` en `tekst_met_gebruik`, en `TenantSuggestionProvider.suggest` (de provider kent zijn klant zelf via `noodstop_tenant_id`, dus een stop geeft een harde weigering en geen stille lege suggestie). `src/core/tasks/dramatiq_broker.py` staat als vrijgesteld (de broker en de decorator, geen actor).
- DSM-plafonds bij de samenvoeging, gemeten met een per-bestand-lijst (zie de commentaarblokken in de tests): agent_runtime Ce 247 -> 253 (develop alleen 243 plus de tien noodstop-importstatements van ronde 1 en 2) en core_api fan-out 566 -> 568 (twee paren die al in het plafond van de noodstoptak zaten, die van develop is 566). Elke tak paste apart; de som past niet. Deze plafonds zijn gemeten zonder de opstart-imports van ronde 4 en 5 (zie Ronde 5 hieronder voor wat die toevoegen).
- Ronde 5 (variant A van de hertoets): de opstartpunten schrijven `from src.core.noodstop import model_deur  # noqa: F401`, en de architectuurtest accepteert alleen die vorm. Reden: de DSM-meter (`scripts/dsm_full_analysis.py`) telt `ast.ImportFrom` en telt `import x` (`ast.Import`) NIET; een kale `import src.core.noodstop.model_deur` liet een echte afhankelijkheid onzichtbaar (op develop staan al ongeveer 100 `import src.`-regels die de meter niet ziet). Dat de meter `import x` niet telt is een eigen gebrek met een eigen opdracht (`2026-10-22-sprint-dag-dsm-meter-telt-ook-import-x`) en is in deze tak NIET opgelost. Dat gebrek is inmiddels opgelost in `9cc83edc` (de meter telt nu `import x` gelijk aan `from x import y`) en die meter is hier samengevoegd. Gemeten met de nieuwe meter: agent_runtime Ce 258, Ca 212, I = 0,549 (grens 0,55, ongewijzigd); core_api fan-out 570. De drie opstartpunten in agent_runtime (`src/core/als/bonlezer/worker.py`, `src/core/learning/worker.py`, `src/workers/scheduler.py`, elk naar `src.core.noodstop`) tellen mee; `src/main.py` en `src/workers/workflow_worker.py` niet. Het Ce-plafond staat op de gemeten waarde, met per rand een regel in `RANDEN_SINDS_247` in `tests/architecture/test_dsm_008_reclassification.py`.
- Typering: `bewaakt_model_aanroep` geeft `CoroutineType[object, object, R]` terug in plaats van `Awaitable[R]`, zodat de Protocols uit develop (`ChatTaalmodel`, `ILLMSuggestionProvider`) de bewaakte methoden blijven accepteren.

## Afronding (2026-10-24, bouwer 60/8c; besluit regie 2026-10-25)

- Samengevoegd: `iter/crediteuren` `ce0e395a` (bevat `origin/develop` `69f433cc` en `iter/schemadrift` `b10b20eb`) in de noodstoptak, merge-commit `c07bf929`; daarna `42c7b906`.
- De enkele ingang `src/core/services/noodstop_toegang.py` is toegepast (alleen aliassen op de guard en de teller), met de architectuurtest `test_agent_runtime_importeert_noodstop_alleen_via_de_ingang.py` (uitzonderingen per bestand::regel, staleness-test) en `test_noodstop_toegang_is_alleen_aliassen.py` (elke alias is hetzelfde object als in guard en metrics, de facade definieert geen functie of klasse). Mutatiebewijs: een directe import in een agent_runtime-bestand, een ingang die de guard niet doorgeeft en een deur zonder controle worden alle drie rood en zijn teruggezet.
- Migratievolgorde: `down_revision` van `20261020_tenant_noodstop` is `20261024_payables_rls`; de keten is `20261020_tenant_ap_verbindingen` -> `20261023_schemadrift_schadelijk` -> `20261024_payables_rls` -> `20261020_tenant_noodstop`; `alembic heads` geeft een kop. Op een wegwerpdatabase gemeten: upgrade, downgrade -1 (versie `20261024_payables_rls`, tabel weg, `payables` intact) en weer upgrade (tabel en een beleid). Interlock 1: alleen de volgorde veranderde.
- Grenzen: gemeten met de eigen meter van de boom agent_runtime Ce 250, Ca 208, I = 0,5459 (grens 0,55 ongewijzigd).
- Typering van `bewaakt_model_aanroep` aangepast: een gebonden TypeVar met `cast` laat de handtekening van de bewaakte functie zoals ze was (de oude vorm gaf 97 fouten in de mypy-audit met de vastgepinde versie; `Awaitable[R]` brak de Protocols). Drie keer "does not explicitly export" opgelost met expliciete her-exports in `tool_broker/service.py` en `governance/noodstop_service.py`. Gate 3 daarna: ruff, pyright en mypy-audit 0, Any-ratel gelijk aan de baseline.
- Een testfix buiten deze feature die de commit nodig had: `test_worker_initialiseert_de_database.py` zette geen `REDIS_URL` in zijn subproces en faalde los gedraaid in elke boom.
- Gerichte hertoets security-reviewer, alleen facade en migratievolgorde: GO op beide. Twee lage aanbevelingen zijn bewust niet gedaan en krijgen een vervolgbrief na de push: een deur die lokaal een eigen `eis_klant_actief` definieert blijft groen in de deurtest; de sleutel van de uitzonderingslijst `bestand::regel` kan op dezelfde regel een directe guard-import verbergen (beter: `bestand::modulenaam`).
- Volledige ronde op `c07bf929`: 27651 geslaagd, 1 mislukt; die ene (`test_focus_builder_observer.py`, `HoofdsleutelOntbreekt`) was een bestaande volgorde-afhankelijkheid die uitrol-nazorg-2 oplost met de vaste testsleutel.
- Besluit regie 2026-10-25: goedgekeurd op `42c7b906`.
