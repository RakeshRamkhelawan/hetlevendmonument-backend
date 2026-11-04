# Klantworkflow voor debiteuren via de workflowbuilder: wat gebeurt er?

Onderzoek op `develop` @ `b4cb23b2` (2026-10-08). Alleen gelezen, niets gedraaid of gewijzigd. Regelnummers gelden voor die commit.

## Conclusie in gewone taal

Een klant kan vandaag in de workflowbuilder een "debiteurenworkflow" maken. Die workflow komt echter **niet** langs onze debiteurenwaarborgen. De builder vertaalt de stappen naar ActivePieces (AP). AP voert ze daarna zelf uit, met vrije stappen zoals "e-mail", "HTTP-verzoek", "database-query" en elke andere AP-koppeling (`ap_<naam>`).

- **Mail naar een debiteur.** Een klant kan een mail-, Slack- of HTTP-stap rechtstreeks naar een debiteur laten gaan. Er is dan geen HITL, geen vier-ogen, geen betaald-check, geen dubbelverzendbeveiliging, geen veertiendagenregel en geen audit in ons log. Deze stap gaat buiten `outgoing_messages` om.
- **Status wijzigen.** Wil de klant een status zetten, dan moet hij met een HTTP-stap onze API aanroepen met het token van een echte gebruiker. Op dat pad gelden RBAC, de tenantgrens en de audit wel. Zo'n aanroep kan een dossier echter op `herinnerd` zetten zonder dat er een brief is verstuurd. De ingebouwde job escaleert het dossier dan na 14 dagen toch.
- **Wie de workflow uitvoert.** Een AP-run draait onder het beheeraccount van AP en de koppeling van de klant, niet onder een gebruiker van ons. In ons audit-log staat daarom niemand als aanvrager. Vier-ogen kan op dit pad niet werken, omdat er geen ticket is.

Kort gezegd: de ToolBroker-route van de debiteurenagent is goed afgeschermd, maar de builder is een tweede deur zonder die afscherming. ADR-040 (B7, B12) vraagt die afscherming wel, maar die is nog niet gebouwd. `grep hitl|approval|risk` in `src/core/activepieces`, `src/domains/flows`, `src/core/api/v1/activepieces` en `workflow_execution_ap_router.py` geeft 0 treffers.

## Tabel: waarborgen per pad

Uitleg van de paden:

- **A** is de referentie: de debiteurenagent via de ToolBroker (`send_payment_reminder`).
- **B** is een AP-workflow met een vrije mail-, Slack- of HTTP-stap naar de debiteur.
- **C** is een AP-workflow met een HTTP-stap naar onze receivables-API, met het token van een gebruiker.
- **D** is een AP-workflow met een `database_query`-stap (postgres-piece).

| Waarborg | A: ToolBroker | B: vrije mail- of HTTP-stap | C: HTTP naar onze API | D: database-stap |
|---|---|---|---|---|
| RBAC/scopes (incl. `receivables_propose`) | geldt | **omzeild**: alleen login of `WRITE` voor de flow zelf | geldt (`receivables:write` van de token-eigenaar) | **omzeild** |
| Council/SecurityOfficer | geldt | **deels**: alleen bij handmatig uitvoeren via de focus-builder, en de Council ziet alleen `flow_id` en `input_keys` | deels (zoals B) | deels (zoals B) |
| HITL en vier-ogen (geen zelfgoedkeuring) | geldt | **omzeild** | **omzeild**: PATCH-status kent geen HITL | **omzeild** |
| Audit-log | geldt | **omzeild**: alleen AP-runlog | geldt, met de token-eigenaar als aanvrager | **omzeild** |
| Tenantgrens (RLS, `adopt_tenant`) | geldt | n.v.t. (extern), maar het AP-project is niet per tenant: `client.py:482-489` | geldt (JWT) | afhankelijk van de inloggegevens; RLS geldt alleen als de DB-rol niet bypasst |
| Dubbelverzending, betaald-check, rate limit | geldt | **omzeild** | n.v.t. (er wordt niets verstuurd); `consent_update_limit` geldt | **omzeild** |
| Wettelijke regels (14-dagenbrief, incassokosten, B2C/B2B, betwist/belofte) | **deels** (ontbreekt ook hier, zie het testcasedoc) | **omzeild**: vrije tekst | **deels**: alleen de toegestane overgangen | **omzeild** |

