# Plan van aanpak — open punten na Keten B nazorg (2026-10-08)

Samengesteld door de regie uit twee onderzoeken. Deel I: beveiliging. Deel II: overige punten.

---

# Deel I — Beveiliging

# Plan: dreigingsdetectie, IP-blokkade, body-scan en autorisatievolgorde

Rol: onderzoek (vraag). Niets gewijzigd in de repo. Basis: develop @ 5176fb95.
Gemeten met .venv: fastapi 0.136.3, starlette 1.4.1, limits 5.8.0, redis-py 5.0.1 (requirements-base.txt:31).
Scratchscripts: `scratchpad/sec/order.py` (volgorde van dependency en body) en `scratchpad/sec/inv.py` (inventaris over `app.routes`).

## Bronnen (overkoepelend)

- OWASP SQL Injection Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html. De primaire verdediging zijn prepared statements en geparametriseerde queries. Inputvalidatie geldt als "secondary defense in ALL cases". Escapen wordt "STRONGLY DISCOURAGED".
- OWASP Input Validation Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html. Het advies is een allowlist: "Do not try to recognize every malicious string". Het blokkeren van tekens "rejects legitimate names without making a database query safe".
- WAF-regels en false positives: een regexdetectie van SQL en XSS staat in de OWASP CRS pas op paranoia level 2, met de waarschuwing "false positives are more likely". Tuning en uitzonderingen zijn daarbij nodig: https://docs.varnish-software.com/varnish-waf/owasp-crs/, https://www.netnea.com/cms/?p=951 en https://owasp.org/www-chapter-dorset/assets/presentations/2023-06/Introduction_to_the_OWASP_ModSecurity_Core_Rule_Set_Project.pdf. De officiele pagina op coreruleset.org gaf een 404, daarom staan hier secundaire bronnen.
- OWASP Denial of Service Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Denial_of_Service_Cheat_Sheet.html. Rate limiting kan op IP, op blocklists of op geolocatie.
- MDN X-Forwarded-For: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/X-Forwarded-For. Voor beveiliging gebruik je alleen adressen die een vertrouwde proxy heeft toegevoegd. Je neemt het adres met "trusted proxy count" of "trusted proxy list" vanaf rechts. De volledige lijst over alle XFF-headers telt, want "It is insufficient to use only one of multiple X-Forwarded-For headers". Is de server ook direct bereikbaar, dan is "no part" van de header te vertrouwen.
- Uvicorn settings: https://uvicorn.dev/settings/. `--proxy-headers` staat standaard aan, maar vertrouwt alleen `--forwarded-allow-ips`. Die waarde komt uit `$FORWARDED_ALLOW_IPS` en is anders `127.0.0.1` en `::1`.
- Starlette Requests: https://starlette.dev/requests/. Na `.stream()` "Any subsequent calls to .body(), .form(), or .json() will raise an error".
- FastAPI, dependencies in de decorator: https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-in-path-operation-decorators/. Deze dependencies "can raise exceptions, the same as normal dependencies". Voor dependencies op routerniveau: https://fastapi.tiangolo.com/tutorial/bigger-applications/. Voor globale dependencies: https://fastapi.tiangolo.com/tutorial/dependencies/global-dependencies/.
- Redis SET met EX en NX, voor een sleutel met TTL: https://redis.io/docs/latest/commands/set/
- SlowAPI: https://slowapi.readthedocs.io/en/latest/. Ondersteunt de backends redis, memcached en memory. Over proxies zegt de documentatie niets.

---

## a. Een aanvraag met een aanval krijgt zelf nog 200

### Huidige toestand
- `src/core/security/security_middleware.py:171-186` roept `detect_suspicious_activity` aan en weigert alleen bij `ThreatLevel.CRITICAL`.
- `src/core/security/security_manager.py:411-434` telt een SQLi-match als +10. Dat geeft `HIGH`, want `>=8` en `<15` (`:428-431`). Alleen op een gevoelig pad (+3 per patroon, `:405-409`) of na mislukte logins komt de score op CRITICAL.
- Tegelijk logt `:417` een event met `ThreatLevel.CRITICAL`. `_log_security_event` zet daarna het IP in `blocked_ips` (`:488-490`).
- Gevolg: de aanvraag zelf loopt door met 200. Pas de volgende aanvraag krijgt bij `security_middleware.py:136-146` een 429.
- De regexen staan in `security_manager.py:438-444`. `--`, `#`, `/*` en losse woorden als SELECT, UPDATE, DELETE, CREATE en ALTER matchen al. Daardoor leveren `?color=#fff`, `?q=update address` en `?sort=--date` een permanente IP-blokkade op. De repo heeft hier al eerder last van gehad: `tests/unit/security/test_routepad_is_geen_sql_invoer.py` en de docstring op `:384-386`.
- De statuscode klopt ook niet: een blokkade geeft 429 ("Too Many Requests"), terwijl het geen rate limit is.

### Gekozen oplossing: niet meer blokkeren op regex, alleen loggen en tellen
1. De SQLi-regex wordt een signaal. Het event krijgt `severity=MEDIUM` met type `sql_injection_signal`. De aanvraag wordt niet afgekapt en het IP niet direct geblokkeerd.
2. Het signaal voedt de score uit punt b, met een drempel in een tijdvenster. Pas herhaald verdacht gedrag geeft een tijdelijke blokkade.
3. De echte verdediging blijft de ORM met geparametriseerde queries (SQLAlchemy). Zet daar een architectuurtest naast die ruwe SQL-strings met f-strings of `%` in `text()` verbiedt, als die nog niet bestaat. Dat is de laag die OWASP primair noemt.
4. `_log_security_event` voegt niets meer automatisch toe aan `blocked_ips`. Blokkeren wordt een expliciete beslissing van de scorecomponent uit punt b.

### Alternatieven en waarom niet
- **De aanvraag direct afkappen met 403 bij een SQLi-match.** Dat is consistent ("de aanval zelf krijgt geen 200"), maar met de huidige regexen blokkeer je legitieme invoer zoals `#`, `--` en gewone Engelse woorden. OWASP Input Validation zegt letterlijk dat je niet elke kwaadaardige string moet proberen te herkennen. CRS zet zulke regels pas op PL2, met tuning. Voor een solo-project zonder tuningproces kost dit klanten meer dan het oplevert, en het helpt een klant niet ("productieklaar").
- **Een echte WAF (CRS) voor de ingress.** Dat is een betere plek als je wilt blokkeren, maar het is infrastructuur buiten de repo (interlock 2) en vraagt tuning. Noteer het als optie voor later.
- **Alles laten zoals het is.** Dat is het slechtste van beide: de aanvaller krijgt zijn antwoord en een legitieme gebruiker wordt permanent buitengesloten.

### Stappen
1. `security_manager.py`: `detect_suspicious_activity` geeft ook een lijst signalen terug (of een klein dataclass-resultaat). Het SQLi-event wordt MEDIUM. Het auto-block op `:488-490` gaat eruit.
2. `security_middleware.py:176`: bij CRITICAL (een hoge score uit punt b) volgt 403 voor die aanvraag zelf. Een SQLi-signaal alleen geeft geen 403.
3. De blokkade-response bij `:138` wordt 403 met een `Retry-After`, of 429 alleen als het om een rate limit gaat.
4. Optioneel: zet de regex achter een featureflag `SECURITY_SQLI_SIGNAL=log|off`.

