# BE-AGT-069 -- De sleutelafleiding strip het achtervoegsel, niet elk voorkomen

Status:   GELEVERD
Datum:    2026-09-26
Basis:    develop `f03af73a`
Domein:   backend (agentcatalogus)
Brief:    `docs/agent-briefs/generated/2026-09-25-sprint-dag-de-sleutelafleiding-knipt-blind.md`
Aanleiding: Devil's Advocate van een Gate 2-reviewer op BE-AGT-068

---

## 1. De bevinding

De catalogussleutel werd afgeleid met:

```python
# src/core/als/agents/loader.py:93, zoals het stond op f03af73a
return class_name.lower().replace("agent", "")
```

`str.replace` vervangt ELK voorkomen, niet het achtervoegsel. Dat is geen schoonheidsfout:
het is de oorzaak van de bevinding uit BE-AGT-068. `DunningAgentAgent` werd `dunning`,
waarna de loader `skills/dunning.py` VOND en daarin `DunningSkillSkill` zocht -- een
bestaande, werkende skill die nooit laadde, met alleen een `logger.debug` als spoor.

De reviewer die dit aanwees zei het scherper dan ik het zelf had opgeschreven: de bewaker
die ik in BE-AGT-068 bouwde roept deze afleiding AAN, en legt de kapotte regel daarmee vast
als norm. Wie hem ooit repareert, maakt die bewaker groen op een andere verzameling zonder
dat iemand het merkt.

## 2. De meting die de knip klein maakte

Gemeten op `f03af73a` over alle 139 configuraties, beide configuratievormen:

| Wat | Gemeten |
|---|---|
| Configuraties waarvan de sleutel zou veranderen | **0** |
| Genoemd in `config/domain_packs.yaml` | 0 |
| Letterlijke aanroepers van een gewijzigde sleutel | 0 |

De brief van 2026-09-25 mat nog **2** veranderende sleutels (`AgentHealthMonitorAgent`,
`AgentRouterAgent`) en noemde als stopvoorwaarde: staat er iets anders dan 2 en 0, dan is de
brief verlopen. Hij voorzag ook de reden waarom: "tussen het schrijven en het uitvoeren kan
de opruiming van de 151 configuraties zijn geland, waardoor beide veranderende sleutels
verdwenen zijn; dan is de reparatie helemaal vrij." Dat is precies wat er is gebeurd -- beide
waren catalogusvermeldingen zonder implementatie en gingen mee in BE-AGT-068.

De reparatie is daarmee een aantoonbare no-op op levende data. Van "gedragswijziging met
risico" naar "landmijn onschadelijk maken".

## 3. Wat er is gewijzigd -- drie plekken, niet een

```python
romp = class_name[: -len("Agent")] if class_name.endswith("Agent") else class_name
return romp.lower() or class_name.lower()
```

**De terugval bij een lege romp is een besluit met een reden.** Een klassenaam die exact
`"Agent"` is geeft een lege sleutel, en dan importeert `get_agent_instance` de modulenaam
`src.core.als.agents.skills.` -- dat faalt op een manier die niemand leest. Zo'n naam bestaat
vandaag niet; de terugval staat er zodat hij niet stil kan ontstaan.

**De tweede plek is geen slordigheid.** `scripts/audit_agent_yaml.py::_normalize_key` houdt
bewust een kopie, met een geldige reden in zijn eigen docstring: dat script moet buiten de
applicatiecontext kunnen draaien en importeert daarom niets uit `src/`. Een kopie met een
goede reden blijft een kopie, en deze codebase heeft op 2026-09-25 twee keer meegemaakt dat
een tweede vindplaats stil uiteenliep.

**De derde plek is de toets daarop:**
`tests/architecture/test_de_twee_sleutelafleidingen_zijn_het_eens.py` draait tien namen die
de RANDEN raken door beide implementaties en eist hetzelfde antwoord.

## 4. Het gat dat het mutatiebewijs blootlegde

De overeenstemmingstoets meet overeenstemming -- en dat is juist. Maar mutatie S4 liet zien
wat dat betekent: zet iemand BEIDE implementaties terug op de oude regel, dan blijft hij
groen. Er was dus niets dat de REGEL zelf vastlegde.

Daarom staat er in datzelfde bestand een tweede toets die de afleiding vastpint op vijf
gevallen die onder de oude regel anders uitkomen:

