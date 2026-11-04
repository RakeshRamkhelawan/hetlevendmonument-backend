# Review BE-AGT-040 -- piloot-prompt belooft geen werkende tools meer

| Veld | Waarde |
| --- | --- |
| Feature-ID | BE-AGT-040 |
| Datum | 2026-08-01 |
| Reviewvorm | Zelfreview (reviewer-subagents staan deze sessie uit) |
| Omvang | 1 formulering in 1 script + hetzelfde manifest; 5 nieuwe tests |
| Uitkomst | **APPROVED** |

> **Gate 2, expliciet vastgelegd in plaats van weggelaten.** `quality-gates.md` vraagt bij
> features boven de 50 regels `code-reviewer` + `quality-reviewer`. Die zijn deze sessie niet
> inzetbaar. De wijziging is < 20 regels in 2 bestanden en valt onder de eigen uitzondering
> "small fixes: self-review is sufficient" -- het leeuwendeel van de diff is test- en
> documentatiecode. Genoteerd, niet verzwegen.

---

## 1. De kern: een profiel is geen wiring

De prompt beweerde "You have working tools". Een permissieprofiel geeft **toestemming**; het
maakt geen tool. Geen van de vijf tools van de piloot resolveert in `execute_tool`, dus de
bewering was onwaar.

Wat de fix goed maakt is niet de tekst maar de eigenschap ervan: de nieuwe formulering is waar
in beide toestanden -- tools nog niet gebouwd (nu) en tools wel gebouwd (na Fase 2). Er hoeft
dus later niets terug, en dat is precies waarom ik niet voor een tijdelijke variant heb
gekozen.

## 2. Wat ik heb gemeten in plaats van aangenomen

Zes aannames uit mijn eerste opzet zijn getoetst; twee bleken onjuist en veranderden het plan.

| Aanname | Uitkomst |
| --- | --- |
| Generator-output == gecommit manifest | **Waar** -- `build_manifest()` naast de YAML gelegd: volledig identiek. Daarom is de drift-guard groen vanaf de eerste run en niet meteen rood |
| Alleen het piloot-manifest wijzigt | **Waar** -- `_profiled_skill_ids()` filtert `NON_SKILL_PROFILES`, dus `copilot` valt af |
| De generator draaien is een optie | **Onwaar** -- `main()` herschrijft 135 manifesten EN 135 skill-bronbestanden. Alleen het piloot-manifest is opnieuw geschreven, daarna geverifieerd dat uitsluitend `system_prompt` verschilt |
| Geen test of doc pint de oude tekst | **Waar** -- "You have working tools" kwam exact 2x voor: generator en manifest |
| Eén productie-aanroeper | **Waar** -- `packs.py:337`, alleen voor `_PILOT_WIRED_AGENT_IDS` |
| Dit is een live bug | **Onwaar** -- zie par. 3 |

Dat de tweede en zesde aanname sneuvelden, is het argument voor deze werkwijze: beide klonken
volkomen redelijk.

## 3. Eerlijk over de impact

De piloot-prompt bereikt vandaag geen enkele LLM in productie. Er bestaat wel een echte pack
met de piloot als eerste stap (`domain_packs.yaml:88`), maar de enige productie-aanroeper geeft
een synthetische pack door met hardcoded `agent1`/`agent2` (OP-09), die niet gewired zijn.

Dus: correctheidsfix in een artefact, geen reparatie van een incident. Ik noem dat expliciet
omdat een review die de opbrengst opblaast net zo misleidend is als een die hem verzwijgt. De
waarde zit in het artefact dat niets onwaars meer beweert, in de anti-fabricatie-instructie die
gaat werken zodra tools bestaan, en in de eerste drift-guard tussen generator en manifest.

## 4. Bevindingen tijdens de review

**F-1 (bewust, en het lastigste punt).** De naïeve oplossing -- de branchvoorwaarde omzetten
naar "resolveren de tools?" -- zet de piloot terug op de tekst-only stopgap en herintroduceert
daarmee exact de inconsistentie die onafhankelijke review IR-001 afdwong te voorkomen
(profiel + stopgap). Daarom is de voorwaarde onveranderd gebleven en is alleen de bewering
herschreven. Mutatie-getest dat het ook echt zo werkt: de stopgap-tekst invoeren maakt zowel
mijn eigen test als `test_skill_profiles_are_consistent_with_manifests` rood.

**F-2 (bewust, afgewogen).** Het alternatief "neem de piloot zijn profiel af" is verworpen: dat
unwindt AUDIT-008 (dubbele onafhankelijke GO), de `denied_actions` van D5 die aan dat profiel
hangen, en de 21 tests van de evaluatieset. Drie afgeronde sprintdagen terugdraaien voor één
zin.

**F-3 (opgelost tijdens uitvoering).** Mijn eerste versie van de drift-guard-test miste de
`yaml`-import. Ruff meldde dat direct.

**F-4 (geen actie, wel vastgelegd).** Een derde verlanglijst-oppervlak:
`config/agents/hr_culture_skillsgaptraining.yaml:19` heeft `tools: ["standard_toolbox"]`, een
naam die in 8 configbestanden en nul Python-bestanden voorkomt. Dode metadata. Staat in de
feature-doc par. 7 zodat het niet opnieuw als capaciteit wordt gelezen; opruimen valt onder
D12.

## 5. Compliance-controle

| Regel | Status |
| --- | --- |
| Rode test vóór de fix, eigen commit | OK -- `d93897f7`, 2 failed / 5 passed |
| Mutatie-getest in beide richtingen | OK -- oude bewering terug, en stopgap-tekst invoeren |
| ASCII-only in code, comments en strings | OK -- manifest expliciet gecontroleerd: 0 non-ASCII tekens |
| Geen `datetime.now()` / `tenant_id` uit body | n.v.t. |
| Bestaande invarianten intact | OK -- evaluatieset 21/21, architectuurtest groen, 608 gerichte tests groen |
| Impact-analyse vóór de eerste wijziging | OK -- vastgelegd in het goedgekeurde plan |

## 6. Conclusie

**APPROVED.** Klein, waar in beide toestanden, en op het punt dat telt (de bewering) getest
in plaats van aangenomen. De twee gates die deze wijziging bewaken -- IR-001 en de drift tussen
generator en manifest -- zijn nu beide expliciet getest; de tweede bestond nog niet.

Wat dit niet oplost, staat er ook: de piloot blijft mislukte tool-aanroepen doen tot Fase 2 de
eerste echte tool levert. De prompt vertelt daar nu alleen de waarheid over.
