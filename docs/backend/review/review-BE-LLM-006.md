STATUS: APPROVED WITH MINOR GAPS
Twee gerichte reviews op de Mistral-brief en een derde ronde op de brief "DeepSeek overal eruit".
ff48c72d kreeg NO-GO met vijf punten; 5afce2e6 kreeg GO. Daarna zijn de overige DeepSeek-paden
dichtgezet (iter/geendeepseek). Wat niet gemeten of niet opgelost is, staat onderaan.

# Review BE-LLM-006 -- Mistral (EU) als standaardmodel, DeepSeek eruit

Datum:     2026-10-19
Spec:      `docs/backend/features/BE-LLM-006-mistral-eu-standaardmodel.md`
Reviewers: gerichte review door de regie (sessie sanskritisetu-org-90), twee rondes
Basis:     develop `9c58df3d`

---

## Review 1 -- ff48c72d: NO-GO

De commit zette Mistral als standaard en haalde DeepSeek uit de platformketens. De regie vond vijf
punten die een klant of een beheerder zouden raken:

1. **Stil namaakmodel buiten productie.** `LLMService.__init__` maakte bij een `ValueError` een
   MockProvider met alleen een waarschuwing; staging is "niet productie", dus een klant daar kreeg
   verzonnen antwoorden. Nu: alleen onder `TESTING` (met een `[MOCK]`-melding), anders een fout.
2. **`api/v1/tenant_management/` zou de taalmodelkeuze kunnen wissen.** Eigen `TenantUpdate` met een los
   `settings`-veld. Gemeten: 0 routes uit die map in de echte app (930 routes), dus nu geen gat, maar een
   guard faalt zodra dat verandert (`tests/architecture/test_tenant_management_is_niet_bereikbaar.py`).
3. **`LLMProviderConfig.api_key` stond in `repr`.** Nu `repr=False`.
4. **`LLM_API_KEY` in de dev-compose.** Eruit.
5. **Besluit over `tenants.externe_providers_toegestaan`.** Die vlag blokkeert NIET Mistral: Mistral is de
   platformverwerker (Rakesh 2026-10-15); de vlag blijft voor klant-eigen eindpunten. Vastgelegd in de
   docstrings en in de spec.

## Review 2 -- 5afce2e6: GO

Alle vijf opgelost met een test per punt. Gemeten: volledige `tests/architecture` serieel op 5afce2e6:
7451 passed, 1 skipped in 1086,07 s (0:18:06).

## Ronde 3 -- iter/geendeepseek (brief 2026-10-19 "DeepSeek overal eruit")

Wat de regie extra vroeg, en wat ervan is gedaan:

- **2a (MIDDEL):** `ProviderFactory.create_from_env` viel zonder `LLM_PROVIDER` stil terug op `mock`.
  Nu: zonder sleutel en buiten tests een fout; met `MISTRAL_API_KEY` wordt het Mistral; een
  uitdrukkelijke `LLM_PROVIDER=mock` blijft werken. `LLM_PROVIDER=deepseek` zonder Mistralsleutel is een
  fout (was: DeepSeek gebouwd). Rode test eerst: `tests/unit/llm/test_platformpaden_zonder_deepseek.py`
  (13 tests, alle 13 ROOD voor de wijziging).
- **1b (LAAG):** de guard op `tenant_management` had geen controlegroep. Nu: een test die eist dat er
  routes uit `src.core.api.v1.tenants` in de echte app staan.
- **`src/core/llm/llm_endpoints.py:18` (module-level `LLMService()`):** gemeten zonder enige sleutel en met
  `LLM_PROVIDER` en `TESTING` uit de omgeving: de import slaagt, `initialized` is `False`. De constructor
  is lazy; de providers komen pas in `initialize()`. De app start dus wel. Zonder provider geeft een
  aanroep daarna een duidelijke fout (geen namaakmodel).
- **De zeven paden en een deel van de overige platformpaden:** lopen nu via een deur
  (`TenantTaalmodel`, `src/core/services/llm/tenant_deur.py`) met de keuze van de klant; geen eigen
  client met een eigen leverancier meer. Per pad een test op de HTTP-laag
  (`tests/unit/llm/test_klantverzoeken_per_pad.py`, 21 tests) en een integratietest met echte
  tenantrijen (`tests/integration/test_een_deur_naar_het_taalmodel.py`, 3 tests).
