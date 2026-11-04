# ADR-040: Workflowbuilder met ActivePieces -- een eigen installatie per tenant

## Status

Accepted (Rakesh, 2026-10-06)

## Datum

2026-10-06

## Auteur

Claude (rol architect), op verzoek van de regie, op basis van de besluiten van Rakesh van
2026-10-06. Dit is een voorstel. Alleen Rakesh zet de status op `Accepted`.

**Review-datum:** 2026-11-05 (30 dagen). Staat dit dan nog op `Proposed`, dan vraagt het een
besluit of verwijdering.

**Peildatum code:** commit `7c95780f` (2026-10-06); de tweede route (2.7, B10 t/m B13) is
gemeten op commit `b3841e48`. Regelnummers hieronder staan op `7c95780f`, tenzij `b3841e48`
erbij staat. Gegevens over AP zelf komen uit de AP-bron op tag `0.92.1`
(`github.com/activepieces/activepieces`, tag `0.92.1`, door mij gelezen via
`raw.githubusercontent.com`), niet uit een lokale kopie. "Gemeten" betekent: een commando of aanroep is uitgevoerd en de
uitkomst is gezien. "Gelezen" betekent: de code is geopend, niet gedraaid.

**Geen juridisch advies.** Licentietekst hieronder is een technische lezing van de bron die
bij elke bewering staat. Een jurist moet hem beoordelen voordat een klant erop vertrouwt.

---

## 1. Samenvatting in gewone taal (een halve pagina)

**Wat we willen.** Een klant bouwt zijn eigen workflow in ons scherm: "als er een factuur
binnenkomt, stuur dan een mail". Dat werkt alleen als er honderden koppelingen zijn met
programma's die de klant al gebruikt (Outlook, Slack, HubSpot, enzovoort). Die zelf nabouwen
en onderhouden is eerder afgewezen. ActivePieces (AP) is een bestaand programma dat die
koppelingen heeft en bijhoudt. De klant ziet AP niet: het zit achter ons scherm.

**Wat we hebben gekozen.** AP blijft de motor. De licentie staat het toe: bijna alles is
gratis te gebruiken, ook commercieel. De bekende alternatieven vielen af, vooral om hun
licentie.

**Het probleem dat we tegenkwamen.** De gratis versie (Community) laat maar een team-project
toe. Een tweede project geven we gemeten een foutmelding. Een "project per klant" in een
gedeelde AP kan dus niet. De betaalde versies hebben dat wel, maar die willen we niet.

**Het besluit van Rakesh.** Elke klant (tenant) krijgt een EIGEN AP, gratis Community-versie,
door ons gehost. Wij bewaren per klant waar die AP staat en met welk beheeraccount wij erin
kunnen, versleuteld. Het voordeel: klanten delen niets met elkaar. Het nadeel: per klant een
stukje hosting, en een klant aanzetten is een uitrol. Voor de pilot doen we dat met de hand.

**Twee manieren waarop klanten de koppelingen gebruiken.** Dit ADR ging eerst alleen over de
eerste. (1) De klant bouwt zelf een workflow in ons scherm en AP voert hem uit. (2) Een
agent, bijvoorbeeld de debiteurenagent, gebruikt een koppeling als gereedschap, via de
ToolBroker: onze controlelaag die bepaalt wat een agent mag, of een mens eerst moet
goedkeuren, en alles vastlegt. Voor beide manieren geldt: dezelfde AP van de klant, dezelfde
inloggegevens, dezelfde indeling in "gevaarlijk of niet" en dezelfde regel dat een mens
goedkeurt bij een uitgaande actie (zoals een mail versturen). Een agent praat nooit rechtstreeks
met AP; alles gaat via de ToolBroker. De koppeling zelf draait in de AP van de klant, zodat de
sleutels van de klant daar blijven. Of dat technisch zo kan, is nog niet gemeten (2.7).

**Wat we NIET doen.** Geen eigen koppelingen voor Nederlandse boekhoudpakketten (Exact Online,
SnelStart, Moneybird, enzovoort): die zitten niet in AP en de pilotklant is nog onbekend.
Financiele gegevens gaan voor de pilot met de hand (invoer van debiteuren bestaat al).
Zodra er een klant is met een bekend pakket, kunnen we een eigen koppeling bouwen; dat mag
licentietechnisch.

**Wat dit vervangt.** In de brief voor de workflowbuilder stond "een project per klant in een
gedeelde AP". Dat kan niet in de gratis versie en vervalt.

**Wat nog moet.** Een deel is bekend defect: opslaan geeft een lege flow, uitvoeren geeft een
404, publiceren geeft een fout. Dat staat in de brief met bron en blijft daar het werk.

---

## 2. Context en bevindingen

### 2.1 Waarom AP -- bronnen

| Bevinding | Bewijs |
|---|---|
| Doel van de integratie: 400+ koppelingen ("pieces") toevoegen, volledig white-label: "frontend hoeft NIET te weten dat ActivePieces bestaat". | `docs/6-Development/old-implementation/ACTIVEPIECES_INTEGRATION_IMPLEMENTATION_PLAN.md:14` en `:16` (gelezen op `7c95780f`). Plan is van 2026-01-16. |
| De klant bouwt in ons scherm; onze code vertaalt onze stappen naar AP-pieces. | `src/core/activepieces/transformer.py:291` (`_map_agent_to_piece`), mapping `:297-315`. Gelezen. |
| Onze eigen `workflow_engine.py` is voor samenwerkende AI-agents, niet voor koppelingen met externe programma's. | `src/core/agents/workflow_engine.py` -- besluit regie 2026-10-06; de inhoud van dat bestand is door mij niet opnieuw doorgelezen. |
| Zelf nabouwen of kopieren is eerder afgewezen omdat AP het onderhoud doet. | Uitspraak Rakesh, 2026-10-06. Geen document gevonden dat dit eerder vastlegt; dit ADR legt het vast. |

### 2.2 Licentie -- bron en alternatieven

Bron: `https://raw.githubusercontent.com/activepieces/activepieces/main/LICENSE`. Volgens die
tekst is alles MIT, behalve `packages/ee/` en `packages/server/api/src/app/ee`. Pieces zijn
dus gratis, ook commercieel. Dit is via de regie aangeleverd; ik heb de URL in deze sessie
niet zelf opnieuw geopend (zie paragraaf 9).