### Tests
- `?q=update%20address`, `?color=%23fff` en `?sort=--date`: 200, ook de volgende aanvraag, en het IP wordt niet geblokkeerd.
- `?id=1%20OR%201=1`: 200 (de ORM beschermt), er is een event gelogd en geen blokkade.
- N signalen binnen het venster: de aanvraag die de drempel passeert krijgt zelf 403 (punt b).
- Pas `tests/unit/test_security_manager_coverage.py`, `tests/security/test_security_manager.py` en `tests/unit/test_security_middleware_flow.py` aan. Daar staan waarschijnlijk asserts op het auto-block. Pas de verwachting aan, sla geen test over.

### Risico's
- Een gevoel van "minder beveiliging". Leg in een ADR vast dat de ORM de verdediging is.
- Bestaande tests rekenen op het auto-block en moeten met een goede reden worden herschreven.
- Schatting: **S**

---

## b. Een IP-blokkade duurt tot de server opnieuw start

### Huidige toestand
- `blocked_ips: set[str]` in het geheugen (`security_manager.py:85`). Er is geen TTL, en `cleanup_old_data` (`:541-558`) ruimt `blocked_ips` niet op. Er is ook geen uitzondering voor beheerders of interne adressen.
- Productie draait gunicorn met `UvicornWorker` en `workers = cpu*2+1` (`scripts/gunicorn_config.py:26-29`, `scripts/entrypoint-prod.sh:76`). Elke worker heeft zijn eigen `_security_manager`-singleton (`security_manager.py:564-570`). Een blokkade, de rate-limit-lijsten (`:86`, `:321-358`) en de failed attempts gelden dus per proces en per replica. De handhaving is willekeurig en de geheugengroei is onbegrensd per IP en endpoint.
- **Bepaling van het IP.** `SecurityMiddleware._get_client_ip` (`security_middleware.py:276-313`) neemt het N-de element vanaf rechts met `TRUSTED_PROXY_COUNT` (default 1). Dat is de methode "trusted proxy count" van MDN en dat is goed (ADR-036 OP-111, `tests/security/test_client_ip_is_not_spoofable.py`). Twee gaten:
  - `request.headers.get("X-Forwarded-For")` leest alleen de eerste header. MDN eist dat je alle XFF-headers samenvoegt. Gebruik `request.headers.getlist(...)` en join.
  - De terugval op `X-Real-IP` (`:307-309`) is spoofbaar als de proxy die header niet zelf overschrijft.
