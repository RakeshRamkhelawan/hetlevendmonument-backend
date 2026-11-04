# Review: BE-AGT-050 -- `autonomous_breakthrough` blijft fail-secure zonder ticket

**Spec:** `docs/backend/features/BE-AGT-050-cva-breakthrough-fails-closed-without-ticket.md` (v1)
**Reviewer:** onafhankelijke doc-reviewer-agent
**Datum:** 2026-08-19
**Methode:** elke concrete, checkbare claim geverifieerd tegen de daadwerkelijke broncode
(`git show HEAD:...` vs working tree), de nieuwe testfile, `git diff`, herhaalde
`pytest`-runs (incl. twee eigen mutatie-reverts met backup/restore, niet via `git checkout
--`), `grep`/`Glob` op de repo, en `docs/backend/features/ID-REGISTRY.md`.

---

## A. EINDOORDEEL (Ronde 1)

APPROVED WITH MINOR GAPS

---

## B. SAMENVATTING

De spec beschrijft een kleine, goed beargumenteerde fix: een misleidende TODO en een
dubbelzinnige log-marker vervangen door een eerlijke WHY-comment en marker op een codepad
dat vandaag onbereikbaar is in productie. De kernclaims (BLOCKED-pad ongewijzigd,
marker-uniciteit, enige constructieplek, dode router) zijn zorgvuldig onderbouwd en
overleven onafhankelijke verificatie. Het probleem zat niet in de argumentatie maar in de
precisie van regelverwijzingen: de spec citeerde op drie plekken regelnummers die niet
(meer) overeenkwamen met wat er werkelijk op die regels staat, waarvan er een al was
doorgesijpeld naar het nieuwe testbestand. Daarnaast was een bewijsclaim ("repo-brede
grep... precies 1 treffer") feitelijk onjuist als je hem letterlijk greept, al bleef de
conclusie zelf overeind.

---

## C. BEVINDINGEN PER CATEGORIE

### 1. Coverage gaps
Geen. Het enige gewijzigde artefact is volledig geinventariseerd.

### 2. Functionele onduidelijkheden
Geen. "Ongewijzigd extern gedrag" is correct bevestigd tegen `git show HEAD` vs working tree.

### 3. Technische onduidelijkheden (zwaartepunt van deze review)
- Sectie 2 "Locatie" citeerde `318-329`, werkelijk bereik `318-333` (de marker-aanroep op
  330-332 en de `return` op 333 vielen buiten het genoemde bereik).
- Sectie 6 stelde dat `_log_to_sandbox(...)` op regel 322-329 staat -- dat is de WHY-comment,
  niet de aanroep (die staat op 330-332).
- "In scope" citeerde het PRE-fix bereik (318-326) zonder dat als zodanig te markeren.
- "Doel"-sectie citeerde de constructieplek als regel 1055 -- klopte voor `HEAD`, maar de
  huidige (post-fix) versie heeft het op regel 1062 door de +7-regelverschuiving. Dezelfde
  stale referentie stond ook al in de nieuwe testfile-docstring.
- "Open aannames" claimde dat een grep op `.oversight_gate\s*=` precies 1 treffer geeft;
  werkelijk 2 (de bedoelde, plus een ongerelateerde in `AgentRegistry`).

### 4. Ontbrekende foutstatussen en edge cases
N.v.t., correct zo gemarkeerd.

### 5. Acceptatiecriteria problemen
Geen. Alle drie tests 1-op-1 aanwezig en gedragen zoals beschreven; zelf mutatiegetest
(marker terugzetten naar de oude tekst maakt precies de bedoelde test rood, de andere twee
blijven groen; een geinjecteerde "TICKET-STUB-OP163 aangemaakt:"-string laat de eerste test
terecht falen -- geen van de drie is een holle guard).

### 6. Integratorhandleiding / API-uitleg problemen
Geen, correct "n.v.t.".

### 7. Trainingsdata problemen
De regelnummer-fouten uit punt 3 zijn een reeel trainingsdata-risico: een systeem dat op
deze spec traint zou een verkeerd feit over de marker-locatie leren.

### 8. Structuur- en consistentieproblemen
- Build summary claimde "3 regels" wijziging; `git diff --stat` toont 9 toevoegingen /
  2 verwijderingen (11 regels) -- geen letterlijke "3 regels".
- Procedureel: `BE-AGT-050` stond nog niet in `ID-REGISTRY.md` en er bestond nog geen
  `review-BE-AGT-050.md` op het moment van Ronde 1 -- exact het patroon dat 2 dagen eerder
  (BE-FLW-057/058) al tot een dubbele ID-uitgifte leidde, al is 050 zelf bevestigd het
  daadwerkelijk vrije volgende nummer (geen collision).

### 9. Risico's voor implementatie, security of QA
Geen CRITICAL/HIGH. De security-relevante claims (geen tenant-context, `hitl_tickets.
tenant_id NOT NULL`, ADR-005, geen halve workaround) zijn feitelijk juist.

---

## D. ISSUE REGISTER

| Severity | ID/sectie | Probleem | Correctie |
|---|---|---|---|
| Medium | Sectie 6 | `_log_to_sandbox` fout gelokaliseerd op 322-329 i.p.v. 330-332 | Regelnummer gecorrigeerd, comment vs. aanroep expliciet onderscheiden |
| Medium | Sectie 2 | Locatie-bereik 318-329 dekte niet de volledige tak (318-333) | Bereik gecorrigeerd + sub-aanduiding comment/aanroep/return |
| Medium | In scope | Citeerde het PRE-fix bereik (318-326) ongemarkeerd | Beide bereiken (voor/na fix) expliciet genoemd |
| Medium | Build summary | "3 regels" i.p.v. de daadwerkelijke 9+/2- uit `git diff --stat` | Herformuleerd naar de exacte diff-omvang |
| Medium | Doel + testfile-docstring | Constructieplek regel 1055 (pre-fix) i.p.v. 1062 (post-fix) | Beide regelnummers genoemd, in BEIDE bestanden |
| Medium | Open aannames | Grep-claim "precies 1 treffer" klopte niet voor `.oversight_gate\s*=` (2 treffers) | Herformuleerd met het echte aantal + de ongerelateerde tweede treffer benoemd |
| Medium | Procedureel | Geen ID-REGISTRY-rij, geen reviewbestand bij Ronde 1 | Beide toegevoegd (deze rondes) |
| Low | Sectie 6 | "enige plek" was waar voor de bracket-vorm, niet voor de bare enum-waarde elders | Gepreciseerd: bracket-vorm i.p.v. absolute uniciteit |
| Low (pre-existing) | ID-REGISTRY.md:137 | Samenvattingstabel toonde nog `BE-AGT-### -> 029` i.p.v. 051 | Geisoleerd, 1 regel, lage impact -- direct gefixed (zie Ronde 2, punt 9) i.p.v. als los actiepunt te laten liggen. De ANDERE stale rijen in die tabel (bv. `BE-FLW-### -> 004`) zijn NIET aangepakt -- dat is een bredere, niet door deze wijziging veroorzaakte opschoning |

---

## E. ONTBREKENDE ITEMS

- Regressie-/gate-status (pyright/mypy/ruff/testtellingen) ontbrak in Build summary/Risico's
  -- toegevoegd in Ronde 2.
- ID-REGISTRY-rij en dit reviewbestand -- toegevoegd in Ronde 2.

---

## F. RONDE 2 -- FIXES TOEGEPAST (2026-08-19)

Alle zeven Medium/Low-bevindingen uit het Issue Register zijn gecorrigeerd:

1. Sectie 6: `_log_to_sandbox` nu correct op regel 330-332, met de WHY-comment op 322-329
   expliciet ervoor genoemd.
2. Sectie 2 (Locatie): bereik gewijzigd naar `318-333`, met sub-aanduiding per onderdeel
   (if/logger.warning/comment/aanroep/return).
3. "In scope": nu "vóór de fix regel 318-326, na de fix regel 318-333".
4. Build summary: "3 regels" vervangen door de exacte `git diff`-omvang (9 toevoegingen /
   2 verwijderingen).
5. "Doel"-sectie: constructieplek nu "regel 1055 in de pre-fix versie, regel 1062 in de
   huidige versie" -- ZELF opnieuw geverifieerd via `grep -n "cva_trigger =
   CVAAutonomousTrigger" src/core/agents/cva_autonomous_trigger.py` (bevestigd: 1062).
6. "Open aannames": grep-resultaat gecorrigeerd naar 2 treffers voor `.oversight_gate\s*=`
   (`cva_autonomous_trigger.py:66` + de ongerelateerde `agent_registry.py:140`), 1 treffer
   voor `CVAAutonomousTrigger\(` -- beide ZELF opnieuw gegrept, niet aangenomen van de
   reviewer.
7. Sectie 6 marker-uniciteitsclaim: gepreciseerd naar de bracket-vorm `[APPROVAL_REQUIRED]`
   i.p.v. een absolute "enige plek"-claim (de bare-word `APPROVAL_REQUIRED` komt wel elders
   voor in ongerelateerde enums).
8. Build summary/Risico's: gate-status toegevoegd (79 passed/3 xfailed gerichte set; 907
   passed architecture+unit/api; pyright 0; mypy 0/0; ruff schoon).