Afgevallen alternatieven, met de reden zoals de regie ze heeft aangeleverd (niet door mij
opnieuw nagelezen):

| Alternatief | Reden van afwijzing |
|---|---|
| n8n | Sustainable Use License: alleen interne bedrijfsdoeleinden, niet aan betalende klanten aanbieden |
| Windmill (CE) | geen managed service of inbedding zonder afspraak |
| Automatisch | AGPL, kleiner |
| Node-RED | Apache, maar geen zakelijke koppelingen met login |

### 2.3 Wat de Community-editie wel en niet kan (gemeten)

Gemeten in de draaiende lokale AP (`EDITION: ce`, versie 0.92.1, `GET /api/v1/flags`,
2026-10-06, door de regie):

| Meting | Uitkomst |
|---|---|
| Aantal projecten | 1 PERSONAL en 1 TEAM. Een tweede `POST /v1/projects` gaf 402 `FEATURE_DISABLED`: "Maximum limit of 1 team project(s) reached for this plan". |
| API-sleutels en ingebedde login | Alleen in Cloud en Enterprise. |
| Inloggen met e-mail en wachtwoord | Werkt in CE: `POST /v1/authentication/sign-in`. |

Gevolg: de eis uit de eerdere brief ("een project per tenant") is in CE gemeten onmogelijk.
Dat was in die brief als "niet gemeten" opgenomen en is nu gemeten
(`docs/agent-briefs/generated/2026-10-06-sprint-dag-workflowbuilder-echt-werkend.md:387`,
stopvoorwaarde `:351`).

### 2.4 Wat er nu in onze code staat (gelezen)

| Bevinding | Bewijs |
|---|---|
| `find_project_for_tenant` negeert `tenant_id` en geeft het eerste project, anders `"default"`. Een tenant ziet dus elders alles van een ander. | `src/core/activepieces/client.py:482-489` |
| `get_tenant_ap_project` valt bij een fout terug op `str(tenant_id)` als project-id. | `src/core/activepieces/tenant_utils.py:8` (functie), terugval `str(tenant_id)` op `:25` en `:33` |
| Een tweede pad naar AP buiten `ActivePiecesService` om, met rechtstreeks httpx, en een sleutel die niet bestaat in de configuratie. | `src/core/api/v1/focus_builder/agents.py:95` (`getattr(app_config, "activepieces_api_key", None)`), `:106` (httpx-aanroep, zie `async with httpx.AsyncClient` rond `:105-110`), `:134` (`get_tenant_ap_project`); `src/core/services/focus_builder_service.py:32` |
| De configuratie kent een enkele, globale AP-URL en een enkel wachtwoord voor het service-account. Er is dus geen per-tenant gegeven. | `src/core/config/unified_config.py:281` (`activepieces_api_url`), `:283` (`activepieces_password`) |
| `ACTIVEPIECES_API_URL` heeft twee betekenissen: pieces-URL in de syncer, basis-URL elders. | `src/core/activepieces/catalog_syncer.py:21` (default `.../api/v1/pieces`), `src/core/monitoring/health_checks.py:311`, `src/core/config/unified_config.py:281` |
| Bij ontbrekende gegevens schakelt de service stil over op een uitgeschakelde client. | `src/core/activepieces/service.py:328` e.v. |
| Uitvoermodus in compose is `SANDBOXED` zonder privileged container. | `docker-compose.yml:354` |

### 2.5 De catalogus (gemeten)

`GET /api/v1/pieces` tegen de lokale AP, 2026-10-06: 766 pieces. Lijst:
`scratch/activepieces-koppelingen-2026-10-06.csv` (766 datarijen; het bestand is **niet in
git**, zie paragraaf 9).

Inlogsoorten, door mij herteld uit dat CSV met een Python-telling op kolom "Inloggen":

| Soort | Aantal |
|---|---|
| SECRET_TEXT (een sleutel) | 377 |
| CUSTOM_AUTH (eigen velden) | 204 |
| OAUTH2 | 95 |
| geen inlog | 46 |
| meerdere inlogsoorten (lijst) | 33 |
| BASIC_AUTH | 11 |

Ter vergelijking: de regie meldde "geen 79". Dat is 46 plus 33; de 33 zijn pieces met
meerdere mogelijke inlogsoorten, niet pieces zonder inlog. Zie paragraaf 4.3 voor wat dat
doet met het scope-getal.

Wat onze builder nu kent: 11 pieces in het CSV hebben "ja" in de kolom "Nu in onze builder".
`_map_agent_to_piece` (`transformer.py:291-322`) kent 20 stapnamen die op 11 verschillende
pieces uitkomen, plus een terugval op `@activepieces/piece-code`. Die laatste bestaat NIET in
de catalogus (gemeten: geen rij met die technische naam); code is in AP een ingebouwd staptype
en geen piece. Elke onbekende stapnaam wordt dus nu een stap met een niet-bestaande piece:
een defect.

### 2.6 Het gat in de Nederlandse markt (gemeten in dezelfde catalogus)

Afwezig: Exact Online, SnelStart, Moneybird, Twinfield, AFAS, e-Boekhouden, Nmbrs, Loket,
Youforce, Personio, Wix, Lightspeed, Bol, Google Ads. Aanwezig o.a.: Outlook, Teams, Excel,
SharePoint, OneDrive, Gmail, Slack, WhatsApp Business, HubSpot, Salesforce, Dynamics (incl.
Business Central), Pipedrive, Teamleader, Shopify, WooCommerce, Mollie, Stripe, Zendesk,
Freshdesk, Asana, monday, Jira, Planner, DocuSign.

Door de regie gemeten; ik heb de afwezigheid niet voor elke naam herhaald (zie paragraaf 9).

### 2.7 De tweede route: agents gebruiken pieces als tools (gemeten op `b3841e48`)

