# BE-LLM-007 -- elk pad met klantgegevens volgt de modelkeuze van de klant

Datum:     2026-10-20
Fase:      Pilot december 2026, ADR-041 blokkade B14 (vervolg op BE-LLM-006)
Brief:     `docs/agent-briefs/generated/2026-10-20-sprint-dag-elk-pad-volgt-de-modelkeuze.md`
Basis:     `origin/develop` `8fdb38cb`

---

## 1. Waarom deze knip bestaat

BE-LLM-006 haalde DeepSeek uit elk platformpad en zette de zeven gemelde paden achter een deur
(`TenantTaalmodel`, `src/core/services/llm/tenant_deur.py`). Wat bleef staan (eigen melding 2026-10-19, punt 2
"niet opgelost", plus de ADR's 025/026/032): paden die nog het PLATFORMmodel gebruiken, of een eigen client met
een eigen leverancier, terwijl de klant een eigen model (`ollama`) of het gehuurde EU-model (`mistral`) koos.

Gemeten op `8fdb38cb` met `ast`: **51 plaatsen** buiten de LLM-pakketten bouwen of kiezen een taalmodel langs de
deur om (`create_llm_client`, `create_llm_client_from_config`, `get_default_llm_config`, `LLMService()`,
`get_llm_service`, `get_llm_provider`, `get_fallback_chain`, `LLMProviderFactory.get_provider`).

## 2. Wat er nu gebeurt

**De gedeelde clientstapel valt niet meer stil terug** (`src/core/shared/llm_client.py`, `src/core/llm/llm_client.py`):

| Was | Nu |
|---|---|
| `create_llm_client("anthropic")` gaf een GOOGLE-client ("fallback to Google") | `ValueError` |
| `create_llm_client("google")` zonder sleutel viel door naar Google, Local, mock | `ValueError` |
| een onbekende naam gaf een namaakclient | `ValueError` |
| `create_llm_client("mock")` werkte ook buiten tests | `ValueError` buiten tests (`namaak_toegestaan()`) |
| `get_default_llm_config()` (stapel A) gaf bij alleen een OpenAI-sleutel of zonder iets een mockconfig | `ValueError` buiten tests |

**Omgebouwd naar de deur** (met de tenant van de agent of het verzoek): `BaseAgent`-fabriek
(`create_agent` -> `_setup_llm_client(tenant_id)`), `CriticAgent` (alle rechters op het tenantmodel, de lijst
`judge_provider_types` is vervallen), `AgentRouterAgent` (stond op Google) en zijn routering,
`MasterOrchestratorAgent` (planning), `LearningLoop`, `UltimateCVAAgent`, `EvaluationService` (vast
`gemini-1.5-flash` weg; tenant via een `ContextVar` die `asyncio.to_thread` meekopieert), de AI-copilot SSE-route,
het `llm_generate`-tool van de `LocalToolRegistry` (tenant uit de verzoekcontext) en de **Digital Twin**
(`TenantSuggestionProvider`; de keten kiest niet meer uit omgevingssleutels, `eu_only` verandert de keuze niet
meer omdat beide keuzes EU zijn; `hard_cap` en `soft_cap` blijven een budgetbesluit met de vaste pauzetekst).

**De deur kan meer vormen aanbieden** zodat die paden niets van hun aanroepcode hoeven te wijzigen:
`text_completion`, `generate`, `generate_with_tools`, `initialize`, `get_service_status`, `default_provider`,
`tekst_met_gebruik` (tokens voor de kostenregistratie van de twin), en `keuze_van_de_tenant(tenant_id)`.

**Wat NIET is omgebouwd en waarom** staat in `tests/architecture/test_klantpaden_volgen_de_modelkeuze.py`, per
`bestand::functie`:

- `systeem`: geen tenantgegevens (modellijst en status, gezondheid, beheerdersendpoints, opstart);
- `dood`: geen aanroeper in een gemonteerde route of actor (de transitieve importeurs zijn zelf niet
  bereikbaar vanaf `create_test_app`, gemeten 2026-10-20). Per dood pad staat de exacte set importeurs vast; een
  nieuwe importeur laat de test falen.

**Vast Gemini-model in `src/core/ai/router.py`** (`route_to_model`): alleen `agents/cva_agent.py` en
`agents/code_agent.py` roepen het aan, allebei dode paden; de test pint die twee aanroepers.

## 3. Laag punt

`router_debug` (`/stats`, `/heatmap`, `/test`): de tenant komt uit de JWT, niet uit de querystring (NOOIT-lijst);
`/test` neemt maximaal 20 queries van maximaal 1000 tekens.

## 4. Niet gedaan

- Echt verkeer naar Mistral (het account geeft 429); alles is bewezen op de HTTP-laag met een testdubbel.
- Een rate limit per gebruiker op `/router/debug/test` (alleen een limiet op het aantal queries).
- De dode agentklassen zijn niet omgebouwd. De `SubagentLoader` (`scan_directories` relatief, `core/agents`) kan
  klassen op naam laden; NIET gemeten of dat in productie iets vindt. Ze kunnen zonder sleutel nergens heen
  (de fabriek weigert), maar met een Google-sleutel gaat een expliciete `create_llm_client("google")` wel door.
- Twee toegangen tot het taalmodel naast elkaar (`llm/llm_config.py::get_llm_service` voor de gezondheid en
  `llm/llm_service.py::get_llm_service` voor stapel A): alleen gemeten, zie het reviewdocument.

## 5. Bewaking

- `tests/architecture/test_klantpaden_volgen_de_modelkeuze.py` (AST; uitzonderingen met datum, categorie, reden;
  staleness; transitieve importeurs van dode paden vast; vaste Gemini-keuze).
- `tests/unit/llm/test_klantpaden_modelkeuze.py` (15 tests, ollama-tenant op de HTTP-laag, en een storing = fout).
- `tests/unit/llm/test_gedeelde_clientstapel_geen_stille_terugval.py`.
- `tests/unit/api/test_router_debug_tenant_uit_jwt.py`.

## Trainingssamenvatting

- **Actor:** een agent, een route of een achtergrondtaak die namens een tenant een taalmodel nodig heeft (geen
  menselijke actor).
- **Voorwaarde:** de tenant heeft in `tenants.settings["llm_provider"]` niets, `mistral` of `ollama` staan; de
  bijbehorende sleutel of het lokale model is beschikbaar.
- **Actie:** het pad vraagt zijn model op via `TenantTaalmodel(tenant_id)`.
- **Systeemreactie:** de keuze van de klant wordt gevolgd (zijn eigen eindpunten, anders Mistral of zijn lokale
  model); de tenant komt uit de agent, de JWT of de verzoekcontext, nooit uit de invoer.
- **Succes:** het antwoord komt van de gekozen verwerker.
- **Fout:** een storing of een ontbrekende configuratie geeft een zichtbare fout (alleen het fouttype naar de
  gebruiker, de volledige fout in het logboek); er wordt nooit op Google, Anthropic of een namaakmodel
  teruggevallen.
- **Uitzonderingen:** paden zonder tenantgegevens (gezondheid, opstart, modellijst) gebruiken het platformmodel en
  staan met een reden op de lijst van de guard; de Digital Twin geeft bij een storing GEEN suggestie en toont alleen bij
  een budgetgrens de vaste pauzetekst.
