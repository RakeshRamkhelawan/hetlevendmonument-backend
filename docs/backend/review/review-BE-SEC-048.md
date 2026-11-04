STATUS: APPROVED WITH MINOR GAPS

# Review BE-SEC-048 -- initiator-concept op `EnhancedBaseAgent`

- Beoordeeld document: `docs/backend/features/BE-SEC-048-initiator-concept-enhanced-base-agent.md`
- Reviewdatum: 2026-09-01
- Beoordelaar: documentatiereview conform `docs/backend/FEATURE_DOC_WORKFLOW.md`, stap 2
- Branch: `worktree-agent-a4bf751726d1f51a2` (afgeleid van `develop`)
- Aard: DOCUMENTATIEreview van een ontwerpvoorstel plus impact-analyse. Dit is geen
  implementatiereview van `ded5b236`; die is op 2026-08-26 apart en blind uitgevoerd en
  staat samengevat in de OP-24-rij van ADR-036.

## B. EINDOORDEEL

APPROVED WITH MINOR GAPS.

Het oordeel geldt voor het document ZOALS HET NU IS, dus inclusief SS10 en SS11 die op
2026-09-01 zijn toegevoegd. Zonder SS10 was dit oordeel NEEDS REVISION geweest: de kop van
het document zei "geen implementatie" terwijl de implementatie er vijf dagen in zat. Zie
H-1; die bevinding is gefixed voordat dit oordeel is gegeven, niet erna weggeschreven.

## C. SAMENVATTING

Dit is een sterk ontwerpdocument met een ongebruikelijk eerlijke opbouw: het beschrijft
niet alleen wat er zou moeten gebeuren, maar legt in SS9 vast dat het eigen uitgangspunt na
onderzoek onjuist bleek (er is geen levende aanroeper) en dat de aanbeveling daardoor
verandert. Dat is precies het gedrag dat `.claude/rules/quality-gates.md` vraagt onder "een
onbewezen oorzaak wordt nooit een WHY-comment": de auteur meet, en corrigeert zichzelf in
het document in plaats van de eerdere tekst stil te herschrijven. SS7.1 is het beste
voorbeeld: daar wordt een door Rakesh genomen beslissing niet bevestigd maar doorgerekend,
met de gemeten consequentie (`Proposal.__post_init__` gooit bij `user_id<=0`, dus de
Council-aanroep crasht in plaats van te weigeren) en de conclusie dat een eerder
onafhankelijke vraag daarmee een harde prerequisite wordt.

Wat het document NIET is, staat er ook expliciet in (SS4), en dat is zeldzaam genoeg om te
benoemen. De openstaande beslissingen zijn in SS5 en SS7.5 als genummerde tabel opgenomen
met een status per rij, wat ze toetsbaar maakt.

De zwakte zat niet in het denkwerk maar in het ONDERHOUD: het document is na de
implementatie niet bijgewerkt en droeg vijf dagen een statusregel die het tegendeel beweerde
van de code en van de ADR-registerrij. Daarnaast zijn twee gemeten aantallen niet
herleidbaar: de categorietabel in SS2 telt intern niet op, en de openingsmeting is vandaag
niet reproduceerbaar. Geen van beide raakt de conclusie van het document, want die rust op
SS9's per-klasse-sweep en niet op de tellingen -- vandaar Medium en niet High.

## D. BEVINDINGEN PER CATEGORIE

### 1. Coverage gaps

De impact-analyse dekt de klassen die het benoemt, maar de VERZAMELING is niet sluitend
gedefinieerd. SS2 splitst in vijf categorieen, waarvan de rij "Overig (`ExternalAgentBridge`,
scheduling-agents)" drie klassen bevat die volgens de code evengoed DIRECTE
`EnhancedBaseAgent`-subklassen zijn (`external_agent_bridge.py:66`,
`scheduling/agents/orchestrator_agent.py:21`, `scheduling/voice/agent.py:37`). Ze staan dus
in een restcategorie terwijl ze in de hoofdcategorie horen. SS3.3 noemt ze wel als klassen
die onderzocht moeten worden, en SS9.1 zegt "alle 20 klassen" te hebben onderzocht --
16 + 4 = 20, wat die drie uitsluit. Zie M-1: de conclusie blijft overeind (SS9.1 noemt ook
een repo-brede sweep op externe aanroepen die alle 17 treffers naar broker-objecten
herleidt), maar de LEZER kan die dekking niet uit het document afleiden.

