# BE-SEC-049 -- Zelf-goedkeuring blokkeren op het gatekeeper-HITL-pad

| Veld | Waarde |
| --- | --- |
| ID | BE-SEC-049 |
| Registerpunt | ADR-036 OP-81 |
| Sprint | ADR-036 open-punten, OP-81 |
| Datum | 2026-09-01 |
| Status | Geimplementeerd |
| Branch | `iter/op-81-zelfgoedkeuring-gatekeeper` |

---

## A. Build Summary

Op het gatekeeper-HITL-pad kon de aanvrager zijn EIGEN goedkeuringsticket goedkeuren of
afwijzen. Het zusteroppervlak (de tool-broker) had die grens al sinds OP-70; hier ontbrak
hij omdat het ticketmodel geen veld had voor de mens namens wie de agent de aanvraag deed.

Deze wijziging voegt dat veld toe (`hitl_requests.requested_by_user_id`), laat de bestaande
producent het vullen, en past dezelfde zelf-goedkeuringscheck toe op beide routes die staat
wijzigen.

Geen nieuw concept: het is symmetrie met wat op het broker-pad al bewezen werkt.

---

## B. Backend Inventory

| Eenheid | Type | Bestand | Wijziging |
| --- | --- | --- | --- |
| `HITLRequestModel.requested_by_user_id` | SQLAlchemy-kolom | `src/core/governance/models.py` | NIEUW |
| `adr036_op81_requested_by` | Alembic-migratie | `src/alembic/versions/20260901_adr036_op81_hitl_requested_by.py` | NIEUW |
| `HITLRequest.requested_by_user_id` | dataclass-veld | `src/core/als/enterprise/gatekeeper.py` | NIEUW |
| `_als_gebruikersnummer()` | hulpfunctie | `src/core/als/enterprise/gatekeeper.py` | NIEUW |
| `Gatekeeper._create_hitl_request()` | methode | `src/core/als/enterprise/gatekeeper.py` | GEWIJZIGD (parameter) |
| `Gatekeeper.evaluate_task()` | methode | `src/core/als/enterprise/gatekeeper.py` | GEWIJZIGD (leest `context["user_id"]`) |
| `GatekeeperRepository.save_hitl_request()` | repository | `src/core/als/enterprise/gatekeeper_repository.py` | GEWIJZIGD (persisteert veld) |
| `_refuse_self_approval()` | guard | `src/core/api/v1/gatekeeper/gatekeeper_hitl_router.py` | NIEUW |
| `POST /api/v1/gatekeeper/hitl/approve` | endpoint | idem | GEWIJZIGD (guard toegepast) |
| `POST /api/v1/gatekeeper/hitl/reject` | endpoint | idem | GEWIJZIGD (guard toegepast) |

---

## C. Functionele specificatie

**Wat er misging.** De rolcheck uit OP-43 (`_require_approver`) toetst een ROL, geen RELATIE.
Een tenantbeheerder kon dus een agent namens zichzelf een HIGH-risk actie laten voorstellen en
het resulterende goedkeuringsticket vervolgens zelf goedkeuren. Bij precies de groep met de
meeste rechten was het vierogenprincipe uit ADR-015 daarmee een formaliteit.

**Waarom het gat bestond.** Niet uit vergeetachtigheid: `HITLRequestModel` legde alleen
`agent_id` en `task_id` vast. Er was geen veld dat zei NAMENS WIE de agent handelde, dus de
vergelijking "beslisser == aanvrager" kon domweg niet gemaakt worden.

**Wat er nu gebeurt.** Bij het aanmaken van een HITL-aanvraag legt de gatekeeper het
gebruikersnummer van de initierende mens vast. Bij goedkeuren of afwijzen vergelijkt de route
dat nummer met de geauthenticeerde gebruiker. Zijn ze gelijk, dan volgt een 403.

**Wie merkt hier iets van.** Alleen een beheerder die zijn eigen aanvraag probeert af te
handelen. Elke andere beheerder kan het ticket onveranderd goedkeuren of afwijzen.

---

## D. Technische specificatie

### D1. Datamodel

```python
requested_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
```

- **Integer en geen tekst.** Zelfde reden als bij `approved_by` in OP-55: een e-mailadres kan
  de gebruiker zelf wijzigen via `PUT /api/v1/users/me` en is dus geen stabiele sleutel voor
  een identiteitsvergelijking. Een integer kan bovendien niet in formaat afdrijven -- de
  JSONB-tegenhanger op het broker-pad kostte daar een aparte reparatie (OP-106).
