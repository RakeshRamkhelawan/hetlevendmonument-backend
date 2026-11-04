# ADR-036 Backlog-Sluiting -- Masterprompt

## Update 2026-09-09 -- de tabel hieronder is nu script-gegenereerd, niet met de hand bijgehouden

**Gemeten defect dat aanleiding gaf tot deze update.** De tabel in dit document (2026-09-07)
toonde 69 rijen en zette OP-139/OP-141 als open, terwijl die twee al gesloten waren, en miste
OP-175/176/177/179/210/212/213 die er sindsdien bij waren gekomen -- binnen twee dagen al
onjuist. Een met de hand getypte tabel op een register dat continu verandert wordt zo
misleidend voor de volgende lezer. De tabel is daarom vervangen door de verse uitvoer van:

```bash
python scripts/list_adr036_open_items.py --triage-table
```

Regenereer hem met dat commando aan het begin van elke nieuwe sessie op dit document --
plak de nieuwe uitvoer erover, vertrouw nooit op wat hier al stond. De Vlag-kolom (vraagt dit
Rakesh / is dit onomkeerbaar / is dit al eerder bewust uitgesteld) blijft BEWUST leeg: dat is
een oordeel dat vraagt om de rij zelf te lezen, en een keyword-classifier daarop zou dezelfde
fout herhalen als de guards die op FORMULERING matchen in plaats van op de handeling. Vul hem
per rij in bij het lezen, zoals hieronder bij Stap 2 al stond.

**Beleid voor hoe een rij een brief krijgt (vastgelegd 2026-09-09, na een sessie die het
tegenovergestelde probeerde: 71 losse, vooraf geschreven dagbrieven met codesnippets voor
alle open rijen tegelijk -- verworpen omdat zo'n bevroren document binnen dagen stale is,
precies zoals deze tabel dat was):**

- **P0-rijen (het autorisatiecluster):** GEEN werkbrief. Blijven omheind tot Rakesh zelf een
  apart moment aankondigt, ongewijzigd t.o.v. de rest van dit document.
- **P1-rijen:** krijgen een volledige `sprint-dag.md`-brief MET codesnippets -- maar pas
  geschreven vlak voordat een sprint die batch daadwerkelijk oppakt, in batches van 5-8
  samenhangende rijen (zoals Stap 3 hieronder al voorschreef). Nooit maanden vooraf.
- **P2/P3-rijen:** blijven gewoon registerrijen tot ze ingepland worden. Geen brief nodig
  voordat dat moment aanbreekt.
- **Codesnippets in een brief:** altijd op het moment van schrijven uit het ACTUELE bestand
  gelezen, nooit uit een ouder document overgenomen. Stempel elk snippet met `bestand:regel`
  plus de commit-hash waarop het gelezen is (zelfde discipline als het `BEWIJS=pad:regel`-veld
  in het register). Zie `.claude/skills/sprint-workflow/SKILL.md`, sectie "Codesnippets in een
  brief", voor het volledige patroon.
- **Een losse rij apart weggeven:** vul `docs/agent-briefs/one-off-taak.md` in op het moment
  zelf, vanuit de actuele registerrij-inhoud. Geen archief van 74 losse briefs nodig.

De rest van dit document (Stap 1-3, de NOOIT-lijst, het dagskelet) beschrijft nog steeds de
werkwijze die al eerder werkte (batches van 5-8, mutatiebewijs, registerrij-update in dezelfde
commit). Het **dagskelet onderaan** en de per-rij Vlag-toekenningen in de OUDE tabel
weerspiegelen de planningsronde van 2026-09-07 en zijn deels al uitgevoerd -- een nieuwe
sprintstart begint met een verse `--triage-table` en herhaalt Stap 2 (elke rij zelf bevestigen),
niet met de aanname dat de oude Vlaggen nog kloppen.

---

## Wat dit document is

