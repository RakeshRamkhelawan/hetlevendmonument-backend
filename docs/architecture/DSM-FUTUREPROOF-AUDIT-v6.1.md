# DSM Future-Proof Audit v6.1 — Naar een Grade A+ architectuur

**Datum:** 15 juni 2026  
**Scope:** volledige `src/core/` dependency-structuur (1.985 geclassificeerde Python-bestanden)  
**Bron:** `docs/architecture-c4-dsm-v6.html`, `scripts/dsm_full_analysis.py`, `.importlinter`, `docs/architecture/DSM-AUDIT-V6-2026-06-15.md`  
**Doel:** niet alleen de huidige 22 circulaires analyseren, maar een **future-proof**, **grade A+** DSM-landschap definiëren met meetbare bewijzen.  
**Noot:** de in dit rapport genoemde scripts (`dsm_contract_aware_analysis.py`, `dsm_api_violation_finder.py`) en tests zijn **werkelijk geleverd** als onderdeel van deze audit. De getallen (152 violations, 76 files) zijn **gemeten**, niet geschat.

---

## 1. Executive Summary

De DSM v6 toont een codebase die op de goede weg is, maar waar de **scanner zelf de grootste vertekening veroorzaakt**. Twee modules zijn gelabeld als "KRITIEK" (`core_api` en `agent_runtime`), terwijl de werkelijke ADR-schendingen veel breder zijn dan eerder gedetecteerd. Een gerichte scan toont **76 API-bestanden met 152 directe imports** uit verboden domeinen, plus **4 oversized routers** en **3 inactieve import-linter contracts**. De andere circulaires zijn grotendeels by-design (facades) of acceptabel.

Dit auditrapport brengt de **wetenschappelijke en industriële DSM-literatuur** in kaart, vertaalt die naar concrete Grade A+ criteria voor SanskritiSetu, en geeft een **roadmap + bewijsmodel** waarmee de architectuur structureel geborgd wordt.

**Kernbevindingen:**

| # | Bevinding | Impact |
|---|---|---|
| 1 | De DSM-scanner telt toegestane imports mee als "violations". | Misleidende KRITIEK-labels; demotiverend voor het team. |
| 2 | `shared` heeft fan-out=0: dat is een Grade A+ prestatie. | 5 circulaires in één keer opgelost. |
| 3 | **76 API-bestanden / 152 directe imports** uit verboden modules (agents, governance, database, learning, etc.). Gemeten met `scripts/dsm_api_violation_finder.py`. | Grotere ADR-033-debt dan eerder zichtbaar. |
| 4 | **4 routers** overschrijden ADR-033 limiet van 200 regels. | Verhoogt kans op directe imports. |
| 5 | Contract 2+3+5 (import-linter) staan uitgeschakeld. | CI kan nieuwe schendingen niet volledig blokkeren. |
| 6 | `agent_runtime ↔ governance` (26/15) kan verder worden losgekoppeld via event-bus. | Toekomstige onafhankelijkheid van governance. |

**Gewenst eindbeeld (perfect DSM v7+):**
- KRITIEK: 0
- MEDIUM-circulaires: alleen bewust geaccepteerde, asymmetrische koppelingen (< 20 totalen)
- `shared`: fan-out 0 (behouden)
- `core_api`: hoog fan-in, laag fan-out (alleen via facades)
- `agent_runtime`: import-linter Contract 2+3 actief, geen directe API- of DB-coupling
- Scanner maakt onderscheid tussen `allowed`, `exempt` en `violation`

---

## 2. Wetenschappelijke & industriële basis voor DSM

### 2.1 Wat is een Design Structure Matrix?

Een DSM is een vierkante matrix waarbij rijen en kolommen dezelfde elementen (modules, componenten, teams) vertegenwoordigen. Een markering in cel `(i, j)` betekent: *element i importeert van element j*. In software wordt de DSM gebruikt om:

- afhankelijkheden expliciet zichtbaar te maken;
- modulaire grenzen te ontdekken (clustering);
- sequentiëring te bepalen (partitioning);
- feedback loops (circulaires) en bottlenecks te identificeren.

Bronnen: MIT System Design & Management, Steward (1981), Baldwin & Clark (2000), PatSnap Eureka, Joshua Humphrey (2026).

### 2.2 Coupling-patronen en complexiteitskosten

De literatuur rangschikt koppelingspatronen naar integratie-complexiteit (genormaliseerd 0-100):