## Bevindingen met bewijs

### 1. Wat is "de workflowbuilder"?

Er zijn drie lagen. Alleen de AP-laag is de klantbuilder.

- **ActivePieces (de klantbuilder, ADR-040).** De klant bouwt in ons scherm en AP voert uit (`docs/adr/040-workflowbuilder-met-activepieces.md:33-37`, B1 `:210`).
  - Stappen worden in `src/core/activepieces/transformer.py:295-316` vertaald. Daar staan `email` → gmail `send_email`, `http_request` → `piece-http send_request`, `database_query` → `piece-postgres run_query`, `slack`, `notification_agent` (discord), `openai` en andere.
  - Elke `ap_<naam>` wordt een willekeurige piece (`:318-320`). Een onbekende naam valt terug op `piece-code run_code` (`:322`).
  - Endpoints:
    - `src/core/api/v1/activepieces/flows_router.py:90-209` (create, update, delete, toggle);
    - `execution_router.py:28` (`/flows/{id}/execute`);
    - `connections_router.py:97`, voor het aanleggen van verbindingen met de klantsleutels;
    - `src/core/api/v1/workflow/workflow_execution_ap_router.py:103` (`/execute`) en `:247` (`/ap/{id}/execute`);
    - de focus-builder: `src/core/api/v1/focus_builder/flows_router.py`, `execution_router.py`.
- **De eigen workflow-engine (`src/core/workflow/engine.py`, `src/core/tasks/workflow_tasks.py`).** Die is voor samenwerkende agents en niet voor klantkoppelingen (ADR-040 B1). Tools lopen via `ProductionToolBroker` (`src/core/workflow/providers.py:130-186`), dus langs de ToolBroker. Het is niet onderzocht onder welke agent-identiteit dat gebeurt. Het lijkt geen klantgerichte builder te zijn.
- **De agentroute naar AP-pieces (`src/core/tool_broker/ap_mcp_registry.py`).** Die heeft geen aanroeper (ADR-040 `:176`) en is dus niet actief.

**Benodigde rol:**

| Route | Wat nodig is |
|---|---|
| `/api/v1/activepieces/flows*` en `/execute` | alleen `get_current_user` (`flows_router.py:58,78,101,131,161,186,209`; `execution_router.py:39,113,136`). Elke ingelogde gebruiker kan een flow maken, aanzetten en uitvoeren. |
| Focus-builder: flow maken, wijzigen of verwijderen | `Permission.WRITE` (`focus_builder/flows_router.py:42,149,206`) |
| Focus-builder: uitvoeren | login plus Council (`focus_builder/execution_router.py:41,61-78`) |
| Pieces beheren | `ADMIN` (`pieces_router.py:83`) |
| `/api/v1/workflows/ap/{id}/execute` | geen gebruiker-dependency; `tenant_id: int = 1` is een queryparameter (`workflow_execution_ap_router.py:252-255`) |

Bij die laatste route is niet nagegaan of een globale middleware auth afdwingt. Ze botst in elk geval met de NOOIT-regel in CLAUDE.md dat de tenant niet uit de query mag komen. De route geeft waarschijnlijk 501 door de ontbrekende import (`:263-268`), maar daar moet je niet op rekenen.

### 2. Kan een klantworkflow debiteurenacties uitvoeren?

Ja, langs drie paden:

