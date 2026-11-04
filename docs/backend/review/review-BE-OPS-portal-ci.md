# Review BE-OPS-portal-ci: portal-job in ci-feature.yml + lokale act-runner

STATUS: APPROVED WITH MINOR GAPS

**Reviewer:** onafhankelijke Gate 2-review-agent (code-reviewer + quality-reviewer ineen, Red Team). Code niet zelf geschreven; worktree `hlm-wk1-ci-portal` read-only gereviewd (alleen dit review-document is toegevoegd). Elke claim uit commits, spec en bevindingen-brief is zelf met commando's her-verifierd; niets op aannames overgenomen.
**Datum:** 2026-09-24
**Scope:** commits `a811fd189` + `51a865565` op branch `iter/wk1-ci-portal` (diff t.o.v. `45f3f45fe`) -- `.github/workflows/ci-feature.yml` (nieuwe job `portal`), `scripts/run_ci_act.ps1` (ValidateSet + `$defaultTargets`), spec `docs/backend/specs/spec-BE-OPS-portal-ci.md`, bevindingen-brief `docs/agent-briefs/generated/2026-09-24-bevinding-portal-lint-stub.md`. Context gelezen: guard `tests/architecture/test_local_ci_runner_covers_every_ci_job.py`, `portal/package.json`, `portal/package-lock.json` (engines-analyse), workflow-kop en frontend-job ter vergelijking, `.actrc`, gedeelde `.git/hooks/pre-push`.

---

## B. Eindoordeel

APPROVED WITH MINOR GAPS -- de kern is aantoonbaar correct: de YAML laadt (`yaml.safe_load`), de portal-job staat er met zes stappen gespiegeld aan de echte scripts in `portal/package.json`, de guard is zelf gedraaid groen (`2 passed`) en een gesimuleerde mutatie (portal uit de ValidateSet) laat hem rood gaan met exact `['portal']` als ontbrekende job, en alle vier de native checks zijn door deze review herhaald met dezelfde uitkomst als de spec claimt (type-check exit 0, vitest 86/86 in 72.34s, build groen in 14.94s, `npm run lint` faalt inderdaad met "eslint is not recognized"). Het weglaten van de lint-stap is gemeten juist (eslint zit nergens: niet in deps, niet in de lockfile, geen config) en eerlijk gedocumenteerd op drie plekken plus een eigen herstel-brief. De minor gaps: (1) de spec claimt Node-20-compatibiliteit als feit, maar de lockfile bevat een directe devDependency (`@testing-library/jest-dom@^7.0.1`, engines `>=22`) die Node 20 uitsluit, en de enige echte uitvoerder (act) is nooit gedraaid -- de job kan bij zijn eerste echte run rood zijn; (2) de guard bewaakt alleen de ValidateSet-pariteit, niet `$defaultTargets` -- portal kan stilletjes uit de standaardbatch verdwijnen terwijl de guard groen blijft; (3) drie kleine documentatie-afwijkingen (eslint in een runner-commentaarregel, workflow-kop niet bijgewerkt, spec in een nieuwe `specs/`-map i.p.v. het voorgeschreven `features/`-pad). Punt 1 verdient een eenmalige verificatie (`.\scripts\run_ci_act.ps1 -Job portal` of `node-version: 24` voor de portal-job) voordat een develop-push op deze job gaat vertrouwen; niets blokkeert de merge zelf, want de wijziging degradaat niets bestaands en voegt dekking toe waar er geen was.

## C. Samenvatting

Verificatie met eigen runs vanuit de worktree (venv en node_modules van de worktree/hoofdrepo):