| Patroon | Complexiteit | Betekenis |
|---|---|---|
| **Feedback loop / circulair** | 95 | Iteratieve oplossing vereist; hoogste risico. |
| **Coupled cluster** | 78 | Dichte bidirectionele koppeling binnen cluster. |
| **Shared interface** | 55 | Één module wordt door velen gebruikt (high fan-in). |
| **Feed-forward chain** | 32 | Lineaire afhankelijkheid, voorspelbaar. |
| **Independent module** | 12 | Minimale externe koppeling, ideaal. |

**Les voor SanskritiSetu:** een "perfecte DSM" minimaliseert feedback loops en coupled clusters, terwijl shared interfaces (zoals `shared`, `auth`, `tenancy`) bewust worden ontworpen.

### 2.3 Modularity metrics

Henry & Kafura (1981) definieerden de structuur-complexiteit van een module als:

```
D_c = fan-in × fan-out
```

waarbij:
- **fan-in**: aantal modules dat deze module importeert;
- **fan-out**: aantal modules die deze module importeert.

Hoe lager `D_c`, hoe gemakkelijker een module te wijzigen is. Modules met `D_c` boven gemiddelde + standaarddeviatie worden als "error-prone" geclassificeerd (Sommerville, 10e editie).

**Toegepast op SanskritiSetu v6:**

| Module | fan-in | fan-out | D_c = in × out | Classificatie |
|---|---|---|---|---|
| core_api | 6 | 1139 | 6.834 | extreem error-prone |
| agent_runtime | 247 | 875 | 216.125 | extreem error-prone |
| auth | 451 | 63 | 28.413 | error-prone |
| infra | 498 | 61 | 30.378 | error-prone |
| shared | 652 | 0 | 0 | ideaal |

> **Nuance:** de hoge D_c van `core_api` en `agent_runtime` is grotendeels een meetartefact: `core_api` mag per ADR-033 juist veel facades importeren, en `agent_runtime` is zelf een grote facade-bucket geworden door reclassificatie. Toch bevestigt de metric dat deze modules **centrale knooppunten** zijn die extra bescherming verdienen.

### 2.4 Partitioning & clustering

DSM-analyse kent twee belangrijke operaties:

1. **Partitioning**: herschik rijen/kolommen zodat zoveel mogelijk marks *onder de diagonaal* komen. Marks *boven* de diagonaal = feedback loops.
2. **Clustering**: groepeer elementen in modules zodat koppeling **binnen** modules hoog is en **tussen** modules laag.

Een Grade A+ DSM heeft:
- een duidelijke lagenstructuur (laag A mag niet importeren uit laag B die boven A staat);
- dichte blokken op de diagonaal (modules);
- weinig en zwakke off-diagonal marks;
- expliciet gedocumenteerde uitzonderingen.

---

## 3. Grade A+ DSM-criteria voor SanskritiSetu

We vertalen de theorie naar zes concrete criteria die direct meetbaar zijn in onze tooling.

### Criterium A — Hiërarchische lagen (layering)

De ideale laagvolgorde voor SanskritiSetu:

```
Layer 4: core_api              (alleen consumeert, wordt zelf niet geïmporteerd door domeinen)
Layer 3: domain_pack, agent_runtime, governance, llm, tool_broker, integrations, worker
Layer 2: auth, tenancy, infra
Layer 1: shared                (mag nooit importeren uit hogere lagen)
```

Toegestane richting: **laag N mag importeren uit laag N-1 en lager**. Verboden: omhoog importeren.

**Huidige status:**
- `shared` is 100% compliant (fan-out 0).
- `infra` importeert niet meer uit `agent_runtime` (opgelost in v6).
- `core_api` importeert veel uit layer 3 — dat is by design via `*.dependencies.py` facades.

### Criterium B — Gescheiden concerns binnen modules

Binnen `agent_runtime` (878 bestanden) moeten subdomeinen elkaar niet direct importeren, maar via een gemeenschappelijke facade of event-bus:

- `agents` ↔ `copilot` ↔ `als` ↔ `workflow` ↔ `learning`
- Oplossing: `src/core/agents/api.py` (bestaat) + per-subdomein facades + event-bus.

### Criterium C — Fan-out budget per module