- **Mail of bericht (pad B).** Gmail, Outlook (via `ap_`), Slack, Discord, WhatsApp en dergelijke met de eigen koppeling van de klant (`transformer.py:297,300,313,318`). De run gaat volledig in AP en raakt `outgoing_messages` niet.
- **Status of betaald zetten (pad C).** Een HTTP-stap (`transformer.py:305`) naar `PATCH /api/v1/receivables/{id}` (`receivables/router.py:100-142`). Daarvoor is nodig:
  - een Bearer-token van een gebruiker met `receivables:write` (`:108`);
  - een CSRF-token (`:111`; `src/core/api/auth/dependencies.py:29-67`). Dat token is gebonden aan IP en User-Agent, dus een flow kan het eerst ophalen en dan meesturen.

  Toegestaan zijn `open|herinnerd|betaald` (`receivables/schemas.py:43`), binnen de overgangen in `receivable_repository.py:86-100`. Ook `POST /reminder-proposals` (`router.py:145`) kan worden aangeroepen. Dat pad loopt netjes naar de HITL.
- **Database (pad D).** `piece-postgres run_query` (`transformer.py:311`) met inloggegevens die de klant zelf invult. Dit raakt onze database alleen als de klant onze DB-gegevens heeft; dat is niet aannemelijk, maar het is wel een open vrije SQL-stap.

### 3. Waarborgen per onderdeel

- **RBAC.** `receivables_propose` (`src/core/auth/rbac.py:79,89`) bestaat alleen voor broker-tools (`src/core/config/tool_risk_levels.yml:118-123`). De AP-routes controleren hem niet. Op pad C geldt de database-RBAC `receivables:write`, niet `receivables_propose`. Die is breder: daarmee kun je ook `betaald` zetten.
- **Council.**
  - `focus_builder/execution_router.py:61-78` legt een voorstel voor met alleen `flow_id` en `input_keys`. De stappen (wie, wat, welke tekst) ziet de Council niet.
  - Zet de klant de flow aan met `toggle` (`activepieces/flows_router.py:198`) en loopt hij daarna op een schema- of webhooktrigger (`transformer.py:298-299`), dan gaat geen enkele run meer langs de Council.
  - `/api/v1/activepieces/flows/{id}/execute` heeft geen Council.
- **HITL en vier-ogen.**
  - Op pad A: het HIGH-niveau (`tool_risk_levels.yml:40`) dwingt een ticket af. Zelfgoedkeuring wordt geweigerd (`src/core/api/v1/tool_broker/hitl_router.py:104-150`, `_is_requester`; `gatekeeper_hitl_router.py:97-125`). Vier-ogen voor `send_payment_reminder` staat standaard UIT (`src/core/governance/four_eyes.py:60`).
  - Op de AP-paden is er geen ticket, dus ook geen vier-ogen. ADR-040 B7 en B12 (`:240`, `:266-274`) eisen het wel, maar het is niet gebouwd (`:436-439`, 0 treffers).
- **Identiteit en audit.**
  - AP draait met één globaal service-account (`src/core/config/unified_config.py:281-283`, ADR-040 `:127`). De piece-actie gebruikt de koppeling van de klant.
  - De webhook `src/core/api/webhooks/activepieces_handler.py:33-75,134-330` schrijft alleen run- en flowstatus bij. Er is geen audit van wat er naar wie is verstuurd.
  - Op pad C staat de token-eigenaar in `schrijf_debiteur_audit` (`receivables/router.py:130-141`). Dat is best-effort en gebeurt na de commit.
  - De maker van de workflow staat nergens als aanvrager van de verzending.
- **Tenantgrens.**
  - Pad C volgt de JWT (`_resolve_tenant_id`). Pad A gebruikt `adopt_tenant` (`debiteuren_tasks.py:144,215`).
  - In AP zelf geeft `find_project_for_tenant` het eerste project terug, ongeacht de tenant (`src/core/activepieces/client.py:482-489`, ADR-040 `:124`). Tot B2 (een AP per tenant) is gebouwd, kunnen flows en koppelingen tussen tenants lekken.
  - De egress-controle gebruikt `tenant_id=0` (`client.py:157`).
