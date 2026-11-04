STATUS: APPROVED WITH MINOR GAPS
Twee reviewers, beide CHANGES_REQUESTED in ronde 1, en ze wezen ONAFHANKELIJK van elkaar
hetzelfde hoofdpunt aan: het streampad. Alle blokkerende bevindingen zijn eerst zelf nagemeten en
daarna gerepareerd, met mutatiebewijs in beide richtingen. Twee punten zijn bewust niet opgelost
en staan onderaan.

# Review BE-LLM-005 -- de failoverketen per tenant

Datum:     2026-09-24
Spec:      `docs/backend/features/BE-LLM-005-failoverketen-per-tenant.md`
Reviewers: code-reviewer (afgerond), quality-reviewer (afgerond)
Basis:     develop `54e4b1e7`

---

## De zwaarste bevinding: mijn breaker mat op het streampad niets, en genas een dood eindpunt

Beide reviewers vonden dit los van elkaar. Ik had de breaker daar om een LEGE aanroep gewikkeld
(`await breaker.execute(_niets)`), omdat een async generator pas draait als je erover loopt. De
docstring noemde dat "de eerlijke tussenvorm: de breaker beslist of de schakel geprobeerd MAG
worden, en de lus eronder bepaalt of het lukte."

De tweede helft van die zin was niet geimplementeerd. Zelf nagemeten:

```text
breaker OPEN  --1x lege aanroep-->  HALF_OPEN  --2e lege aanroep-->  CLOSED
```

Dus twee MISLUKTE stromen op een dood eindpunt verklaarden dat eindpunt weer gezond -- ook voor
het gewone pad, want beide halen dezelfde breaker op. En omgekeerd zag de breaker op het
streampad nooit een fout, dus een kapot eindpunt werd bij elk verzoek opnieuw geprobeerd tot zijn
tijdslimiet: precies de kosten die hij hoort te besparen.

Daar kwam bij dat er GEEN ENKELE test op het streampad stond. Zeven tests, alle zeven op
`generate`, terwijl `supports_streaming` op True staat en `LLMService.stream_generate` er
doorheen gaat. De dekking volgde de makkelijkste testvorm in plaats van het risico.

**Gedaan:** de breaker omhult nu het OPENEN van de stroom plus het eerste stukje
(`_eerste_stuk`), dus succes is echt succes en een storing is echt een storing. Vijf nieuwe
stroomtests, waaronder een die expliciet vaststelt dat mislukte stromen een open circuit NIET
sluiten.

## De tweede: mijn inhoudsfilter-belofte was leeg

De moduledocstring beloofde dat een inhoudsweigering niet doorvalt -- "een filter omzeilen door
het vaak genoeg te vragen" mag niet. Die bescherming hing volledig aan
`except LLMContentFilterError`.

Nagemeten: `OpenAICompatibleProvider` -- het ENIGE type dat een klantrij kan opleveren -- gooit
die fout nergens. Een weigering komt binnen als `content: null` met
`finish_reason: "content_filter"`, en `_lees_antwoord` keek eerst naar de inhoud en gooide een
generieke fout. Gevolg: een weigering ging als gewone storing de keten in (dezelfde prompt naar
leverancier 2 en 3) EN telde als storing op de breaker van een kerngezond eindpunt.

**Gedaan:** `_lees_antwoord` leest `finish_reason` voordat hij over de lege inhoud valt.

## De derde en vierde

**Een lege stroom was een stil succes.** Nul stukjes zonder fout: `iets_geleverd` bleef False, er
kwam geen uitzondering, en de keten stopte met een leeg antwoord. Dat is de
succes-zonder-werk-vorm uit ADR-036, en het gewone pad was er wel tegen beschermd. Nu is het een
storing en valt de keten door.