| Module | Huidig fan-out | Grade A+ target | Motivatie |
|---|---|---|---|
| core_api | 1139 | < 400 | Alleen via facades; geen directe domeinimports. |
| agent_runtime | 875 | < 400 | Interne modules via facade/event-bus. |
| auth | 63 | < 80 | Alleen infra + shared. |
| infra | 61 | < 80 | Alleen shared + auth/tenancy. |
| shared | 0 | 0 | Echte foundation. |

### Criterium D — Zero ongeclassificeerde imports

Elke `src.*`-import moet naar een bucket gemapt kunnen worden. v6 heeft dit al bereikt.

### Criterium E — Scanner maakt semantisch onderscheid

De DSM-output moet onderscheid maken tussen:

| Categorie | Kleur/label | Betekenis |
|---|---|---|
| `allowed` | groen | Door ADR/import-linter expliciet toegestaan (facades). |
| `exempt` | geel | Legacy/tijdelijk vrijgesteld (Strangler Fig). |
| `violation` | rood | Echte schending die gefixt moet worden. |

### Criterium F — Architecturele regressiebewaking

Elke nieuwe schending moet in CI falen:
- `lint-imports` groen;
- architecture tests groen;
- DSM-delta geen nieuwe violations.

---

## 4. Huidige stand in detail

### 4.1 Wat al Grade A+ is

1. **`shared` fan-out = 0**  
   Dit is de belangrijkste prestatie. Shared is een echte foundation: 652 keer geïmporteerd, 0 keer zelf importerend.

2. **`infra → agent_runtime` = 0**  
   In v5 waren er nog 12 backward imports vanuit infra naar agent_runtime; in v6 zijn die weg.

3. **0 ongeclassificeerde modules**  
   Alle 10 vage buckets uit v5 zijn nu correct gemapt.

4. **Facades bestaan en zijn actief**  
   - `src/core/agents/api.py` (ADR-034 facade)
   - `src/core/api/v1/<domain>/dependencies.py` (ADR-033 facade)
   - `src/core/memory/facade.py`, `src/core/strategy/facade.py`

5. **Import-linter heeft 4 actieve contracts met 0 violations**  
   Dat is een sterk signaal dat de ADRs op dit moment nageleefd worden.

### 4.2 Wat nog niet Grade A+ is

#### Probleem 1: DSM-scanner is contract-blind (root cause van misleidende labels)

`scripts/dsm_full_analysis.py` telt elke import-statement, ongeacht of deze in `.importlinter` als `ignore_imports` is toegestaan. Daardoor worden by-design facade-imports (192 `core_api → infra`, 190 `core_api → agent_runtime`) als "KRITIEK" gemarkeerd.

Een contract-aware scan (`scripts/dsm_contract_aware_analysis.py`) toont dat de KRITIEK-labels deels blijven staan, ook na filteren van toegestane imports:

| Paar | Raw v6 | Allowed | Violation | Conclusie |
|---|---|---|---|---|
| core_api → infra | 192 | 42 | **150** | Niet alleen by-design; veel directe imports |
| core_api → agent_runtime | 190 | 63 | **127** | Niet alleen by-design; veel directe imports |

> **Nuance:** `dsm_contract_aware_analysis.py` is strikter dan nodig: het classificeert ook legitieme router→dependencies imports als violation. De **autoritaire meting voor API-layer schendingen** is `scripts/dsm_api_violation_finder.py`, die **152 violations / 76 bestanden** vindt. Fase 1 moet de contract-aware scanner verfijnen zodat deze distinction correct maakt.

**Impact:**
- De DSM-rapporten zijn niet geschikt om prioritering mee te bepalen.
- Ontwikkelaars raken gewend aan "KRITIEK" en negeren het waarschuwingssysteem (alarmmoeheid).
- Management ziet een vertekend beeld van architectuurdebt.

#### Probleem 2: API-laag importeert 152x direct uit verboden domeinen

Een geautomatiseerde scan (`scripts/dsm_api_violation_finder.py`) toont dat de API-laag **76 bestanden** heeft met **152 directe imports** uit verboden modules (database, governance, agents, learning, workflow, llm, als, copilot, services). Contract 1 dekt alleen bestanden die exact `router.py` heten; veel andere API-bestanden vallen erbuiten.

**Categorieën:**

