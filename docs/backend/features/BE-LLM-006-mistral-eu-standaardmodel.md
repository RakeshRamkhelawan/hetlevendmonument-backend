# BE-LLM-006 -- Mistral (EU) als standaard taalmodel, per klant te kiezen

Datum:     2026-10-19
Fase:      Pilot december 2026, ADR-041 blokkade B14
Brief:     `docs/agent-briefs/generated/2026-10-15-sprint-dag-mistral-als-eu-taalmodel.md`
Basis:     develop `9c58df3d`; commit `ff48c72d` (tak iter/mistral)

---

## 1. Waarom deze knip bestaat

De uitrol (`cd-staging.yml`, `cd-production.yml`) zet `LLM_PROVIDER=deepseek`. DeepSeek is een
Chinese leverancier zonder verwerkersovereenkomst en mag niet met klantgegevens (ADR-041 B14).
Gemeten op `9c58df3d` was DeepSeek bovendien niet alleen "aangesloten" maar DE standaard:

| Plek | Wat er stond |
|---|---|
| `src/core/llm/llm_service.py` (centrale service, stapel A) | `default_provider = DEEPSEEK`; DeepSeek stond bovenaan zodra `DEEPSEEK_API_KEY` bestond |
| `src/core/llm/fallback_chain.py::get_fallback_chain` | registreerde DeepSeek zodra de sleutel bestond |
| `src/core/llm/provider_factory.py::_detect_provider_type` | `deepseek` stond vooraan in de automatische keuze |
| `LLMService.for_tenant` (stapel B, `src/core/services/llm/service.py`) | een tenant zonder eigen eindpunt kreeg `LLMService()`, de platformstandaard uit `LLM_PROVIDER` |
| `BaseSpecialistAgent._get_llm_service` | bij elke fout terugval op diezelfde platformstandaard |

**Het besluit.** Rakesh, 2026-10-15: "1. c" -- een gehuurd taalmodel in de EU, per klant schakelbaar
naar een eigen model, nooit stil terugvallen; leverancier Mistral AI ("prima" op het advies). Rakesh regelt
zelf het account, de opt-out voor training, zero data retention, de verwerkersovereenkomst (DPA) en de
sleutel. Onderzoek: `docs/onderzoek-keuze-eu-taalmodel.md`.

## 2. Wat er nu gebeurt

- **Provider `mistral`** in beide stapels: `src/core/llm/mistral_provider.py` (stapel A, met JSON-uitvoer en
  toolaanroepen) en `src/core/services/llm/providers/mistral.py` (stapel B, via het generieke
  OpenAI-compatibele pad). Eindpunt `https://api.mistral.ai/v1`; `MISTRAL_BASE_URL` moet https zijn.
- **De sleutel** komt UITSLUITEND uit `MISTRAL_API_KEY`. Hij staat niet in `repr`, niet in een foutmelding en
  niet in een logregel; een afwijzing wordt gelogd met de statuscode en niet met de tekst van het antwoord.
- **Het model**: `LLM_MODEL` telt alleen als `LLM_PROVIDER=mistral` en bevat nooit "deepseek"; anders
  `mistral-small-latest`.
- **De fabrieken**: de automatische keuze is mistral eerst en bevat DeepSeek niet meer; de standaardketen
  registreert Mistral voorop en DeepSeek niet meer; de centrale service initialiseert DeepSeek alleen bij
  `LLM_PROVIDER=deepseek` (en dan zonder Mistralsleutel).
- **Uitrolbrug**: `LLM_PROVIDER=deepseek` samen met `MISTRAL_API_KEY` wordt in beide stapels Mistral (met een
  waarschuwing); de DeepSeek-sleutel en `LLM_API_KEY` gaan niet naar Mistral. Zonder Mistralsleutel gedraagt
  de code zich als voorheen. Zo hoeft de CD niet eerst te wijzigen.
- **Mock**: een onbekende provider of geen enkele provider is buiten tests een FOUT; in tests een namaakmodel
  met een `[MOCK]`-melding. Een uitdrukkelijke `LLM_PROVIDER=mock` (de CD gebruikt dat) blijft kunnen, met
  dezelfde melding.

## 3. De keuze per klant

`tenants.settings["llm_provider"]` (de bestaande JSON-kolom, dus GEEN migratie). De regels staan op een
plek: `src/core/shared/tenant_llm_keuze.py`.

| Keuze | Toegestane providers bij een verzoek van die klant | Bij een storing |
|---|---|---|
| `mistral` (standaard) | mistral, ollama, lmstudio | valt door naar het EIGEN model; nooit naar een ander gehuurd model |
| `ollama` | ollama, lmstudio | een duidelijke fout; NOOIT een gehuurd model |
| iets anders (`deepseek`, `mock`, typfout) | niets | een fout; valt niet stil terug op de standaard |

De keuze wordt gelezen in de ene korte sessie van `LLMService.for_tenant`, gecontroleerd bij het opslaan
(`TenantCreate` en `TenantUpdate`) en blijft staan bij een vervangende settings-update
(`behoud_llm_keuze`). De terugvalketen heeft daarvoor `generate(..., tenant_keuze=...)`.

## 4. De vlag `externe_providers_toegestaan` blokkeert Mistral NIET

`tenants.externe_providers_toegestaan` (standaard FALSE, BE-LLM-003) is de "lokaal-alleen"-schakelaar voor
KLANT-EIGEN eindpunten: staat hij uit, dan weigert het schrijfpad een extern LLM-eindpunt dat de klant zelf
laat inrichten. Dat blijft zo.

Mistral valt daar bewust buiten. Het is de platformverwerker die het platform zelf kiest, onder een
verwerkersovereenkomst die Rakesh regelt. Een klant die Mistral niet wil, kiest `ollama`. Zou de vlag wel
voor Mistral gelden, dan werkte Mistral voor niemand, want alle tenants staan standaard op FALSE.

