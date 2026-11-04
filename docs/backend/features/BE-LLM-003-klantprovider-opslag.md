# BE-LLM-003 -- Klantprovider-opslag: eigen eindpunt, eigen sleutel, per tenant

**Status:** geimplementeerd (fase 2a)
**Datum:** 2026-09-20
**Sprint-dag-brief:** `docs/agent-briefs/generated/2026-09-20-sprint-dag-fase2a-klantprovider-opslag.md`
**Bouwt op:** BE-LLM-002 (provider-agnostische LLM-laag)
**ADR's:** ADR-026 (failoverketen), ADR-005 (tenant_id NOT NULL + RLS), ADR-033 (3-laags router),
ADR-036 B8 (inrichting is dienstverlening, geen zelfbediening)

---

## Waarom

BE-LLM-002 maakte de LLM-laag provider-agnostisch: elk OpenAI-compatibel eindpunt werkt. Maar het
adres van dat eindpunt had daarna nog exact EEN bron -- `os.getenv("LLM_BASE_URL")` in
`src/core/services/llm/factory.py:227`, gemeten. "De klant geeft zijn eigen provider op" was dus
nog niet waar; alleen "de uitroller kan ook een onbekende naam invullen".

Deze feature voegt de tenant-dimensie toe aan de OPSLAG. De resolutie (welke keten gebruikt een
aanroep werkelijk) is fase 2b en zit hier bewust niet in.

**Het productmodel dat dit ondersteunt (besluit Rakesh, 2026-09-20).** Ollama draait standaard
mee op onze eigen server. Een klant die niets opgeeft, draait daarmee volledig lokaal -- dat is
de verkoopbelofte "uw data blijft op uw server". Een klant die zijn eigen provider wil, krijgt
die, maar dan expliciet aangezet.

---

## Waarom dit de gevaarlijkste stap van het hele traject is

Zodra een gebruiker het adres bepaalt waar onze server naartoe belt, met onze opgeslagen sleutel
eraan, staat het systeem in precies de positie waarin LiteLLM dit jaar twee keer is uitgebuit:

- **CVE-2026-59823** -- een genest configuratieveld kwam langs de adrescontrole heen.
- **CVE-2026-84377** -- de proxy stuurde de opgeslagen sleutels van de operator mee naar een
  adres dat de gebruiker koos.

Dat is geen theoretisch risico maar de gemeten faalvorm van het dichtstbijzijnde product met
dezelfde functie. De hele opzet hieronder is daarop gebouwd: EEN doorgang, met een
architectuurbewaker die rood wordt zodra er een tweede bijkomt.

---

## Wat er is gebouwd

### 1. Versleuteling met een sleutel per tenant

`src/core/security/tenant_secret_encryption.py`, nieuw en klein. Drie dingen anders dan het
bestaande `token_encryption.py`:

| Eigenschap | Bestaand object | Hier |
|---|---|---|
| Ontbrekende `MASTER_ENCRYPTION_KEY` | waarschuwing + proces-lokale terugvalsleutel | `HoofdsleutelOntbreekt`, harde fout |
| Sleutelscheiding | een afgeleide sleutel voor alles | een sleutel per tenant, via HKDF met `tenant_id` als context |
| Zout | `sha256(b"sanskritisetu_calendar_tokens")` | eigen domeinzout |

**Fail-closed is hier de kern, niet een detail.** Een terugvalsleutel maakt opgeslagen
klantsleutels onleesbaar zodra het proces herstart -- en onleesbaar tussen de gunicorn-workers
onderling. Voor een OAuth-token is dat vervelend; voor een sleutel die een klant ons heeft
gegeven is het stil gegevensverlies. Luidruchtig weigeren is het goede gedrag.

**Dit is geen zelfgebouwde cryptografie.** HKDF en Fernet komen allebei uit `cryptography` en
worden gebruikt waarvoor ze bedoeld zijn. Wat het NIET is: een vervanging voor een sleutelkluis.
De hoofdsleutel leeft in de omgeving, dus wie de server heeft, heeft de sleutels. Dat hoort in
het inrichtingsdossier te staan en niet weggeschreven te worden als "versleuteld, dus veilig".

### 2. De tabel

`tenant_llm_providers` (`src/core/models/tenant_llm_provider_models.py`, geregistreerd in
`src/core/database/import_all_models.py` -- anders is hij onzichtbaar voor autogenerate).