**"Na drie OPEENVOLGENDE fouten" was onwaar.** Zelf nagemeten op `CircuitBreaker`: twee fouten,
een succes, teller nog steeds 2 -- een succes in de staat CLOSED zet hem niet terug. De drempel
is cumulatief. Die formulering stond in de code, de featuredoc EN de brief; alle drie gecorrigeerd
met de meting erbij.

## Wat de reviewers nog meer aanwezen, en wat ermee is gebeurd

| Bevinding | Gedaan |
|---|---|
| Een fout van ONSZELF (`TypeError`, `KeyError`, ...) liet de keten doorvallen: een bug van ons zou een wissel van subverwerker veroorzaken, in een knip die dat juist met AVG art. 28 verbiedt | die vijf fouttypen gaan nu omhoog, net als in de agentdeur; `LLMAuthenticationError` valt bewust WEL door, met een test op die tegenrichting |
| `volgorde` in de breaker-id was ongetest: de bestaande test gebruikte twee verschillende hosts, dus de mutatie "volgorde eraf" bleef groen | test met twee rijen op DEZELFDE host |
| Het testdubbel negeerde zijn `rijen`-argument, dus de koppeling tussen de twee helften lag nergens vast | het dubbel houdt de ontvangen lijst vast en er is een test op |
| De nieuwe module stond niet in de bewaker die de klantsleutel uit logregels houdt | toegevoegd -- en die bewaker vond meteen iets: zie hieronder |
| Geen enkel venster op de breakertoestanden, terwijl elke andere breaker in deze repo dat wel heeft | `breaker_toestanden()`, alleen-lezen |
| Het dienstobject houdt na `for_tenant` een GESLOTEN sessie vast; een toekomstige databaseaanroep in `beproef()` zou stil een verbinding lekken | architectuurbewaker: in `beproef` mag `self._repo` niet voorkomen, met de tegenrichting erbij |
| Drie verouderde toelichtingen (de `importlib`-alinea in de agentdeur, het mutatierecept van een bewaker, een handtekening met `db`) | gecorrigeerd |
| Dode code in het testbestand, een `type: ignore` op een prive-veld, een publieke testhaak in productiecode | opgeruimd; de haak heet nu `_reset_alle_breakers` |

## Wat de logbewaker vond toen hij de nieuwe module zag

Zes onschuldige logregels werden rood, en de bewaker had gelijk: mijn veld met de
breaker-IDENTIFICATOR heette `sleutel`, en in deze codebase betekent dat woord een GEHEIM. Dat is
precies de "een woord, een betekenis"-regel uit CLAUDE.md, toegepast op mijn eigen verse code --
en het antwoord is niet de bewaker versoepelen maar het woord teruggeven aan zijn betekenis.
Hernoemd naar `breaker_id`.

## Wat de afsluitende ronde zelf nog vond: de reparatie had geen test

De inhoudsfilter-reparatie hierboven stond als "gedaan" in dit document, en dat was te vroeg
opgeschreven. Bij het opstellen van het mutatiebewijs bleek `finish_reason == "content_filter"`
in `openai_compatible.py` door GEEN ENKELE test gedekt: `grep -rln content_filter tests/` gaf
alleen `tests/unit/test_llm_service.py`, dat over een ander pad gaat. Een mutatie die de controle
weghaalt was dus per constructie niet te betrappen -- precies de vorm die dit project "een belofte
zonder iets dat hem waarmaakt" noemt, een laag hoger dan de bevinding die hij moest repareren.

Toegevoegd: `test_een_geweigerde_inhoud_is_een_EIGEN_fout_en_geen_storing` plus de tegenrichting
`test_een_ANDERE_reden_met_lege_inhoud_blijft_een_gewone_storing` -- zonder die tweede zou "elke
`finish_reason` met lege inhoud is een weigering" een geldige implementatie zijn, en dan valt een
afgekapt antwoord (`length`) niet meer door naar de volgende schakel terwijl dat juist wel hoort.
Beide zijn in beide richtingen gemuteerd (CF1, CF2).