**Bron:** besluit Rakesh 2026-10-15 ("1. c", gehuurd EU-model met DPA en opt-out door hemzelf), bevestigd door
de regie (sessie sanskritisetu-org-90) op 2026-10-19 op de vraag van de bouwer in het verslag bij `ff48c72d`.

## 5. Gedragswijzigingen die je moet kennen

1. **`LLMService.for_tenant` met een lege keten** gaf de platformstandaard (BE-LLM-005 noemt dat nog); het geeft
   nu de keuze van de klant, standaard Mistral. Een ontbrekende `MISTRAL_API_KEY` is dan een fout.
2. **De agentdeur valt niet meer terug op het platformmodel.** Elke fout in het bepalen van het taalmodel
   (een ongeldige keuze, een ontbrekende sleutel, een databasestoring) laat de taak zichtbaar mislukken
   (`TenantLLMKeuzeFout`, `TenantLLMNietBeschikbaarError`). Het platformmodel is in de uitrol DeepSeek.
3. **De gebruikerskeuze van een model in de CVA** (`_ALLOWED_CVA_MODELS`) bevat geen deepseek-modellen meer.
4. **`docker-compose.dev.yml`** staat standaard op mistral.

## 6. Uitrol -- wat de regie moet doen (interlock 2, niet in deze wijziging)

- `cd-staging.yml:621-627` en `cd-production.yml:466-469`: nu `LLM_PROVIDER=deepseek` met `DEEPSEEK_API_KEY`
  als secret, anders `LLM_PROVIDER=mock`. Naar: secret `mistral-api-key`, `LLM_PROVIDER=mistral`,
  `LLM_MODEL=mistral-small-latest`, `MISTRAL_API_KEY=secretref:...`; geen DeepSeek; het mock-pad bij een
  ontbrekende sleutel vervangen door een duidelijke fout.
- **Uitrolvoorwaarde:** zonder `MISTRAL_API_KEY` in de omgeving mislukken alle agenttaken van klanten zonder
  eigen eindpunt (bedoeld: fail-closed).
- **Het Mistral-account:** de sleutel is geldig maar het account antwoordt HTTP 429 met
  `x-ratelimit-limit-req-minute: 0` (gemeten 2026-10-19): er is geen actief plan. Rakesh activeert dat.

## 7. Meting

| Wat | Resultaat |
|---|---|
| nieuwe en aangepaste tests (`tests/unit/llm/test_mistral_provider.py`, `test_tenant_llm_keuze.py`) | 88 groen |
| mutatiebewijs, beide richtingen, een regel per element | 44 mutanten, alle 44 gedood; herstel groen |
| ruff / pyright / mypy-audit / Any-teller | schoon / 0 / 0 / 7037 (gelijk aan baseline) |
| pre-commit (gerichte tests op 43+ bestanden) | 1496 passed |
| proefscript met de echte sleutel (`scripts/proef_mistral.py`) | NIET GEMETEN: HTTP 429, limiet 0 per minuut |

Bestaande tests die het oude gedrag vastlegden zijn omgedraaid (niet overgeslagen):
`test_provider_factory_deepseek`, `test_fallback_chain_enabled`, de fixture van `test_llm_service` en
`test_llmservice_for_tenant`.

## 8. Wat niet is opgepakt

- Directe aanroepen naar api.deepseek.com in `workflow_generator_service._init_deepseek_client` en
  `focus_suggestion_service._call_deepseek`.
- `GuaranteedLLMService` (`llm_config.py`, alleen health-eindpunten) heeft DeepSeek nog eerst en mock als laatste.
- Aanroepers van de terugvalketen zonder `tenant_keuze` (agent_router_agent, master_orchestrator_agent,
  agent_selector): Mistral staat voorop, maar Google en OpenAI staan erachter als hun sleutels gezet zijn.
- PII-maskering zit in `generate_response`, niet in `chat_completion` en `text_completion`; berichten met de
  rol `tool` worden niet gemaskeerd.
- De CVA kan een Gemini-model kiezen terwijl de provider Mistral is (bestond al).
- `api/v1/tenant_management/crud_router.py` heeft eigen schema's zonder keuzecontrole; het is niet gemonteerd
  (ADR-036 OP-224).

## Trainingssamenvatting

- **Actor:** een agent die namens een tenant een taak uitvoert (geen menselijke actor; dit loopt in een worker).
- **Voorwaarde:** `MISTRAL_API_KEY` staat in de omgeving en het Mistral-account heeft een actief plan; de tenant
  heeft in `tenants.settings["llm_provider"]` niets, `mistral` of `ollama` staan.
- **Actie:** de agent vraagt om een taalmodel en doet een aanroep.
- **Systeemreactie:** heeft de klant eigen eindpunten ingericht (en staat `externe_providers_toegestaan` aan),
  dan geldt zijn keten (BE-LLM-004/005). Anders volgt zijn keuze: `mistral` gaat naar Mistral (EU), `ollama` naar
  het eigen model.
- **Succes:** het antwoord komt van de gekozen verwerker; `provider_name` noemt welke.
- **Fout:** een ongeldige keuze, een ontbrekende sleutel of een storing in het bepalen van het model geeft een
  duidelijke fout en de taak mislukt zichtbaar; een afwijzing van Mistral staat in het log met de statuscode.
- **Uitzonderingen:** een klant die `ollama` koos krijgt nooit een gehuurd model, ook niet bij een storing;
  DeepSeek wordt voor geen enkel klantverzoek gekozen; een namaakmodel bestaat buiten tests alleen bij een
  uitdrukkelijke `LLM_PROVIDER=mock`, met een `[MOCK]`-melding.