- **Gedragswijzigingen die je moet weten:**
  - de CVA-chat gebruikt het model van de tenant; een `model=` van het verzoek kiest niets meer (de
    lijst van drie Gemini-modellen is weg: die omzeilde de keuze van de klant);
  - de copilot gebruikt het model van de tenant; de terugval op `LLM_FALLBACK_PROVIDER` is uit de code
    (die stuurde klantgegevens naar een tweede leverancier). De auditnaam van het model is nu het gekozen
    model, niet meer vast `deepseek-chat-v3.1`;
  - `ExecutionFeedbackAgent` en `WorkflowOrchestratorAgent` gebruikten altijd een kapot pad
    (`async_prompt` bestond niet op de gedeelde clients) en gaven dus altijd de vaste terugvalsuggesties;
    ze gebruiken nu echt het model;
  - `LocalClient` valt bij een storing niet meer terug op DeepSeek of Gemini en meldt `success=False`;
  - de twee `suggest`-endpoints van de workflowbouwer sturen de prompt niet meer naar een model (het
    antwoord werd nergens gebruikt);
  - productiestart eiste `DEEPSEEK_API_KEY`; nu `MISTRAL_API_KEY` (zie "Niet opgelost" over de
    ingesprongen debugcontrole in dezelfde functie).

## Gate 2 op 252e5dfc (security-reviewer, ronde 1): NO-GO, daarna gerepareerd

De reviewer las alleen (geen tests). Eerst zelf nagemeten, dan gerepareerd, elk met een test en een mutatie:

1. **HOOG, `GuaranteedLLMService` (`llm/llm_config.py`) bouwde DeepSeek als eerste keuze** en is bereikbaar
   via `/llm-test` en de providerwissel van `api/v1/system/llm_health.py`. De guard zag het niet: de klasse
   stond in een woordenboek, geen `ast.Call`. Nu: DeepSeek uit `is_configured`, `available_providers`,
   de prioriteit en de providertabel. De guard toetst nu ook een VERWIJZING (import, naam, attribuut), niet
   alleen een aanroep.
2. **HOOG, registry-pad:** `LLMProviderFactory.get_provider(provider_type="deepseek")` ging via
   `ProviderRegistry`. Aanroeper: `critic_agent` met `judge_provider_types: deepseek` in
   `config/agents/critic_agent.yaml`. Nu: `get_provider` weigert elke naam uit
   `LEVERANCIERS_ZONDER_VERWERKERSOVEREENKOMST`, de yaml noemt `mistral`, en `get_llm_provider` staat in
   de fabrieken die de guard toetst.
3. **HOOG, tenant uit een queryparameter:** `POST /router/test` (`router_debug.py`) had geen authenticatie en
   nam `tenant_id` uit de querystring (bestond al; de tenantdeur in laag 3 maakte het erger). Nu: de
   tenant komt uit de JWT.
4. **MIDDEL, proactieve copilot zonder tenantcontext:** `_build_copilot_service` riep al voor deze brief
   `require_tenant_id()` aan voor de `AIContextEngine`; mijn `TenantTaalmodel(require_tenant_id())` voegt
   geen nieuwe afhankelijkheid toe. NIET gewijzigd, NIET gemeten of de proactieve taak elders een
   context zet.
5. **MIDDEL, `MISTRAL_API_KEY` wordt nergens uitgerold:** klopt (CD en prod-compose zetten alleen
   DeepSeek). Gemeld aan de regie als voorwaarde voor een deploy (interlock 2, niet aangeraakt).
   `validate_configuration()` is volgens de reviewer geen startblokkade; de ingesprongen debugcontrole
   staat er nog.
6. **MIDDEL, gedeelde clientstapel valt nog terug op mock en Google:** NIET opgelost, buiten deze brief
   (agents `base_agent`, `financial_agent`, `marketing_agent`, `product_agent`, `cva/llm_handler` en
   `get_default_llm_config`). Geen DeepSeek, wel niet de keuze van de tenant: eigen brief.
7. **LAAG, foutteksten naar de gebruiker:** `TenantTaalmodel` geeft nu alleen het TYPE van de fout terug;
   de volledige tekst staat in het logboek.
8. **LAAG, auditlabel:** de standaard `model_id` van `LLMHandler` is nu `onbekend` in plaats van
   `deepseek-chat-v3.1`.

Een tweede bevinding uit de brede testrun: `tests/unit/test_llm_service.py` en
`tests/unit/services/llm/test_no_mock_in_production.py` faalden in een brede run omdat de omgeving dan
`LLM_PROVIDER=Mistral` en een sleutel bevatte (bron niet vastgesteld; een lokaal dotenv-bestand of een
eerdere test). Ze scrubben die twee variabelen nu zelf.

## Gate 2 ronde 2 (e4414820): GO

1 tot en met 3, 7 en 8 bevestigd dicht. Twee aanbevelingen opgepakt (daarna ronde GEEN derde review, de
ronde-cap): (A) de weigering in `provider_factory.get_provider` was hoofdlettergevoelig terwijl de registry
`name.lower()` doet, dus `"DeepSeek"` uit een configuratiebestand passeerde: nu `strip().lower()` eerst,
test met vier schrijfwijzen, mutatie ROOD; (guard) een enumlid `LLMProvider.DEEPSEEK` als `provider=` werd
niet gezien: nu wel, mutatie ROOD. NIET opgepakt (laag): `POST /router/test` heeft geen limiet op het aantal
queries, en `/stats` en `/heatmap` in `router_debug.py` nemen `tenant_id` nog uit de querystring (vaste
placeholdergetallen, nu geen lek, maar het patroon van de NOOIT-lijst); `GuaranteedLLMService` kent Google
en een stille mock buiten tests (punt 6); `tool_broker/local_registry.py:213,259` geeft `str(e)` terug.