9. Dit reviewbestand + de ID-REGISTRY-rij zijn nu aangemaakt/bijgewerkt.

Geen van de fixes raakte productiecode of tests -- alleen documentatie (de
ID-REGISTRY.md:137-samenvattingsrij is wel gefixed, zie punt 9, maar dat is ook
documentatie).

**Eindoordeel na Ronde 2: APPROVED.**

---

## G. RONDE 3 -- VERPLICHTE BLINDE REVIEW OP DE COMMIT (2026-08-19)

De verplichte, volledig blinde onafhankelijke review op commit `49a482d0` (zonder
sessiecontext) gaf **NO-GO** met 2 BLOCKER + 4 MINOR bevindingen. Alle zes gefixt in
dezelfde sessie, geen backlog:

- **BLOCKER-1**: geen van de drie tests bewees dat `_execute_breakthrough_session()`
  daadwerkelijk NIET uitvoert -- alleen dat de LOG een bepaalde tekst wel/niet bevat. De
  reviewer verwijderde de `return` op de approval-tak en alle drie tests bleven groen
  terwijl `_run_cva_breakthrough()` en `_enable_cva_file_management()` echt draaiden
  (inclusief een echt geschreven bestand op disk). Gefixt: `_build_agent()` mockt nu ook
  `_run_cva_breakthrough`; TWEE van de drie bestaande tests (`test_no_hitl_ticket_is_
  created_when_approval_is_required` en `test_blocked_path_is_unaffected_by_the_approval_
  path_fix`) kregen een directe `assert_not_called()`-assertie toegevoegd (de derde,
  `test_the_log_message_explains_why_no_ticket_exists_instead_of_a_todo`, bleef ongewijzigd
  -- die toetst uitsluitend de logtekst), plus een vierde, NIEUWE test
  (`test_approval_required_actually_blocks_execution_not_just_the_log`) die ZELF ook
  `assert_not_called()` bevat als enige/kern-assertie -- dus 3 van de 4 tests bevatten deze
  assertie, niet "drie bestaande plus een vierde" (dat zou 4 hebben geimpliceerd). Zelf
  gereproduceerd: de `return` verwijderen maakt nu 2 van de 4 tests rood.
