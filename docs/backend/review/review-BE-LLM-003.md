# Review BE-LLM-003 -- Klantprovider-opslag

**Datum:** 2026-09-20
**Rondes:** 2 (beide met twee onafhankelijke reviewers)
**Spec:** `docs/backend/features/BE-LLM-003-klantprovider-opslag.md`

STATUS: APPROVED WITH MINOR GAPS

De negen bevindingen uit ronde 1 en de acht uit ronde 2 zijn allemaal nagemeten
voordat ze werden gerepareerd, en de reparaties zijn mutatiegetest in beide richtingen. Wat
resteert staat onderaan onder "Bewust niet opgelost", met per punt de reden en de meting.

---

## Ronde 1 -- beide reviewers: CHANGES_REQUESTED

Elke bevinding is door mij zelf nagemeten voordat er iets veranderde. Alle negen klopten.

| # | Ernst | Bevinding | Meting | Reparatie |
|---|---|---|---|---|
| 1 | HIGH | `SSRFProtector` faalt OPEN als DNS niets oplevert (`ssrf_protection.py:500-508`) | `http://interne-app.corp`, `https://2130706433/` en `http://ollama/v1` allemaal TOEGESTAAN | `KlantEindpuntControle` om de protector heen, fail-closed op naamresolutie. `ssrf_protection.py` ONGEMOEID -- die heeft andere aanroepers |
| 2 | HIGH | `keten()` gaf adres + ontsleutelde sleutel terug zonder hercontrole (CVE-2026-84377-vorm) | `git grep`: nul aanroepers, dus niet uitbuitbaar vandaag | Hercontrole in `keten()`, rij overslaan met `logger.error` |
| 3 | HIGH | Non-ASCII (`U+00E9`) in `llm_endpoint_policy.py:20,25` | Eigen scan; `test_no_non_ascii_in_core_zone.py` dekt `src/core/security` niet | Verwijderd |
| 4 | HIGH | De drie `log_security_event`-aanroepen gaven geen `db` mee | `audit_service.py:188-190` keert dan meteen terug: geen `AuditLog`-rij | `schrijf_llm_provider_audit` in de facade dwingt `db` af |
| 5 | MEDIUM | `ProviderRij.__repr__` drukte de ontsleutelde sleutel af | `repr()` gedraaid: sleutel zichtbaar | `field(repr=False)` |
| 6 | MEDIUM | Inloggegevens in de URL passeerden en belandden onversleuteld in `base_url` | `https://user:sk-...@api.deepseek.com/v1` TOEGESTAAN | Geweigerd, net als query en fragment |
| 7 | MEDIUM | `http` naar publieke hosts toegestaan | `http://api.deepseek.com/v1` passeerde | Alleen `https`, alleen 443 |
| 8 | MEDIUM | Zwakke hoofdsleutel geaccepteerd; HKDF strekt niet | `master_key="x"` versleutelde gewoon | Sterkte-eis plus `HoofdsleutelTeZwak` |
| 9 | MEDIUM | Geen sleutelversie: rotatie = stil gegevensverlies | Geen voorvoegsel in de ciphertext | `v1:` plus `OnbekendeSleutelversie` |

Daarnaast uit ronde 1: geen paginering (opgelost), 500 bij dubbele volgorde (nu 409), geen
routertests (nu 14), `extra="forbid"` ontbrak (toegevoegd), een fout auditpad (gecorrigeerd
naar `/admin/llm-providers`), en de architectuurbewaker kende maar EEN vocabulaire (nu drie).

**De pijnlijkste bevinding uit ronde 1 ging over mijn eigen test.** `test_een_gewoon_extern_eindpunt_mag_wel`
gebruikte `https://api.voorbeeld-leverancier.test` -- een naam die niet bestaat. Die test
slaagde dus UITSLUITEND via het fail-open pad uit bevinding 1. De helft van het mutatiebewijs
die moet aantonen dat "weiger alles" geen geldige oplossing is, bewees de bug in plaats van de
eigenschap. De servicetests gebruiken nu een testdubbel met een expliciet antwoord; het beleid
zelf staat in een eigen bestand met een gestuurde naamresolutie, zodat geen enkele unittest nog
een echte DNS-lookup doet.

