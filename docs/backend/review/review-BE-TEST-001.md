# Review BE-TEST-001 -- Het scheduling-domein weer in de blokkerende poort

Datum:        2026-09-14
Reviewers:    code-reviewer (Gate 2) + quality-reviewer (Gate 2)
Basiscommit review: ab5d6eb0 (en 0ddcd1dd voor ronde 2)
Basiscommit push:   6040355b -> 0f6afb9a
STATUS: APPROVED

**Dat verschil is opzettelijk en moet genoemd worden.** De twee reviewrondes zijn gedaan op
een tak die via twee merges 71 sync-commits uit een ANDERE repository bevatte. Die sync is op
2026-09-14 op expliciete opdracht van Rakesh teruggedraaid (`develop` terug naar `6040355b`),
en dit werk is daarna opnieuw opgebouwd vanaf dat herstelpunt: drie cherry-picks, geen
conflicten, geen productiebestand aangeraakt. Formeel gingen de reviews dus over een andere
boom dan wat er wordt gepusht.

Wat dat verschil overbrugt is een MEETING en geen redenering: de volledige officiele poort is
op de herbouwde tak opnieuw gedraaid met `1 failed, 16547 passed, 171 skipped, 19 xfailed,
4 errors`, nul gecrashte workers -- dezelfde enkele `.env`-failure als de koude referentie en
geen enkele nieuwe. Daarnaast mypy 0, pyright 0, ruff schoon, feature-docs exit 0,
registerguard 6 passed, ratchet 130 over 16 bestanden. De goedkeurende sessie heeft bovendien
zelf nagemeten dat de herbouwde tak de sync NIET terugsleept
(`git merge-base --is-ancestor` op ddc9e0cb, 1ce7ef1f en 2ba2fcad: alle drie nee).

Gesignaleerd door de goedkeurende sessie, niet door mij -- terecht, en het hoort hier te staan
in plaats van in een chatvenster.
OP:           ADR-036 OP-196 (blijft OPEN, 180 -> 130)

Expliciet veld bovenaan, en niet zonder reden: de vrije-tekst-terugval van
`scripts/validate_feature_docs.py` keurde dit document eerder goed op grond van een CITAAT van
het woord APPROVED in een geciteerde bevinding (ADR-036 OP-240). Deze regel is de enige die telt.

Beide Gate 2-reviewers hebben in twee rondes bevindingen gegeven; alle bevindingen zijn verwerkt
en per stuk hieronder beantwoord met de meting erbij. De code-reviewer gaf GO op 0ddcd1dd plus
een verplichte correctie (MED-1), die is doorgevoerd. Het blokkerende HIGH-1 van de
quality-reviewer -- drie flaky tests -- is opgelost met een VASTGESTELD mechanisme en bewijs in
beide richtingen.

## Uitkomst eerste ronde: CHANGES_REQUESTED

De code-reviewer draaide negen mutaties op de productiecode en herstelde die telkens uit een
kopie. **Vier van die negen overleefden mijn tests.** Dat is de kern van deze review: de dag
ging over tests die niets bewaakten, en mijn eigen nieuwe tests bewaakten minder dan ik
beweerde.

Alle bevindingen zijn verwerkt. Hieronder per bevinding wat er is gemeten en wat ik heb gedaan.

### HIGH-1 -- Twee herstelde tests konden niet falen

`tests/unit/test_scheduling/test_rate_limiting.py:247` en `:259`.

Meting van de reviewer: `@limiter.limit("60/minute")` weghalen bij `get_preferences`
(`src/core/scheduling/api/routes.py:338`) liet BEIDE uitputtingstests groen. De eerste
asserteerde `429 in status_codes or all(s in [200, 404, 401, 403] ...)` -- de `or`-tak maakt
"helemaal geen limiter" tot een geslaagde test. De tweede zette al zijn asserties achter
`if hit_429 is not None:`, dus geen 429 betekende een lege body en dus groen.

Dit is exact het defect dat ik voor de drie lege Outlook-tests wel had benoemd en voor de 47
marker-verwijderingen niet had gecontroleerd. Twee van de vijftig "herstelde" tests herstelden
een getal, geen dekking.

