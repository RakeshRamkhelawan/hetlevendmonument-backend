# De agentwerkwijze -- hoe we willen werken

> Vastgelegd 2026-09-27, tijdens het opnieuw inrichten van `.claude/`.
> Dit document beschrijft de BEDOELDE werkwijze en wat er nog voor nodig is.
> Het is geen uitvoerplan en geen bewijs dat iets werkt.

## Lees eerst deze twee

Dit document staat NIET op zichzelf. Er lag al materiaal, en dat is hier niet opnieuw
opgeschreven:

| Document | Wat erin staat | Stand |
|---|---|---|
| `docs/reports/AGENT-WORKFLOW-VOORSTEL-2026-09-19.md` | acht gemeten gaten met per gat een mechanisme en de kosten | geschreven 2026-09-19, **nooit uitgevoerd** |
| `docs/reports/AGENT-WORKFLOW-ONDERZOEK-2026-09-19.md` | het onderzoek waar dat voorstel op rust | idem |
| `docs/agent-briefs/REGIE-WERKAFSPRAKEN.md` | 208 regels werkafspraken onder regie | bestaat |
| `.claude/agents/regie.md` | 317 regels rolbrief voor de regie | bestaat, tweemaal overtreden |

**Waarschuwing voor de volgende lezer, en het is een gemeten fout.** Op 2026-09-27 is een
deel van het onderzoek van 19 september opnieuw gedaan zonder dat iemand wist dat het er
al lag. Twee van de acht gaten uit dat voorstel -- "de instructielaag verwijst naar dingen
die niet bestaan" en "de schrijver van een brief is ook de controleur" -- zijn die dag
opnieuw "ontdekt". Kijk hier dus eerst, voor je gaat onderzoeken.

---

## 1. De werkwijze zoals Rakesh hem beschrijft

1. Rakesh stelt een vraag, of geeft een opdracht en zegt wie de regie heeft.
2. Bij een **vraag** antwoordt de agent gewoon, zoals een chatbot. Verder niets.
3. Bij **regie** begint de meer-agent-werkwijze:
   - de regie kijkt eerst waar het werk staat (de takenlijst met status)
   - de regie haalt zijn persona op uit `.claude/agents/`
   - de regie pakt de eerstvolgende taak en maakt een sprint-brief
   - die brief wordt getoetst: voldoet hij aan de voorwaarden?
   - een andere sessie krijgt de dagbrief, met daarin **welke persona** hij aanneemt voor
     het bouwen, welke voor de review, enzovoort
4. Rakesh opent zelf de andere sessies. Dat kan de regie niet.

**Dit model klopt.** De documentatie van Claude Code bevestigt dat een rolbestand in
`.claude/agents/` op drie manieren werkt: als hulpje dat de regie aanroept, als teamlid,
en als rol waarmee een hele sessie start.

## 2. Wat er vandaag misgaat, in Rakesh' eigen woorden

> "ik open 3 chatsessies, en jullie communiceren al met elkaar, jij geeft sessie a of b een
> opdracht, en sessie a of b koppelt al terug naar jou, probleem was, jij had geen
> overzicht en ging zelf alles alsnog doen"

Dat is de kern. De communicatie werkt al. Het probleem is drieledig:

1. De regie **ziet niet** wat er loopt.
2. Dus **voelt** het alsof er niets gebeurt.
3. En de regie **kan** zelf bouwen, dus doet zij het zelf.

Een regie die niets mag en niets ziet, kan niets. Beide helften zijn dus nodig.

## 3. De drie kleine dingen die dit oplossen

Geen van drieen is groot. Twee zijn hooks van enkele tientallen regels, in hetzelfde
patroon als `.claude/hooks/session-start.sh` die er al staat.

### 3a. De stand komt naar de regie toe, niet andersom

Een `UserPromptSubmit`-hook injecteert bij **elke beurt** de stand. Gemeten op
2026-09-27: dit kan met het veld `additionalContext` in de JSON-uitvoer van de hook.

Wat erin hoort: welke claims open staan, wie de regie is, welke sessies draaien, en of er
ongecommit werk ligt.

**Waar dat vandaan komt, en waarom dat nu al kan:** de scripts werken rechtstreeks in
0 seconden:

```bash
python scripts/claim_op.py list      # exit 0, 0s
python scripts/push_gate.py whois    # exit 0, 0s
```

De MCP-laag ernaartoe geeft een time-out na 30 s (alle negen tools in
`mcp-server/tools/scripts.py`), maar die hoeft niet eerst gerepareerd te worden -- de hook
roept de scripts direct aan.

De claims staan in `<git-common-dir>/sanskritisetu-active-work.json`, dus elke worktree
ziet dezelfde lijst.

### 3b. De regie kan niet zelf bouwen

`.claude/agents/regie.md` zonder `Write` en zonder `Edit`. Bij een sessiebrede rol
vervangen de rolomschrijving, de toolbeperking en het model de standaard voor het hele
gesprek, en er is geen commando om er middenin uit te stappen.

Let op: de regie moet wel **briefen** kunnen schrijven. Die uitzondering wordt met een
hook op het pad afgedwongen, niet door schrijfrechten terug te geven.

### 3c. "Klaar" kan geweigerd worden

Een `Stop`-hook die met exit-code 2 weigert dat de beurt eindigt zolang er een claim open
staat, werk ongecommit is of een taak nog loopt.

Bij agent teams bestaat daarnaast `TaskCompleted`, die kan voorkomen dat een taak als
klaar wordt gemarkeerd.

## 4. De vier mechanismen, en wanneer je welk gebruikt

Gemeten uit de documentatie op 2026-09-27. Het verschil zit op een punt: **wie het plan
vasthoudt.**

| | Wie beslist wat er volgt | Waar tussenresultaten blijven | Schaal |
|---|---|---|---|
| Hulpje (subagent) | de agent, beurt voor beurt | het geheugen van de agent | enkele taken per beurt |
| Werkwijze (skill) | de agent, beurt voor beurt | idem | idem |
| Team (agent teams) | de lead, beurt voor beurt | gedeelde takenlijst | handvol langlopende sessies |
| **Werkstroom (workflow)** | **het script** | **scriptvariabelen** | tientallen tot honderden |

