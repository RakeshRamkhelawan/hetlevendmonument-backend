# ADR-038: De netwerkgrens ligt bij de ingress, niet in de applicatie

## Status
Proposed

## Datum
2026-08-29

## Auteur
Claude (Opus 5), op verzoek van Rakesh, na een gemeten storing op staging tijdens de
afronding van ADR-036 OP-111.

---

## Context

Op 2026-08-29 draaide staging voor het eerst volledig: database, Redis, worker, scheduler,
migraties en een groene CD-run. Toch gaf de API op elk pad behalve `/health` en `/status`
een **403**. De oorzaak lag in twee lagen boven elkaar.

**De storing.** `security_manager.py::_get_allowed_ip_ranges` viel terug op een
hardgecodeerde default: `127.0.0.1,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16`. Geen enkel
deploy-pad zet `ALLOWED_IP_RANGES`, en `ENVIRONMENT=staging` telt niet als development
(`security_middleware.py::_is_development_mode`). Op Azure Container Apps ziet de applicatie
het PUBLIEKE client-adres, dus viel elke bezoeker buiten die default. Productie had exact
dezelfde configuratie en zou bij oplevering meteen onbereikbaar zijn geweest.

**Het lek eronder, en dat weegt zwaarder.** `_get_client_ip` nam het EERSTE element van
`X-Forwarded-For`. Die header stuurt de client zelf mee; elke proxy voegt er RECHTS aan toe.
Het eerste element is dus door de aanvaller bepaald. Gemeten tegen staging:

```
curl .../health/ready                                  -> 403
curl .../health/ready -H "X-Forwarded-For: 10.0.0.1"    -> 200
```

Dat ene punt voedt vijf controles in `security_middleware.py`, en maakte ze alle vijf
omzeilbaar:

| regel | controle | gevolg |
| --- | --- | --- |
| 116 | IP-allowlist | 403 omzeild (gemeten) |
| 131 | `blocked_ips` | een geblokkeerd adres ontwijkt de blokkade met een header |
| 147 | `check_rate_limit` | rate limiting omzeilbaar door het adres te roteren |
| 163 | threat detection | idem |
| 233 | security-event logging | de aanvaller bepaalt welk adres in de auditregels komt |

Die laatste raakt ADR-019: de auditketen legde een herkomst vast die de aanvaller koos.

**Waarom het maandenlang onzichtbaar bleef.** Geen enkele test draaide de echte
`ProductionSecurityManager` met een publiek adres. `test_security_middleware_registration_red_phase.py`
toetst de brontekst, `test_security_middleware_flow.py` mockt de manager weg, en
`test_production_security_middleware_coverage.py` asserteerde juist het eerste element --
die test legde de spoofbaarheid dus vast als gewenst gedrag.

**Waarom de default ooit klopte.** ADR-009 koos Traefik als edge gateway en stelt expliciet:
"De backend vertrouwt alleen `X-Forwarded-For` headers van de Traefik IP-range (Network
Isolation)". Dat is waar in de docker-compose-topologie waarvoor die ADR is geschreven. Azure
Container Apps komt in ADR-009 niet voor, en daar bestaat dat privénetwerk niet.

## Besluit

1. **De netwerkgrens ligt op de rand van het platform.** Op Azure is de Container
   Apps-ingress de edge gateway. Wie verkeer wil beperken doet dat met ingress-restricties
   (`ipSecurityRestrictions`), die VOOR de container worden afgedwongen en niet met een
   header te omzeilen zijn. ADR-009 blijft gelden voor de compose-topologie; daar is Traefik
   die rand.

2. **De grens van de applicatie is authenticatie plus tenant-isolatie** (JWT, RLS). Een
   IP-lijst in Python die op een client-header vertrouwt is geen grens: hij houdt eerlijke
   gebruikers buiten en aanvallers niet tegen.

3. **`ALLOWED_IP_RANGES` is opt-in.** Niet ingesteld betekent "de ingress bewaakt dit", niet
   "iedereen eruit". Wie hem invult krijgt hem onverkort gehandhaafd. Een ongeldig adres
   blijft onwaar opleveren -- de controle daarop staat bewust vóór de opt-in-tak.

4. **Het client-adres komt van de rechtse vertrouwde hop**, met het aantal proxies expliciet
   in `TRUSTED_PROXY_COUNT` (default 1: de Container Apps-ingress, en in compose Traefik).
   Op 0 wordt geen enkele forwarding-header vertrouwd en telt alleen de verbinding zelf.

## Gevolgen

**Goed:** de vijf controles hierboven werken weer zoals bedoeld; de auditketen registreert een
adres dat de aanvaller niet kiest; staging en straks productie zijn bereikbaar zonder dat
iemand een variabele moet raden.

