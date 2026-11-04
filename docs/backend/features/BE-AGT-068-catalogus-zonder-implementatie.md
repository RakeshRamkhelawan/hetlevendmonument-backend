# BE-AGT-068 -- De catalogus zonder implementatie, en de skill die nooit laadde

Status:   DEELS GELEVERD (de opruiming zelf is geblokkeerd, zie "Wat NIET is geleverd")
Datum:    2026-09-25
Basis:    develop `dbbe8d9f`
Domein:   backend (agentcatalogus)
Aanlei.:  vraag van Rakesh -- "haal de agents eruit die door klanten niet gebruikt worden"

---

## 1. De meting

`config/agents/` bevat 289 yaml-configuraties. De loader
(`src/core/als/agents/loader.py::get_agent_instance`) leidt uit `class_name` een sleutel af
met `_normalize_agent_key` (`class_name.lower().replace("agent", "")`), importeert
`src.core.als.agents.skills.<sleutel>` en zoekt daarin de klasse
`class_name.replace("Agent", "Skill")`. Lukt dat niet, dan valt hij terug op
`BaseSpecialistAgent` met een `logger.debug`.

Gemeten op `dbbe8d9f`, met beide configuratievormen (plat met `agent_id`, genest met `agent:`):

| Herkomst | Aantal |
|---|---|
| Skillmodule EN de gezochte klasse aanwezig | 134 |
| Klasse in `agents/departments/`, niet via de loader bereikbaar | 3 |
| Skillmodule aanwezig, gezochte klasse ONTBREEKT | 1 |
| Geen enkele implementatie | 151 |
| **Totaal** | **289** |

Die tabel is de stand OP `dbbe8d9f`, dus VOOR de reparatie in 2.1. Na die reparatie
wordt het 135 met module en klasse en 0 met een ontbrekende klasse; elk getal verderop
dat 135 noemt is dus de stand NA de fix. Beide zijn nagemeten door een Gate 2-reviewer.

De verdeling valt vrijwel samen met de schrijfwijze van de afdeling: afdelingen in
kleine letters (`it_security`, `sales_marketing`, de `zzp_`-reeks) tellen 139
configuraties waarvan er 135 zijn gebouwd; afdelingen met hoofdletters ("Core Platform",
"Software Engineering", "Mobile Engineering") tellen er 150 waarvan 3.

Wat die 151 zijn, met een naamsfilter op de weg-lijst gemeten: 33 dragen een naam uit de
wereld van programmeergereedschap -- `CppPro`, `CsharpPro`, `GolangPro`, `RustPro`,
`ScalaPro`, `ElixirPro`, `PhpPro`, `RubyPro`, `JavaPro`, `SqlPro`, `ApiDocumenter`,
`Debugger`, `AndroidDeveloper`, `IosDeveloper`, `UnityDeveloper`, `Web3Developer`, en
`MinecraftBukkitPro`. Die laatste is een agent voor Minecraft-serverplugins in een
platform dat bedrijfsprocessen automatiseert; er is geen lezing waarin een klant die
afneemt. Het filter is ruwweg op achtervoegsel (`*Pro`, `*Developer`, `*Engineer`) en
vangt daardoor ook `HrPro`, dat zakelijk KAN zijn -- het getal 33 is een indicatie van de
herkomst van deze lijst, geen tweede criterium. Het criterium voor verwijdering blijft
uitsluitend: er is geen implementatie, dus een klant kan hem niet gebruiken.

**Veiligheidscontrole.** `config/domain_packs.yaml` noemt 124 unieke `agent_id`-waarden.
Alle 124 staan in de blijf-lijst en NUL in de weg-lijst. De controlegroep (124) bewijst dat
de controle werkt; zonder die tweede getal is nul treffers niet te onderscheiden van een
kapot commando.

## 2. Wat WEL is geleverd

### 2.1 De skill die nooit laadde

`config/agents/mkb_admin_lite_dunningagent.yaml` had `class_name: "DunningAgentAgent"` --
een dubbel achtervoegsel. `.replace("agent", "")` haalt BEIDE weg, dus de sleutel werd
`dunning`, de module `skills/dunning.py` werd gevonden, en daarin werd
`DunningSkillSkill` gezocht. Die bestaat niet; de klasse heet `DunningSkill`. Gevolg: een
volledig werkende skill werd nooit geladen en het enige spoor was een `logger.debug`.