> "Een werkstroom verplaatst het plan naar code."

**Dit is het antwoord op drift.** Bij de eerste drie beslist de agent elke beurt opnieuw
wat er volgt -- precies waar het afdwaalt. In een werkstroom ligt de volgorde vast in een
script. De runtime laat `Date.now()` en `Math.random()` expres falen, zodat een herstart
dezelfde stappen herhaalt.

Een werkstroom kan bovendien onafhankelijke agents elkaars bevindingen laten
**tegenspreken** voordat ze gerapporteerd worden.

**Voorstel:** de keten (taak pakken -> brief -> toetsen -> bouwen -> beoordelen ->
accepteren) wordt een werkstroom, niet een reeks beslissingen van de regie.

## 5. Agent teams -- bestaat, staat uit, en vervangt wat wij zelf bouwden

Claude Code heeft een ingebouwd team-systeem: gedeelde takenlijst met drie statussen,
afhankelijkheden die vanzelf ontgrendelen, bestandsvergrendeling tegen race-condities, en
een postvak per teamlid. Opslag onder `~/.claude/teams/` en `~/.claude/tasks/`.

**Wij hebben dat zelf nagebouwd** (`claim_op.py` plus negen MCP-tools) en die laag is nu
stuk. Dat is drift in zijn zuiverste vorm.

Stand op 2026-09-27: `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` staat nergens aan, en geen van
de drie team-hooks is aangesloten.

**Wat ertegen pleit, eerlijk:**

- experimenteel, standaard uit
- ongeveer **zeven keer** de tokens van een gewone sessie (advies: Sonnet voor teamleden,
  klein houden, afsluiten als ze klaar zijn)
- teamleden vergeten soms af te vinken, wat afhankelijke taken blokkeert -- hoe vaak is
  niet gedocumenteerd
- geen herstel na hervatten: sessie weg is teamleden weg
- een team per sessie, geen geneste teams
- split-schermen werken niet in VS Code

**Openstaand besluit.** Niet nu nemen. De persona's uit paragraaf 6 zijn hoe dan ook
nodig, dus die keuze kan later zonder herbouw.

## 6. De persona's -- de eerstvolgende stap

De vier sessierollen die Rakesh bij het openen kiest: **vraag, bouwen, regie, accepteren.**

Daarnaast de hulprollen. Zes bestaan er al (vijf beoordelaars plus een schermenbouwer).
Zes ontbreken, en vijf daarvan hebben een tegenhanger in onze eigen applicatie:

| Ontbreekt | Waarom | Bestaat in de app als |
|---|---|---|
| architect | keuzes over meerdere domeinen | `technicalarchitect` |
| testspecialist | de bouwer schrijft zijn eigen tests niet | `testautomator` |
| acceptant | bedient de draaiende applicatie als klant | `qabugdetection` |
| database | migraties en ketens | `databaseadmin` |
| verkenner | pluist bestaande code uit voor je hem aanraakt | -- |
| tenant-isolatie | het P0-cluster en keten D van de meetlat | -- |

**Gemeten grond hiervoor:** onze applicatie heeft 135 werkende agents, waarvan 34
development-disciplines. We bouwen een product met een rollenmodel dat we zelf niet
gebruiken.

## 7. Wat er in een persona hoort

Uit de ECC-repository (`affaan-m/ECC`, 268k sterren) en de literatuur:

1. **Wat je met je handen kunt** -- de toolbeperking. Niet "je schrijft geen code" maar
   geen schrijfgereedschap hebben.
2. **Wat je eerst controleert** -- de vaste openingsronde.
3. **Wat je nadrukkelijk NIET doet** -- expliciet opgeschreven. Hun beoordelaar begint met
   "doe het werk niet over".
4. **Wanneer je stopt** -- geen voortgang na twee controlepunten, dezelfde fout die zich
   herhaalt, budget op.
5. **Wat je oplevert** -- de vorm van het antwoord.

En de regel die de altijd-geladen laag verkleint:

> "Instructies die maar een agent hoeft op te volgen, horen niet in de hoofdconfiguratie
> maar in het rolbestand van die agent -- met expliciete 'nooit doe X'-regels."

