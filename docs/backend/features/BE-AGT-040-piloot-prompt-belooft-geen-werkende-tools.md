# BE-AGT-040 -- De piloot-prompt belooft geen werkende tools meer

| Veld | Waarde |
| --- | --- |
| Feature-ID | BE-AGT-040 |
| Datum | 2026-08-01 |
| ADR | ADR-036 D10 (piloot), ADR-015 (allowlist), AI Act art. 13 (juiste beschrijving van capaciteiten) |
| Voortkomend uit | BE-AGT-039 F1 (gap-analyse dag 3) |
| Omvang | 1 formulering in de generator + hetzelfde manifest; 5 nieuwe tests (7 in het bestand) |

---

## 1. Probleem

`scripts/generate_skill_manifests.py` kiest de tool-instructie van een skill op basis van
**"heeft deze skill een permissieprofiel?"**:

- geen profiel -> `"You do not have working tools available yet -- ... without attempting a
  TOOL_CALL."` Dat geldt voor 134 skills en is waar.
- wel profiel -> `"You have working tools (see allowed_tools in your manifest). ..."`

De piloot `skillsgaptraining` kreeg in Fase A dag 4 een profiel (AUDIT-008) en dus de tweede
tekst. Die is onwaar: geen van zijn vijf tools resolveert in
`ToolBrokerService.execute_tool`. De aanname eronder is dat een profiel wiring impliceert --
een profiel geeft alleen **toestemming**. Toestemming voor een deur die niet bestaat.

## 2. Eerlijke waardering van de impact

Dit repareert geen lopend incident. De piloot-prompt bereikt vandaag geen enkele LLM in
productie: `config/domain_packs.yaml:88` definieert wel een echte pack
(`hr.reskilling_engine`) met de piloot als eerste stap, maar de enige productie-aanroeper van
`execute_pack` (`api/v1/agentic/agentic_domain_router.py:81`) geeft een **synthetische** pack
door met hardcoded `{"agents": ["agent1", "agent2"]}`. Die zijn niet gewired, dus
`_execute_step` retourneert "unwired-agent" en de piloot draait niet. Dat is OP-09.

De opbrengst is daarmee drieledig, niet groter:

1. het artefact beweert niets onwaars meer;
2. de toegevoegde anti-fabricatie-instructie werkt zodra tools bestaan;
3. het drift-gat tussen generator en manifest krijgt zijn eerste guard.

Het risico is om dezelfde reden laag: geen live pad verandert.

## 3. Wat de oplossing begrensde

Drie bestaande invarianten sloten de simpele weg af:

| Invariant | Gevolg |
| --- | --- |
| `test_als_skills_tool_permissions.py:103` -- profiel => geen stopgap-tekst (uit review IR-001) | De piloot terugzetten op de stopgap herintroduceert exact de inconsistentie die IR-001 afdwong |
| `test_skillsgaptraining_evaluation_set.py:308` -- prompt bevat `TOOL_CALL:` en `Never invent data` | Het contract weghalen sloopt de 21 tests van dag 1 |
| `test_generate_skill_manifests_stopgap.py:35` | Pint de generatorlogica; wijzigt mee |

**Afgewogen en verworpen:** de piloot zijn profiel afnemen. Dat unwindt AUDIT-008 (Fase A dag
4, dubbele onafhankelijke GO), de `denied_actions` van D5 (dag 2 hangt daaraan) en de
evaluatieset van dag 1. Drie sprintdagen terugdraaien voor één zin is de verkeerde ruil.

## 4. Oplossing

Eén formulering die waar is vóór én na Fase 2, dus zonder revisie later:

```text
You may use only the tools listed under allowed_tools in your manifest. When a tool is
needed, emit exactly one directive per line in the format TOOL_CALL: tool_name
{"param": "value"} -- anything outside that list is denied by the ToolBroker (ADR-015).
Some listed tools are not connected yet; the ToolBroker refuses those with an error. That
is expected -- report the failure plainly and never invent a tool result. Otherwise provide
your analysis and recommendation as a concise final answer, in text.
```

Weg: de bewering. Behouden: het `TOOL_CALL`-formaat, de allowlist-beperking, ADR-015 en
`Never invent data`. Nieuw: wat er gebeurt bij een niet-aangesloten tool, plus het verbod om
een resultaat te verzinnen -- dat laatste dekt het echte risico van een geweigerde aanroep.

**De branchvoorwaarde is niet gewijzigd.** `_profiled_skill_ids()` blijft de vraag "mag deze
skill tool-calls doen"; die is juist. De fout zat uitsluitend in wat de tekst daarna beweerde.
Omzetten naar een resolvability-check zou de piloot op de stopgap zetten en IR-001 breken.

## 5. Tests