Dit is het enige startdocument voor een nieuwe sessie die de open OP-punten in
ADR-036 moet sluiten. Plak dit hele bestand (of verwijs ernaar) als eerste
bericht in een verse sessie. De sessie heeft geen geheugen van eerdere
gesprekken -- dit document plus de altijd-geladen CLAUDE.md-context is alles
wat hij heeft.

**Eerlijke verwachting vooraf, niet pas aan het eind:** er staan 69 rijen open
(gemeten 2026-09-07, `python scripts/list_adr036_open_items.py --count`). Een
deel daarvan kan een agent zelfstandig sluiten. Een ander deel vraagt eerst een
beslissing van Rakesh (niet "hoe implementeer ik dit" maar "welke van twee
architecturale routes wil je").

**Vaststaand feit, geen open vraag (bevestigd door Rakesh 2026-09-07, zie
`.claude/WORKING-CONTEXT.md` sectie "Project-status" en `docs/prod-readiness.md`
PHASE 0): er zijn GEEN bestaande klanten en er komen GEEN nieuwe klanten zolang
de applicatie in de bouwfase zit.** Twaalf rijen (OP-182 t/m OP-193) zijn een
samenhangend, LIVE-security-kritiek cluster (privilege-escalatie,
cross-tenant-schrijven, een JWT-scope die elke controle passeert) dat om
precies die reden BEWUST buiten deze sprint blijft -- niet omdat het onbelangrijk
is, maar omdat er vandaag niemand is om tegen te beschermen en de reparatie
zelf risico's kent (OP-186 mag niet dicht voor OP-187 gemeten is; fout uitgevoerd
sluit dit potentiele echte beheerders buiten zodra er wel klanten zijn). Dit
cluster hoeft NIET elke keer opnieuw ter discussie gesteld te worden: het blijft
ongemoeid voor de volle duur van de bouw, punt uit, tot Rakesh zelf een apart
moment aankondigt. De 3 dagen gaan volledig naar de overige 57 rijen.

---

## Stap 1 -- Verplichte context lezen (voor je iets anders doet)

In deze volgorde, volledig:

1. `CLAUDE.md` -- hard, geen uitzonderingen.
2. `.claude/rules/quality-gates.md`, `.claude/rules/backend-patterns.md` --
   worden automatisch geladen, maar lees ze zelf ook bewust door: dit zijn de
   3 gates en de 11 backend-patronen die elke wijziging vandaag moet volgen.
3. `.claude/WORKING-CONTEXT.md`, sectie **"Huidige stand (2026-09-07)"**
   bovenaan -- de exacte staat waarin `develop` nu verkeert (commit `4ebfbe78`,
   groen, 69 open OP-punten, welke vijf net zijn gesloten en waarom).
4. `.claude/skills/valkuilen/SKILL.md` -- volledig, met extra aandacht voor:
   - **"Nooit in een lus"** (helemaal onderaan het eerste blok): dezelfde
     kwaliteitslat die code voor een klant beschermt, wordt een tijdverspillende
     lus als je hem toepast op werk dat je zelf deze week hebt verzonnen. Drie
     meetbare stopregels staan erin -- die gelden HARD voor deze sprint.
   - **"Een gefixte bevinding sluit de registerrij niet vanzelf mee"** (laatste
     sectie): de registerrij-update hoort in DEZELFDE commit als de fix.
   - **"Meetinstrumenten die hun eigen falen niet zien"**: mutatiebewijs is
     verplicht voor elke NIEUWE of GEWIJZIGDE guard, in beide richtingen.
   - **"De les die alle andere lessen overstijgt"**: gebruik
     `scripts/mutation_harness.py`, verzin geen eigen variant.
5. `.claude/skills/sprint-workflow/SKILL.md` -- de vaste taakvolgorde per
   sprintdag (Taak 0 t/m 10), het final-approver-formaat, het
   pre-existing-issues-drempelmodel. Dit document overschrijft NIETS daarvan;
   het voegt de ADR-036-specifieke triage en stopregels toe.