| Bevinding | Bewijs |
|---|---|
| Een registry meldt AP-pieces aan als MCP-servers: 3 pieces (gmail MEDIUM, google-calendar LOW, slack MEDIUM) en standaardtools per afdeling (sales, marketing, finance, hr, support, operations). | `src/core/tool_broker/ap_mcp_registry.py:21-25`, `:28-35` (b3841e48). Gelezen. |
| `build_server_params` start per piece `node node_modules/<pakket>/dist/index.js --mcp` via stdio, negeert `tenant_id` en geeft de inlog mee in de omgevingsvariabele `AP_PIECE_AUTH`. | `ap_mcp_registry.py:52-58` (b3841e48). Gelezen. |
| `build_server_params` heeft geen aanroeper in `src/`. | `git grep -n "build_server_params" b3841e48 -- src` geeft alleen de definitie (gemeten). Er is een unit-test: `tests/unit/test_ap_mcp_registry.py:29`. |
| `node_modules/@activepieces` bestaat niet in de repo-root. | Door de regie gemeten; niet door mij herhaald. |
| Of een piece-pakket een `--mcp`-modus heeft: niet gemeten. | Zie paragraaf 9. |
| De enige gebruiker van de registry is de afdelingsactivatie. Die logt per standaardtool "tool_registered" maar voegt niets toe aan de allowlist (commentaar in de code: "In production, this would call ToolBroker to add to allowlist"). | `src/core/events/department_activation_handler.py:29-35` (b3841e48). Gelezen. |
| De ToolBroker-client kent alleen stdio-servers. | `src/core/tool_broker/mcp_client.py:14` (`from mcp.client.stdio import stdio_client`, b3841e48). Gelezen. |
| In `config/tool_permissions.yml` staan nu minstens drie agentprofielen: `copilot`, `skillsgaptraining`, `dunning`. ADR-037 G10 zegt "enige profiel is `copilot`" (gemeten 2026-07-07). G10 is dus verouderd. | `config/tool_permissions.yml:38`, `:68`, `:110` (b3841e48) via `grep -n agent_id`. |
| Het risiconiveau van de ToolBroker staat in `src/core/config/tool_risk_levels.yml:14` (b3841e48), naast een tweede, losse risicolijst in de registry (`ToolRisk`, `ap_mcp_registry.py:12`). Twee bronnen voor hetzelfde begrip. Of ze elkaar tegenspreken is niet vergeleken. | Gelezen. |

**AP 0.92.1 heeft zelf een ingebouwde MCP-server** (gelezen in de AP-bron, tag `0.92.1`):

- Docs: `docs/mcp/overview.mdx` ("Activepieces includes a built-in MCP server"; adres
  `https://<instance>/mcp`; aanmelding via OAuth in de browser van de gebruiker).
- Hij wordt geregistreerd in de gedeelde opstartlijst:
  `packages/server/api/src/app/app.ts:256-259` (`mcpServerModule` e.a.), vlak voor de
  edition-specifieke blokken die de brief op regel 351-399 noemt (gelezen). Of hij in
  Community daadwerkelijk antwoordt: niet gemeten.
- De beheerroutes zijn `/v1/projects/:projectId/mcp-server` en `/v1/mcp-server`
  (`packages/server/api/src/app/mcp/mcp-module.ts`), met onder meer `POST .../token`
  (`mcp-server-controller.ts:33`). Dat past bij de 404 op `/api/v1/mcp-servers` en
  `/api/v1/mcp` die de regie mat: die geraden routes bestaan niet, deze (gelezen, niet
  aangeroepen) wel.
- `docs/mcp/tools.mdx` noemt het gereedschap `ap_run_action`: "Execute a single piece action
  once without building or saving a flow ... runs directly in the engine". Het gebruikt een
  bestaande verbinding via `connectionExternalId`; `docs/mcp/overview.mdx`, sectie "Security",
  zegt: "Credentials are never exposed".

Dat is wat de agentroute nodig heeft: een piece-actie uitvoeren met de sleutels van de klant,
zonder dat die sleutels bij ons komen. Dat het zo werkt is uit documentatie gelezen, niet
gemeten.

---

## 3. Besluiten

**B1. AP blijft de motor voor koppelingen met externe programma's.** De klant bouwt in ons
scherm; AP is niet zichtbaar. Onze eigen agent-workflowmotor blijft voor samenwerkende
AI-agents en wordt hier niet voor gebruikt.

**B2. Elke tenant krijgt een eigen, gratis, self-hosted AP Community-installatie, door ons
gehost.** Geen AP Cloud, geen Enterprise. Dit vervangt besluit 2 ("een AP-project per tenant")
uit de brief van 2026-10-06 (`...echt-werkend.md`, Regie-besluiten, rond regel 170).

**B3. Per tenant bewaren wij het adres van die AP en de inloggegevens van het beheeraccount,
versleuteld.** Wij loggen in met e-mail en wachtwoord (`POST /v1/authentication/sign-in`,
gemeten in CE). De klantgebruiker logt nooit in AP in; hij werkt in ons scherm.

**B4. De tenant-scheiding zit in het opzoeken van de verbinding.** Het adres en de
inloggegevens worden opgezocht met de `tenant_id` uit de JWT (ContextVar), nooit uit een
request body, queryparameter of payload (CLAUDE.md, NOOIT-lijst). Ontbreekt de verbinding voor
die tenant, dan is dat een fout: nooit een terugval op een andere tenant, nooit op een
algemene AP, nooit `projects[0]`, nooit `"default"`, nooit `str(tenant_id)`.

**B5. Een tenant aanzetten is een uitrol, dus interlock 2.** Voor de pilot gebeurt dat met de
hand en alleen na het woord van Rakesh. Automatiseren is een later besluit (paragraaf 7).

**B6. Het tweede pad vervalt.** `focus_builder/agents.py` en `focus_builder_service.py` gaan
via dezelfde per-tenant verbinding en via `ActivePiecesClient`, niet met eigen httpx en een
niet-bestaande sleutel. Er blijft een enkele toegangsweg tot AP.

**B7. Overgenomen uit de brief van 2026-10-06 (ongewijzigd):**
- uitvoermodus `SANDBOX_CODE_ONLY` (zie 5.1 voor wat de reden hier lichter weegt);
- opslaan via `IMPORT_FLOW` met `schemaVersion` van de actuele server;
- uitvoeren via `LOCK_AND_PUBLISH`, `CHANGE_STATUS` en een webhook;
- `ACTIVEPIECES_API_URL` is overal de basis-URL `.../api/v1`;
- bij uitgaande acties mens-in-de-lus volgens ADR-039, op BEIDE routes (B10 t/m B13).