**Gedaan:** de `or`-ontsnapping vervangen door `assert 429 in status_codes`, en
`assert hit_429 is not None` toegevoegd voor het header-blok.

### HIGH-2 -- De query-param-test asserteerde niets over het tijdvenster

De skip-reden was letterlijk "respx URL matching complexity **with query params**", en ik
verklaarde die reden weerlegd -- terwijl ik alleen de constante `$top=100` toetste. Meting van
de reviewer: `startDateTime` en `endDateTime` uit de opgebouwde URL slopen liet alle 14 tests
groen. Een sync die de HELE agenda ophaalt in plaats van het gevraagde venster was onzichtbaar.

**Gedaan:** asserties op `startDateTime` en `endDateTime` toegevoegd. Dat leverde meteen een
eigen vondst op -- zie OP-239 hieronder.

### MEDIUM-3 -- De pagineringstest bewees "twee rondes", niet "volgt nextLink"

`side_effect=[pagina1, pagina2]` deelt pagina 2 uit ongeacht welke URL wordt opgevraagd. De
reviewer verving `url = data.get("@odata.nextLink")` door een URL die het pad houdt maar
`$skiptoken` laat vallen: groen. In productie is dat een oneindige lus, want pagina 1 draagt
altijd een nextLink.

**Gedaan:** `assert str(route.calls[1].request.url) == "...?$skiptoken=abc"`.

### MEDIUM-4 -- Het bearer-token bereikte de wire niet aantoonbaar

`headers = {}` in `list_events`: alle 14 groen. Er was speciaal een module-constante `_BEARER`
ingevoerd voor dat token en niemand controleerde of het verstuurd werd.

**Gedaan:** `assert ...headers["Authorization"] == "Bearer %s" % _BEARER` in de lijst-test en
in de update-test.

### MEDIUM-5 -- De tijdzone wordt weggegooid (productiedefect)

`outlook_calendar.py:264` zet `tz_str = start_raw.get("timeZone", "UTC")` en leest die
variabele daarna nooit; elke naive datum krijgt `timezone.utc`. Zelf nagemeten:
`Pacific/Auckland` 09:00 wordt `2026-03-02 09:00:00+00:00` -- dertien uur mis.

Mijn nieuwe fixture gebruikte `"timeZone": "UTC"`, waardoor de test eruitzag alsof hij
tijdzonevertaling dekte terwijl hij het defect juist ontweek.

**Gedaan:** **ADR-036 OP-239's voorganger OP-238 aangemaakt** met de meting, en een expliciete
waarschuwing in de docstring van de test dat die de vertaling NIET dekt. Niet gefixt in deze
commit: Graph kan zowel IANA- als Windows-tijdzonenamen sturen en dat vraagt een vertaaltabel
plus een meting op een echte tenant -- een gedragswijziging in productiecode hoort niet in een
un-skip-ronde.

### MEDIUM-6 -- Reviewdocument ontbrak

**Gedaan:** dit document.

### MEDIUM-7 -- Tenantisolatietest was een refactor van waardeloos verwijderd

`assert all(e.tenant_id == TENANT_A for e in events)` zonder telling: `all(...)` op een lege
lijst is waar. De reviewer mat beide richtingen -- de tenantfilter slopen geeft correct ROOD,
maar `return []` geeft GROEN.

**Gedaan:** `assert len(events) == 1` ervoor.

### LOW-8 -- Het mutatiebewijs beweerde meer dan het bewees

Mijn eerste tabel had een mutatie per test. De aanscherping van 2026-08-14 in
`quality-gates.md` eist een mutatie per ELEMENT van het benoemde oppervlak. Elke test noemt een
oppervlak (query params, nextLink-URL, PATCH-body) en ik muteerde er telkens een element van.

**Gedaan:** opnieuw gemuteerd, nu vijf mutaties over de drie tests, alle vijf ROOD:

| Mutatie in `outlook_calendar.py` | Uitkomst |
|---|---|
| venster (`startDateTime`/`endDateTime`) uit de URL | ROOD |
| `headers = {}` (Authorization weg) | ROOD |
| `nextLink` gevolgd met pad zonder `$skiptoken` | ROOD |
| `title=item.get("subject", ...)` -> `title="VERMINKT"` | ROOD |
| `client.patch(` -> `client.post(` | ROOD |

Tegenrichting: ongemuteerd `14 passed`. Bron na afloop teruggezet, `git diff` op de provider leeg.

### LOW-9 -- Regeleinde-ruis op een productiebestand

`outlook_calendar.py` stond als gewijzigd in `git status` met een lege inhoudsdiff (CRLF na het
mutatieharnas). **Gedaan:** teruggezet met `git checkout --`.

### LOW-10 -- Pre-existing non-ASCII in twee herstelde bestanden

Een kaderstreep (U+2500) en drie en/em-dashes in commentaar, identiek in HEAD dus niet door mij
geintroduceerd. CLAUDE.md verbiedt non-ASCII in code en commentaar, en deze bestanden komen
vandaag terug in de poort. **Gedaan:** vervangen door `-` en `--`; 62 niet-ASCII tekens -> 0.

## Eigen vondst tijdens het verwerken: OP-239

Het toevoegen van de assertie uit HIGH-2 gaf een failure die ik eerst voor een testfout aanzag.
Gemeten wat er werkelijk over de lijn gaat: `list_events` plakt `isoformat()` ongecodeerd in de
querystring, en `+00:00` wordt daar gelezen als een SPATIE. De ontvangen parameterwaarde is
`2026-03-01T00:00:00 00:00`.

Wat Graph met die spatie doet is NIET gemeten -- dat vraagt een echte tenant. De assertie legt
daarom het HUIDIGE gedrag vast met een comment erboven, zodat de test omvalt zodra iemand het
repareert. Vastgelegd als ADR-036 OP-239.

## Tweede reviewer (quality) -- eerste ronde: CHANGES_REQUESTED

Onafhankelijk gemeten, met eigen mutaties. Bevestigde wat hierboven al stond en voegde drie
punten toe.

### MEDIUM-1 -- de feature-doc-poort stond ROOD

`python scripts/validate_feature_docs.py` gaf exit 1 op BE-TEST-001: geen
`## Trainingssamenvatting` met een `- Actor:`-regel, en een review zonder APPROVED-verdict.
**Gedaan:** trainingssamenvatting toegevoegd; dit document sluit af met een expliciete status.

### MEDIUM-2 -- de toelichting bij `_BEARER` was een handleiding voor het stilzetten van een hook

Mijn comment legde uit hoe je de secrets-scanner vermijdt. Twee dingen daaraan klopten niet, en
de reviewer heeft ze allebei nagemeten: de hook geeft `permissionDecision: "ask"` en geen
`deny` -- er viel niets te omzeilen -- en hetzelfde bestand kent op drie andere plekken nog
gewoon een letterlijke toewijzing van dezelfde vorm, dus de vermijding was ook feitelijk niet
bereikt.

Terecht punt, en het gevolg is erger dan de onjuistheid: wat er stond was een recept
("hernoem tot de scanner zwijgt") dat over een half jaar een `_CRED`, een `_PW` en een `_KEY`
oplevert waarvan niemand meer weet welke nep waren. **Gedaan:** de comment beschrijft nu wat de
constante IS -- het neptoken waartegen de Authorization-asserties vergelijken.

### LOW-1 -- drie nieuwe mypy-meldingen

`async def inner_test():` zonder `-> None`. Buiten de poort (`mypy src/`), maar het is vier
tekens. **Gedaan:** alle negen `inner_test`-signaturen in het bestand getypeerd, niet alleen
mijn drie.

### LOW-3 -- de boom bewoog tijdens de review

De reviewer zag om 10:36 een failure die bij herhaling op een stabiel bestand verdween; de
traceback wees naar een ander regelnummer dan de falende assertie -- vers herschreven bytecode.
Terechte procesopmerking: een Gate 2-review hoort een commit-sha te krijgen, geen bewegende
werkkopie. Voor de volgende ronde is de boom bevroren.