## Mutatiebewijs: 21 mutaties, alle 21 betrapt

Ronde 1 had elf mutaties waarvan VIER ongeldig, en de oorzaak is leerzaam: drie ankers kwamen twee
keer voor omdat `generate` en `stream` dezelfde regel `_REGISTRY.get_breaker(...)` hadden staan, en
`replace_anchor` weigert een niet-uniek anker. Dat is niet alleen een meetprobleem -- het is
hetzelfde duplicaat dat de kans geeft dat een latere wijziging maar EEN van de twee paden raakt.
Daarom staat die aanroep nu op een plek (`_breaker_voor`). De vierde ongeldige mutatie haalde
alleen een logregel weg en kon dus niets aantonen; die is vervangen door de DREMPEL onbereikbaar
te maken (`failure_threshold=10_000`), wat het gedrag raakt in plaats van de melding.

Ronde 2: 21 mutaties over vier bestanden, alle betrapt, met de tegenrichting per keer erbij.
Twee stelden zich eerst niet op scherp en dat is bewijs op zichzelf: de eerste tegenrichting op de
databasebewaker haalde EEN van de drie `self._repo`-aanroepen uit `opgeslagen_rijen` weg en bleef
groen -- terecht, want de methode raakt de repository dan nog steeds. Hij moest naar `toon`, de
enige methode met precies EEN aanroep. De volledige lijst staat in de featuredoc.

## Meting

```text
tests/unit/llm                                      104 passed
tests/unit/llm + {services,als,agents,security} + ssrf
                                                   1785 passed  (baseline 1724, 0 nieuwe failures)
tests/architecture (drie geraakte bewakers)           6 passed
mutatiebewijs (21 mutaties, 4 bestanden)             21/21 BETRAPT, werkboom daarna schoon

ruff src/ tests/          All checks passed!
scripts/run_mypy_audit    Total errors: 0  (baseline 0)
python -m pyright         0 errors, 35 warnings
check_any_gate            7110 = 7110
validate_feature_docs     exit 0 (711 van 712)
agent_runtime             Ce 240, infra 105, auth 17 (gelijk aan BE-LLM-004)
```

**Twee getallen in een eerdere versie van deze paragraaf waren onjuist en zijn hierboven
vervangen.** Er stond "tests/unit/llm 107 passed" en daaronder 1783 voor de bredere selectie; bij
het namaken van de meting kwam `tests/unit/llm` op 104 (102 voor de twee tests van vandaag) en
bleek 1783 de GECOMBINEERDE selectie inclusief `tests/unit/llm` te zijn, niet de bredere alleen.
Het verschil verandert geen conclusie, maar een getal dat niemand kan namaken hoort hier niet te
staan -- en het namaken kostte een minuut.

## Openstaand -- bewust niet in deze knip

1. **De breaker meet bereikbaarheid, niet bruikbaarheid.** Een eindpunt dat snel met HTTP 200 en
   onbruikbare JSON antwoordt, geldt als gezond. Dat is een echte grens en de scherpste opmerking
   uit de Devil's Advocate-secties; een antwoordkwaliteitsoordeel in een circuit breaker is een
   eigen ontwerp en geen bijvangst.
2. **Er is geen METRIEK op doorval en open circuits, alleen logregels.** Zonder teller draait een
   klant over zes maanden permanent op zijn reserveprovider terwijl het dashboard groen staat.
   `breaker_toestanden()` is het venster; de Prometheus-tellers uit ADR-026 par. 1.2.1 (
   `..._provider_failures_total`, `..._circuit_open_total`) bestaan alleen in de twin-stapel.
   Dat hoort bij de knip die ook het kostenplafond aansluit.
3. **`organism_registry` bewaart agent-exemplaren op een sleutel zonder tenant** -- de tweede
   bevinding uit BE-LLM-004, nog steeds open, met eigen brief.
