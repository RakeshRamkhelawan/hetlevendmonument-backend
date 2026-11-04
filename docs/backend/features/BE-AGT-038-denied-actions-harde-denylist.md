# BE-AGT-038 -- `denied_actions`: harde denylist vóór de Council-poort

| Veld | Waarde |
| --- | --- |
| Feature-ID | BE-AGT-038 |
| Datum | 2026-08-01 |
| ADR | ADR-036 D5 (bevoegdheidsniveaus), ADR-015 (ToolBroker allowlist) |
| Wettelijke koppeling | AI Act art. 14 (menselijk toezicht) |
| Sprint | ADR-036 Fase B / Fase 1 / dag 2 |
| Voorganger | BE-AGT-037 (evaluatieset piloot-skill) |

---

## 1. Probleem

ADR-036 D5 beschrijft vijf bevoegdheidsniveaus, waarvan het hoogste "nooit aanraken" is:
handelingen die een agent onder geen enkele omstandigheid mag uitvoeren. Vóór deze
wijziging bestond dat niveau niet in code. Het bestaande `denied_tools` kwam in de buurt,
maar er was geen expliciete afspraak over de verhouding tussen allow- en denylist, en geen
enkele test die vastlegde dat een weigering niet alsnog door een menselijke goedkeuring
ongedaan gemaakt kon worden.

Dat laatste is het eigenlijke punt. Een denylist die de Council of een HITL-goedkeurder mag
overrulen is geen "nooit aanraken" -- dan is het een waarschuwing. Het verschil zit niet in
de configuratie maar in de **volgorde** waarin `ToolBrokerService.execute_tool` zijn poorten
langsloopt.

## 2. Oplossing

### 2.1 Het veld

`AgentToolProfile` krijgt `denied_actions: list[str]`, gevuld vanuit
`config/tool_permissions.yml`. Een ontbrekend veld levert een lege lijst op, zodat bestaande
profielen ongewijzigd blijven werken.

### 2.2 Handhaving en volgorde

`is_tool_allowed()` controleert de denylist als eerste, vóór de allowlist:

```python
if tool_name in profile.denied_actions or tool_name in profile.denied_tools:
    return False
return tool_name in profile.allowed_tools
```

`execute_tool` roept `is_tool_allowed` aan op stap 0 -- vóór de risk-classificatie en dus
vóór de HITL/Council-poort. Die volgorde is nu onderdeel van het contract en wordt door een
test bewaakt (zie §4).

### 2.3 Reconciliatie met `denied_tools` (D5 vereist dit expliciet)

`denied_tools` is de legacy-alias en functioneel een deelverzameling; `denied_actions` is
leidend voor nieuwe profielen. **Beide worden gehandhaafd -- de unie is verboden.**

De reden voor de unie in plaats van vervanging: als `denied_actions` het oude veld zou
overschrijven, wordt een bestaand profiel stilzwijgend losser op het moment dat iemand
alleen het nieuwe veld invult. Een security-veld dat permissiever wordt door een toevoeging
is een valkuil die pas bij een incident zichtbaar wordt.

De afspraak staat bij het veld in de YAML zelf én in de klasse-docstring, niet alleen in
deze spec -- daar kijkt de volgende ontwikkelaar.

### 2.4 Piloot-profiel

`skillsgaptraining` krijgt vier concrete verboden acties:

| Actie | Reden |
| --- | --- |
| `delete_employee_record` | onomkeerbaar, raakt persoonsgegevens (AVG) |
| `update_salary` | arbeidsvoorwaardelijk besluit, geen advieshandeling |
| `terminate_employment` | zwaarste personeelsbesluit dat er is |
| `export_employee_data` | bulk-export van persoonsgegevens buiten het DSAR-pad |

De keuze volgt uit de rol: een skills-gap-skill is **adviserend** (niveau
"Voorstellen"/"Voorbereiden" uit D5). Onomkeerbare personeelsbesluiten horen bij een mens
met de juiste bevoegdheid -- ook mét goedkeuring niet bij de agent.

Een leeg `denied_actions`-veld zou D5 op papier invullen zonder iets af te dwingen; een test
blokkeert dat expliciet.

## 3. Het naamconflict: categoriemodel verwijderd

D5 vraagt ook om verwijdering van de "dode duplicaatklasse" `ToolPermissionManager` in
`src/core/agents/tool_permissions.py`.