**B8. Catalogus: een generieke weergave per piece, gebaseerd op wat AP over de velden
teruggeeft, en een generieke inlogstap per soort** (sleutel, OAuth2, geen). De 18
stapsoorten en 12 handmatige afbeeldingen van nu zijn geen bovengrens meer. Een piece wordt
pas beloofd aan een klant als hij is getest ("alleen getest = beloofd").

**B9. Geen eigen koppelingen voor Nederlandse pakketten in de pilot.** De pilotklant is
onbekend. Financiele gegevens gaan met de hand (handmatige invoer debiteuren, BE-DEB-001).
Een eigen piece bouwen mag later (MIT, 2.2) zodra een klant met een bekend pakket er is.

**B10. De ToolBroker is de ENIGE weg waarlangs een agent een AP-piece gebruikt.** Allowlist
per agentprofiel, risiconiveau, HITL en SHA-256-audit gelden daarmee voor elke
piece-actie van een agent, in lijn met ADR-015 en ADR-037. Geen agent, skill of service praat
rechtstreeks met AP. De AP-aanroep zelf zit achter een adapter van de ToolBroker; een
architectuurtest bewaakt dat buiten `src/core/activepieces/` en die adapter niets AP aanroept
(zelfde test als B6).

**B11. Bij de agentroute draait het piece in de AP-installatie van de tenant, niet als lokaal
node-proces.** Concreet: de ToolBroker-adapter roept de ingebouwde MCP-server van de AP van de
tenant aan (`ap_run_action`, 2.7) met een verbinding (`connectionExternalId`) die de klant of
ICT in die AP heeft ingericht. De stdio-aanpak van `ap_mcp_registry.build_server_params`
(`node node_modules/...`) wordt NIET de bouwroute (reden: 5.3). **Voorwaarde voor bouwen:** de
metingen M1 tot en met M4 in paragraaf 9 moeten slagen. Falen ze, dan komt dit terug bij de
architect met een wijziging van dit ADR; het stdio-pad wordt niet stilletjes de terugval.

**B12. Een bron voor risico en HITL per piece-actie, voor beide routes.** Er komt een
classificatie per `piece.actie` (voorbeeld `gmail.send_email`) in de bestaande lijst
`src/core/config/tool_risk_levels.yml`. De workflowroute (B7, onderdeel 7 van de brief) en de
agentroute lezen dezelfde lijst. De tweede lijst in de registry (`ToolRisk`) vervalt. Een
uitgaande actie (mail, bericht, betaling, schrijven naar een extern systeem) vraagt op beide
routes mens-in-de-lus volgens ADR-039; vier ogen volgt de instelling van de gebruiker. De
huidige classificatie "gmail en slack zijn MEDIUM" (`ap_mcp_registry.py:22`, `:24`) is dus
niet het eindpunt: of MEDIUM volstaat voor het versturen van een mail beslist de bouwer met
de lijst en ADR-039 erbij, niet de registry.

**B13. Standaardtools per afdeling worden allowlist-profielen via de ToolBroker, in de
pilot alleen voor wat de pilot gebruikt.** `DEPARTMENT_DEFAULT_TOOLS` (`:28-35`) blijft als
voorstel, maar de handler die alleen logt (`department_activation_handler.py:29-35`) wordt
een van twee dingen: een echte schrijfactie naar het agentprofiel (profiel per agenttype, bijv.
`dunning`, in `config/tool_permissions.yml`) OF hij verliest de log "tool_registered", die nu
beweert dat iets is geregistreerd terwijl dat niet gebeurt. Voor de pilot (debiteuren, finance)
is alleen het profiel voor finance in scope; de andere vijf afdelingen volgen pas met hun eigen
brief. Reden: een profiel voor een afdeling die niemand gebruikt maakt het allowlist-oppervlak
groter dan nodig, terwijl default-deny (ADR-037 G10) de afdelingen zonder profiel veilig laat.

---

## 4. Scope

### 4.1 WEL in scope

1. Een bewaarplek per tenant voor AP-adres en versleutelde inloggegevens, met opzoeken via
   `tenant_id` uit de JWT (B3, B4).
2. De `ActivePiecesClient` verbindt per tenant in plaats van met een globaal service-account
   (de globale velden uit 2.4 gaan op in de per-tenant verbinding).
3. Een enkele toegangsweg: ook de focus-builder (B6), bewaakt met een architectuurtest.
4. De bekende defecten uit de brief (opslaan leeg, uitvoeren 404, publiceren 400,
   `SANDBOXED`, twee betekenissen van de URL) blijven werk in die brief en gelden hier als
   scope.
5. Generieke weergave en generieke inlogstap voor pieces met sleutel, OAuth2 en zonder inlog
   (B8).
6. HITL bij uitgaande acties volgens ADR-039 (vier ogen is een instelling van de gebruiker),
   op beide routes.
7. De agentroute (B10 t/m B13): een ToolBroker-adapter naar de AP van de tenant, een HTTP-
   transport naast stdio in `mcp_client.py`, een gedeelde risicolijst per `piece.actie`, en
   een echt profiel voor de finance-agent. Meetvolgorde: eerst M1 t/m M4 (paragraaf 9).

### 4.2 NIET in scope

- AP Cloud of Enterprise; ingebedde login; API-sleutels per project.
- Eigen koppelingen voor Exact Online, SnelStart, Moneybird, Twinfield, AFAS, e-Boekhouden,
  Nmbrs, Loket, Youforce, Personio, Wix, Lightspeed, Bol of Google Ads.
- Klanten die eigen pieces uploaden (blijft uit; wij bepalen welke pieces aan staan).
- Automatisch uitrollen van een AP per nieuwe tenant.
- Pieces met `CUSTOM_AUTH` (204) en `BASIC_AUTH` (11): geen generieke inlogstap in de pilot.
- OAuth2 per programma anders dan na een aparte registratie (zie 4.3).
- Het uitrollen van standaardprofielen voor sales, marketing, hr, support en operations.
- ADR-037 Fase 2 (ToolBroker als MCP-server voor externe hosts): hier alleen geraakt voor zover
  de adapter van B11 de client-kant is. Fase 2 zelf blijft ADR-037.
- De ingebouwde MCP-server van AP openstellen voor klanten of externe agents: nee; alleen onze
  ToolBroker praat ermee.

