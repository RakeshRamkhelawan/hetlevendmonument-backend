# BE-LLM-004 -- de klantprovider wordt gebruikt, en het verzoek gaat waar de controle keek

Datum:     2026-09-23
Fase:      Lokaal-eerst LLM-platform, fase 2b (na 2a = BE-LLM-003)
ADR:       ADR-026 (LLM-keten per tenant), ADR-005 (tenant NOT NULL), ADR-036 D10
Basis:     develop `0a69e1ab`

---

## 1. Waarom deze knip bestaat

Fase 2a gaf een klant de mogelijkheid zijn eigen LLM-eindpunt en sleutel te laten inrichten.
Gemeten op `0a69e1ab`, voordat er iets is gewijzigd:

| Wat | Meting |
|---|---|
| `LLMService.for_tenant` | bestaat niet -- nul treffers in `src/` |
| `TenantLLMProviderService.keten()` | nul aanroepers; de enige vermeldingen staan in docstrings |
| `BaseSpecialistAgent._get_llm_service()` | bouwt `LLMService()` zonder tenant, terwijl `self.tenant_id` bekend is |

Een klant kon dus een eindpunt en een sleutel inrichten, en elke agent praatte toch met het
platformmodel. Opslag zonder gebruiker.

## 2. Wat er nu gebeurt

`LLMService.for_tenant(tenant_id, db)` vraagt de keten op, neemt de EERSTE bruikbare rij en
bouwt daarmee een provider. Lege keten -- geen rijen, noodknop uit, of elke rij overgeslagen --
levert de platformstandaard. De agentdeur (`_get_llm_service`) is async geworden en gebruikt hem;
dat is de enige aanroepplek die er vandaag is, en het is een pad dat daadwerkelijk draait
(de HR-piloot, stap 6/7 van de acceptatieketen).

Gemeten met drie tenants naast elkaar:

```text
tenant 1  ->  OpenAICompatibleProvider  base_url=https://llm-a.klant.test/v1  vastgepind
tenant 2  ->  OpenAICompatibleProvider  base_url=https://llm-b.klant.test/v1  vastgepind
tenant 3  ->  platformstandaard (lege keten)
```

## 3. Het deel dat geen bijvangst is: het verzoek gaat naar het gecontroleerde adres

**Dit is de belangrijkste wijziging van deze knip, en hij stond niet in de eerste opzet.**

`keten()` controleerde het opgeslagen adres opnieuw bij gebruik -- een goede eigenschap uit fase
2a. Maar daarna kreeg de HTTP-client de NAAM, en die zoekt hem zelf nog een keer op. Tussen de
controle en de verbinding zit dan een venster waarin het antwoord kan veranderen: DNS-rebinding.
Dat is niet theoretisch. Het is in 2026 tweemaal als kwetsbaarheid uitgebracht in precies deze
constructie -- de URL-component van Langflow (IBM-bulletin) en `mcp-atlassian` (CVE-2026-27826),
allebei "valideren en daarna opnieuw opzoeken".

De moduledocstring van `openai_compatible.py` schreef dit zelf vooruit: *"Zet dat veld in een
formulier of een tenantkolom, dan hoort die controle er EERST bij."* Sinds fase 2a komt
`base_url` uit een tenantkolom. Dit is dat moment.

Wat er nu gebeurt, met de publieke httpx-API en zonder prive-internals:

- `keten()` gebruikt `validate_and_resolve()` en geeft het gecontroleerde IP mee in `ProviderRij`;
- de provider verbindt met dat IP, zet de `Host`-kop op de oorspronkelijke naam, en geeft die
  naam mee als `sni_hostname` zodat SNI en certificaatcontrole intact blijven;
- op het gewone pad EN op het streampad -- twee wegen naar buiten, twee keer dezelfde eis.

```text
config: base_url=https://llm.klant.test/api/v1  pinned_ip=203.0.113.7
verzoek: https://203.0.113.7/api/v1/chat/completions
         Host: llm.klant.test
         extensions: {"sni_hostname": "llm.klant.test"}
```

(Een eerdere versie van dit voorbeeld gebruikte poort 8443. Een reviewer wees erop dat
`KLANT_EINDPUNT_CONFIG` alleen 443 toestaat, dus zo'n rij kan niet bestaan -- het voorbeeld
toonde een configuratie die het beleid weigert.)