- **BLOCKER-2**: de OP-12-registerrij (STATUS=OPEN) rust volledig op de claim dat het pad
  vandaag dood is, maar niets bewaakte dat die claim WAAR BLIJFT. Gefixt: nieuwe
  architecture-guard `tests/architecture/test_op12_autonomous_breakthrough_stays_
  unwired.py` (AST-gebaseerd), 2 tests, elk zelf mutatiegetest (een `oversight_gate`-
  argument aan de module-singleton toevoegen, resp. een externe aanroep naar
  `start_cva_autonomous()` toevoegen, maken elke test apart rood).
- **MINOR-1**: "twee onafhankelijke routes" was onjuist -- het is EEN keten
  (`OversightGate.check` -> `PolicyEngineAdapter.validate_action` -> `ActionContext` ->
  `AGENT_ENTRYPOINT_ACTIONS`). Gecorrigeerd in zowel deze spec (sectie Doel) als de
  ADR-036-registerrij zelf.
- **MINOR-2**: het nieuwe testbestand had zelf nog de ongekwalificeerde, verouderde
  regelverwijzing `1055` in de docstring. Gecorrigeerd naar "1055 in de pre-fix versie,
  1062 in de huidige versie" -- nu in BEIDE bestanden (spec EN testbestand), niet alleen de
  spec.
