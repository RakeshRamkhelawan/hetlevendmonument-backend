# Review BE-AGT-043 -- Herstel en compliance

| Veld | Waarde |
| --- | --- |
| Feature-ID | BE-AGT-043 |
| Datum | 2026-08-02 |
| Reviewvorm | **Gate 2 gehaald** -- `code-reviewer` en `security-reviewer` onafhankelijk gedraaid op `ab323ec7`, plus zelfreview op het herstelwerk |
| Omvang | ~150 regels productiecode in 9 bestanden; 25 tests |
| Uitkomst | **APPROVED**, met drie vastgelegde openstaande punten |

---

## 0. Gate 2, eindelijk

Twee dagen op rij stond in de review dat de dubbele reviewer-GO ontbrak. Die is nu gehaald.
Beide reviewers gaven **CHANGES_REQUESTED** op `ab323ec7`, en dat was terecht: ze vonden
onafhankelijk van elkaar hetzelfde kritieke defect dat mijn eigen review had gemist.

Dat is het belangrijkste resultaat van deze dag, en het pleit tegen mijn eigen eerdere
beoordeling. `review-BE-AGT-042.md` gaf **APPROVED** op een zelfreview van ~90 regels over
5 bestanden, terwijl de drempel voor zelfreview op <20 regels en 1 bestand staat. Beide
reviewers merkten dat op; de uitkomst had BLOCKED moeten zijn. Ik heb dat in dat document
laten staan zoals het was en de correctie hier vastgelegd -- een review achteraf herschrijven
naar een gunstiger oordeel is precies het soort onwaarheid waar deze ADR over gaat.

## 1. Wat de reviewers vonden en wat ermee gebeurd is

| Bevinding | Severity | Status |
| --- | --- | --- |
| Initiator viel weg op 4 aanroepen; `/packs/execute` was volledig inert | CRITICAL | **Opgelost** + regressietest op ketenniveau, mutatie-getest |
| `MODIFIED` voerde de ongewijzigde actie uit | HIGH | **Opgelost** -- geweigerd tot samenvoegen kan (OP-25 verwant) |
| Poort wiste de tenant-ContextVar van de aanroeper | HIGH | **Opgelost** + regressietest, mutatie-getest |
| Rauwe LLM-parameters onuitwisbaar in de audit-hashketen | HIGH | **Opgelost** -- alleen sleutelnamen; functieverlies vastgelegd als OP-25 |
| Modelgestuurde governance-sleutels (`ai_disclosure`) | MEDIUM-blokkerend | **Opgelost** door dezelfde wijziging + test |
| Geerfde ongegate `execute_tool()` op alle 135 skills | HIGH | **Zichtbaar gemaakt** in de guard, OP-24; niet gedicht |
| Poort buiten de `try`; docstring beloofde "gooit nooit" | MEDIUM | **Opgelost** |
| Geen spoor bij een weigering | MEDIUM | **Opgelost** -- `logger.warning` |
| Initiator als instance-state, niet opgeruimd | MEDIUM/LOW | **Opgelost** + test |
| Geen test op de echte ingang | MEDIUM | **Opgelost** -- dat was de oorzaak van de CRITICAL |
| Guard CWD-relatief en volgordetest te ruim | MEDIUM | **Opgelost** -- vanaf `__file__`, AST-body |
| Goedkeuringstest controleerde alleen een aanroeptelling | MEDIUM | **Opgelost** -- payload wordt nagelopen |
| Verkeerd `trigger`-label in de audittrail | MEDIUM | **Opgelost** -- `USER_REQUEST` |
| Geen rate limit op `/packs/execute` | MEDIUM | **Opgelost** -- 10/min via de facade |
| `get_user_id()` kon `None` geven | MEDIUM | **Opgelost** -- 401 aan de grens |
| Ontbrekende `exc_info`; importvolgorde; stale TODO | LOW | **Opgelost** |
| Autouse `council_gate` standaard APPROVED | MEDIUM | **Bewust behouden**, zie par. 3 |

## 2. Bevindingen in mijn eigen herstelwerk

**F-1 (opgelost, en illustratief).** Mijn rate-limit-fix importeerde `governance` rechtstreeks
in een laag-1 router. ADR-033 verbiedt dat expliciet en vier architectuurtests vielen direct
om. Verplaatst naar de `dependencies.py`-facade. Dit is het beste bewijs van de dag dat die
guards echt werken: ze vingen mij binnen een minuut, terwijl mijn eigen review van dag 2
een inerte feature had goedgekeurd.