Zonder vastgepind IP verandert er niets: `http://127.0.0.1:11434` -- de lokale bodem van de
keten -- houdt zijn eigen adres, zijn eigen `Host`-kop en geen SNI.

## 4. De naam van een klant kiest geen klasse

`ProviderFactory.create()` kiest op NAAM. `configureer()` valideert die naam niet; het is een
vrij tekstveld van de klant. Gemeten gevolg als `for_tenant` die naam had doorgegeven:

| Rij heet | Zou opleveren |
|---|---|
| `mock` | MockProvider -- in productie een harde fout op onze eigen guard, daarbuiten verzonnen tekst |
| `gemini` | de Google-klasse, met het adres van de klant genegeerd en zijn sleutel naar een leverancier die hij niet koos |

Een tenantrij gaat daarom altijd door `ProviderFactory.create_generic()`, waar de klasse vastligt
en de naam alleen een ETIKET is. Gemeten na de wijziging: een rij die "mock" heet levert
`serves_mock=False` en het eigen adres van de klant.

Dit is dezelfde faalvorm als de productieguard van 2026-09-21 (`provider_name == "mock"`, een
naam die uit de klassenaam kwam): beslissen op hoe iets HEET in plaats van op wat het DOET.

## 5. Drie dingen die onderweg zijn gerepareerd

**De wrapper miste de resolverende weg.** `KlantEindpuntControle` had alleen `validate_url`.
Met `keten()` overgezet op `validate_and_resolve` zou in productie ELKE rij van ELKE klant een
`AttributeError` hebben gegeven, netjes gelogd als "het opgeslagen adres doorstaat de
adrescontrole niet meer" -- een melding die naar de klant wijst terwijl het probleem bij ons zit.
De unittests zagen het niet, want hun dubbel had de methode wel; de typecontrole ving het. Er
staan nu twee tests op de ECHTE wrapper.

**De DNS-opzoeking wiste een procesbrede instelling.** `_resolve_hostname` zette in zijn
`finally` de standaard-tijdslimiet op `None` -- niet herstellen maar "geen limiet meer", voor
elke socket van elke andere gebruiker in het proces. Zolang die controle alleen bij het inrichten
draaide viel dat niet op; sinds deze knip draait hij op het verzoekpad. Nu wordt de vorige
waarde teruggezet.

**De blokkerende opzoeking staat niet meer op de event loop.** `keten()` roept de synchrone
controle aan via `asyncio.to_thread`: per rij tot vijf seconden blokkeren zou elke andere taak in
dat proces stilzetten.

## 6. De dode tenant-parameter in de oude stapel

`LLMProviderFactory.get_provider(tenant_id=...)` accepteerde een tenant en negeerde hem: de
fabriek keek in `_tenant_configs`, een woordenboek dat in heel `src/` en `tests/` door NIETS werd
gevuld (gemeten). De enige aanroeper gaf een tenant mee en meldde bij een ontbrekende sleutel
"No Gemini API Key found for tenant" -- een melding die een inrichting per klant suggereerde die
niet bestond.

De parameter is weg. De twee tests die de doorgifte vastlegden zijn VERVANGEN, niet geschrapt:
ze legden een belofte vast in plaats van een gedrag. Het chatpad blijft voorlopig op de
platformstandaard; die stapel migreren is een eigen beslissing en geen bijvangst van deze knip.

## 7. Wat dit kost, en wat het NIET is

**Koppeling.** `agent_runtime` Ce 236 -> 240, auth 15 -> 17, infra 103 -> 105. Drie randen
komen uit EEN functie (`bouw_tenant_llm_service`) en zijn onvermijdelijk: een klantsleutel
gebruiken vereist ontsleutelen (security), het adres opnieuw controleren (security) en de rij
ophalen (infra). De vierde is de eerlijkheidsrand uit de Gate 2-ronde: `get_db_session` stond in
`specialist_base.py` achter `importlib` met als reden "om het koppelingsbudget niet te
belasten", terwijl de plafond-docstring in dezelfde wijziging zegt dat verstoppen achter
`importlib` juist niet is gedaan. Een reviewer legde die twee naast elkaar; de import staat nu
gewoon bovenaan en de rand is betaald. Gemeten door de bak op `origin/develop` en op deze
wijziging te scannen, niet afgeleid uit de diff. De gezaghebbende grens `I <= 0,55` breekt pas
bij Ce=245.