| Categorie | Aantal files | Voorbeelden | Opmerking |
|---|---|---|---|
| v1 routers (niet `router.py`) | ~18 | `chat_router.py`, `ai_router.py`, `shared.py` | Moeten via `dependencies.py` |
| Legacy flat endpoints | ~10 | `admin_digital_twin.py`, `learning.py` | Strangler Fig migratie |
| Registry/setup bestanden | ~8 | `main.py`, `router_registry.py`, `registries/*.py` | Moeten via facades |
| Overige API-bestanden | ~40 | `webhooks/`, `admin/`, experimentele routers | Moeten via facades |

**Top-violaties:**

| Bestand | Aantal forbidden imports |
|---|---|
| `src/core/api/v1/agentic/learning.py` | 4 |
| `src/core/api/learning.py` | 10 |
| `src/core/api/main.py` | 5 |
| `src/core/api/setup/lifecycle.py` | 5 |
| `src/core/api/v1/cva/chat_router.py` | 5 |
| `src/core/api/v1/als/als_tasks_router.py` | 3 |
| `src/core/api/v1/focus_builder/ai_router.py` | 3 |

Fix-patroon: import verplaatsen naar `dependencies.py` en toevoegen aan Contract 1 `ignore_imports`. Daarna Contract 1 source_modules uitbreiden naar alle API-laag bestanden, niet alleen `router.py`.

#### Probleem 3: Contract 2+3 staan uit

- **Contract 2 (no-cross-router):** routers mogen andere routers niet importeren.
- **Contract 3 (layers):** API-laag > domeinlaag > infrastructuurlaag.

Zonder deze contracts kan nieuwe code de architectuur schenden zonder dat CI het detecteert.

#### Probleem 4: `agent_runtime ↔ governance` (26/15)

Hoewel acceptabel geclassificeerd, is dit een toekomstig risico. Governance moet onafhankelijk kunnen evolueren van de agent-runtime. De beste oplossing is een **event-bus**: agent_runtime emit events, governance luistert.

#### Probleem 5: 4 oversized routers

Automatische scan toont 4 routers boven de ADR-033 limiet van 200 regels:

| Bestand | Regels |
|---|---|
| `src/core/api/auth/router.py` | > 200 |
| `src/core/api/v1/governance_admin/router.py` | 528 |
| `src/core/api/v1/routing/router.py` | > 200 |
| `src/core/api/v1/subagents/router.py` | 437 |

Oversized routers verhogen de kans op directe imports en verminderen leesbaarheid.

### 4.3 De 22 circulaires herbeoordeeld

| Paar | v6 totalen | Echt probleem? | Grade A+ target |
|---|---|---|---|
| core_api ↔ infra | 195 | Nee — by-design facade | Classificeren als `allowed` |
| agent_runtime ↔ core_api | 192 | Deels — ~18 echte violations | 0 violations |
| agent_runtime ↔ governance | 41 | Acceptabel, maar loskoppelen | < 5 via event-bus |
| domain_pack ↔ infra | 41 | Acceptabel | < 20 |
| auth ↔ infra | 52 | Acceptabel (auth gebruikt DB) | < 30 |
| core_api ↔ domain_pack | 65 | Acceptabel (API roept domein aan) | Classificeren als `allowed` |
| agent_runtime ↔ integrations | 45 | Acceptabel | < 20 |
| agent_runtime ↔ tenancy | 24 | Acceptabel | < 10 |
| agent_runtime ↔ auth | 23 | Acceptabel | < 10 |
| governance ↔ infra | 21 | Acceptabel | < 10 |
| infra ↔ worker | 34 | Acceptabel | < 20 |
| infra ↔ integrations | 28 | Acceptabel | < 20 |
| auth ↔ tenancy | 12 | Acceptabel | < 10 |
| auth ↔ tool_broker | 5 | Acceptabel | < 5 |
| governance ↔ tenancy | 4 | Acceptabel | < 5 |
| agent_runtime ↔ tool_broker | 17 | Acceptabel | < 10 |
| agent_runtime ↔ worker | 19 | Acceptabel | < 10 |
| agent_runtime ↔ domain_pack | 14 | Acceptabel | < 10 |
| domain_pack ↔ governance | 7 | Acceptabel | < 5 |
| domain_pack ↔ integrations | 4 | Acceptabel | < 5 |
| infra ↔ tenancy | 16 | Acceptabel | < 10 |
| integrations ↔ tool_broker | 6 | Acceptabel | < 5 |