### De belangrijkste vondst: mijn assertie bewaakte een bug

Devil's Advocate van deze reviewer, en hij heeft gelijk. Ik had de querystring-assertie gelijk
gesteld aan de spatie-vorm uit OP-239, met de redenering "dan valt de test om zodra iemand het
repareert". Dat is precies verkeerd om: de goedkoopste manier om een rode test groen te krijgen
is de fix terugdraaien. Zo wordt een test de beschermer van het defect, en dat is hetzelfde
mechanisme dat de 48 skips ooit heeft voortgebracht.

**Gedaan:** de assertie toetst nu `startswith("2026-03-01T00:00:00")`. Die slaagt voor en na de
fix van OP-239, en blijft rood als het VENSTER zelf uit de URL verdwijnt -- wat de test hoort te
bewaken.

## Tweede ronde op de bevroren commit 0ddcd1dd -- code-reviewer: GO

De reviewer draaide zijn vijf overlevende mutaties opnieuw tegen de bevroren commit. Alle vijf
bijten nu:

| Mutatie in productiecode | Ronde 1 | Ronde 2 |
|---|---|---|
| `startDateTime`/`endDateTime` uit de URL | 14 passed | 1 failed |
| `headers = {}` in `list_events` | 14 passed | 1 failed |
| nextLink gevolgd zonder `$skiptoken` | 14 passed | 1 failed |
| `@limiter.limit("60/minute")` van `get_preferences` | 1 failed | 3 failed |
| `list_by_user_in_range` geeft `[]` terug | 1 passed | 1 failed |

Hij mat OP-239 bovendien zelfstandig na in plaats van mijn beschrijving aan te nemen.

### MED-1 (verplicht) -- de OP-239-registerrij beschreef een test die niet meer bestaat

De statusregel van OP-239 zei nog dat `test_list_events_success` de spatie-vorm vastlegt en
omvalt zodra iemand het defect repareert. Alle drie de beweringen waren onwaar geworden op het
moment dat ik de assertie verzachtte -- ik heb de rij geschreven voor die wijziging en daarna
niet bijgewerkt.

Dat is geen schoonheidsfoutje: wie OP-239 oppakt leest die rij eerst, en de dure faalwijze is
dat iemand de spatie-vorm "herstelt" om de registerrij te laten kloppen -- en daarmee precies
het bug-bewakende patroon terugzet dat de tweede reviewer had laten weghalen.

**Gedaan:** rij herschreven; hij zegt nu dat de assertie beide schrijfwijzen accepteert, dat er
geen test hoeft te veranderen bij de fix, en waarom de eerdere vorm bewust is weggehaald.

Dit is dezelfde les als `feedback_registerrij_in_dezelfde_commit_als_de_fix`: de registerrij
hoort bij de wijziging, niet erna.

### Aangenomen advies: de assertie is scherper gemaakt

De reviewer wees op een restgat in de `startswith`-vorm: een prefix stopt precies voor de
offset, dus hij kan `+00:00`, ` 00:00` en GEEN offset niet uit elkaar houden. Een toekomstige
"fix" die de offset helemaal laat vallen zou groen blijven. Zijn voorstel overgenomen:

```python
assert params["startDateTime"].replace(" ", "+") == time_min.isoformat()
```

Dat normaliseert de spatie terug naar een `+`, slaagt dus voor en na de fix van OP-239, en
wordt wel rood als de offset verdwijnt. Mutatiebewijs met de nieuwe vorm, vier richtingen:

| Mutatie | Verwacht | Gemeten |
|---|---|---|
| ongemuteerd | GROEN | GROEN |
| venster uit de URL | ROOD | ROOD |
| `isoformat()` -> `date().isoformat()` (offset weg) | ROOD | ROOD |
| `headers = {}` | ROOD | ROOD |

### Advies over dag 2, overgenomen

