STATUS: APPROVED WITH MINOR GAPS
Twee reviewers, allebei CHANGES_REQUESTED in ronde 1. Elke bevinding is eerst tegen de bron
nagemeten en daarna gerepareerd, met mutatiebewijs in beide richtingen. Drie punten blijven
bewust open en staan onderaan. De opruiming zelf is alsnog geleverd: de classifier weigerde
`git rm` tweemaal, waarna Rakesh het commando zelf heeft gedraaid. Daarbij kwam EEN
configuratie terug die niet weg had gemogen -- zie de nagekomen bevinding onderaan; die is
hersteld en er staat nu een bewaker op.

# Review BE-AGT-068 -- de catalogus zonder implementatie

Datum:     2026-09-25
Spec:      `docs/backend/features/BE-AGT-068-catalogus-zonder-implementatie.md`
Reviewers: code-reviewer (afgerond), quality-reviewer (afgerond)
Basis:     develop `dbbe8d9f`

---

## De zwaarste bevinding: mijn bewaker toetste TEKST waar STRUCTUUR hoort

De eerste versie las de klassen met `ast.walk` uit de broncode. De loader doet
`getattr(module, class_name)` -- dat leest de module-globals. Die twee zijn niet hetzelfde,
en de reviewer wees beide afwijkingsrichtingen aan:

- **te ruim:** `ast.walk` vindt een `ClassDef` op elke diepte, ook in een functiebody of
  onder `if TYPE_CHECKING:`. De guard staat dan GROEN terwijl de loader terugvalt.
- **te smal:** een re-export (`from .base import DunningSkill`) of alias laat `getattr`
  slagen maar maakt de guard ROOD.
- **en hij dekte maar de helft van de faalvorm:** de loader vangt `(ImportError,
  AttributeError)`. Een AST-parse ziet een ImportError per definitie nooit.

