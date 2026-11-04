# Backend Feature Review -- BE-CI-006

## Metadata

- Feature ID: BE-CI-006
- Feature naam: Any-type handhaving herstel -- de gate vuurde nergens en de teller was niet reproduceerbaar
- Review datum: 2026-08-13
- Reviewer: zelfreview per bestand. Gate 2 vraagt hier twee subagents (code-reviewer en
  quality-reviewer); de sessie draaide met de instructie geen subagents te starten. Die
  afwijking is expliciet en staat ook in de spec onder "Openstaand".
- Spec locatie: `docs/backend/features/BE-CI-006-any-type-handhaving-herstel.md`

---

## Eindoordeel

**APPROVED MET EEN OPENSTAANDE CONTROLE** -- de wijziging is intern consistent, in beide
richtingen mutatie-getest, en het vuren van de gate is inmiddels op een echte runner bewezen
(zie punt 2 onder Openstaand). Wat ontbreekt is de subagent-review: drie pogingen zijn op
API-limieten gestrand, dus Gate 2 is formeel niet gehaald.

Bijgewerkt 2026-08-13 na de eerste CI-runs. Die runs leverden twee bevindingen op die lokaal
niet te vinden waren -- F-007 (de teller hing af van de Python-minorversie) en F-008 (de
frontend-gate miste `any` aan het regeleinde in CRLF-bestanden). Beide zijn gerepareerd. Dat
de eerste CI-run mijn eigen ratel rood zette is het beste bewijs dat de gate werkt.

---

## Samenvatting

De opdracht was een ratel bouwen. De ratel bestond al; wat ontbrak was dat er iets handhaafde
en dat het getal betrouwbaar was. Deze review beoordeelt of de gekozen oplossing die twee
problemen echt oplost en of de guards niet hol zijn.

---

## Bevindingen

### F-001 (was CRITICAL, opgelost tijdens het bouwen) -- de frontend-terugval zou permanent rood zijn

De eerste versie van de fail-closed-terugval deed voor de frontend hetzelfde als voor de
backend: `check-any-gate.mjs --fail` over de hele boom. De frontend heeft 472 bestaande
`any`'s, dus die stap zou bij elke push zonder frontend-wijzigingen rood zijn geweest -- een
gate die altijd faalt wordt binnen een week uitgezet.

Gemeten (`exit=1` frontend, `exit=0` backend) en gecorrigeerd: de frontend valt terug op de
ratel, die de hele boom wel controleert maar alleen faalt als het getal beweegt. De asymmetrie
staat als comment in de workflow, omdat hij anders bij de eerstvolgende opschoning
"geharmoniseerd" wordt.

### F-002 (was HIGH, opgelost tijdens het bouwen) -- scope-controle sloeg aan op een schuine streep

De baseline legt `scan_dirs` vast en weigert een vergelijking met een andere scope. Een
baseline geschreven met `src/` matchte daardoor niet tegen een run met `src`. Dat is precies de
pathspec-ambiguiteit die deze wijziging wilde uitroeien, nu in de controle zelf. Genormaliseerd
door trailing slashes te strippen, en apart getest.

### F-003 (MEDIUM, geaccepteerd) -- `xargs` geeft 123 in plaats van 1

Bij een violation in het diff-pad geeft de keten `echo | xargs python check_any_gate.py --fail`
exit 123, niet 1. Dat is de xargs-code voor "een commando eindigde non-zero". Voor CI maakt het
niets uit (elke non-zero maakt de stap rood) en het aanpassen zou een extra shell-laag kosten.
Geaccepteerd, wel gemeten en benoemd.

### F-004 (MEDIUM, geaccepteerd) -- `docs/any_type_baseline.json` is 1185 regels

`per_file` staat in de baseline zodat een afwijking te debuggen is. Dat maakt het bestand
groot. De eerste commit is daardoor een grote diff; een normale update raakt alleen de regels
van de bewogen bestanden. Alternatief (alleen `total` opslaan) maakt een verschil op bijna 8000
onvindbaar. Bewuste ruil.

### F-005 (LOW, opgelost) -- het scanscript schreef ongevraagd in de repo-root

`scan_any_usage.py` negeerde zijn argumenten en schreef altijd `any_usage_scan_report.md` in de
repo-root, ook bij `--help`. Dat is tijdens het onderzoek nog gebeurd. Nu argparse met een
optionele `--report PATH`, en het achtergebleven bestand is verwijderd.

### F-007 (was CRITICAL, opgelost) -- de teller hing af van de Python-MINORVERSIE

Gevonden door de eerste echte CI-run, niet lokaal: baseline 7896, gemeten 7892. Geen
codewijziging.