---

## Ronde 2 -- beide reviewers opnieuw

Opdracht: niet de feature opnieuw beoordelen, maar toetsen of de reparaties ECHT zijn. Dat
leverde acht nieuwe bevindingen op, waarvan er drie IN de reparatie zelf zaten (A, B, C).

| # | Ernst | Bevinding | Meting | Reparatie |
|---|---|---|---|---|
| A | HIGH | De auditregels van de twee WEIGERINGEN worden geschreven en daarna teruggedraaid | `log_event` doet alleen `flush()` (`audit_service.py:123`); `get_db` doet `rollback()` bij een uitzondering (`database.py:509-513`); de router gooit daarna een `HTTPException` | Expliciete `commit()` in het auditblok; primaire data committeert de router ervoor |
| B | MEDIUM | De sterkte-eis is feitelijk een LENGTE-eis | `urlsafe_b64decode` draait met `validate=False` en dunt stil uit: `"correct horse battery staple ..."`, `"a" * 43` en een Nederlandse wachtwoordzin passeerden allemaal | `validate=True` + minstens 16 verschillende bytes + hoofdletters in de base64-vorm |
| C | MEDIUM | `test_de_fabriek_levert_de_strenge_configuratie` was HOL | Met de mutatie `KlantEindpuntControle(SSRFProtector())` bleven alle vijf asserties groen: ze keken naar de module-constante, niet naar het object | Toetst nu het object EN het gedrag (een `http`-adres moet sterven) |
| D | MEDIUM | `dubbele_volgorde_fout()` was de kale `IntegrityError`: elke integriteitsfout werd "volgorde al in gebruik" | Code gelezen; een FK- of NOT NULL-schending geeft hetzelfde type | `is_dubbele_volgorde` toetst de constraintnaam; al het andere valt door naar de 500 |
| E | MEDIUM | De spec liep op negen punten achter op de code | Reviewer somde ze met regelnummers op | Alle negen bijgewerkt, plus een nieuwe paragraaf 4b |
| F | MEDIUM | Drie IPv6-vormen liepen nog steeds door de enige rem | `https://[::]/v1`, `https://[2002:a9fe:a9fe::]/v1` (6to4) en `https://[64:ff9b::a9fe:a9fe]/v1` (NAT64) werden TOEGESTAAN, terwijl de IPv4-tegenhanger `0.0.0.0` WEL werd geweigerd | Een letterlijk IP moet nu `is_global` zijn; NAT64 wordt apart uitgepakt omdat `is_global` daar doorheen kijkt |
| G | MEDIUM | `.env.example` noemt `MASTER_ENCRYPTION_KEY` niet, terwijl productie er zonder weigert te starten | Bestand is 293 regels en bevat de naam niet | NIET opgelost: dat pad valt onder een denyregel. De regel staat klaar voor Rakesh; zie "Bewust niet opgelost" |
| H | LOW | De docstring van `validate_url` beloofde dat alleen `SSRFValidationError` eruit komt | Een IDNA-onvriendelijke hostnaam geeft `UnicodeEncodeError`, een poort boven 65535 geeft `ValueError` | Docstring gecorrigeerd; beide aanroepers vangen breed en degraderen veilig, dus het was een contractfout en geen gat |

**Waarom de IPv6-bevinding zwaarder weegt dan haar ernst suggereert.** Het is de TWEEDE keer
dat dezelfde klasse opduikt: `0.0.0.0` was onthouden, `::` vergeten. De oplossing is daarom
bewust geen vierde adres op een handlijst maar `is_global`, dat de hele categorie afdekt -- plus
precies een uitzondering (NAT64) waarvan gemeten is dat `is_global` hem mist. Dertien adressen
zijn nagemeten, nul afwijkingen, en de tegenrichting ("weiger elk letterlijk IP") is
mutatiegetest zodat "weiger alles" geen geldige oplossing blijft.