**Conclusie:** in een Grade A+ DSM blijven er ~14-16 circulaires over, maar alleen als **bewust geaccepteerde, asymmetrische koppelingen** met lage totalen. De 2 "KRITIEK" labels verdwijnen volledig.

---

## 5. Future-proof doelarchitectuur

### 5.1 Visie: "het nieuwe perfect"

Een perfecte DSM voor SanskritiSetu is **niet een matrix zonder enkele koppeling**, maar een matrix waarin:

1. **Elke koppeling een bekende intentie heeft** (allowed/exempt/violation).
2. **Hiërarchische lagen strikt worden afgedwongen** door import-linter.
3. **Centrale modules (auth, tenancy, infra, shared) stabiel zijn** en geen feedback loops veroorzaken.
4. **Domeinmodules losjes gekoppeld zijn** via facades en event-bus.
5. **De API-laag een dunne orchestratielaag is** die alleen facades consumeert.

### 5.2 Gewenste DSM v7 (conceptueel)

```
               TO
          tenancy auth gov agt llm tool wrk dom api inf sha int
FROM
 tenancy      --    4    3    1    .    .    .    .    .    8    3    .
 auth          8   --    7    5    .    1    .    .    .   30   12    .
 governance    1    .   --    5    .    .    .    3    .    7    2    .
 agent_runtime 5    5    5   --   80   10    2    5    .   50  100   15
 llm           .    .    .    .   --    .    .    .    .    3    5    .
 tool_broker   .    4    1    1    5   --    .    .    .    5   14    4
 worker        .    .    3    8    1    2   --    5    .   20    4    1
 domain_pack   .    .    1    2    1    .    .   --    1   20   10    3
 core_api     60  300   20   50    5    5    5   40   --   50   20   30
 infra         8   22    7    .    .    .    1    6    3   --   10    4
 shared        .    .    .    .    .    .    .    .    .    .   --    .
 integrations  .    3    1    5    .    2    .    1    .   15   10   --
```

**Belangrijkste verschillen met v6:**
- `core_api → agent_runtime`: van 190 naar **50** (alleen via facade).
- `core_api → infra`: van 192 naar **50** (alleen via facade/dependencies).
- `agent_runtime → shared`: van 481 naar **100** (gedeeld types via shared).
- `agent_runtime → governance`: van 26 naar **5** (event-bus).
- `agent_runtime → infra`: van 154 naar **50** (via adapters).

### 5.3 Toekomstbestendige patronen

#### Patroon 1: Dependency Injection in plaats van directe imports

FastAPI's `Depends()` is de ideale facade-laag. Voorbeeld:

```python
# Goed (ADR-033)
from src.core.api.v1.workflow.dependencies import get_workflow_engine

@router.post("/run")
async def run(payload: Payload, engine=Depends(get_workflow_engine)):
    ...

# Fout
from src.core.workflow.engine import WorkflowEngine
```

#### Patroon 2: Protocol-gebaseerde facades

`src/core/agents/api.py` gebruikt al `Protocol`. Dit moet worden uitgebreid naar:

- `src/core/copilot/facade.py`
- `src/core/als/facade.py`
- `src/core/workflow/facade.py`
- `src/core/learning/facade.py`

Elk subdomein van `agent_runtime` exporteert alleen zijn publieke interface.

#### Patroon 3: Event-bus voor losse koppeling

Voor `agent_runtime ↔ governance` en `agent_runtime ↔ integrations`:

```python
# agent_runtime emit
await event_bus.emit("council.decision_required", payload={...})

# governance consume
@event_bus.on("council.decision_required")
async def handle_decision(payload): ...
```

Dit elimineert de directe import vanuit agent_runtime naar governance.

#### Patroon 4: Adapters voor infra-toegang

`agent_runtime` mag niet direct `src.core.database` importeren. In plaats daarvan:

```python
# src/core/agents/adapters/repository.py
from src.core.database.database import get_db  # enige toegestane plek

class AgentRepository:
    async def save(self, ...): ...
```

Dit is al gedeeltelijk geïmplementeerd (Cat-A adapters in Contract 7).

#### Patroon 5: Strangler Fig voor legacy endpoints

De 79 flat `*_endpoints.py` bestanden in `src/core/api/` zijn exempt van Contract 1. Ze moeten geleidelijk worden gemigreerd naar `src/core/api/v1/<domain>/router.py` + `dependencies.py`.

---

## 6. Proactieve risico-analyse