### 4.3 Wat "generieke login" in aantallen betekent

Met de telling uit 2.5: sleutel (377) plus OAuth2 (95) plus geen inlog (46) is **518 van
766**. De regie noemde 551; dat telde 33 pieces met meerdere inlogsoorten mee als "geen". Die
33 zijn pas dekkend als hun inlogvormen apart zijn bekeken. Tot dat is gebeurd is het getal
dat we mogen noemen 518, niet 551.

OAuth2 (95) vraagt per programma een app-registratie bij ons, bij dat programma. Zonder die
registratie werkt een OAuth2-piece niet; "generiek" betekent dus alleen dat de schermcode
generiek is, niet dat het zonder werk gaat.

---

## 5. Kwaliteitsattributen en spanningen

| Attribuut (ISO 25010) | Weging | Spanning |
|---|---|---|
| Beveiliging (vertrouwelijkheid, scheiding) | Hoogst | Een eigen AP per tenant geeft de sterkste scheiding (eigen proces, eigen database), maar wij bewaren een wachtwoord dat bij een lek toegang geeft tot alle AP's. |
| Onderhoudbaarheid | Hoog | N installaties betekent N keer upgraden. De gekozen versie moet gepind blijven (nu 0.92.1, commit `aadb311d`). |
| Bruikbaarheid (functionele geschiktheid) | Hoog | Veel koppelingen (766) maar het NL-gat is echt; de klant mist Exact en AFAS. |
| Prestatie en kosten | Midden | Kosten is hosting per tenant (AP-container en eigen database); niet in euro's gemeten. |
| Betrouwbaarheid | Midden | Per tenant een kleinere schade bij uitval, maar meer onderdelen die kunnen uitvallen. |
| Draagbaarheid | Midden | Het model past op ADR-035 (een tenant, meerdere gebruikers): daar wordt het een installatie. |

### 5.1 Afweging: uitvoermodus

**Afweging.** `SANDBOX_CODE_ONLY` blijft de keuze (door Rakesh overgenomen uit de brief). De
reden uit de brief was "de enige modus die de makers multi-tenant-veilig noemen"
(`...echt-werkend.md:162-169`; docs-citaat uit die brief, niet door mij nagelezen). Met een
AP per tenant delen klanten geen engine-proces meer, dus die reden weegt hier lichter. De modus
blijft nodig omdat Azure Container Apps `privileged` niet toestaat en omdat gebruikers binnen
een tenant elkaars Code-stappen niet in het hoofdproces moeten kunnen bereiken.

```
Aanname: SANDBOX_CODE_ONLY wordt geaccepteerd door de startcontrole van AP Community
0.92.1 en publiceren werkt erin.
Toets: eerste lokale start met AP_EXECUTION_MODE=SANDBOX_CODE_ONLY, daarna
LOCK_AND_PUBLISH en een run via de brief (onderdeel 3). Review: 2026-11-05.
```

### 5.2 Afweging: een AP per tenant tegenover een gedeelde AP

**Afweging.** Per tenant is duurder maar de enige route zonder betaalde licentie waarbij de
scheiding in AP zelf zit en niet alleen in onze code.

```
Aanname: de hostingkosten per tenant (AP-container plus eigen database op een gedeelde
databaseserver) zijn voor de pilot en de eerste klanten aanvaardbaar.
Toets: meet op staging het geheugen en de CPU van een AP-container in rust en onder een run,
tel dat bij het aantal verwachte tenants, vraag Rakesh of dat past in de prijs per klant.
Review: voor de tweede tenant, uiterlijk 2026-11-05.
```

### 5.3 Afweging: waar draait het piece bij de agentroute

**Afweging.** Twee serieuze opties, B11 kiest de eerste.

| | A. In de AP van de tenant (`ap_run_action`) | B. Lokaal node-stdio-proces (de registry nu) |
|---|---|---|
| Waar liggen de sleutels van de klant | In AP, bij de verbinding. Wij bewaren alleen het beheeraccount (B3). | In onze ToolBroker-omgeving (`AP_PIECE_AUTH`, `ap_mcp_registry.py:54`): per piece een geheim van de klant bij ons. |
| Tenant-scheiding | Volgt B4: de verbinding is van die tenant. | De registry negeert `tenant_id` (`:52-58`); scheiding moet nog bedacht worden. |
| Dezelfde uitvoering als workflows | Ja: dezelfde engine, dezelfde sandbox-modus (B7). | Nee: een tweede manier om pieces te draaien, buiten de sandbox van B7. |
| Bewijs dat het werkt | Documentatie in de AP-bron (2.7); nog niet aangeroepen. | Geen: geen aanroeper, geen `node_modules`, `--mcp` niet gemeten. |
| Voor ons te bouwen | HTTP-client voor MCP (nu alleen stdio, `mcp_client.py:14`), verbinding per tenant. | Pakketten installeren, procesbeheer, upgrades per piece. |
| Risico | Afhankelijk van AP-MCP (editie, authenticatie voor een backend: niet gemeten). | N pakketten bijhouden die AP zelf al bijhoudt: dat is wat we met AP juist wilden voorkomen (2.1). |

```
Aanname: de ingebouwde MCP-server van AP 0.92.1 CE is aan, bereikbaar met een token en laat
`ap_run_action` toe voor een gewone beheerdersgebruiker.
Toets: M1 tot en met M4 in paragraaf 9, tegen de lokale AP 0.92.1. Review: voor de bouw
begint, uiterlijk 2026-11-05.
```

---

## 6. Alternatieven