### 2. Functionele onduidelijkheden

Geen. De voorgestelde flow was in SS3.2 al concreet genoeg om te implementeren, en SS11
legt nu beide gedragsvarianten (flag uit / flag aan) vast met de foutmeldingen erbij.

### 3. Technische onduidelijkheden

SS8.2 stelt een feature-flag voor met een "allowlist in de flag-config" als per-ring
mechanisme, maar SS7.5 vraag 4 (schakelmechanisme per klasse of per tool) blijft open. De
implementatie heeft vervolgens de proces-brede boolean genomen. Het document benoemt die
uitkomst nu in SS10.2 als de enige echt openstaande beslissing uit SS7.5. Voor de
implementatiereview is dat afgehandeld; voor dit document is het correct vastgelegd.

### 4. Ontbrekende foutstatussen en edge cases

Niet van toepassing in de klassieke vorm: dit artefact heeft geen endpoints, dus geen
400/401/403/404/409/422/429/500/503-matrix. De relevante equivalent is het foutgedrag van
`execute_tool()`, en dat ontbrak tot 2026-09-01 volledig. SS11 vult dat nu in: welke
exception, met welke `error_detail`, in welke volgorde, en welk verdict tot welke afwijzing
leidt. Zonder die sectie was dit een High geweest.

### 5. Acceptatiecriteria problemen

SS6 ("Verificatie dat dit document geen gedrag wijzigt") is testbaar en concreet: een
commando plus de verwachte uitkomst. SS8.1's stopcriterium ("meer dan 0 onverwachte crashes
op de initiator-check in de observatieperiode") en SS8.2's stopcriterium ("meer dan 1% van
de `execute_tool()`-aanroepen ... over een venster van 10 minuten") zijn eveneens vooraf
vastgelegd en meetbaar. Wat ONTBREEKT is de meetvoorziening: het document zegt nergens
welke metric of welk logveld die 1% zou moeten opleveren, en er is vandaag geen teller op
de initiator-check. Zie L-1. Dat is Low omdat SS9.2 het ring-proces zelf achterhaald
verklaart.

### 6. Integratorhandleiding / API-uitleg problemen

Niet van toepassing: er is geen API-consument. De aanroeper is interne agentcode, en SS11
Flow 2 benoemt expliciet wat de aanroepende laag moet doen (`_initiated_by_user_id` zetten
voordat `execute_tool()` wordt aangeroepen). Dat is de enige integratie-instructie die dit
artefact nodig heeft.

### 7. Trainingsdata problemen

Tot 2026-09-01 ontbrak de Trainingssamenvatting volledig; het document viel daarmee door de
documentatiepoort (`python scripts/validate_feature_docs.py`, MISSING). Nu aanwezig als
SS11, met twee flows in het vaste mini-format. Er is bewust NIET een enkele flow geschreven:
het gedrag verschilt volledig per feature-flag, en een samengevoegde beschrijving zou
suggereren dat de initiator-eis vandaag wordt afgedwongen. Dat is niet zo.

### 8. Structuur- en consistentieproblemen

Dit is de zwaarste categorie van deze review.

- De statusregel van het document sprak de code en de ADR tegen (H-1, gefixed).
- SS2's aantallenkolom spreekt SS2's eigen voorbeeldkolom tegen (M-1).
- SS2's openingsmeting is niet reproduceerbaar (M-2).
- SS4 en SS9.3 spreken elkaar tegen over `KNOWN_UNGATED` -- SS4 zegt "niet aanraken, anders
  wordt de guard rood", SS9.3 punt 2 zegt "verwijderen". Beide zijn in hun eigen context
  juist (SS4 gaat over de documentatiedag, SS9.3 over de implementatiedag), maar het
  document maakt dat verschil niet expliciet en de lezer moet het afleiden. SS10.2 zegt dit
  nu wel met zoveel woorden.

De gekozen oplossing -- SS1 t/m SS9 ongewijzigd laten staan als besluitgeschiedenis en de
correctie in een gedateerde SS10 zetten -- is de juiste: de eerdere secties zijn de
onderbouwing van Rakesh's beslissing van 2026-08-25/26 en mogen niet achteraf worden
gladgestreken.