Verder uit ronde 2: de modeldocstring zei "de repository versleutelt" terwijl de repository
zelf het tegenovergestelde zegt (gecorrigeerd), en "de volgorde IS de failoverketen" terwijl
`keten()` nul aanroepers heeft (nu "wordt").

**Twee dingen die deze ronde hebben blootgelegd en die groter zijn dan de bevindingen zelf.**
Ten eerste: bevinding A is dezelfde faalvorm als bevinding 4 uit ronde 1, alleen een laag
dieper -- eerst ontbrak de database, daarna werd de transactie teruggedraaid. Het spoor van
precies de twee gebeurtenissen die je forensisch nodig hebt, bestond in beide gevallen niet, en
op het slaagpad werkte het wel. Dat verschil maakte het onzichtbaar. Ten tweede: drie van mijn
eigen WHY-docstrings bleken deze ronde onwaar (B, D, en de redenering over `best_effort`). Dit
project gebruikt lange toelichtingen als draagconstructie; die werkt alleen zolang ze nagemeten
zijn, en een module die uitlegt waarom zijn eigen beveiliging klopt is precies de plek waar de
volgende lezer niet meer meet.

---

## Ronde 3 -- 2026-09-21, de productieguard

Geen nieuwe feature maar een gat dat bij het natrekken voor fase 2b boven kwam, en dat deze
feature raakt omdat de keten van fase 2b er doorheen zou glippen.

**Het gat.** `LLMService.__init__` weigerde in productie te starten als de provider `"mock"`
HEETTE. Die naam wordt afgeleid van de klassenaam (`base.py:200`). Een samengestelde provider
heet daarmee `"keten"` en passeert, ook met alleen een namaakmodel erin. Geen test werd rood.

**De reparatie.** Een expliciete eigenschap `serves_mock`, met een standaard die het antwoord
uit dezelfde naam afleidt zodat bestaande providers zich onveranderd gedragen.
`provider_name` is ongemoeid gelaten -- 55 bestanden noemen hem.

Twee Gate 2-reviewers, beide CHANGES_REQUESTED. Zeven bevindingen, alle nagemeten:

| # | Ernst | Bevinding | Meting | Reparatie |
|---|---|---|---|---|
| 1 | MEDIUM | Een klant kon zijn eigen productie-LLM stilleggen met een naam | `OpenAICompatibleProvider` haalt `provider_name` uit een LABEL dat sinds BE-LLM-003 uit een vrij tekstveld van de klant komt; met `label='mock'` gaf de standaard `True` voor een ECHT eindpunt | `serves_mock` daar expliciet op `False`, plus een test die het label vastpint |
| 2 | MEDIUM | De standaard is fail-open voor een samengestelde provider, en niets dwingt het overschrijven af | Nul samengestelde subklassen vandaag, maar de keten van 2b erft `False` als hij het vergeet | Architectuurbewaker: wie `provider_name` overschrijft, moet ook `serves_mock` overschrijven. Betrapte meteen `MockProvider`, die het goede antwoord bij toeval gaf |
| 3 | MEDIUM | Mijn docstring zei "FORCE toevoegen is geen verbetering van de bescherming" | Klopt voor het applicatiepad, niet voor de eigenaar; spreekt ADR-036 OP-151 tegen | Herschreven, met wat WEL en NIET gemeten is |
| 4 | MEDIUM | Het overdrachtsdocument beschreef het zojuist gedichte gat als openstaand werk | Regel 108 was al vervangen door `serves_mock` op `:112` | Herschreven naar verleden tijd, plus de overschrijfplicht voor de keten |
| 5 | MEDIUM | De claim "FORCE staat op 170 staging-tabellen" is niet na te meten | Geen migratie in deze repo voert FORCE uit; lokaal nul tabellen; staging weigerde de verbinding | Als documentair gemarkeerd |
| 6 | LOW | De testdubbels DRAGEN het attribuut, dus een `getattr(..., False)`-herschrijving bleef groen | Een dubbel zonder het attribuut geeft `AttributeError` -- fail-closed | Zevende test die dat vastlegt |
| 7 | LOW | Telling "54 bestanden", assertie op het dubbel, inert `# noqa`, gekoppelde dubbels | 55 gemeten | Alle vier gecorrigeerd |