**Wat dit NIET is.** Geen failover: alleen de eerste bruikbare rij wordt gebruikt, de rest van de
keten is fase 3. Geen klantscherm (ADR-036 B8: inrichting is dienstverlening). Geen migratie van
het chatpad. En de acceptatieketen blijft op stap 4 van 7 -- deze knip verandert WIE het model
levert, niet hoe ver de keten komt.

**Wat een volgende sessie moet weten.** De provider wordt op het agent-exemplaar gecachet. Een
agent-exemplaar wordt per aanroep gebouwd (`loader.py:215`, `organism_registry.create_agent`), dus
de noodknop `externe_providers_toegestaan` werkt bij de volgende taak en niet halverwege de
huidige. Dat is bewust: binnen een taak blijft het vastgepinde adres stabiel.

## 8. Meting

```text
tests/unit/llm/test_llmservice_for_tenant.py                        4 passed  (nieuw)
tests/unit/llm/test_het_verzoek_gaat_naar_het_gevalideerde_ip.py    5 passed  (nieuw)
tests/architecture/test_de_agentdeur_haalt_het_model_per_tenant.py  2 passed  (nieuw)
tests/architecture/test_een_klantrij_gaat_nooit_op_naam_...py       2 passed  (nieuw)
tests/architecture/test_de_klantsleutel_komt_nooit_in_een_log...py  1 passed  (nieuw)
tests/unit/security/test_klant_eindpunt_beleid.py                  29 passed  (+2)
tests/unit/services/test_tenant_llm_provider_service.py            17 passed  (+2)
tests/unit/test_ssrf_protection.py                                 81 passed  (+1)
tests/unit/{services,llm,als,agents} + ssrf                      1404 passed
tests/architecture                                               1003 passed

ruff                     All checks passed!
scripts/run_mypy_audit   Total errors: 0
python -m pyright        0 errors, 35 warnings
check_any_gate           7111 -> 7110, baseline vastgeklikt
```

**Mutatiebewijs: 16 mutaties, alle betrapt**, tegenrichting groen. Per bewaakte eigenschap
minstens een, inclusief de tegenrichtingen (de platformterugval blijft werken, een lokaal adres
wordt niet vastgepind, een naam zonder adres levert geen verzonnen IP).

## Trainingssamenvatting

- **Actor:** een agent die namens een tenant een taak uitvoert (vandaag de HR-piloot,
  `SkillsGapTrainingSkill` via `BaseSpecialistAgent`). Er is GEEN menselijke actor: dit pad
  draait in een worker, buiten elk verzoek.
- **Voorwaarde:** de tenant heeft via een adviseur een of meer providers laten inrichten
  (BE-LLM-003) en `externe_providers_toegestaan` staat op TRUE. Op de server is
  `MASTER_ENCRYPTION_KEY` gezet. Heeft de tenant niets ingericht, dan is dat geen fout -- dan
  geldt de platformstandaard.
- **Actie:** de agent vraagt tijdens zijn OODA-stap om een taalmodel
  (`await self._get_llm_service()`).
- **Systeemreactie:** de keten van die tenant wordt opgehaald; per rij wordt het opgeslagen adres
  OPNIEUW gecontroleerd en opgezocht, en de sleutel ontsleuteld. De eerste bruikbare rij levert
  de provider, die verbindt met het gecontroleerde IP-adres met de oorspronkelijke naam in de
  `Host`-kop en in de TLS-controle. Er komt een logregel met tenant, etiket en host -- nooit de
  sleutel.
- **Succes:** de agent praat met het eindpunt van zijn eigen klant. In het log staat
  `LLM per tenant: tenant=<id> label=<naam> host=<host> vastgepind=True`.
- **Fout:** een rij waarvan het adres niet meer deugt of de sleutel niet te ontsleutelen is,
  wordt OVERGESLAGEN met een `logger.error` die de reden noemt en de sleutel niet. Blijft er
  niets over, dan geldt de platformstandaard, met een logregel die zegt dat de keten leeg was.
- **Uitzonderingen:** een programmeerfout in dit pad (`AttributeError`, `TypeError`,
  `ImportError`, `NameError`) wordt NIET afgevangen en stopt de taak -- anders zou een defect
  zich uiten als "de agent werkte, alleen met een ander model". Een configuratie- of
  infrastructuurfout degradeert wel naar de platformstandaard, met een logregel die het gevolg
  benoemt: de gegevens gaan dan naar de standaardprovider en niet naar de verwerker die de klant
  zelf koos.
