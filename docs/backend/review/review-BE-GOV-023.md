STATUS: APPROVED WITH MINOR GAPS
Een reviewronde door de code-reviewer: CHANGES_REQUESTED met drie HIGH's, alle drie zelf
nagemeten en gerepareerd, met mutatiebewijs in beide richtingen. De quality-reviewer heeft
GEEN uitspraak gedaan -- zijn sessie liep twee keer op een API-limiet. Gate 2 is dus HALF
uitgevoerd, en de openstaande punten staan onderaan.

# Review BE-GOV-023 -- InputGuard, een inhoudswachter op twee deuren voor vrije tekst

Datum:     2026-09-22
Spec:      `docs/backend/features/BE-GOV-023-inhoudswachter-op-vrije-tekst.md`
Reviewers: code-reviewer (afgerond), quality-reviewer (twee keer afgebroken op een API-limiet)
Basis:     develop, HEAD 016a836c

---

## Eerst dit: wat er NIET is gebeurd

De quality-reviewer is twee keer gestrand voordat hij een uitspraak deed. Zijn vragenlijst
stond klaar (holle asserties, `lru_cache`-gedrag, ReDoS op lange invoer, OWASP, non-ASCII,
de eigen Gate 3-metingen) en is dus ONGETOETST door een onafhankelijke partij. Ik heb die
punten zelf nagelopen waar ik kon, maar dat is niet hetzelfde: een verse subagent heeft geen
gespreksgeschiedenis en dus geen aannames, en dat is precies waarvoor Gate 2 bestaat.

Bovendien heb ik tijdens zijn tweede poging de werkboom herschreven (`input_guard.py` ging van
231 naar 397 regels). Dat maakte zijn review een bewegend doel en het is mijn fout -- ik had het
een uur eerder zelf nog opgeschreven als iets dat je niet doet.

---

## De drie HIGH's, elk zelf nagemeten voor ik iets aanraakte

### HIGH-1 -- de wachter was te omzeilen door de tekst een JSON-veld verderop te zetten

De chatdeur beoordeelde `message` en niet `context`. Zelf nagemeten:

```text
message   <class 'str'>          metadata=[MinLen(1), MaxLen(2000)]
context   dict[str, typing.Any]  metadata=[]        <-- geen lengtegrens
```

`context` komt rechtstreeks van de client, gaat via `_augment_context` naar het taalmodel EN
naar `proposal.context_snapshot`, dus naar de Council en daarmee de auditketen. Een BSN in
`{"notitie": "..."}` kwam er dus ongehinderd langs, in dezelfde HTTP-aanvraag.

**Gedaan:** `beoordeel({"message": message, "context": context}, ...)`. Plus een test die het
geval vastlegt, en een mutatie die `context` weer weghaalt -> rood.

### HIGH-2 -- hij blokkeerde het VERKEERDE: zes van de zes gewone teksten

Zelf nagemeten met de echte detector:

```text
ts=1726937461123 duurde te lang              -> GEWEIGERD
Version 1.2.3 build 20260922145501           -> GEWEIGERD
order 9780306406157 ontbreekt                -> GEWEIGERD
Open ticket 123456782 graag                  -> GEWEIGERD
run_id 1726937461123 is vastgelopen          -> GEWEIGERD
Het factuurnummer is 2026-0000-1234-5678     -> GEWEIGERD
```

En 9-cijferige nummers: **1823 van 20.000 (9,12%)** halen de elfproef.

Twee oorzaken. `credit_card` stond niet in `_CHECKSUM_VALIDATORS`, terwijl het patroon elke
reeks van 13-20 cijfers is -- een defect volgens het contract dat `gdpr_enforcer` zelf
opschrijft, niet een beleidskeuze. En de elfproef alleen is te zwak om op te blokkeren in een
systeem vol ticketnummers.

