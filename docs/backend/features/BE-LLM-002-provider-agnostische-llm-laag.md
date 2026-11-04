# BE-LLM-002 -- Provider-agnostische LLM-laag

**Datum:** 2026-09-20
**Branch:** `develop`
**ADR:** ADR-026 (LLM-failoverketen), ADR-036 (acceptatieketen stap 6/7)
**Plan:** "Lokaal-eerst LLM-platform: Ollama als bodem, elke andere provider als configuratie"
(goedgekeurd door Rakesh, 2026-09-20)

---

## Waarom

Besluit Rakesh, 2026-09-20: geen vendor lock-in. Klanten geven bij de inrichting hun eigen
eindpunt, model en sleutel op.

Dat kon niet. De keuze zat in de omgevingsvariabelen van de MACHINE: `LLMService()` wordt op
ongeveer twintig plekken aangeroepen zonder tenant, dus het hele platform praat met wie er bij
het uitrollen is ingevuld. De aanleiding was een gemeten storing:

```
.env: LLM_PROVIDER=moonshot
-> "Unknown provider: moonshot. Available: ollama, deepseek, gemini, mock"
-> Falling back to MockProvider
```

Een namaakmodel geeft plausibele tekst terug. Stap 6 en 7 van de acceptatieketen lopen per
ontwerp via het taalmodel, dus een demo daarvan zou verzonnen tekst hebben opgeleverd die er
werkend uitziet -- de faalvorm uit ADR-036 paragraaf 1.

---

## Wat er is gebouwd

### 1. `OpenAICompatibleProvider` (`src/core/services/llm/providers/openai_compatible.py`)

Praat met elk eindpunt dat het OpenAI-chatprotocol aanbiedt. De markt spreekt inmiddels
grotendeels hetzelfde: DeepSeek, Moonshot/Kimi, OpenAI, Groq, Mistral, vLLM, LM Studio, Ollama
(op zijn v1-ingang) en Gemini via de compatibiliteitslaag van Google. Een nieuwe leverancier
kost daarmee een regel configuratie en geen klasse.

Er staat met opzet GEEN adres van een leverancier in dat bestand; `base_url` komt van de
aanroeper.

### 2. `ProviderFactory.create()` -- een onbekende naam MET adres is geldig

Een naam die wij niet kennen levert de generieke provider op, met die naam als label. Een
onbekende naam ZONDER adres faalt met een melding die de uitweg noemt.

### 3. De configuratiefout komt bij de mens aan

`src/core/api/v1/cva/dependencies.py` vangt het nieuwe fouttype naast `ValueError`, op twee
plekken. Zonder die regel gaf de dependency een kale HTTP 500 in plaats van de 503 met
"Check LLM_PROVIDER and LLM_MODEL", en meldde de health-probe `config_error: False` --
waarmee de beheerder naar zijn sleutel werd gestuurd terwijl zijn providernaam fout stond.
Gemeten bij Gate 2, ronde 3; de fout was luider geworden en tegelijk dommer.

### 4. Eigen velden van de aanroeper gaan mee naar het eindpunt

Gevonden bij het uitputtend natrekken NA de drie reviewrondes, en gemeten: een aanroeper die
`max_completion_tokens=100` meegaf, kreeg een verzoek met alleen `max_tokens: 1000` -- zijn veld
werd zonder melding weggegooid. OpenAI heeft `max_tokens` afgeschaft en de redeneermodellen
(o-serie, GPT-5) WEIGEREN dat veld. De belofte "werkt met elk OpenAI-compatibel eindpunt" was
daarmee onwaar voor een groeiende klasse modellen.

Velden uit `extra_params` gaan nu mee en mogen de onze overschrijven; `None` verwijdert een
veld (nodig, want `max_tokens` en `max_completion_tokens` samen geven een weigering).
`messages` en `stream` liggen vast -- dat is de vorm van het verzoek, geen instelling.

### 5. `LLMProviderUnknownError` (`src/core/services/llm/base.py`)