Gerepareerd naar `DunningAgent`, in lijn met de buren in dezelfde afdeling
(`ReceiptScannerAgent`, `VATComplianceAgent`). Geverifieerd: sleutel `dunning`, klasse
`DunningSkill` wordt gevonden.

**Dit verandert gedrag, en dat stond eerst nergens.** Een Gate 2-reviewer wees het aan en ik
heb het zelf nagemeten: `DunningSkill.__init__` (`skills/dunning.py:20-25`) bouwt zijn
configuratie uit `skills/manifests/dunning.yml` en NEGEERT de catalogusconfiguratie die de
loader meegeeft (die belandt via `config.update(kwargs)` onder de sleutel `"config"`). Wat
er dus vanaf nu anders is:

| veld | voor (generieke agent + catalogus-yaml) | na (DunningSkill + manifest) |
|---|---|---|
| runtime-id | `mkb.admin_lite.dunningagent.001` | `dunning` |
| department | `admin_lite` | `finance_treasury` |
| allowed_tools | `debt_tracker`, `email_sender` | `query_database`, `calculate`, `generate_report`, `send_notification`, `search_documents` |

Alles wat op het runtime-id sleutelt -- auditlog, geheugennamespace, ToolBroker-profiel --
ziet vanaf nu een andere agent. **De ruil gaat richting werkelijkheid, niet ervandaan:**
`debt_tracker` en `email_sender` bestaan NERGENS in `src/` (gemeten, nul treffers), en het
manifest bevat nog de stopgap-zin "without attempting a TOOL_CALL", dus er ontstaat geen
gat in een broker-profiel. De nu dode velden in die yaml zijn ter plekke gemarkeerd; ze
opruimen raakt ook de `ooda_profile`-vraag uit BE-LLM-006 en hoort in die knip.

### 2.2 De bewaker

`tests/architecture/test_een_bestaande_skillmodule_heeft_ook_zijn_klasse.py` eist dat elke
configuratie waarvan de skillMODULE bestaat, ook de klasse OPLEVERT die de loader erin
zoekt. Hij doet daarvoor wat de loader doet: `importlib.import_module` gevolgd door
`getattr`.

**De eerste versie deed dat NIET en was hol.** Die las de klassen met `ast.walk` uit de
broncode -- TEKST waar STRUCTUUR hoort, de faalvorm waar `.claude/rules/quality-gates.md`
een hele paragraaf aan wijdt, en dit keer met mijn eigen gedocumenteerde valkuil
`valkuil_ast_walk_duikt_functiebodies_in` erbij. Een Gate 2-reviewer wees aan dat hij in
twee richtingen van `getattr` afweek: te ruim (een klasse genest in een functiebody werd
gevonden terwijl de loader alsnog terugvalt) en te smal (een re-export of alias op
moduleniveau laat `getattr` slagen maar maakte de bewaker rood). De mutatie die dat
aantoont -- `DunningSkill` in een functiebody nesten -- bleef bij de eerste versie GROEN en
is bij de huidige ROOD.

Beide afleidingen worden AANGEROEPEN, niet nagebouwd: `_normalize_agent_key` en de nieuwe
`_skill_class_name`. Die tweede is voor deze wijziging uit `get_agent_instance` gelicht,
omdat de bewaker anders een KOPIE van `class_name.replace("Agent", "Skill")` bevatte en dus
precies de wijziging zou overleven die hij hoort te betrappen. Mutatie D5 bewijst dat de
koppeling echt is.

Verder: de bewaker leest `.yaml` EN `.yml` zoals `_load_agents` dat doet (vandaag 0
`.yml`-bestanden, maar het was een luik dat nooit rood kon worden), en hij leest zonder
`errors="ignore"` -- in een ASCII-only repo kan die vlag niets redden en wel iets
verbergen.

Bewust smal: configuraties ZONDER module blijven toegestaan. Dat is een andere kwestie (een
catalogusvermelding zonder implementatie) en die bewaker hoort pas te bestaan als de 151
weg zijn -- anders is hij per definitie rood en legt hij elke merge stil.

De zelfcontrole `gecontroleerd >= 100` vangt een bewaker die per ongeluk niets meer
bekijkt. Gemeten stand 2026-09-25: 135, dus 35 marge. Dat getal en die datum staan in de
foutmelding, zodat een latere lezer een daling kan onderscheiden van opruiming.

**Eerlijk over het bereik:** die 135 zitten ALLE in de platte configuratievorm. Geen enkele
geneste configuratie heeft vandaag een skillmodule, dus de geneste tak van `_class_name_uit`
staat er voor de toekomst en is NIET door een mutatie gedekt. Dat staat ook in de docstring;
de eerste versie beweerde daar "voor beide configuratievormen" zonder die nuance.

