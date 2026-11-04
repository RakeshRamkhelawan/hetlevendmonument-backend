# BE-AGT-043 -- Herstel en compliance na onafhankelijke hercontrole

| Veld | Waarde |
| --- | --- |
| Feature-ID | BE-AGT-043 |
| Datum | 2026-08-02 |
| ADR | ADR-036 D2, D5, D10 stap 6; AI Act art. 14; AVG art. 16/17 |
| Sprint | ADR-036 Fase B / Fase 2 / dag 2b (hersteldag) |
| Voorafgaand | BE-AGT-042 (`ab323ec7`), rode tests in `fb4fb295` |

---

## 1. Waarom deze dag bestaat

Op verzoek van Rakesh is elke opgeleverde fase van deze sprintreeks opnieuw beoordeeld,
zonder de eigen documentatie als uitgangspunt. Die hercontrole gebruikte drie sondes, gekozen
omdat het precies de faalvormen zijn die deze reeks al drie keer opleverde: *wordt het
aangeroepen*, *bewijst de test iets*, *klopt het cijfer*.

Daarna is Gate 2 alsnog gedraaid -- de dubbele reviewer-GO die twee dagen op rij ontbrak.
Beide reviewers gaven **CHANGES_REQUESTED** en vonden, onafhankelijk van elkaar, hetzelfde
kritieke defect in BE-AGT-042.

## 2. Wat de hercontrole ophaalde

| Sonde | Uitkomst |
| --- | --- |
| Aansluiting van 12 opgeleverde mechanismen | elk >= 1 productie-aanroeper; geen vierde "gebouwd maar niet aangesloten" |
| Mutatiedekking van de guards | 6 van 6 mutaties betrapt |
| Testaantallen tegen het register | 10 / 4 / 8+3 / 21 / 10 -- alle correct |
| Generator versus gegenereerd manifest | geen drift; de eerlijke tooltekst staat in het artefact |
| mypy | 52 fouten, **identiek op parent-commit** `b742bb8b` (worktree-vergelijking) |

Bijkomend inzicht zonder actie: de `agent_id`-parameter uit AUDIT-007 (Fase A dag 3) had tot
BE-AGT-042 **nul** productie-aanroepers. `background_gate.py` was de enige aanroeper die een
ander `agent_id` dan `"copilot"` meegeeft, en die werd door niets aangeroepen. Fase A sloot
AUDIT-007 terecht op unit- en architectuurbewijs, maar het gedrag in productie begint nu.

## 3. Het kritieke defect: de keten was doorgeknipt

`BE-AGT-042` claimde dat `initiated_by_user_id` "expliciet door 10 signaturen naar de skill"
loopt. De signaturen waren er allemaal. **Vier van de aanroepen gaven de waarde niet mee:**

| Plek | Aanroep |
| --- | --- |
| `packs.py:138` | `_execute_sequential(agents, tenant_id)` |
| `packs.py:210` | `_execute_single_agent(agent_id, tenant_id)` |
| `packs.py:275` | `_run_parallel_batch(batch, tenant_id, pack_id)` |
| `packs.py:292` | idem |

Regel 210 zit op het enige pad van `execute_pack` naar `_execute_step`, dus **beide** takken
verloren de waarde. Gevolg: `POST /packs/execute` weigerde elke tool-actie met "geen initiator
bekend", elke stap faalde, en de pack rapporteerde `FAILED` met escalatie naar een mens. De
poort was op het pad waarvoor hij gebouwd is volledig inert -- exact het patroon dat
BE-AGT-042 zei op te lossen, opnieuw ontstaan binnen de oplossing.

**Waarom de tests dit niet vingen.** Alle veertien tests riepen `_execute_step` of `run_pack`
rechtstreeks aan, met de parameter er al in. `execute_pack` -- de enige productie-ingang --
werd nergens getoetst. Een test die de keten niet vanaf het begin doorloopt, bewijst niets
over de keten. Dat is dezelfde les als OP-15: dekking meet je door de asserts te lezen, niet
door referenties te tellen.

De regressietest staat nu op `execute_pack`-niveau, geparametriseerd over een sequentiele en
een parallelle fase, en is mutatie-getest: het terugdraaien van regel 210 maakt beide rood.

## 4. De overige blokkerende bevindingen

**`MODIFIED` voerde de ongewijzigde actie uit.** `CouncilDecision.modifications` werd nooit
gelezen, terwijl `act()` daarna `execute_tool(payload=params)` met de originele parameters
aanriep. Een verdict "goedgekeurd MITS aangepast" negeerde dus precies de inperking waar de
Officer om vroeg -- een scope-beperking van de SecurityOfficer of een redactie van de
PrivacyOfficer viel stil weg. En dit was geen randgeval: de ComplianceOfficer geeft
`APPROVE_WITH_MODIFICATION` zodra `action_params` geen `ai_disclosure` bevat, wat bij
agent-acties altijd zo is. **Nu geweigerd**, net als `governance_gate.py` doet. Samenvoegen
van de aanpassingen vraagt een poort die parameters kan teruggeven; dat is latere fase.