- **Nullable.** Bestaande rijen hebben geen aanvrager, en een aanvraag zonder menselijke
  opdrachtgever (een autonome planner) heeft er geen. De check slaat dan over; de rolcheck
  blijft staan. Zelfde afweging en zelfde motivering als op het broker-pad.
- **Geen foreign key naar `users.id`.** `tenant_id` en `agent_id` in deze tabel hebben er ook
  geen, en een FK zou het opschonen van een gebruikersaccount laten botsen met bewaarde
  goedkeuringshistorie. Dat is een eigen besluit (retentie), niet iets om hier binnen te
  smokkelen.

### D2. Migratie

`adr036_op81_requested_by`, `down_revision = 20260824_adr029_portal_v1`.

- `upgrade()`: `ADD COLUMN IF NOT EXISTS` plus `CREATE INDEX IF NOT EXISTS`.
- `downgrade()`: `DROP INDEX IF EXISTS` plus `DROP COLUMN IF EXISTS` -- een echte terugweg,
  geen `pass`.
- Geen `sa.inspect(op.get_bind())` (backend-patterns par. 9): rauwe SQL, hetzelfde patroon als
  `c3d4e5f6a7b8` toen dat `hitl_requests.agent_id` toevoegde.

Gemeten tegen een echte Postgres 15 (wegwerpcontainer op poort 5459):

| Meting | Uitkomst |
| --- | --- |
| `alembic heads` | `adr036_op81_requested_by (head)` -- precies EEN head |
| `alembic upgrade head` | volledige keten toegepast, kolom + index aanwezig |
| `alembic downgrade -1` | kolom EN index verdwenen (geverifieerd met `\d hitl_requests`) |
| `alembic upgrade head` (opnieuw) | kolom + index terug |
| `alembic check` -- parent-baseline | 854 drift-operaties |
| `alembic check` -- met deze wijziging | 854 drift-operaties, waarvan 0 over `requested_by_user_id` |

De 854 is pre-existente, schemabrede drift in deze repo (`ab_tests`, `account_lockouts`,
`agent_configs` en tientallen andere tabellen). Deze wijziging voegt er nul aan toe. Dat is
gemeten door de parent-staat op dezelfde database te reproduceren, niet beredeneerd.

### D3. Identiteitsketen

De aanvrager komt binnen via `evaluate_task(..., context={"user_id": <int>})`. Dat is een
server-side parameter van een servicemethode, nooit een request body -- OWASP ASVS 5.0 8.3.1
eist handhaving in een trusted service layer op iets dat de consumer niet kan manipuleren.
`context["user_id"]` is de bestaande conventie in deze codebase voor "de mens namens wie dit
loopt" (zie `tool_broker/hitl_router.py::_voer_goedgekeurde_actie_uit`).

`_als_gebruikersnummer()` accepteert alleen een echt geheel getal of een zuiver decimale
ASCII-string. `bool` wordt expliciet geweigerd (`isinstance(True, int)` is True in Python) en
er wordt `isascii() and isdecimal()` gebruikt in plaats van `isdigit()` -- dat laatste is True
voor Arabisch-Indische cijfers en superscripts, waarop `int()` een `ValueError` gooit (OP-106).

### D4. De guard

```python
requester = hitl.requested_by_user_id
if requester is not None and requester == current_user.id:
    raise HTTPException(status_code=403, detail="...")
```

Rechtstreeks en NIET via `getattr(..., None)`: een vangnet met een default maakt van een
hernoemde of verdwenen kolom een stille fail-open, en dat is precies de holle-guard-vorm die
`.claude/rules/quality-gates.md` verbiedt.

Toegepast op BEIDE staat-wijzigende routes. Afwijzen is net zo goed een governance-besluit:
zonder die helft haalt de aanvrager zijn eigen aanvraag uit de wachtrij voordat een ander mens
hem ziet.

**Tweede guard, alleen op GOEDKEUREN: `_require_traceable_requester`.** Is
`requested_by_user_id` NULL, dan is goedkeuren onmogelijk (403, `REQUESTER_NOT_TRACEABLE`) en
afwijzen nog steeds toegestaan. Besluit Rakesh 2026-09-01, en het wijkt bewust af van het
broker-pad: een goedkeuring die niet kan aantonen dat aanvrager en beslisser twee verschillende
mensen zijn, is geen art.-14-bewijs. De vastgelopen-wachtrij-tegenwerping gaat hier niet op,
want (a) er is nooit een productieschrijfpad geweest, dus er zijn geen rijen om vast te laten
lopen, en (b) afwijzen blijft open, dus elk ticket heeft altijd een uitweg. Twee onderscheidende
foutcodes, zodat een beheerder "jij mag dit niet" van "dit ticket is onbewijsbaar" kan scheiden.