**Mutatiebewijs, zes mutaties, alle zes betrapt:**

| # | Mutatie | Uitkomst |
|---|---|---|
| D1 | `class_name` terug op `DunningAgentAgent` (de echte bevinding) | ROOD |
| D2 | `DunningSkill` hernoemd in `skills/dunning.py`, configuratie ongemoeid | ROOD |
| D3 | `SKILLS_DIR` naar een niet-bestaande map (zelfcontrole) | ROOD |
| D4 | `DunningSkill` GENEST in een functiebody -- groen bij de ast.walk-versie | ROOD |
| D5 | `_skill_class_name` gewijzigd in de LOADER (de kopie-val) | ROOD |
| D6 | TEGEN: configuratie zonder skillmodule toegevoegd | GROEN -- blijft smal |

### 2.3 De stille terugval, gesplitst in plaats van luid gemaakt

Beide Gate 2-reviewers noemden onafhankelijk dezelfde goedkoopste maatregel: maak
`loader.py` bij de terugval luid in plaats van `logger.debug`. Het bezwaar was dat dat
vandaag 151 waarschuwingen per cataloguslading geeft.

Dat bezwaar geldt maar voor EEN van de twee gevallen, en die zagen er alleen hetzelfde uit
omdat ze samen werden afgevangen (`except (ImportError, AttributeError)`):

* **de skillmodule bestaat niet** -- de bekende stand voor 151 vermeldingen. Blijft `debug`.
  Herkend aan `ModuleNotFoundError` waarvan `e.name` exact de gezochte modulenaam is.
* **de module bestaat wel maar levert de klasse niet op, of is zelf kapot** -- altijd een
  defect. Nu `logger.warning`, met de module- EN de klassenaam als eigen argumenten, zodat
  je niet hoeft te raden welke van de twee namen fout is.

Die tweede tak is precies de vorm die `DunningAgentAgent` onzichtbaar hield, en hij dekt
ook de ImportError-helft die een reviewer terecht als blinde vlek van de bewaker aanwees:
een skill die op zijn EIGEN import stukloopt viel voorheen weg tussen de 151.

Drie gedragstests in `tests/unit/als/agents/test_de_loader_meldt_een_kapotte_skill_luid.py`,
vijf mutaties, alle vijf betrapt -- zie sectie 6.

## 3. Wat NIET is geleverd, en waarom

**De opruiming IS uitgevoerd, door Rakesh zelf.** `git rm` is twee keer geweigerd door de
auto-mode-classifier als onomkeerbare bulkverwijdering; die weigering is technisch en niet
met een mondelinge toestemming op te heffen. Rakesh heeft het commando daarop zelf gedraaid,
met de lijst die ik had voorbereid. Twee dingen daarover zijn het vastleggen waard.

**Het overdrachtsbestand was eerst stuk, en het faalde misleidend.** `Path.write_text`
gebruikt op Windows universele regeleindes, dus de padenlijst kreeg CRLF, en
`git rm --pathspec-from-file` rekent zo'n regeleindeteken tot het pad. Mijn controlelus
meldde 151 van 151 paden "ONTBREEKT" terwijl `git ls-files` in hetzelfde commando 289
bestaande configuraties telde. Zonder dat tweede getal ernaast was de conclusie "ze zijn al
weg" geweest -- het omgekeerde van de waarheid. Herschreven met expliciete LF voordat het
commando werd afgegeven.

**En de markdown moest mee.** `src/core/agents/*.md` bevat de BRON waaruit
`scripts/generate_agent_yaml.py` deze configuraties maakt; het zijn letterlijk Claude
Code-subagentdefinities (`cpp-pro.md` opent met "Use PROACTIVELY for C++ refactoring"). Van
de 77 hoorden er 63 bij een verwijderde configuratie. Ze laten staan zou twee dingen doen:
`test_g1_markdown_agents_are_covered_by_loaded_catalog` rood maken, en -- erger -- de eerste
generator-run zou alle 151 configuraties terugzetten. Ook verwijderd.

Eindstand: **289 -> 139 configuraties** en **77 -> 14 agentdefinities** (plus een geneste
`SKILL.md`, die `git ls-files 'src/core/agents/*.md'` meetelt en `Path.glob('*.md')` niet).

### 3.1 Een configuratie kan op VIER manieren in gebruik zijn, en ik controleerde er drie