**Mutatiebewijs.** Guard: terug naar de naamsvergelijking -> ROOD; standaard altijd `False`
-> ROOD; standaard altijd `True` -> ROOD; ongewijzigd -> GROEN. Nieuwe architectuurbewaker:
`serves_mock` uit `openai_compatible.py` -> ROOD; uit `mock.py` -> ROOD; een nieuwe klasse met
alleen `provider_name` -> ROOD; ongewijzigd -> GROEN.

**Wat de testpoort zelf ving.** De eerste run na deze wijziging stond rood op
`test_er_staat_geen_leveranciersadres_in_de_agnostische_laag` -- een bewaker uit BE-LLM-002,
die een voorbeeld-URL in mijn nieuwe docstring betrapte. Het adres is eruit; de bewaker deed
precies waarvoor hij is geschreven, tegen de persoon die hem schreef.

**Eindmeting:** 16944 passed, 115 skipped, 20 xfailed, 0 failed (15:56). ruff schoon, mypy 0,
pyright 0 errors, documentatiepoort PASS, acceptatieketen stap 2 van 7 (onveranderd).

**Buiten scope gehouden, met een eigen brief:** twee productiepaden die WEL onvoorwaardelijk
op een namaakmodel uitkomen -- de Digital Twin (`twin_service_factory.py`, nul
`is_production`-controles in heel `src/core/learning/`) en de oude LLM-stack
(`src/core/llm/llm_service.py`, 11 importeurs, nul controles). Zie
`docs/agent-briefs/generated/2026-09-21-bevinding-twee-productiepaden-naar-een-namaakmodel.md`.

---

## Mutatiebewijs (scripts/mutation_harness.py, beide richtingen)

Architectuurbewaker, voor de derde keer gedraaid omdat het bewijs van een vorige vorm niet
geldt voor wat er nu staat:

1. `validate_url` uit `configureer` -> ROOD
2. gevalideerd adres weggegooid, origineel opgeslagen -> ROOD (deze ving de vorige versie niet)
3. tweede aanroeper van het schrijfpad -> ROOD
4. tweede plek die de rij aanmaakt -> ROOD
5. rauwe `INSERT INTO tenant_llm_providers` -> ROOD (deze ving de vorige versie niet)
6. ongewijzigd -> GROEN

Routerlaag en auditweg:

- `db=` uit de auditaanroep -> ROOD
- de `commit()` uit het auditblok -> ROOD, zowel in de unittest als in de integratietest tegen
  een echte PostgreSQL (met commit: 1 rij overleeft de rollback; zonder: 0)
- `extra="forbid"` -> `extra="ignore"` -> ROOD
- de constraint-controle uitgeschakeld -> ROOD
- ongewijzigd -> GROEN

Adresbeleid (na bevinding F):

- de publieke-bestemmingseis op een letterlijk IP weggehaald -> ROOD
- NAT64 niet meer uitgepakt -> ROOD
- `if not echt.is_global` -> `if True` (de "weiger alles"-oplossing) -> ROOD, dus de
  tegenrichting bestaat echt en IPv6 wordt niet als categorie geweigerd
- ongewijzigd -> GROEN

---

## Gate 3

| Meting | Uitkomst |
|---|---|
| `ruff check src/ tests/` | All checks passed |
| `python scripts/run_mypy_audit.py --fail-on-increase` | Total errors: 0, baseline 0 |
| `python -m pyright` | 0 errors, 35 warnings (optionele imports, bestaand) |
| Volledige testpoort | 16916 passed, 115 skipped, 20 xfailed |
| `tests/integration/database/test_tenant_llm_provider_isolatie.py` | 10 passed tegen PostgreSQL |

---

## Bewust niet opgelost, met reden

1. **Het rebinding-venster is verkleind, niet gesloten.** Tussen de hercontrole in `keten()` en
   het moment dat de HTTP-client verbindt, resolveert de naam opnieuw. Dichtzetten vraagt om
   het gevalideerde IP vastpinnen bij de verbinding; die verbinding wordt in fase 2b gelegd, en
   daar hoort het dus ook. Staat als eerste punt in de fase-2b-brief.