6. `docs/adr/036-agentic-organizational-hierarchy-governance-reuse.md`, de
   leeswijzer boven paragraaf 10 (het register) -- de exacte grammatica
   (`STATUS=`/`GEVERIFIEERD=`/`BEWIJS=`, laatste veld wint) en
   `tests/architecture/test_adr036_register_is_parseable.py` voor wat een
   `STATUS=GESLOTEN` bewijstechnisch nodig heeft
   (`_closure_evidence_is_strong`: een bestaande commit-hash, of een
   test-/node-id-referentie waarin het eigen OP-nummer letterlijk voorkomt --
   een kaal documentpad is NIET genoeg).
7. `docs/reports/OVERDRACHT_2026-09-03_CI_HERSTEL.md` en
   `docs/reports/ADR-036_NAMETING_74_RIJEN_2026-08-31.md` -- alleen als je een
   specifieke rij tegenkomt die daarnaar verwijst; niet vooraf volledig lezen.

---

## Stap 2 -- Dag 0 (eerste uur): triage, geen code

**Doe dit VOORDAT je ook maar een regel code of documentatie wijzigt.**

1. Meet de nulmeting:
   ```bash
   python scripts/list_adr036_open_items.py --count
   grep -c "^| OP-" docs/adr/036-agentic-organizational-hierarchy-governance-reuse.md
   ```
   Schrijf beide getallen op. Je meet ze aan het EIND van dag 3 opnieuw.

2. Genereer de actuele tabel (vervangt elke eerder hier geplakte versie -- zie de
   Update-sectie bovenaan dit document) en loop hem langs:

   ```bash
   python scripts/list_adr036_open_items.py --triage-table
   ```

   Bevestig per rij zelf in het register of de categorie nog klopt -- rijen
   veranderen, deze tabel is een startpunt, geen waarheid. De "Prio"-kolom is
   het individuele P-niveau van de rij zelf; dat is IETS ANDERS dan of een rij
   tot het hieronder genoemde, expliciet omheinde P0-cluster hoort (OP-154 +
   OP-182 t/m OP-193) -- meerdere clusterleden staan met een individueel P1/P2
   in de tabel, maar blijven wel deel van het omheinde cluster. Kolom "Vlag"
   (leeg in de script-output, hier met de hand aan te vullen): `R` = de rij
   noemt zelf een beslissing/besluit van Rakesh, `I` = de rij noemt een
   onomkeerbare/database-rakende actie, `D` = de rij is al eerder BEWUST
   uitgesteld met een reden. Leeg = op het eerste gezicht zelfstandig te
   onderzoeken en te sluiten door een agent.

   Ter referentie: de tabel die hier stond op 2026-09-07 (69 rijen) is
   VERVANGEN, niet aangevuld -- die had OP-139/OP-141 nog als open staan
   (inmiddels gesloten) en miste OP-175/176/177/179/210/212/213 en alles wat
   na 2026-09-07 is bijgekomen. Vertrouw niet op een tabel die hier ooit is
   geplakt; draai het commando opnieuw.