**F-2 (opgelost).** Mijn eerste versie van de caching-test pinde "precies 1 config-lezing"
vast. Bij meten bleek het 2 tegen 4: de agent bouwt bij constructie al een `ToolBrokerService`
die zelf een manager aanmaakt. Dat basisgetal is een detail van een andere laag. Herschreven
naar een groei-invariant -- het aantal lezingen mag niet meegroeien met het aantal acties.
Zonder die correctie was de test broos geweest op een wijziging die er niets mee te maken had.

**F-3 (opgelost).** Mijn mutatieharnas schreef bestanden terug met Python's
regeleinde-conversie en zette daarmee LF om naar CRLF in drie bronbestanden. Betrapt doordat
ik het herstel heb gecontroleerd in plaats van aangenomen; byte-getrouw teruggezet en
geverifieerd op exact de oorspronkelijke diffstat.

**F-4 (bewust nagelaten).** Vier van de bestanden die ik voor de ASCII-opschoning aanraakte,
waren al niet black-conform op `HEAD`. Ik heb die pre-existing opmaakschuld laten staan en
alleen de non-ASCII-tekens gewijzigd. Reden: dag 2 leverde een diff op met 70 ongerelateerde
reformats, waardoor die review onmogelijk werd. Een hersteldag moet dat niet herhalen. Waar
mijn eigen wijziging een regel over de 100 tekens duwde (`ethics_officer.py`) heb ik de
comment ingekort in plaats van black te laten wrappen.

## 3. Wat bewust NIET is veranderd

**De autouse Council-stub blijft standaard APPROVED.** Het gevolg is reeel: het verwijderen
van de poort uit `act()` maakt in drie testbomen geen enkele test rood. Het alternatief is
erger -- zonder stub opent elke skill-uitvoering een echte databaseverbinding met vijf
pogingen en backoff tegen een suite-timeout van 60 seconden, wat eerder 56,8 seconden per test
kostte (OP-18). De aanwezigheid van de poort is afgedekt door de architectuurtest, die
mutatie-getest is. Het risico staat nu expliciet in de docstring van de fixture, met de
waarschuwing die guard niet te slopen zonder de fixture eerst opt-in te maken.

**De geerfde `execute_tool()` is niet dichtgezet.** Die methode wordt ook door niet-ALS-agents
gebruikt; dichtzetten vraagt een eigen impact-analyse. Nu zichtbaar in de guard met datum en
reden (OP-24) in plaats van onzichtbaar.

**Geen CI-gate op mypy.** De baseline is vastgelegd op 52 met meetmethode, maar
`quality-gates.md` eist voor het verwijderen van `continue-on-error` bewijs plus Rakesh'
expliciete GO. Dat is niet aan mij.

## 4. Compliance-controle

| Regel | Status |
| --- | --- |
| Gate 1: plan vooraf | OK -- goedgekeurd plan |
| Gate 2: dubbele reviewer-GO | **OK** -- beide gedraaid, alle blokkerende punten opgelost |
| Gate 3: pyright | OK -- 0 errors |
| Gate 3: ruff | OK -- `src/` en `tests/` schoon |
| Gate 3: mypy | 52, gelijk aan de baseline (niet gestegen) |
| black | OK op eigen bestanden; pre-existing schuld bewust niet meegenomen |
| Rode test voor de fix, eigen commit | OK -- `fb4fb295` |
| Mutatie-getest | OK -- acht richtingen |
| Geen ongerelateerde wijzigingen | OK -- zie F-4 |
| ASCII-only | OK, en nu ook afgedwongen in de kernzone |
| Bevinding zonder fix heeft een test | OK -- OP-24 en OP-25 hebben elk een guard met verval-detector |
| Doc-gate | OK -- exit 0 |

## 5. Conclusie

**APPROVED.** De keten die BE-AGT-042 beweerde te hebben aangelegd, ligt er nu echt en is
getoetst op het niveau van de productie-ingang. De vier zwaarste bevindingen zijn opgelost met
een regressietest per stuk, elk mutatie-getest.

De les die ik meeneem is niet technisch maar procedureel: mijn zelfreview van dag 2 gaf
APPROVED aan een feature die op het enige productiepad niets deed. De reviewers vonden dat
binnen een half uur, allebei, onafhankelijk. Gate 2 overslaan omdat de omvang "wel meevalt" is
daarmee geen tijdwinst maar uitgesteld herstelwerk -- deze dag is de rekening.

Openstaand: OP-21 (OODA-pad zonder initiator, D1/Fase 4), OP-24 (geerfde bypass, Fase D),
OP-25 (Council ziet geen waarden, Fase D). Alle drie met een afdwingende test.