- **YAML-syntax geldig:** `yaml.safe_load` op `ci-feature.yml` slaagt; `jobs` bevat `['bicep', 'python', 'any-type-baseline', 'frontend', 'portal', 'docker-validate', 'security']`; de portal-job heeft de zes verwachte stappen (checkout, setup-node, npm ci, type-check, test, build) en `timeout-minutes: 30`.
- **Guard zelf gedraaid: 2 passed in 0.52s.** Mutatiebewijs gesimuleerd zonder bestanden te muteren (bronstring in-memory aangepast): portal uit de ValidateSet -> test 1 zou rood gaan met precies `['portal']` als ontbrekende job. De guard parst de workflow structureel (yaml) en leest de ValidateSet via een gerichte regex, niet via een losse substring -- geen tekst-vs-structuur-valkuil. Wel: de guard toetst `$defaultTargets` NIET (gemeten: de string `defaultTargets` komt niet in de guard voor) -- zie E, MEDIUM-2.
- **Native checks herhaald, claims kloppen:** `npm run type-check` exit 0 zonder foutoutput; `npm test` -> `Test Files 19 passed (19)`, `Tests 86 passed (86)`, 72.34s; `npm run build` exit 0, `built in 14.94s` (de >500 kB chunk-waarschuwing is inderdaad een waarschuwing, geen fout).
- **Lint-stub-claim klopt volledig:** `grep -i eslint` op `portal/package.json` treft alleen het dode script `"lint": "eslint ."`; de lockfile bevat nul eslint-treffers; er is geen `.eslintrc*`/`eslint.config.*` in `portal/`; `npm run lint` faalt reproduceerbaar met `'eslint' is not recognized as an internal or external command`.
- **Runner-wijziging consistent:** ValidateSet bevat `'portal'`, `$defaultTargets` bevat `'portal'` (gevallen van "wel in de set, niet in de batch" is er dus niet), `$buitenAct` ongemoeid, documentatie-commentaar bijgewerkt -- met uitzondering van regel 93 (zie E, LOW-1).
- **Patroon-consistentie met frontend-job:** zelfde `setup-node@v4` + `cache: npm` + `cache-dependency-path`, zelfde schedule-ref-truc (`ref: ${{ github.event_name == 'schedule' && 'develop' || '' }}`), zelfde redundante stap-niveau `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24` (staat al in het workflow-niveau `env`, regel 35 -- bij beide jobs dode configuratie, dus consistente cargo, geen schending). Geen `fetch-depth: 0` is correct: er is geen diff-gebaseerde gate in deze job.
- **Worktree-hooks-claim klopt:** `git rev-parse --git-common-dir` vanuit de worktree geeft `C:/Users/rsram/OneDrive/Documenten/GitHub/het-levend-monument/.git` -- worktrees delen inderdaad `.git/hooks`, de geinstalleerde pre-push hook geldt ook hier. Spec-sectie "Pre-push hook en worktree-hooks" is dus correct.
- **Node-versie-risico is NIET correct beoordeeld in de spec** -- zie E, MEDIUM-1. De spec zegt "portal gebruikt vite 5 / typescript 5.5, compatibel", maar een engines-analyse van de lockfile (alle `engines.node`-velden uitgelezen) toont: `@testing-library/jest-dom` (directe devDependency, `>=22` -- Node 20 valt erbuiten), `jsdom` (`^20.19.0 || ^22.13.0 || >=24.0.0` -- Node 20 alleen vanaf 20.19, `setup-node` met `node-version: 20` pakt de nieuwste 20.x dus dit is ok), `@napi-rs/lzma-linux-x64-gnu` (`^22.20 || ^24.12 || >=25`, maar dat is een *optionele* rollup-binding -- laag risico) en vier jsdom-hulppakketten (`^20.19.0 || ^22.12.0 || >=24.0.0`). Lokaal draait alles op Node v24.15.0; de job draait op 20; de act-run die dat zou bewijzen is nooit uitgevoerd (spec benoemt dat eerlijk onder "Open aannames", maar de compatibiliteitsclaim in sectie 12 staat er als feit).

Niet herhaald: de act-run zelf (vereist Docker-sessie; buiten het bereik van een read-only review) en een echte bestandsmutatie van de guard (worktree read-only; in plaats daarvan in-memory gesimuleerd, zie hierboven).

## D. Bevindingen per categorie (samengevat)

