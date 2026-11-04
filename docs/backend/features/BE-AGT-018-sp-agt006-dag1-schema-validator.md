# Backend Feature Specification

## Metadata

- Feature ID: BE-AGT-018
- Feature naam: OutputSchemaValidator -- Tier-1 deterministisch schema/format validatie in CriticAgent
- Status: APPROVED
- Auteur: SP-AGT-006 Dag 1
- Reviewer: doc-reviewer subagent
- Datum: 2026-06-27
- Gerelateerde user story / ticket: SP-AGT-006
- Gerelateerde router / module: src/core/agents/critic_agent.py
- Gerelateerde frontend endpoints: geen
- Gerelateerde database tabellen: agent_critiques (via CritiqueStore)
- Versie: 1.0

---

## Doel en scope

### Doel

Voeg een deterministisch Tier-1 validatiescherm toe aan de CriticAgent dat agent-output
structureel controleert (leeg/None, type, verplichte velden, tekenlengte) voordat
de HeuristicScorer of LLM-escalatie wordt aangeroepen. Een harde structuurfout kortsluitt
de volledige pijplijn onmiddellijk en retourneert score 0.0, zodat er geen LLM-tokens
worden verspild aan aantoonbaar ongeldige output.

### In scope

- Nieuwe dataclass `SchemaValidationResult` in `src/core/agents/critic_agent.py`
- Nieuwe klasse `OutputSchemaValidator` in `src/core/agents/critic_agent.py`
- Integratie van `OutputSchemaValidator` als eerste stap in `CriticAgent.critique_task()`
- `get_capabilities()` methode toegevoegd aan `CriticAgent` (9 capabilities, inclusief `schema_validation`)
- Uitbreiding van `config/agents/critic_agent.yaml` met sectie `capability_schemas:` (4 capability-schemas)
- 8 TDD-unittests in `tests/unit/agents/test_critic_agent_schema_validator.py`

### Out of scope

- Config-gestuurde instantiatie van `OutputSchemaValidator` per capability (enkel de default
  validator zonder parameters wordt nu in `CriticAgent.__init__` aangemaakt)
- Semantische of inhoudelijke outputvalidatie (dat is de taak van HeuristicScorer en LLM)
- Persistentie van SchemaValidationResult als afzonderlijke tabelrij (het wordt opgenomen
  in `Critique.metadata`)
- Aanpassingen aan de `CritiqueStore` of database-schema

---

## Build summary

- Nieuw gebouwd:
  - `SchemaValidationResult` dataclass
  - `OutputSchemaValidator` klasse
  - `CriticAgent.get_capabilities()` methode
  - `capability_schemas:` sectie in `config/agents/critic_agent.yaml`
  - `tests/unit/agents/test_critic_agent_schema_validator.py` (8 tests)
- Gewijzigd:
  - `CriticAgent.__init__()` -- instantiatie van `self._default_schema_validator`
  - `CriticAgent.critique_task()` -- Tier-1 schema-check als eerste stap
  - `config/agents/critic_agent.yaml` -- capabilities-lijst uitgebreid met `schema_validation`,
    nieuwe `capability_schemas:` sectie toegevoegd
- Verwijderd: geen
- Beinvloede bestaande flows:
  - `critique_task()` -- aanroepende code die een `Critique` verwacht bij een lege/None
    output krijgt nu onmiddellijk `score=0.0` terug met `metadata={"schema_validation_failed": True, "tier": "schema"}`
    zonder dat de HeuristicScorer of LLM wordt aangeroepen
  - `get_capabilities()` -- retourneert nu een lijst in plaats van niets (methode bestond niet)

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
|----|------|------|-------------|-----------------|-------------------|
| BE-AGT-018-A | SchemaValidationResult | dataclass | src/core/agents/critic_agent.py | Nieuw | Tier-1 validatieresultaat |
| BE-AGT-018-B | OutputSchemaValidator | klasse | src/core/agents/critic_agent.py | Nieuw | Tier-1 schema/format check |
| BE-AGT-018-C | CriticAgent.critique_task() | methode (wijziging) | src/core/agents/critic_agent.py | Wijziging | Tier-1 kortsluitingspijplijn |
| BE-AGT-018-D | CriticAgent.get_capabilities() | methode | src/core/agents/critic_agent.py | Nieuw | Capability-registratie |
| BE-AGT-018-E | config/agents/critic_agent.yaml | YAML configuratie | config/agents/critic_agent.yaml | Wijziging | capability_schemas declaratie |
| BE-AGT-018-F | test_critic_agent_schema_validator.py | testbestand | tests/unit/agents/test_critic_agent_schema_validator.py | Nieuw | TDD-dekking Tier-1 |

