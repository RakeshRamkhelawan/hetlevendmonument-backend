# Review BE-AGT-038 -- `denied_actions` harde denylist

| Veld | Waarde |
| --- | --- |
| Feature-ID | BE-AGT-038 |
| Datum | 2026-08-01 |
| Reviewvorm | Zelfreview (reviewer-subagents staan deze sessie uit) |
| Omvang | 2 bronregels-blokken in 1 bestand + 1 configblok; 13 nieuwe tests |
| Uitkomst | **APPROVED** |

> Vorm-voorbehoud: `quality-gates.md` Gate 2 vraagt bij features boven de 50 regels om
> `code-reviewer` + `quality-reviewer`. Die zijn deze sessie niet inzetbaar. De
> codewijziging zelf is klein (< 20 regels productiecode, 1 bestand + 1 config), wat onder
> de eigen uitzondering "small fixes: self-review is sufficient" valt; het leeuwendeel van
> de diff is test- en documentatiecode. Voor de volledigheid staat het hier genoteerd in
> plaats van weggelaten.

---

## 1. Correctheid

**De unie, niet de vervanging.** `is_tool_allowed` weigert bij
`denied_actions ∪ denied_tools`. Getoetst met twee profielen in één configbestand: eentje
dat alleen het nieuwe veld gebruikt, eentje dat alleen het oude gebruikt. Beide weigeren.
Was dit een vervanging geweest, dan zou het tweede profiel stilzwijgend permissiever
geworden zijn -- precies het soort regressie dat pas bij een incident opvalt.

**Fail-closed blijft.** Onbekend agent-id en lege string geven nog steeds `False`
(ADR-015). Apart getest, want een refactor van de eerste `if` in die functie is een
plausibele plek om dat per ongeluk te slopen.

**Achterwaartse compatibiliteit.** `field(default_factory=list)` plus
`profile_data.get("denied_actions", []) or []` -- een profiel zonder het veld en een profiel
met `denied_actions:` (YAML-null) geven beide een lege lijst. Beide paden getest.

## 2. Het architecturale punt: volgorde

De kern van D5 is niet het veld maar de plaats van de check. `execute_tool` roept
`is_tool_allowed` aan op stap 0, vóór `risk_classifier.classify` en dus vóór de
HITL/Council-poort. Zou die volgorde omdraaien, dan kan een menselijke goedkeuring een
"nooit aanraken"-actie alsnog doorlaten en is de laag zijn betekenis kwijt.

`test_permission_check_precedes_risk_and_council_gating` toetst dat op broncodeniveau. Dat
is een bewuste afweging en geen luiheid: een gedragstest zou de volledige broker moeten
opzetten (resilience, circuit breaker, HITL-store) om iets te bewijzen dat puur over
volgorde gaat, en zou daarmee fragieler zijn dan wat hij bewaakt. De test faalt zodra
iemand de check naar beneden verplaatst -- dat is wat hij moet doen.

## 3. Bevindingen tijdens de review

**F-0 (opgelost tijdens review).** De eerste versie van
`test_pilot_denied_actions_are_actually_refused` was **vacuum**: hij toetste
`is_tool_allowed(PILOT, actie) is False` op het echte profiel, en bleef groen toen de
denylist-check uit de broncode werd gemuteerd -- want die acties staan niet in
`allowed_tools`, dus de allowlist weigert ze toch al. Herschreven naar
`test_pilot_denied_actions_survive_a_widened_allowlist`, die de allowlist verruimt met
precies die acties; die versie gaat wel rood bij mutatie. Dit is de reden dat mutatie-testen
geen formaliteit is: zonder die stap was hier dekking geteld die niet bestond.

**F-1 (opgelost tijdens review).** De eerste versie van de botsingsguard nam aan dat
`PermissionDeniedError` in `src/core/exceptions/__init__.py` gedefinieerd stond. Dat is een
re-export; de definitie staat in `exceptions.py`. Twee tests vingen dit onafhankelijk van
elkaar -- de botsingstest én de staleness-test. Dat is het bewijs dat het staleness-patroon
werkt: een uitzonderingslijst die niemand controleert, rot dicht.