3. **Voordat je een letter code schrijft**: stel Rakesh EEN gebundeld bericht
   met alle beslissingen die je nodig hebt om de komende 3 dagen zonder
   wachttijd door te werken. Niet 69 losse vragen, niet per rij interrumperen.
   - **Het P0-cluster (OP-182 t/m OP-193, 12 rijen) is GEEN open vraag.** Er
     zijn geen klanten en die komen niet tijdens de bouw (vaststaand feit,
     zie Stap 1 hierboven en `.claude/WORKING-CONTEXT.md`). Dit cluster blijft
     de volle 3 dagen ONGEMOEID -- geen enkele code-wijziging op login/auth/
     rollen/tokens vanuit deze sprint, en niet opnieuw ter discussie stellen.
     De 3 dagen gaan volledig naar de overige 57 rijen. Mocht je tijdens het
     werk toch een AANGRENZEND probleem in dit cluster tegenkomen (bijv. via
     OP-199 of OP-202, die er wel los van staan): registreer het, raak het
     niet aan.
   - Elke rij met vlag `R` die niet in het cluster zit: verzamel de ECHTE
     open vraag uit de rij zelf (bijv. OP-40: "welke van drie vocabulaires
     wordt de centrale admin-definitie", OP-62: "welke triage-aanpak voor 155
     routes", OP-149/150: "DROP toestaan, ja/nee"). Stel ze als korte,
     concrete keuzes, niet als open vraag.
   - Vlag `I` (onomkeerbaar): expliciet benoemen dat je er NIETS aan doet
     zonder aparte, expliciete GO op het moment zelf -- ook als Rakesh nu al
     "ja" zegt op de intentie.
4. Verwerk de antwoorden in een korte, eigen aantekening (niet in het
   register, dat is voor bevindingen, niet voor planning) en ga pas dan naar
   Stap 3.

---

## Stap 3 -- Werkwijze per rij of klein batchje (na Dag 0)

Voor de rijen zonder vlag `R`/`I` (of met `R` beantwoord), in batches van
**maximaal 5-8 onafhankelijke rijen tegelijk** (zoals de bundel van
2026-09-06/07: OP-152/149/116/41/73 -- dat werkte, groter wordt onoverzichtelijk):

1. **Impact-analyse eerst** (sprint-workflow skill, Taak 0) -- welke bestaande
   tests raken de bestanden die je gaat wijzigen.
2. **Plan (Gate 1, EnterPlanMode)** per batch, niet per rij: beschrijf aanpak,
   aannames, risico's. Wacht op goedkeuring voor je verder gaat.
3. **Implementeer.** Volg `.claude/rules/backend-patterns.md` (tenant_id uit
   JWT, datetime timezone-aware, best_effort voor audit/metrics, response-
   format, ADR-033-routerlagen) en `.claude/rules/database.md` waar van
   toepassing.
4. **Voor elke nieuwe of gewijzigde guard**: mutatiebewijs in BEIDE richtingen
   via `scripts/mutation_harness.py` (`Mutation`, `replace_anchor`,
   `verify_red`, `verify_green`) -- geen eigen script, geen heredoc-mutaties,
   geen opgeschreven-maar-niet-uitgevoerd bewijs.
5. **Registerrij bijwerken in DEZELFDE commit** als de code/documentwijziging.
   Nieuwe `STATUS=GESLOTEN` moet een bestaande commit-hash citeren OF een
   test-/node-id waar het eigen OP-nummer letterlijk in voorkomt (zie Stap 1,
   punt 6). Blijft een rij open: schrijf waarom, met een concrete
   vervolgvraag, niet "TODO later".
6. **Gate 2 -- dual review** via de Agent-tool: spawn `code-reviewer` en
   `security-reviewer` (of `performance-reviewer` bij DB/query-zware
   wijzigingen) PARALLEL op de gecombineerde diff van de batch. Beide moeten
   GO geven. **Stopregel: bij een DERDE review-/herschrijfronde op hetzelfde
   artefact binnen deze sprint, stop je met repareren** -- verwijder de
   wijziging, geef de bevinding met de reden door aan de regie voor een
   sprint-dag-brief in `docs/agent-briefs/generated/` (sinds 2026-09-19; hier
   stond "zet de bevinding terug als openstaande registerrij"),
   en ga door met de volgende batch. Dit is de kernles van "Nooit in een lus":
   niet nog een keer, wel opschrijven.
7. **Gate 3**: `ruff check src/`, `python -m pyright` (geen args), mypy-audit
   (`python scripts/run_mypy_audit.py --fail-on-increase`) -- alle drie 0
   nieuwe fouten t.o.v. baseline.
8. **Gerichte tests + registerguards**:
   ```bash
   python -m pytest tests/architecture/test_adr036_register_is_parseable.py tests/architecture/test_adr036_references_have_a_register_row.py -q
   python -m pytest <gerichte tests uit de impact-analyse> -q --timeout=60
   ```
9. **Commit** de hele batch in een keer (code + registerrij-updates samen),
   Nederlandse boodschap in de stijl van eerdere commits deze week
   (`fix(...)`/`feat(...)`/`docs(...)` + welke OP-nummers).
10. **ASCII-check** op elk nieuw/gewijzigd tekstbestand voor je committeert
    (Python-scan op non-ASCII in de TOEGEVOEGDE regels, niet visueel).

Aan het eind van elke batch: meet `python scripts/list_adr036_open_items.py --count`
opnieuw en noteer het verschil. Een batch die het getal niet daadwerkelijk
laat zakken (of die een geldige, gedocumenteerde reden heeft waarom niet) is
een signaal om de aanpak te herzien, niet om door te denderen.

---

## Volledige testsuite en Windows-specifieke regels

```bash
# Backend, volledige poort (NOOIT -n 8 hiervoor, NOOIT -n auto op Windows)
python -m pytest tests/unit tests/architecture tests/core tests/contracts -n 4 --timeout=60 -q --tb=short

# Frontend
cd frontend && npm run test:unit   # NOOIT npx vitest direct op Windows

# Alembic (na elke nieuwe migratie)
alembic -c src/alembic.ini heads   # moet precies 1 head tonen
alembic -c src/alembic.ini check   # mag geen drift melden
```

---

## Nooit-in-een-lus: drie harde stopregels voor deze sprint

Uit `.claude/skills/valkuilen/SKILL.md`, hier herhaald omdat ze voor DEZE
sprint het grootste risico afdekken (een 4-dagen-iteratie eerder dit project
sloot minder open punten dan hij ERBIJ maakte):

1. **Derde review-/herschrijfronde op een eigen vers artefact = stop en
   registreren, niet nog een keer repareren.**
2. **Meet het open-aantal aan het begin van dag 1 en het eind van dag 3.**
   Loopt het op zonder dat er een klant-blokkerend punt is gesloten: meld dat
   expliciet aan Rakesh in plaats van door te werken alsof er niets aan de
   hand is.
3. **Een bevinding die niets blokkeert krijgt geen guard-met-mutatiebewijs in
   twee richtingen als dat de sprint in een lus dreigt te trekken** -- dit is
   nog steeds een voorstel dat op Rakesh's beslissing wacht (zie CLAUDE.md
   NOOIT-lijst), dus vraag het als onderdeel van de Dag-0-vragenronde in
   plaats van zelf te beslissen.