---

## Detaildocumentatie per artefact

---

### [BE-AGT-018-A] SchemaValidationResult

**Type:** dataclass (Python stdlib `dataclasses`)
**Locatie:** `src/core/agents/critic_agent.py`, na imports, voor `OutputSchemaValidator`

**Doel:** Gestandaardiseerd resultaatobject dat de uitkomst van een schema-validatie
vastlegt en doorgegeven wordt aan `critique_task()` voor kortsluitingsbeslissing.

**Functionele beschrijving:**
Bevat vier velden die samen de validatiestatus volledig beschrijven:
- `passed`: `True` als alle checks geslaagd zijn, `False` bij elke fout
- `score`: `1.0` bij geen issues, `0.0` bij elke gefaalde check
- `issues`: leesbare foutomschrijvingen (lijst van strings)
- `suggestions`: concrete herstelacties voor de agent-ontwikkelaar (standaard lege lijst)

**Technische beschrijving:**

```python
@dataclass
class SchemaValidationResult:
    passed: bool
    score: float
    issues: list[str]
    suggestions: list[str] = dc_field(default_factory=list)
```

**Acceptatiecriteria:**
- `passed=True` en `score=1.0` worden alleen retourned als er nul issues zijn
- `passed=False` gaat altijd samen met `score=0.0` en minimaal een issue-string
- `suggestions` heeft een lege lijst als standaardwaarde (niet None)

**Trainingssamenvatting:**
- Actor: OutputSchemaValidator
- Voorwaarde: validatierun voltooid
- Actie: construeer SchemaValidationResult
- Systeemverwerking: velden worden toegewezen op basis van check-uitkomsten
- Succesrespons: `SchemaValidationResult(passed=True, score=1.0, issues=[], suggestions=[])`
- Foutrespons: `SchemaValidationResult(passed=False, score=0.0, issues=[...], suggestions=[...])`
- Uitzonderingen: geen

---

### [BE-AGT-018-B] OutputSchemaValidator

**Type:** klasse
**Locatie:** `src/core/agents/critic_agent.py`, na `SchemaValidationResult`, voor `HeuristicScorer`

**Doel:** Tier-1 deterministisch schema/format validatie. Controleert structurele
eigenschappen van agent-output onafhankelijk van inhoud, voor de HeuristicScorer loopt.

**Constructor:**

```python
def __init__(
    self,
    required_type: type | None = None,
    required_fields: list[str] | None = None,
    max_chars: int | None = None,
) -> None:
```

**Methode `validate(output: object) -> SchemaValidationResult`:**

Checks in volgorde (vroeg-retour bij stap 1 en 2, accumulerend bij stap 3 en 4):

1. **Leeg/None check** -- retourneert onmiddellijk bij `output is None`, `output == ""`,
   `output == {}` of `output == []`.
   Let op: `0`, `False`, en andere falsy niet-container waarden worden NIET als leeg beschouwd.
2. **Type check** -- retourneert onmiddellijk als `not isinstance(output, required_type)`.
3. **Required fields check** -- accumuleert ontbrekende velden; alleen als output een `dict` is.
   Als `required_fields` gezet is maar output geen dict is, worden de veldchecks stilzwijgend overgeslagen.
4. **Max chars check** -- vergelijkt `len(str(output))` met `max_chars`.

**Falsy waarden gedrag (BE-AGT-018-minor-3):**

De leeg-check gebruikt drie expliciete gelijkheidstoetsen, NIET Python's algemene truthiness:

| Waarde | Wordt als leeg beschouwd? | Reden |
|--------|--------------------------|-------|
| `None` | Ja | Ontbrekende output |
| `""` (lege string) | Ja | Lege tekstuele output |
| `{}` (leeg dict) | Ja | Lege structured output |
| `[]` (lege lijst) | Ja | Lege meervoudige output |
| `0` | **Nee** | Numerieke output; 0 is een geldige score |
| `False` | **Nee** | Boolean output; False is een geldig resultaat |
| `0.0` | **Nee** | Float output; 0.0 is een geldige confidence |
| `b""` (lege bytes) | **Nee** | Niet in de expliciete leeg-check opgenomen |
| `set()` (lege set) | **Nee** | Niet in de expliciete leeg-check opgenomen |