**De poort vernietigde de tenant-context van zijn aanroeper.** `background_gate.py` zette in
zijn `finally` hard `set_tenant_id(None)` -- correct voor een Dramatiq-taak, maar deze poort
draait sinds BE-AGT-042 per tool-actie binnen `act()`, in dezelfde asynctaak als het
HTTP-verzoek. Die `None` lekte dus terug. Daarna gaf de ADR-004-hook stil nul rijen op elke
query en brak een latere `require_tenant_id()` af met een 500. **Nu bewaren en herstellen**,
met een regressietest die mutatie-getest is.

**Rauwe modelparameters gingen onuitwisbaar de audit-keten in.** `action_params=params` kwam
rechtstreeks uit `json.loads()` van LLM-output en werd verbatim naar
`council_decisions.action_params` geschreven en meegehasht in de ADR-019-keten -- een record
dat per ontwerp niet corrigeerbaar of wisbaar is. HR-inhoud daarin botst met AVG art. 16/17,
en de zusteringang schrijft het omgekeerde contract al voor ("keep PII out -- use keys only").
Bovendien lazen meerdere Officers governance-vlaggen uit diezelfde dict, dus een
prompt-injectie met `{"ai_disclosure": true}` kon de ComplianceOfficer stilzetten.

**Nu gaan alleen de toolnaam en de sleutelnamen de poort in.** Dat lost beide punten in een
keer op: geen waarden in de keten, en modeloutput kan per constructie geen control-sleutel
meer vullen. Prijs: Officers kunnen niet meer op waarden toetsen. Dat is een echte
functieverlies en staat als **OP-25** vastgelegd, met een test die faalt zodra er weer een
waarde de poort in gaat.

**Alle 135 skills erven een ongegate `execute_tool()`.** Via `SymbioticAgent` en
`EnhancedBaseAgent` bestaat een publieke methode die rechtstreeks naar de broker gaat: geen
denylist, geen Council, geen initiator. `self.execute_tool(...)` was daarmee een bypass in een
enkele regel, en mijn guard kon hem niet zien omdat de scope alleen `src/core/als/**` was.
**Nu in scope**, met een gedateerde uitzondering plus verval-detector (**OP-24**). Niet
gedicht: de methode wordt ook door niet-ALS-agents gebruikt.

## 5. De rest, kort

| Punt | Wat |
| --- | --- |
| Poort buiten de `try` | Een DB-hapering gooide alle al verzamelde resultaten weg, tegen de eigen belofte van `act()` in. Nu in dezelfde `try`, met `exc_info` |
| Geen spoor bij een weigering | Een geweigerde actie is precies wat art. 14 vastgelegd wil zien, en `result_data["errors"]` leest niemand. Nu `logger.warning` |
| Verkeerd aanleidingslabel | `trigger` bleef op de default `PROACTIVE_MONITOR`: een door een mens gestarte uitvoering werd vastgelegd als autonome achtergrondscan. Nu `USER_REQUEST` |
| Permissieconfig per actie van schijf | Bij 8 acties 8 keer YAML lezen, en een tweede bron naast de manager die de broker al heeft. Nu hergebruikt, met een groei-invariant als test |
| `getattr` op de uitleg | Een hernoeming zou stil een lege AVG-motivering geven. Directe toegang |
| Initiator bleef achter | Bij hergebruik van een instantie zou een volgende actie de vorige gebruiker krijgen. Nu opgeruimd in een `finally` |
| Geen limiet op `/packs/execute` | Elk verzoek veroorzaakt tot 8 beraadslagingen, elk met een per-tenant advisory lock. Nu `agent_execute_limit` (10/min), via de ADR-033-facade |
| `get_user_id()` kon `None` geven | Dan liep de uitvoering door en strandde diep in de keten, met HTTP 200 en een mislukte pack. Nu 401 aan de grens |
| Test schreef in de repo | `test_documentation_is_exportable` herschreef `docs/ai_act/...` bij elke suite-run. Nu `tmp_path` |
| ASCII-regel zonder handhaving | Repo-breed 301 bestanden / 1049 regels. Kernzone (23 regels) opgeruimd, guard met **lege** uitzonderingslijst; rest is **OP-22** |
| mypy zonder baseline | Gate eiste "groen" terwijl de stand 52 is. Vastgelegd met datum en meetmethode; geen CI-gate zonder Rakesh' GO (**OP-23**) |

Twee van de 23 ASCII-gevallen waren echte defecten en geen cosmetiek: een dubbel-gecodeerde
em-dash (mojibake) in `api/v1/agentic/learning.py` en een UTF-8 BOM aan het begin van
`api/v1/agentic/monitoring.py`. Beide onzichtbaar in een diff.

