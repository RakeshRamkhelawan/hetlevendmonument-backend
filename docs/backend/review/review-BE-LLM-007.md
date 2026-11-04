STATUS: APPROVED WITH MINOR GAPS
Gate 2 (security-reviewer): ronde 1 NO-GO (twee HOOG), ronde 2 GO. Stap 0 (meting per pad), de bewijzen en wat
nog openstaat staan hieronder.

# Review BE-LLM-007 -- elk pad met klantgegevens volgt de modelkeuze van de klant

Datum:     2026-10-20
Spec:      `docs/backend/features/BE-LLM-007-elk-pad-volgt-de-modelkeuze.md`
Basis:     `origin/develop` `8fdb38cb`, tak `iter/modelkeuze`

---

## Stap 0: wat is gemeten, en hoe

**Commando's.** (1) `ast`-scan van `src/` buiten de LLM-pakketten op de aanroepen `create_llm_client`,
`create_llm_client_from_config`, `get_default_llm_config`, `get_cva_llm_config`, `LLMService(...)`,
`get_llm_service`, `get_llm_provider`, `get_fallback_chain`, `LLMProviderFactory.get_provider`: 51 plaatsen.
(2) Bereikbaarheid: de importgraaf (ook functie-imports) vanaf alle modules die `create_test_app()` laadt; van de
2356 modules in `src/` zijn er 1470 bereikbaar. Deze graaf is een BOVENGRENS voor "bereikbaar": hij ziet
`importlib` met een samengestelde naam niet. (3) Per dood pad de transitieve importeurs, in de guard vastgelegd.

| Pad | Tenantgegevens? | Model nu | Besluit |
|---|---|---|---|
| `agents/base_agent` (`_setup_llm_client`) | ja, `create_agent(tenant_id)` | platformmodel (Ollama of Google) | **deur** |
| `agents/critic_agent` | ja | platformmodel, rechters over deepseek/gemini/openai | **deur** (diversiteit opgegeven) |
| `agents/agent_router_agent` | ja | Google vast + platformketen | **deur** |
| `agents/master_orchestrator_agent` | ja | platformketen | **deur** |
| `agents/learning_loop` | ja (of `None` = globaal) | keten google, anthropic (=Google), mock | **deur** |
| `agents/ultimate_cva/agent` | ja | platformmodel | **deur** |
| `evaluation/evaluation_service` | ja | platformmodel met vast `gemini-1.5-flash` | **deur** |
| `api/v1/ai_copilot/router` (SSE) | ja | platformmodel uit `LLM_PROVIDER` | **deur** |
| `tool_broker/local_registry` (`llm_generate`) | ja | platformmodel | **deur** |
| `learning/services/twin_service_factory` | ja (gedragsdata) | keten uit omgevingssleutels (Claude, Gemini, Ollama), eindigt in vaste tekst | **deur** |
| `api/v1/agentic/router_debug` | n.v.t. | n.v.t. | tenant uit JWT, limiet op `/test` |
| `api/llm_endpoints`, `api/v1/system/llm_health`, `llm_status`, `cva/dependencies.probe_llm_health`, `app_lifespan` | nee | platformmodel | **systeem** (reden in de guard) |
| 18 agentklassen (`analyzer`, `code_agent`, `cva_agent`, `cva/llm_handler`, `ethical/*`, `executor`, `financial`, `marketing`, `product`, `research`, `security`, `vision_synthesis`, `ml_ethics_engine`, ...) | ja, maar zonder aanroeper | via de gedeelde stapel | **dood**: guard met exacte importeurs |
| `services/ai_pack_customizer`, `multi_pack_assembler`, `pack_template_converter`, `shared/cva_llm_config`, `sandbox/doctor_agent`, `agents/router_agent_service` (expliciet Gemini), `api/setup/lifecycle` | ja/nee | platform | **dood** (alleen importeurs buiten de app, of geen) |
| `domains/agentic` `chat_service`, `feature_router`, `simulator_node`, `prompt_mutator` | ja | `create_llm_client("google")` | **dood**: enige gebruiker `src/api/v1/endpoints/agent.py` (niet gemonteerd) of onbereikbare graaf |

**Aanvullingen van de regie (2026-10-20).**
- `src/core/ai/router.py:107` kiest een vast Gemini-model; aanroepers `agents/cva_agent.py:203,244` en
  `agents/code_agent.py:230`, allebei dood. Een test pint die twee aanroepers.