| Kolom | Vorm |
|---|---|
| `tenant_id` | Integer NOT NULL, FK `tenants.id`, ondelete CASCADE |
| `volgorde` | Integer NOT NULL -- de keten van ADR-026 is hier de sortering van |
| `naam` | String(64) |
| `base_url` | String(512) |
| `model` | String(128) |
| `api_key_encrypted` | Text, nullable (leeg voor een lokaal eindpunt) |
| `actief` | Boolean, default true |

Uniek op `(tenant_id, volgorde)`. Plus een nieuwe kolom op `tenants`:
`externe_providers_toegestaan`, Boolean, **default FALSE**. Een echte kolom en geen sleutel in
het bestaande `settings`-JSON: een veiligheidsschakelaar hoort typed en queryable te zijn en niet
stil te kunnen ontbreken.

**Eerlijk over RLS.** De migratie zet de policies volgens het bestaande patroon, maar ze doen
vandaag NIETS: de applicatie verbindt als eigenaar van de tabellen, en PostgreSQL past RLS niet
toe op de eigenaar (ADR-036 OP-151, gemeten). Ze werken zodra de rolwissel uit OP-154 landt. Het
expliciete `tenant_id`-filter op elke repositorymethode is dus niet een tweede laag maar de
ENIGE laag, en daarom niet optioneel.

### 3. De drie lagen, en waarom de grens ligt waar hij ligt

```
router (api/v1/admin/llm_providers_router.py)   <- HTTP, audit, statuscodes
  |  via dependencies.py (ADR-033-facade)
service (services/tenant_llm_provider_service.py)  <- BELEID: mag het? deugt het adres?
  |
repository (repositories/tenant_llm_provider_repository.py)  <- pure persistentie
```

De eerste versie zette de controles in de repository. `test_dsm_009_no_medium_backward.py` viel
daarop om: de DSM-indeling rekent repositories tot `infra` en `src/core/security` tot `auth`, en
infra mag niet van auth afhangen. Die regel wees iets echts aan -- opslag hoort niet te weten wat
een geldig adres is.

De tweede versie importeerde de beveiligingsmodules in de service. Toen vielen
`test_dsm017_runtime_deps_facade.py` en `test_dsm_008_reclassification.py` om:
`agent_runtime` heeft een budget van 16 auth-imports (werd 17) en een koppelingsplafond van 234
(werd 237). Het antwoord daarop is niet ophogen maar minder koppelen: alle afhankelijkheden komen
nu van de aanroeper, de imports staan onder `TYPE_CHECKING`, en de wiring gebeurt in de
API-laag. Dat is bovendien het patroon dat ADR-034 voorschrijft, en het maakt de klasse testbaar
zonder iets te patchen.

De derde correctie was kleiner en leerzaam: ook na die verplaatsing bleef
`test_fan_out_budget[core_api]` rood op 558 tegen een plafond van 557. Er was nog EEN paar over
-- het routerbestand kende `src.core.auth` zelf, alleen om `UserResponse` als annotatie te
gebruiken. `dependencies.py` her-exporteert dat symbool nu, en kende `auth` toch al.

### 4. De twee sloten, in deze volgorde

In `TenantLLMProviderService.configureer`, de enige doorgang:

1. **Mag deze tenant extern?** Staat `externe_providers_toegestaan` op FALSE, dan wordt een
   extern eindpunt geweigerd **bij het schrijven** -- `ExterneProviderNietToegestaan`, een
   `PermissionError`. Fail-secure: bewaar geen sleutel die je niet mag gebruiken.
2. **Deugt het adres?** `SSRFProtector.validate_url()` met een strenge configuratie in
   `src/core/security/llm_endpoint_policy.py`: geen loopback, geen private netwerken, geen
   link-local, geen metadata-diensten, alleen `https` en alleen poort 443.

**De volgorde is bewust.** Andersom zou een tenant op lokaal-alleen uit de foutmelding kunnen
aflezen welke interne adressen bestaan.

**Waarom `ssrf_protection.py` en niet `egress_control.py`.** Ze lijken op elkaar en doen iets
anders. `SSRFProtector.validate_url(url)` toetst de VORM en bestemming van een URL.
`EgressController.validate_request(url, tenant_id, ...)` is een tenantbeleid met audit, staat
achter `FEATURE_FLAG_EGRESS_CONTROL` (standaard uit) en wordt alleen door activepieces gebruikt.
Wij toetsen hier een adres, geen beleid.