Bewust GEEN `ValueError`. `LLMService.__init__` vangt `ValueError` en valt buiten productie
terug op de MockProvider -- bedoeld als gemak wanneer er geen sleutel is. Een onbekende
providerNAAM is iets anders dan een ontbrekende sleutel, en stil een namaakmodel gebruiken
verbergt hem.

---

## Contract

| Veld | Verplicht | Toelichting |
|---|---|---|
| `base_url` | ja | Schema `http` of `https`, met host. Al het andere wordt geweigerd |
| `model` | ja | De modelnaam zoals die leverancier hem noemt |
| `api_key` | nee | Weggelaten = geen Authorization-kop (lokale eindpunten) |
| `extra_params[provider_label]` | nee | De naam in de logregel en het API-veld; anders de host |

`provider_name` wordt opgeschoond tot `[a-z0-9._-]`, maximaal 32 tekens.

---

## Metingen

Alle onderstaande zijn gedraaid op 2026-09-20, niet afgeleid.

| Wat | Uitkomst |
|---|---|
| Onbekende naam via `LLMService` | `LLMProviderUnknownError` (was: provider `mock`) |
| Onbekende naam + `base_url`, live tegen Ollama | `OpenAICompatibleProvider`, naam `mijn-eigen-llm-leverancier`, echt antwoord, 170 tokens |
| `content: null` | `LLMServiceError` (was: `content = None`, 0 tokens) |
| `usage` als tekst | geen ongevangen fout, tokens 0 (was: ongevangen `AttributeError`) |
| SSE zonder spatie na `data:` | `['hallo']` (was: `[]`, stil) |
| `file:`, `javascript:`, adres zonder schema | geweigerd |
| `http://127.0.0.1:11434/v1` | toegestaan -- het lokale model is de bodem |
| Label met regeleinde | `deepseekvervalst`, geen tweede logregel mogelijk |
| `max_completion_tokens` meegeven | komt aan bij het eindpunt (was: stil weggegooid) |
| `providers/deepseek.py` met `content: null` | geeft `None` terug -- de oude faalvorm, door hem te DRAAIEN gemeten en niet door te tellen |
| Bronnen van `base_url` in de LLM-laag | exact een: `os.getenv("LLM_BASE_URL")` op `factory.py:227` |

**Poorten**, met het commando erbij zodat het getal navolgbaar is:

```
pytest tests/unit/llm tests/unit/test_llm_service.py tests/unit/test_llm_service_coverage.py        tests/unit/test_sp_d01_llm_fix.py tests/unit/als tests/unit/api/v1/cva tests/architecture -n 4
ruff check src/
python scripts/run_mypy_audit.py --fail-on-increase
python -m pyright
```

---

## Bewaakt door

- `tests/unit/llm/test_openai_compatible_provider.py` -- 50 tests, inclusief de weg via
  `LLMService` (niet alleen de fabriek), de foutvertaling 401/403/429/500/timeout, het
  stroompad in beide SSE-schrijfwijzen, dat de sleutel niet in een foutmelding komt, en dat
  een eigen veld van de aanroeper werkelijk de deur uit gaat.
- `tests/unit/api/v1/cva/test_llm_configuratiefout_bereikt_de_gebruiker.py` -- 2 tests: de
  configuratiefout komt als 503 met een bruikbare melding bij de gebruiker, en de health-probe
  noemt hem een configuratiefout.
- `tests/architecture/test_de_generieke_provider_kent_geen_leverancier.py` -- 3 tests: geen
  leveranciersadres in `openai_compatible.py`, `factory.py` en `base.py`. Mutatiegetest in vijf
  richtingen plus de tegenrichting.

---

## Wat dit NIET doet -- en dat hoort hier te staan

1. **De bestaande providers gaan nog niet door deze laag.** `deepseek`, `ollama`, `gemini` en
   `mock` houden hun eigen klasse. De generieke klasse bedient vandaag alleen namen die wij
   niet kennen. Er is daarmee een tweede implementatie van hetzelfde protocol
   (`providers/deepseek.py`), en die kan apart verouderen. Het samenvoegen is een eigen stap.
