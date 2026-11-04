# Review: BE-LLM-002 -- Provider-agnostische LLM-laag

**STATUS: APPROVED**
**Goedgekeurd door:** Rakesh, na escalatie -- NIET door Gate 2. Zie de sectie hieronder.
**Datum:** 2026-09-20
**Branch:** `develop` (ongecommit op het moment van schrijven)
**Reviewers:** code-reviewer en quality-reviewer (Gate 2), drie rondes

---

## Wie hier precies heeft goedgekeurd -- lees dit voor je verder bouwt

**GEEN REVIEWER heeft het eindresultaat goedgekeurd.** Drie reviewrondes gaven alle drie
CHANGES_REQUESTED. Alle bevindingen zijn nagemeten door de auteur -- allemaal bevestigd -- en
gerepareerd, met een meting per reparatie. Daarna is er bewust GEEN vierde ronde gedraaid.

`.claude/rules/quality-gates.md` schrijft voor: "BLOCKED after 2 attempts -> escalate to
Rakesh, stop." Dat is gebeurd: de auteur heeft de reviewlus gestopt, de stand voorgelegd, en
Rakesh heeft op 2026-09-20 besloten dat het naar `develop` mag. De APPROVED hierboven is dus
ZIJN besluit na escalatie, niet het oordeel van twee reviewers.

Dat onderscheid staat hier omdat het later verschil maakt. Wie dit document aantreft en denkt
"dit is door Gate 2 heen gekomen", leest het verkeerd. Wat er staat is: drie rondes vonden
echte defecten, die zijn alle dicht, de poorten staan groen, en de eigenaar heeft het restrisico
aanvaard met de openstaande punten onderaan dit document voor ogen.

---

## Ronde 1 -- beide reviewers: CHANGES_REQUESTED

Vier HIGH, allemaal door de auteur nagemeten en bevestigd:

| # | Bevinding | Nameting auteur |
|---|---|---|
| H1 | `LLMService.__init__` vangt `ValueError` en valt buiten productie terug op de MockProvider, dus een onbekende providernaam werd STIL een namaakmodel | `LLMService(provider="moonshot", ...)` gaf provider `mock` |
| H2 | `content: null` passeerde als geslaagd; `usage` als tekst gaf een ongevangen `AttributeError` | `content = None`, tokens 0; `AttributeError` bevestigd |
| H3 | Het streampad brak stil op `data:` zonder spatie en was volledig ongetest | stroom leverde `[]` op, zonder fout of log |
| H4 | Geen adresvalidatie: `http://` met bearer, kaal metadata-adres geaccepteerd | beide bevestigd |

Plus een terechte tik: een WHY-comment beweerde dat `provider_name` in de ADR-019-auditketen en
in metrics belandt. Nagemeten en onjuist -- er zijn drie lezers en geen daarvan schrijft een
auditrecord.

**De belangrijkste les van deze ronde:** de test die H1 had moeten vangen stond op de FABRIEK,
terwijl de fout een laag hoger werd opgegeten. Een test die zijn eigen producent verzint,
bewijst niets.

---

## Ronde 2 -- beide reviewers: alle ronde-1-reparaties werken; twee nieuwe MEDIUM

De quality-reviewer verifieerde alle zeven punten een voor een en vond ze weg. Nieuw:

- **M-1:** de auteur had in ronde 1 `exc_info=True` toegevoegd (terecht, er was anders geen
  bewijsmateriaal bij een falend klanteindpunt). Gevolg: met inloggegevens in `base_url` komt
  het wachtwoord via de traceback in het log, terwijl de docstring belooft dat de sleutel niet
  lekt. Een onware veiligheidsclaim.
- **M-2:** de weerlegde auditketen-claim was in het providerbestand gecorrigeerd maar niet in
  de fabriek -- twee bestanden uit dezelfde wijziging die elkaar tegenspreken.

Plus drie LOW, waaronder een assertie die per constructie niet rood kon worden.

---

## Ronde 3 -- code-reviewer: twee nieuwe HIGH

| # | Bevinding | Nameting auteur |
|---|---|---|
| B1 | Ronde 2 sloot `user:pass@host`, maar niet `?key=<sleutel>`. Die belandt via dezelfde weg in het log, EN het adres wordt stil kapot: `/chat/completions` komt achter de query | `https://host/v1?key=x` -> `https://host/v1?key=x/chat/completions`, sleutel in het log |
| B2 | `src/core/api/v1/cva/dependencies.py` vangt alleen `ValueError`, dus het nieuwe fouttype gaf een kale HTTP 500 in plaats van de 503 met "Check LLM_PROVIDER and LLM_MODEL" | bevestigd door de code te lezen (een async functie, dus een snelle aanroep bewijst niets) |

Plus MEDIUM: de health-probe meldde `config_error: False` en stuurde de beheerder naar zijn
sleutel terwijl zijn providernaam fout stond. En: `base.py` viel buiten het bereik van de
architectuurbewaker, terwijl een default op `LLMConfig` daar in een klap voor elke provider
geldt.

**B2 is de scherpste van de hele reeks.** Het nieuwe fouttype maakte de fout luider en op de
enige plek waar een mens hem ziet tegelijk dommer. Dat is een regressie die door deze wijziging
is veroorzaakt.