- Twee toegangen tot het taalmodel naast elkaar: `llm/llm_config.py:443` (`GuaranteedLLMService`, voor de
  gezondheid via `app_lifespan` en `api/v1/system`) en `llm/llm_service.py:759` (stapel A, voor
  `api/llm_endpoints` en drie dode pack-modules). Negen bestanden importeren nog uit `llm/llm_service`
  (`api/llm_endpoints`, `workflow/dependencies`, `llm/__init__`, `llm/llm_endpoints`, drie pack-modules,
  `scripts/verify_ollama_cva`). Alleen gemeten; samenvoegen is een eigen brief.
- Digital Twin: er is GEEN bewijs dat hij standaard uit staat (de keten wordt bij elke bouw van de copilot-service
  gemaakt en alleen de gebruikerstoestemming bepaalt of er een suggestie komt); daarom omgebouwd, niet alleen
  bewaakt. De stand "alleen EU = Ollama" botste met het besluit voor Mistral en is losgelaten.

## Gate 2 ronde 1 (security-reviewer, op 8054e064): NO-GO, verwerkt

Gemeten, dan gerepareerd. De reviewer las alleen.

1. **HOOG, `/api/v1/llm/chat|test|status|models` zonder authenticatie en buiten de guard.** Gemeten: `src/core/llm/llm_endpoints.py`
   (met `chat` en een module-level `LLMService()`) wordt alleen gemonteerd door `register_routers` in `api/main.py`; de
   productie-ingang is `src.main:app` (`scripts/entrypoint-prod.sh:76`). `create_test_app()` heeft `/api/v1/llm/chat`
   NIET; de wel aanwezige `/api/v1/llm/models` en `/status` geven zonder token 401 (globale middleware). Dus nu geen open
   route, maar de guard sloot het hele pakket `src/core/llm/` uit. Nu: `llm_endpoints.py` wordt wel gescand
   (`TOCH_GESCAND`), staat als `dood` op de lijst met de reden en de pin `test_de_llm_chatroute_staat_niet_in_de_app`
   (met controlegroep `/models`). Een nieuwe functie in dat bestand laat de guard falen (mutatie ROOD). **Niet gewijzigd:**
   een tweede module-level `LLMService()` in hetzelfde bestand blijft voor de guard onzichtbaar (sleutel `::<module>`).
2. **HOOG, de classificatie `dood` van de agentklassen klopte niet.** De `SubagentLoader` kan klassen op naam laden
   (`/subagents/.../action` met scope `AGENTS_WRITE`, `agent_class(**init_params)`) en `_is_agent_class` kijkt ook naar
   methodenamen. Negen BaseAgent-klassen zijn daarom omgebouwd naar `TenantTaalmodel(self.tenant_id)` (analyzer,
   code, security, executor, research, financial, marketing, product en `CVAAgent._get_llm_client_for_provider`); een
   parametrische test per klasse (ollama-tenant op de HTTP-laag) en vier mutaties ROOD. De overige `dood`-klassen bouwen hun
   model alleen met `create_llm_client("anthropic")` (ValueError sinds deze brief) of `"mock"` (ValueError buiten tests); de
   enige echte restkans is `agents/cva/llm_handler.py` (`get_default_llm_config()` kan Ollama of Google geven). De reden in
   de guard zegt dat nu per bestand, en dat NIET gemeten is of de loader die klassen in productie vindt.
3. **MIDDEL, `router_debug`:** `/test` geeft nu het fouttype terug (was `str(e)`), `/debug` heeft `query` max 1000 tekens.
   Een rate limit per gebruiker is er niet (restrisico, genoemd).
4. **MIDDEL, `llm-switch-provider`:** `require_admin_user` is beheer BINNEN een tenant (gelezen in `api/dependencies.py`),
   terwijl de wissel een gedeelde singleton van het platform omzet. Nu `require_platform_beheerder`
   (`is_platform_superuser`), `mock` wordt buiten tests geweigerd, en de 500-melding en de `llm-test`/metrics-fouten geven
   het fouttype in plaats van `str(e)`.
5. **LAAG, `namaak_toegestaan()` hing aan `TESTING`:** weigert nu ook als `ENVIRONMENT=production`.

## Gate 2 ronde 2 (op 7434f3e9): GO

Geen BLOCKER of HOOG; de bevindingen 1 tot en met 5 van ronde 1 zijn bevestigd dicht. Wat de reviewer bleef noemen, en
dat bewust NIET in deze commit zit (er is geen derde ronde; het hoort in een vervolgbrief):

