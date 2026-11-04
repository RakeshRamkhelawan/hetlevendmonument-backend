# BE-AGT-042 -- Council-poort verplicht per actie

| Veld | Waarde |
| --- | --- |
| Feature-ID | BE-AGT-042 |
| Datum | 2026-08-02 |
| ADR | ADR-036 D10 stap 6, D2, D5 (volgorde), AI Act art. 14 |
| Sprint | ADR-036 Fase B / Fase 2 / dag 2 |

---

## 1. Probleem

`request_council_decision_for_agent()` (`copilot/council/background_gate.py:50`) is de
transport-neutrale Council-ingang voor achtergrondtaken. Compleet, met unit- EN
integratietests, en met **nul productie-aanroepers**: alleen tests riepen hem aan.

Dat is het derde geval van hetzelfde patroon in deze sprintreeks:

| Onderdeel | Bestond | Aangesloten |
| --- | --- | --- |
| 27 tools in 135 manifesten | ja | nee (BE-AGT-039 F1) |
| Manifest-budget (4 limieten) | ja, geparseerd | nee (BE-AGT-041) |
| Council-ingang | ja, getest | **nee** |

Een tool-aanroep doorliep: manifest-allowlist, `execute_tool`, permissiecheck,
categoriecheck, risk-classificatie, HITL bij HIGH risk. De Council kwam daar nergens in voor.

## 2. Oplossing

De poort staat in `act()`, per tool-call. De volgorde is contract:

```text
1. manifest-allowlist-filter   (bestond, _parse_tool_calls)
2. D5 harde denylist           NIEUW -- moet VOOR de Council
3. Council-beraadslaging       NIEUW -- per actie
4. execute_tool                herhaalt de permissiecheck, plus risk/HITL
```

**Verdict-vertaling.** De gate gooit nooit; hij retourneert een `CouncilDecision` en laat de
aanroeper vertalen (D7). `APPROVED` en `MODIFIED` laten de actie door; `BLOCKED`,
`HITL_REQUIRED` en `DEFERRED` niet, met het verdict in `errors`. Door `success = not errors`
(BE-AGT-039 F3) is een geblokkeerde actie automatisch geen succes -- geen extra logica.

### 2.1 Waarom niet in `execute_tool`

`execute_tool` heeft **twaalf** productie-aanroepers, waaronder HTTP-paden die al via
`require_council_approval()` gaan. De poort daar plaatsen zou dubbele beraadslaging geven en
een systeembrede gedragswijziging -- te groot en te riskant voor deze stap.

### 2.2 De accountability-vraag

De gate vereist `user_id` en legt het besluit daarop vast. De bestaande tests gebruiken `1`.
Een verzonnen waarde schrijft een autonome agent-actie toe aan een echt persoon; dat is geen
cosmetisch detail maar een verantwoordingsprobleem.

Drie bronnen onderzocht:

| Bron | Uitkomst |
| --- | --- |
| `Department.head_user_id` | Bestaat, maar nullable en nergens voor autorisatie gelezen. Koppelen is expliciet **D1-werk (Fase 4)**; niet vooruithalen |
| Een systeem-/service-user | Bestaat niet in deze codebase; zou ik moeten verzinnen |
| **De mens die de uitvoering start** | `POST /packs/execute` had `_current_user` -- met underscore, dus **bewust ongebruikt**. De geauthenticeerde gebruiker was er wel en werd weggegooid |

De derde is waar en verifieerbaar. `initiated_by_user_id` loopt nu expliciet van de
HTTP-ingang via `execute_pack`/`run_pack`/`_run_single_step`/`_execute_step` naar de skill.
Expliciet en niet via een ContextVar: impliciete ambient identiteit is precies de klasse
problemen die deze ADR blootlegt. En niet via de `params`-dict, om dezelfde reden waarom
`backend-patterns.md` par. 1 dat voor `tenant_id` verbiedt.