`tokenize` deelt f-strings per versie anders op. Tot 3.11 is een f-string EEN STRING-token
dat al zijn regels dekt; vanaf 3.12 valt hij uiteen in FSTRING_START / FSTRING_MIDDLE /
expressietokens / FSTRING_END. `_string_literal_line_numbers()` voegde in dat tweede geval
alleen de regels toe waar een token BEGINT, en kwam op een kleinere set string-regels --
waardoor meer Any-regels als echte code werden geteld.

Gereproduceerd met twee interpreters op dezelfde boom, `src/core/agents/agent_factory.py`:

| | `FSTRING_START` | string-regels | Any geteld |
| --- | --- | --- | --- |
| py3.13 | aanwezig | 266 | 9 |
| py3.10 | afwezig | 452 | 5 |

Een f-string is nu EEN span van FSTRING_START tot FSTRING_END, met een diepteteller omdat
nesting vanaf 3.12 mag. De 3.11-semantiek is de norm: de hele f-string is stringinhoud. Na de
fix geven beide interpreters 452, 5 en repo-breed 7892. De runner had gelijk; het lokale
getal was fout. Baseline gecorrigeerd.

Dit is de DERDE variant van dezelfde fout in deze wijziging -- een teller die beweegt zonder
dat de code beweegt. De eerste twee (stille leesfout, terugval op een andere bestandsset)
vond ik lokaal. Deze was met een enkele interpreter onvindbaar. Dat maakt de CI-run bewijs en
geen formaliteit, en het is de reden dat "de gate is pas bewezen op een echte runner" in de
spec stond.

### F-008 (HIGH, opgelost) -- frontend-gate miste `any` aan het regeleinde bij CRLF

Aangewezen door de code-reviewer-subagent, die dit als cross-platform risico noemde in zijn
laatste bericht voordat hij op een API-limiet omviel. Nagetrokken en bevestigd met node:

    "const x: any"    matcht
    "const x: any\r"  matcht NIET

De patronen eindigen op `$` zonder m-vlag en `checkFile()` splitste op `'\n'` zonder de `\r`
te verwijderen. Onder `frontend/src` heeft 1884 van de bestanden lokaal CRLF; `.gitattributes`
dwingt LF alleen af voor `.sh`, `.py` en Dockerfile. Op de runner is alles LF. De gate mat dus
per platform iets anders.

Waarom lokaal en CI toch beide 472 gaven: er is momenteel geen enkele regel onder
`frontend/src` waar `any` het laatste token is -- alle treffers eindigen op `;`, `,`, `)` of
`|` en matchen via het andere alternatief. Het verschil was nul, maar door toeval.
`checkFile()` normaliseert nu `\r\n`; teller onveranderd op 472.

### F-006 (LOW, opgelost) -- non-ASCII en `datetime.now()` in aangeraakte regels

Het rapportgedeelte gebruikte emoji en een pijl, en `datetime.now()` zonder timezone. Beide
verboden per CLAUDE.md. Vervangen door ASCII en `datetime.now(timezone.utc)`. Alleen op regels
die deze wijziging toch al aanraakte -- de rest van het bestand is niet opgeschoond, om de diff
reviewbaar te houden.

---

## Guard-kwaliteit

`.claude/rules/quality-gates.md` eist dat elke guard in beide richtingen mutatie-getest is en
dat hij structuur toetst in plaats van tekst. Nagelopen:

| Guard | Mutatie die hem rood maakt | Legitiem geval blijft groen |
| --- | --- | --- |
| `test_gate_jobs_fetch_full_history` | `fetch-depth: 0` -> `1` | ja, 10 tests groen |
| `test_no_gate_step_can_exit_silently` | `exit 0` terug in de terugval | ja |
| `test_frontend_gate_runs_from_repo_root` | `working-directory: frontend` toevoegen | ja |
| `test_no_continue_on_error_on_gates` | `continue-on-error: true` op de ratel | ja |
| `test_ratchet_steps_reference_real_baselines` | baseline-pad naar een niet-bestaand bestand | ja |
| `test_baseline_higher_fails` | baseline hoger zetten | `test_baseline_equal_passes` |
| `test_unreadable_file_raises` | onleesbaar pad | de twee marker-tests |
| `scripts/hooks/pre-commit` | kale `x: Any` gestaged -> commit blokkeert | `x: Any  # TODO(TYPE)` gaat door |
| `test_a_multiline_fstring_is_one_string_span` | oude versieafhankelijke f-string-logica terug | `test_a_real_annotation_next_to_an_fstring_is_still_counted` |
| `test_crlf_file_is_flagged` | de `\r\n`-normalisatie uit checkFile() halen | `test_a_clean_file_passes_in_both_encodings` |
| `test_no_mutating_hook_runs_on_commit` | `stages: [manual]` weghalen bij black of trailing-whitespace | `test_the_mutating_hooks_still_exist` |

Drie dingen zijn hierbij misgegaan en verdienen vermelding, omdat ze precies de faalvormen zijn
die het regelbestand beschrijft:

1. **De eerste fetch-depth-mutatie kwam groen terug.** Niet omdat de guard zwak was, maar omdat
   mijn tekstvervanging de comment `# fetch-depth: 0 toegevoegd ...` trof in plaats van de
   sleutel; de YAML bleef onveranderd. Herhaald met een assertie dat de geparseerde waarde
   daadwerkelijk 1 was, en dan is hij rood. Een mutatie die niet muteert bewijst niets.
2. **De eerste hook-mutatie was een vals positief.** Het testbestand heette
   `src/tmp_hook_mutatietest.py` en `tmp_*.py` staat in `.gitignore`, dus `git add` weigerde het
   en de commit faalde omdat er niets gestaged stond -- niet omdat de hook blokkeerde. Opnieuw
   gedaan met een niet-genegeerd pad en met een expliciete controle dat er echt een bestand
   gestaged was.
3. **De eerste CRLF-mutatie landde niet.** De zoekstring in mijn mutatiescript bevatte echte
   CR/LF-tekens in plaats van de twee-tekensequenties `\r` en `\n`, doordat de escaping door
   shell en Python heen collapste. De `assert t2 != t` in het script ving dat op; daarna heb ik
   op regelnummer gemuteerd. Zonder die assertie had ik een groene testronde als bewijs gelezen
   -- dezelfde fout als punt 1, in een andere gedaante.

Alle drie hebben dezelfde vorm: de mutatie deed niet wat ik dacht, en het bewijs leek daardoor
te kloppen. De les die dit oplevert is niet "wees voorzichtiger" maar "zet een assertie in het
mutatiescript zelf": tweemaal ving die assertie de fout, eenmaal moest een tweede meting het
doen.

De guard vindt de gate-stappen op het **commando** (`check_any_gate.py`,
`check-any-gate.mjs`), niet op de stapnaam. Een naam kan blijven staan terwijl de aanroep
verdwijnt; dat is de vorm waarin zeven eerdere guards in dit project hol bleken.

---

## Wat deze wijziging NIET oplost

- De 7896 geboekte `Any`'s blijven staan. Dit is een teller die niet meer kan weglopen, geen
  afbouw.
- De frontend-ratel staat op 472 zonder dat die 472 ooit zijn beoordeeld. Ze zijn nu wel
  vastgeklikt.
- `ci-local-fast.sh` (de pre-push-gate) heeft de any-gate nog niet. De pre-commit hook dekt het
  moment ervoor, dus dit is een dubbeling die ontbreekt, geen gat.

---

## Gate 2 subagent-review -- status

Drie pogingen ondernomen op 2026-08-13. Alle zes subagents (drie rondes x twee reviewers)
stierven op een API-fout: twee keer `529 Overloaded`, de derde keer een sessielimiet die om
14:00 Europe/Amsterdam reset. Geen van de zes heeft een oordeel afgegeven.

Wat er wel uit is gekomen: de code-reviewer van de derde ronde noemde in zijn laatste bericht
een cross-platform risico met regeleindes in de frontend-gate voordat hij omviel. Die aanwijzing
is nagetrokken, bevestigd en gerepareerd -- dat is F-008 hierboven. Een reviewer die halverwege
sterft is dus niet waardeloos, maar hij is ook geen review.

**Gate 2 is hiermee NIET gehaald.** Deze review is een zelfreview. Dat is expliciet
onvoldoende volgens CLAUDE.md voor een wijziging van deze omvang, en het is de reden dat het
eindoordeel hierboven een openstaande controle noemt. De rondes moeten na 14:00 opnieuw.

## Openstaand voor de merge naar main

1. Code-reviewer en quality-reviewer subagent alsnog laten draaien. Drie pogingen zijn op
   API-limieten gestrand, niet op de code.
2. **Afgehandeld op 2026-08-13.** De CI-run bewijst dat de gate vuurt: log van run
   31682177276 regel 1096 zegt
   `Geen gewijzigde Python-bronbestanden in 724d96f2...HEAD; volledige scan als vangnet.`
   De basis-commit was dus bereikbaar (fetch-depth werkt) en het lege bereik leidde tot een
   ECHTE volledige scan in plaats van "skipping". De frontend-kant idem, met
   `Baseline: 472; gemeten: 472`. Op run 31684116372 zijn beide ratel-stappen groen.
3. De Python-job van run 31684116372 faalde op
   `tests/unit/workers/test_worker_initialiseert_de_database.py` met een
   `subprocess.TimeoutExpired` na 600s. Dat bestand is eigendom van de OP-136-commits
   (2c56b908, 724d96f2, b5f66517) van een parallelle iteratie en valt buiten deze wijziging;
   de enige aanraking van `src/workers/` hier zijn twee commentaarregels. Blijft staan voor
   die iteratie, niet voor BE-CI-006.