**Kosten:** wie op de oude default vertrouwde als afscherming heeft die nu niet meer. Dat is
bewust: die afscherming was aantoonbaar te omzeilen, dus het verschil is schijnzekerheid die
verdwijnt, geen bescherming die wegvalt. Wil je staging echt privé, dan hoort dat als
ingress-restrictie in `infra/`, niet als env-var in de applicatie.

**Bewijs:** `tests/security/test_client_ip_is_not_spoofable.py`, rood-voor-groen aangetoond
(3 rood voor de wijziging, 6 groen erna). `test_production_security_middleware_coverage.py`
is aangepast omdat die het defect vastlegde, met de reden in de docstring.

## Open punt

Dit is de derde vondst van dezelfde vorm binnen OP-111: een instelling die de runtime
vereist, die geen enkel deploy-pad zet en die `config_validator.py` niet kent. Eerder waren
dat `REDIS_URL` (wel in de validator, niet in de deploy) en `DEFAULT_ADMIN_PASSWORD` (in geen
van beide). Een gedeelde bron voor "wat heeft deze omgeving nodig", met een guard die de
doorsnede toetst tussen wat de validator eist en wat de deploy zet, zou alle drie vóór de
deploy hebben gepakt. Dat is een eigen wijziging met een eigen meting en staat hier alleen
geregistreerd, niet opgelost.

## Aanvulling 2026-10-08 (plan nazorg, deel I punt b)

- **Alle `X-Forwarded-For`-headers tellen.** `_get_client_ip` voegt ze samen in volgorde en
  neemt dan het N-de adres van rechts. Alleen de eerste header lezen liet de client het adres
  kiezen als de proxy een tweede header toevoegt.
- **Geen terugval op `X-Real-IP`.** Zonder `X-Forwarded-For` telt de verbinding zelf.
- **`FORWARDED_ALLOW_IPS`** staat nu expliciet in `scripts/gunicorn_config.py`
  (`forwarded_allow_ips`, default `127.0.0.1,::1`). Productie start `gunicorn src.main:app -c
  gunicorn_config.py` met `UvicornWorker` (`scripts/entrypoint-prod.sh`); de worker geeft deze
  waarde door aan uvicorn. Zonder een waarde voor het ingress-subnet ziet `request.client.host`
  (en dus SlowAPI) het adres van de ingress. Zet de variabele per omgeving op het
  ingress-subnet. **Niet gemeten op staging**: welk adres de ingress daar gebruikt is nog niet
  vastgesteld; dat moet voor een merge naar productie.
- De IP-blokkade staat in Redis met een tijdslimiet, een allowlist
  (`SECURITY_BLOCK_EXEMPT_CIDRS`) en een vrijstelling voor een beheerder met een geldig token;
  zie `src/core/security/ip_reputation.py`.

## Aanvulling 2026-10-28 (een regel voor het klantadres)

- **Een functie, een regel.** `afzender_adres` in `src/core/shared/limiet_sleutel.py` is de enige
  bron van het klantadres voor de limietsleutel, de `SecurityMiddleware` en de
  `AuditLoggingMiddleware`. Hun eigen `_get_client_ip` (en `_trusted_proxy_count`) zijn weg. De
  auditmiddleware nam tot dan de EERSTE `X-Forwarded-For`-waarde: een door de client gekozen adres in
  het auditlog (principe 3). Regels die al in de keten staan blijven ongemoeid; alleen nieuwe regels
  krijgen het juiste adres.
- **Een instelling.** `TRUSTED_PROXY_NETWORKS` (komma-gescheiden CIDR) vervangt `TRUSTED_PROXY_COUNT`.
  Een directe afzender in een van die netwerken, of in loopback of de prive-netwerken, is een
  proxy; alleen van zo'n afzender telt `X-Forwarded-For`, en wel van RECHTS gelezen, vertrouwde
  proxy's overgeslagen. Standaard (instelling leeg) vertrouwt dit niets wat de client meestuurt. Een
  ongeldig netwerk of een netwerk dat breder is dan /8 (IPv4) of /16 (IPv6) wordt genegeerd met een
  waarschuwing in het logboek.
- **Gevolg voor staging, NIET gemeten.** `TRUSTED_PROXY_COUNT=1` vertrouwde de laatste waarde zonder
  naar de afzender te kijken. Nu moet de afzender een vertrouwde proxy zijn. Ligt de
  Container Apps-ingress buiten loopback en de prive-netwerken (bijvoorbeeld 100.64.0.0/10), dan ziet
  de app overal het adres van de ingress tot de instelling is gezet. Meten na de eerste
  staging-uitrol (alleen lezen, via het logboek van een verzoek) en dan het netwerk invullen.