## 6. Wat ik hierbij zelf fout deed

Mijn eigen rate-limit-fix importeerde `src.core.governance.rate_limiter` rechtstreeks in een
laag-1 router. Dat verbiedt ADR-033 expliciet, en vier architectuurtests sloegen onmiddellijk
aan. Verplaatst naar de `dependencies.py`-facade. Waard om te noemen omdat het aantoont dat
die guards werken -- ze vingen mij binnen een minuut.

Verder heeft mijn eigen mutatieharnas eerder op de dag CRLF-regeleindes geintroduceerd in drie
bronbestanden. Betrapt doordat ik het herstel heb gecontroleerd in plaats van aangenomen, en
byte-getrouw teruggezet.

## 7. Trainingssamenvatting

**Flow 1 -- een pack-uitvoering met een bekende initiator**

- Actor: ingelogde gebruiker via `POST /packs/execute`
- Voorwaarde: geldige JWT, herleidbare gebruiker, binnen 10 verzoeken per minuut
- Actie: de gebruiker start een pack
- Systeemreactie: de initiator loopt door de hele keten; elke tool-actie gaat langs de
  denylist en de Council; de Council ziet de toolnaam en de argument-sleutels
- Succes: alleen bij `APPROVED`, en dan met de getoetste parameters
- Fout: bij elk ander verdict wordt niets uitgevoerd en staat de reden in `errors`
- Uitzonderingen: `MODIFIED` laat niet door zolang de aanpassingen niet toegepast kunnen worden

**Flow 2 -- een verzoek zonder herleidbare gebruiker**

- Actor: geauthenticeerd verzoek waarvan de gebruiker niet te bepalen is
- Voorwaarde: `get_user_id()` geeft `None`
- Actie: de gebruiker start een pack
- Systeemreactie: het verzoek wordt aan de grens geweigerd
- Succes: n.v.t.
- Fout: HTTP 401
- Uitzonderingen: geen -- doorlopen zou eindigen in HTTP 200 met een volledig mislukte pack

**Flow 3 -- de tenant-context na een beraadslaging**

- Actor: elke aanroeper van de Council-poort
- Voorwaarde: er is een tenant in de ContextVar
- Actie: de poort wordt geraadpleegd
- Systeemreactie: na terugkeer staat dezelfde tenant er nog
- Succes: vervolgqueries in hetzelfde verzoek zien hun eigen data
- Fout: n.v.t.
- Uitzonderingen: geen

## 8. Tests

`tests/unit/als/test_agent_governance_hardening.py` -- 6 tests: config-leesgroei,
`execute_pack`-keten (2 varianten), tenant-context, initiator opgeruimd, OODA fail-closed.

`tests/unit/als/test_council_gate_per_action.py` -- 11 tests; `MODIFIED` verhuisd naar de
weigerende set, de goedkeuringstest controleert nu de payload in plaats van een aanroeptelling,
en er is een test die aantoont dat waarden en governance-sleutels de poort niet in gaan.

`tests/architecture/test_no_non_ascii_in_core_zone.py` -- 3 tests, lege uitzonderingslijst.

`tests/architecture/test_agent_actions_pass_council.py` -- 5 tests; scope uitgebreid,
CWD-onafhankelijk, en de volgordetest gebruikt nu de AST-body van `act` in plaats van een
tekstknip die de hele rest van het bestand meenam.

**Mutatie-getest:** initiator-doorgifte, tenant-herstel, Council-poort, denylist, volgorde,
helper-hernoeming, budget-afdwingpunt, ASCII-guard.

## 9. Gewijzigde bestanden

| Bestand | Wijziging |
| --- | --- |
| `src/core/als/enterprise/packs.py` | 4 ontbrekende doorgiftes, `exc_info`, verouderde TODO weg |
| `src/core/als/agents/specialist_base.py` | `_get_permission_manager()`, `MODIFIED` weigeren, poort in de `try`, weigering loggen, alleen sleutelnamen naar de Council, `trigger=USER_REQUEST`, imports gesorteerd |
| `src/core/copilot/council/background_gate.py` | tenant-context bewaren en herstellen |
| `src/core/als/agents/skills/skillsgaptraining.py` | initiator opruimen in een `finally` |
| `src/core/api/v1/agentic/agentic_domain_router.py` | rate limit, 401 bij ontbrekende gebruiker |
| `src/core/api/v1/agentic/dependencies.py` | `agent_execute_limit` via de facade (ADR-033) |
| `tests/unit/governance/test_public_docs.py` | export naar `tmp_path` |
| 6 bronbestanden in de kernzone | 23 non-ASCII regels, waaronder een mojibake en een BOM |
| `.claude/rules/quality-gates.md` | mypy-baseline 52 met meetmethode |
| `docs/adr/036-...md` | OP-21 t/m OP-25 |