### D5. Waarom de MENS en niet de agent

OWASP ASVS 5.0 8.3.3: neem het autorisatiebesluit op de permissies van het OORSPRONKELIJKE
subject, niet van een tussenliggende service die namens hem handelt. `hitl.agent_id` is die
tussenliggende service. Een agent is geen tweede paar ogen en kan geen verantwoording dragen;
toetsen op `agent_id` zou bovendien elk ticket van dezelfde agent aan elkaar knopen en niets
zeggen over de mens die erachter zat.

Het broker-pad doet dit al goed en is daarmee de bewezen referentie: `create_hitl_request` zet
`_requested_by = str(user_id)` (de mens) en bewaart de agent apart als `_executing_identity`
voor de permissiecheck. Twee identiteiten, besluit hangt aan de mens. Conform 8.3.3, dus
gekopieerd en niet gecorrigeerd.

---

## E. Integratorhandleiding

### `POST /api/v1/gatekeeper/hitl/approve`

| Aspect | Waarde |
| --- | --- |
| Auth | Bearer/cookie + CSRF-token; tenantbeheerder (`is_tenant_admin`) |
| Body | `ticket_ref` (str), `approved_by` (str, GENEGEERD), `notes` (str, optioneel) |
| 200 | `{"status": "approved", "ticket_ref": ..., "message": ...}` |
| 400 | Ticket is al afgehandeld |
| 401 | Geen tenantcontext |
| 403 | Geen beheerdersrol, GEEN CSRF-token, OF de aanvrager probeert zijn eigen ticket af te handelen (NIEUW) |
| 404 | Ticket niet gevonden |

### `POST /api/v1/gatekeeper/hitl/reject`

Identiek, met `rejected_by` (GENEGEERD) en een verplichte `reason` van minimaal 10 tekens. De
403 om zelf-goedkeuring geldt hier even goed.

**Migratiepad voor bestaande integraties.** Geen breuk: bestaande rijen hebben
`requested_by_user_id = NULL` en blijven door iedere beheerder af te handelen. De nieuwe 403
treedt alleen op voor tickets die NA deze wijziging zijn aangemaakt met een bekende aanvrager,
en alleen voor die ene persoon.

---

## F. Acceptatiecriteria

| # | Criterium | Bewijs |
| --- | --- | --- |
| 1 | De aanvrager krijgt 403 bij goedkeuren van zijn eigen ticket | `test_the_initiating_human_cannot_approve_their_own_request` |
| 2 | Idem bij afwijzen | `test_the_initiating_human_cannot_reject_their_own_request` |
| 3 | Een ANDERE beheerder kan gewoon goedkeuren | `test_another_administrator_can_still_approve_the_request` |
| 4 | Idem afwijzen | `test_another_administrator_can_still_reject_the_request` |
| 5 | De echte producent legt de aanvrager vast | `test_the_persisted_request_records_the_initiating_human` |
| 6 | Tenant B ziet het ticket van tenant A niet | `test_a_ticket_from_another_tenant_is_not_visible` |
| 7 | Precies EEN alembic head | `alembic heads` -> `adr036_op81_requested_by (head)` |
| 8 | `downgrade()` werkt echt | kolom + index weg na `downgrade -1`, gemeten op Postgres 15 |
| 9 | Geen nieuwe drift | 854 -> 854 drift-operaties, 0 over deze kolom |
| 11 | Ticket zonder herleidbare aanvrager kan NIET goedgekeurd worden (403 + `REQUESTER_NOT_TRACEABLE`) | `test_it_cannot_be_approved` |
| 12 | Datzelfde ticket kan WEL afgewezen worden (200) | `test_it_can_still_be_rejected` |
| 10 | Gate 3 groen | ruff: All checks passed; pyright: 0 errors; mypy-audit: zie review |

Alle tests lopen over de ECHTE producent (echte `Gatekeeper`, echte `TaskData`, echte
`GatekeeperRepository`, echte route), niet over zelfverzonnen invoer aan beide kanten van de
vergelijking.

---

## G. Open aannames en risico's