`tests/unit/scripts/test_generate_skill_manifests_stopgap.py` -- 5 nieuwe tests (7 in het
bestand), waarvan 2 rood gecommit in `d93897f7`. NB: die commit-boodschap zegt "zes tests";
dat is een telfout, het zijn er vijf. De suite gaf het verschil weg -- 14.955 + 5 = 14.960.

| Test | Legt vast |
| --- | --- |
| `test_profiled_skill_does_not_claim_working_tools` | de bewering is weg (**was rood**) |
| `test_profiled_skill_warns_that_listed_tools_may_be_unconnected` | de prompt benoemt de weigering en verbiedt fabricatie (**was rood**) |
| `test_profiled_skill_keeps_tool_call_contract` | `TOOL_CALL: tool_name`, `allowed_tools`, `ADR-015`, `Never invent data` blijven |
| `test_profiled_skill_has_no_stopgap_marker` | IR-001-invariant, expliciet in dit bestand |
| `test_generated_pilot_prompt_matches_committed_manifest` | **drift-guard**, bestond nog niet |

**Mutatie-getest, beide richtingen:**

- oude bewering terugzetten -> `does_not_claim_working_tools` rood, plus de drift-guard (want
  het manifest liep dan achter -- de guard doet precies zijn werk);
- de stopgap-tekst invoeren -> `has_no_stopgap_marker` rood **en**
  `test_skill_profiles_are_consistent_with_manifests` rood. IR-001 is dus dubbel bewaakt.

## 6. Waarschuwing bij onderhoud

`main()` van de generator herschrijft **alle 135 manifesten EN alle 135 skill-bronbestanden**
(`path.write_text(new_source)`). Draai hem niet om één manifest bij te werken. Voor deze
wijziging is uitsluitend het piloot-manifest opnieuw geschreven via `build_manifest()`, en
daarna geverifieerd dat alleen het veld `system_prompt` verschilt.

De drift-guard is er precies voor dit risico: hij faalt zodra generator en manifest uiteen
gaan lopen, wat het gat was waardoor IR-001 kon ontstaan.

## 7. Observatie buiten scope: een derde verlanglijst-oppervlak

`config/agents/hr_culture_skillsgaptraining.yaml:19` bevat `tools: ["standard_toolbox"]`. Die
naam komt in 8 configbestanden voor en in **nul** Python-bestanden -- dode metadata, en een
derde naamgeving naast `allowed_tools` (manifest) en de profielen in
`config/tool_permissions.yml`. Hier vermeld zodat het niet opnieuw als bestaande capaciteit
wordt gelezen. Opruimen valt onder D12.

## 8. Trainingssamenvatting

**Flow 1 -- de piloot roept een tool aan die nog niet bestaat**

- Actor: ALS-skill `skillsgaptraining`
- Voorwaarde: de tool staat in `allowed_tools` maar resolveert niet in `execute_tool`
- Actie: het model emit `TOOL_CALL: query_hr_database {...}`
- Systeemreactie: de ToolBroker weigert met "Unknown tool category"; `act()` zet de fout in
  `errors` en `success` is False (BE-AGT-039 F3)
- Succes: n.v.t.
- Fout: de skill meldt de weigering; de prompt verbiedt expliciet een verzonnen resultaat
- Uitzonderingen: geen -- dit is het verwachte gedrag tot Fase 2 de tool bouwt

**Flow 2 -- iemand werkt het manifest bij zonder de generator**

- Actor: ontwikkelaar
- Voorwaarde: de system-prompt in `skillsgaptraining.yml` wordt handmatig aangepast
- Actie: commit zonder de generator bij te werken
- Systeemreactie: `test_generated_pilot_prompt_matches_committed_manifest` faalt
- Succes: de afwijking wordt bij het committen gevonden, niet bij een latere regeneratie
- Fout: n.v.t.
- Uitzonderingen: geen; beide bronnen moeten dezelfde tekst bevatten

**Flow 3 -- een skill zonder profiel**

- Actor: elk van de 134 overige skills
- Voorwaarde: geen profiel in `config/tool_permissions.yml`
- Actie: de generator bouwt het manifest
- Systeemreactie: de tekst-only stopgap blijft ongewijzigd
- Succes: de skill probeert geen tool-call en blijft eerlijk tekst-only
- Fout: n.v.t.
- Uitzonderingen: zodra zo'n skill een profiel krijgt, komt hij in de geprofileerde tak en
  krijgt hij dezelfde nieuwe formulering

## 9. Gewijzigde bestanden

| Bestand | Wijziging |
| --- | --- |
| `scripts/generate_skill_manifests.py` | nieuwe formulering in de geprofileerde tak, met de reden erbij |
| `src/core/als/agents/skills/manifests/skillsgaptraining.yml` | `system_prompt` bijgewerkt via `build_manifest()`, dus letterlijk identiek |
| `tests/unit/scripts/test_generate_skill_manifests_stopgap.py` | 5 nieuwe tests, waarvan 2 rood gecommit vóór de fix |