- **Bestaande rate limiting: vier lagen naast elkaar.**
  1. `ProductionSecurityManager.check_rate_limit`: in het geheugen, per proces, met de regels in `security_manager.py:137-156`. Dit draait in de SecurityMiddleware.
  2. SlowAPI: `src/core/middleware/rate_limiter.py:85-138`. In productie draait het met `storage_uri` Redis DB 2, moving-window en een sleutel per tenant met IP als fallback. Daarbuiten is het `memory://` en fixed-window. `app.state.limiter` wordt gezet in `src/core/app_factory.py:360-364`. Het werkt alleen met `@limiter.limit` op routes (`tests/architecture/test_rate_limited_endpoints_slowapi_contract.py`). Voor het IP gebruikt het `slowapi.util.get_remote_address`, dus `request.client.host`. Achter de ACA-ingress is dat het adres van de ingress, tenzij `FORWARDED_ALLOW_IPS` is gezet: Uvicorn vertrouwt standaard alleen 127.0.0.1 (https://uvicorn.dev/settings/). In `gunicorn_config.py` en `entrypoint-prod.sh` vond ik geen `forwarded_allow_ips`. Waarschijnlijk delen alle anonieme bezoekers dus een bucket. Dat moet je controleren op staging.
  3. `src/core/middleware/rate_limit_middleware.py:70-341`: `TokenBucketRateLimiter` op Redis met `INCR` en `EXPIRE`, en `RateLimitMiddleware` die het meest rechtse XFF-element pakt (`:307-311`). Ik vond geen registratie in `middleware_config.py`, dus controleer of dit dode code is.
  4. `src/core/governance/rate_limiter.py`: privacy-limiters op Redis per IP of e-mail.

### Gekozen oplossing: een tijdelijke blokkade op score, in Redis, met een allowlist
- **Een nieuwe component `IpReputation`** in `src/core/security/ip_reputation.py`, met Redis als backend (zelfde client als `src/core/shared/redis_client.get_redis`).
  - Score: `INCRBY sec:score:{ip} <punten>` plus `EXPIRE sec:score:{ip} 900`. Dat is een glijdend venster van 15 minuten. Punten: SQLi-signaal 3, mislukte login 2, 401/403-storm 1.
  - Blokkade: bij `score >= 15` volgt `SET sec:block:{ip} <reden> EX <ttl> NX` (https://redis.io/docs/latest/commands/set/). De TTL loopt op per herhaling, bijvoorbeeld 15 minuten, dan 1 uur, dan 24 uur, via `INCR sec:strikes:{ip}` met `EX 7d`.
  - Controle in de middleware: `EXISTS sec:block:{ip}`. Dat is een round-trip per aanvraag. Cache het hooguit 5 seconden lokaal.
  - Fail-open bij een Redis-storing, met een waarschuwing in de log en een metric. Een storing in de beveiligingsheuristiek mag de site niet platleggen. Authenticatie en autorisatie blijven fail-closed.
- **Allowlist** via de env `SECURITY_BLOCK_EXEMPT_CIDRS` (de interne VNet, health probes, kantoor-IP), gecontroleerd met `ipaddress.ip_network`. Een geldige JWT met de beheerdersrol telt ook mee: zo'n gebruiker wordt nooit op IP geblokkeerd, maar telt wel in de logging. Let op: de JWT-check moet wel echt verifieren, en dat doet `_extract_user_id` al.
- **Een beheerroute om te deblokkeren**, `DELETE /api/v1/system/security/blocks/{ip}`, met een rolcontrole als dependency (zie punt d). Plus een lijst met de resterende TTL.
- **Het IP bepalen:** XFF samenvoegen over alle headers, de terugval op `X-Real-IP` alleen gebruiken als de configuratie dat zegt, en kies een van twee (niet beide):
  - (aanbevolen) `FORWARDED_ALLOW_IPS` op het ingress-subnet in gunicorn, zodat `request.client.host` klopt voor SlowAPI en alle andere lagen, of
  - SlowAPI een eigen `key_func` geven die `SecurityMiddleware._get_client_ip` hergebruikt. Een plek waar het IP wordt bepaald.
- **De rate limit in het geheugen opruimen:** `check_rate_limit` in de manager vervangen door een gedeelde Redis-limiter. Gebruik de `limits`-bibliotheek met `RedisStorage` en `MovingWindowRateLimiter`, die SlowAPI al meeneemt. Dat is een aparte stap.

### Alternatieven en waarom niet
- **Een TTL in het geheugen (dict ip -> verlooptijd).** Simpel, maar per worker en per replica inconsistent. Met `cpu*2+1` workers is dat de huidige fout in het klein.
- **Fail2ban of blokkeren op de ingress (ACA IP-restricties).** Robuust, maar buiten de repo en handmatig.
- **Helemaal geen IP-blokkade, alleen rate limiting.** Dat is een verdedigbaar minimum en goedkoper. Het verschil is klein als a wordt doorgevoerd. Kies dit als Redis-latency per aanvraag een bezwaar is.

### Stappen
1. Een ADR "IP-reputatie: TTL, score, Redis, allowlist".
2. `ip_reputation.py` met de interface `record(ip, signal)`, `is_blocked(ip)`, `unblock(ip)` en `list_blocks()`. Async, op Redis, met een fake voor tests.
3. De SecurityMiddleware gebruikt de nieuwe component. `blocked_ips` vervalt, of wordt een alleen-lezen weergave voor `get_security_report`.
4. Het IP bepalen met `getlist` en de config `FORWARDED_ALLOW_IPS`. Meet eerst op staging welk adres SlowAPI nu ziet.
5. De beheerroute plus de architectuurtest uit punt d.
6. Later: de rate limit uit de manager naar `limits` met Redis.

### Tests
- Unit, met fakeredis of een fake: score onder de drempel geeft geen blokkade. Boven de drempel volgt een blokkade met een TTL tussen 899 en 900. Na het verstrijken (tijd verzetten of `EXPIRE` kort zetten) is het IP vrij. Strikes laten de TTL oplopen.
- Allowlist: een IP in de CIDR-lijst wordt nooit geblokkeerd. Een token met de beheerdersrol idem. Een ongeldig token geeft geen vrijstelling.
- Meerdere processen: twee `IpReputation`-instanties op dezelfde Redis zien dezelfde blokkade.
- Een Redis-storing: de aanvraag gaat door (fail-open) en er wordt een waarschuwing gelogd.
- XFF: twee XFF-headers worden samengevoegd. De client voegt links een adres toe en dat wordt genegeerd. Breid `tests/security/test_client_ip_is_not_spoofable.py` uit.
- Integratie (marker `requires_redis`): de volgorde aanvallen, blokkade, 403, unblock via de beheerroute, 200.

### Risico's
- Een gedeeld NAT- of kantoor-IP blokkeert meerdere klanten tegelijk. Daar zijn de allowlist, een korte eerste TTL en de unblock-route voor.
- Elke aanvraag kost een extra Redis-round-trip. Dat valt te beperken met een korte lokale cache.
- Een verkeerde `TRUSTED_PROXY_COUNT` of `FORWARDED_ALLOW_IPS` laat iedereen een bucket delen, of laat spoofing toe. Meet het op staging voordat je merget.
- Schatting: **M** (de rate-limitconsolidatie apart erbij: **M**)

---

## c. De body van een verzoek wordt niet gescand

### Huidige toestand
- De scan bekijkt alleen queryparameters en padparameters: `security_middleware.py:342-360` (`_door_gebruiker_geleverd`).
- `MaxRequestBodySizeMiddleware` (`src/core/middleware/max_body_size_middleware.py:96-118`) begrenst de body al per chunk via een omwikkelde `receive`. Dat is goed.
- De invoer wordt gevalideerd door Pydantic-modellen per route. Data gaat via SQLAlchemy (ORM, gebonden parameters).

### Advies: de body NIET scannen in de middleware
- **De juiste laag** is Pydantic als allowlist (typen, lengtes, enums, patronen per veld) plus de ORM met gebonden parameters. Dat is precies de combinatie die OWASP noemt: primair parametriseren, validatie als secundaire verdediging, en geen denylist (zie de SQLi- en Input Validation Cheat Sheets hierboven).
- **De kosten van scannen in ASGI.** Om de body te scannen moet de middleware de hele body bufferen en daarna een nieuwe `receive` naspelen voor de app. Volgens Starlette kan een verbruikte stream niet opnieuw worden gelezen (https://starlette.dev/requests/). Dat geeft:
  - geheugen per aanvraag tot `max_upload_size_bytes`, en het streamen van uploads gaat verloren,
  - complexiteit met multipart en bestanden, met binaire inhoud die vol "--" en "#" zit,
  - meer false positives dan bij queryparameters: vrije tekst in chat (`/api/v1/cva/chat`), canvasblokken en workflowdefinities bevat legitiem SQL-achtige woorden en tekens. Gezien punt a zou dat klanten blokkeren.
- **Als je toch iets wilt:** scan per veld in Pydantic, met een `AfterValidator` op velden die echt naar een raw query gaan. Dat is gericht, kent het type en kost geen extra buffering.

### Alternatieven en waarom niet
- **Een body-scan met bufferen en naspelen in `SecurityMiddleware`.** Verworpen om de redenen hierboven: geheugen, streaming en false positives op vrije tekst.
- **Een body-scan alleen voor `application/json` onder N KB.** Minder kosten, maar nog steeds een denylist met false positives. Je schuift het probleem alleen op.
- **Een WAF op de ingress.** Die kan de body inspecteren met tuning. Dat is buiten de repo, zie a.

### Stappen
1. Een ADR of notitie: "body-inspectie is bewust niet de taak van de middleware".
2. Een audit (script) naar `text(`, `.execute(f"`, `%s`-formatting en `exec_driver_sql` in `src/`, met een architectuurtest die ruwe SQL met interpolatie verbiedt. Meet eerst hoeveel treffers er zijn.
3. Een steekproef van Pydantic-modellen op `max_length` en `extra="forbid"` voor schrijfendpoints. Dat is apart werk en hoort alleen bij de meetlat als het een klantscenario raakt.

### Tests
- Architectuurtest: geen `text()` met f-string of `%`-interpolatie in `src/`.
- Regressie: een POST met een body die `"'; DROP TABLE users; --"` bevat wordt gewoon opgeslagen en teruggegeven als tekst, er volgt geen blokkade en de tabel bestaat nog.

### Risico's
- Het risico zit in plekken waar wel ruwe SQL met interpolatie wordt gebouwd. De architectuurtest is de controle daarop.
- Schatting: **S** (de audit en de architectuurtest; reparaties per gevonden treffer apart)

---

## d. roles/create controleert de invoer voor de rol

### Huidige toestand
- `src/core/api/v1/rbac/roles_router.py:58-78`: `create_role(request: CreateRoleRequest, ...)` doet de controle `rbac.user_has_permission(..., Permission.TENANT_ADMIN, ...)` pas in de functie zelf (`:72-77`). Het pad is `/api/rbac/roles/create`, zonder v1.
- **Gemeten** (`scratchpad/sec/order.py`, fastapi 0.136.3):

  | route | body `{}` (ongeldig schema) | kapotte JSON |
  |---|---|---|
  | controle in de handler | 422 | 422 |
  | `dependencies=[Depends(deny)]` op de decorator | **403** | 422 |
  | `APIRouter(dependencies=[...])` | **403** | 422 |

  Conclusie: met een dependency krijgt een niet-beheerder 403 voordat zijn body wordt gevalideerd. Kapotte JSON geeft altijd 422 voor de dependencies, want FastAPI parset de body in de request handler voordat de dependencies worden opgelost. Dat lekt hooguit "dit is geen geldige JSON" en geen schema-informatie. Wil je ook dat dichten, dan moet de autorisatie in middleware. Dat raad ik niet aan.
- **Inventaris** (`scratchpad/sec/inv.py` over `src.main.app.routes`): 877 APIRoutes, waarvan 262 met een body. Bij **38** staat een autorisatiepatroon (403, `user_has_permission`, `is_admin` enzovoort) in de handler zonder autorisatiedependency in de dependency-boom. Het is een heuristiek en moet met de hand worden bevestigd.
  - **Echt hetzelfde patroon (rol of permissie, hoort in een dependency):**
    - `POST /api/rbac/roles/create`
    - `POST` en `DELETE /api/rbac/roles/{role_id}/permissions`
    - `POST /api/rbac/users/assign-role`, `/assign-role/bulk`, `/revoke-role` en `/revoke-role/bulk`
    - `POST /api/rbac/permissions/check`
    - `POST /api/admin/features/{feature}/toggle`
    - `POST /api/v1/tenants/` en `PUT /api/v1/tenants/{tenant_id}`
    - `POST /api/v1/users/` en `PUT /api/v1/users/{user_id}`
    - `POST /api/gdpr/delete-all`
    - `PUT /api/v1/tools/hitl/four-eyes`
    - `POST /api/v1/gatekeeper/hitl/approve` en `/reject`
    - `POST /api/v1/domain-packs` en `PUT /api/v1/domain-packs/{pack_id}`
    - `POST /execute` (terminal)
  - **Autorisatie op resourceniveau** (eigenaar of deelnemer). Die hangt van de resource af en kan pas na het laden. Dat is acceptabel, eventueel via een dependency op het pad-ID:
    - `/api/v1/canvas/{canvas_id}...`: 5 routes
    - `/api/v1/workflows/{execution_id}/cancel`
    - `/api/v1/focus-builder/flows/{flow_id}/execute`
    - `/api/v1/agentic/agents/{agent_id}/execute-agency-capability`
    - `PUT /api/v1/users/{user_id}/password`
  - **Waarschijnlijk vals positief** (een 403 om een andere reden, zoals een inactief account of een featureflag):
    - `/api/v1/auth/login`, `/token` en `/register`
    - `/api/v1/cva/chat` en `/chat/stream`
    - `/api/v1/agentic/generate`
    - `/api/v1/orchestrate/critique`
    - `/api/v1/pack-selector`
    - `/api/v1/scheduling/smart/profile`

### Gekozen oplossing
- De rolcontrole wordt een dependency. Gebruik de bestaande fabriek `src/core/auth/dependencies.py:402` `require_permission(permission)`, die al de tenant controleert en de `user_id` teruggeeft.
  - Per route: `current_user_id: int = Depends(require_permission(Permission.TENANT_ADMIN))`, of `dependencies=[...]` in de decorator.
  - Per router, waar alle routes dezelfde rol vragen: `APIRouter(prefix="/rbac", dependencies=[Depends(...)])`. Dat werkt niet voor `rbac/roles` als `GET /roles` voor gewone gebruikers moet blijven werken. Splits dan in een lees- en een schrijfrouter.
- Controleer eerst of `Permission` in `src/core/auth/dependencies.py` hetzelfde enum is als `src/core/api/v1/rbac/dependencies.Permission` (TENANT_ADMIN). Anders is een dunne adapter-dependency nodig rond `RBACService.user_has_permission`.
- Een architectuurtest, als uitbreiding op `tests/architecture/test_admin_routes_hebben_een_rolcontrole.py`: elke APIRoute met een body onder `/api/rbac`, `/api/admin`, `/api/v1/tenants`, `/api/v1/users` (behalve `/me`), `/api/gdpr`, `/api/v1/system` en `/api/v1/autonomous` heeft in de dependency-boom een autorisatiedependency uit een expliciete allowlist van callables. Gebruik de logica van `inv.py` (recursief over `route.dependant.dependencies`).

### Alternatieven en waarom niet
- **Autorisatie in middleware (op pad en rol).** Dat dekt ook kapotte JSON af, maar dupliceert routekennis. De repo heeft daar al eerder last van gehad (padparameter `admin`, zie `security_middleware.py:363-389`). Het lekken van "ongeldige JSON" is verwaarloosbaar.
- **De body als `Request` lezen en zelf valideren na de rolcontrole.** Dan raak je de OpenAPI-documentatie en de typeveiligheid kwijt.
- **Laten zoals het is.** Dan lekt het schema (veldnamen en constraints in 422-details) naar ongeautoriseerde gebruikers. Dat is beperkt ernstig, maar het is ook een signaal dat de rolcontrole los staat van de route en dus vergeten kan worden.

### Stappen
1. Controleer het `Permission`-enum en maak zo nodig `require_tenant_admin`.
2. `roles_router.py` en `assignment_router.py`: de controle uit de handler naar een dependency, en splits in een lees- en een schrijfrouter.
3. Daarna de overige rol-routes uit de lijst hierboven, per module een commit.
4. De architectuurtest, met de inventaris als baseline: eerst rood op de bekende routes, dan groen.

### Tests
- Per route: een niet-beheerder met een ongeldige body krijgt 403, niet 422. Een niet-beheerder met een geldige body krijgt 403. Een beheerder met een ongeldige body krijgt 422. Een beheerder met een geldige body krijgt 200 of 201.
- Kapotte JSON van een niet-beheerder: 422 is het gedocumenteerde, geaccepteerde gedrag. Leg dat vast in een test, zodat het een bewuste keuze is.
- De architectuurtest uit de vorige sectie.

### Risico's
- Een router-dependency raakt per ongeluk ook lees- of `me`-routes. Daarom splitsen en per route testen.
- Een dubbele DB-sessie of dubbele query: `require_permission` doet een eigen lookup. Dat is acceptabel, en FastAPI cachet dezelfde dependency per aanvraag.
- De heuristiek mist routes die de rol controleren via een servicelaag zonder 403 in de handler. De architectuurtest op prefix vangt die wel.
- Schatting: **M** (RBAC en een architectuurtest S, de rest van de 20 rol-routes M)

---

## Volgorde en samenvatting

| Punt | Keuze | Schatting |
|---|---|---|
| a | De SQLi-regex wordt een signaal (loggen en score). Geen auto-block en geen 403 op een regex. Bij een overschreden drempel krijgt die aanvraag zelf 403. | S |
| b | Een IP-reputatie in Redis met TTL, score, strikes, een CIDR- en beheerdersallowlist en een unblock-route. XFF samenvoegen. `FORWARDED_ALLOW_IPS` controleren. | M (+M voor de rate-limitconsolidatie) |
| c | Geen body-scan. Pydantic als allowlist plus ORM, en een architectuurtest tegen ruwe SQL. | S |
| d | Autorisatie als dependency (decorator of router). Architectuurtest. 20 rol-routes plus 9 op resourceniveau gevonden. | M |

Aanbevolen volgorde: eerst d (het raakt de beveiliging van klantdata het meest direct), dan a+b samen (a zonder b haalt alleen weg), en c als laatste (vooral een vastlegging).

**Te melden en niet nu oppakken:**
- Er zijn vier rate-limitlagen naast elkaar.
- `rate_limit_middleware.RateLimitMiddleware` is mogelijk dode code.
- `_log_security_event` schrijft bij elke middlewarefout een traceback naar het tempbestand (`security_middleware.py:234-237`).
- `/orchestrator` staat op PUBLIC (`:399-400`).


---

# Deel II — Overige punten

# Plan overige punten (rol: onderzoek, niets gewijzigd)

Repo `D:/Dev/SanskritiSetu.org`, develop @ `5176fb95` (= origin/develop). Datum 2026-10-08.

---

## 1. Rolmodel debiteuren

### Huidige toestand
- Alle schrijfroutes eisen `require_permission(Permission.WRITE)`:
  `src/core/api/v1/receivables/router.py:50` (toevoegen), `:109` (PATCH, ook op betaald zetten),
  `:152` (herinnering voorstellen). Lezen: `:88` met `Permission.READ`.
- `require_permission` (`src/core/auth/dependencies.py:402-468`) vraagt
  `RBACService.has_permission(user_id, "*", "write")`, dus het recht `*:write` met resource-wildcard.
- Standaardrollen per tenant (`src/core/services/rbac_service.py:834-870`, `ensure_default_roles`):
  `admin` = `*:*`; `editor` = `agents:*`, `workflows:*`; `user` = `agents:read`, `workflows:read`.
  Gevolg: **alleen `admin` kan debiteuren schrijven**; `editor` en `user` krijgen 403
  (vastgelegd in `tests/integration/api/test_receivables_schrijfrecht_per_rol.py`, genoemd in
  `frontend/src/pages/ReceivablesPage.tsx:75-81`).
- Het oude woordenboek `ROLE_PERMISSIONS` in `src/core/auth/rbac.py:66-95` (user/moderator/admin)
  is een tweede, los model (ADR-039 par. 2.1, regel 120). **Bijgewerkt 2026-10-09 (OP-143): dat
  woordenboek is verwijderd; tools lezen `role_permissions`.**
- Frontend: `magSchrijven = user?.isAdmin === true` (`ReceivablesPage.tsx:81`); `/auth/me` levert
  geen rechtenlijst.
- ADR-039 (`docs/adr/039-rollen-en-bevoegdhedenmodel-in-drie-lagen.md:202-255`) schrijft laag 3 voor:
  handelingen inzien / voorstellen / uitvoeren / beslissen, rol "Debiteurenadministrateur" als
  voorbeeld (`:221`), default-deny, vier ogen als instelling per tenant (par. 3.4).
- Goedkeuren van het HITL-ticket loopt via `_require_approver` (= tenantbeheerder) en
  `_refuse_self_approval` (`src/core/api/v1/tool_broker/hitl_router.py:102-185`).
  Een herinnering *voorstellen* is dus nog geen versturen: een agentvoorstel wacht op een beslissing.

### Bronnen
- Functiescheiding: de onverenigbare taken zijn autorisatie, bewaring van activa en
  registratie, en daarnaast reconciliatie. Geen enkele persoon hoort te kunnen innen, vastleggen en
  aansluiten: UNLV Cash Control https://www.unlv.edu/qafc/resources/cash-control ;
  NJCPA https://www.njcpa.org/learn/article/2024/09/23/why-segregation-of-duties-is-essential-for-internal-control ;
  NC Dept. of Agriculture internal-control lijst https://www.ncagr.gov/ncdacs-internal-audit-division-standard-list-internal-controls/open .
- COSO plaatst functiescheiding onder de *control activities* (Internal Control – Integrated
  Framework 2013). Het brondocument zelf is niet opgehaald; zie de samenvatting bij NJCPA hierboven.
- Kleine organisaties: volledige scheiding lukt vaak niet. Dan geldt aanvullend toezicht en review
  (UNLV, zelfde URL). Dat sluit aan bij ADR-039 par. 3.4 (zzp-uitzondering).
- Nederlandse AO/IC: functiescheiding verdeelt de bevoegdheden voor verzamelen, vastleggen en
  verwerken zo dat de kans op fouten kleiner wordt:
  https://boommanagement.nl/artikel/controletechnische-functiescheiding/ ;
  over de controlerende functie die onafhankelijk blijft van de uitvoering:
  https://www.pensioenfederatie.nl/stream/15.1.1-qa-sleutelfuncties-en-adequate-functiescheiding-20200117.pdf .
  De klassieke vijfdeling (beschikkend, bewarend, registrerend, uitvoerend, controlerend) komt uit
  de AO-vakliteratuur. Die heb ik niet online als primaire bron gevonden; markeer dit als vakkennis.

Toegepast: debiteuren **toevoegen** en **op betaald zetten** is registreren. **Herinnering
voorstellen** is uitvoerend-voorbereidend. **Beslissen over versturen** is beschikkend. Betaald
zetten raakt de aansluiting met de bank. Wie registreert, hoort zijn eigen betaald-markering niet
ongezien te laten staan.

### Opties
**A. Rol `debiteurenadministrateur` met `receivables:read` + `receivables:write`, zonder goedkeuren (aanbevolen).**
- Backend: nieuwe `Permission`-waarden of een tweede dependency `require_scope("receivables:write")`.
  `require_permission` vraagt nu hard `"*"`; maak een variant `require_resource_permission(resource, action)`
  in `src/core/auth/dependencies.py` die `has_permission(user_id, "receivables", "write")` vraagt.
  `admin` blijft slagen via `*:*`.
- `ensure_default_roles` (`rbac_service.py:851`) uitbreiden met `("debiteuren", "Debiteurenadministrateur",
  [{"resource":"receivables","action":"read"},{"resource":"receivables","action":"write"}])`.
  Bestaande tenants krijgen hem bij de volgende aanroep (OP-187-gedrag: ontbrekende rechten worden aangevuld).
- Router: `:50`, `:109`, `:152` naar `receivables:write`; `:88` naar `receivables:read`.
- ~~Goedkeuren blijft `_require_approver` (beheerder).~~ **Achterhaald 2026-10-09 (besluit Rakesh):**
  goedkeuren is een procesbevoegdheid, geen beheerdersrecht. Recht `receivables:approve` (en
  `hr:approve`) in de database-RBAC, standaardrol `goedkeurder`, NIET onder de beheerder-wildcard; zie
  ADR-039 "Stand 2026-10-09". Vier ogen standaard aan zodra er meer dan een
  beslisser is (ADR-039 3.4).
- Betaald → terug naar open vraagt al een `reden` (`schemas.py:44-45`). Overweeg betaald zetten boven een
  bedrag als voorstel te laten lopen (later, laag 3 met limiet).
- Frontend: `/auth/me` uitbreiden met `permissions: string[]` (of `can: {receivablesWrite: boolean}`).
  `magSchrijven = user?.permissions?.includes('receivables:write') || user?.isAdmin`. Knoppen
  "Toevoegen", "Betaald" en "Herinnering voorstellen" volgen `magSchrijven`. De goedkeurknoppen op de
  HITL-pagina volgen sinds 2026-10-09 `receivables:approve` / `hr:approve` uit `/auth/me`, niet
  `isAdmin` (ADR-039).

**B. Alleen beheerder (huidige toestand vastleggen).**
- Geen codewijziging. Alleen een ADR-aanvulling en een meetlat-noot.
- Nadeel: in het mkb is de beheerder vaak ook de beslisser, dus registreren, voorstellen en beslissen
  liggen in een hand. Vier ogen werkt dan alleen bij twee beheerders. Dit is in strijd met de geest
  van ADR-039 3.4.

**C. Gesplitst: `receivables:write` (toevoegen/wijzigen) + apart `receivables:propose`; betaald zetten alleen beheerder.**
- Fijnste scheiding: registratie los van de bankaansluiting.
- Meer werk: een aparte route of een veldcontrole in de PATCH (`status == "betaald"` → extra eis).

### Stappen (optie A)
1. ADR-039 aanvullen met een tabel rol × handeling voor debiteuren (besluit Rakesh).
2. Dependency `require_resource_permission` met unit-tests.
3. Seed de rol in `ensure_default_roles` + migratie- en idempotentietest.
4. Router omzetten; `/auth/me` aanvullen; frontend `magSchrijven` omzetten.
5. Tests aanpassen.

### Tests
- `tests/integration/api/test_receivables_schrijfrecht_per_rol.py`: per rol (admin 2xx,
  debiteuren 2xx, editor 403, user 403) voor POST, PATCH en reminder-proposals; GET voor
  debiteuren 200.
- Test dat de rol `debiteuren` een HITL-ticket **niet** kan goedkeuren (403 via `_require_approver`). Sinds 2026-10-09 geldt dat ook voor de beheerder zonder rol `goedkeurder`.
- Frontend: `ReceivablesPageRol.test.tsx` met `permissions: ['receivables:write']` en `isAdmin: false`:
  de knoppen zijn zichtbaar.

### Risico's
- 306 endpoints gebruiken scopes. Raak `require_permission` zelf niet aan; voeg alleen een variant toe.
- De asymmetrie OP-143 (hoofdlettergevoeligheid) blijft bestaan.
- De frontend en de backend kunnen uit elkaar lopen. De backend blijft de autoriteit.

**Schatting:** A = M, B = S, C = L.
**Beslissing Rakesh:** A, B of C. Moet betaald zetten onder vier ogen? Hoe heet de rol?

---

## 2. In het log staat "UTC", maar de job draait op lokale tijd

### Huidige toestand
- `SCHEDULER_TIMEZONE = os.getenv("SCHEDULER_TIMEZONE", "UTC")` (`src/workers/scheduler.py:36`).
  Die waarde gaat naar `AsyncIOScheduler(timezone=...)` (`:67-68`).
- De jobs gebruiken een **CronTrigger-instantie zonder timezone**: `:91` (pack health), `:105`, `:115`,
  `:125`, `:135` en `volg_debiteuren_op` op `:206` (`CronTrigger(hour=4, minute=15)`).
  De logregels printen wel `({SCHEDULER_TIMEZONE})`: `:99`, `:126-:156` en `:211`.
- De retentiejobs vanaf `:218` geven `timezone="UTC"` wel expliciet mee. Die kloppen.
- Geinstalleerde versie: APScheduler 3.11.2 (`requirements-base.txt:88`: `>=3.10.4,<4.0`).

### Bronnen
- De documentatie zegt dat de timezone "defaults to scheduler timezone":
  https://apscheduler.readthedocs.io/en/3.x/modules/triggers/cron.html . **Dat geldt alleen voor
  `add_job(trigger="cron", ...)`.** `BaseScheduler._create_trigger` geeft een `BaseTrigger`-instantie
  ongewijzigd terug en zet alleen bij een tekst-trigger `trigger_args.setdefault("timezone", self.timezone)`.
  `CronTrigger.__init__` valt zonder timezone terug op `get_localzone()`. Lokaal geverifieerd in
  de geinstalleerde 3.11.2-bron; upstream:
  https://github.com/agronholm/apscheduler/blob/3.x/src/apscheduler/schedulers/base.py en
  https://github.com/agronholm/apscheduler/blob/3.x/src/apscheduler/triggers/cron/__init__.py .
- Over zomer- en wintertijd zegt dezelfde docs-pagina dat cron op "wall clock" werkt. Bij de
  omschakeling kan een job overgeslagen worden of twee keer draaien. Het advies is UTC, of geen
  jobs in het omschakeluur.

### Oplossing
- Bedoeld is **Europe/Amsterdam** voor klantgerichte jobs: debiteuren opvolgen om 04:15 en
  `verstuur_klare_berichten`. Een klant denkt in lokale kantoortijd. Onderhoud en retentie blijven
  UTC. 04:15 valt buiten het omschakelvenster 02:00-03:00 (EU-regel: de laatste zondag van maart
  en van oktober om 01:00 UTC), dus er is geen dubbele run. Pack health om 02:00 valt wel in dat
  venster: in maart bestaat 02:00 lokaal niet (`misfire_grace_time=3600` vangt dat op), en in oktober
  kan hij twee keer draaien. Zet hem dus op UTC of verschuif hem naar 03:30.
- Concreet: geef elke `CronTrigger(...)` expliciet `timezone=SCHEDULER_TIMEZONE` mee, of gebruik
  `add_job(..., trigger="cron", hour=4, minute=15)`. Zet `SCHEDULER_TIMEZONE=Europe/Amsterdam` in
  `docker-compose.yml` en `.env.example`. Maak de logregel af van `job.trigger.timezone` in plaats
  van de constante, zodat het log nooit meer liegt.
- In de container is de lokale tijdzone meestal UTC; op de Windows-dev-host is hij Europe/Amsterdam.
  Daarom ziet de acceptant lokaal een uur of twee verschil.

### Alternatieven
- Alles UTC (eenvoudig, DST-vrij). Dan schuift 04:15 UTC in de zomer naar 06:15 lokaal. Voor een
  klant is dat acceptabel, maar de log en de meetlat moeten het dan zo zeggen.

### Tests
- Unit-test: na `initialize()` heeft elke job in `scheduler.get_jobs()` een `trigger.timezone` gelijk
  aan `ZoneInfo(SCHEDULER_TIMEZONE)` of aan UTC voor de retentiejobs. Draai hem met `TZ` op iets
  anders, zodat de lokale zone niet stiekem meetelt.
- Test voor `next_fire_time` rond 2026-10-25 en 2027-03-28 (vanaf een vaste `now`).

### Risico's
Jobs die nu "per ongeluk" goed liepen, verschuiven een of twee uur. **Schatting: S.**
**Beslissing Rakesh:** Europe/Amsterdam voor klantjobs of alles UTC.

---

## 3. Bedrag met komma ("1250,00") geeft 422

### Huidige toestand
- Het frontendveld is `type: 'text'` (`frontend/src/pages/ReceivablesPage.tsx:70`). De waarde gaat
  rauw als string mee (`:260`; `frontend/src/lib/api/receivables.ts:32`, `:71-73`).
- Het backendschema heeft `amount: Decimal = Field(ge=0, max_digits=14, decimal_places=2)`
  (`src/core/api/v1/receivables/schemas.py:28`, `:39`). Lokaal gemeten met Pydantic:
  `"1250.00"` geeft OK, `"1250,00"` en `"1.250,00"` geven `decimal_parsing`, dus 422.
- De frontend toont dan "Controleer de velden." (`ReceivablesPage.tsx:28`), zonder te zeggen welk veld.
  De weigering zit dus in het **Pydantic-schema**; de frontend normaliseert niet.
- Decimal wordt al goed gebruikt; er is geen float.

### Bronnen
- `Intl.NumberFormat.prototype.formatToParts` geeft het decimaal- en groepsteken per locale
  (bijvoorbeeld `,` en `.` voor de-DE/nl-NL):
  https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat/formatToParts .
  Daarmee kun je locale-invoer parsen zonder de tekens hard te coderen. Intl heeft zelf geen parse-API.
- Python `decimal.Decimal` accepteert alleen een punt als decimaalteken:
  https://docs.python.org/3/library/decimal.html#decimal.Decimal .
- Geld nooit als binaire float, maar als Decimal of als string:
  https://docs.python.org/3/tutorial/floatingpoint.html .

### Oplossing (aanbevolen)
De frontend parset de nl-NL-invoer naar een canonieke string ("1250.00"). De API-contract blijft
punt-decimaal, en de backend blijft streng: een API moet locale-vrij zijn.
1. Nieuw `frontend/src/lib/bedrag.ts`: `parseBedrag(invoer, locale='nl-NL'): string | null`.
   Het haalt het groeps- en decimaalteken via `formatToParts(12345.6)`, verwijdert spaties en het
   euroteken, en verwijdert het groepsteken alleen als het in groepen van drie staat. Daarna wordt
   het decimaalteken een punt. Het controleert met `^\d+(\.\d{1,2})?$` en geeft de string terug,
   nooit een `Number`.
   Bij twijfel ("1.250" zonder komma) volgt het de locale: nl-NL leest dat als 1250.
2. Gebruik het in `toevoegen` (`ReceivablesPage.tsx:104`) en in de PATCH. Bij `null` geeft het een
   veldfout "Bedrag: gebruik bijvoorbeeld 1250,00", zonder request.
3. Zet `inputMode="decimal"` op het veld.
4. Weergave: `rij.amount` (`:203`) via `Intl.NumberFormat('nl-NL', {style:'currency', currency})`.
5. Optioneel, als vangnet: geef de 422 met `loc` door, zodat de melding het veld noemt.

### Alternatief
Laat de backend ook een komma accepteren via een `field_validator(mode="before")`. Dat is
vergevingsgezind, maar maakt "1.250" dubbelzinnig voor andere API-klanten (Activepieces,
importen). Niet aanbevolen; hooguit alleen de vorm `^\d+,\d{1,2}$`.

### Tests
- Vitest voor `bedrag.test.ts`: "1250,00" geeft "1250.00"; "1.250,00" geeft "1250.00"; "€ 1.250,5"
  geeft "1250.50"; "1250" geeft "1250"; "12,345" geeft null (drie decimalen); "abc", "-5" en ""
  geven null; "1250.00" geeft... (beslissen: wel of niet accepteren onder nl-NL; voorstel: ja, als
  het de enige scheider is en er 1 of 2 decimalen volgen).
- `ReceivablesPageToevoegenFout.test.tsx`: met "1250,00" vertrekt een POST met `amount: "1250.00"`;
  met "abc" vertrekt geen POST en verschijnt de veldmelding.
- Backend: een regressietest dat `"1250,00"` 422 blijft (het contract).

### Risico's
Dubbelzinnige invoer ("1.250"). Leg de regel vast in de test. **Schatting: S.**
**Beslissing Rakesh:** alleen de frontend parset (aanbevolen), of ook de backend.

---

## 4. Docker-stack start niet

### Huidige toestand
- `docker-compose.yml` eist de variabelen met `${VAR:?... is verplicht}`: `:13`, `:34`, `:184`,
  `:329-332`, `:477` en verder.
- `D:/Dev/SanskritiSetu.org/.env` **bestaat en bevat alle zeven sleutels met een waarde**. Alleen
  namen zijn gecontroleerd, geen waarden; `AP_ENCRYPTION_KEY` is 32 tekens.
  `.env.example` bevat ze ook en staat als enige (met `.env.single-tenant.example`) in git.
  `.gitignore:382` (`.env*`) negeert `.env` (`git check-ignore -v` bevestigt dit).
- **Geen enkele worktree heeft een `.env`**: alle tien onder `.claude/worktrees/*` niet, en
  `D:/Dev/ss-regie` ook niet. Docker Compose leest `.env` uit de *projectmap*, dat is de map van
  het compose-bestand of de werkmap. Wie `docker compose up` in een worktree of in `ss-regie` draait,
  krijgt precies deze fout. Dat is de waarschijnlijke oorzaak.

### Bronnen
- Compose leest `.env` uit de projectmap; `--env-file` overschrijft dat:
  https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/ .
  `${VAR:?err}` stopt met een fout als de variabele leeg is of ontbreekt (zelfde pagina).
- Activepieces: `AP_ENCRYPTION_KEY` is een "32-character (16-byte) hexadecimal key ... `openssl rand -hex 16`";
  `AP_JWT_SECRET` wordt gemaakt met `openssl rand -hex 32` (de pagina noemt hier 32 tekens, maar dat
  commando geeft er 64; dat is een inconsistentie in de docs):
  https://www.activepieces.com/docs/install/configuration/environment-variables .
  `AP_WORKER_TOKEN` staat daar niet. Volgens de repo is hij vereist sinds AP 0.81.4
  (`docker-compose.yml:331`). Behandel hem als een willekeurig geheim (`openssl rand -hex 32`).
- Python `secrets` voor veilige willekeur: https://docs.python.org/3/library/secrets.html .

### Oplossing en stappen
1. Werk vanuit de hoofdcheckout: `cd D:/Dev/SanskritiSetu.org && docker compose up -d`.
   Of geef vanuit een worktree het bestand expliciet mee:
   `docker compose --env-file D:/Dev/SanskritiSetu.org/.env up -d`. Dat heeft de voorkeur boven
   kopieren, omdat je dan geen geheimen dupliceert.
2. Alleen als er nergens een `.env` is, maak je een nieuwe:
   ```bash
   cp .env.example .env
   git check-ignore -v .env      # moet .gitignore:382 tonen
   python -c "import secrets;print('AP_ENCRYPTION_KEY='+secrets.token_hex(16))"   # 32 hex
   python -c "import secrets;print('AP_JWT_SECRET='+secrets.token_hex(32))"
   python -c "import secrets;print('AP_WORKER_TOKEN='+secrets.token_hex(32))"
   python -c "import secrets;print('REDIS_PASSWORD='+secrets.token_urlsafe(32))"
   python -c "import secrets;print('POSTGRES_PASSWORD='+secrets.token_hex(24))"   # hex: geen URL-escaping nodig in DSN's
   python -c "import secrets;print('GRAFANA_ADMIN_PASSWORD='+secrets.token_urlsafe(24))"
   python -c "import secrets;print('SYNC_WEBHOOK_SECRET='+secrets.token_hex(32))"
   ```
   Plak de waarden met de hand in `.env`, niet via een echo in de shellgeschiedenis.
   Controleer met `docker compose config --quiet` (exit 0 betekent dat alles is ingevuld).
3. **Interlock:** `AP_ENCRYPTION_KEY` of `POSTGRES_PASSWORD` wijzigen op een bestaand volume is een
   secret-rotatie. Dan zijn de Activepieces-connecties onleesbaar of logt de database niet meer in.
   Doe dat alleen met het woord van Rakesh (CLAUDE.md, interlock 1). Een nieuwe `.env` hoort bij een
   leeg volume.

### Live meten door de acceptant
- **Agent factory:** stack op, inloggen als beheerder, een agent aanmaken in de UI en starten.
  Meet dat de agent in de lijst staat, dat er een run in de logs zit
  (`docker compose logs -f app worker`) en dat er een auditregel is.
- **Vier-ogenweigering bij een eigen HITL-voorstel, langs het copilot-pad:**
  1. Zet vier ogen aan voor de tenant via het `put_four_eyes`-endpoint
     (`src/core/api/v1/tool_broker/four_eyes_router.py:111`) of via het instellingenscherm.
  2. Laat gebruiker A in de copilot-chat een HIGH-risk actie vragen, bijvoorbeeld een herinnering
     sturen, of gebruik op de debiteurenpagina "Herinnering voorstellen". De Council geeft
     `HITL_REQUIRED`. Daarna roept `src/core/copilot/council/governance_gate.py:150-165`
     `HITLTicketRepository.create_hitl_request(user_id=...)` aan, en die zet
     `"_requested_by": str(user_id)` en `_requester_kind` (`src/core/tool_broker/hitl_repository.py:582-590`).
  3. A (beheerder) probeert het ticket zelf goed te keuren: verwacht **403** van
     `_refuse_self_approval` (`hitl_router.py:143-185`), plus een auditregel.
  4. Beheerder B keurt het goed: 200.
  Controle in de DB: `select payload->>'_requested_by' from hitl_requests order by id desc limit 1;`
  moet het user-id van A geven.
- **Bevinding (melden, niet oppakken):** het directe ToolBroker-pad
  (`src/core/tool_broker/router.py:460`) zet `_requested_by` op `current_user.email`. De vergelijking
  in `hitl_router.py:168-169` gebruikt `str(current_user.id)`, dus via dat pad wordt een
  zelfgoedkeuring **niet** geweigerd. Meet het copilot-pad, niet dit pad, of laat dit eerst repareren.

**Schatting:** S (env), M (acceptatie). **Beslissing Rakesh:** een aparte acceptatie-`.env` per
worktree of altijd de hoofdcheckout; en of de bevinding over `router.py:460` een ticket wordt.

---

## 5. Opruimen (alleen inventaris)

### Huidige toestand
- `git stash list`: `stash@{0}: On iter/keten-b-nazorg-frontend: bouwer-c-d-tmp` (d4f6304f,
  2026-10-07 18:48). Raakt `frontend/src/pages/AuditLogs.tsx` (-4) en `ReceivablesPage.tsx` (+15/-2).
- `git worktree list`: 11 stuks.
  - De hoofdcheckout (develop).
  - `D:/Dev/ss-regie` (regie/werkbank).
  - Onder `.claude/worktrees/`: agent-a04539f7773af9e37 (iter/debiteuren-keten-b-dag5),
    **agent-a07651c56c277df6d (iter/keten-b-nazorg-frontend, LOCKED: "claude agent ... (pid 6908)")**,
    agent-a09f8134fbea7a11c (iter/keten-b-nazorg-backend), agent-a29643e4ddbbd334c (dag2),
    agent-a336beafc1a4a2e94 (dag4), agent-a5ed8a171b943549a (dag1), agent-a7282acd0140a1b56 (dag3),
    agent-a9fa0f14232739593 (detached HEAD) en agent-af050fc61c352d3a2 (worktree-agent-af050fc61c352d3a2).
- `iter/keten-b-nazorg-backend` en `iter/keten-b-nazorg-frontend`: 0 commits voor op origin/develop,
  `merge-base --is-ancestor` geeft ja en `git cherry` geeft 0 plus-regels. Ze zijn **volledig opgenomen**.
- node_modules in `agent-a09f8134fbea7a11c/frontend`: ongeveer 489 MB (gemeten met Get-ChildItem -Recurse). PID 6908 draait niet meer (tasklist geeft geen resultaat), dus het slot is verweesd. De locked worktree heeft geen lokale wijzigingen (`git status --short` is leeg).

### Bronnen
- `git worktree remove`: een locked worktree "cannot be removed" tenzij je `--force` **twee keer**
  opgeeft; een vuile worktree vraagt een enkele `--force`. `git worktree unlock` haalt het slot weg.
  `git worktree prune` ruimt administratie op van mappen die al weg zijn, maar niet van locked
  worktrees: https://git-scm.com/docs/git-worktree .
- `git branch -d` weigert een tak die niet gemerged is; `-D` dwingt:
  https://git-scm.com/docs/git-branch .
- `git stash show -p` om eerst te bekijken; `git stash drop` is onomkeerbaar
  (alleen via reflog/fsck terug te halen): https://git-scm.com/docs/git-stash .

### Veilige volgorde (voor Rakesh of een bouwsessie)
```bash
cd D:/Dev/SanskritiSetu.org
git fetch origin
# 0. Inspectie
git stash show -p stash@{0} > "$TEMP/stash0.patch"     # bewaar, vergelijk met origin/develop
git diff origin/develop stash@{0} -- frontend/src/pages/ReceivablesPage.tsx frontend/src/pages/AuditLogs.tsx
git -C .claude/worktrees/agent-a07651c56c277df6d status --short   # per worktree: vuil?
tasklist /FI "PID eq 6908"                              # leeft de lockende agent nog?
# 1. node_modules (alleen de map, geen git-data)
rm -rf .claude/worktrees/agent-a09f8134fbea7a11c/frontend/node_modules
# 2. Worktrees van gemergde takken, eerst zonder force
git worktree remove .claude/worktrees/agent-a09f8134fbea7a11c
git worktree unlock .claude/worktrees/agent-a07651c56c277df6d    # alleen als pid 6908 weg is
git worktree remove .claude/worktrees/agent-a07651c56c277df6d
# 3. Takken (veilige -d: weigert als niet gemerged)
git branch -d iter/keten-b-nazorg-backend iter/keten-b-nazorg-frontend
# 4. Stash pas laten vallen als stap 0 liet zien dat de inhoud in develop zit
git stash drop stash@{0}
# 5. Administratie
git worktree prune --dry-run && git worktree prune
```
Dag1-dag5, a9fa0f en af050f: eerst dezelfde merge-check per tak
(`git merge-base --is-ancestor <tak> origin/develop`) voordat je ze opneemt. `ss-regie` laat je staan.

### Wat er misgaat bij een locked worktree
- `git worktree remove` weigert met "cannot remove a locked working tree". Met een enkele `-f`
  weigert hij nog steeds; pas `-f -f` dwingt, en dan haal je een map weg onder een mogelijk nog
  draaiende agent (pid 6908). Die agent schrijft dan in het niets of crasht halverwege een commit.
- `git branch -d iter/keten-b-nazorg-frontend` weigert zolang die tak in een worktree uitgecheckt is.
- `prune` slaat hem over. Unlock dus alleen als de pid niet meer bestaat.
- Windows: open bestanden (de vite-server of een editor in die map) laten `remove` of `rm -rf`
  halverwege mislukken. Stop eerst die processen.

**Schatting: S.** **Beslissing Rakesh:** stash drop (na inspectie), welke dag-takken weg mogen,
en of pid 6908 gestopt mag worden.

---

## 6. De regiesessie in de poort

### Huidige toestand
- De state staat in `<git-common-dir>/sanskritisetu-push-gate.json` (`scripts/push_gate.py:45-60`),
  gedeeld door alle worktrees.
- `whois` (`:282-301`) print de regie plus de waarschuwing dat je de naam tegen ListAgents
  moet controleren. Het script kan zelf niet zien of de sessie nog leeft. Nu: **`sanskritisetu-org-7f`,
  ingesteld 2026-09-26** (12 dagen oud, waarschijnlijk dood).
- `set-coordinator --session <naam>` (`:304-313`) overschrijft zonder enige controle. Het
  docstring (`:25`) zegt "alleen Rakesh/de regie zelf"; dat is protocol, geen slot (`:14-21`).
- `approve` (`:356-`) eist een eerdere `request` en weigert zelfgoedkeuring (zelfde sessie of
  zelfde werkmap). Het controleert **niet** of `--by` de ingestelde regie is; `check` noemt de regie
  alleen in de melding (`:426-428`).
- Is de aangewezen sessie weg, dan blokkeert niets technisch, maar volgens het protocol is de regie
  vervallen. Pushes wachten dan tot Rakesh een nieuwe aanwijst (de tekst op `:296-299`).

### Werkwijze en commando voor Rakesh
1. Start of kies de sessie die regie wordt, en geef haar de rol "regie" (CLAUDE.md).
2. Controleer de oude: `python scripts/push_gate.py whois` en daarna ListAgents. Staat de naam er
   niet bij, dan is de regie vervallen.
3. Rakesh zegt in die sessie letterlijk dat zij de regie is. Daarna draait die sessie (of Rakesh in
   een terminal, in een willekeurige worktree):
   ```bash
   python scripts/push_gate.py set-coordinator --session <exacte-sessienaam-uit-ListAgents>
   python scripts/push_gate.py whois     # verwacht: Regie: <naam> (ingesteld <nu>)
   python scripts/push_gate.py status    # openstaande aanvragen en goedkeuringen
   ```
4. Openstaande `request`s blijven geldig. De nieuwe regie keurt ze goed met
   `approve --sha <sha> --by <naam>`.

### Verbetering (optioneel, M)
`approve` laten weigeren als `--by` niet de ingestelde regie is, en `whois` een
leeftijdswaarschuwing laten geven (bijvoorbeeld ouder dan 24 uur). Test: `tests/scripts/test_push_gate.py`
met een tijdelijke `GATE_PATH`.
**Risico:** het blijft een erewoordslot, want elke sessie kan `set-coordinator` draaien.
**Schatting:** S (aanwijzen), M (verbetering). **Beslissing Rakesh:** wie de nieuwe regie wordt,
en of `approve` aan de regie gebonden moet worden.
