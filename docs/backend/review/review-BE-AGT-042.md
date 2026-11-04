# Review BE-AGT-042 -- Council-poort per actie

| Veld | Waarde |
| --- | --- |
| Feature-ID | BE-AGT-042 |
| Datum | 2026-08-02 |
| Reviewvorm | Zelfreview (reviewer-subagents staan deze sessie uit) |
| Omvang | ~90 regels productiecode in 5 bestanden; 14 tests |
| Uitkomst | **APPROVED**, met een openstaand punt |

> **Gate 2 niet gehaald, opnieuw.** Deze wijziging is ruim boven de "small fixes"-drempel.
> `code-reviewer` en `quality-reviewer` zijn deze sessie niet inzetbaar, dus de dubbele GO
> ontbreekt -- net als bij BE-AGT-041. Twee dagen op rij is geen incident meer maar een
> patroon; bij de eerstvolgende sessie met reviewers horen beide diffs er alsnog langs.

---

## 1. Wat dit oplost

De derde "gebouwd maar niet aangesloten" van deze sprintreeks. De Council-ingang was
compleet en getest en werd door niets aangeroepen. Nu loopt elke tool-actie van een skill er
langs, met de D5-denylist ervoor.

Het patroon is inmiddels zo consistent dat het geen toeval meer is: tools, budget, Council.
Drie keer een component die aan zijn specificatie voldeed en niet verbonden was, en drie keer
geen symptoom dat het verried. Daarom staat er bij elke fix een guard die de aansluiting
afdwingt in plaats van alleen de aansluiting zelf.

## 2. Wat ik heb gemeten in plaats van aangenomen

Tien twijfels getoetst; **drie** veranderden het ontwerp.

| Aanname | Uitkomst |
| --- | --- |
| De poort kan in `execute_tool` | **Onwaar** -- 12 productie-aanroepers, waaronder HTTP-paden die al beraadslagen. Dubbele Council en systeembrede impact |
| De initiator kan als parameter naar `act()` | **Onwaar** -- 135 skills overschrijven die signatuur identiek; wijzigen vraagt een regeneratie van 270 bestanden. Nu instance-state |
| `is_tool_allowed()` is de juiste precheck | **Onwaar** -- die bevat ook de default-deny, waardoor elke profielloze agent al bij de precheck strandt. Ontdekt doordat 3 bestaande tests omvielen. Vervangen door een smalle `is_denied()` |
| De keten is 5 methoden diep | Nee, **10 signaturen en 8 aanroepen** over twee paden. Mechanisch, met default `None` |
| De Council is goedkoop genoeg per actie | Rekentijd ja (regelgebaseerde officers), maar elke beraadslaging opent een **eigen DB-sessie**. Begrensd door `max_steps=8` van gisteren |
| Er is een `user_id` in het skill-pad | Niet in de uitvoering, wel bij de ingang -- als `_current_user`, bewust ongebruikt |

## 3. De keuze waar ik het langst over heb gedaan

De gate vereist een `user_id`. De makkelijke weg was `user_id=1`, zoals de bestaande tests.
Dat zou een autonome agent-actie toeschrijven aan een echt persoon -- en dit is precies een
ADR over dingen die iets anders beweren dan ze zijn.

Drie bronnen onderzocht en twee verworpen: `Department.head_user_id` is nullable en het
koppelen ervan is expliciet D1/Fase 4-werk; een systeem-user bestaat niet en zou ik moeten
verzinnen. Wat overbleef was waar en al aanwezig: de mens die op de knop drukt. Die stond in
de endpoint als `_current_user` -- met underscore, dus alleen om authenticatie af te dwingen,
en daarna weggegooid.

Fail-closed bij afwezigheid is bewust en niet defensief: liever niets doen dan iemand
verantwoordelijk maken voor een actie die hij niet startte.

## 4. Bevindingen tijdens de review

**F-1 (opgelost).** De rode tests zetten de initiator als instance-state, maar
`execute_with_manifest_prompt` overschrijft dat veld met zijn parameter (default `None`).
De tests gaven de waarde daarna via de aanroep mee -- het productiepad.

**F-2 (opgelost, en het was mijn grootste slordigheid).** Ik gaf black hele mappen mee in
plaats van mijn eigen bestanden, waardoor **70 bestanden** werden geherformatteerd die ik
nooit had aangeraakt. 84 gewijzigde bestanden terwijl er 15 van mij waren. Teruggedraaid tot
uitsluitend de eigen wijzigingen, daarna opnieuw geverifieerd (1519 gerichte tests groen).
Een commit met 70 ongerelateerde reformats maakt een review onmogelijk.

**F-3 (opgelost).** De bulk-invoeging van de initiator zette een toelichting ook in
`TestParseToolCalls`, waar `act()` niet eens wordt aangeroepen. Ruis verwijderd.

**F-4 (geen actie, vastgelegd).** Acht beraadslagingen betekenen acht DB-sessies. Vandaag
begrensd door `max_steps`; samenvoegen kan later, maar de gate accepteert geen sessie van
buiten. Staat in de feature-doc zodat het geen verrassing wordt.

## 5. Compliance-controle

| Regel | Status |
| --- | --- |
| Rode test vóór de fix, eigen commit | OK -- `b742bb8b`, 10 tests rood |
| Mutatie-getest | OK -- zes richtingen, elk exact de bijbehorende test rood |
| D5-volgorde bewaard | OK -- broncodetest plus gedragstest, beide mutatie-getest |
| `tenant_id`/identiteit niet uit een payload | OK -- expliciete parameter, geen ContextVar, geen params-dict |
| ASCII-only | OK |
| Impact-analyse vóór de eerste wijziging | OK -- in het goedgekeurde plan, inclusief de fail-closed-blast-radius |
| Geen ongerelateerde wijzigingen in de commit | OK **na correctie** -- zie F-2 |

## 6. Conclusie

**APPROVED** op de inhoud. De poort is echt aangesloten, de volgorde die D5 eist is bewaard
en dubbel getest, en de accountability berust op een verifieerbare bron in plaats van op een
verzonnen id.

Twee dingen blijven staan: de dubbele reviewer-GO (par. 0) en het feit dat "werkt in
productie" pas aantoonbaar is na OP-09 -- de HTTP-ingang bouwt nog steeds een synthetische
pack met hardcoded agents, dus de piloot wordt daar niet bereikt. Dat stond al in de
Fase 2-DoD en verandert hier niet.