**Eerste conclusie (fout).** Bij de eerste verificatie leek de ADR-premisse niet te
kloppen: het is geen duplicaat maar een ander ontwerp met dezelfde naam, en er hing een
testsuite aan met 33 referenties. Die conclusie berustte op het *tellen* van verwijzingen
in plaats van lezen wat ze toetsen -- en op zoekacties met een blinde vlek (zie §3.2).

**Hercontrole.**

- `tests/integration/test_budget_tool_permissions.py` bevatte 8 tests die niets toetsten:
  `assert True`, `assert len([...]) == 3` op een zojuist aangemaakte literal, en
  enum-waarden. `test_analytical_cant_write` toetste niet dat een analytische agent niet
  mag schrijven, maar drie enum-strings. Geen enkele test riep een permissiefunctie aan.
- `tests/unit/test_tool_permissions.py` (20 echte gedragstests) en
  `tests/integration/test_milestone2_resilience_security.py` waren in ronde 1 onzichtbaar.
- Productie-importeurs: **nul**. Het bestand kwam op 2026-04-06 binnen via een bulk-restore
  van 972 Copilot-gestashte bestanden en is nooit aangesloten; sindsdien alleen
  typing-migraties.

**Beslissing: verwijderd.** Twintig tests voor een model met nul aanroepers is geen
dekking maar onderhoud van een museumstuk. Het enige effect op het draaiende systeem was
naamverwarring in de laag waar dat het gevaarlijkst is -- en ADR-036 par. 1.2.B documenteert
dat die verwarring (de drie `ChiefOrchestrator`-klassen) al eerder tot echte fouten leidde.
"Het is getest" bewijst dat het model werkt, niet dat iemand het nodig heeft.

Verwijderd: de module, `tests/unit/test_tool_permissions.py` en
`tests/integration/test_budget_tool_permissions.py`. De defaults-test in
`test_milestone2_resilience_security.py` is niet weggegooid maar omgehangen naar de levende
manager -- de intentie ("de defaults zijn veilig") was geldig, alleen het doelwit niet.

Daarmee zijn **alle vier** de naambotsingen weg, niet alleen die van
`ToolPermissionManager`: ook `ToolCategory` (stond ook in `tool_broker/schemas.py`),
`PermissionEffect` en `PermissionDeniedError` (ook in `src/core/exceptions/exceptions.py`).
OP-15 is CLOSED.

### 3.2 Waarom ronde 1 twee testbestanden miste

`.git/info/exclude` bevatte een blok van 2041 regels uit de bulk-restore van april, dat
1816 **tracked** bestanden verborg -- 15% van de repo, waaronder 585 in `src/core`. Git
negeert exclude-regels voor tracked bestanden, ripgrep niet: `git check-ignore` meldde
"niet genegeerd" terwijl elke zoekactie ze oversloeg.

Opgeschoond (OP-17): 733 tracked-paden verwijderd, de 287 untracked-regels behouden.
Architecture-guards waren niet geraakt -- die gebruiken `Path.rglob`, dat geen ignore-regels
leest. Dat is precies waarom guards op `rglob` horen te draaien en niet op grep.

## 4. Tests

`tests/unit/tool_broker/test_denied_actions_hard_denylist.py` (10 tests, rood gecommit vóór
de fix in `fa0d39ff`):

| Test | Legt vast |
| --- | --- |
| `test_profile_carries_denied_actions` | het veld bestaat op het profiel |
| `test_denied_action_wins_from_allowed_tools` | denylist wint van allowlist |
| `test_denied_tools_stays_enforced` | het legacy-veld verliest zijn kracht niet |
| `test_unknown_agent_still_default_denied` | fail-closed blijft (ADR-015) |
| `test_missing_denied_actions_defaults_to_empty` | oude profielen blijven werken |
| `test_permission_check_precedes_risk_and_council_gating` | de **volgorde** in `execute_tool` |
| `test_denied_action_blocks_without_reaching_the_broker` | weigering leidt niet tot uitvoering |
| `test_pilot_profile_declares_denied_actions` | geen leeg placeholder-veld |
| `test_pilot_denied_actions_are_not_in_allowed_tools` | profiel spreekt zichzelf niet tegen |
| `test_pilot_denied_actions_survive_a_widened_allowlist` | de echte piloot-acties blijven geweigerd als de allowlist wordt verruimd |