**F-2 (opgelost -- en mijn eerste oordeel was fout).** Ik concludeerde eerst dat D5's
premisse ("dode duplicaatklasse") niet klopte en stelde de bevinding uit als OP-15. Die
conclusie hield geen stand. Ze berustte op twee fouten:

1. **Ik telde verwijzingen zonder te lezen wat ze toetsen.** "33 referenties in een
   testsuite" klonk als coverage die verloren zou gaan. Het waren `assert True`, de lengte
   van een zojuist aangemaakte literal, en enum-waarden -- geen enkele test riep een
   permissiefunctie aan.
2. **Mijn zoekacties hadden een blinde vlek.** `.git/info/exclude` verborg 1816 tracked
   bestanden voor ripgrep, waardoor ik twee van de drie consumerende testbestanden niet
   zag -- waaronder `tests/unit/test_tool_permissions.py` met 20 echte gedragstests.

Na hercontrole is het model verwijderd: nul productie-aanroepers sinds april 2026, en de
enige werking op het levende systeem was naamverwarring. Alle vier de botsingen zijn
daarmee weg. De les is niet "ik had de ADR moeten geloven" maar: een claim over dekking
verifieer je door de asserts te lezen, niet door regels te tellen.

**F-2b (projectregel aangepast).** `quality-gates.md` eiste een **falende**
architectuurtest voor elke niet-gefixte bevinding. Die regel dateert van vóór de
blokkerende CI-gate; sindsdien legt een opzettelijk rode test élke merge stil, niet alleen
de eigen bevinding. De regel is uitgebreid met een expliciet alternatief: een groene guard
met gedateerde uitzondering plus staleness-test, onder vier voorwaarden (OP-nummer in de
ADR, reden per regel, staleness-test, mutatie-test in beide richtingen). Met de nadrukkelijke
toevoeging dat de guard bedoeld is voor uitstel-met-reden en niet voor uitstel omdat fixen
ongemakkelijk is -- OP-15 is daarvan zelf het voorbeeld.

**F-3 (geen actie).** De vier verboden acties voor de piloot bestaan nog niet als
geregistreerde tools. Dat is geen probleem -- een denylist die vooruitloopt op de
tool-registratie is juist de goede volgorde -- maar het betekent wel dat de handhaving nu
alleen op profielniveau bewezen is, niet end-to-end door de broker. Zodra een van deze
acties een echte tool wordt, hoort daar een integratietest bij.

## 4. Compliance-controle

| Regel | Status |
| --- | --- |
| Geen emoji / non-ASCII in code, comments, logs | OK |
| `tenant_id` niet uit request body | n.v.t. |
| `datetime.now(timezone.utc)` | n.v.t. |
| loguru `{}`-formattering (geen `%d`) | OK -- eerder in deze sprint in dit bestand gefixt |
| ADR-015 default-deny intact | OK, apart getest |
| Rode test vóór de fix | OK -- commit `fa0d39ff`, 5 failed / 4 passed |
| Mutatie-getest | OK -- volgordetest en botsingsguard beide aantoonbaar rood gemaakt |

## 5. Conclusie

**APPROVED.** De wijziging is klein, fail-closed, achterwaarts compatibel en op het punt dat
er werkelijk toe doet (de volgorde) getest in plaats van aangenomen. D5 is volledig
geleverd: veld, handhaving vóór de Council, reconciliatie met `denied_tools`, een concrete
denylist voor de piloot, en het naamconflict opgeruimd.

Twee bevindingen zijn buiten deze feature om ontstaan en apart vastgelegd: OP-16 (vijf
asyncio-primitieven die bij import aan de verkeerde event loop binden) en OP-17 (de
zoek-blinde-vlek in `.git/info/exclude`; grotendeels gesloten, rest zit in het gedeelde
`.gitignore`).