**Ontwerp-rationale:** CriticAgent beoordeelt ook agents die numerieke of boolean output
produceren (bijv. `score=0`, `approved=False`). Een truthiness-check zou deze waarden
foutief als "leeg" markeren en `score=0.0` teruggeven, terwijl de output inhoudelijk geldig is.
De expliciete check beperkt het leeg-oordeel tot de vier container-types die semantisch leeg zijn.

**Test-dekking:** zie `test_critic_agent_schema_validator.py` -- happy/unhappy paden voor
lege container-types en falsy niet-lege waarden.

**Acceptatiecriteria:**
- `validate("geldig")` met `required_type=str` -> `passed=True, score=1.0`
- `validate("")` -> `passed=False, score=0.0`
- `validate(None)` -> `passed=False, score=0.0`
- `validate({"score": 0.8})` met `required_fields=["score","reasoning"]` -> `passed=False`, issue bevat `"reasoning"`
- `validate({"key":"val"})` met `required_type=str` -> `passed=False, score=0.0`
- `validate("x"*100)` met `max_chars=50` -> `passed=False`
- Default `OutputSchemaValidator()` accepteert elke niet-lege waarde

**Trainingssamenvatting:**
- Actor: CriticAgent (intern)
- Voorwaarde: `critique_task()` wordt aangeroepen
- Actie: `validate(output)` aangeroepen met de output van het `ExecutionResult`-object
- Systeemverwerking: vier checks in volgorde; vroeg-retour bij harde failures
- Succesrespons: `SchemaValidationResult(passed=True, score=1.0, issues=[], suggestions=[])`
- Foutrespons: `SchemaValidationResult(passed=False, score=0.0, issues=[...], suggestions=[...])`
- Uitzonderingen: meerdere issues worden gecombineerd in een enkel resultaat

---

### [BE-AGT-018-C] CriticAgent.critique_task() -- Tier-1 integratie

**Type:** methode (wijziging van bestaande async methode)
**Locatie:** `src/core/agents/critic_agent.py`, klasse `CriticAgent`

**Technische beschrijving:**

In `CriticAgent.__init__()`: `self._default_schema_validator = OutputSchemaValidator()`

Let op: `CriticAgent` is een singleton per `tenant_id`. De `_default_schema_validator`
wordt eenmalig aangemaakt bij eerste initialisatie en is gedeeld over alle
critique-aanroepen voor dezelfde tenant.

Eerste stap in `critique_task()`:

```python
schema_result = self._default_schema_validator.validate(
    getattr(result, "output", None)
)
if not schema_result.passed:
    critique = Critique(
        critique_id=critique_id, agent_name=agent_name, task_id=task_id,
        tenant_id=self._tenant_id, score=0.0,
        issues=schema_result.issues, suggestions=schema_result.suggestions,
        mode=mode, metadata={"schema_validation_failed": True, "tier": "schema"},
    )
    await self._store.store(critique)
    return critique
```

**Business rules:**
- `getattr(result, "output", None)` behandelt ontbrekend `output`-attribuut veilig.
- Schema-falen slaat de critique op via `self._store.store()` (audit trail blijft compleet).
- `use_llm=True` wordt volledig genegeerd bij schema-failure.

**Acceptatiecriteria:**
- Bij lege output en `use_llm=True`: `_llm_critique` wordt niet aangeroepen
- `Critique(score=0.0, metadata={"schema_validation_failed": True, "tier": "schema"})` bij schema-failure
- De critique wordt opgeslagen in de store ook bij schema-failure
- Bij geldige output wordt doorgegaan naar HeuristicScorer

**Trainingssamenvatting:**
- Actor: externe service die `critique_task()` aanroept
- Voorwaarde: `CriticAgent` geinitialiseerd voor `tenant_id`; `ExecutionResult` beschikbaar
- Actie: `await critic_agent.critique_task(agent_name, task_id, result, mode, use_llm)`
- Systeemverwerking: Tier-1 check eerst; bij falen: opslaan en retourneren; bij slagen: HeuristicScorer
- Succesrespons (schema OK): `Critique` met score van HeuristicScorer/LLM
- Foutrespons (schema fail): `Critique(score=0.0, metadata={"schema_validation_failed": True})`
- Uitzonderingen: onverwachte exception -> fallback `Critique(score=0.5)`

---

### [BE-AGT-018-D] CriticAgent.get_capabilities()

**Type:** methode (nieuw)
**Locatie:** `src/core/agents/critic_agent.py`, klasse `CriticAgent`