---

## Verkorte NOOIT-lijst (volledige lijst: CLAUDE.md)

- NOOIT het P0-cluster (OP-182 t/m OP-193) aanraken zonder de expliciete,
  verse GO uit Stap 2.
- NOOIT een onomkeerbare actie (DROP, secret-rotatie) zonder GO op het moment
  zelf, ook als een eerdere GO de intentie al goedkeurde.
- NOOIT mergen naar `main` zonder expliciete GO van Rakesh.
- NOOIT `--no-verify` bij git push, nooit een git-tag aanmaken.
- NOOIT tenant_id uit request body, nooit `datetime.now()`/`datetime.utcnow()`
  zonder timezone.
- NOOIT emoji of non-ASCII in code, comments, logs of documentatie.
- NOOIT een test overslaan of uitcommentarieren om de suite groen te krijgen.
- NOOIT een registerrij op `STATUS=GESLOTEN` zetten zonder de bewijsvorm die
  de guard eist (zie Stap 1, punt 6).
- NOOIT pushen naar `origin/develop` zonder Rakesh's expliciete bevestiging
  vooraf (elke dag opnieuw vragen, een eerdere push-bevestiging geldt niet
  automatisch voor de volgende dag).

---

## Einde van elke dag

Volg het bestaande patroon uit `sprint-workflow` SKILL.md:

1. Commit (verplicht, voor de brief).
2. Genereer een final-approver brief:
   `docs/agent-briefs/generated/YYYY-MM-DD-final-approver-adr036-backlog-dag-N.md`
   met: welke OP-nummers gesloten/deels gefixed/bewust niet aangeraakt, de
   open-aantal-meting van vandaag versus gisteren, commit-hashes, testresultaten.
3. Meld aan Rakesh, wacht op GO voor dag N+1. Vraag GO voor de push apart van
   GO voor de volgende dag -- dit zijn twee verschillende beslissingen.

---

## Voorlopig dag-skelet (Dag 0 kan dit bijstellen op de niet-cluster-punten -- dit is een startpunt, geen belofte)

Het P0-cluster blijft de volle 3 dagen ongemoeid (vaststaand, geen open vraag --
zie hierboven). De rest van dit skelet is een startpunt op basis van de
overige 57 rijen, en Dag 0 kan de volgorde daarbinnen bijstellen na de
antwoorden van Rakesh:

- **Dag 1**: rijen zonder vlag of met een simpele/al-beantwoorde `R`
  (OP-01/02/03/04/05/07/13/17/18/20/21/22/25/34/44/108/110/113/115/127/160/173/
  195/199/202/205 en de kleinere `D/P2/P3`-rijen die bij lezing geen
  Rakesh-beslissing meer nodig blijken). Doel: zoveel mogelijk van deze
  batch daadwerkelijk sluiten, in batches van 5-8, met het volledige
  gate-proces per batch.
- **Dag 2**: rijen die na Dag 0's antwoorden ontgrendeld zijn (bijv. OP-40 met
  een gekozen vocabulaire, OP-62 met een gekozen triage-aanpak, OP-149/150 als
  Rakesh DROP goedkeurt, OP-137/139/141/142/143/148/153/154/155/174 voor zover
  hun onderliggende beslissing binnen is). OP-146 (de volgorde-afhankelijke
  flaky test) is een aparte, tijdrovende diagnose -- alleen oppakken als er
  ruimte is nadat de rest van dag 2 klaar is, anders als eigen registerrij
  laten staan met de huidige diagnostische stand.
- **Dag 3**: afronden wat van dag 1-2 is blijven liggen, OP-194/196/198
  (testpoort-hygiene, kan een eigen mini-iteratie zijn -- val terug op de
  "Een uitzonderingslijst die op FORMULERING matcht is geen ratchet"-les als
  je hier een guard aanpast), eindmeting, final-approver-brief voor de hele
  sprint, en een korte, eerlijke stand: hoeveel rijen ECHT dicht, hoeveel
  bewust blijven staan en waarom, wat het P0-cluster nog steeds kost als het
  ooit wordt opgepakt.

---

## Relatie tot het einddoel: een echte werkende agent conform ADR-036

Deze sprint is VOORBEREIDEND werk -- opruimen wat de fundering onbetrouwbaar
maakt (tenant-isolatie-gaten, ontbrekende guards, drift tussen migratie en
model, governance-wiring-gaten). Het is niet hetzelfde als het daadwerkelijk
bouwen van de werkende agent-hierarchie uit ADR-036 (Manager-laag,
Hierarchical Task Blackboard, de OODA-loop-observer-keten). Behandel het
bouwen van die agent als een EIGEN, volgende planningsronde met een eigen
Gate-1-plan, niet als iets dat je in de kantlijn van deze 3 dagen meeneemt.
Als er tijdens deze sprint tijd overblijft: gebruik die om de OP-01/02/03/04/05
07-rijen (allemaal ontwerpvragen over die agent-hierarchie zelf) scherper te
formuleren als input voor die volgende ronde, niet om alvast te bouwen.

---

Begin nu met Stap 1.
