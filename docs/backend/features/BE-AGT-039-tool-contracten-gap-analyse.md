# BE-AGT-039 -- Tool-contracten: gap-analyse + contract `query_hr_database`

| Veld | Waarde |
| --- | --- |
| Feature-ID | BE-AGT-039 |
| Datum | 2026-08-01 |
| ADR | ADR-036 D10 stap 3, D5, ADR-015 |
| Sprint | ADR-036 Fase B / Fase 1 / dag 3 |
| Scope | Fase 1 is **gap-analyse only** voor tool-contracten; implementatie is Fase 2 |

---

## 1. Probleem

D10 stap 3 vraagt "tool-contracten voor de (nog te bepalen, interne) tools van de
gap-analyse". De ADR noteert er zelf een blokkade bij: contracten zijn zinloos zolang
tool-executie non-functioneel is. Die blokkade is formeel opgeheven (permissieprofiel in
Fase A dag 4, `denied_actions` gisteren), dus de vraag van vandaag is: **welk contract
hebben die tools, en bestaan ze?**

## 2. Gap-analyse

Uitvoerbaarheid is getoetst met exact de check uit `ToolBrokerService.execute_tool` stap 0a
(`service.py:166-175`): een toolnaam is uitvoerbaar met een voorvoegsel (`local__`,
`test__`, `serena__`, `sequentialthinking__`) of als lid van
`BusinessToolRegistry.known_tool_names()` -- een set van vier (`create_task`, `list_tasks`,
`update_task`, `delete_task`).

### F1 -- Geen enkele gedeclareerde skill-tool is uitvoerbaar

| Bron | Gedeclareerd | Uitvoerbaar |
| --- | --- | --- |
| 135 skill-manifesten (27 unieke tools) | 27 | **0** |
| piloot `skillsgaptraining` | 5 | **0** |

Meest gedeclareerd en niet-bestaand: `generate_text` (74 skills), `query_database` (68),
`send_notification` (67), `search_documents` (63), `search_web` (62).

Dit is geen stille storing: `execute_tool` gooit `ToolExecutionException("Unknown tool
category")` en `BaseSpecialistAgent.act()` zet die in `errors`. Het faalt eerlijk. Maar het
tool-contract van de piloot is vandaag leeg -- er is niets om een contract over te sluiten.

### F2 -- Twee onverenigbare naamruimtes in één bestand

`config/tool_permissions.yml` bevatte twee soorten namen die er identiek uitzien:

| Profiel | Wat de namen zijn | Gecontroleerd door | Uitgevoerd door |
| --- | --- | --- | --- |
| `copilot` (17) | Council `action_type` | `_ToolBrokerAdapter.is_allowed` | copilot-actiehandlers |
| `skillsgaptraining` (5) | broker-toolnamen | dezelfde `is_tool_allowed` | `execute_tool` |

Gevolg: 13 van de 17 copilot-entries "bestaan niet" als broker-tool, maar dat is **correct**
-- het zijn geen tools. Wie dat niet weet leest een gat dat er niet is; wie een echte
skill-tool toevoegt krijgt geen enkel signaal dat er niets achter zit.

Dit is niet theoretisch: de eerste lezing van deze analyse concludeerde dat 13
copilot-tools stuk waren in productie. Dat bleek pas onjuist bij het lezen van de adapter.

**Opgelost:** elk profiel declareert nu `namespace: council_action | broker_tool`, met de
uitleg bij het veld in de YAML. Bewaakt door
`tests/architecture/test_tool_profile_namespaces.py` (4 tests), inclusief een gedateerde
uitzonderingslijst voor de vijf nog-niet-bestaande piloot-tools plus twee
verval-detectoren (een tool die wel gaat bestaan, en een uitzondering die niemand meer
declareert).

### F3 -- Gedeeltelijk mislukte tool-reeks rapporteerde succes -- GEFIXT

`specialist_base.py:268` bepaalde succes met:

```python
success = len(results) > 0 or len(errors) == 0
```

Bij twee tool-calls waarvan één slaagt en één faalt: `results=1`, `errors=1`, dus
`success=True`.

**Waarom dit meer is dan een verkeerde melding.** Direct na `act()` staat in de OODA-loop
(`specialist_base.py:324-327`):

```python
if result.success:
    await guard.charge_prana(self.tenant_id, 100)
```

De tenant werd dus afgerekend voor werk dat deels niet is uitgevoerd. Een repo-brede
zoekactie bevestigt dat niets in `src/` `result_data["errors"]` inspecteert -- er was geen
tweede vangnet.

Gewijzigd naar `success = not errors`. Het tekst-only-pad (geen tool-calls) retourneert
eerder al met `success=True` en komt deze regel niet langs; die tak is dus ongemoeid.

### F4 -- `denied_actions` benoemt niet-bestaande acties

De vier verboden personeelsacties van gisteren bestaan niet als tool. Bewust: een denylist
die vooruitloopt op tool-registratie is de goede volgorde (zie `review-BE-AGT-038.md`, F-3).
Hier vermeld zodat het samen met F1 in één beeld staat.