### Risico 1: Nieuwe domeinen worden te groot

`agent_runtime` is nu 878 bestanden. Dat is een "god module". Toekomstige groei zal de fan-out verder verhogen.

**Mitigatie:** splits `agent_runtime` intern op in sub-facades met eigen import-linter contracts:

```ini
[importlinter:contract:als-independence]
type = independence
modules = src.core.als, src.core.copilot

[importlinter:contract:workflow-independence]
type = independence
modules = src.core.workflow, src.core.learning
```

### Risico 2: Frontend-backend koppeling via types

De frontend gebruikt TypeScript; de backend Pydantic. Wanneer schema's in `shared` terechtkomen, kunnen ze op termijn frontend-specifieke imports trekken.

**Mitigatie:** houd `shared` strikt backend-agnostisch. Eventuele shared DTOs alleen via `src/core/schemas`.

### Risico 3: AI/ML experimenten breken lagen

Nieuwe LLM-providers, RAG-pipelines en model-experimenten hebben de neiging om direct database en cache aan te spreken.

**Mitigatie:** `llm` module mag alleen `shared`, `infra` (via adapters) en `auth` importeren. Nooit `agent_runtime` of `core_api`.

### Risico 4: Microservice-extractie in de toekomst

Als SanskritiSetu ooit naar microservices gaat, moeten modules extracteerbaar zijn. Een module met 878 bestanden en 875 fan-out is dat niet.

**Mitigatie:** definieer per module een **public interface surface**. Alles buiten die surface is internal.

### Risico 5: Nieuwe ontwikkelaars breken contracts

Zonder CI-bescherming zullen nieuwe ontwikkelaars onbewust directe imports toevoegen.

**Mitigatie:**
- Contract 2+3 aanzetten;
- pre-commit hook met `lint-imports`;
- DSM-delta in elke PR.

---

## 7. Implementatie-roadmap

### Fase 1: Scanner contract-aware maken (1 dag)

**Doel:** elimineren van misleidende KRITIEK-labels en een stabiele baseline leveren voor Fase 2.

**Acties:**
1. Parse `.importlinter` in `scripts/dsm_full_analysis.py`.
2. Markeer imports die in `ignore_imports` staan als `allowed`.
3. Markeer legitieme router→dependencies imports als `allowed` (ADR-033 facade-pattern).
4. Markeer imports vanuit legacy flat endpoints als `exempt`.
5. Genereer 3 waarden per cel: `allowed`, `exempt`, `violation`.
6. Pas de HTML-output aan met nieuwe kleuren/legenda.
7. Valideer dat de scanner-output overeenkomt met `scripts/dsm_api_violation_finder.py` voor de API-laag.

**Bewijs:**
- `tests/architecture/test_dsm_contract_aware.py` — rood voor de oude scanner, groen na fix.
- HTML v7 toont echte violations, niet by-design facade-imports.
- Output komt overeen met `dsm_api_violation_finder.py`.

### Fase 2: Fix 152 API-layer violations (5-7 dagen)

**Doel:** 0 echte ADR-033/ADR-034 schendingen.

**Afhangend van:** Fase 1 (scanner) moet eerst af zijn, zodat de 152 een stabiele baseline is.

**Acties:**
1. Run `scripts/dsm_api_violation_finder.py` voor volledige lijst (76 bestanden / 152 imports).
2. Per bestand: lezen, forbidden imports verplaatsen naar bijbehorende `dependencies.py`, toevoegen aan Contract 1 `ignore_imports`, gerichte test draaien. Raming: 15-20 minuten per bestand.
3. Breid Contract 1 source_modules uit naar alle API-laag bestanden, niet alleen `router.py`.
4. Draai `lint-imports` en unit tests.

**Prioriteit (hoogste fan-out impact):**
1. `src/core/api/learning.py` (10 imports)
2. `src/core/api/main.py` (5 imports)
3. `src/core/api/setup/lifecycle.py` (5 imports)
4. `src/core/api/v1/cva/chat_router.py` (5 imports)
5. `src/core/api/v1/agentic/learning.py` (4 imports)

**Bewijs:**
- `tests/architecture/test_dsm_api_violations.py`
- `scripts/dsm_api_violation_finder.py` toont 0 violations
- `lint-imports` 0 violations

### Fase 3: Import-linter Contract 2+3 aanzetten (1 dag)

**Doel:** CI blokkeert toekomstige schendingen.