| Alternatief | Waarom afgewezen |
|---|---|
| **Een gedeelde AP met een project per tenant** (besluit 2 van de eerdere brief) | Community laat een tweede team-project niet toe (402, gemeten, 2.3). Betaald alternatief nodig. |
| **AP Cloud of Enterprise** | API-sleutels en ingebedde login zitten alleen daar (bron: brief, onderdeel "ActivePieces 0.92.1 -- uit de bron", app.ts regel 351-399 in de fork). Rakesh wil geen AP Cloud. Prijs niet gemeten; geen prijsclaim in dit ADR. |
| **Een gedeelde AP zonder projectscheiding, scheiding alleen in onze code** | De scheiding zou dan alleen op `tenant_id`-filters berusten; een enkel gemist filter lekt flows tussen klanten. Dit is exact wat nu in `client.py:482` fout gaat. |
| **Zelf alle koppelingen nabouwen** | Eerder afgewezen (onderhoud). Honderden koppelingen met elk hun eigen API-veranderingen. |
| **n8n, Windmill CE, Automatisch, Node-RED** | Licentie of omvang (2.2). |
| **Agentroute: lokaal node-stdio-proces per piece (de registry zoals hij nu is)** | Sleutels van de klant bij ons, `tenant_id` genegeerd, tweede uitvoerpad buiten de sandbox, niets bewezen (5.3). Niet als bouwroute gekozen; ook niet als stille terugval (B11). |
| **Agentroute: agents praten rechtstreeks met AP** | Omzeilt allowlist, risico, HITL en audit van ADR-015 en ADR-037. Uitgesloten door B10. |
| **Agentroute: een eigen ToolBroker-tool per piece, met eigen code naar de API van het programma** | Is het "zelf nabouwen" dat eerder is afgewezen (2.1). |
| **Een eigen workflowmotor voor externe koppelingen** | De motor in `workflow_engine.py` is voor samenwerkende AI-agents, niet voor externe programma's (B1). |

---

## 7. Gevolgen

1. **Migratie en gegevens.** Nieuwe tabel of kolommen voor adres en versleutelde
   inloggegevens per tenant. Dat is een migratie (interlock 1: vooraf aankondigen, werkende
   `downgrade()`) en het bewaart een geheim. De vorm kies ik hier niet vast; de bouwer
   kiest hem binnen B3 en B4. De kolom `tenants.activepieces_project_id` uit de eerdere brief
   (onderdeel 1, `...echt-werkend.md:207`) vervalt.
2. **Versleuteling.** In de repo staat een Fernet-gebaseerde `src/core/security/secret_manager.py`
   (`:2-15`, sleutel uit `MASTER_ENCRYPTION_KEY`). Ik heb niet vastgesteld of die geschikt is
   voor dit gebruik (hij schrijft naar `os.environ`, `:157`); dat moet de bouwer meten voordat
   hij hem hergebruikt.
3. **Rotatie van het beheerwachtwoord** is een interlock (secret-rotatie) en hoort bij de
   uitrolprocedure per tenant.
4. **Brief van 2026-10-06 verschuift.** Onderdeel 1 (tenantscheiding) verandert van "project
   per tenant" naar "verbinding per tenant". Stopvoorwaarde "Community staat geen tweede project
   toe" (`:351`) is bevestigd en vervalt als stop: het is nu de reden voor dit besluit. De
   backfill van projecten (`:209-211`) vervalt. De brief zelf is hier niet gewijzigd.
5. **De staging-brief** (`2026-10-05-sprint-dag-activepieces-naar-staging.md`) gaat uit van een
   AP. Een AP per tenant betekent dat staging per tenant een container en database nodig
   heeft; dat is een aanpassing in die brief, door mij niet doorgelezen.
6. **Pilot december 2026** (gedeelde server, ook single tenant, ADR-035): in single-tenant is
   er een tenant en dus een AP; het model is hetzelfde.
7. **HITL.** Vier ogen en mens-in-de-lus bij uitgaande acties volgen ADR-039
   (`docs/adr/039-rollen-en-bevoegdhedenmodel-in-drie-lagen.md`). Vandaag bestaat daarvoor in
   de AP-koppeling niets: grep op `hitl|approval` in `src/core/activepieces` en
   `src/domains/flows` gaf 0 treffers (bron: brief, `:111-115`; niet door mij herhaald).
8. **Twee routes, een bron.** De classificatie per `piece.actie` (B12) wordt op twee plekken
   gelezen: de workflowroute (publiceren weigert een flow met een uitgaande stap zonder
   keuze) en de agentroute (ToolBroker). Wijkt een van beide af, dan gelden voor hetzelfde piece
   twee regels; een architectuurtest die beide routes op dezelfde lijst laat steunen is dus
   onderdeel van het werk.
9. **De agentroute heeft een ingerichte verbinding nodig.** Een agent gebruikt een verbinding
   die iemand in de AP van de tenant heeft ingericht (technisch beheer, ADR-039 laag 2a).
   Zonder verbinding is de tool niet beschikbaar en geeft de ToolBroker een duidelijke fout;
   nooit een terugval op een andere tenant (B4).
10. **Upgrades.** Een versie-upgrade van AP geldt voor N installaties. Het versieverschil kan
   de opslagvorm raken (de dubbele verpakking bij `schemaVersion` zonder waarde, brief
   `:140-143`). Dat geldt ook voor de MCP-ingang van AP: toolnamen en gedrag staan in de
   AP-docs van die versie en moeten per upgrade opnieuw worden gemeten.

---

## 7a. Welke andere ADR's dit raakt

Gezocht met `git grep -i -E "activepieces|workflow.?builder" -- docs/adr` plus een lezing van
de ADR's die de besluiten hierboven inhoudelijk raken (2026-10-06, commit `0ca5aa76`).
"Moet mee" betekent: die ADR klopt niet meer zodra B2 gebouwd is, en krijgt dan een
aanvulling die naar deze ADR verwijst. Deze ADR wijzigt ze zelf niet.