Bron: [AGENTS.md voor multi-agent systemen](https://www.betterclaw.io/blog/agents-md-multi-agent-best-practices).

## 7b. De verdeelsleutel -- wie voert de regel uit, die krijgt hem

> Vastgesteld 2026-09-27 na een vraag van Rakesh: "paragraaf 9 en 10, waarom moet dat erin
> staan? Volgens mij moet dit door de workers gedaan worden." Dat klopte, en het gold voor
> meer paragrafen dan die twee.
>
> **STATUS: NIET UITGEVOERD.** Dit is de analyse, niet de verhuizing. Rakesh, 2026-09-27:
> "we zijn denk ik nog niet klaar om jouw persona en rol waterdicht te maken."

### De regel

> **Wie voert deze regel uit? Die krijgt hem. Staat hij ergens anders, dan is het ruis --
> en ruis is waar naleving op stukloopt.**

Dit is dezelfde regel als in paragraaf 7, maar dan toegepast in plaats van geciteerd. Het
onderscheid dat hem bruikbaar maakt: **een brief lees je een keer, een persona ben je elke
beurt.** Daarom moet een persona klein zijn.

### De analyse van `.claude/agents/regie.md` (317 regels)

| # | Sectie | Wie voert het uit | Waar het hoort |
|---|---|---|---|
| 0 | wat je wel en niet bent | regie | **persona** -- dit is de grens zelf |
| 1 | openingsronde | regie | **persona**, kort |
| 2 | werk verdelen over drie assen | regie | **persona** -- doet niemand anders |
| 3 | de brief: vers gelezen, gestempeld met bestand:regel + hash | beide | **briefsjabloon** |
| 4 | niets aannemen op gezag, ook niet van een goede sessie | regie | **persona** -- kern van de rol |
| 5 | de poorten: `ruff`, `pyright`, `--fail-on-increase`, mutatiebewijs | **de bouwer** | **bouwer-persona** |
| 6 | volgorde bij meerdere sessies | regie | persona |
| 7 | push goedkeuren | regie | **al in `.claude/rules/git-safety.md`** -- dubbel |
| 8 | register en documentatie | beide | apart document |
| 8b | een brief draagt zijn metingen | beide | **briefsjabloon** |
| 9 | valkuilen | **gemengd** | zie hieronder |
| 10 | afvinklijst bij het afronden | regie | **de afrondcontrole (hook)**, niet het geheugen |
| 11 | de houding die dit vraagt | **iedereen** | CLAUDE.md of `.claude/SOUL.md` |

### Sectie 9 uitgesplitst

Twee van de zes valkuilen zijn algemeen en horen in `/valkuilen`, waar elke rol ze vindt:

- uitvoer door een pipe naar `tail` -- de foutcode is die van `tail`, niet van pytest
- repo-brede `grep` of `find` op Windows -- duurt 30 tot 60 minuten, gebruik `git grep`

Vier zijn echt van de regie en horen in de persona:

- een claim van een sessie of subagent overnemen zonder zelf na te meten
- zelf code schrijven tijdens de regie (je wordt auteur en goedkeurder tegelijk)
- een registerrij aanleggen voor iets dat in tien minuten te repareren is
- een instructie geven zonder de aanname eronder te meten

### Het duidelijkste geval was sectie 5, niet 9 of 10

Daar staan de commando's `ruff check src/`, `python -m pyright` en
`run_mypy_audit.py --fail-on-increase`. Dat zijn commando's voor wie ze draait: de bouwer.
De regie hoeft alleen te weten DAT ze gedaan zijn, en hoe een vervalste uitslag eruitziet.

Sectie 10 is wel degelijk regie-werk -- claims, worktrees en pushes doet niemand anders --
maar het is een afvinklijst voor het einde. Die hoort in de afrondcontrole uit paragraaf 3c
en niet in een tekst die onthouden moet worden.

### Wat er overblijft

Ongeveer een kwart van de 317 regels blijft over voor `.claude/agents/regie.md`:
secties 0, 1, 2, 4, 6 en vier van de zes valkuilen. De rest verhuist naar de bouwer, het
briefsjabloon, `/valkuilen`, CLAUDE.md, of naar gereedschap.

`.claude/agents/regie.md` blijft bestaan als naslagwerk met de metingen en de
data erbij. Er gaat dus niets verloren.

### Het gat dat de literatuur toevoegt en dat nergens stond

> "Een goed begrensde orchestrator kan een subagent starten die geen van zijn beperkingen
> heeft. Het beleid van de ouder gaat niet vanzelf over op het kind -- je delegeert
> impliciet ook je bevoegdheid."

Een regie zonder schrijfrechten die een hulpje start dat wel mag schrijven, heeft de grens
omzeild. Het tegengif uit dezelfde bron: een kind krijgt **alleen een deelverzameling van
de tools van de ouder**, een diepte-limiet van twee, en een kostenplafond dat voor elke
aanroep wordt gecontroleerd.

Dat hoort in de persona, en het staat in geen van de 317 regels.

Bron: [Your Multi-Agent System Has a Governance Blind Spot](https://dev.to/waxell/your-multi-agent-system-has-a-governance-blind-spot-heres-where-to-look-4jol),
[One Orchestrator, Many Agents, Many Prompts](https://medium.com/@lokesh.mulpuru/one-orchestrator-many-agents-many-prompts-1ed9241225dc).

## 7c. Het rollenontwerp -- gegrond op functiescheiding

> Vastgesteld 2026-09-27. Dit is het ONTWERP: welke rollen er moeten zijn en waarom.
> Niet de invulling, niet de bestanden.

### Het fundament is geen voorkeur maar een formele eis

Uit het onderzoek naar hoe softwarebedrijven werken:

> "Het review- en goedkeuringsproces moet worden uitgevoerd door iemand die de code niet
> heeft geschreven."
>
> "Er moet functiescheiding zijn tussen wie aan de ontwikkel- en testomgeving werkt en wie
> aan productie."

En, uit hetzelfde onderzoek: "een dubbele bouw-en-review-lus past functiescheiding toe op
autonome agents". Het principe wordt dus al op agents toegepast, niet alleen op mensen.

**Dat is de ordenende vraag.** Niet "hoeveel rollen is handig", maar: welke taken mogen
nooit door dezelfde partij worden gedaan. Gemeten aanleiding: op 2026-09-18 zette de regie
zes commits van eigen hand, waarvan er vier werden goedgekeurd door de auteur ervan.

Bronnen: [SDLC-beleid en functiescheiding](https://help.drata.com/en/articles/8002321-software-development-lifecycle-sdlc-policy-guidance),
[QA-rollen](https://www.altexsoft.com/blog/qa-engineering-roles-skills-tools-and-responsibilities-within-a-testing-team/),
[rollen in de SDLC](https://www.devopsschool.com/blog/list-of-all-job-roles-job-titles-in-software-and-it-companies/).

### De taakvolgorde bestaat al -- in `docs/agent-briefs/sprint-dag.md`

Die brief (698 regels) beschrijft de hele werkwijze al: elf taken in vaste volgorde, met
stopvoorwaarden, een definitie van klaar, en sinds 2026-07-03 geen backlog-optie meer.
Helemaal onderaan staat het mechanisme tegen schijnbewijs, daar sinds 2026-07-29:

> "Wordt uitgevoerd zonder aannames en zonder context uit deze sessie: de reviewer krijgt
> alleen de bestandspaden, commit-hashes en de testcommando's om zelf te draaien -- geen
> samenvattingen van wat 'al gecontroleerd is', geen kopie van jouw bevindingen, geen
> verwijzing naar eerdere GO-oordelen."

**Het ontwerp is dus niet nieuw. Wat ontbreekt is de koppeling taak -> rol.** Bovenaan die
brief staat een veld "Jouw rol" met daarin EEN persona (senior developer) voor alle elf
taken, terwijl die taken verschillende disciplines vragen.

### De rollen, afgeleid uit die elf taken

| Taak in de brief | Discipline | Bestaat |
|---|---|---|
| 0. baseline en impact-analyse | verkenner | nee |
| 1. rode tests schrijven | **QA / testspecialist** | **nee** |
| 2. review laag A | code reviewer | ja (vier stuks) |
| 3-6. de fixes | software engineer | alleen frontend |
| 7. groen verifieren | bouwer | -- |
| 8. regressiecheck | QA-engineer | nee |
| 9. feature docs | **technisch schrijver** | alleen een beoordelaar |
| 10. commit | bouwer | -- |
| taak 5 vandaag: migratie | **database-beheerder** | nee |
| final-approver brief | **onafhankelijke beoordelaar** | nee |
| de meetlat toetsen | **acceptant** | nee |

### Wat erbij moet, op volgorde van hardheid

**Deze drie eist de functiescheiding -- zonder deze is het niet waterdicht:**

1. **Testspecialist** -- schrijft de rode tests uit taak 1. Nooit dezelfde als de bouwer:
   wie bouwt en zijn eigen test schrijft, schrijft een test die zijn werk bevestigt. Zo
   ontstonden 37 holle bewakers die groen bleven onder precies de fout die ze moesten
   vangen.
2. **Onafhankelijke beoordelaar** (final approver) -- zonder context uit de bouwsessie.
   Staat al in de brief sinds 2026-07-29, bestaat nergens als rol.
3. **Acceptant** -- toetst de draaiende applicatie tegen `docs/meetlat.md`. Mag niet
   repareren wat hij afkeurt: wie een fout zelf mag oplossen, keurt hem te makkelijk goed.

**Deze drie zijn echte functies uit het bedrijfsleven die wij missen:**

4. **Architect** -- bij keuzes die meerdere domeinen raken (hoog niveau en laag niveau:
   modulelogica, datastructuren, API-contracten, databaseschema)
5. **Database-beheerder** -- migraties en ketens; er is een hele ADR over alembic
6. **Technisch schrijver** -- de feature docs en de gebruikershandleiding uit de meetlat

**En een die geen echte functie is maar wel werk scheelt:** de verkenner voor taak 0.

Met de zes bestaande komt dat op twaalf a dertien rollen: precies zoveel als er
disciplines in de keten zitten.

### Wat het NIET kost

Gemeten 2026-09-27: onze zes rolbeschrijvingen kosten samen **90 tokens** aan altijd
geladen context. De grens waarbij Claude Code waarschuwt ligt op 15.000. De INHOUD van een
rolbestand laadt alleen wanneer die rol draait.

**Correctie op een eerdere bewering in dit gesprek:** er is eerder gezegd dat meer rollen
de altijd geladen laag zouden verdrievoudigen. Dat was onjuist. Meer rollen kosten bijna
niets. Het argument tegen veel rollen is niet de prijs, maar dat een rol die je niet kunt
uitleggen wanneer je hem inzet, nooit wordt ingezet.

## 7d. Openstaande twijfels bij het rollenontwerp

> Rakesh, 2026-09-27: "jouw twijfels kunnen we later echt oplossen, sla ze op in het
> document." Ze staan hier zodat ze niet verdwijnen, NIET opgelost.

### Twijfel 1 -- wat roept de rollen straks aan? (de zwaarste)

Het patroon in dit project is niet dat er te weinig gemaakt wordt, maar dat wat gemaakt
wordt niet wordt aangeroepen. Gemeten op 2026-09-27:

- 12 van de 15 skills worden nergens in CLAUDE.md genoemd
- `quality-reviewer` stond in tien instructiebestanden als verplicht en bestond maandenlang
  niet
- 229 van de 435 scripts worden nergens aangeroepen

Zeven nieuwe rolbestanden zijn zeven nieuwe kandidaten voor diezelfde stapel, tenzij iets
ernaar wijst. Het enige wat dat kan is het veld "Jouw rol" in `sprint-dag.md`, en dat veld
kent nu een rol per DAG in plaats van per TAAK.

**Conclusie: de rollen en de aanpassing van het briefsjabloon horen bij elkaar.** Het een
zonder het ander levert bestanden op die niemand aanroept.

### Twijfel 2 -- toetsen we of een rol echt werkt?

Een rol werkt als hij drie dingen doet: hij wordt aangeroepen, hij doet wat er staat, en
hij KAN niet wat er niet mag. Dat laatste is meetbaar: geef de regie een schrijfopdracht en
kijk of hij weigert. Zonder die meting is een rolbestand een bordje.

Zeven rollen tegelijk maken levert zeven ongetoetste bestanden op.

### Twijfel 3 -- het formaat overnemen, niet de instellingen

De negen blokken waaruit VoltAgents definities bestaan zijn bruikbaar, maar hun rollen
hebben geen `Bash` omdat het planners zijn die een markdown-plan opleveren. Onze bouwer en
testspecialist hebben `Bash` wel nodig. De opbouw is overneembaar, de toolinstellingen niet.

### Twijfel 4 -- met welke rol beginnen

Voorstel bij de uitvoering: begin met EEN rol, toets of hij werkt, maak dan pas de rest.
De testspecialist is de kandidaat: de scherpste grens (schrijft tests, raakt geen
productiecode, dus met een mutatie te bewijzen), hij lost de scherpst gemeten faalvorm op,
en hij is nodig in taak 1 van elke sprint-dag.

De regie is de moeilijkste en dus niet de eerste: die grens is subtiel, want geen
productiecode maar wel briefen.

## 7e. Sessies: hoeveel, wie doet wat, en hoe je ze hergebruikt

> Vastgesteld 2026-09-27 in gesprek met Rakesh.

### De drieslag bij elke dagstart

Rakesh: "Stap 1 is altijd ook bij een dagstart: waar staan we nu, wat gaan we doen en wat
moet af zijn. Die 3 dingen moeten beantwoord zijn voordat je uberhaupt gaat dirigeren."

| Vraag | Bron |
|---|---|
| Waar staan we? | de werkvoorraad |
| Wat gaan we doen? | de werkvoorraad, geschift op urgentie |
| Wat moet af zijn? | **nog geen vastgestelde bron** -- zie hieronder |

**Openstaand:** de derde vraag heeft nog geen bron. Vermoeden: de definitie van klaar uit
`docs/agent-briefs/sprint-dag.md` samen met het bijbehorende scenario uit
`docs/meetlat.md`. Dat is niet bevestigd en het is niet de makkelijkste van de drie --
"af" is precies wat jarenlang te ruim is uitgelegd.

### Wie maakt de dagbrief

Het voorstel van 2026-09-19 (gat 7) koos: de regie schrijft, de ontvangende sessie
controleert, want die heeft er belang bij. Dat voorstel erkende zelf de zwakte: "kosten
nul, behalve discipline; hij hangt volledig van gedrag af en dat is de zwakste vorm van
borging die er is."

**Aangescherpt voorstel 2026-09-27, om een reden die daar niet stond.** Een goede dagbrief
bestaat uit twee soorten werk:

| Onderdeel | Wat het vraagt |
|---|---|
| welke taak, waarom nu, scope en grenzen, welke persona per taak | overzicht -- dit is regie-werk |
| de meting die het werk rechtvaardigt | **in de code duiken** |
| codefragmenten, vers gelezen, gestempeld met bestand:regel en commit-hash | **in de code duiken** |
| testcommando's en hun verwachte uitkomst | **in de code duiken** |

De onderste drie zijn het meeste werk en vullen precies het geheugen dat de regie nodig
heeft voor overzicht. De literatuur waarschuwt daarvoor: "de orchestrator is een
langlopende sessie; alles wat de ontwerpstap ophaalt blijft in die context voor elke
volgende beurt."

**Dat is Rakesh' klacht letterlijk:** een regie die voor elke brief de code in duikt, zit
na drie briefen vol code en heeft geen overzicht meer -- en gaat dan zelf doen.

**Voorstel:** de regie BEPAALT de brief (taak, scope, grenzen, persona's, wat af moet), een
aparte **brief-schrijver** VULT hem (meet, leest vers, stempelt). De regie toetst een
ding: dekt deze brief mijn opdracht? De ontvangende sessie mag hem alsnog weigeren als een
bewering geen commando draagt.

Dat is niet alleen functiescheiding maar contextscheiding: het zware leeswerk gebeurt in
een geheugen dat daarna weg mag.

### Hoeveel sessies

Een **hulpje** heeft geen sessie nodig: het werkt in een eigen geheugen en geeft antwoord
terug. Een **eigen sessie** is alleen nodig als de onafhankelijkheid echt moet, want een
hulpje krijgt altijd de opdracht van wie hem aanroept.

| Rol | Sessie of hulpje |
|---|---|
| brief-schrijver | hulpje van de regie |
| `code-reviewer`, `quality-reviewer`, `security-reviewer` | hulpjes van de bouwer (taak 2) |
| **testspecialist** | **sessie** -- schrijft de rode tests voor er gebouwd wordt |
| **bouwer** | **sessie** |
| **onafhankelijke beoordelaar** | **sessie** -- expliciet zonder context uit de bouwsessie |

**Drie naast de regie als je het waterdicht wilt. Twee is het minimum**, en dan laat je de
testspecialist weg -- waarmee de bouwer zijn eigen tests schrijft, precies de faalvorm die
37 holle bewakers opleverde.

Ze hoeven niet tegelijk open te staan: de keten is grotendeels sequentieel, dus meestal
staan er twee open (de regie plus wie aan de beurt is). Anthropic adviseert drie tot vijf,
met "drie gerichte teamleden presteren vaak beter dan vijf verstrooide". Vier in totaal zit
op de goede kant van die ondergrens.

### Een sessie mag van rol wisselen -- met een grens

Rakesh, 2026-09-27: een sessie koppelt terug als hij klaar is, en dan kan de regie een
nieuwe persona en taak toekennen. Dat klopt, en een eerdere bewering in dit gesprek dat een
rol vaststaat was op het verkeerde argument gebaseerd.

Er zijn twee niveaus, en alleen het eerste staat vast:

| | Hoe | Wat het oplevert |
|---|---|---|
| Rol bij het openen | `--agent` of de `agent`-instelling | harde grens: de sessie KAN bepaalde tools niet gebruiken; geen commando om te wisselen |
| Persona via de opdracht | een bericht met de rol erin | de sessie gedraagt zich ernaar; de tools blijven wat ze waren |

**Het bezwaar tegen hergebruik is niet de rol maar het geheugen.** De regel is daarom
smaller:

> Een sessie mag van rol wisselen, behalve naar een rol die het werk van zijn vorige rol
> moet beoordelen.

| Wissel | Mag | Waarom |
|---|---|---|
| testspecialist -> bouwer | ja | de kennis helpt; hij bouwt naar tests die er al liggen |
| bouwer -> volgende bouwtaak | ja | geen oordeel over eigen werk |
| bouwer -> beoordelaar | **nee** | hij zou zijn eigen werk goedkeuren |
| testspecialist -> beoordelaar | liever niet | hij kent de tests waarop geoordeeld wordt |

### Wat `/clear` precies doet -- opgezocht 2026-09-27

Uit de documentatie: "`/clear`: start fresh with an empty context. Claude Code saves the
previous conversation; resume it with `/resume`."

| | Na `/clear` |
|---|---|
| Het gesprek | weg uit het geheugen van de agent, maar **bewaard op schijf** en terug te halen met `/resume` |
| CLAUDE.md en de regels | laden opnieuw |
| De hooks | draaien opnieuw; de `SessionStart`-hook vuurt met de matcher `clear` |
| Een naam die je zelf gaf | blijft |
| Een automatisch verzonnen titel | vervalt |

**Gevolg voor de werkwijze:** een venster is te hergebruiken. Wis de context, geef een
nieuwe persona en taak, en de sessie is vers genoeg voor de eis uit `sprint-dag.md` --
geen samenvattingen, geen kopie van bevindingen, geen eerdere GO-oordelen. Er is dus geen
derde venster nodig als je bereid bent tussendoor te wissen.

**Niet vastgesteld:** of een rol die bij het openen is meegegeven (`--agent`) een `/clear`
overleeft. De documentatie zegt dat expliciet over hervatten, niet over wissen. Voor de
huidige werkwijze maakt het niet uit (de persona komt via de opdracht), maar het moet
gemeten worden voordat de harde toolgrens in gebruik gaat.

## 7f. Verse context zonder Rakesh, en wie er pusht

> Vastgesteld 2026-09-27. Aanleiding: Rakesh is niet altijd aanwezig, dus een werkwijze die
> op zijn handelingen leunt, staat stil zodra hij wegloopt.

### `/clear` kan niet programmatisch -- en dat was het verkeerde gereedschap

Opgezocht 2026-09-27: een agent kan `/clear` of `/compact` niet zelf uitvoeren. Dat is een
bekende beperking met drie open verzoeken bij Anthropic (issues 20267, 35150, 68127). Het
komt er voorlopig niet.

**Maar het hoeft ook niet.** Er zijn drie mechanismen die een verse context geven en die de
regie zelf kan starten:

| Mechanisme | Verse context | Wie start het |
|---|---|---|
| Hulpje (subagent) | ja -- eigen geheugen, krijgt alleen de opdracht | de regie |
| Teamlid | ja -- "de gespreksgeschiedenis van de lead gaat niet mee" | de regie |
| Werkstroom-agent | ja, per stap | een script |

De denkfout was te redeneren in "vensters die Rakesh opent". Een hulpje IS al een verse
sessie. De onafhankelijke beoordelaar uit `sprint-dag.md` kan dus een hulpje zijn, mits de
opdracht alleen paden, commit-hashes en testcommando's bevat -- geen samenvatting van wat
de bouwer vond.

### Het probleem dat daarvoor in de plaats komt

Als alles via hulpjes loopt, komt elk resultaat terug in het geheugen van de regie. Na drie
fases zit die vol, en dat is precies waar het vandaag misging.

**Oplossing, en hun rollen doen het al zo: de uitkomst gaat naar een BESTAND, niet naar de
regie.** Elke VoltAgent-rol levert een markdown-document op. Het hulpje meldt alleen
"klaar, het staat in `<pad>`". De volgende fase leest dat bestand, niet de samenvatting van
de regie.

Dat is tegelijk de overdracht en het contextbeheer.

### Wie pusht -- besluit Rakesh, 2026-09-27

> "de push wil ik best doen, zolang er iedere keer aparte worktrees worden gemaakt, ik push
> aan het einde van de dag alles in 1 keer naar develop. of tussendoor wanneer ik er ben."

Dat lost twee dingen op die niet in het ontwerp zaten:

1. **Rakesh wordt de onafhankelijke goedkeurder.** De regel "niemand keurt zijn eigen push
   goed" bestond omdat een sessie haar eigen werk niet mag doorlaten. Als Rakesh tekent, is
   dat probleem weg: hij is de enige partij zonder belang bij het landen. De regie hoeft
   dan geen tweede sessie meer te zoeken om goed te keuren.
2. **Een testronde per dag in plaats van per push.** Gemeten: een volledige testronde kost
   14,2 GB geheugen en liet de machine vastlopen (zie
   `project_machine_loopt_vast_op_commit_limiet`). Alles in een keer aan het eind betekent
   die ronde een keer over het werk van de hele dag.

**Voor de eis over aparte worktrees bestaat een kant-en-klaar veld:** een hulpje met
`isolation: worktree` krijgt automatisch een eigen kopie van de repo. Claude Code blokkeert
commando's waarmee hij naar de hoofdmap zou ontsnappen, en ruimt de kopie op als er niets
gewijzigd is. Dat scheelt handwerk en voorkomt achtergebleven worktrees zoals
`.claude/worktrees/ci-green-2026-05-19` (310 bestanden, 19 mei, nooit opgeruimd).

### Interlock 1 wordt vooraf aangekondigd -- eis Rakesh, 2026-09-27

> "Wanneer dit zich mogelijkerwijs voor zal gaan doen, wil ik vooraf op de hoogte gesteld
> worden, dan weet ik dat ik niet weg kan lopen van de pc"

**Voorzienbaar -- melden bij de dagstart.** Bij het schiften van de werkvoorraad is aan de
taak of de geraakte paden al te zien of interlock 1 speelt:

| Signaal | Waarom |
|---|---|
| `alembic/versions/`, `migrations/` | elke migratie kan een werkende `downgrade()` missen |
| `DROP`, `TRUNCATE`, `ALTER ... DROP COLUMN` | onomkeerbaar |
| secrets, sleutels, rotatie, `.env`-wijzigingen | onomkeerbaar en buiten de repo |
| gebruikersdata verwijderen of opschonen | onomkeerbaar |

De melding luidt dan: welke taak, waarom het interlock 1 raakt, en rond welk moment zijn
aanwezigheid nodig is. **Speelt er vandaag niets van, dan wordt dat ook expliciet gezegd**
-- dan weet hij dat hij de hele dag weg kan.

**Onvoorzien -- stoppen en melden.** Blijkt pas tijdens het bouwen dat er een migratie
nodig is, dan stopt de sessie en meldt. Niet doorwerken aan iets anders: dan staat Rakesh
later voor een keuze waarvan de context is weggezakt.

Deze eis staat ook in `CLAUDE.md` bij interlock 1, omdat hij altijd geladen moet zijn.

## 8. De anti-driftregel

Vastgesteld 2026-09-27 na een meting:

| Bestand | Gemaakt | Laatst gebruikt |
|---|---|---|
| `docs/SPRINT_TRACKER.md` | 13 april | 25 augustus |
| `docs/SPRINT-CANVAS.md` | 28 mei | 6 juli |
| `docs/6-Development/SPRINT-TRACKER.MD` | 10 april | 2 juli |
| `.claude/WORKING-CONTEXT.md` | **9 juni** | vandaag |

Er waren al twee sprint-trackers toen de canvas erbij kwam, en die drie waren nog in
gebruik toen `WORKING-CONTEXT.md` ontstond. Geen van de drie is ooit bewust gesloten.

**De regel:** voordat je een nieuw document, register of systeem aanmaakt, zoek je of er
al een is. Vind je er een, dan gebruik je die of je sluit hem expliciet met een reden.
Een nieuw bestand naast een bestaand is drift, ook als het nieuwe beter is.

### 8b. De tweede soort drift: van doel naar doel (gemeten 2026-09-28)

Hierboven gaat het over documenten. Deze gaat over aandacht, en hij is duurder.

Op 2026-09-28 dreef ik in een sessie minstens vier keer af. Van "controleer sprint-dag" naar
het repareren ervan; van daar naar `check_brief.py`; en aan het eind van "de workflow
verbeteren" naar "ik ga door met de volgende taak". **Elke afslag was op zichzelf
verdedigbaar** -- dat is wat deze vorm gevaarlijk maakt. Er was geen moment waarop een
duidelijk foute keuze viel. Bij elkaar opgeteld bepaalde de agent zelf waar we mee bezig
waren, en Rakesh moest vier keer bijsturen.

**De oorzaak is aanwijsbaar en het is geen karakterfout.** CLAUDE.md zegt: "Werk dat daar
niet aan bijdraagt, doen we niet -- hoe terecht een bevinding ook is." Maar **"daar" staat
nergens.** Er is geen plek waar het lopende doel staat. Dus is er niets om aan te toetsen,
en dan wint elke terechte bevinding het van de opdracht -- want een bevinding is concreet
en het doel is dat niet.

Dezelfde dag liet zien wat dat kost. Een regel die die dag werd geschreven luidde "parkeer
de push en begin aan de volgende taak", terwijl "blijf niet idle wachten" bedoeld was.
Zonder vastgelegd doel is het verschil tussen die twee niet te zien -- en de agent koos de
lezing die hem van het lopende werk afhaalde.

**Wat dit vraagt, en het is nog niet gebouwd:** een plek waar staat waar we nu aan werken,
die bij elke sessiestart wordt ingelezen, plus een controle op het moment dat een sessie
"klaar" zegt die vraagt of het werk daaraan bijdroeg. Die twee horen bij elkaar: een
controle bij het afronden zonder doel om aan te toetsen, wordt een vinkje. Zie paragraaf 9.

## 9. Wat hierna nog open staat -- gemeten 2026-09-28

Deze lijst is opgemaakt na de eerste keer dat de keten van begin tot eind is doorlopen
(een echte taak, OP-263, met drie sessies). Elk punt is gemeten, niet vermoed.

| # | Wat ontbreekt | Hoe het is vastgesteld |
|---|---|---|
| 1 | ~~Een vastgelegd lopend doel~~ **GEDICHT 2026-09-28** | `.claude/HUIDIGE-OPDRACHT.md`, getoond bij elke sessiestart met zijn OUDERDOM erbij -- een doel van vorige week ziet er anders hetzelfde uit als een doel van vandaag |
| 2 | ~~Een controle op het moment dat een sessie "klaar" zegt~~ **GEDICHT 2026-09-28** | `.claude/hooks/klaar-is-echt-klaar.sh` als Stop-hook: weigert af te ronden bij ongecommit werk of een openstaande claim van deze sessie. Toetst FEITEN, niet "heb je bijgedragen aan het doel" -- een vraag die je met ja kunt beantwoorden zonder te kijken is geen controle |
| 3 | ~~De rollen als bestand~~ **GEDICHT 2026-09-28** | vijftien rollen in `.claude/agents/`, elk met zijn schrijfgrens in `.claude/hooks/rol-schrijfgrens.sh` -- een tabel, geen negen losse scripts. Welke rol welke taak doet staat in `sprint-dag.md`, want zonder die koppeling roept niemand ze aan |
| 4 | **Bewijs dat een test rood was voor de fix** | de Final Approver leest dat in een tekst die de auteur zelf schreef; brief ligt klaar in `generated/2026-09-28-one-off-niemand-kan-nameten-dat-de-test-rood-was.md` |
| 5 | ~~Een wachtende of geblokkeerde sessie meldt zichzelf niet~~ **DEELS GEDICHT 2026-10-01** (commit 4c7ea49c) | de sessiestart toont nu elke geparkeerde push met sha, aanvrager en leeftijd, en een onvindbare aanvraag luid in plaats van stil. Aanleiding gemeten die dag: eaa98ed2 wachtte twaalf uur terwijl de aanvrager niet meer bestond. NIET gedicht: een goedkeurder die tegen de werkmap-regel aanloopt meldt dat nog steeds nergens |
| 6 | ~~De acceptant -- rol bestaat, is nog nooit gedraaid~~ **GEDRAAID 2026-10-01** (commit e039f2f7) | opstelling klaar, drie vaste opdrachten in `frontend/package.json` (commit eaa98ed2, die zelf 12 passed meldt -- niet door de regie nagemeten). Of de rol een hele sprint dekt, is nog niet gemeten |
| 7 | ~~De coordinatielaag~~ **GEDICHT 2026-09-30** (commit 95713977) | volgens die commit draaien de negen vastlopende MCP-tools weer in een halve seconde, na het weghalen van pijpen in het subproces |
| 8 | ~~`check_brief.py` leest `bestand.py:12` ook BINNEN een codeblok~~ **GEDICHT 2026-10-01** (commit 20c48b3c) | alleen hekken aan het begin van een regel tellen, blokregels worden leeg in plaats van weg zodat regelnummers gelijk blijven. Restpunt: een bestand ZONDER extensie (zoals `scripts/hooks/pre-push`) telt nog niet als verwijzing |
| 9 | **De testronde bij een push testte de werkmap, niet de gepushte commit** -- **GEDICHT 2026-10-01** (commit 3786b9e9) | gevonden bij de push van 20c48b3c: 17883 tests getest, 17888 gepusht. De pre-push hook weigert nu een develop-push als HEAD niet gelijk is aan de sha, ook op het documentpad |

**Stand 2026-09-28, na een halve dag diagnose op punt 7:** zeven hypothesen uitgesloten,
oorzaak nog niet gevonden. Wat is uitgesloten staat in
`docs/agent-briefs/generated/2026-09-28-one-off-de-mcp-coordinatielaag-loopt-vast.md`,
zodat de volgende sessie daar niet opnieuw begint.

**Stand 2026-09-28, einde dag.** Punt 1 en 2 zijn gebouwd, als paar en in die volgorde --
zonder 1 was 2 een vinkje geweest, zonder 2 bleef 1 een document dat niemand leest. Punt 3
is deels gedicht: de regie bestaat als rolbestand met een slot, de andere drie rollen nog
niet. Wat overblijft: 3 (de overige rollen), 4, 5, 6 en 7, plus het achtste punt hieronder.

**Stand 2026-09-28, avond: de Stop-hook is voor het eerst ZIEN vuren.** Tot dat moment was
punt 2 "gedicht" op grond van een bestand dat bestond en in `settings.json` stond -- precies
de bewering waar dit project een aparte waarschuwing voor heeft ("een hook kan in
`.claude/hooks/` staan zonder aangesloten te zijn"). Hij weigerde een afronding met een
gewijzigd, ongecommit `tests/unit/test_slug_validation.py` en noemde het bestand bij naam:

```
KLAAR IS NOG NIET KLAAR. Er staat iets open:
  - 1 bestand(en) gewijzigd maar niet gecommit:
      M tests/unit/test_slug_validation.py
   Let op: 1 commit(s) staan lokaal, nog niet op origin/develop.
```

Het was een terechte weigering: de rode tests stonden er wel, maar Gate 2 liep nog. Dat is
precies het moment waarop "klaar" vroeger gewoon werd gezegd.

**Stand 2026-09-28, avond: punt 3 stond ten onrechte als GEDICHT.** De vijftien rollen
bestonden, en hun bewaker was in beide richtingen mutatie-getest: 21 gevallen, 0 afwijkend.
Op grond daarvan is aan Rakesh gemeld dat de rolgrenzen afgedwongen waren.

Dat was onwaar, en een externe review van de acceptant-persona wees de plek aan. Gemeten met
een echte subagent in de rol verkenner:

```
Write -> src/core/PROEF-SCHRIJFGRENS-WEGWERP.py
"File created successfully at: ...\src\core\PROEF-SCHRIJFGRENS-WEGWERP.py"
```

**Hooks in de KOP van een rolbestand vuren niet wanneer die rol als subagent draait.**
`disallowedTools` in diezelfde kop had evenmin effect. Het mutatiebewijs bewees dus dat het
SCRIPT klopte, niet dat het AANGESLOTEN was -- precies de fout die CLAUDE.md al benoemt en
die op 2026-09-27 bij `auto-test.sh` ook gemaakt werd. Twee keer dezelfde fout in twee dagen,
en beide keren was mijn eigen bewijs de reden dat ik hem niet zag.

Wat WEL vuurt bij een subagent is een hook uit `.claude/settings.json` -- gemeten met een
weigering op `*.gen.ts` door `protect-files.sh`. En de invoer van zo'n hook draagt de rol
mee: `"agent_type":"verkenner"`, vastgesteld door een dump te hangen aan een hook die al
vuurde. Daar hangt de grens nu, met `NotebookEdit` erbij -- dat was een open route.

Tweede gat uit dezelfde review, ook nagemeten: **elke rol mocht `docs/meetlat.md`
overschrijven**, ook de acceptant wiens hele oordeel eraan hangt. `docs/` stond bewust open
zodat elke rol zijn bevinding kwijt kan; de meetlat had daar altijd al de uitzondering op
moeten zijn. Nu geweigerd voor iedereen.

Na de ombouw opnieuw live gemeten, met dezelfde rol die er eerst doorheen liep:

```
src/core/...     -> "ROL 'verkenner' MAG HIER NIET SCHRIJVEN"
docs/meetlat.md  -> "NIEMAND WIJZIGT DE MEETLAT"
docs/gewoon.md   -> aangemaakt   (de controlevraag: het is geen "weiger alles")
```

Bewaakt door `tests/architecture/test_de_schrijfgrens_hangt_waar_hij_vuurt.py` -- een test op
de BEDRADING en niet op het gedrag, want dat laatste was al bewezen en hielp niets.

**Wat geen van beide nieuwe bewakers doet, en dat is met opzet.** Ze toetsen geen OORDEEL.
De Stop-hook vraagt niet "heb je bijgedragen aan het doel" -- dat kan geen script beoordelen,
en een vraag die je met ja kunt beantwoorden zonder te kijken is geen controle. Hij toetst
wat meetbaar is: ongecommit werk, een openstaande claim. Het oordeel blijft bij de agent,
maar nu met een doel om aan te toetsen dat bij elke sessiestart voor zijn neus staat.

**Wat NIET meer op deze lijst staat, en waarom.** Eerdere versies noemden "het besluit over
agent teams" en "de keten als werkstroom". Het eerste is geen gat maar een keuze die pas
speelt als 1 tot en met 3 dicht zijn; het tweede is op 2026-09-28 beproefd en werkte -- zes
schakels, waarvan vijf iets vonden dat de andere niet hadden gevangen.