## Mutatiebewijs geen-DeepSeek-guard

Guard: `tests/architecture/test_geen_deepseek_voor_klantgegevens.py` (AST, sleutel `bestand::functie`,
negen gedateerde uitzonderingen, veroudering-test). Elke mutatie is aangebracht in de productiecode, de
test draaide, en het bestand is teruggezet vanuit een kopie (werkboom daarna ongewijzigd).

| Mutatie | Verwacht | Uitkomst |
|---|---|---|
| nieuwe `DeepSeekProvider()` in een schoon bestand | ROOD | ROOD |
| nieuw adres `https://api.deepseek.com/v1` | ROOD | ROOD |
| nieuw `create_llm_client("deepseek")` | ROOD | ROOD |
| nieuw `LLMService(provider="qwen")` | ROOD | ROOD |
| nieuw Dashscope-adres (Qwen) | ROOD | ROOD |
| `DeepSeekClient(...)` in een ANDERE functie van `llm/llm_client.py` (staat al op de lijst) | ROOD | ROOD |
| idem in `shared/llm_client.py` | ROOD | ROOD |
| docstring die `api.deepseek.com` noemt | GROEN | GROEN |
| `provider="DeepSeek"` buiten een fabrieksaanroep (modelkaart) | GROEN | GROEN |
| ongewijzigd bestand | GROEN | GROEN |
| vrijgestelde klasse hernoemd (veroudering) | ROOD | ROOD |
| verwijzing via woordenboek `{'d': DeepSeekProvider}` in een schoon bestand | ROOD | ROOD |
| `import DeepSeekClient` in een schoon bestand | ROOD | ROOD |
| `get_llm_provider(provider_type='deepseek')` | ROOD | ROOD |
| verwijzing in een ANDERE functie van `services/llm/factory.py` (staat al op de lijst) | ROOD | ROOD |

Overige mutaties (allemaal GEVANGEN): de deur valt terug op de platformstandaard (integratietest);
`CVAService._llm_voor` en de CVA-dependency vallen terug op `LLMService()`; de copilot-auditnaam
verdwijnt; elke van de drie CRAG-knopen krijgt `None` als tenant; `create_from_env` valt weer terug op
mock (2a); DeepSeek zonder sleutel wordt weer gebouwd; `create_llm_client_from_config` bouwt weer een
DeepSeekclient; `LocalClient` meldt weer succes; de controlegroep (1b) krijgt een verkeerd voorvoegsel.
Een eerste mutatie op `transform_query` van CRAG bleef GROEN: mijn test dekte alleen
`grade_documents`. Twee tests erbij (`transform_query`, `generate`); herhaald: beide ROOD.

## Niet opgelost of niet gemeten (met reden)

- **Geen echt verkeer naar Mistral gemeten.** Het account geeft 429 (limiet 0 per minuut). Alles is
  bewezen op de HTTP-laag met een testdubbel. Het acceptatiebewijs met echte antwoorden wacht op het
  actieve account van Rakesh.
- **Blijven op het platformmodel, niet per tenant** (DeepSeek is daar wel onbereikbaar):
  `master_orchestrator_agent`, `agent_router_agent` (beide via `get_fallback_chain()`),
  `router_agent_service` (een uitdrukkelijk Gemini-pad; staat al als "verdwijnt in fase 4" genoemd),
  `evaluation_service`, `tool_broker/local_registry`, `ultimate_cva`, `sandbox/doctor_agent`. De
  geheugen-agent en laag 3 zijn WEL omgezet. Dit is een eigen brief.
- **`get_cva_llm_config` en `get_default_llm_config`** kiezen buiten DeepSeek nog Ollama of Google op
  basis van sleutels in de omgeving; dat is de platformstandaard en geen tenantkeuze.
- **`src/core/shared/config.py`:** de debugcontrole ("P0-5") staat ingesprongen binnen de
  productie-sleutelcontrole en draait dus alleen als die sleutel ontbreekt. Bestaand, niet aangeraakt
  (een eigen wijziging).
- **JSON-modus van de copilot:** `TenantTaalmodel.complete_json` dwingt geen `response_format` af
  (het model van de tenant volgt de prompt; de handler heeft een hertrekking bij ongeldige JSON). Niet
  gemeten met een echt model.
- **CD en compose** (interlock 2, niet aangeraakt): zie de melding aan de regie voor de regels.