| klassenaam | nieuw | oud |
|---|---|---|
| `AgentRouterAgent` | `agentrouter` | `router` |
| `AgentHealthMonitorAgent` | `agenthealthmonitor` | `healthmonitor` |
| `PaymentAgentRouterAgent` | `paymentagentrouter` | `paymentrouter` |
| `DunningAgentAgent` | `dunningagent` | `dunning` |
| `AgentAgent` | `agent` | `` (leeg) |

## 5. Mutatiebewijs, vier mutaties

| # | Mutatie | Uitkomst |
|---|---|---|
| S1 | de LOADER terug op de oude regel, het script niet | ROOD |
| S2 | het SCRIPT terug op de oude regel, de loader niet | ROOD |
| S3 | de terugval bij een lege romp weggehaald | ROOD |
| S4 | BEIDE terug op de oude regel | GROEN op overeenstemming, ROOD op de regel |

S4 is de belangrijkste en is in de tweede ronde aangescherpt. In de eerste versie toetste hij
alleen dat de overeenstemming bleef; dat is correct gedrag maar liet het gat uit paragraaf 4
open. Nu eist hij beide uitslagen in dezelfde mutatie.

## 6. Verificatie

```text
nulmeting   : 90 passed, 3 xfailed
nameting    : 1294 passed, 3 xfailed, 0 failed
catalogus   : 139 vermeldingen, 135 implementaties, 80 bundels (ongewijzigd)
sleutels     : 0 van 139 veranderd
ruff        : All checks passed
mypy        : 0 errors, baseline 0
pyright     : 0 errors (37 warnings, ongewijzigd)
Any-ratel   : 7050 = 7050
```

## 7. Wat NIET is gedaan

- **De dode velden in `mkb_admin_lite_dunningagent.yaml`** blijven gemarkeerd in plaats van
  verwijderd. Ze raken de `ooda_profile`-vraag uit BE-LLM-006.
- **Een bewaker op sleutelBOTSINGEN.** Twee klassenamen kunnen nog steeds op dezelfde sleutel
  uitkomen; `self.agents[key] = cfg` overschrijft dan stil. Gemeten vandaag: 0 botsingen over
  139 configuraties. Dat is met de nieuwe afleiding aanzienlijk onwaarschijnlijker geworden
  (hij is niet langer lossy in het midden van een naam), maar het is niet onmogelijk en er
  staat geen toets op. Dat is een bewuste grens van deze knip, geen vergetelheid.

---

## Trainingssamenvatting

### Stroom 1 -- een catalogussleutel afleiden uit een klassenaam

- Actor: `EnterpriseCatalogLoader`, bij het laden van de catalogus en bij het opvragen van
  een agent.

- Voorwaarde: er is een configuratie met een `class_name`.

- Actie: `_normalize_agent_key(class_name)`.

- Systeemreactie: het achtervoegsel `Agent` wordt eraf gehaald als het er staat, en de rest
  wordt kleingeschreven. Levert dat niets op, dan wordt de volledige naam kleingeschreven
  gebruikt.

- Succes: een sleutel die een-op-een terug te voeren is op de klassenaam, ook als die naam
  het woord "Agent" ergens in het midden bevat.

- Fout: geen. De afleiding kan niet falen; hij kan hooguit een sleutel opleveren waarvoor
  geen skillmodule bestaat, en dat is een andere kwestie met een eigen melding.

- Uitzonderingen: een klassenaam die exact `"Agent"` is levert `agent` op in plaats van een
  lege sleutel. Zo'n naam bestaat vandaag niet.

### Stroom 2 -- dezelfde afleiding buiten de applicatie

- Actor: `scripts/audit_agent_yaml.py`, gedraaid vanaf de opdrachtregel.

- Voorwaarde: het script mag niets uit `src/` importeren, want het moet buiten de
  applicatiecontext kunnen draaien.

- Actie: `_normalize_key(raw_config)`.

- Systeemreactie: dezelfde afleiding, als bewuste kopie.

- Succes: hetzelfde antwoord als de loader, voor elke naam.

- Fout: loopt de kopie uiteen met de bron, dan faalt
  `tests/architecture/test_de_twee_sleutelafleidingen_zijn_het_eens.py`.

- Uitzonderingen: geen. Er is geen naam waarvoor de twee verschillend mogen antwoorden.