- **Dubbelverzending, betaald-check en rate limit.** Op pad A: betaald ⇒ weigeren, debiteur gewijzigd ⇒ opnieuw goedkeuren, een unieke `hitl_ticket_ref` en de verzendlus `verstuur_klare_berichten` (`receivables_registry.py:332-384`; `debiteuren_tasks.py:159-201`). Een AP-stap gaat daar volledig aan voorbij.
- **Wettelijke regels.** `docs/debiteuren-top10-testcases.md:112-153` laat zien dat ze ook op pad A nog ontbreken:
  - geen klanttype;
  - geen incassokosten in de brief;
  - termijn na dagtekening;
  - geen `betwist` of belofte.

  Op pad B schrijft de klant zelf de tekst, dus elke regel is daar omzeild.

### 4. Conflicten met de ingebouwde automatisering

- **Dubbele brieven.** De agent zet via HITL een herinnering klaar en een klantflow mailt dezelfde debiteur ook. Er is geen gedeeld register: `outgoing_messages` kent de AP-mail niet. Het resultaat zijn twee brieven, mogelijk met tegenstrijdige termijnen.
- **Escalatie zonder brief.** Een flow zet via PATCH de status op `herinnerd`. Daarmee wordt `herinnerd_op = nu` gezet (`receivable_repository.py:178-181`). Na 14 dagen zet `volg_debiteuren_op` het dossier op `geescaleerd` (`debiteuren_tasks.py:206-258`), ook als er nooit een herinnering via ons is verstuurd. Het wettelijke vervolg rust dan op een brief die niet aantoonbaar is verstuurd.
- **Statusrace.** De agent heeft een goedgekeurd ticket voor dossier X, en een flow zet X intussen op `betaald` of terug. De verzendtool controleert dat opnieuw bij het verzilveren (`receivables_registry.py:353`). Dat is goed. Omgekeerd geldt dat niet: een flow zet `betaald → open` met een willekeurige `reden` (`receivable_repository.py:99-100`), waarna de agent of de job weer kan opvolgen.
  - Escaleren gebruikt `with_for_update(skip_locked=True)` en controleert de status opnieuw (`debiteuren_tasks.py:216-229`), dus daar is geen corruptie, alleen een semantisch conflict.
  - Er is geen concurrency-veld of versiecontrole op PATCH. Het is last-write-wins.

### 5. Tests

**Aanwezig:**

- `tests/architecture/test_tool_policy_matches_the_tools.py`
- `test_tool_profile_namespaces.py`
- `test_receivables_has_row_level_security_in_an_active_migration.py`
- `test_debiteuren_actors_are_scheduled.py`
- `test_elk_nieuw_hitl_ticket_wordt_gemeld.py`
- `test_activepieces_sandboxed_ci_gate.py`
- `test_webhook_payload_no_tenant_id.py`
- `tests/integration/test_rbac_focus_builder.py`
- `test_focus_builder_council_e2e.py`

**Ontbreekt:**

- een test dat een flow met een uitgaande stap (mail, bericht, HTTP) niet gepubliceerd of aangezet kan worden zonder HITL-keuze (ADR-040 gevolg 8, `:440-444`);
- een test dat de AP-routes meer vragen dan alleen login (rol of scope);
- een architectuurtest "één bron voor de risicolijst per `piece.actie`" (B12);
- een test dat `/api/v1/workflows/ap/{id}/execute` geen `tenant_id` uit de query accepteert;
- een test dat een PATCH naar `herinnerd` zonder verzonden bericht niet tot escalatie leidt, of dat die PATCH niet mag;
- een test die dubbele brieven tussen agent en flow detecteert.

## Risico's, geprioriteerd