### 9. Risico's voor implementatie, security of QA

Het reeele risico van dit document is een LEESRISICO, en het is niet hypothetisch: tussen
2026-08-26 en 2026-09-01 kon iedereen die alleen dit bestand las concluderen dat OP-24 nog
openstond en dat `KNOWN_UNGATED` de methode nog bevatte. Beide onwaar. In een project waar
de ADR-rij en het feature-document allebei als bron gelden, is een tegenspraak tussen die
twee erger dan een gat in een van beide.

Het omgekeerde leesrisico is nu ingebouwd afgedekt: SS10.3 zegt expliciet dat GESLOTEN hier
"geimplementeerd en getest" betekent en niet "actief", zodat SS10 zelf niet als
"OP-24 wordt afgedwongen" gelezen kan worden.

Tenant-isolatie en permissiegedrag: correct beschreven. `execute_tool()` geeft
`context={"tenant_id": self.tenant_id}` mee aan de broker en de Council-aanroep krijgt
`tenant_id` uit het agent-object, nooit uit de payload. Dat is conform
`.claude/rules/backend-patterns.md` punt 1 en het document doet geen andere bewering.

## E. ISSUE REGISTER

| Severity | ID of sectie | Probleem | Waarom dit een probleem is | Concrete correctie |
|---|---|---|---|---|
| High | Kop + SS4 + SS9.3 | Statusregel zei "ONTWERPVOORSTEL + IMPACT-ANALYSE -- geen implementatie" terwijl commit `ded5b236` (2026-08-26) de implementatie bevatte; SS4 zei "Geen wijziging aan `KNOWN_UNGATED`" terwijl die lijst nu leeg is | Het document sprak de code EN de ADR-036-registerrij (STATUS=GESLOTEN) tegen. Een lezer die dit bestand als bron nam, concludeerde dat een AI-Act-artikel-14-gat openstond dat gesloten is | GEFIXED 2026-09-01: kop herschreven naar "GEIMPLEMENTEERD achter een uitgeschakelde feature-flag", plus SS10 met de gemeten stand en een expliciete opsomming van welke uitspraken in SS1-SS9 achterhaald zijn |
| High | Ontbrekende SS11 | Geen `## Trainingssamenvatting`, dus geen enkele beschrijving van het feitelijke request/respons/foutgedrag | `docs/backend/FEATURE_DOC_WORKFLOW.md` noemt een ontbrekende trainingssamenvatting expliciet als kwaliteitspoort-blokker, en `validate_feature_docs.py` faalde er hard op | GEFIXED 2026-09-01: SS11 toegevoegd met twee flows in het vaste mini-format, gemeten tegen `base_agent.py:358-447` in plaats van overgenomen uit het ontwerp in SS3 |
| Medium | SS2, categorietabel (M-1) | De rij "Directe `EnhancedBaseAgent`-subklassen" heeft 13 in de aantallenkolom en noemt er 16 in de voorbeeldkolom. Nagemeten (AST over 2242 bestanden in `src/`, 2026-09-01): 20 directe subklassen van `EnhancedBaseAgent`, waarvan 16 in `src/core/agents/`; 6 van `SymbioticAgent`; 135 van `BaseSpecialistAgent`. `ExternalAgentBridge` en de twee scheduling-agents staan in "Overig" terwijl ze directe subklassen zijn | Het hele document rekent met "~17-20" en SS9.1 met "alle 20 klassen". Een lezer kan uit de tabel niet reconstrueren welke verzameling dat is, en de drie klassen in "Overig" zijn precies de klassen waarvan SS3.3 zegt dat ze een eigen check nodig hebben | Vastgelegd in SS10.3, derde bullet, met het meetcommando en de drie getallen. NIET in SS2 zelf gecorrigeerd: SS2 is de onderbouwing van een genomen beslissing en wordt niet achteraf herschreven |
| Medium | SS2, regel "28 bestanden matchen" (M-2) | Het gegeven grep-commando geeft vandaag 30 bestanden, niet 28. Er staat geen commit-hash of meetdatum bij het commando | Het document presenteert dit als "gemeten, niet geschat", maar zonder anker is de meting niet herhaalbaar en kan een lezer niet vaststellen of het verschil drift is of een fout | Vastgelegd in SS10.3. Voor volgende metingen: noteer commit-hash naast het commando, conform de regel dat een oorzaak alleen mag worden opgeschreven met de meting erbij |
| Low | SS8.2, stopcriterium (L-1) | "meer dan 1% van de `execute_tool()`-aanroepen ... over een venster van 10 minuten" noemt geen metric, logveld of dashboard waaruit dat percentage komt | Een stopcriterium dat niet gemeten kan worden, is geen stopcriterium maar een voornemen. Dezelfde faalvorm als een guard die niets bewaakt | Geen actie nu: SS9.2 verklaart het ring-proces achterhaald zolang er geen aanroeper is. Wel meenemen zodra open vraag 4 (SS7.5) wordt beslecht en de flag ergens aangaat |
| Low | SS8.1/SS8.2, bronvermelding | Twee van de drie bronnen zijn commerciele blogs (`featureflow.com`, `beefed.ai`); alleen de Google SRE Workbook-verwijzing is een erkende engineering-bron | Het document noemt dit "industriestandaard, met bron". Voor het kernprincipe (een schakelaar op het instappunt, niet verspreid) is dat verdedigbaar, maar de kwalificatie is sterker dan de bronnen dragen | Geen actie. De ontwerpkeuze die eruit volgt is los daarvan juist en is in de implementatie ook zo gebouwd |