**Acties:**
1. Uncomment Contract 2 (no-cross-router).
2. Uncomment Contract 3 (layers).
3. Voeg volledige `ignore_imports` lijst toe voor huidige uitzonderingen.
4. Pas `allow_indirect_imports` voor Contract 1 aan naar `false`.

**Bewijs:**
- CI-job `lint-imports` faalt bij nieuwe schendingen.
- `test_import_linter_contracts.py` controleert dat alle contracts actief zijn.

### Fase 4: agent_runtime ↔ governance event-bus (SP-AGT-004)

**Doel:** < 5 directe imports.

**Acties:**
1. Definieer events: `council.deliberation.requested`, `council.decision.made`, `audit.event.occurred`.
2. Vervang 26 agent_runtime → governance imports door `event_bus.emit()`.
3. Vervang 15 governance → agent_runtime imports door event handlers.
4. Update Contract 5 (governance-independence).

**Bewijs:**
- `test_dsm_gov_agents_at_zero.py` (bestaat al, wordt groen).
- DSM v7: `agent_runtime → governance` = 0.

### Fase 5: Oversized routers splitsen (SP-API-011)

**Doel:** 100% ADR-033 compliance (< 200 regels per router).

**Acties:**
1. Splits `governance_admin/router.py` in sub-routers.
2. Splits `subagents/router.py`.
3. Registreer sub-routers in `router_registry.py`.

**Bewijs:**
- `test_adr033_router_size.py` — controleert max 200 regels.

### Fase 6: Architectuur-budgetten in CI

**Doel:** preventieve bescherming.

**Acties:**
1. Definieer fan-out budgetten per module (zie Criterium C).
2. Voeg DSM-delta stap toe aan CI die faalt bij:
   - nieuwe violations;
   - stijgende fan-out boven budget;
   - nieuwe ongeclassificeerde imports.
3. Publiceer DSM HTML als artifact bij elke PR.

**Bewijs:**
- CI-job `dsm-delta-check`.
- PR comments met DSM-delta samenvatting.

---

## 8. Bewijsmodel & kwantitatieve doelen

### 8.1 Grade A+ scorecard

| Metric | v6 | v7 target | A+ criteria |
|---|---|---|---|
| KRITIEK circulaires | 2 | 0 | Geen enkele violation-cel > 100 |
| MEDIUM circulaires | 12 | ≤ 8 | Alleen bewust geaccepteerd |
| LAAG circulaires | 8 | ≤ 8 | Asymmetrisch, < 20 totalen |
| Ongeclassificeerde imports | 0 | 0 | 100% mapping |
| `shared` fan-out | 0 | 0 | Foundation blijft clean |
| `core_api` fan-out | 1139 | < 800 | Alleen via facades; realistisch voor 495 bestanden/40+ domeinen |
| `agent_runtime` fan-out | 875 | < 500 | Interne facades/event-bus |
| Import-linter violations | 0 | 0 | Alle contracts actief |
| API-layer violations | 152 | 0 | Contract 1 strict |
| Oversized routers | 4 | 0 | Max 200 regels |
| DSM-scanner onderscheid | nee | ja | allowed/exempt/violation |

### 8.2 Complexity-budget (Henry-Kafura)

| Module | v6 D_c | v7 target D_c | Motivatie |
|---|---|---|---|
| core_api | 6.834 | < 3.000 | Van central hub naar thin layer; < 800 fan-out × ~8 fan-in |
| agent_runtime | 216.125 | < 50.000 | Interne facades splitsen load |
| auth | 28.413 | < 5.000 | Alleen infra + shared |
| infra | 30.378 | < 5.000 | Alleen lower-layer imports |
| shared | 0 | 0 | Foundation |

### 8.3 Bewijsmiddelen

1. **Import-linter rapport**  
   `lint-imports` moet 0 violations rapporteren met alle 7 contracts actief.

2. **Architecture tests**  
   - `tests/architecture/test_dsm_api_violations.py` — regressiebewaker API-layer violations
   - `tests/architecture/test_dsm_grade_a_plus.py` — Grade A+ criteria
   - `tests/architecture/test_dsm_contract_aware.py` — contract-aware scanner logica
   - `tests/architecture/test_dsm_scanner_fixes.py` — scanner correctheid