2. **Blokkerende DNS op de event loop.** `SSRFProtector._resolve_hostname` doet een synchrone
   `socket.getaddrinfo` met een time-out van 5 seconden, nu vanuit `async def`. Vandaag
   onschuldig (`keten()` heeft nul aanroepers), maar fase 2b zet dit op het verzoekpad: N rijen
   maal maximaal 5 seconden. Moet VOOR 2b opgelost worden, niet erna.
3. **`_resolve_tenant_id` heeft een `TESTING=1`-luik** (`dependencies.py:80`). Bestaand, niet
   van deze feature, maar het betekent dat een routertest op dit endpoint een pad neemt dat
   productie nooit neemt -- de valkuil `testluik_maakt_bewaker_hol`. De nieuwe routertests
   dichten dat niet.
4. **De RLS-policy op de nieuwe tabel is inert** tot de rolwissel uit ADR-036 OP-154 landt. Het
   expliciete `tenant_id`-filter in de repository is vandaag de enige laag, en dat is met tien
   integratietests tegen een echte database vastgelegd.
5. **`.env.example` is niet bijgewerkt, en dat is nu dringender dan het klinkt.** Sinds
   `docker-compose.prod.yml` de variabele vier keer met `:?` eist, weigert een productie-uitrol
   te starten met een melding die wijst naar een variabele die het sjabloon nergens noemt. Dat
   pad valt onder een denyregel en is voor mij niet te lezen of te bewerken. De regel die erin
   moet, staat in de afsluitende samenvatting en luidt:
   `MASTER_ENCRYPTION_KEY=` met daarboven een commentaarregel die zegt dat productie zonder
   deze waarde weigert te starten en dat hij gegenereerd wordt met
   `python -c "import secrets; print(secrets.token_urlsafe(32))"`.

---

## Devil's Advocate (CLAUDE.md regel 9)

**Waarom dit over zes maanden alsnog faalt.**

1. **Het koppelingsbudget wordt bevredigd met indirectie, niet met ontkoppeling.**
   `llm_provider_fouten()`, `dubbele_volgorde_fout()` en `is_dubbele_volgorde()` bestaan mede om
   `test_fan_out_budget[core_api]` groen te houden. De router HANGT nog steeds af van
   `sqlalchemy.exc.IntegrityError` en van de foutentaxonomie van de service -- alleen via een
   functieaanroep die import-linter niet ziet. De meter staat groen en de koppeling is er nog.
   Over een half jaar staat hier een vierde en een vijfde helper en is het patroon de norm. Dit
   faalt op de dag dat iemand het budget wil geloven.
2. **`externe_providers_toegestaan` is een verkoopbelofte die als technische controle vermomd
   gaat.** Er is geen endpoint om de vlag te zetten, dus iemand doet het straks met een
   `UPDATE`. Er is geen audit op die wijziging en geen bewaker die er een eist. De eerste keer
   dat "alle data blijft op eigen server" in een contract staat en iemand die vlag stil omzet,
   is er geen spoor.
3. **De derde versleutelingslaag op dezelfde omgevingsvariabele.** `secret_manager.py`,
   `token_encryption.py` en nu `tenant_secret_encryption.py` hangen alle drie aan
   `MASTER_ENCRYPTION_KEY`, met drie verschillende KDF's. Een sleutelrotatie vraagt straks drie
   migratiescripts, geschreven door iemand die van de derde niet weet. Het `v1:`-voorvoegsel
   maakt dat voor DEZE laag oplosbaar; voor de andere twee niet.
4. **Fase 2b kan de bewaker nog steeds omzeilen.** Hij ziet nu insert, update, delete en rauwe
   SQL, maar niet een `try/except` die bij een weigering terugvalt op het originele adres, en
   niet een aanroep onder een `if False:`. Dat staat expliciet in zijn docstring -- en precies
   dat soort voetnoot leest de volgende bouwer niet.