---

## Wat er na ronde 3 is gerepareerd, met de meting

```
B1 query geweigerd -> 'base_url' mag geen query of fragment bevatten...
B2 status: 503 | LLM service not configured. Check LLM_PROVIDER and L...
B3 probe: {'available': False, 'config_error': True}
```

De bewaker dekt nu `openai_compatible.py`, `factory.py` en `base.py`, met mutatiebewijs per
toegevoegd bestand. Het featuredocument is gecorrigeerd op twee getallen die niet klopten (41
tests was 45; "1772 tests" was niet reproduceerbaar zonder het commando, dat staat er nu bij).

**Poorten na de laatste reparatie:** 1793 tests groen, ruff schoon, mypy 0 (baseline 0),
pyright 0 errors.

---

## Na de drie rondes -- uitputtend natrekken op verzoek van Rakesh

Opdracht: elke bevinding zelf nameten, geen aannames, internet verplicht. Dat leverde EEN
defect op dat geen enkele reviewronde had gezien, en het raakte de kernbelofte:

**Een aanroeper kon geen eigen veld meesturen; het werd stil weggegooid.** Gemeten: met
`max_completion_tokens=100` ging er een verzoek de deur uit met alleen `max_tokens: 1000`.
OpenAI heeft `max_tokens` afgeschaft en de redeneermodellen weigeren hem, dus "werkt met elk
OpenAI-compatibel eindpunt" was onwaar voor een groeiende klasse modellen. Gerepareerd met vier
tests. Deze reparatie is NIET door een reviewer gezien.

**De SSRF-inschatting is zwaarder geworden.** Extern nagezocht: de positie die dit document
innam -- "de hostbegrenzing hoort bij de aannamekant van fase 2, vastgelegd in proza" -- is
precies de positie waarin LiteLLM stond voor CVE-2026-59823 en CVE-2026-84377. Bij die tweede
stuurt de proxy de opgeslagen sleutels van de operator mee naar een bestemming die de gebruiker
kiest. Wat WEL geruststelt en door mij is gemeten: `base_url` heeft vandaag exact een bron,
`os.getenv("LLM_BASE_URL")` op `factory.py:227`. Er is geen pad van buiten. Besluit: de bewaker
hierop wordt de eerste stap van fase 2, samen met de code die hij beschermt.

**Vier beweringen uit de reviews, nu door de auteur zelf gemeten in plaats van overgenomen:**

| Bewering | Meting | Uitkomst |
|---|---|---|
| `deepseek.py` houdt de `content: null`-faalvorm | de provider echt gedraaid | `content = None` in een veld dat `str` heet |
| De tweede LLM-stapel valt stil terug op mock | code gelezen | terugval na alleen een `logger.error` |
| `_PROVIDER_DISPLAY` geeft `null` | tabel uitgelezen | kent drie namen; onbekend -> `None` |
| Het CVA-streampad heeft geen tijdsgrens | gezocht op `wait_for`/`timeout` | geen enkele |

**Nieuw en door niemand genoemd:** `focus_suggestion_service.py` en
`workflow_generator_service.py` hebben `https://api.deepseek.com` hardgecodeerd. Dat is lock-in
buiten het bereik van de bewaker, die alleen naar de agnostische laag kijkt.

**Externe bevestiging:** de SSE-specificatie van WHATWG stelt dat `data:{...}` en `data: {...}`
allebei geldig zijn en hetzelfde moeten opleveren. Parsers die een spatie eisen en regels stil
laten vallen zijn in 2026 als bug gemeld tegen meerdere producten -- de gerepareerde faalvorm
is dus een bekende klasse en geen toeval.

---

## Wat BEWUST niet is opgelost, en wat de reviewers daarover zeggen

Deze punten staan in het featuredocument onder "Wat dit NIET doet". Ze zijn genoemd door de
reviewers en niet weggepoetst:

1. `providers/deepseek.py` HOUDT de `content: null`-faalvorm die hier is gerepareerd. Wie
   `LLM_PROVIDER=deepseek` zet, krijgt het oude gedrag terug.
2. De gesloten leverancierstabellen (`_PROVIDER_DISPLAY` -> `null`, `cost_tracker` -> 0 euro)
   hebben geen falende test en geen gedateerde guard. De code-reviewer noemt dat expliciet
   "guard-theater"-risico: groen op het bestand waar niemand een adres zou zetten, niets op de
   plekken waar leveranciersnamen wel zijn ingebakken.
3. De SSRF-begrenzing ligt bij de aannamekant (fase 2) en wordt vandaag door niets afgedwongen
   behalve proza. Zodra `base_url` uit een tenantkolom komt, wordt geen enkele test rood als
   `SSRFProtector.validate_url` ontbreekt.
4. `stream()` heeft geen wandklokgrens buiten het piloot-pad.

**Het advies van de reviewer dat de auteur onderschrijft:** de titel "provider-agnostische
laag" is waar op machineniveau en niet op klantniveau. Wie dit leest als "klanten kunnen nu hun
eigen provider opgeven", leest het verkeerd -- dat is fase 2.