`config/agents/critic_agent.yaml` ging mee en moest terug. Die vermelding heeft inderdaad
geen skillmodule -- maar `src/core/agents/critic_agent.py:39` opent hem RECHTSTREEKS op pad,
buiten `EnterpriseCatalogLoader` om. Mijn vooronderzoek keek naar een skillmodule, een klasse
in `agents/departments/` en een verwijzing in `domain_packs.yaml`. Die vierde vorm stond niet
op de lijst.

Het faalde bovendien precies zoals dit project overal vreest: `_load_critic_agent_yaml` vangt
`FileNotFoundError`, logt een waarschuwing en geeft `{}` terug. Zonder schema keurde
`OutputSchemaValidator` daarna ALLES goed -- gemeten `passed=True, score=1.0, issues=[]`.
Drie tests vielen om; zonder die tests was een validator die niets meer valideert
onopgemerkt gebleven.

Hersteld, en er staat nu een bewaker op de algemene vorm:
`tests/architecture/test_een_yaml_die_code_bij_naam_noemt_bestaat.py` eist dat elke
yaml-bestandsnaam die code in `src/` hardgecodeerd noemt, ook bestaat. Gemeten: 146 namen,
143 vinden hun bestand, 3 gedateerde uitzonderingen met een reden. Vijf mutaties, alle vijf
betrapt, inclusief de tegenrichting dat een glob als `*.yaml` geen bestandsnaam is.

**Zoek die vierde vorm op de BESTANDSNAAM, niet op het pad.** De eerste versie van deze
regel gaf `git grep -nE "config/agents/[a-z0-9_-]+.ya?ml" -- src/` als commando en dat geeft
NUL treffers: `critic_agent.py` bouwt zijn pad op uit losse stukken. Het werkende commando
is `git grep -nE '"[a-z0-9_-]+.ya?ml"' -- src/` (10 bestanden, `critic_agent.py` erbij); de
bewaker doet het via de AST en vindt daarmee ook een naam die over regels is afgebroken.

Die bewaker werd zelf betrapt door een bestaande bewaker: hij riep `git` aan zonder de
`GIT_*`-omgeving te wissen, en onder de pre-push hook wint `GIT_DIR` van `cwd`. Dat heeft dit
project eerder een halve dag gekost; `test_a_test_never_runs_git_against_another_repo.py`
vond het binnen een uur.

**En er is een voorwaarde die ik pas NA de weigering heb gevonden.** De pre-commit hook van
deze commit draaide `tests/unit/test_g1_yaml_validation.py` en daar staat een drempel op het
AANTAL catalogusvermeldingen. Gemeten:

| Assertie | Nu | Na verwijdering van 151 |
|---|---|---|
| `agent_count >= 285` (tweemaal) | 289 | **138 -- BREEKT** |
| `agent_count + pack_count >= 300` | 369 | **218 -- BREEKT** |
| `pack_count >= 80` | 80 | 80 -- haalt het |

Die drempels tellen catalogusREGELS, niet werkende agents. Een test die eist dat er minstens
285 agents laden terwijl 151 daarvan lege hulzen zijn, verdedigt precies de holle catalogus
die deze knip opruimt -- het is dezelfde "succes zonder werk"-vorm die dit project overal
bestrijdt, maar dan in een test. Hij zou bovendien groen blijven als ALLE 289 hun
implementatie verloren.

**Opgelost, en los van de verwijdering.** `EnterpriseCatalogLoader.implemented_agent_keys()`
beantwoordt nu de vraag die de catalogus niet kon beantwoorden: welke vermeldingen leveren
echt een skill op. Hij stelt dezelfde vraag als `get_agent_instance` -- import plus `getattr`
-- zonder te instantieren. De drie G1-drempels toetsen daarop:

| Assertie | Nu | Na verwijdering van 151 |
|---|---|---|
| `len(implemented) >= 130` (tweemaal) | 135 | 135 -- houdt |
| `len(implemented) + pack_count >= 210` | 215 | 215 -- houdt |
| `pack_count >= 80` | 80 | 80 -- houdt |

Dat de getallen NIET bewegen is precies het punt: lege hulzen opruimen verandert niets aan
wat werkt. De post-verwijderingsstand is gesimuleerd door de 151 sleutels uit een geladen
catalogus te filteren, zonder een bestand aan te raken.

Let op het verschil tussen 135 en 138. De 138 zijn de configuraties die blijven; de 135 zijn
de configuraties die de LOADER kan leveren. Het verschil is de drie agents waarvan de klasse
alleen in `agents/departments/` bestaat en die `get_agent_instance` niet kan bereiken.