| ADR | Wat er nu staat | Wat ADR-040 eraan verandert | Moet mee? |
|---|---|---|---|
| 005 RLS en `tenant_id NOT NULL` | Elke tabel met tenantgegevens krijgt `tenant_id NOT NULL` en een RLS-policy | De nieuwe opslag van de AP-verbinding per tenant (B3) valt hieronder: `NOT NULL` + policy + isolatietest. Zie ook OP-155 in `036-REGISTER-OVERIG-EN-AFGEROND.md:166` (27 tabellen zonder policy) -- deze mag er niet bij komen | Nee, wordt toegepast |
| 009 Traefik | `docker-compose.yml` routeert naar EEN `activepieces`-service (`009-edge-gateway-traefik-tls-routing.md:16`) | Met een AP per tenant is er geen enkele AP-route meer. Klanten bereiken AP nooit rechtstreeks (B2); alleen onze backend praat ermee. Lokaal blijft een AP voor ontwikkeling | Ja: de AP-route wordt intern-only |
| 030 Build-stack security | Bevinding F-09: "Activepieces sandbox uitgeschakeld" (`030-build-stack-security-program.md:33`, `:139`) | B7 zet `SANDBOX_CODE_ONLY`. Daarmee sluit F-09, zodra `docker-compose.yml:354` en `cd-staging.yml` echt zijn aangepast | Ja: F-09 sluiten met de meting |
| 031 addendum autonomieladder | `activepieces/client.py:155` gebruikt `tenant_id=0` als "systeem" (`031-addendum-fase5-autonomy-ladder-scope.md:354`) | Gemeten: dat is de egress-controle in `src/core/activepieces/client.py:157` (`tenant_id=0  # system/service tenant`). Met een AP per tenant hoort die controle bij de echte tenant, net als B4 | Nee, maar de bouwer neemt `client.py:157` mee in B4 |
| 033 API-laag | Drie lagen per domein; `router.py` importeert niets rechtstreeks; activepieces staat onder `v1/` (`033-api-layer-service-boundary.md:312`) | B6: `focus_builder/agents.py` praat nu met `httpx` rechtstreeks met AP. Dat gaat via `dependencies.py` naar `ActivePiecesClient`, zoals ADR-033 voorschrijft | Nee, wordt toegepast |
| 034 Agent-runtime | De capability-registry voegt "ActivePieces flows" samen met agents en tools (`034-agent-runtime-service-boundary.md:331`) | Flows zijn nu per tenant, in een eigen AP. De registry mag alleen de flows van de huidige tenant tonen | Ja: aanvulling "flows per tenant" |
| 035 Single-tenant | Een organisatie, meerdere gebruikers, eigen installatie | Past: een single-tenant-installatie heeft precies een eigen AP. Geen tegenspraak | Nee |
| 036 Agentische organisatie | Noemt de workflow-bouwer met versies en changelog (`036-agentic-organizational-hierarchy-governance-reuse.md:127`) | Geen tegenspraak; de versies blijven in onze database, de uitvoering in de AP van de tenant | Nee |
| 037 ToolBroker (en ADR-015 zero-trust) | De ToolBroker is de zero-trust-laag: allowlist per agentprofiel, risico LOW/MEDIUM/HIGH, HITL voor HIGH, SHA-256 audit. Consumeert MCP-servers alleen via stdio (`mcp_client.py:14`, b3841e48). Fase 2 = ToolBroker als MCP-server, Fase 3 noemt "tenant-scoped-MCP" | De ToolBroker is DE weg voor agents naar AP-pieces (B10). Concreet moet mee: (1) Fase 3 tenant-scoped MCP krijgt hier zijn eerste gebruik: een MCP-verbinding per tenant naar de AP van die tenant, met HTTP-transport naast stdio; (2) G9 (`_ToolBrokerAdapter` hardcodet "copilot", `src/core/copilot/council/factory.py:127-138` volgens ADR-037, niet opnieuw gelezen) moet eerst op: de agentroute heeft een echte aanroeper-identiteit nodig; (3) G10 is verouderd: er staan nu 3 profielen (`copilot`, `skillsgaptraining`, `dunning`), de finance-agent krijgt een eigen (B13); (4) de registry `ap_mcp_registry.py` verliest `build_server_params` en de eigen risicolijst, of krijgt een nieuwe vorm (B11, B12); (5) `piece.actie` komt in `tool_risk_levels.yml`. | **Ja** |
| 038 Netwerkgrens | De ingress van Container Apps is de rand; achter de ingress geen eigen IP-controle | Een AP per tenant in Azure is een interne container zonder publieke ingress; alleen onze backend praat ermee | Ja: "AP-containers zonder publieke ingress" vastleggen |
| 039 Rollen en vier ogen | Vier ogen als instelling; technisch beheer (ICT) beheert koppelingen en geheimen | Het invullen van de AP-verbinding van een tenant is technisch beheer (laag 2a). HITL op uitgaande acties volgt de vier-ogen-instelling | Nee, wordt toegepast |

Niet geraakt: de overige ADR's in de index. Daar is alleen op trefwoorden gezocht en niet elke
ADR inhoudelijk gelezen.

## 8. Open vragen

1. Hoe versleutelen we de inloggegevens, en waar staat de sleutel? (Zie 7.2.) Beslist de
   bouwer met de meting erbij; vraagt het een ander besluit dan B3, dan terug naar de architect.
2. Wat gebeurt er met bestaande lokale flows en met tenants zonder AP? B4 zegt: fout, geen
   terugval. De melding aan de klant is een ontwerpkeuze van de bouwer.
3. Hoe weten we dat een AP van een tenant "gezond" is (de bestaande `health_check`,
   `client.py:492`, kent maar een verbinding)? Moet per tenant.
4. De 33 pieces met meerdere inlogsoorten (4.3): welke zijn dekkend?
5. Wat is de uitrolprocedure per tenant (container, database, eerste gebruiker, versleuteld
   opslaan)? Niet ontworpen; voor de pilot met de hand.
6. Welke agent-identiteit gebruikt de agentroute: een profiel per agenttype (`dunning`) of per
   agentinstantie (`finance-<tenant>`, zoals de handler het id vormt:
   `department_activation_handler.py`, regel met `agent_id = f"{event.department}-{event.tenant_id}"`)?
   Aanbeveling: per type, met de tenant uit de JWT; niet gemeten of de huidige permissiecontrole
   dat aankan.
7. Hoe krijgt de ToolBroker een token voor de MCP-ingang van de AP van de tenant? OAuth in een
   browser is voor een mens, niet voor een backend; het `token`-endpoint uit 2.7 is
   waarschijnlijk de route. Meting M2.

---

## 9. Wat niet gemeten is (en aannames met toets)

Niet gemeten, niet nagelezen of alleen van de regie overgenomen:

- De licentietekst (2.2) en de afgevallen alternatieven: via de regie, niet door mij opnieuw
  geopend.
- De 402-meting (2.3) en de vlaggen: door de regie gedaan, niet door mij herhaald.
- Dat een per-tenant AP-container en database op Azure Container Apps werkt, en wat het
  kost: niet gemeten.