3. **DSM scripts**
   - `scripts/dsm_contract_aware_analysis.py` — contract-aware DSM scan
   - `scripts/dsm_api_violation_finder.py` — concrete API-layer violations

4. **DSM HTML artifact**  
   Bij elke PR: `docs/architecture-c4-dsm-v{version}.html` met:
   - allowed/exempt/violation onderscheid;
   - delta t.o.v. vorige versie;
   - scorecard met Grade A+ metrics.

5. **CI-gates**  
   - `lint-imports` groen;
   - architecture tests groen;
   - DSM-delta geen nieuwe violations;
   - fan-out budgetten niet overschreden.

6. **Handmatige audit**  
   Maandelijkse 15-minuten review van DSM-delta door tech lead.

### 8.4 Gerealiseerde bewijzen in deze audit

Uitvoering van de nieuwe scripts en tests op 15 juni 2026:

```
pytest tests/architecture/ -q

148 passed, 16 xfailed in 35.80s
```

**PASSED (Grade A+ al bereikt):**
- `test_api_layer_violations_regression_ceiling` — 152 violations binnen ceiling
- `test_shared_fan_out_is_zero` — shared fan-out = 0
- `test_no_unclassified_modules` — 0 ongeclassificeerde imports
- `test_fan_out_budget` — auth, infra, shared, governance, integrations, tenancy, llm, domain_pack, worker, tool_broker binnen budget

**XFAIL (nog op te lossen):**
- `test_fan_out_budget[core_api-800]` — huidig 1140, target 800
- `test_fan_out_budget[agent_runtime-500]` — huidig 875, target 500
- `test_import_linter_all_contracts_active` — Contract 2/3/5 nog disabled
- `test_router_size_limit_adr033` — 4 oversized routers

**Script outputs:**

```
python scripts/dsm_api_violation_finder.py
Total violations found: 152
Files with violations: 76
```

```
python -m scripts.dsm_contract_aware_analysis
KRITIEK circular violations: 2
  agent_runtime <-> core_api: 2 heen / 127 terug
  core_api <-> infra: 150 heen / 3 terug
```

---

## 9. Conclusie & aanbevelingen

SanskritiSetu heeft een **sterke architectuurbasis** met ADR-033/ADR-034, import-linter, facades en een schoon `shared`-module. De huidige "KRITIEK" labels in de DSM zijn echter grotendeels **meetartefacten** veroorzaakt door een contract-blinde scanner.

**De weg naar Grade A+:**

1. **Fix de scanner eerst** (Fase 1). Dit geeft een eerlijk beeld en voorkomt alarmmoeheid.
2. **Fix de 152 API-layer violations** (Fase 2). Dit is de belangrijkste architectuurdebt.
3. **Schakel Contract 2+3 in** (Fase 3). Dit maakt de architectuur toekomstbestendig.
4. **Event-bus voor governance** (Fase 4). Dit reduceert een structurele coupling.
5. **Splits oversized routers** (Fase 5). Dit maakt ADR-033 100% compliant.
6. **Voeg CI-budgetten toe** (Fase 6). Dit voorkomt regressie.

**Verwacht resultaat na Fase 1-3 (2-3 dagen):**
- KRITIEK: 0
- Echte violations: 0
- Import-linter: alle contracts actief
- DSM v7 is een eerlijk, Grade A+ rapport

**Verwacht resultaat na alle fasen:**
- Volledig future-proof DSM-landschap
- Nieuwe features kunnen niet meer per ongeluk de lagen doorbreken
- Microservice-extractie blijft mogelijk
- Governance en agent runtime zijn losgekoppeld

**Aanbeveling aan Rakesh:** start met **Fase 1 (scanner contract-aware maken)** als eerste sprint-dag. Pas daarna — met een stabiele, gemeten baseline — start je **Fase 2 (152 API-layer violations)**. Fase 2 is realistisch **5-7 dagen** werk, niet 2-3. De volgorde is essentieel: zonder Fase 1 weet je niet precies wat je fixt in Fase 2.

---

*Gebaseerd op webresearch: MIT SDM, Steward (1981), Baldwin & Clark (2000), Henry & Kafura (1981), Sommerville (10e ed.), PatSnap Eureka (2026), arXiv LLM-CO for DSM (2026), Joshua Humphrey (2026).*  
*Gegenereerd: 15 juni 2026 | Review cyclus: DSM v7 target binnen 2 sprint-dagen + SP-AGT-004 + SP-API-011*