De drempel zelf kan niet bewijzen dat er het juiste geteld wordt -- 130 wordt door 289
vermeldingen net zo goed gehaald als door 135 implementaties. Drie aparte tests op
`implemented_agent_keys()` doen dat wel, elk mutatiegetest: een vermelding zonder module
telt niet, een module zonder de gezochte klasse telt niet, en een volledige vermelding telt
wel. Die derde mutatie (de klasse-controle weghalen) bleef onbetrapt tot de tweede test
bestond -- bij een ontbrekende module komt de code daar namelijk nooit.

Twee dingen hangen daaraan en zijn bewust NIET los geleverd:

- **Een bewaker die eist dat ELKE configuratie een implementatie heeft.** Die staat vandaag
  op 151 overtredingen en wordt groen zodra de opruiming landt. Zolang die er niet is,
  blijft de `debug`-tak uit 2.3 een bewuste stilte over 151 bekende gevallen -- geen
  ontdekking die we missen, wel een stilte die verdwijnt zodra de opruiming landt.

## 4. Een besluit dat ik heb genomen, met de meting erbij

De blijf-lijst bevat namen die als ontwikkelaarsgereedschap lezen: `PythonPro`,
`TypeScriptPro`, `FastAPIPro`, `TestAutomator`, `CloudArchitect`, `KubernetesArchitect`,
`TerraformSpecialist`. De opdracht luidde "het moeten echte zakelijke agents zijn", dus die
verdienden een eigen toets.

Gemeten in `domain_packs.yaml`: ze zitten in VERKOCHTE bundels --
`product.fullstack_launch`, `product.api_first`, `it.cloud_migration`,
`it.k8s_optimization`, `it.terraform_shield`, `data.mlops_hardening`. Software-oplevering en
IT-beheer zijn hier dus een productlijn, geen restant. **Besluit: de blijf-lijst blijft
ongemoeid.** Vier namen staan in nul bundels (`DjangoPro`, `JavaScriptPro`, `CodeReviewer`,
`AutoDevOps`); die zijn WEL gebouwd en horen bij een bundel die er plausibel bijkomt, dus ze
weghalen zou bouwwerk vernietigen voor een besparing van vier bestanden.

## 5. Twee correcties op eigen eerdere cijfers

- Ik meldde eerder 138 gebouwd via twee routes. Een tussenmeting gaf 134 doordat mijn
  telling `departments/` alleen op de BOVENSTE laag bekeek; de agentklassen zitten in
  submappen. Met `rglob` komt het weer op 137 + de dunning-reparatie = 138. De eerste
  uitkomst was juist, de tussenmeting was de onvolledige.
- Mijn eerste `domain_packs`-controle gaf nul treffers MET een nul-controlegroep. Dat was
  geen bevinding maar een kapot commando: ik zocht op sleutelnamen `agents`/`members`,
  terwijl de structuur `packs[].steps[].agent_id` is.

## 6. Verificatie

```text
nulmeting   : 118 passed, 3 xfailed   (catalogus-, pack- en agent-endpointtests)
nameting    : 119 passed, 3 xfailed   (+1 = de nieuwe bewaker)
na Gate 2   : 546 passed              (tests/architecture/<bewaker> + tests/unit/als/agents/)
ruff        : All checks passed
mypy        : Total errors 0, baseline 0
pyright     : 0 errors
Any-ratel   : baseline 7050, gemeten 7050
mutaties    : 6 van 6 op de bewaker, 5 van 5 op de loader, beide richtingen
```

`tests/als/test_41_agent_organogram.py` is uit de nulmeting gelaten: die map vraagt de
testdatabase, valt buiten de testpoort, en leest geen yaml (gecontroleerd).

## 7. Gate 2 -- wat de reviewers vonden

Beide reviewers: CHANGES_REQUESTED in ronde 1. Elke bevinding is eerst zelf nagemeten tegen
de bron voordat ik hem aannam.

De codereview vond het zwaarste punt tweemaal: de bewaker toetste TEKST waar STRUCTUUR
hoorde (`ast.walk`), en hij bevatte een KOPIE van de klassenaam-afleiding terwijl een
comment beweerde dat hij die aanriep. Die comment was half onwaar en van mijn hand. Beide
gerepareerd, met een nieuwe mutatie per geval.