- **MINOR-3**: deze reviewtekst zelf (sectie D/F hierboven) beschreef de
  ID-REGISTRY.md:137-fix als "onopgelost, buiten scope" terwijl die WEL gefixed was (029 ->
  051). Gecorrigeerd.
- **MINOR-4**: `MAX_UNVERIFIED` in `test_adr036_register_is_parseable.py` stond nog op 94
  terwijl het aantal ONGEVERIFIEERD-rijen door de OP-12-fix (ONGEVERIFIEERD -> OPEN) met
  een is gedaald naar 93. Verlaagd naar 93, conform de eigen docstring-eis van die guard
  ("dit getal mag alleen omlaag").

Herverificatie: gerichte set (impact-analyse + beide nieuwe/gewijzigde testbestanden) 88
passed / 3 xfailed / 0 failed; `python -m pyright` 0 errors; `ruff check` op alle vier
gewijzigde bestanden schoon; `python -m pytest tests/architecture/test_adr036_register_is_
parseable.py` 6 passed.

**Eindoordeel na Ronde 3: APPROVED.** Geen resterende bevindingen.

---

## H. RONDE 4 -- DERDE VERPLICHTE BLINDE REVIEW OP DE COMMIT (2026-08-19)

**GO met 1 MINOR.** De reviewer bevestigde onafhankelijk dat de BLOCKER-fix uit Ronde 3
(de ontbrekende `trigger_manual_*`-namen) daadwerkelijk stand houdt, inclusief een eigen
reconstructie van de complete call-graph naar `_execute_breakthrough_session()` (via
`_process_trigger_queue` <- `_add_trigger` <- de vier genoemde namen -- geen vijfde publieke
ingang gevonden).

**MINOR (gefixed)**: `_external_autonomous_start_callers()` matcht alleen de SYNTAX van een
aanroep (`node.func`), niet elk gebruik. Drie ontsnappingen bleven groen, alle drie zelf
gereproduceerd door de reviewer: een naam als referentie doorgeven (bv.
`router.add_api_route("/x", trigger_manual_cva_breakthrough)`), een alias-import gevolgd
door een aanroep op de alias, en een private-methode-aanroep op een geimporteerde
`cva_trigger` (`cva_trigger._add_trigger(...)`). Alle drie vereisen eerst een import.
Gefixt: nieuwe test `test_nothing_outside_the_module_imports_the_singleton_or_its_start_
functions`, die elke externe `from ...cva_autonomous_trigger import <naam>` (voor
`cva_trigger` of een van de vier startfuncties) verbiedt -- dit subsumeert alle drie
ontsnappingen in een keer, omdat elk gebruik eerst een import vereist. Zelf gereproduceerd:
alle drie de ontsnappingen (referentie, alias, private-methode-import) maken deze nieuwe
test rood; teruggedraaid, weer groen.

Herverificatie: alle drie tests in `test_op12_autonomous_breakthrough_stays_unwired.py`
groen; `python -m pyright` 0 errors; `ruff check` schoon.

**Eindoordeel na Ronde 4: APPROVED.** Geen resterende bevindingen.

---