**Waarom ons eigen Ollama hier niet langs hoeft:** dat adres komt uit `LLM_BASE_URL` in de
uitrol, nooit uit een tenantrij, en het draait op een prive-adres op poort 11434 -- precies wat
de strenge configuratie voor klantinvoer blokkeert. De twee gevallen scheiden zich vanzelf.

### 4b. Wat de TWEE reviewrondes hebben toegevoegd

Deze paragraaf staat er omdat de rest van dit document beschrijft hoe het ontwerp bedoeld was,
en Gate 2 aantoonde dat de uitvoering daar op zes punten onder zat. Alle zes zijn nagemeten
voordat ze werden gerepareerd.

| Wat er mis was (gemeten) | Wat er nu staat |
|---|---|
| `SSRFProtector` faalt OPEN als DNS niets oplevert: `http://interne-app.corp` en `https://2130706433/` werden TOEGESTAAN | `KlantEindpuntControle` weigert een naam die hier niet opzoekbaar is. Een letterlijk IP slaat die eis over -- dat pad komt nooit bij de naamresolutie |
| Een sleutel kon in het ADRES: `https://gebruiker:geheim@host/v1` passeerde en belandde onversleuteld in `base_url`, die het leesendpoint teruggeeft | Inloggegevens, query en fragment worden geweigerd |
| `http` naar een publieke host mocht; de sleutel gaat als bearer-token mee | Alleen `https`, alleen poort 443 |
| De drie `log_security_event`-aanroepen gaven geen `db` mee, dus er kwam NOOIT een auditrij | `schrijf_llm_provider_audit` dwingt `db` af |
| ...en daarna: de auditrij werd wel geschreven maar alleen GEFLUSHT, en `get_db` rolt terug bij een `HTTPException` -- dus juist de twee WEIGERINGEN lieten geen spoor na | Expliciete `commit()` in het auditblok, bewezen met een integratietest die na een rollback de rij terugleest |
| Drie IPv6-vormen liepen door de enige rem: `[::]` (komt bij verbinden op loopback uit), 6to4 en NAT64 van 169.254.169.254 -- terwijl `0.0.0.0` wel werd geweigerd | Een letterlijk IP moet `is_global` zijn; NAT64 wordt apart uitgepakt omdat `is_global` daar doorheen kijkt |
| De sterkte-eis op de hoofdsleutel was feitelijk een LENGTE-eis: `"a" * 43` en een wachtwoordzin passeerden | Drie zeven: `validate=True`, minstens 16 verschillende bytes, en hoofdletters in de base64-vorm. Gemeten: 0 van 2000 echte generatorsleutels ten onrechte geweigerd |

**Eerlijk over wat er NIET is opgelost.** De hercontrole in `keten()` verkleint het
rebinding-venster maar sluit het niet: tussen die controle en het moment dat de HTTP-client
verbindt, resolveert de naam opnieuw. Echt dichtzetten vraagt om het gevalideerde IP vastpinnen
bij de verbinding, en dat hoort bij fase 2b waar die verbinding wordt gelegd. En de
fail-closed-eis op de naamresolutie is ook een beschikbaarheidsschakelaar: bij een DNS-storing
valt de klantketen weg, stil richting de gebruiker (terugval op het platformmodel) en luid in
het logbestand. Dat is de veilige kant, maar het hoort in het inrichtingsdossier te staan.

### 5. De sleutel is write-only

Hij gaat erin via het verzoek en komt er nooit uit. Het leesantwoord zegt alleen OF er een
sleutel staat (`heeft_sleutel: bool`). Een beheerder die hem kwijt is, zet een nieuwe -- dat is
goedkoper dan een endpoint dat geheimen teruggeeft. `OpgeslagenProvider` (de repository-vorm) kan
geen leesbare sleutel produceren, ook niet per ongeluk, omdat de klasse er geen kan maken.

### 6. Geen klantscherm

ADR-036 B8: de inrichting is dienstverlening. Een adviseur zet dit bij de onboarding via
`POST /admin/llm-providers`, en dat geeft meteen een auditspoor. Drie
`log_security_event`-gebeurtenissen: `LLM_PROVIDER_INGERICHT`,
`LLM_PROVIDER_EXTERN_GEWEIGERD`, `LLM_PROVIDER_ADRES_GEWEIGERD`. De twee weigeringen worden
geauditeerd VOOR het antwoord: een beheerder die interne adressen aftast hoort een spoor achter
te laten.

---

## Trainingssamenvatting