**Ontbreekt de initiator, dan wordt er niets uitgevoerd.** Geen fallback op een verzonnen id.
Dat is de AI-Act-art.-14-houding die de ADR zelf formuleert ("een naam zonder ingreepmacht
telt niet"), en de plek waar D1 later invult.

### 2.3 Vanaf de skill gaat het als instance-state verder

Alle **135** skills overschrijven `act(self, decision: str)` met hetzelfde delegerende
lichaam. De signatuur wijzigen zou een regeneratie van 135 bron- EN manifestbestanden
vragen, met een generator die alles herschrijft. Daarom zet `execute_with_manifest_prompt()`
de waarde op de instance en houdt `act()` zijn signatuur.

### 2.4 `is_denied()` in plaats van `is_tool_allowed()`

De precheck gebruikt een nieuwe, smalle methode op `ToolPermissionManager`. `is_tool_allowed`
bevat ook de allowlist en de ADR-015 default-deny; die op skill-niveau herhalen zou elke
agent zonder profiel al daar laten stranden -- veel breder dan D5 vraagt. Ontdekt doordat
drie bestaande tests met een profielloze agent omvielen. De allowlist en default-deny blijven
het werk van `execute_tool`, waar ze al getest zijn.

## 3. Kosten

Elke beraadslaging opent een eigen DB-sessie (`background_gate.py:93`), dus acht tool-calls
zijn acht sessies. Begrensd door `max_steps=8` uit BE-AGT-041 -- een prettig neveneffect van
de vorige dag. De acht Officers zijn regelgebaseerd (geen LLM), dus de rekentijd is
verwaarloosbaar; de sessies zijn de kostenpost. Samenvoegen tot een sessie per invocatie kan
later; de gate accepteert vandaag geen sessie van buiten.

## 4. Tests

`tests/unit/als/test_council_gate_per_action.py` -- 10 tests, alle 10 rood gecommit in
`b742bb8b` (toen met dezelfde `AttributeError`: het patch-doel bestond niet, want de ingang
werd nergens geimporteerd -- dat *is* de bevinding).

`tests/architecture/test_agent_actions_pass_council.py` -- 4 tests: AST-scan op methoden die
`execute_tool` aanroepen zonder poort, een broncode-volgordetest voor D5, een vangnet tegen
hernoemen, en een verval-detector op de uitzonderingslijst.

**Mutatie-getest, zes richtingen:** poort weghalen, denylist weghalen, fail-closed weghalen,
volgorde omdraaien, helper hernoemen. Elk maakt exact de bijbehorende test rood.

De denylist-test construeert **bewust** een divergentie tussen manifest en profiel. In de
huidige configuratie zijn die lijsten disjunct, dus zonder die divergentie zou de
manifest-filter de tool al wegvangen en bewees de test niets -- een vacuum-test.

## 5. Voorzien neveneffect

Fail-closed liet 9 bestaande tests omvallen die geen initiator meegaven, plus 3 die `act()`
rechtstreeks aanroepen. Allemaal opgelost door de initiator expliciet mee te geven -- dat
maakt die tests realistischer, want een run start in productie altijd bij iemand.

De governance-stubs staan nu in `tests/fixtures/agent_governance.py` en worden door twee
conftests geherexporteerd, in plaats van per map gekopieerd. Reden: het gaat om dezelfde twee
lagen, en een kopie per map loopt uiteen zodra er een derde bijkomt.

## 6. Trainingssamenvatting

**Flow 1 -- een actie wordt geblokkeerd door de Council**

- Actor: ALS-skill met een permissieprofiel
- Voorwaarde: de tool staat in de allowlist en niet op de denylist; er is een initiator
- Actie: de skill emit `TOOL_CALL: <tool>`
- Systeemreactie: de Council beraadslaagt en geeft `BLOCKED`; de tool wordt niet uitgevoerd
  en het verdict komt met uitleg in `errors`
- Succes: n.v.t.
- Fout: `success` is False, want er staat een fout in `errors`
- Uitzonderingen: `APPROVED` en `MODIFIED` laten de actie wel door

**Flow 2 -- een actie op de harde denylist**

- Actor: ALS-skill
- Voorwaarde: de tool staat in `denied_actions` van het profiel
- Actie: de skill probeert de tool
- Systeemreactie: geweigerd vóór de Council; er wordt geen beraadslaging gestart
- Succes: n.v.t.
- Fout: de reden vermeldt expliciet dat de Council niet is geraadpleegd
- Uitzonderingen: geen -- geen goedkeuring kan dit overrulen (D5)

**Flow 3 -- een uitvoering zonder bekende initiator**

- Actor: een aanroeper die `initiated_by_user_id` niet meegeeft
- Voorwaarde: de skill wil een tool uitvoeren
- Actie: `act()` bereikt de poort
- Systeemreactie: er wordt niets uitgevoerd en de Council wordt niet geraadpleegd
- Succes: n.v.t.
- Fout: de melding benoemt dat er geen verantwoordelijke mens aan de uitvoering hangt
- Uitzonderingen: geen. Tot D1 het afdelingshoofd invult is de startende mens de enige
  verifieerbare bron

## 7. Gewijzigde bestanden

| Bestand | Wijziging |
| --- | --- |
| `src/core/als/agents/specialist_base.py` | `_reject_before_council()`, `_council_rejection()`, poort in `act()`, initiator als instance-state |
| `src/core/tool_broker/permission_manager.py` | `is_denied()` -- alleen de denylist |
| `src/core/als/enterprise/packs.py` | `initiated_by_user_id` door 10 signaturen en 8 aanroepen |
| `src/core/api/v1/agentic/agentic_domain_router.py` | `_current_user` -> `current_user`, id doorgegeven |
| `src/core/als/agents/skills/skillsgaptraining.py` | initiator ontvangen en op de instance zetten |
| `tests/fixtures/agent_governance.py` | nieuw -- gedeelde stubs |
| `tests/unit/als/conftest.py`, `tests/unit/agents/conftest.py` | herexport van die stubs |
| `tests/unit/als/test_council_gate_per_action.py` | nieuw -- 10 tests |
| `tests/architecture/test_agent_actions_pass_council.py` | nieuw -- 4 tests |