De laatste test is een tweede poging. De eerste versie toetste simpelweg
`is_tool_allowed(PILOT, actie) is False` op het echte profiel -- en bleef **groen** toen de
`denied_actions`-check uit de broncode werd gemuteerd. Reden: de vier verboden acties staan
niet in `allowed_tools`, dus de allowlist weigert ze sowieso. De test bewees dus niets over
D5. De herschreven versie verruimt de allowlist met precies die acties en toetst dan of de
denylist standhoudt -- het enige scenario waarin die laag er werkelijk toe doet. Zonder de
mutatietest was dit als dekking geteld die er niet was.

`tests/architecture/test_no_duplicate_permission_class_names.py` (3 tests, OP-15):
blokkeert nieuwe naambotsingen, houdt de bestaande als gedateerde uitzondering, faalt zodra
die uitzondering veroudert, en legt vast wélke van de twee managers het productiepad bedient.

**Mutatie-getest.** De volgordetest gaat rood als de permissiecheck onder de
risk-classificatie wordt geschoven. De botsingsguard is geverifieerd met een tijdelijke
klasse in `src/` (rood) die daarna is verwijderd.

De volgordetest toetst bewust op broncodeniveau: een gedragstest zou de hele broker moeten
opzetten (resilience, circuit breaker, HITL-store) om iets aan te tonen dat puur over
volgorde gaat.

## 5. Trainingssamenvatting

**Flow 1 -- een verboden actie wordt geweigerd, ongeacht goedkeuring**

- Actor: ALS-skill `skillsgaptraining` (agent, niet de eindgebruiker)
- Voorwaarde: het profiel bestaat in `config/tool_permissions.yml` en bevat de actie in
  `denied_actions`
- Actie: de skill probeert `terminate_employment` uit te voeren via de ToolBroker
- Systeemreactie: `is_tool_allowed` geeft `False` op stap 0 van `execute_tool`; de
  aanroep breekt af vóór de risk-classificatie, dus er wordt geen HITL-verzoek aangemaakt
  en de Council wordt niet geraadpleegd
- Succes: de tool wordt niet uitgevoerd en er ontstaat geen goedkeuringspad
- Fout: geen -- weigering is hier het correcte eindresultaat
- Uitzonderingen: geen. Dit pad is niet overrulebaar; dat is het punt van het niveau
  "nooit aanraken" (AI Act art. 14)

**Flow 2 -- een tegenstrijdig profiel: actie staat in beide lijsten**

- Actor: beheerder die `config/tool_permissions.yml` onderhoudt
- Voorwaarde: een actie staat zowel in `allowed_tools` als in `denied_actions`
- Actie: een agent roept die actie aan
- Systeemreactie: de denylist wint; de actie wordt geweigerd
- Succes: geen uitvoering, ondanks de allowlist-vermelding
- Fout: n.v.t.
- Uitzonderingen: het profiel spreekt zichzelf tegen en dat is een leesfout die wacht om
  te gebeuren; `test_pilot_denied_actions_are_not_in_allowed_tools` blokkeert deze
  combinatie voor het piloot-profiel

**Flow 3 -- een bestaand profiel dat alleen `denied_tools` gebruikt**

- Actor: elk agent-profiel van vóór deze wijziging
- Voorwaarde: het profiel heeft geen `denied_actions`-veld
- Actie: een agent roept een actie aan die in `denied_tools` staat
- Systeemreactie: de actie wordt geweigerd; het ontbrekende veld levert een lege lijst op
  en de unie van beide lijsten wordt gehandhaafd
- Succes: het profiel is niet losser geworden door de introductie van het nieuwe veld
- Fout: geen
- Uitzonderingen: een profiel zonder beide velden valt terug op de allowlist, en een
  onbekend profiel wordt volledig geweigerd (ADR-015 default-deny)

## 6. Gewijzigde bestanden

| Bestand | Wijziging |
| --- | --- |
| `src/core/tool_broker/permission_manager.py` | `denied_actions` op het profiel, loader, unie-check in `is_tool_allowed`, docstring met resolutievolgorde |
| `config/tool_permissions.yml` | `denied_actions`-blok voor `skillsgaptraining` + reconciliatie-afspraak |
| `tests/unit/tool_broker/test_denied_actions_hard_denylist.py` | nieuw, 9 tests |
| `tests/architecture/test_no_duplicate_permission_class_names.py` | nieuw, 3 tests (OP-15) |
| `docs/adr/036-...-reuse.md` | OP-15 in §10 |