**Gedaan:** een Luhn-validator in `gdpr_enforcer` (root cause, raakt ook de PrivacyOfficer, dus
met rood-bewijs vooraf en de bestaande test A->B omgezet -- die gebruikte `1234-5678-9012-3456`
en legde daarmee het defect vast). En `bsn` blokkeert alleen nog met een contextwoord.

### HIGH-3 -- mijn verdediging van fail-closed hield geen steek

Ik schreef "geen I/O, dus bijna geen faaloppervlak". De coercie `int(t)` voor de tenantlijst
stond BUITEN de afscherming, die alleen `OSError`/`YAMLError` ving -- en het commentaar in de
YAML nodigde zelf uit tot de vorm die dat breekt (`- 42   # reden`). Zelf nagemeten met
`- "42 (Acme, 2026-09-22)"`: **zes `ValueError`s bij zes aanroepen**, want `lru_cache` bewaart
een uitzondering niet. Gevolg: elke aanvraag geweigerd voor alle tenants, plus een
schijfleesactie en een traceback per verzoek.

**Gedaan:** alles binnen de `try`, terugval GECACHET (teruggeven in plaats van gooien). Plus een
test die eist dat `cache_info().misses` niet oploopt, en een mutatie die de `except` weer
versmalt -> rood.

## De MEDIUM's

| # | Bevinding | Gedaan |
|---|---|---|
| M4 | De AST-bewaker blijft groen bij NEUTRALISEREN (aanroep laten staan, weigering uitzetten). Mijn twaalf mutaties toetsten alleen VERWIJDEREN. En op de agentdeur was er geen enkele gedragstest | vier neutraliseer-mutaties toegevoegd (alle vier betrapt), en `tests/unit/als/test_de_agentdeur_beoordeelt_de_inhoud.py` is nieuw. De bewaker is eerlijk herbenoemd tot een wiring-toets |
| M5 | Geneste waarden op het agentpad: `{"employees": [{"bsn": ...}]}` glipte erlangs, en `params` is `json.loads()` van modeloutput. Die payload gaat naar `hitl_tickets.payload`, dat als "LIVE en RAUW" staat gedocumenteerd | de HELE `params` gaat erin; `detect_pii` doorzoekt geneste structuren zelf al, dus de eerste versie gooide capaciteit weg |
| M6 | Het regelbestand kan de vloer alleen VERBREDEN, niet versmallen -- terwijl mijn docstring beweerde dat het onderscheid daar te wijzigen was. Een compliance-document dat inert is, beeindigt een onderzoek | de onwaarheid staat gecorrigeerd in de YAML, de module en de featuredoc, met het gevolg erbij: een tenant die IBAN's wil toestaan kan alleen de HELE wachter uitzetten |
| M7 | Nog ZES ingangen waar vrije tekst een taalmodel of de Council bereikt. "Elke deur" in mijn testnaam was onwaar | de bewaker heet nu `test_deuren_voor_vrije_tekst_hebben_een_wachter.py` en draagt een gedateerde lijst met de zes, plus een staleness-test. Drie zelf nagemeten, drie overgenomen -- en dat staat er zo bij |
| M8 | De weigering was hardgecodeerd Nederlands, terwijl `language` `Literal["nl","en"]` is | `reden(taal)` is tweetalig, met een test per taal |

## De LOW's

- **Mijn uitleg bij de randbewaker was onwaar in de RICHTING.** Ik schreef dat de opsomming een
  rand mist; gemeten klopt het omgekeerde: hij telt te VEEL, want regel 8 (`factory.py ->
  prana_guard`) is inmiddels een `importlib.import_module` en dus onzichtbaar voor de scanner.
  Gecorrigeerd, met de meting.
- **De importlib-uitweg niet genoemd.** Dat patroon staat op DRIE plekken in deze codebase, elke
  keer met een comment dat naar diezelfde test wijst. Ik gebruik hem niet -- een echte
  afhankelijkheid voor de meter verstoppen is erger dan de +2 betalen -- maar hij hoort genoemd
  en verworpen, anders denkt de volgende lezer dat ik hem niet kende. Met de eerlijke
  waarschuwing erbij: de werkelijke governance-afhankelijkheid is hoger dan negen.