- **Actor:** adviseur met de rol `admin` (of `system_admin` / `tenantadmin`), tijdens de
  onboarding van een klant.
- **Voorwaarde:** de adviseur is geauthenticeerd; `tenant_id` komt uit het token, NOOIT uit de
  body. Voor een extern eindpunt staat `externe_providers_toegestaan` van die tenant op TRUE.
  Op de server is `MASTER_ENCRYPTION_KEY` gezet.
- **Actie:** `POST /admin/llm-providers` met volgorde, naam, base_url, model, optioneel
  een api_key, en actief. Of `GET /admin/llm-providers` om de keten te bekijken.
- **Systeemreactie:** de service toetst eerst of de tenant extern mag, dan of het adres de
  SSRF-controle doorstaat, versleutelt de sleutel met de tenant-eigen afgeleide sleutel, slaat de
  rij op en schrijft een auditregel.
- **Succes:** `201` met `{"success": true, "data": {"id": <nieuw id>}}`. Bij GET: `200` met de
  keten op volgorde, met `heeft_sleutel` in plaats van de sleutel.
- **Fout:**
  - `403` -- deze tenant staat op lokaal-alleen (`LLM_PROVIDER_EXTERN_GEWEIGERD` in de audit).
  - `400` -- het adres is geweigerd door de SSRF-controle, met de reden erbij. De reden mag naar
    de beheerder: hij moet zijn eigen typefout kunnen zien, en er is nog geen netwerkaanroep
    gedaan waaruit iets kan lekken.
  - `409` -- er staat al een provider op die `volgorde`. Een botsing die de aanvrager zelf
    kan oplossen; andere integriteitsfouten krijgen bewust de 500 die erbij hoort.
  - `503` -- `MASTER_ENCRYPTION_KEY` ontbreekt OF is te zwak (`HoofdsleutelTeZwak` erft van
    `HoofdsleutelOntbreekt`). Bewust 503 en geen 500: dit is een ontbrekende configuratie,
    geen defect, en de melding zegt wat er moet gebeuren.
- **Uitzonderingen:** een lokaal eindpunt zonder sleutel is geldig (`api_key_encrypted` blijft
  NULL). De RLS-policies staan op de tabel maar beschermen vandaag niets (zie hierboven).

---

## Bewakers

| Bewaker | Wat hij vastzet |
|---|---|
| `tests/architecture/test_elk_schrijfpad_naar_een_klanteindpunt_wordt_gevalideerd.py` | Twee schakels: wie een rij AANMAAKT, en wie het schrijfpad AANROEPT -- en dat elke aanroeper `validate_url` doet |
| `tests/unit/security/test_tenant_secret_encryption.py` (28) | Fail-closed zonder hoofdsleutel EN bij een te zwakke sleutel; sleutel per tenant; kruislings ontsleutelen faalt; de `v1:`-versie-aanduiding |
| `tests/unit/security/test_klant_eindpunt_beleid.py` (14) | Het adresbeleid zelf, met een GESTUURDE naamresolutie zodat er geen echte DNS aan te pas komt |
| `tests/unit/api/v1/admin/test_llm_providers_router.py` (14) | Statuscodes (403/400/409/503), het auditspoor MET database, en dat een meegestuurd `tenant_id` wordt geweigerd |
| `tests/unit/services/test_tenant_llm_provider_service.py` (12) | De twee sloten, hun volgorde, dat de sleutel VERSLEUTELD naar de opslag gaat, en de hercontrole in `keten()` |
| `tests/integration/database/test_tenant_llm_provider_isolatie.py` (10) | Tenantisolatie tegen een ECHTE PostgreSQL -- een dubbelganger kan een vergeten `WHERE tenant_id` niet vertonen, omdat hij het filter nooit uitvoert |

**De architectuurbewaker is mutatiegetest in beide richtingen** (met
`scripts/mutation_harness.py`), en opnieuw gedraaid na de herindeling naar twee schakels -- het
bewijs van de eenschakelige vorm gold niet meer voor wat er nu staat:

1. `validate_url` uit `configureer` gehaald -> ROOD
2. het gevalideerde adres weggegooid en het ORIGINEEL opgeslagen -> ROOD
3. een tweede aanroeper van het schrijfpad toegevoegd -> ROOD
4. een tweede plek die de rij aanmaakt toegevoegd -> ROOD
5. een rauwe `INSERT INTO tenant_llm_providers` toegevoegd -> ROOD
6. ongewijzigd -> GROEN