## 3. Tool-contract: `query_hr_database`

Het artefact dat D10 stap 3 vraagt. **Specificatie, geen implementatie** -- bouw in Fase 2.

| Aspect | Contract |
| --- | --- |
| Naam | `query_hr_database` |
| Doel | Leest medewerker-, rol- en trainingsgegevens voor gap-analyse. Uitsluitend lezen |
| Naamruimte | `broker_tool` -- loopt via `execute_tool` |
| Risicoklasse | `LOW` (`ToolRiskLevel`) -- leest alleen, muteert niets. Let op: de classifier valt terug op `HIGH` voor onbekende tools (zero-trust, `risk_classifier.py:35`), dus de tool moet expliciet geregistreerd worden of hij belandt in de HITL-poort |
| `tenant_id` | **Nooit uit de payload.** `execute_tool` overschrijft `payload["tenant_id"]` met de context (`service.py:147-150`); de implementatie moet die waarde gebruiken en een payload-`tenant_id` negeren |
| Parameters | `role` (str, optioneel), `department` (str, optioneel), `employee_id` (str, optioneel), `limit` (int, default 50, max 1000) |
| Retour bij succes | `{"success": true, "rows": [...], "row_count": int, "truncated": bool}` |
| Retour bij fout | `{"success": false, "error": "<reden>"}` -- nooit een exception naar de skill, behalve de bestaande `ToolExecutionException` voor onbekende tools |
| Verplichte paginering | `limit`/`offset` conform `.claude/rules/backend-patterns.md` par. 5 |
| Persoonsgegevens | Retourneert nooit BSN, salaris of beoordelingsteksten -- die vallen onder de `denied_actions` van het profiel en horen niet in een leespad voor een adviserende skill |
| Isolatietest verplicht | Tenant A mag geen rij van tenant B zien (`backend-patterns.md` par. 11) |

**Waarom juist deze tool eerst:** het is de enige van de vijf zonder externe afhankelijkheid.
`search_documents` vraagt de RAG-laag (D11, Fase 3), `generate_text` overlapt met de
LLM-abstractie, `send_notification` en `schedule_training` zijn schrijfacties die de
Council-poort nodig hebben (D2, Fase 2). De gap-analysefunctie kan met alleen deze tool al
werken -- precies de knip die D10 voorschrijft.

## 4. Wat NIET is gedaan

Geen tool geïmplementeerd. Fase 1 is gap-analyse; `query_hr_database` bouwen vereist de
Council-poort en het echte harnas uit Fase 2. Het contract hierboven is het overdrachtspunt.

## 5. Trainingssamenvatting

**Flow 1 -- een skill roept een tool aan die niet bestaat**

- Actor: ALS-skill (agent)
- Voorwaarde: het manifest declareert de tool en het profiel staat hem toe, maar er is geen
  implementatie
- Actie: de skill emit `TOOL_CALL: query_hr_database {...}`
- Systeemreactie: `is_tool_allowed` geeft True (permissie is toegekend), de categoriecheck
  op stap 0a weigert met `ToolExecutionException("Unknown tool category")`; `act()` vangt
  die en zet hem in `errors`
- Succes: n.v.t. -- `success` is False omdat er een fout is
- Fout: de skill krijgt een expliciete fout, geen stil succes
- Uitzonderingen: geen. Dit is het huidige gedrag voor alle 27 gedeclareerde tools

**Flow 2 -- twee tool-calls waarvan één faalt**

- Actor: ALS-skill met meerdere tool-calls in één antwoord
- Voorwaarde: beide tools staan in de allowlist
- Actie: de eerste tool slaagt, de tweede geeft een fout
- Systeemreactie: `results` bevat 1 item, `errors` 1 item; `success` is **False**
- Succes: n.v.t.
- Fout: de OODA-loop rekent geen prana af, want die hangt aan `result.success`
- Uitzonderingen: vóór deze wijziging was `success` True en werd er wél afgerekend

**Flow 3 -- een beheerder voegt een tool aan een profiel toe**

- Actor: beheerder van `config/tool_permissions.yml`
- Voorwaarde: het profiel heeft `namespace: broker_tool`
- Actie: er wordt een toolnaam toegevoegd die niet resolveert
- Systeemreactie: `test_broker_namespace_tools_resolve_or_are_known_gaps` faalt met de naam
  van de tool en het profiel erbij
- Succes: de fout wordt bij het committen gevonden, niet bij de eerste agent-aanroep
- Fout: n.v.t.
- Uitzonderingen: een bewuste, gedateerde uitzondering in
  `KNOWN_UNRESOLVED_BROKER_TOOLS` met reden per regel

## 6. Gewijzigde bestanden

| Bestand | Wijziging |
| --- | --- |
| `src/core/als/agents/specialist_base.py` | F3: `success = not errors` |
| `config/tool_permissions.yml` | F2: `namespace` per profiel + uitleg bij het veld |
| `tests/unit/als/test_act_partial_tool_failure.py` | nieuw, 4 tests (1 rood -> groen) |
| `tests/architecture/test_tool_profile_namespaces.py` | nieuw, 4 tests |