1. **Kritiek: vrije mail naar debiteuren buiten HITL en buiten de wet.** Een flow met een gmail-, Outlook-, Slack- of HTTP-stap stuurt ongecontroleerd aanmaningen, zonder 14-dagenbrief of incassokostenregel, zonder betaald-check en zonder audit. Elke ingelogde gebruiker kan dit (`activepieces/flows_router.py`, alleen `get_current_user`).
2. **Kritiek (tot B2 gebouwd is): geen tenantscheiding in AP.** Zie `client.py:482-489`.
3. **Hoog: geplande en webhook-runs gaan nooit langs de Council.** De Council ziet bij een handmatige run ook geen stapinhoud.
4. **Hoog: escalatie zonder brief.** Een PATCH naar `herinnerd` start de klok van `volg_debiteuren_op`.
5. **Hoog: geen identiteit van een mens.** Er is geen aanvrager in het audit-log en vier-ogen is niet toepasbaar.
6. **Middel: route zonder gebruiker.** `/api/v1/workflows/ap/{id}/execute` heeft geen gebruiker-dependency en een `tenant_id` uit de query (`workflow_execution_ap_router.py:252-255`).
7. **Middel: `receivables:write` is breder dan `receivables_propose`.** Een token in een flow kan op `betaald` zetten en weer terug.
8. **Middel: vrije `database_query`- en `code`-stappen** (`transformer.py:311,322`).

## Advies

1. **Een eigen blok "Debiteuren" in de builder, als enige manier om een debiteur te benaderen.** Het blok heeft twee acties: "herinnering voorstellen" en "aanmaning voorstellen".
   - Het roept de ToolBroker aan (`send_payment_reminder`) of `start_reminder_proposals`, onder de identiteit van de **maker van de flow**. Die wordt bij het publiceren vastgelegd en bij elke run opnieuw gecontroleerd op `receivables_propose`.
   - Het resultaat is altijd een HITL-ticket. Vier-ogen weigert de maker als goedkeurder, ook als de maker een beheerder is.
   - Verzenden blijft uitsluitend via `outgoing_messages` en `verstuur_klare_berichten`, dus met de betaald-check, de dubbelverzendbeveiliging en het rate limit.
2. **Bij publiceren of aanzetten van een flow met een uitgaande stap een classificatie per `piece.actie` afdwingen** (B12, `tool_risk_levels.yml`). Een uitgaande stap (mail, bericht, HTTP-POST of PUT, betaling) wordt geweigerd zonder HITL-keuze. Het eenvoudigst voor de pilot: zulke stappen uitzetten. Dit staat in de servercontrole van `toggle` en `create`, niet alleen in de UI.
3. **Ontvangers controleren tegen het debiteurenbestand.** Komt het adres van een uitgaande stap voor als `customer_email` van een debiteur van de tenant, dan wordt de stap geblokkeerd of omgeleid naar het debiteurenblok.
4. **Rechten aanscherpen.** De AP-routes krijgen een rol of scope (bijvoorbeeld `workflows:write` en `workflows:publish`). `/api/v1/workflows/ap/{id}/execute` krijgt `get_current_user` en de tenant uit de JWT, of wordt verwijderd.
5. **De status `herinnerd` alleen via een verzonden bericht.** Haal `herinnerd` uit de PATCH-schema (`schemas.py:43`), of laat `volg_debiteuren_op` alleen escaleren als er een `outgoing_messages`-rij met `verzonden` voor dat dossier bestaat.
6. **Elke AP-run en elke piece-actie in het audit-log** vastleggen, met `flow_id`, de maker en de goedkeurder.
7. **Eerst B2 en B4 bouwen** (een AP per tenant, geen terugval) voordat klanten flows maken.
8. **Tests toevoegen** voor de lijst onder "Ontbreekt" in paragraaf 5.

## Wat niet is vastgesteld

- Of een globale auth-middleware de route zonder gebruiker-dependency alsnog afschermt.
- Of de frontend de `ap_<naam>`-route en de vrije stappen al aan klanten aanbiedt; de frontend is niet gelezen.
- Hoe AP 0.92.1 schema- en webhooktriggers in onze opzet echt draait. ADR-040 noemt publiceren en uitvoeren nog defect (`:71-72`). Een deel van de risico's is dus latent: "latent" is geen borging.