De kwaliteitsreview vond `errors="ignore"` (kan in deze repo alleen iets verbergen), het
`.yaml`-tegenover-`.yml`-luik, en een onbewezen getal in de doc over een externe verzameling
subagents. Dat laatste had ik al vervangen door een lokaal herhaalbare meting voordat de
review binnenkwam.

**Twee mutaties bleven in de eerste ronde onbetrapt en dat wees op gaten in MIJN tests, niet
in de code.** De assertie dat de waarschuwing de modulenaam noemt, werd al waargemaakt door
de tekst van de `AttributeError` zelf ("module '...' has no attribute '...'") -- ik toetste
dus tekst die er toevallig stond. Nu toetst hij `record.args`, wat bewijst dat de logregel
die namen bewust meegeeft. En ik beweerde in een comment dat de splitsing ook een kapotte
import BINNEN een skill vangt zonder dat ooit te testen; die test bestaat nu.

Niet overgenomen: het voorstel om de dode velden in de dunning-yaml te VERWIJDEREN. Die
velden raken de `ooda_profile`-vraag uit BE-LLM-006; ze zijn gemarkeerd met een verwijzing
naar het manifest dat werkelijk geldt.

---

## Trainingssamenvatting

### Stroom 1 -- een agent uit de catalogus starten die WEL een implementatie heeft

- Actor: de pack-orchestrator (`src/core/als/enterprise/packs.py`), namens een tenant.

- Voorwaarde: er is een configuratie in `config/agents/` waarvan de `class_name` via
`_normalize_agent_key` naar een bestaande module in `src/core/als/agents/skills/` leidt, en
die module levert de klasse op die `_skill_class_name` eruit afleidt.

- Actie: `EnterpriseCatalogLoader.get_agent_instance(agent_key, tenant_id)`.

- Systeemreactie: de loader importeert de skillmodule, haalt de klasse op met `getattr` en
instantieert die met de catalogusconfiguratie en het tenant-id.

- Succes: de aanroeper krijgt de SPECIFIEKE skill terug. Let op: een skill met een eigen
manifest (zoals `DunningSkill`) bouwt zijn configuratie uit dat manifest en negeert de
catalogusrij -- afdeling, toollijst en runtime-id komen dan uit het manifest.

- Fout: geen. Dit is het gelukte pad.

- Uitzonderingen: geen.

### Stroom 2 -- een catalogusvermelding zonder implementatie

- Actor: dezelfde.

- Voorwaarde: er is wel een configuratie maar geen module
`src/core/als/agents/skills/<sleutel>.py`. Dat geldt vandaag voor 151 van de 289
configuraties.

- Actie: dezelfde aanroep.

- Systeemreactie: `importlib.import_module` gooit een `ModuleNotFoundError` waarvan `e.name`
exact de gezochte modulenaam is. De loader herkent dat als de bekende stand, schrijft EEN
regel op `debug`-niveau en valt terug op `BaseSpecialistAgent`.

- Succes: de aanroeper krijgt een werkend maar GENERIEK object terug. Dat is bewust: zonder
terugval zou een halve catalogus elke pack laten crashen.

- Fout: er is geen foutmelding, en dat is het bekende risico -- de aanroeper kan niet zien dat
hij iets generieks heeft gekregen. Daarom is de opruiming van die 151 de eigenlijke
oplossing en niet een luidere melding.

- Uitzonderingen: wie wel wil weten of hij de specifieke skill kreeg, toetst het type van het
teruggegeven object; de basisklasse kent skill-specifieke methoden niet.

### Stroom 3 -- de implementatie bestaat maar levert zijn klasse niet op

- Actor: dezelfde.

- Voorwaarde: de module bestaat, maar de gezochte klasse ontbreekt (verkeerde `class_name` in
de configuratie, of een hernoemde klasse), OF de module loopt zelf stuk op een import.

- Actie: dezelfde aanroep.

- Systeemreactie: de loader herkent dat dit GEEN ontbrekende module is en schrijft een
`warning` met de modulenaam, de gezochte klassenaam, het agent-id en het uitzonderingstype
als eigen logargumenten. Daarna volgt dezelfde terugval op `BaseSpecialistAgent`.

- Succes: het systeem blijft draaien EN de storing is zichtbaar in de logs van elke omgeving
die op `warning` logt.

- Fout: dit is altijd een defect. De melding noemt beide namen, zodat direct duidelijk is of
de configuratie of de klasse fout is.

- Uitzonderingen: een `TypeError` in de constructor van de skill valt hier NIET onder -- die
wordt niet gevangen en gooit door. Dat is opzettelijk: een skill die niet te construeren is,
is geen catalogusprobleem.