1. **Correctheid** -- De job-definitie is een getrouwe spiegeling van `portal/package.json`: `type-check` = `tsc --noEmit`, `test` = `vitest run`, `build` = `tsc && vite build`; alle drie native groen herhaald. `npm ci` hangt aan `portal/package-lock.json` (aanwezig, geverifieerd). De `build`-stap is deels dubbel (`tsc` draait dan twee keer per job: een keer `--noEmit`, een keer in de build) -- onschadelijk, secondenwerk. Geen tautologie of holle stap gevonden: elke stap is blokkerend zonder `continue-on-error`.
2. **Guard-dekking** -- Pariteit workflow <-> ValidateSet is echt bewaakt (structuur, geen substring; mutatie in beide richtingen aantoonbaar). Maar de guard kent het begrip "standaardbatch" niet: `$defaultTargets` en `$buitenAct` worden niet gelezen. De eigen faal-boodschap van de guard instrueert "zet hem in de standaardlijst of in $buitenAct" -- een instructie die de test zelf niet afdwingt. In deze commit staat portal correct in beide; de guard kan dat alleen niet vasthouden.
3. **Architectuur/regels** -- Geen applicatiecode aangeraakt, dus ADR-033/034, tenant-isolatie en de backend-gates zijn n.v.t. ASCII-check op de twee gewijzigde bestanden en de twee nieuwe docs: schoon (Nederlandse tekst zonder diakrieten, geen emoji). Geen secrets, geen `datetime.now()`. De workflow-wijziging raakt geen `continue-on-error`-vlag van een bestaande quality-gate-stap.
4. **Proces/docs** -- Spec volgt het FEATURE_DOC_WORKFLOW-sjabloon qua inhoud (metadata, scope, inventory, 19 detail-secties, trainingssamenvatting, acceptatiecriteria met metingen), maar staat in `docs/backend/specs/` -- een nieuwe map met alleen dit bestand -- terwijl het workflow `docs/backend/features/<ID>-<naam>.md` voorschrijft. ID-REGISTRY-uitstel naar de regisseur is conform de bestaande praktijk (commit `45f3f45fe` deed dat centraal voor vier andere ID's). De bevindingen-brief volgt de post-2026-09-19-regel (eigen brief in `docs/agent-briefs/generated/`, geen registerrij) correct, met meetbewijs en acceptatiecriteria voor de reparatie.
5. **Risico-inschatting** -- De beslissing "geen lint-stap" is gemeten en goed onderbouwd (een per constructie rode stap went -- dezelfde reden die de workflow-kop zelf geeft voor het stilleggen van Actions). De beslissing "Node 20 is compatibel" is daarentegen ongemeten en door de lockfile deels tegengesproken; de enige omgeving waar de job ooit zal draaien (act-container, Node 20) is nooit getest.

## E. Issue register

| Severity | Locatie | Probleem | Correctie |
| --- | --- | --- | --- |
| MEDIUM | `.github/workflows/ci-feature.yml` (`env.NODE_VERSION: 20`) + `portal/package-lock.json` | De spec claimt Node-20-compatibiliteit als feit (sectie 12), maar `@testing-library/jest-dom@^7.0.1` -- een directe devDependency die in de vitest-setup van vrijwel elke testfile geladen wordt -- declareert `engines.node >= 22`. `npm ci` faalt daar niet op (engine-strict staat default uit, dus alleen een EBADENGINE-waarschuwing), maar als jest-dom 7 een Node-22-only API gebruikt, gaat de `Unit tests`-stap onder Node 20 rood terwijl hij lokaal (Node 24) groen is. De act-run die dit zou bewijzen is nooit gedraaid. Gevolg als het misgaat: de nieuwe job is bij zijn eerste echte run rood -- precies het "een job die altijd faalt went"-scenario dat deze commit zelf als reden noemt om lint weg te laten. | Eenmalig `.\scripts\run_ci_act.ps1 -Job portal` draaien; bij rood: `node-version: 24` (of `'>=20.19'` waar dat volstaat) alleen voor de portal-job zetten in plaats van de gedeelde `env.NODE_VERSION`, en de spec-sectie 12 corrigeren van feit naar meting. |
| MEDIUM | `tests/architecture/test_local_ci_runner_covers_every_ci_job.py` (ongewijzigd, blootgesteld door deze commit) | De guard bewaakt alleen ValidateSet-pariteit. Haal een volgende iteratie `'portal'` uit `$defaultTargets` (of zet een nieuwe job er alleen in de ValidateSet bij) en de guard blijft groen terwijl de job in de standaardflow nooit meer draait -- de exacte stille-dekkingsvermindering waarvoor de guard bestaat ("zo'n job draait NERGENS en wordt nooit rood"). De faal-boodschap instrueert de standaardlijst/$buitenAct wel, maar de test dwingt het niet af. | Guard uitbreiden: elke workflow-job MOET in `$defaultTargets` of in `$buitenAct` staan (met reden), plus mutatiebewijs in beide richtingen. Losse taak; niet blokkerend voor deze merge omdat portal nu correct in beide staat. |
| LOW | `scripts/run_ci_act.ps1:93` | Commentaar boven `$defaultTargets` zegt "'portal' is lichtgewicht (npm ci + tsc + eslint + vitest + vite build ...)" -- eslint draait juist NIET; dat is de kernbeslissing van deze iteratie. De enige plek in de runner die de stappen opsomt, somt een stap op die bewust is weggelaten. | `eslint + ` schrappen uit die regel. |
| LOW | `.github/workflows/ci-feature.yml` kop (regel ~19) | Het kopcommentaar somt de act-runner-dekking op als "security, frontend, docker-validate, bicep" -- portal ontbreekt. | `'portal'` toevoegen aan die opsomming bij de eerstvolgende workflow-wijziging. |
| LOW | `docs/backend/specs/` (map) | FEATURE_DOC_WORKFLOW schrijft `docs/backend/features/<ID>-<naam>.md` voor; deze spec introduceert een parallelle `specs/`-map met een eigen naamconventie (`spec-BE-OPS-portal-ci.md`). Een tweede conventie naast de eerste maakt het register en toekomstige guards (die op `features/` zouden kunnen toetsen) minder betrouwbaar. | Verplaats naar `docs/backend/features/BE-OPS-portal-ci.md`, of leg de `specs/`-variant als bewuste conventie vast in FEATURE_DOC_WORKFLOW. Een van de twee, niet laten zweven. |
| LOW | `ci-feature.yml` portal-job (`ref:` schedule-truc) | De workflow heeft sinds 2026-09-14 alleen `workflow_dispatch`; de schedule-tak van de ref-expressie is dode configuratie. Consistent met alle andere jobs (die ervoor toen de trigger nog bestond), dus geen schending -- maar het commentaar "Zelfde schedule-uitzondering als de andere jobs" kopieert een dood patroon door. | Accepteren (consistentie wint), of centraal opruimen als Actions-structureel uit blijft. Geen actie in deze iteratie. |

## F. Ontbrekende items

- Eenmalige act-run van de portal-job (`.\scripts\run_ci_act.ps1 -Job portal`) als bewijs dat de job in zijn enige echte uitvoeromgeving groen is -- of de Node-versie-bump als dat rood blijkt. Dit is het enige punt dat geen bijvangst mag worden: zonder deze meting blijft "de portal zit in de CI" een papieren waarheid.
- Correctie van spec-sectie 12 ("compatibel" als feit -> gemeten uitslag van de act-run, inclusief de jest-dom engines-constatering).
- De guard-uitbreiding voor `$defaultTargets`/`$buitenAct` (MEDIUM-2) verdient een eigen brief in `docs/agent-briefs/generated/` conform de post-2026-09-19-regel; nu staat hij nergens vast.
- De drie LOW-documentatiepunten (eslint in runner-commentaar, workflow-kop, spec-pad).

## G. Verbeterde codevoorstellen

Guard-uitbreiding (richting, geen kant-en-klare code -- mutatiebewijs in beide richtingen hoort erbij):

```python
def test_elke_job_draait_in_de_standaardbatch_of_heeft_een_gedocumenteerde_reden() -> None:
    """Een job die alleen in de ValidateSet staat, draait in de standaardflow NERGENS."""
    bron = _RUNNER.read_text(encoding="utf-8")
    batch = set(re.findall(r"'([^']+)'", re.search(r"\$defaultTargets = @\(([^)]*)\)", bron).group(1)))
    buiten = set(re.findall(r"'([^']+)'\s*=", re.search(r"\$buitenAct = @\{(.*?)\}", bron, re.S).group(1)))
    # any-type-baseline heeft een gedocumenteerde handmatige status in de runner-output
    gedocumenteerd = batch | buiten | {"any-type-baseline"}
    assert not (_workflow_jobs() - gedocumenteerd), "..."
```

Portal-job indien de act-run rood blijkt op Node 20:

```yaml
      - uses: actions/setup-node@v4
        with:
          # portal vereist >= 22 (jest-dom 7 engines, gemeten in package-lock.json
          # 2026-09-24); frontend blijft op de gedeelde NODE_VERSION 20.
          node-version: "24"
```

## H. Release-oordelen

- Bouw/implementatie: **ja** -- de job en runner-wijziging zijn correct, minimaal en consistent met het frontend-patroon.
- QA/geautomatiseerd testen: **ja, met voorbehoud** -- guard groen en mutatie-bewezen voor het deel dat hij bewaakt; native checks door deze review herhaald met identieke uitslag. Voorbehoud: de job is nooit in zijn echte uitvoeromgeving (act, Node 20) gedraaid en de lockfile bevat een directe dependency die Node 20 uitsluit (MEDIUM-1).
- LLM-training: **ja**.
- Integratorhandleiding / spec: **ja, na correctie** -- de spec is volledig en eerlijk over wat niet is gedaan (act-run), maar sectie 12 presenteert een ongemeten compatibiliteitsaanname als feit; dat moet een meting worden zodra de act-run heeft plaatsgevonden. De bevindingen-brief voor de lint-stub is volledig conform de nieuwe regel (meetbewijs, reden, reparatiepad, acceptatiecriteria).

## Wat wel klopt

- De YAML is echt valide (geladen met `yaml.safe_load`, niet alleen bekeken) en de job staat structureel goed: zes stappen, allemaal blokkerend, geen `continue-on-error`, geen onnodige `fetch-depth: 0`.
- De stappen zijn een exacte spiegeling van de werkelijke scripts in `portal/package.json` (gelezen, niet gegokt): `tsc --noEmit`, `vitest run`, `tsc && vite build`.
- Alle native claims door deze review onafhankelijk herhaald met dezelfde uitkomst: type-check exit 0, 19/19 testfiles en 86/86 tests groen (72.34s), build groen (14.94s). De spec-metingen (75.52s / 16.09s) liggen binnen normale run-variatie.
- De lint-stub-claim is volledig en correct gemeten: eslint ontbreekt in dependencies, devDependencies, de hele lockfile en er is geen config; `npm run lint` faalt reproduceerbaar. De keuze om een per constructie rode stap NIET op te nemen is de juiste -- het alternatief (wel opnemen en rood laten) is precies het went-scenario dat de workflow-kop beschrijft.
- De guard is echt gekoppeld: hij parst de workflow als YAML (structuur) en de ValidateSet via een gerichte regex met expliciete reden waarom geen substring-zoektocht; de in-memory mutatie (portal uit de ValidateSet) produceert precies de door de spec beschreven rode assertie met `['portal']`.
- Het rood-bewijs in de spec (guard faalde met `1 failed, 1 passed` toen de job in de workflow stond maar nog niet in de runner) is consistent met de guard-logica zoals deze review die heeft nagegaan.
- De worktree-hooks-claim is kloppend en bovendien zelf geverifieerd in de spec (`git rev-parse --git-common-dir` -> gedeelde `.git` van de hoofdrepo); deze review heeft dezelfde meting herhaald met dezelfde uitkomst.
- De bevindingen-brief volgt de post-2026-09-19-regel precies: eigen brief in `docs/agent-briefs/generated/`, geen registerrij, met meetbewijs en concrete acceptatiecriteria voor de reparatie -- inclusief de eerlijke markering dat "overgekopieerd uit een template" een vermoeden is, geen meting.
- Eerlijke meetcultuur: de spec benoemt de niet-gedraaide act-run als open aanname met een exact verificatiecommando, markeert de jsdom-waarschuwingen als bestaand gedrag en de chunk-waarschuwing als niet-blokkerend -- alle drie door deze review kloppend bevonden.

## Devil's Advocate -- waarom faalt deze oplossing in de toekomst?

1. **De job kan bij zijn eerste echte run rood zijn -- en niemand merkt het tot iemand handmatig act draait.** GitHub Actions is dood; de enige uitvoerder is een handmatige `run_ci_act.ps1`. Als jest-dom 7 onder Node 20 breekt, is de portal-job vanaf dag een rood, en omdat er geen automatische trigger is, is er geen moment waarop dat vanzelf opvalt. Deze iteratie citeerde "een run die altijd faalt went" als reden om lint weg te laten -- en levert mogelijk precies zo'n job op. De mitigatie is een commando (`-Job portal`), maar dat commando is nooit uitgevoerd.
2. **"Compatibel" als feit in sectie 12 is een landmijn voor de volgende lezer.** De WHY-regel in quality-gates.md (een oorzaak/claim mag alleen staan als je de meting kunt noemen) is hier in tegengekomen: de claim is waar voor vite/typescript maar de engines-analyse die hem zou staven of ontkrachten is niet gedaan. Een volgende developer die de portal-job als voorbeeld kopieert voor een derde app, kopieert ook de ongemeten aanname -- en voor die app kan hij wel onwaar zijn.
3. **De guard bewaakt de verkeerde laag voor de werkelijke uitvoering.** ValidateSet-pariteit voelt als "de runner kent de job", maar de standaardflow draait `$defaultTargets`. Een toekomstige opruimer die `'portal'` uit die array haalt ("is toch lichtgewicht, draaien we wel los") produceert precies de stille dekkingsvermindering waarvoor deze guard ooit is gebouwd -- en de guard zegt niets. De bewaker bewaakt de catalogus, niet de werkvloer.
4. **De gedeelde `env.NODE_VERSION` koppelt twee onafhankelijke apps.** Als frontend ooit naar Node 22/24 moet (of juist gepind blijft op 20 voor een oude dependency), erft portal die keuze zonder eigen afweging -- terwijl de lockfiles volstrekt onafhankelijk zijn en portal vandaag al een >=22-dependency heeft. De "consistentie" van één gedeelde versie is schijn: het is een koppeling zonder eigenaar.
5. **De lint-brief kan verworden tot een permanent gat.** De brief is netjes, maar heeft geen eigenaar en geen datum. "Portal heeft geen lint" wordt dan de nieuwe norm, het dode `"lint": "eslint ."`-script blijft nieuwe developers misleiden (de eerste die het serieus neemt "fixt" het misschien door eslint te installeren met een default-config die 400 overtredingen geeft -- en dan is de verleiding groot om `continue-on-error` te gebruiken), en de dekking tussen frontend en portal drijft stilletjes verder uit elkaar: frontend heeft coverage-drempels en lint, portal heeft geen van beide.
6. **`npm ci` met EBADENGINE-waarschuwingen went ook.** Zodra de act-run eenmaal draait, zal de log altijd engine-waarschuwingen bevatten (jest-dom >=22 op Node 20). Waarschuwingen die er structureel zijn, worden onzichtbaar -- tot een echte engine-incompatibiliteit zich er tussen verstopt. De schone oplossing (portal-job op Node 24, of `engines` vastleggen in `portal/package.json` zodat de mismatch een fout wordt in plaats van een waarschuwing) is niet gekozen.

Geen van deze punten blokkeert de merge: de wijziging voegt gemeten dekking toe waar er geen was en degradeert niets bestaands. Punt 1 vereist een eenmalige verificatie voordat een develop-push op deze job vertrouwt, punt 2 een zinnetje in de spec, punt 3 een eigen guard-brief, punten 4-6 zijn bewust te accepteren risico's die nu tenminste vastliggen.