- Dat een versie-upgrade van AP geen opgeslagen flows breekt: niet gemeten.
- Het aantal "18 stapsoorten" van onze builder: ik heb dat getal niet teruggevonden in de
  code; wel `_map_agent_to_piece` met 20 namen op 11 pieces plus een terugval. Het getal
  "12 pieces" van de regie komt overeen met 11 plus `piece-code`.
- Dat de afwezigheid van de 14 NL-pakketten in 2.6 klopt voor elke naam: gemeten door de
  regie; ik heb alleen de 11 bestaande stappen in het CSV gecontroleerd.
- `scratch/activepieces-koppelingen-2026-10-06.csv` is **niet in git** (`git ls-files` is
  leeg); de bron van 2.5 kan dus verdwijnen. Opnemen in `docs/` of regenereren met
  `GET /api/v1/pieces` is nodig voordat dit ADR op `Accepted` gaat.
- **De `--mcp`-modus van piece-pakketten** (`ap_mcp_registry.py:57`): niet gemeten. Of
  `@activepieces/piece-gmail` een `dist/index.js` met `--mcp` heeft, is niet vastgesteld;
  `node_modules/@activepieces` ontbreekt (regie). Dit ADR kiest dat pad niet (B11), dus het is
  geen blokkade maar een open feit.
- **Of de ingebouwde MCP-server van AP 0.92.1 in Community antwoordt**, welke authenticatie
  een backend kan gebruiken en of `ap_run_action` een verbinding van de tenant kan gebruiken:
  alleen uit documentatie en bron gelezen, niet aangeroepen (zie M1 tot en met M4).
- Dat de agentroute via MCP binnen de sandbox-modus `SANDBOX_CODE_ONLY` werkt: niet gemeten.
- Of `tool_risk_levels.yml` en `ToolRisk` in de registry elkaar tegenspreken: niet vergeleken.
- Of de MCP-ingang van AP past in onze netwerkopzet (ADR-038, interne container zonder
  publieke ingress): niet gemeten.
- Isolatie van pieces binnen een enkel engine-proces: niet gemeten.
- De prijs van AP Cloud of Enterprise: niet onderzocht, geen claim.
- Welke pieces de AP-gebruikersinterface een klant zou aanbieden: niet gemeten (de klant ziet
  die interface niet).

Metingen die VOOR het bouwen van de agentroute moeten slagen (B11), tegen de lokale AP 0.92.1:

```
M1. Een aanroep van <ap>/mcp zonder token geeft een OAuth-uitdaging (401 met
    WWW-Authenticate), niet 404. Commando: curl -i <ap>/mcp.
M2. Een token voor een backend is te krijgen: POST /v1/projects/<id>/mcp-server/token met
    het beheeraccount; daarmee geeft tools/list op /mcp ap_run_action terug.
M3. ap_run_action met een bestaande verbinding in dat project voert een actie uit en geeft
    het resultaat terug zonder dat de sleutel zichtbaar is (bijv. een actie tegen een
    testdoel).
M4. M3 werkt met AP_EXECUTION_MODE=SANDBOX_CODE_ONLY, en met het token van AP A is in AP B
    niets uit te voeren (twee installaties, een mislukte aanroep).
```

Aannames, elk met toets:

```
Aanname: de gratis Community-editie van AP blijft MIT en blijft inloggen met e-mail en
wachtwoord toestaan.
Toets: controleer bij elke versie-upgrade `LICENSE` in de fork (tag) en `POST
/v1/authentication/sign-in` tegen de nieuwe versie. Review: bij elke upgrade, uiterlijk
2026-11-05.

Aanname: een klant heeft voor de pilot genoeg aan wat in AP zit zonder NL-boekhoudpakketten.
Toets: vraag Rakesh zodra de pilotklant bekend is welk pakket die gebruikt en lees de
catalogus (CSV of `GET /api/v1/pieces`). Review: zodra de pilotklant bekend is.

Aanname: 518 pieces met generieke inlog is voor de pilot ruim voldoende; de klant gebruikt
er een handvol.
Toets: bouw per aantoonbaar gebruikte piece een test; beloof alleen wat getest is. Review:
na de eerste klantsessie.

Aanname: de 33 pieces met meerdere inlogsoorten zijn grotendeels met sleutel of OAuth2 te
dekken.
Toets: lees van elk van de 33 de lijst met inlogsoorten uit het CSV en deel in. Review:
2026-11-05.
```

---

## 10. Wat alleen Rakesh kan beslissen

Niets nieuws. De technische keuzes in dit document zijn door de architect gemaakt. Wel
wacht dit werk op zijn woord bij:

1. Een migratie met een geheim (interlock 1, B3): vooraf aankondigen.
2. Elke uitrol van een AP voor een tenant en elke deploy (interlock 2, B5).
3. De status: alleen hij zet dit ADR op `Accepted`.

---

## 11. Verwijzingen

- `docs/agent-briefs/generated/2026-10-06-sprint-dag-workflowbuilder-echt-werkend.md`
  (regie-besluiten, bekende defecten met bron; onderdeel 1 is door dit ADR ingehaald)
- `docs/6-Development/old-implementation/ACTIVEPIECES_INTEGRATION_IMPLEMENTATION_PLAN.md`
- ADR-035 (single-tenant), ADR-039 (rollen, vier ogen, mens-in-de-lus)
- `src/core/activepieces/` (`client.py`, `service.py`, `tenant_utils.py`, `transformer.py`,
  `catalog_syncer.py`), `src/core/api/v1/focus_builder/agents.py`,
  `src/core/services/focus_builder_service.py`, `src/core/config/unified_config.py`
- `docker-compose.yml:354`
- Tweede route (b3841e48): `src/core/tool_broker/ap_mcp_registry.py`,
  `src/core/events/department_activation_handler.py`, `src/core/tool_broker/mcp_client.py`,
  `config/tool_permissions.yml`, `src/core/config/tool_risk_levels.yml`
- ADR-015 (zero-trust ToolBroker), ADR-037 (ToolBroker productiehardening, G9, G10, Fase 2 en 3)
- AP-bron tag `0.92.1`: `docs/mcp/overview.mdx`, `docs/mcp/tools.mdx`,
  `packages/server/api/src/app/app.ts:256-259`, `packages/server/api/src/app/mcp/mcp-module.ts`,
  `packages/server/api/src/app/mcp/mcp-server-controller.ts:33`
