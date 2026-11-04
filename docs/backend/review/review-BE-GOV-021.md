# Review BE-GOV-021 — Autonomy ladder gedifferentieerd per agent-type

## A. Eindoordeel

APPROVED WITH MINOR GAPS

## B. Samenvatting

De specificatie beschrijft de differentiatie van `autonomy_level` en `risk_category` per agent-type via `ai_act_classifier.classify_agent()` in `EnhancedBaseAgent.__init__()`. HIGH_RISK/UNACCEPTABLE agenten krijgen HUMAN_IN_LOOP, LIMITED/MINIMAL blijven HUMAN_ON_LOOP. De broncode in `src/core/agents/base_agent.py` bevestigt de classificatie na department-consolidatie en de risk-to-autonomy mapping.

## C. Bevindingen per categorie

### 1. Coverage gaps

- De spec noemt `EnhancedBaseAgent.__init__()` maar geeft geen expliciet bestandspad. Broncode zit in `src/core/agents/base_agent.py`. TODO toevoegen.
- De spec noemt twee pre-existing bugs die zijn gefixt (`agent_type` als string, `SymbioticAgent` department doorgeven). Dat is waardevolle context, maar zonder bestandspaden moeilijk te verifiëren.

### 2. Functionele onduidelijkheden

- Geen. Het doel (niet alles hardcoded HUMAN_ON_LOOP/LIMITED) is helder.

### 3. Technische onduidelijkheden

- De spec legt uit dat classificatie NA department/function-consolidatie uit YAML gebeurt. Broncode bevestigt dit.
- De `record_evidence` voor Art. 9 risk management wordt genoemd. Broncode bevestigt dit.

### 4. Ontbrekende foutstatussen en edge cases

- De spec noemt dat `classify_agent()` faalt niet stilzwijgend; exceptions propageren. Dat is correct.
- Een edge case ontbreekt: wat gebeurt er als `ai_act_classifier` niet beschikbaar is bij import? De code gebruikt `importlib.import_module`, dus een `ModuleNotFoundError` zou de agent-constructie laten crashen. Dat is fail-closed, maar niet gedocumenteerd.

### 5. Acceptatiecriteria problemen

- Geen expliciete acceptatiecriteria. Testbewijs is aanwezig.

### 6. Integratorhandleiding / API-uitleg problemen

- De Trainingssamenvatting is goed en noemt de uitzondering over department-agents.

### 7. Trainingsdata problemen

- Geschikt voor LLM-training.

### 8. Structuur- en consistentieproblemen

- Compacte feature-note. De backlog SP-GOV-ARCH-6/7 wordt expliciet benoemd.

### 9. Risico's voor implementatie, security of QA

- De backlog (HIGH_RISK agenten classificeren nog als LIMITED vanwege capabilities die na `super().__init__()` worden gezet) is correct gemarkeerd als falende architecture-test.
- `GovernanceContract.record_hitl_approval()` heeft geen productie-aanroepers (SP-GOV-ARCH-7). Dit is een reeel maar buiten-scope risico.

## D. Issue Register

| Severity | ID of sectie | Probleem | Waarom dit een probleem is | Concrete correctie |
| --- | --- | --- | --- | --- |
| Low | Locatie | Bestandspad van `EnhancedBaseAgent` ontbreekt | Reviewers kunnen de implementatie niet direct vinden | Voeg toe: `src/core/agents/base_agent.py` |
| Low | Edge case | Afhandeling van `importlib.import_module` fouten niet gedocumenteerd | Als `ai_act_classifier` ontbreekt, crasht agent-constructie | Noteer expliciet dat een ontbrekende classifier fail-closed is (agent wordt niet geconstrueerd) |

## E. Ontbrekende items

- Geen functioneel ontbrekende items.

## F. Verbeterde tekstvoorstellen

- Voeg een locatie-regel toe: "`EnhancedBaseAgent` is gedefinieerd in `src/core/agents/base_agent.py`."

## G. Release-oordeel

- Geschikt voor bouw / implementatie: ja, met de kanttekening dat SP-GOV-ARCH-6/7 nog openstaat.
- Geschikt voor QA en geautomatiseerd testen: ja.
- Geschikt voor LLM-training: ja.
- Geschikt voor integratorhandleiding / API-documentatie: beperkt; interne agent-governance.