1. **De tabel `hitl_requests` heeft vandaag GEEN productieschrijfpad.**
   `GatekeeperRepository.save_hitl_request` is de enige schrijver en heeft nul aanroepers in
   `src/`, `tests/` en `scripts/` (gemeten met grep). `Gatekeeper.evaluate_task` maakt wel een
   in-memory `HITLRequest` maar persisteert alleen de DECISION. Alle LIVE ticketproducenten
   (`copilot/council/governance_gate.py`, `background_gate.py`,
   `api/v1/focus_builder/execution_router.py`, `als/agents/specialist_base.py`) schrijven naar
   de ANDERE tabel, `hitl_tickets`, via `HITLTicketRepository`.
   **Gevolg:** deze fix is op dit moment PREVENTIEF, net zoals de OP-37-argumentatie destijds.
   De route is wel geserveerd en leest wel uit deze tabel, dus zodra iemand de producent
   aansluit is de grens er al. Dit is een aparte bevinding die als eigen registerrij hoort te
   worden opgenomen; hij is hier gemeten, niet opgelost.

2. **`evaluate_task` krijgt in productie geen `context`.** De enige aanroeper
   (`src/core/als/router.py::_check_gatekeeper`) roept aan met alleen `task`, en `TaskData`
   draagt geen menselijke aanvrager. In productie blijft `requested_by_user_id` daarom NULL tot
   een aanroeper de context meegeeft. Er is bewust GEEN identiteit verzonnen op die plek.

3. **Fail-open bij een ontbrekende aanvrager is een keuze, geen omissie.** Hij volgt het
   broker-pad. De alternatieve lezing (fail-secure blokkeren) zou elke bestaande rij
   onbeoordeelbaar maken en de wachtrij vastzetten. De rolcheck blijft in beide gevallen staan.

4. **Dit vervangt OP-40 niet.** Er is nog steeds geen echte goedkeurdersrol; `is_tenant_admin`
   is de enige beschikbare grens. Deze fix sluit het geval dat OP-40 niet dekt.

---

## Trainingssamenvatting

- Actor: Tenantbeheerder die zelf de opdracht gaf | Voorwaarde: er staat een HITL-ticket open dat door een agent namens hem is aangemaakt, met zijn gebruikersnummer in `requested_by_user_id` | Actie: `POST /api/v1/gatekeeper/hitl/approve` met de eigen ticketverwijzing | Systeemreactie: 403 met "You cannot resolve a HITL request that was submitted on your own behalf" | Succes: het ticket blijft `pending` en wacht op een ander mens | Fout: zonder deze controle werd het ticket goedgekeurd en gold de HIGH-risk actie als menselijk toegestaan | Uitzonderingen: is `requested_by_user_id` leeg (bestaande rij of aanvraag zonder menselijke opdrachtgever), dan blokkeert de controle niets en geldt alleen de beheerdersrolcheck

- Actor: Een ANDERE tenantbeheerder | Voorwaarde: hetzelfde openstaande ticket, aangevraagd door iemand anders | Actie: `POST /api/v1/gatekeeper/hitl/approve` of `/reject` | Systeemreactie: 200, status wordt `approved` respectievelijk `rejected`, en `approved_by` wordt vastgelegd als `user:<id>` uit het token | Succes: het vierogenprincipe is vervuld -- aanvrager en beslisser zijn verschillende mensen | Fout: als de guard iedereen zou weigeren was de HITL-wachtrij onbeoordeelbaar geworden | Uitzonderingen: 403 zonder beheerdersrol of zonder CSRF-token; 400 als het ticket al is afgehandeld; 404 bij een onbekende ticketverwijzing

- Actor: Gatekeeper (server-side, namens een mens) | Voorwaarde: `evaluate_task` komt tot `REQUIRE_HITL` en de aanroeper geeft `context={"user_id": <int>}` mee | Actie: `_create_hitl_request` bouwt een `HITLRequest` en `save_hitl_request` persisteert de rij | Systeemreactie: `hitl_requests.requested_by_user_id` bevat het gebruikersnummer van de initierende mens | Succes: de goedkeurroute kan aanvrager en beslisser vergelijken (OWASP ASVS 8.3.3) | Fout: valt de waarde onderweg weg, dan is de zelf-goedkeuringscheck stil fail-open | Uitzonderingen: ontbreekt `context["user_id"]`, of is het geen geheel getal of zuiver decimale string, dan blijft het veld NULL -- een `bool` wordt expliciet geweigerd
