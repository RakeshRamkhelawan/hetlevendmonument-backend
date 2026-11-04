# Review BE-SVC-070 — Focus Builder Workflow Generation via complete_json()

## A. Eindoordeel

APPROVED WITH MINOR GAPS

## B. Samenvatting

De specificatie beschrijft de vervanging van handmatige JSON-parsing in de Focus Builder AI-generatie door `LLMClient.complete_json()` met het `ReactFlowGraph` Pydantic schema. De broncode bevestigt dat `AgenticFlowService.generate_flow_from_prompt()` `complete_json()` aanroept en dat de router de nieuwe response envelope gebruikt. De spec is technisch over het algemeen correct.

## C. Bevindingen per categorie

### 1. Coverage gaps

- De spec noemt componenten en wijzigingen, maar is geen volledig backend feature template (geen detailsecties per artefact, geen request/response schema's in template-vorm).
- De spec noemt dat `LLMService.complete_json()` is toegevoegd, maar de broncode toont dat deze methode in `src/core/llm/llm_service.py` bestaat.

### 2. Functionele onduidelijkheden

- Geen. Het doel (betrouwbare gestructureerde output) is helder.

### 3. Technische onduidelijkheden

- De spec zegt "LLM native JSON mode". De implementatie hangt af van de provider; `complete_json()` delegeert naar `provider.complete_json()`. Dat is correct.
- De spec noemt dat `tenant_id` expliciet in het LLM prompt context wordt opgenomen. De broncode van `generate_flow_from_prompt()` toont dat `tenant_id` wordt doorgegeven, maar het is niet direct zichtbaar hoe dit in de prompt wordt geïnjecteerd zonder meer context te lezen.

### 4. Ontbrekende foutstatussen en edge cases

- De spec noemt 403 (Council veto/HITL) en 500 (LLM provider error).
- Een edge case ontbreekt: wat gebeurt er als `complete_json()` een lege of ongeldige JSON retourneert? De spec noemt "Bij lege prompt retourneert de AI een minimaal start-node schema", maar niet het gedrag bij een ongeldige provider-response.

### 5. Acceptatiecriteria problemen

- De testtabel is concreet (14 tests). Een expliciete checklist ontbreekt.

### 6. Integratorhandleiding / API-uitleg problemen

- Het API contract (request/response voorbeelden) is duidelijk.

### 7. Trainingsdata problemen

- De Trainingssamenvatting in tabelvorm volgt het verplichte mini-format. Geschikt voor LLM-training.

### 8. Structuur- en consistentieproblemen

- De spec is een compacte feature-note, niet het volledige template. Dat is acceptabel voor een gerichte refactor.
- De spec noemt pre-existing fixes in `learning_mixin.py` en `router.py`. Dat is correct gescheiden.

### 9. Risico's voor implementatie, security of QA

- Laag risico. Council governance blijft behouden. Tenant-isolatie via JWT is behouden.

## D. Issue Register

| Severity | ID of sectie | Probleem | Waarom dit een probleem is | Concrete correctie |
| --- | --- | --- | --- | --- |
| Low | API Contract / foutafhandeling | Ongeldige JSON-response van provider niet gedocumenteerd | Integrators weten niet wat ze kunnen verwachten bij provider-fouten | Voeg een foutrespons toe voor ongeldige/missende JSON, bijv. 500 met `LLM_GENERATION_FAILED` |
| Low | Tenant isolatie | Claim dat tenant_id expliciet in prompt context zit is niet direct verifieerbaar uit de bekeken broncode | Reviewers kunnen de prompt-injectie niet controleren | Voeg een code-fragment toe of verwijs naar de exacte regel waar `tenant_id` in de prompt wordt opgenomen |

## E. Ontbrekende items

- Geen functioneel ontbrekende items.

## F. Verbeterde tekstvoorstellen

- "Bij lege prompt retourneert de AI een minimaal start-node schema" -> "Bij een lege prompt of ongeldige provider-response wordt een minimaal start-node schema geretourneerd of een 500 `LLM_GENERATION_FAILED`, afhankelijk van de foutlocatie."

## G. Release-oordeel

- Geschikt voor bouw / implementatie: ja.
- Geschikt voor QA en geautomatiseerd testen: ja.
- Geschikt voor LLM-training: ja.
- Geschikt voor integratorhandleiding / API-documentatie: ja.