- **De import op de chatdeur stond buiten elke afscherming** -> een kapotte module gaf een 500
  in plaats van een weigering. Nu binnen een `try`.
- **De architectuurbewaker las paden relatief aan de werkmap** -> nu geankerd op de repo-wortel.

## Wat ik over mijn EIGEN werk vond tijdens het repareren

1. **Mijn verse staleness-bewaker toetste tekst waar structuur hoort.** `WACHTER in bron`
   matchte het woord "beoordeeld" in een Nederlandse foutmelding, waardoor hij beweerde dat
   `agentic_flow_endpoints.py` al een wachter had. Dat is precies de faalvorm die
   `quality-gates.md` beschrijft, in een bewaker die ik net had geschreven om hem te voorkomen.
   Gevonden doordat de test ROOD werd -- hij kan dus tenminste falen. Nu op de AST.
2. **Twee mutaties moesten worden herschreven.** Een selector bestond niet (`TestDetectPII` i.p.v.
   `TestDetectPii`) en het harnas meldde correct "de testrunner heeft GEEN tests uitgevoerd" in
   plaats van groen. De andere zette de coercie binnen de `try` en was daarmee geen reproductie
   van de bug; in de realistische vorm (de `except` weer versmallen) werd hij wel betrapt.
3. **Een test van mij viel op een bestaande patroonbeperking:** `iban_NL91ABNA0417164300` matcht
   niet, want `_` is een woordteken en er is geen `\b`. Niet gerepareerd (raakt de PrivacyOfficer
   en `redact_pii`), wel vastgelegd.

## Meting

```text
tests/unit/governance/test_input_guard.py              30 passed
tests/unit/copilot/test_service.py                     24 passed
tests/unit/als/test_de_agentdeur_beoordeelt_de_inhoud  5 passed   (nieuw -- bestond niet)
tests/architecture/test_deuren_..._wachter.py           4 passed
tests/unit/governance/test_gdpr_enforcer.py            30 passed  (incl. 4 negatieve Luhn-gevallen)

ruff src/ tests/ scripts/                              All checks passed!
scripts/run_mypy_audit.py                              Total errors: 0
python -m pyright                                      0 errors, 35 warnings
scripts/check_any_gate.py --mode acknowledged          Baseline 7111; gemeten 7111
```

**Mutatiebewijs: 20 mutaties, alle betrapt**, tegenrichting groen. Inclusief de vier
NEUTRALISEER-mutaties die ronde 1 helemaal miste, de vier gaten die Gate 2 aanwees, en de zes
uit de eerste reeks.

**Pre-existente rode tests, nagemeten en NIET van deze wijziging:** `tests/security/` geeft 20
failures en 4 errors, en exact dezelfde 20 en 4 op HEAD `016a836c` zonder mijn werk (gemeten in
een verse worktree). Die map zit niet in de testpoort, dus ze draaien nergens blokkerend --
zelfde categorie als `tests/test_tool_broker_local.py`. Eigen brief.

## Openstaand

1. **De quality-review is niet gedaan.** Dat is het grootste openstaande punt van deze knip.
2. **Zes ingangen voor vrije tekst hebben geen wachter**, met `agentic_flow_endpoints.py` als
   scherpste: die zet rauwe gebruikerstekst in het Council-register.
3. **De wachter vindt geen proza.** Burn-out, salaris, adres, zwangerschap gaan er alle vier
   door -- gemeten. Daarvoor is de redenerende laag nodig (alleen escaleren).
4. **Een tenant kan `iban` niet los toestaan**, alleen de hele wachter uitzetten.
5. **`context` heeft geen lengtegrens in het schema.** De wachter kapt zijn eigen werk af op
   20.000 tekens, maar het veld gaat ongebreideld naar het taalmodel.
6. **De dagteller op HIGH-goedkeuringen** (het SCHUFA-punt) staat nog open.
