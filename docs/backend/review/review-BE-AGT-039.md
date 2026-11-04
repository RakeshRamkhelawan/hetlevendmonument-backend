# Review BE-AGT-039 -- tool-contracten gap-analyse + F3-fix

| Veld | Waarde |
| --- | --- |
| Feature-ID | BE-AGT-039 |
| Datum | 2026-08-01 |
| Reviewvorm | Zelfreview (reviewer-subagents staan deze sessie uit) |
| Omvang | 1 regel productiecode + 1 configveld; 8 nieuwe tests; 1 analysedocument |
| Uitkomst | **APPROVED** |

---

## 1. De productiewijziging is één regel -- en juist daarom het nakijken waard

`success = len(results) > 0 or len(errors) == 0` wordt `success = not errors`.

**Waarom de oude vorm fout was, niet alleen lelijk.** De `or`-tak maakt succes waar zodra er
íets gelukt is. Bij 1 geslaagde en 1 mislukte tool-call is dat True. Dat zou een
rapportagekwestie zijn als niemand erop handelde, maar de OODA-loop rekent er direct prana
op af (`specialist_base.py:324-327`). Een tenant betaalde dus voor werk dat deels niet is
uitgevoerd.

**Verificatie dat er geen tweede vangnet was.** Repo-brede zoekactie op
`result_data["errors"]`: nul consumenten in `src/`. Deze zoekactie is betrouwbaar sinds de
`.git/info/exclude`-opschoning van vandaag (OP-17) -- vóór die opschoning had ik dit niet met
zekerheid kunnen stellen, en dat is precies waarom die opschoning eerst moest.

**Randgevallen bewust vastgelegd, niet aangenomen.** Drie van de vier nieuwe tests dekken
gedrag dat NIET mocht veranderen: geen tool-calls (tekst-only -- de normale weg voor een
adviserende skill en het merendeel van de evaluatieset van dag 1), alles geslaagd, en alles
mislukt (was al correct). De rode test was er één; de andere drie waren groen vóór de fix en
zijn dat erna nog. Dat is het bewijs dat de fix chirurgisch is.

**Waarom het tekst-only-pad niet geraakt wordt:** `act()` retourneert eerder al met
`success=True` wanneer er geen `TOOL_CALL` in het antwoord staat; de gewijzigde regel wordt
dan niet bereikt. Getest, niet beredeneerd.

## 2. De naamruimte-vondst is de eigenlijke opbrengst

F1 (nul van 27 tools uitvoerbaar) leest als de grote bevinding, maar is bekend terrein: D10
schrijft de bouwvolgorde al voor en het systeem faalt eerlijk.

F2 is nieuwer en gevaarlijker: één configbestand met twee betekenissen en geen enkel veld
dat ze onderscheidt. Het bewijs dat dit misleidt ben ik zelf -- mijn eerste conclusie was dat
13 copilot-tools stuk waren in productie. Ze zijn dat niet; het zijn Council-actietypes die
door andere handlers worden uitgevoerd. Dat bleek pas bij het lezen van
`_ToolBrokerAdapter`, dat uitsluitend `is_allowed` aanroept en nooit `execute_tool`.

De guard is daarom niet "nog een test" maar de fix voor een leesfout die een reviewer
gegarandeerd nog eens maakt.

## 3. Bevindingen tijdens de review

**F-1 (opgelost).** De eerste versie van de naamruimte-guard gaf twee pyright-fouten door
`dict[str, object]`-typing op `allowed_tools`. Opgelost met een `_tools_of()`-helper die
expliciet op `isinstance(raw, list)` toetst -- dat vangt tegelijk het geval van een ontbrekend
of `null`-veld af. Baseline blijft 0 pyright-fouten.

**F-2 (bewust).** `KNOWN_UNRESOLVED_BROKER_TOOLS` bevat vijf uitzonderingen. Dat is de
groene-guard-met-gedateerde-uitzondering die gisteren in `quality-gates.md` is vastgelegd,
en hij haalt alle vier de voorwaarden: OP-nummer/fase benoemd (Fase 2), reden per regel,
staleness-test aanwezig, en mutatie-getest in beide richtingen (naamruimte weghalen -> 2
rood; verzonnen tool toevoegen -> 1 rood; hersteld -> 4 groen).

Er zit bovendien een tweede verval-detector in die ik elders nog niet gebruikte:
`test_known_unresolved_tools_are_actually_declared` faalt zodra een uitzondering geldt voor
een tool die geen enkel profiel meer declareert. Zonder die test blijft dode ballast staan
die er legitiem uitziet.

