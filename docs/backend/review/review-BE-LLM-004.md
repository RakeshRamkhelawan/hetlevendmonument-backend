STATUS: APPROVED WITH MINOR GAPS
Twee reviewers, allebei CHANGES_REQUESTED in ronde 1. Alle blokkerende bevindingen zijn zelf
nagemeten voor er iets werd aangeraakt, en daarna gerepareerd met mutatiebewijs in beide
richtingen. Twee bevindingen zijn bewust NIET in deze knip opgelost; ze staan onderaan met een
eigen brief.

# Review BE-LLM-004 -- de klantprovider in gebruik, en het vastpinnen van het adres

Datum:     2026-09-23
Spec:      `docs/backend/features/BE-LLM-004-klantprovider-in-gebruik.md`
Reviewers: code-reviewer (afgerond), quality-reviewer (afgerond)
Basis:     develop `0a69e1ab`

---

## De zwaarste bevinding, en beide reviewers vonden hem los van elkaar

**De strengere adreseis gold niet voor het adres waar de verbinding heen gaat.**

`KlantEindpuntControle` bestaat omdat `SSRFProtector` drie IPv6-vormen doorlaat die naar binnen
wijzen. Die strengere eis draaide alleen op de tak waar een klant een LETTERLIJK IP intypt. Gaf
hij een NAAM op, dan werd alleen gecontroleerd dat de naam bestaat. Zelf nagemeten voor de
reparatie:

```text
adres uit de DNS-opzoeking       oordeel
::                           ->  TOEGESTAAN, en het werd vastgepind
64:ff9b::a9fe:a9fe (NAT64)   ->  TOEGESTAAN
2002:a9fe:a9fe:: (6to4)      ->  TOEGESTAAN
::1                          ->  geweigerd
fc00::1                      ->  geweigerd
```

Die eerste drie zijn exact de drie vormen waarvoor deze klasse is gebouwd, en de IPv4-tegenhanger
(169.254.169.254) is wel dicht -- juist die asymmetrie maakt het een omissie en geen keuze.

Tot deze knip was dat een validatiekwestie, want `keten()` had nul aanroepers. BE-LLM-004 maakt
van het opgezochte adres een INSTRUCTIE ("verbind hierheen"), en mijn eigen docstring beweerde
dat alle vier de extra eisen "onverkort" gelden. Dat was onwaar op precies de plek waar een
volgende lezer erop bouwt.

**Gedaan:** elk opgezocht adres gaat nu door `_eis_publiek_adres`. Na de reparatie gemeten: de
drie vormen hierboven worden geweigerd, een echt publiek adres gaat door. Drie tests met een
parameter per vorm, plus de tegenrichting.

## De andere blokkerende bevindingen

**Een verloren-update op een procesbrede instelling.** De DNS-opzoeking doet "opslaan, zetten,
terugzetten" op `socket.setdefaulttimeout`. Dat was veilig zolang hij op een draad liep -- en
deze knip verplaatst hem juist naar een threadpool. Twee agents kunnen dan elkaars TIJDELIJKE
waarde als "de vorige" lezen, waarna het proces permanent op 5,0 blijft staan. Mijn eigen test
daarvoor was single-threaded en kon het per constructie niet zien.
**Gedaan:** een module-slot om de save/set/lookup/restore, met een test die eist dat het slot
vastzit op het moment dat de globale gewijzigd is. Geen twee draden en dus niet flaky.

**Een kale `except Exception` die elk defect in een stille terugval veranderde.** Beide reviewers
wezen erop: een programmeerfout in dit pad werd "de agent werkte, alleen met een ander model" --
onzichtbaar in elke test en elk dashboard. Dat is de succes-zonder-werk-vorm waar ADR-036 om
draait, en deze knip repareerde er net zelf een.
**Gedaan:** `AttributeError`, `TypeError`, `ImportError` en `NameError` gaan door; een
configuratie- of infrastructuurfout degradeert nog steeds, met een logregel die er nu bij zegt
wat het GEVOLG is (de gegevens gaan naar de standaardprovider en niet naar de verwerker die de
klant koos).

**De sleutel had een rem in de ene laag en niet in de volgende.** `ProviderRij.api_key` had
`repr=False` met de motivering "de enige rem"; diezelfde ontsleutelde sleutel reist in deze knip
door naar `LLMConfig.api_key`, waar die vlag ontbrak. Erger: mijn nieuwe logbewaker kon die vorm
niet zien, want hij zocht naar de NAAM van het veld en `self.config` is die naam niet.
**Gedaan:** `repr=False` op `LLMConfig.api_key`, en de bewaker kent nu ook DRAGERS -- een object
dat het geheim bevat. Met het onderscheid dat `X.config` fout is en `X.config.model` niet,
anders zou een bestaande, onschuldige logregel om een uitzonderingslijst vragen.