- **MIDDEL, loader-restkans.** `_is_agent_class` laat elke klasse met `initialize`, `execute` of `get_capabilities` door; dat
  dekt ook `ml_ethics_engine`, `ethical*`, `vision_synthesis`, `ethics_classification_trainer`, `cva/llm_handler` en
  `DoctorAgent`, die nog `create_llm_client(...)` of `get_default_llm_config()` gebruiken. Gemeten: hun `anthropic` en
  `mock` weigeren; echt open blijft `cva/llm_handler` (Ollama of Google bij een sleutel). Niet gemeten of de loader in het
  productie-image iets vindt (`WORKDIR /app`, relatieve scanmappen). Voorstel: een allowlist uit `implemented_agent_keys()` in
  de loader, of ook die klassen aan `TenantTaalmodel` hangen.
- **LAAG:** `CVAAgent.llm_client` wordt door `LLMHandler.__init__` gezet met een platformclient die niets gebruikt
  (`self.llm_client = None` in `cva_agent.py` volstaat); de guard ziet directe clients (`AsyncOpenAI`, `genai.Client`,
  `ChatOpenAI`) niet (alle drie nu dood of embeddings); `llm_switch_provider` logt de wissel niet in de auditketen;
  `llm_status.py:66,116,148` geeft nog `str(e)` terug (achter `require_admin_user`).
- Na de ronde bleek de volledige architectuurronde op 7434f3e9 op een test te falen: `test_admin_routes_hebben_een_rolcontrole`
  kende `require_platform_beheerder` niet als rolcontrole. Toegevoegd aan `ROL_DEPENDENCIES` (strenger dan
  `require_admin_user`); verder niets gewijzigd.

## Bewijs

- Rood voor de wijziging: `tests/unit/llm/test_gedeelde_clientstapel_geen_stille_terugval.py` (7 van 8 rood),
  en de guard vond 51 plaatsen met een lege uitzonderingslijst.
- De padtests (`tests/unit/llm/test_klantpaden_modelkeuze.py`, 15) zijn NA de omzetting geschreven; hun
  rood-bewijs is een mutatie: per pad de tenant vervangen door een andere of `None`, en de deur zelf laten terugvallen
  op de platformstandaard. Resultaat: 11 mutaties, alle GEVANGEN.
- Guard (14 mutaties, allemaal zoals verwacht): nieuw `create_llm_client("google")`, `LLMService()`,
  `get_llm_provider()`, `get_fallback_chain()`, `LLMProviderFactory.get_provider`, `get_default_llm_config()` in een
  klantpad -> ROOD; een extra aanroep in een ANDERE functie van een bestand dat al op de lijst staat -> ROOD; een
  bereikbare importeur voor een dood pad -> ROOD; een nieuwe `route_to_model`-aanroeper -> ROOD; docstring,
  `LLMService.for_tenant`, `TenantTaalmodel` en een aanroep binnen een LLM-pakket -> GROEN; een hernoemde
  vrijgestelde functie -> ROOD (veroudering).

## Gedragswijzigingen die je moet weten

- Een agent uit de fabriek (`create_agent`) krijgt het taalmodel van zijn tenant; bij een storing een fout, niet stil
  `None` of een ander model.
- De criticus beoordeelt met het model van de tenant voor ELKE rechter; de leverancierdiversiteit
  (deepseek/gemini/openai) is bewust opgegeven (die stuurde klantuitvoer naar leveranciers die de klant niet koos).
- De Digital Twin gebruikt het model van de tenant en geeft bij een storing GEEN suggestie (leeg), geen vaste tekst
  van een ander model; de vaste pauzetekst blijft alleen bij een budgetgrens (`hard_cap`, `soft_cap` zonder eigen model).
- `create_llm_client("anthropic")` en `("mock")` buiten tests geven nu een fout; er is geen Anthropic-client.
- `/router/debug/stats` en `/heatmap` vragen nu een ingelogde gebruiker; `/test` weigert meer dan 20 queries.

## Niet opgelost of niet gemeten

- Zie ook de lijst onder Gate 2 ronde 2 hierboven (loader-restkans, directe clients, auditregel voor de providerwissel).

- Echt Mistralverkeer (account 429): alles op de HTTP-laag met een testdubbel.
- De `SubagentLoader` (`scan_directories=["core/agents", "core/subagents", "agents"]`, relatief aan de werkmap) kan
  klassen op naam laden; niet gemeten of dat in productie iets vindt. De dode agentklassen zijn daarom NIET als
  bewezen onbereikbaar te beschouwen, alleen als "geen statische aanroeper"; de gedeelde fabriek weigert zonder
  sleutel, maar een expliciete `create_llm_client("google")` met een Google-sleutel gaat door.
- Een rate limit per gebruiker op `/router/debug/test`.
- Samenvoegen van de twee toegangen (`llm_config` en `llm_service`).