Daarnaast op de routerlaag en de auditweg: `db=` uit de auditaanroep -> ROOD; de commit uit
het auditblok -> ROOD (ook in de integratietest tegen een echte database); `extra="forbid"`
weggehaald -> ROOD; de constraint-controle weggehaald -> ROOD; tegenrichting GROEN.

**De anti-holle test verdiende zich meteen terug.** De eerste versie van de bewaker vond NUL
schrijvers, omdat `git grep` standaard alleen getrackte bestanden doorzoekt en het model nog niet
gecommit was. Een bewaker die nieuwe code niet ziet, is blind op precies het moment dat hij nodig
is. Vandaar `--untracked`.

**De sleutel is `bestand::functie` en niet alleen het bestand** (ADR-036 OP-258): een uitzondering
op bestandsniveau maakt de bewaker blind voor elke andere functie in datzelfde bestand.

---

## Metingen

| Poort | Uitkomst |
|---|---|
| `pytest tests/architecture -n 4` | 987 passed, 1 xfailed |
| De vijf eigen unit-/architectuurbestanden | 78 collected, alle groen |
| `pytest tests/integration/database/test_tenant_llm_provider_isolatie.py` | 9 passed (echte PostgreSQL op netwerkpoort 5455) |
| `ruff check src/` | All checks passed |
| `python scripts/run_mypy_audit.py --fail-on-increase` | Total errors: 0, baseline 0 |
| `python -m pyright` | 0 errors, 35 warnings (optional imports, bestaand) |

---

## Wat dit NIET doet

- **Geen resolutie.** `LLMService.for_tenant(tenant_id)` is fase 2b. De 27 bestaande
  `LLMService()`-aanroepen in 20 bestanden blijven op de platformstandaard; ze in een ronde
  omzetten geeft een diff die niemand kan reviewen, en de meeste hebben vandaag geen tenant bij
  de hand.
- **Geen klantscherm** (ADR-036 B8).
- **Geen circuit breaker en geen kostenplafond.** ADR-026 beschrijft die bij de keten; ze komen
  pas als een tenant er echt meerdere providers op heeft.
- **De kapotte agenda-tokenversleuteling wordt hier NIET gerepareerd.** Dat is een eigen
  bevinding met een eigen brief
  (`docs/agent-briefs/generated/2026-09-20-bevinding-agenda-tokens-onleesbaar-na-herstart.md`);
  meenemen zou deze feature vertroebelen.

---

## Openstaand

1. **`MASTER_ENCRYPTION_KEY` moet nog GEZET worden, en dat is een interlock.** De variabele
   staat nu wel in `docker-compose.yml` (drie diensten, met `:-` zodat lokaal blijft starten)
   en in `docker-compose.prod.yml` (vier diensten, met `:?`). `.env.example` is NIET
   bijgewerkt: dat pad valt onder een denyregel en is niet te lezen of te bewerken -- die regel
   zet Rakesh zelf.

   **Let op, twee gevolgen die bij de uitrol horen en niet stil mogen meegaan:**
   (a) door de `:?` weigert een bestaande productie- of staginguitrol met dat compose-bestand
   te starten tot de variabele er is -- dat is een uitrolhandeling met een geheim en daarmee
   Rakesh' interlock, geen bijvangst van deze commit;
   (b) zodra de sleutel WEL gezet is, stapt het bestaande `TokenEncryptionService` over van
   zijn proces-lokale terugval naar de echte sleutel, waardoor bestaande agenda-tokens
   onleesbaar worden. Ze waren dat na elke herstart al -- dat is de aparte bevindingsbrief --
   dus er gaat niets verloren dat niet al verloren was, maar het hoort hier te staan in plaats
   van ontdekt te worden.
2. **Het mutatiebewijs op het tenantfilter van de repository is nog niet gedraaid.** De
   integratietests zijn groen tegen een echte database, maar "groen" bewijst nog niet dat ze rood
   KUNNEN worden. Uitgesteld met reden: twee Gate 2-reviewers lazen op dat moment hetzelfde
   bestand, en een mutatie op schijf laat een reviewer een defect zien dat niet bestaat
   (valkuil `mutatietesten_in_een_levende_werkboom`). Moet alsnog, voor de commit.
3. **De RLS-policies zijn inert** tot de rolwissel uit ADR-036 OP-154 landt. Dat is bestaand en
   bewust omheind werk, geen regressie van deze feature.