## Wat de reviewers nog meer aanwezen, en wat ermee is gebeurd

| Bevinding | Gedaan |
|---|---|
| Het vastgepinde adres werd uit een `set()` gekozen: per proces een andere keuze, dus een storing die per worker verschilt | `sorted(set(...))`, met de reden erbij |
| De lege-keten-terugval liet geen spoor na, terwijl de succesweg met AVG art. 28 wordt gemotiveerd | logregel toegevoegd, met het onderscheid tussen "niets ingericht" en "alles afgekeurd" |
| De plafond-docstring zei dat verstoppen achter `importlib` niet is gedaan, terwijl mijn eigen nieuwe code `get_db_session` er juist achter verstopte met precies die motivering | de import staat nu gewoon bovenaan; de rand is betaald (infra 104 -> 105, Ce 239 -> 240) |
| De reden onder het poort-behoud klopte niet: het beleid staat alleen 443 toe, dus een eindpunt op `:8443` kan niet bestaan | reden vervangen door de houdbare versie; het voorbeeld in de featuredoc ook |
| De testnaam beloofde een assertie op de foutmelding die er niet was | assertie op de melding toegevoegd, in beide richtingen |

## De scherpste opmerking van de Devil's Advocate, en wat ik ermee heb gedaan

> Het hele vastpinnen rust op EEN eigenschap van httpx: dat hij omleidingen niet volgt. Dat is
> geen afspraak van ons maar een standaardwaarde van een derde partij.

Nagemeten en juist. Een 3xx zou de client zelf een nieuwe bestemming laten opzoeken -- buiten de
adrescontrole om, zonder vastgepind IP, met `sni_hostname` vrolijk mee naar een andere host.

**Gedaan:** `follow_redirects=False` staat nu expliciet in `_client()`, plus twee tests. Die
tweede is het vermelden waard: een gedragstest ("gaat er precies EEN verzoek uit") betrapt het
weghalen van de vlag NIET, want httpx heeft vandaag dezelfde standaard -- gemeten met het
mutatieharnas, de mutatie bleef groen. Er staat daarom ook een toets op de BRON, die wel sterft.
Dat is het enige wat zo'n toets rechtvaardigt.

## Bewust NIET in deze knip, met een brief

1. **De databasesessie blijft open tijdens de adrescontrole.** Per rij tot vijf seconden DNS, met
   de verbinding uit de pool erbij. Met een keten van vier rijen is dat twintig seconden per
   agenttaak, op een staging-database die op 40 van de 50 verbindingen zit. De reparatie (rijen
   ophalen, sessie sluiten, daarna controleren en ontsleutelen) is een eigen knip met eigen
   bewijslast.
2. **`organism_registry.create_agent` bewaart agent-exemplaren voor altijd, op een sleutel zonder
   tenant.** Gemeten: dat woordenboek wordt nergens gelezen, en het levende pad loopt via
   `loader.get_agent_instance()` -- dus vandaag geen lek. Maar een agent die daar belandt houdt nu
   wel een ontsleutelde klantsleutel in procesgeheugen. Zodra iemand dat woordenboek gaat lezen,
   is het een tenantlek.

Beide staan in `docs/agent-briefs/generated/2026-09-23-bevindingen-na-de-klantprovider.md`.

## Meting

```text
tests/unit/llm                                    82 passed
tests/unit/security                              171 passed   (incl. 33 op het klanteindpuntbeleid)
tests/unit/services/test_tenant_llm_provider...   17 passed
tests/unit/test_ssrf_protection.py                82 passed
tests/unit/als + tests/unit/agents               1184 passed
tests/architecture                              1003 passed

ruff                     All checks passed!
scripts/run_mypy_audit   Total errors: 0
python -m pyright        0 errors, 35 warnings
check_any_gate           7110 = 7110 (baseline in deze knip een omlaag vastgeklikt)
```

**Mutatiebewijs: 20 mutaties in ronde 2, alle betrapt**, tegenrichting groen. Inclusief de vier
nieuwe uit deze reviewronde (de opgezochte adressen, het slot, de omleidingsvlag en een logregel
die de hele config afdrukt).

## Openstaand

1. De twee bevindingen hierboven met hun eigen brief.
2. Het chatpad draait nog op de platformstandaard; de oude LLM-stapel migreren is een eigen
   beslissing.
3. Fase 3 (failover over meerdere rijen) erft de open sessie uit punt 1 en wordt daar gevoeliger
   voor: vier rijen betekent vier opzoekingen achter dezelfde verbinding.