## I. RONDE 5 -- VIERDE VERPLICHTE BLINDE REVIEW OP DE COMMIT (2026-08-19)

**GO met 1 MINOR, met een expliciete proportionaliteitsbeoordeling van de reviewer.** De
import-check uit Ronde 4 dekte alleen `from ...cva_autonomous_trigger import <naam>`
(`ast.ImportFrom`), niet `import ...cva_autonomous_trigger as m` gevolgd door
`m.cva_trigger._add_trigger(...)` (whole-module import + attribuutketen, `ast.Import`) --
zelf gereproduceerd: bleef groen terwijl dit een levend pad naar
`_execute_breakthrough_session()` opent. De reviewer beoordeelde dit expliciet als de LAATSTE
zinvolle ronde op deze guard: vier rondes vonden een dalende reeks (twee echte functionele
gaten, dan syntax-randgevallen, dan importvorm-randgevallen) op een pad zonder enige echte
aanroeper in de hele repo (herhaaldelijk, onafhankelijk bevestigd) -- verdere AST-verfijning
zou geen drift meer vangen, alleen opzettelijke omzeiling door iemand met commit-rechten,
waar geen AST-guard tegen bestand is.

Gefixt: een `ast.Import`-tak in `_external_importers_of_governance_bypassing_names()` die
elke whole-module-import van `cva_autonomous_trigger` zelf als bevinding markeert (ongeacht
wat ermee gedaan wordt na de import) -- er is vandaag geen legitiem gebruik van een
whole-module-import van dit bestand. Beide richtingen mutatiegetest: de whole-module-import-
ontsnapping maakt de test rood; het enige echte externe gebruik (`from
...cva_autonomous_trigger import TriggerType` in `mode_manager.py`, al onderdeel van de
gescande bestanden) blijft terecht groen. De eerdere overclaim ("dicht alle drie
ontsnappingen") in de module- en testdocstrings gecorrigeerd naar "dicht ze voor de
ImportFrom-vorm" resp. nu "beide importvormen gedekt".

Herverificatie: alle drie tests groen; `python -m pyright` 0 errors; `ruff check` schoon.

**Eindoordeel na Ronde 5: APPROVED.** (Achteraf gebleken: de "dit sluit de reviewrondes"-
uitspraak hieronder was zelf voorbarig -- zie Ronde 6.)

---

## J. RONDE 6 -- VIJFDE VERPLICHTE BLINDE REVIEW OP DE COMMIT (2026-08-19)

**NO-GO met 1 concrete, aangetoonde bevinding (geen theoretische escalatie).** De reviewer
reproduceerde exact de ene claim uit Ronde 5 ("compleet"): de `ast.Import`-fix loste
`import ...cva_autonomous_trigger as m` op, maar een whole-module import kan OOK via
`ast.ImportFrom` gespeld worden -- `from src.core.agents import cva_autonomous_trigger as
m` en de relatieve vorm `from . import cva_autonomous_trigger as m`. Beide bleven groen met
dezelfde payload (`m.cva_trigger._add_trigger(...)`), zelf gereproduceerd door de reviewer.
Oorzaak: de bestaande ImportFrom-tak filterde op `"cva_autonomous_trigger" not in
node.module`, maar bij deze twee vormen staat de string "cva_autonomous_trigger" niet in
`node.module` (dat is het PAKKET) maar in `alias.name` (de module wordt zelf als naam
geimporteerd) -- de relatieve vorm had zelfs `node.module is None`, wat de oude filter
volledig blokkeerde vóór de naamcheck.

De reviewer benoemde dit expliciet als geen "verzonnen zesde ronde": het is dezelfde
faalvorm als Ronde 5 zelf beschreef (een "compleet"-claim die niet klopte), nu voor een
concreet aangetoonde derde/vierde spelling in plaats van een theoretische.

Gefixt: een check op `alias.name == "cva_autonomous_trigger"` toegevoegd in de
ImportFrom-tak, VOOR de module-string-filter, zodat beide resterende vormen gevangen
worden. Met nu VIER importvormen gedekt (`import X`, `import X as m`, `from Y import X as
m`, `from . import X as m`) is de "compleet"-claim uit Ronde 5 nu pas daadwerkelijk waar.
Beide nieuwe vormen mutatiegetest (elk apart rood, teruggedraaid); de legitieme
`TriggerType`-import in `mode_manager.py` opnieuw bevestigd groen. De docstrings zijn
aangevuld met een expliciete les: een toekomstige "compleet"-claim over deze guard moet de
genoemde verzameling van vormen benoemen, niet het woord "compleet" op zichzelf gebruiken.

Herverificatie: alle drie tests groen; `python -m pyright` 0 errors; `ruff check` schoon.

**Eindoordeel na Ronde 6: APPROVED. Dit sluit de reviewrondes op
`test_op12_autonomous_breakthrough_stays_unwired.py` -- verdere AST-hardening (dynamische
imports via `importlib`, `getattr`-dispatch, etc.) op dit zonder-aanroepers-pad is vanaf
hier bewust niet nagejaagd; zes opeenvolgende rondes vonden een dalende reeks concrete
bevindingen (twee echte functionele gaten, dan syntax-, dan drie importvorm-
randgevallen), en verdere verfijning zou geen drift meer vangen maar alleen opzettelijke
omzeiling door iemand met commit-rechten, waar geen AST-guard tegen bestand is.**

(Deze "sluit de reviewrondes"-uitspraak bleek zelf voorbarig -- zie Ronde 7, de daadwerkelijk
laatste ronde.)

---

## L. RONDE 7 -- ZESDE VERPLICHTE BLINDE REVIEW OP DE COMMIT (2026-08-19)

**GO, nul blokkerende bevindingen. Dit is daadwerkelijk de laatste ronde.** De reviewer
kreeg de eigen structurele analyse van de implementatie-agent voorgelegd (vijf
importspellingen zouden nu gedekt zijn) en heeft die ZELF nagemeten in plaats van
aangenomen, inclusief een expliciete mutatietest op spelling 2
(`from .cva_autonomous_trigger import <naam>`, relatieve submodule-import) die bevestigde
dat de ORIGINELE ronde-3-filter die al ving.

Twee documentatienits gevonden, expliciet als "geen fix nodig om te sluiten" gekwalificeerd
door de reviewer zelf, maar toch toegepast (goedkoop, en precies de les die deze hele
reeks probeerde te leren): de opsomming noemde vier vormen i.p.v. vijf, en de herhaalde
formulering "elk gebruik vereist eerst een import" was strikt onwaar (een
parent-package-import + attribuutketen, een publieke-klasse-plus-private-methode, en een
door `__all__` onschadelijk gemaakte star-import blijven allemaal groen). De reviewer
beoordeelde deze drie expliciet als de deliberate-circumventie-kant van de grens die alle
rondes al erkennen, NIET als een achtste bevinding -- niemand schrijft zo'n constructie per
ongeluk. Docstrings gecorrigeerd: vijf spellingen expliciet genoemd, "elk gebruik" vervangen
door "elk idiomatisch gebruik... vereist een import die deze module bij naam noemt".

Herverificatie: alle drie tests groen; `python -m pyright` 0 errors; `ruff check` schoon.

**Eindoordeel na Ronde 7: APPROVED. Dit sluit de reviewrondes op
`test_op12_autonomous_breakthrough_stays_unwired.py` definitief.**

---

## M. RELEASE-OORDEEL

- Geschikt voor bouw/implementatie: Ja -- de code is al gebouwd, correct en veilig.
- Geschikt voor QA en geautomatiseerd testen: Ja -- alle drie tests bestaan, matchen de
  acceptatiecriteria letterlijk, en zijn mutatiegetest (niet vacuous).
- Geschikt voor LLM-training: Ja, na de Ronde-2-correcties (de regelnummer-fouten die dit
  eerst blokkeerden zijn gefixed).
- Geschikt voor integratorhandleiding/API-documentatie: N.v.t., geen publieke API.