Geen CRITICAL bevindingen. Beide HIGH-bevindingen zijn gefixed in het spec-document zelf
voordat dit eindoordeel is gegeven; de commit die deze review toevoegt bevat ook die fix.

## F. ONTBREKENDE ITEMS

- Een meetvoorziening voor SS8.2's 1%-stopcriterium (L-1). Niet vandaag nodig.
- Een antwoord op SS7.5 vraag 4 (schakelmechanisme per klasse of per tool). Dit is de enige
  beslissing uit dit document die nog echt bij Rakesh ligt; de implementatie heeft er
  voorlopig een proces-brede boolean voor in de plaats gezet.
- Een expliciete uitspraak welke concrete klassen de "~17-20" zijn. SS10.3 geeft nu de
  telling en de meetmethode, maar geen uitgeschreven lijst. Voor het gebruik van dit
  document (besluitvorming, niet uitvoering) is de telling voldoende.

## G. VERBETERDE TEKSTVOORSTELLEN

De twee die er echt toe deden zijn niet als voorstel achtergelaten maar direct doorgevoerd
in het spec-document: de statusregel (kop) en SS10 + SS11. Een derde voorstel, niet
doorgevoerd omdat het historie zou herschrijven:

> SS2, tabelkop: vervang "Aantal" door "Aantal (gemeten 2026-08-25, commit `<hash>`)" en
> zorg dat elke rij zijn eigen voorbeeldkolom telt.

Dit hoort in de volgende impact-analyse die dit patroon gebruikt, niet in een terugwerkende
correctie van SS2.

## H. RELEASE-OORDEEL

- **Geschikt voor bouw / implementatie?** Ja, en dat is empirisch bevestigd: SS3, SS7 en SS9
  zijn op 2026-08-26 zonder aanvullend ontwerpwerk omgezet in `ded5b236`. De enige plek waar
  de implementatie van het document afweek (`MODIFIED` als weigering in plaats van
  doorlaten) is in de ADR-rij onderbouwd en staat nu ook in SS11.
- **Geschikt voor QA en geautomatiseerd testen?** Ja. SS11 geeft per flow een verifieerbare
  fout- en succesconditie; die corresponderen met de 7 bestaande tests in
  `tests/unit/agents/test_enhanced_base_agent_council_consultation.py`. SS6 geeft een
  uitvoerbaar verificatiecommando.
- **Geschikt voor LLM-training?** Ja, met een voorbehoud: een model dat alleen SS1 t/m SS9
  leest, leert een onjuiste stand ("geen implementatie"). SS10 staat daarom expliciet
  vooraan aangekondigd in de kop van het document.
- **Geschikt voor integratorhandleiding / API-documentatie?** Niet van toepassing -- geen
  extern API-oppervlak. Voor de interne aanroeper is SS11 Flow 2 de handleiding.