Dit is de faalvorm uit `.claude/rules/quality-gates.md` ("ik doorzocht TEKST waar ik
STRUCTUUR moest toetsen") plus mijn eigen gedocumenteerde valkuil
`valkuil_ast_walk_duikt_functiebodies_in`. Dat ik hem opnieuw maakte in een bewaker die
speciaal bedoeld was om een stille faalvorm te vangen, is het vermelden waard.

Gerepareerd naar `importlib.import_module` + `getattr`, naar het precedent in
`tests/architecture/test_pilot_wiring_implements_the_manifest_path.py:47-52`. Nieuwe
mutatie D4 (`DunningSkill` in een functiebody nesten) was bij de oude versie GROEN en is nu
ROOD. Looptijd bleef 1,6s.

## De tweede: een comment van mijn hand die niet waar was

De bewaker bevatte `class_name.replace("Agent", "Skill")` als KOPIE van `loader.py:195`,
terwijl de comment ernaast beweerde "niet nagebouwd maar aangeroepen". Dat gold alleen voor
`_normalize_agent_key`. Een latere wijziging van de loader-afleiding zou de bewaker groen
hebben gelaten terwijl elke skill terugvalt -- hij zou precies de wijziging overleven die hij
hoort te betrappen.

Gerepareerd door `_skill_class_name` als `@staticmethod` uit `get_agent_instance` te lichten
en op beide plekken aan te roepen. Mutatie D5 wijzigt die afleiding in de LOADER en maakt de
bewaker rood -- dat is het bewijs dat de koppeling echt is en niet beweerd.

## De derde: twee mutaties die mijn eigen tests ontmaskerden

Bij het mutatiebewijs op de loader-splitsing bleven L3 en L4 onbetrapt. Beide wezen op een
gat in mijn TEST, niet in de code:

- **L3** nam de `%s` voor de modulenaam weg en de test bleef groen. Oorzaak: de tekst van de
  `AttributeError` bevat zelf al `module '...' has no attribute '...'`, dus mijn assertie op
  de string was waargemaakt door de uitzondering en niet door de logregel. Nu toetst hij
  `record.args` -- structuur, geen tekst. De mutatie is herschreven naar het WEGHALEN van het
  argument en wordt dan wel betrapt, net als de nieuwe L3b voor de klassenaam.
- **L4** haalde de naamstoets (`e.name == module_name`) weg en bleef groen. Oorzaak: ik
  beweerde in een comment dat de splitsing ook een kapotte import BINNEN een skill vangt,
  zonder daar ooit een test voor te schrijven. Een onbewezen claim in een toelichting, de
  fout die `quality-gates.md` beschrijft onder "Een onbewezen oorzaak wordt nooit een
  WHY-comment". Die test bestaat nu.

Bij het schrijven van die derde test liep ik nog in een val die het vermelden waard is: een
`monkeypatch` op `importlib.import_module` voor ALLES sloopte ook het terugvalpad zelf, want
`BaseSpecialistAgent` importeert onderweg. De patch geldt nu alleen voor de ene modulenaam.

## Overige bevindingen, alle gerepareerd

| Bron | Bevinding | Actie |
|---|---|---|
| quality | `errors="ignore"` kan in een ASCII-only repo alleen iets verbergen | weggehaald op beide leesplekken |
| beide | bewaker glob't `*.yaml`, loader leest `.yaml` EN `.yml` | `.yml` erbij (vandaag 0 bestanden, maar het luik kon nooit rood worden) |
| code | `_class_name_uit` ging ervan uit dat de yaml een mapping is | `isinstance(raw, dict)`-toets |
| code | drempel `> 100` was een kaal getal | gemeten waarde 135 + datum in de foutmelding |
| code | docstring claimde "beide configuratievormen" zonder dekking | bereik expliciet: 135 gecontroleerd, alle PLAT, geneste tak ongedekt |
| code | geen `@pytest.mark.architecture` | toegevoegd |
| quality | onbewezen getal over een externe verzameling subagents | al vervangen door een lokaal herhaalbare meting voor de review binnenkwam |

## De bevinding die het meeste veranderde: de reparatie verandert gedrag

De codereview mat dat `DunningSkill.__init__` zijn configuratie uit
`skills/manifests/dunning.yml` bouwt en de catalogusconfiguratie NEGEERT. Mijn "reparatie"
maakt de yaml daarmee juist dood: runtime-id `mkb.admin_lite.dunningagent.001` wordt
`dunning`, department `admin_lite` wordt `finance_treasury`, en de toollijst wisselt. Zelf
nagemeten en bevestigd.

Dat stond nergens. Het staat nu in de spec (sectie 2.1) met de tabel erbij, en in de yaml
zelf als kop. De ruil gaat richting werkelijkheid: `debt_tracker` en `email_sender` bestaan
nergens in `src/` (nul treffers), en het manifest houdt de stopgap-zin die het
broker-profiel intact laat.

## Wat bewust NIET is opgelost

1. **De dode velden in `mkb_admin_lite_dunningagent.yaml` zijn gemarkeerd, niet verwijderd.**
   `ooda_profile` is onderwerp van BE-LLM-006 (fase 4); daar apart in snijden zou die
   beslissing vooruitlopen.
2. **De geneste configuratievorm is niet door een mutatie gedekt.** Er is vandaag geen
   geneste configuratie met een skillmodule, dus zo'n mutatie is niet te maken zonder een
   kunstmatig bestand. Het bereik staat expliciet in de docstring.
3. **De sleutelafleiding `.replace("agent", "")` is niet gerepareerd.** Dat is de
   onderliggende oorzaak en een gedragswijziging in productiecode; hij krijgt een eigen knip.
   Gemeten voorwerk ligt klaar in
   `docs/agent-briefs/generated/2026-09-25-sprint-dag-de-sleutelafleiding-knipt-blind.md`:
   2 sleutels veranderen, 0 daarvan in `domain_packs.yaml`, 0 letterlijke aanroepers.

## Devil's Advocate -- waarom dit alsnog faalt

De bewaker raakt 135 van de 289 configuraties. De andere 151 vallen er per ontwerp buiten en
blijven stil terugvallen op een generieke agent. Deze wijziging maakt dus precies het deel
zichtbaar dat al werkte, en laat het grote gat ongemoeid -- hij VOELT als afdekking terwijl
hij de helft van de catalogus niet raakt. De splitsing in 2.3 dempt dat (een module die
bestaat maar niet levert, klinkt nu wel), maar zolang de opruiming geblokkeerd is, is "151
vermeldingen die niets doen" nog steeds de grootste faalvorm in deze catalogus en is geen
enkele bewaker daar een vervanging voor.

Tweede: de drempel 135 zakt bij elke consolidatie van skills. Zodra iemand hem "even
aanpast" zonder meting is de zelfcontrole een ratel zonder reden per regel geworden.


---

## Nagekomen bevinding (na de review, tijdens de uitvoering)

`config/agents/critic_agent.yaml` is meeverwijderd en moest terug. Mijn analyse controleerde
DRIE manieren waarop een catalogusvermelding in gebruik kan zijn -- een skillmodule, een
klasse in `agents/departments/`, een verwijzing in `domain_packs.yaml` -- en miste de
vierde: code die de yaml rechtstreeks op pad opent (`src/core/agents/critic_agent.py:39`).

De faalvorm is de ergste soort. `_load_critic_agent_yaml` vangt `FileNotFoundError`, logt een
waarschuwing en geeft `{}` terug; zonder schema keurde `OutputSchemaValidator` daarna alles
goed (gemeten: `passed=True, score=1.0, issues=[]`). Drie bestaande tests vielen om. Zonder
die tests was een validator die niets meer valideert stil in productie beland.

Hersteld. Nieuwe bewaker `tests/architecture/test_een_yaml_die_code_bij_naam_noemt_bestaat.py`
(146 namen, 143 resolven, 3 gedateerde uitzonderingen, 5 mutaties betrapt). Die bewaker werd
op zijn beurt betrapt door `test_a_test_never_runs_git_against_another_repo.py`: hij riep
`git` aan zonder de `GIT_*`-omgeving te wissen.

**Wat dit zegt over de methode, niet over deze ene fout:** ik had drie manieren opgesomd en
niet gevraagd of de lijst volledig was. Een opsomming die je zelf maakt voelt compleet; de
enige toets is meten of er een vorm bestaat die je niet hebt opgeschreven. Dat is wat de
nieuwe bewaker nu doet -- hij vraagt niet "staat deze configuratie op mijn lijst" maar "noemt
code een yaml die niet bestaat".