**Functionele beschrijving:** Retourneert 9 capabilities als `list[str]`, inclusief
de nieuwe `"schema_validation"` capability toegevoegd in deze sprint.

**Acceptatiecriteria:**
- Retourneert `list[str]` met exact 9 elementen
- `"schema_validation"` aanwezig in de lijst

---

### [BE-AGT-018-E] config/agents/critic_agent.yaml -- capability_schemas

**Type:** YAML configuratiebestand (wijziging)
**Locatie:** `config/agents/critic_agent.yaml`

**Technische noot:** De sectie `capability_schemas:` wordt in deze sprint nog niet
programmatisch ingelezen. Het dient als specificatie voor toekomstige config-gestuurde
`OutputSchemaValidator`-instantiatie per capability (backlog SP-AGT-006 Dag 1 minor gap).

**Acceptatiecriteria:**
- YAML syntactisch geldig
- `capability_schemas:` bevat exact 4 capability-definities
- `capabilities:` lijst bevat `schema_validation`

---

## Acceptatiecriteria (sprint-totaal)

- `SchemaValidationResult(passed=True, score=1.0, issues=[])` bij geldige niet-lege output
- `validate(None)` en `validate("")` retourneren `passed=False, score=0.0`
- `validate({"score": 0.8})` met `required_fields=["score","reasoning"]` -> issue bevat `"reasoning"`
- `validate({"key":"val"})` met `required_type=str` -> `passed=False, score=0.0`
- `validate("x"*100)` met `max_chars=50` -> `passed=False`
- `critique_task()` roept `_llm_critique` niet aan bij schema-failure, ook niet bij `use_llm=True`
- Schema-failure critique wordt opgeslagen in `CritiqueStore`
- `get_capabilities()` retourneert 9 strings inclusief `"schema_validation"`
- 8/8 unittests slagen
- `python -m pyright` 0 nieuwe errors
- `ruff check src/core/agents/critic_agent.py` 0 violations

---

## Trainingssamenvatting (hoofdflow)

- **Actor:** Externe service (bijv. WorkflowService) die een agent-taak heeft uitgevoerd
- **Voorwaarde:** `CriticAgent` geinitialiseerd voor `tenant_id`; `ExecutionResult` beschikbaar
- **Actie:** `await critic_agent.critique_task(agent_name, task_id, result)`
- **Systeemverwerking:**
  1. `OutputSchemaValidator.validate(result.output)` uitgevoerd
  2a. Schema-failure: `Critique(score=0.0, metadata={"tier":"schema"})` opgeslagen en teruggegeven
  2b. Schema-OK: HeuristicScorer -> optioneel LLM-escalatie -> `Critique` opgeslagen en teruggegeven
- **Succesrespons:** `Critique` met `score` 0.0-1.0, gevuld `issues` en `suggestions`
- **Foutrespons (schema):** `Critique(score=0.0, metadata={"schema_validation_failed": True, "tier": "schema"})`
- **Uitzonderingen:** interne exception -> fallback `Critique(score=0.5)`

---

## Open aannames

- De `capability_schemas:` sectie in YAML wordt in een volgende sprint programmatisch ingelezen
  voor config-gestuurde `OutputSchemaValidator`-instantiatie per capability

## Open vragen

- Geen blokkerende open vragen

## Risico's

- Singleton-patroon `CriticAgent`: `_default_schema_validator` is niet hot-reloadable.
  Bij toekomstige runtime-config wijzigingen moet de singleton worden geinvalideerd.

---

## QA-checks

- [x] Tier-1 validatie functioneel getest (happy path)
- [x] Alle check-typen getest (leeg, type, velden, max_chars)
- [x] Kortsluitingsgedrag getest (LLM wordt niet aangeroepen bij schema-fail)
- [x] Tenant-isolatie: geen wijzigingen aan tenant-isolatielogica
- [x] Dataïntegriteit: critique wordt opgeslagen ook bij schema-failure (audit trail)
- [x] pyright 0 errors
- [x] ruff 0 violations

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Alle artefacten geinventariseerd
- [x] Alle foutpaden beschreven
- [x] Functionele beschrijving aanwezig
- [x] Technische beschrijving aanwezig
- [x] Acceptatiecriteria zijn testbaar
- [x] Trainingssamenvatting aanwezig
- [x] Open aannames benoemd
- [x] QA-checks uitgevoerd
- [x] Review: APPROVED WITH MINOR GAPS (minors: YAML niet ingelezen, singleton-noot, falsy-noot)