**F-3 (geen actie, expliciet vastgelegd).** Het contract voor `query_hr_database` noteert dat
de risicoclassificatie terugvalt op `HIGH` voor onbekende tools (`risk_classifier.py:35`,
zero-trust). Dat betekent dat de tool bij implementatie expliciet geregistreerd moet worden,
anders belandt een leesactie in de HITL-poort. Dat is veilig-maar-onbruikbaar, en het soort
detail dat je bij het bouwen kwijt bent als het niet in het contract staat.

## 3b. Twee dingen die de volledige gate pas blootlegde

**Een bestaande test legde het foute gedrag vast -- voor de vierde keer vandaag.**
`tests/unit/agents/test_specialist_act.py::test_act_partial_failure` asserteerde
`result.success is True` bij 1 fout en 1 succes. De docstring zei "one tool failure does not
stop remaining tools" -- een geldige invariant, maar bewezen met de verkeerde assertie: dat
de reeks doorloopt (results==1) is iets anders dan dat de stap gelukt is. Gecorrigeerd met
behoud van de oorspronkelijke bedoeling, plus een expliciete `await_count == 2` zodat de
invariant nu getoetst wordt door wat hij beweert. Dit is hetzelfde patroon als bij de
WS-tokentest, de consent-defaults en de residency-aanname eerder in deze sprintreeks.

**Zes purge-tests bleken ordeafhankelijk -- en dat was geen flakiness.**
`init_tenant_auto_filtering()` hangt een `do_orm_execute`-listener aan de `Session`-klasse
zelf (`propagate=True`, geen verwijdermogelijkheid). Zodra `test_tenant_query_filter.py`
eerder in dezelfde xdist-worker draait, krijgt ook de eigen in-memory-sessie van
`test_memory_item_purge.py` een automatisch tenantfilter -- en dat filter is fail-secure:
geen tenant in de ContextVar betekent nul rijen.

Volledig deterministisch, reproduceerbaar met
`pytest tests/unit/test_tenant_query_filter.py tests/unit/test_memory_item_purge.py`.
Ze slaagden in vijf eerdere runs die dag alleen omdat de sharding ze uit elkaar hield.

Drie dingen expliciet nagetrokken voor ik iets wijzigde:
1. **Niet veroorzaakt door deze feature.** Met mijn nieuwe testbestand uitgesloten faalden ze
   nog steeds, en de rest van de falende set verschoof per run.
2. **Geen productiebug.** `memory_purge_service.py:106,151` gebruikt al expliciet
   `TenantFilterBypass`, met de reden erbij. De tests riepen de laag eronder direct aan en
   misten die wrapper.
3. **De fix maakt de isolatietest niet vacuum.** Na het toevoegen van de bypass is
   mutatie-getest: het weghalen van de expliciete `tenant_id`-filter uit de purge maakt
   `test_purge_is_tenant_scoped` alsnog rood. De isolatie wordt dus bewezen via de expliciete
   parameter -- precies waar productie op leunt.

De onverwijderbare listener zelf blijft staan als OP-20 (Fase D, P1): het volgende
testbestand dat de ORM aanraakt kan hetzelfde overkomen.

## 4. Compliance-controle

| Regel | Status |
| --- | --- |
| Geen emoji / non-ASCII | OK |
| `tenant_id` niet uit request/payload | OK -- expliciet in het contract opgenomen dat `execute_tool` de context laat winnen |
| Rode test vóór de fix | OK -- commit `cdc67072`, 1 failed / 3 passed |
| Mutatie-getest | OK -- F3-fix en naamruimte-guard, beide richtingen |
| Bevinding zonder fix heeft afdwingende test | OK -- F1/F4 via `KNOWN_UNRESOLVED_BROKER_TOOLS` + 2 verval-detectoren |
| Evaluatieset dag 1 nog groen | OK -- 21/21 |

## 5. Conclusie

**APPROVED.** D10 stap 3 is geleverd als wat het is: een analyse plus een contract, niet een
implementatie. De opbrengst zit niet in het contract zelf maar in twee dingen die onderweg
zichtbaar werden -- een afrekening op een verkeerd succes-signaal, en een configbestand dat
twee dingen betekende zonder dat te zeggen.

Fase 1 is hiermee inhoudelijk klaar. Wat rest voor Fase 2: de eerste echte tool bouwen, de
Council-poort verplicht maken, en loop-engineering.