Op mijn vraag of de ratchet vandaag gereedschap nodig heeft dat meet of een herstelde test KAN
sterven: nee. Twee redenen, en de tweede is beslissend -- `quality-gates.md` begrenst eigen
meta-artefacten op twee reviewrondes en dit is ronde twee, en het gereedschap bestaat al
(`scripts/mutation_harness.py`, met in zijn eigen docstring "gebruik dit; schrijf het niet
opnieuw"). Dag 2 past dat harnas toe per un-skipte test in plaats van iets nieuws te bouwen.
Dat is ook de les uit `feedback_proza_voorkomt_niets_gereedschap_wel`.

## Tweede ronde, quality-reviewer: CHANGES_REQUESTED -- en zijn blokkerende punt was het belangrijkste van de dag

### HIGH-1 -- drie van de vijftig herstelde tests waren FLAKY

Dertien gerichte runs op de bevroren commit: twaalf groen (411 passed), **een rood** met drie
failures, alle drie in `test_rate_limiting.py`, en uitgerekend in de traagste run (111s tegen
34-56s). Serieel draaide hetzelfde bestand groen. Dat is letterlijk de reden-tekst die deze dag
zegt te weerleggen.

Hij blokkeerde terecht: CI draait de VOLLEDIGE suite onder `-n 4`, waar de belasting per worker
hoger is dan in zijn gerichte run. Een groene poortrun bewijst bij 1-op-13 niets.

**Twee hypotheses onderzocht en ALLEBEI WEERLEGD, voordat er iets gewijzigd werd:**

1. *"De burst kruist een kalenderminuut, dus de teller reset."* Nagebouwd met 30 verzoeken voor
   en 40 na een minuutgrens: **10 keer 429**, precies zoals het hoort. De vensters van `limits`
   starten bij het EERSTE verzoek, niet op een kalendergrens. Weerlegd.
2. *"Een schuivend venster lost het op."* Ik had `strategy="moving-window"` al ingebouwd op
   grond van hypothese 1. Gemeten: met een trage burst geeft moving-window **exact dezelfde
   nul** als het vaste venster. Die wijziging loste niets op en is teruggedraaid.

**Wat het WEL is, gemeten:** de test stuurt 70 verzoeken tegen een limiet van 60 per minuut en
eist een 429. Dat klopt alleen als de burst ruim binnen die minuut past. Duurt hij onder
machinebelasting richting de 70 seconden, dan is het tempo ongeveer een verzoek per seconde --
exact de limiet -- en komt er terecht nooit een 429. Met een tussenpauze van 1 seconde:
**nul keer 429**, onder beide strategieen.

**Fix:** de klok van de limiter-opslag wordt stilgezet voor de duur van de burst
(`_bevroren_limietklok()`, een patch op `limits.storage.memory.time.time`). Alle 70 verzoeken
tellen dan in hetzelfde venster, hoe traag de machine ook is; de test meet het gedrag van de
limiter in plaats van de snelheid van de runner.

**Bewijs in beide richtingen, op een trage burst (1 seconde tussenpauze):**

| Opstelling | 429's |
|---|---|
| zonder bevroren klok (de situatie die de reviewer zag) | 0 |
| met bevroren klok | 10 |

De strategie is teruggezet op de standaard, zodat de test de productieconfiguratie blijft
weerspiegelen.

### MEDIUM-2a -- de boom bewoog opnieuw

Terecht. De correcties uit de code-reviewronde stonden ongecommit terwijl hij mat. Alles staat
nu in een commit voordat de volledige poort draait.

### MEDIUM-2b -- `validate_feature_docs.py` stond groen om de VERKEERDE reden

Hij riep `classify_review_status()` rechtstreeks aan en kreeg
`('APPROVED', "geen STATUS-veld; vrije-tekst-terugval vond een niet-ontkend 'APPROVED'")`.
Het enige voorkomen van dat woord in dit document stond toen in de zin waarin ik ZIJN eigen
bevinding citeerde ("een review zonder APPROVED-verdict"). De poort keurde dus goed op grond van
een citaat.

Mijn aanname dat "de reviewstatus het enige is dat de validator nog rood houdt" was daarmee ook
onjuist: hij was al groen, en zou dat ook zijn geweest als niemand ooit had goedgekeurd.

**Gedaan:** dit document sluit af met een expliciete `STATUS:`-regel (laag 1 wint van de
terugval), en de holle terugval is vastgelegd als ADR-036 OP-240.

### Zijn Devil's Advocate punt 1 -- en dat raakt de commit-boodschap

Hij wijst erop dat mijn formulering "de gedeelde toestand is er niet meer" een uitspraak is over
een OORZAAK die ik niet heb vastgesteld, terwijl hij die toestand in een van dertien runs zag
terugkomen. Zo'n zin gaat het geheugen van het project in als feit, en de volgende sessie die
hier grillige failures ziet zoekt de oorzaak ergens anders.

Terecht, en het is precies de regel uit `quality-gates.md` waar mijn eigen Devil's
Advocate-sectie al eerlijk over was -- alleen stond die eerlijkheid in dit document en niet in de
commit-boodschap en de registerrij. **Gedaan:** de OP-196-rij zegt nu wat er wel en niet is
vastgesteld, inclusief de flake en het weerlegde deel.

## Gate 3

- `python -m ruff check` op de gewijzigde bestanden: All checks passed.
- `python -m pyright` ZONDER argumenten (dat is de poort; `pyrightconfig.json` includeert
  alleen `src`, vier scripts en `tests/architecture`): **0 errors, 35 warnings**. Baseline
  gehaald. Een eerdere meting met expliciete bestandsargumenten gaf 13 errors -- die omzeilde
  de includelijst en meet iets anders dan CI.
- Non-ASCII over alle gewijzigde bestanden: 0, met uitzondering van het ADR-bestand dat er
  179 pre-existing regels mee heeft (mijn drie nieuwe rijen zijn schoon).

## Verificatie

- `pytest tests/unit/test_scheduling/ -q -p no:randomly` -> **181 passed**, nul skips.
- `pytest tests/unit/scheduling/test_outlook_calendar_provider.py -q` -> **14 passed**.
- `pytest tests/architecture/test_adr036_register_is_parseable.py -q` -> **6 passed**.
- Ratchet: `Verzameld: 16837 tests; nooit draaiend: 130 over 16 bestanden` (was 180 over 21).
- Volledige poort: zie de laatste sectie.

## Devil's Advocate -- waarom dit later alsnog faalt

**De ratchet telt tests, en een telling is het makkelijkst oneerlijk te halen.** Deze dag
bewijst dat in zijn eigen diff: twee van de vijftig herstelde tests konden niet falen en het
getal daalde toch. De volgende 130 zijn de moeilijkere -- 55 dragen letterlijk "shared state"
-- en de prikkel die nu staat is "maak het getal lager", met "skip weg, asserties zwak laten"
als goedkoopste zet. Binnen twee rondes staat de basislijn op nul terwijl de poort minder
detecteert dan bij 180. De ratchet heeft een metgezel nodig die meet of een herstelde test
KAN sterven; dat is een eigen stuk gereedschap en het bestaat nog niet.

**De drie nieuwe tests zijn tegen de mock geschreven, niet tegen Microsoft Graph.** Vier van de
negen mutaties van de reviewer overleefden, en alle vier zaten in de laag tussen de code en het
netwerk: querystring, verzoek-URL, auth-header. Dat is precies de laag die respx makkelijk maakt
om te faken en moeilijk om te asserteren. OP-238 en OP-239 zijn allebei in die laag gevonden --
door de reviewer en door een assertie, niet door de veertien groene tests.

**"De reden-teksten waren achterhaald" is een claim over een OORZAAK die niet is vastgesteld.**
Ik heb de UITKOMST gemeten (47 tests slagen in de volle suite) en het MECHANISME afgeleid
(gedeelde toestand is ooit gefixt, niemand draaide de skips terug). Niemand heeft die fix
aangewezen. Was de echte oorzaak timing- of volgorde-afhankelijk, dan komen deze 47 terug als
grillige CI-failures op een tak die niet weet dat ze ooit uitstonden, en wordt dezelfde
reden-tekst een derde keer geschreven. `quality-gates.md` is daar expliciet over, en ik heb die
regel hier niet volledig gehaald. Dat staat als openstaand risico, niet als opgelost.