2. **Er is nog geen tenant-dimensie.** ADR-026 par. 1.2.1 beschrijft een keten per tenant
   (`tenant.llm_chain`, circuit breaker, kostenplafond); dat veld bestaat niet. Deze wijziging
   maakt "de uitroller kan ook een onbekende naam invullen" mogelijk, nog niet "de klant geeft
   zijn eigen eindpunt op". Dat is fase 2 van het plan.
3. **De host-/netwerkbegrenzing tegen SSRF ligt niet hier.** Deze laag eist http/https en
   verder niets, want een blokkade op private adressen zou `127.0.0.1` uitsluiten en daarmee
   het lokale model. Zodra `base_url` uit tenantconfiguratie of een formulier komt, hoort
   `src/core/security/ssrf_protection.py` (`SSRFProtector.validate_url`) ervoor, zoals
   `src/core/activepieces/client.py::_check_egress` het al doet voor klant-URL's.
4. **Gesloten leverancierstabellen elders zijn niet meegenomen.**
   `services/cva_service.py:394` (`_PROVIDER_DISPLAY`) geeft `None` voor een naam buiten zijn
   tabel, en `learning/cost/cost_tracker.py:178` rekent zo'n naam op 0 euro. Beide vallen
   buiten deze wijziging; gemeld door de Gate 2-review.
5. **De tweede LLM-stapel (`src/core/llm/`) heeft dezelfde faalvorm** en is niet aangeraakt:
   `provider_factory.py:66-73` valt bij een onbekende naam stil terug op mock. Die stapel
   bedient de copilot.
6. **`providers/deepseek.py` HOUDT de faalvorm die hier is gerepareerd.** Gemeten: dat bestand
   heeft geen enkele controle op `content`, dus `content: null` passeert daar nog steeds als
   geslaagd antwoord. Wie `LLM_PROVIDER=deepseek` zet, krijgt het oude gedrag. Dat is het
   concrete gevolg van punt 1 hierboven en de reden dat samenvoegen geen cosmetische klus is.
7. **Geen `get_embeddings`.** `services/llm/cache.py` roept die methode aan binnen
   `except Exception: pass`, dus de semantische L3-cache doet stil niets. Geen regressie --
   geen enkele provider in `providers/` implementeert hem -- maar de nieuwe klasse wordt wel
   de meest waarschijnlijke bewoner van dat pad.
8. **`stream()` heeft geen wandklokgrens.** Het piloot-pad begrenst via
   `budget.timeout_seconds`; het CVA-streampad niet. Een eindpunt dat heel traag druppelt
   houdt daar een worker bezig. Benoemd in de docstring, niet opgelost.

---

## Trainingssamenvatting

- Actor: de inrichter (AI-engineer of adviseur) die het platform voor een omgeving configureert.
- Voorwaarde: er is een taalmodel-eindpunt beschikbaar dat het OpenAI-chatprotocol spreekt, en
  de inrichter kent het adres, de modelnaam en eventueel een sleutel.
- Actie: hij zet `LLM_PROVIDER` op een naam naar keuze en geeft `LLM_BASE_URL` plus `LLM_MODEL`
  mee. Voor een lokaal model (Ollama) blijft de sleutel leeg.
- Systeemreactie: de fabriek herkent de naam niet als eigen klasse, ziet dat er een adres bij
  zit, en levert de generieke OpenAI-compatibele provider. De opgegeven naam wordt het label dat
  in de logregel en in het API-veld verschijnt.
- Succesrespons: de agent krijgt echte antwoorden van het gekozen eindpunt; `provider_name`
  toont de naam die de inrichter koos.
- Foutrespons: een onbekende naam ZONDER adres geeft `LLMProviderUnknownError`, en op de
  CVA-route een HTTP 503 met "LLM service not configured. Check LLM_PROVIDER and LLM_MODEL".
  Een adres zonder schema, met inloggegevens, met een query of met een fragment wordt geweigerd
  met de reden erbij. Er volgt GEEN stille terugval op een namaakmodel.
- Uitzonderingen: een eindpunt dat zijn versie in de query draagt (Azure OpenAI) wordt bewust
  niet ondersteund -- die vorm zet het pad na de query en past niet op deze klasse.

---

## Review

`docs/backend/review/review-BE-LLM-002.md`
