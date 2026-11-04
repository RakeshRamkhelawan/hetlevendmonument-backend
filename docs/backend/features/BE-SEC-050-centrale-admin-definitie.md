# BE-SEC-050 -- Centrale admin-definitie (ADR-036 OP-40)

**Status:** geimplementeerd, wacht op merge-GO van Rakesh
**Sprint:** ADR-036 open-punten, OP-40
**Branch:** `iter/op-40-admin-definitie`
**Datum:** 2026-09-01

---

## A. Build Summary

Zeven plekken in de codebase beslisten elk zelf of een gebruiker beheerder is, in drie
onverenigbare vocabulaires. Ze delegeren nu alle zeven naar een functie: `is_admin` in
`src/core/auth/dependencies.py`. De verzameling erkende rolnamen staat in een module-constante
`ADMIN_ROLE_NAMES`, niet in een literal in een functie.

Geen enkel endpoint, schema, model, migratie of achtergrondtaak is toegevoegd of gewijzigd. Dit is
uitsluitend een consolidatie van bestaande autorisatielogica achter bestaande dependencies.

---

## B. De gemeten uitgangssituatie

Gemeten op `develop` @ `61c5a7c1`, niet overgenomen uit de registerrij. De registerrij bleek
correct in aantal (zeven) en in vocabulaire (drie); er is EEN as bijgekomen die er niet in stond
(hoofdlettergevoeligheid, zie C).

| # | Plek | Accepteerde rollen | Superuser | Aanroepers (gemeten) |
| --- | --- | --- | --- | --- |
| 1 | `auth/dependencies.py:479 is_tenant_admin` | `{admin, tenantadmin}`, kleine letters | ja | 13 aanroepen in 4 bestanden: `api/v1/gatekeeper/gatekeeper_hitl_router.py` (1), `api/v1/tool_audit/router.py` (1), `api/v1/tool_broker/hitl_router.py` (2), `copilot/api/audit_endpoints.py` (9) |
| 2 | `auth/dependencies.py:505 require_admin` | idem, plus `role_id == 1` | ja | `api/debug_endpoints.py` (2), `api/v1/admin/experiments.py` (9), `api/v1/feature_flags/admin_router.py` (1), `scheduling/api/partner_routes.py` (9) |
| 3 | `api/dependencies.py:172 require_admin_role` | `{admin, system_admin}`, exacte case | NEE | `api/admin_digital_twin.py` (1), `api/admin_learning_endpoints.py` (7) |
| 4 | `api/dependencies.py:144 require_admin_user` | `{admin}`, exacte case | ja | **nul** -- gemeten met `git grep`; alleen de definitie en een verwijzing in een docstring |
| 5 | `api/v1/tenant_management/dependencies.py:18 require_admin` | `{admin, system_admin}` | NEE | `crud_router.py` (6 verwijzingen) |
| 6 | `api/v1/user_management/dependencies.py:18 require_admin` | `{admin, system_admin}` | NEE | `crud_router.py` (6), `profile_router.py` (2) |
| 7 | `api/v1/admin/dependencies.py:35 require_admin_role` | `{admin, system_admin}` | NEE | `monitoring_router.py` (5), `users_router.py` (4) |

### Achtste plek, bewust NIET geconsolideerd

`src/core/api/v1/foundation/dependencies.py:260 require_admin` beslist ook zelf, maar op een ANDER
identiteitsmodel: `PortalUser.role != PortalRole.ADMIN` (ADR-029 onderwijsportaal). Dat is een
enum-veld op een apart gebruikerstype, geen rolnamenlijst op `UserResponse`. Hem meenemen zou twee
autorisatiedomeinen samenvoegen die niets delen. Gerapporteerd, niet aangeraakt.

---

## C. De vierde as die niet in de registerrij stond: hoofdlettergevoeligheid

`RoleSeeder.DEFAULT_ROLES` maakt de standaard-beheerdersrol aan onder de naam `"Admin"` met
hoofdletter (`src/core/services/role_seeder.py:44`), en `AuthService` vult `UserResponse.roles`
met `[role.name for role in user.roles]` -- de ruwe databasenaam
(`src/core/auth/auth_service.py:411` en `:447`).

Plek 1 en 2 zetten die naam om naar kleine letters; de plekken 3 tot en met 7 vergeleken exact.
Een gebruiker met alleen de geseede standaard-beheerdersrol was dus beheerder voor twee van de
zeven plekken en gewoon gebruiker voor vijf. Dat is gemeten via het testprofiel
`geseede rol Admin met hoofdletter`, dat voor de fix rood was.

De centrale functie vergelijkt hoofdletter-ongevoelig. Dat is geen verbreding van het besluit maar
het gedrag dat plek 1 en 2 al hadden.

---

## D. De implementatie

### `ADMIN_ROLE_NAMES` (`src/core/auth/dependencies.py`)

```python
ADMIN_ROLE_NAMES: frozenset[str] = frozenset({"admin", "system_admin", "tenantadmin"})
```

De unie van de drie vocabulaires, op expliciet besluit van Rakesh. De oude naam
`TENANT_ADMIN_ROLE_NAMES` is VERWIJDERD: `git grep` geeft nul importeurs en hij stond ook niet in
`__all__` van de commit ervoor (een eerdere versie van dit doc beweerde van wel -- onjuist). Een
alias die niemand gebruikt en die inmiddels breder is dan zijn naam suggereert, is een val voor de
volgende lezer.

### `is_admin(user) -> bool`

- Superuser-bypass eerst; daarna de rolnamen.
- Rolnamen worden `strip().lower()` en vergeleken tegen `ADMIN_ROLE_NAMES`.
- Niet-string-elementen in `roles` worden genegeerd in plaats van een `AttributeError` te geven
  (fail-secure; de vorige vorm crashte met een 500).
- Als de superuser-bypass de ENIGE reden voor toegang is, wordt dat op INFO gelogd met het
  user_id. Deny-by-default kent hier een uitzondering, en die uitzondering hoort zichtbaar te
  zijn (OWASP ASVS 5.0 V8.3.1).

### `is_tenant_admin(user) -> bool`

Blijft bestaan als doorgeefluik naar `is_admin`, zonder eigen logica. Reden: dertien aanroeppunten
in vier bestanden plus de architecture-guard `tests/architecture/test_hitl_audit_is_admin_only.py`
gebruiken die naam. Hernoemen raakt al die plekken zonder dat er gedrag verandert.

### De zes dependencies

`auth/require_admin`, `api/require_admin_role`, `api/require_admin_user`,
`tenant_management/require_admin`, `user_management/require_admin` en
`admin/require_admin_role` roepen nu `is_admin` aan. Elk behoudt zijn EIGEN
`HTTPException`-detailtekst en zijn eigen logregel, zodat het API-contract van geen enkel endpoint
verandert.

Een uitzondering, expliciet: `auth/require_admin` behoudt de legacy-tak `user.role_id == 1`. Die
verbreedt alleen die ene dependency en hoort daarom niet in de centrale functie. `role_id` wordt
gevuld uit de eerste rol; een via die weg ingerichte beheerder zonder benoemde rol zou anders zijn
toegang verliezen op elk endpoint achter `RequireAdmin`.

### Tenant-isolatie

`is_admin` weegt geen tenant-scope mee -- het kijkt alleen naar rolnamen.

**Een eerdere versie van deze paragraaf schreef de tenant-grens toe aan ADR-004
(`do_orm_execute`). Dat is onjuist, en de code-review heeft het weerlegd. Nagemeten:**

- `auth_service.py:398` en `:431` -- de twee queries die `UserResponse.roles` vullen, draaien
  allebei binnen `with TenantFilterBypass():`, met de comment "bypass tenant filter because we
  don't have tenant context during token verification". Op precies deze leesroute staat de
  ADR-004-hook dus UIT.
- `user_roles` heeft geen `tenant_id`-kolom en is expliciet van RLS uitgesloten
  (`20260522_add_rls_core_tables.py`). Er is dus ook geen schema-constraint.

Wat de grens WEL afdwingt is het SCHRIJFpad: `user_management/crud_router.py:518` filtert
`Role.tenant_id == user.tenant_id` voor de insert en `rbac_service.assign_role` neemt een
`tenant_id`-parameter. Een gebruiker kan dus geen rol van een andere tenant in zijn lijst krijgen.
Dat is een zwakkere garantie dan een hook of een constraint -- ze hangt aan de zorgvuldigheid van
elk toekenningspad -- en dat hoort hier te staan in plaats van een mechanisme dat er niet is.

Deze correctie staat ook in de docstring van `is_admin` zelf.

---

## E. Wat er inhoudelijk verandert per aanroeppunt (privilege-uitbreiding)

Dit is de informatie die voor de merge gezien moet worden. Elke regel is een ECHTE uitbreiding:
een rol die er eerst niet bij kon en er nu wel bij kan.

De kolom "geserveerd" is gemeten met een route-enumeratie (`register_all_routers` op een lege
FastAPI-app, 788 routes) door de security-review, niet met `git grep`. Dat onderscheid is precies
de les van OP-37: aanroepers tellen zegt niets over of een router gemount is.

| Aanroeppunt | Wint toegang | Geserveerd | Concreet geraakte endpoints |
| --- | --- | --- | --- |
| 1 `is_tenant_admin` | `system_admin` | ja | HITL goedkeuren/afwijzen (gatekeeper), HITL-auditarchief, tool-audit, 9 copilot-auditendpoints |
| 2 `auth/require_admin` | `system_admin` | ja | debug-endpoints, 9 experiment-endpoints, feature-flag-admin, 9 partner-routes |
| 3 `api/require_admin_role` | `tenantadmin`, superuser, `"Admin"` | ja | digital-twin-admin, 7 admin-learning-endpoints |
| 4 `api/require_admin_user` | `system_admin`, `tenantadmin`, `"Admin"` | n.v.t. | geen -- nul aanroepers |
| 5 `tenant_management/require_admin` | `tenantadmin`, superuser, `"Admin"` | **NEE** | geen. `src.core.api.v1.tenant_management.*` levert nul routes op; het is een legacy shim (`# orphan:exempt -- superseded by v1/tenants/router.py`). De geserveerde tenant-CRUD is `v1/tenants/*` en heeft eigen checks die deze wijziging NIET raakt |
| 6 `user_management/require_admin` | `tenantadmin`, superuser, `"Admin"` | **NEE** | geen, om dezelfde reden. De geserveerde user-CRUD is `v1/users/*` |
| 7 `admin/require_admin_role` | `tenantadmin`, superuser, `"Admin"` | ja | monitoring, en -- belangrijker dan eerder opgeschreven -- `POST /admin/create_user` en `POST /admin/assign_role/{user_id}`, die de ROLNAAM uit de request body nemen (`users_router.py:33 role: str = "admin"`). Dat is rol-uitgifte met een vrije naam, geen gewone gebruikersaanmaak |

Een eerdere versie van deze tabel noemde bij rij 5 en 6 "tenant-CRUD" en "user-CRUD,
profielbeheer" als geraakte endpoints. Dat was onjuist en overdreef de impact: die routers worden
niet gemount. Het blijft wel latent risico -- `user_management/crud_router.py` draait
`update_user`, `assign_user_roles` en `create_user` binnen `TenantFilterBypass()` met een
tenant-id uit query of pad -- maar deze wijziging maakt dat niet bereikbaar.

**De twee scherpste regels, en ze staan allebei niet in de registerrij:**

1. Rij 1: een `system_admin` kan nu HITL-tickets goedkeuren. Dat is de bedoelde uitkomst van
   OP-40, maar het is een uitbreiding van wie de AI Act art.-14-poort mag openen, en op die route
   staat GEEN functiescheiding naast de rolcheck (OP-81 is open; `_refuse_self_approval` bestaat
   alleen op het niet-geserveerde `tool_broker`-zusteroppervlak).
2. Rij 7: `tenantadmin` wint toegang tot endpoints die zelf rollen met een vrije naam uitdelen.
   Zie sectie L.

---

## F. Foutpaden

Onveranderd. Elke dependency geeft `403` met dezelfde detailtekst als voorheen:

| Plek | `detail` |
| --- | --- |
| `auth/require_admin` | `Admin privileges required` |
| `api/require_admin_role` | `Admin access required` |
| `api/require_admin_user` | `Admin privileges required` |
| `tenant_management/require_admin` | `Admin access required` |
| `user_management/require_admin` | `Admin privileges required for user management` |
| `admin/require_admin_role` | `Admin access required` |

Er is een gedragswijziging in het logpad: de aparte "has NO roles"-tak is samengevoegd met de
"geen beheerdersrol"-tak. De statuscode en de detailtekst zijn identiek; alleen de logregel
verschilt. Dat is gedekt door `test_a_user_without_any_role_gets_403` voor alle zeven plekken.

---

## G. Tests

| Bestand | Wat het vastlegt |
| --- | --- |
| `tests/unit/auth/test_admin_definition_is_consistent.py` | Gedrag: alle zeven plekken geven hetzelfde antwoord, EN wat dat antwoord is. Plus de 403-regressie per aanroeppunt (een regel per plek), in twee vormen: rol `viewer` en helemaal geen rol. |
| `tests/architecture/test_admin_checks_use_the_central_definition.py` | Structuur: elk van de zeven roept de centrale definitie aan, en geen van de zeven noemt zelf een beheerdersrolnaam. Met een vangnet dat de docstring-uitsluiting load-bearing houdt, en beide analyserichtingen permanent vastgelegd. |

De gedragstest is bewezen rood op commit `8f4d8430` (4 failed, 17 passed) en groen na de fix
(21 passed). De guard is per element van `ADMIN_CHECK_SITES` gemuteerd; de uitkomsten staan in de
moduledocstring van de guard.

---

## H. Trainingssamenvatting

- Actor: geauthenticeerde gebruiker met rol `system_admin`
  Voorwaarde: geldig JWT met tenant-claim (ADR-003); rol `system_admin` in `UserResponse.roles`
  Actie: roept een endpoint aan achter een willekeurige van de zeven admin-checks
  Systeemreactie: `is_admin` herkent `system_admin` in `ADMIN_ROLE_NAMES` en geeft `True`
  Succes: `200` met de payload van het endpoint, bij alle zeven checks identiek
  Fout: geen
  Uitzonderingen: voor de fix gaf plek 1, 2 en 4 hier `403` en de rest `200`

- Actor: superuser zonder benoemde beheerdersrol (`is_superuser=True`, rollen `["viewer"]`)
  Voorwaarde: geldig JWT; `is_superuser` op het gebruikersobject
  Actie: roept een endpoint aan achter een van de zeven admin-checks
  Systeemreactie: `is_admin` neemt de superuser-bypass en logt op INFO dat de bypass de enige
  reden voor toegang is
  Succes: `200`
  Fout: geen
  Uitzonderingen: voor de fix gaven de plekken 3, 5, 6 en 7 hier `403`

- Actor: gebruiker met alleen de geseede standaardrol `"Admin"` (hoofdletter)
  Voorwaarde: rol aangemaakt door `RoleSeeder.seed_default_roles`
  Actie: roept een endpoint aan achter een van de zeven admin-checks
  Systeemreactie: `is_admin` zet de rolnaam om naar kleine letters en herkent hem
  Succes: `200`
  Fout: geen
  Uitzonderingen: voor de fix werkte dit alleen bij plek 1 en 2

- Actor: gebruiker met rol `viewer`, of zonder enige rol
  Voorwaarde: geldig JWT, geen beheerdersrol, geen `is_superuser`
  Actie: roept een endpoint aan achter een van de zeven admin-checks
  Systeemreactie: `is_admin` geeft `False`; de dependency logt de weigering en werpt
  `HTTPException`
  Succes: niet van toepassing
  Fout: `403` met de detailtekst van die specifieke dependency (zie F)
  Uitzonderingen: geen -- dit gedrag is voor en na de fix identiek, en staat vast in
  `TestANonAdminIsRefusedAtEveryCallPoint` met een regel per aanroeppunt

---

## I. Afwijkingen van de geraadpleegde best practice

De consolidatie zelf is precies wat OWASP aanbeveelt. De BREEDTE van de gekozen verzameling is dat
niet, en dat staat hier expliciet.

| Bron | Wat die zegt | Volgen wij? |
| --- | --- | --- |
| OWASP Authorization Cheat Sheet, "Validate the Permissions on Every Request" | het mechanisme moet application-wide configureerbaar zijn in plaats van per methode of klasse herhaald | ja -- een constante plus een predicaat, aangeroepen door alle zeven |
| OWASP Top 10 A01:2021 / A01:2025 | "Implement access control mechanisms once and re-use them throughout the application" | ja -- dat is letterlijk deze wijziging |
| OWASP Top 10 A01, "deny by default" | alles behalve publieke resources standaard weigeren | ja voor de rolnamen; de superuser-bypass is een expliciete uitzondering, nu met logging |
| OWASP ASVS 5.0 V8.3.1 | handhaving in een trusted service layer, niet op iets wat de consumer manipuleert | ja -- rollen komen uit `AuthService` op basis van het JWT, nooit uit de request body |
| OWASP ASVS 5.0 V8.2.1 | functieniveau beperkt tot consumers met EXPLICIETE permissies | **nee, afgeweken** -- zie J punt 1 en 2 |
| OWASP ASVS 5.0 V8.1.1 | de autorisatieregels moeten gedocumenteerd zijn | ja -- dit document plus de docstring van `is_admin` |
| OWASP ASVS 5.0 V8.3.3 | beslis op de permissies van het oorspronkelijke subject | ja -- `get_current_user`, geen dienst die namens iemand handelt |
| FastAPI, dependencies in path operation decorators | het canonieke mechanisme, per endpoint/router/globaal | ja -- de zes blijven FastAPI-dependencies; alleen hun inhoud is vervangen |
| Oso, "Why Authorization is Hard" | "If we add a new user role, 'editor,' we don't want to hunt through the code-base for all the places where we'll need to update the logic"; scheid beslissing van handhaving | ja -- `is_admin` is de beslissing, de zes dependencies zijn de handhaving |

---

## J. Wat ik anders zou doen, en waarom

Vier punten. Het besluit over de brede verzameling is van Rakesh en staat vast; dit is wat er
tegenover staat, zodat het een geinformeerd besluit blijft.

1. **Least privilege.** De unie verleent op elk aanroeppunt het MAXIMUM van wat daar voorheen
   gold. Consolidatie is de OWASP-aanbeveling; verbreding is dat niet. Sectie E noemt per plek
   welke rol daadwerkelijk toegang wint. Het alternatief dat wel centraliseert zonder te
   verbreden: `is_admin(user, level=...)` met een vereist niveau als parameter, zodat de definitie
   op een plek staat maar een HITL-goedkeuring een ander niveau kan eisen dan een monitoring-lijst.
   Dat is een groter ontwerp en een eigen beslissing.
2. **Deny by default wordt onleesbaar per aanroeppunt.** ASVS 8.1.1 en 8.2.1 vragen dat je per
   permissie kunt rechtvaardigen waarom hij verleend is. Met een grofmazige unie is het antwoord
   overal hetzelfde -- "hij is beheerder" -- en dat is geen rechtvaardiging meer, alleen een
   herhaling.
3. **De superuser-bypass concentreert het risico in de integriteit van een attribuut.** Wie
   `is_superuser` kan zetten, kan alles. Ik heb INFO-logging toegevoegd wanneer die bypass de
   enige reden voor toegang is. Wat ik NIET heb gedaan en wel zou aanraden: dit als
   `SecurityEvent.SUPERUSER_BYPASS` in de ADR-019 auditketen loggen, zoals
   `require_permission_with_tenant_bypass` al doet. Dat vereist een `async` predicaat en een
   database-sessie, en dat verandert de vorm van alle zeven aanroeppunten -- buiten deze scope.
4. **`tenantadmin` is naar zijn aard tenant-gebonden.** Een predicaat dat alleen naar de rolNAAM
   kijkt, kan die begrenzing verliezen. Ik heb dit eerst als "GEMETEN, geen probleem" afgesloten.
   **Dat was te kort door de bocht en de reviews hebben het op twee manieren gecorrigeerd:**

   - Het MECHANISME dat ik noemde was fout (ADR-004 staat op de leesroute uit; het is het
     schrijfpad dat de grens houdt) -- zie sectie D.
   - Belangrijker: de meting dekte alleen het PREDICAAT, niet de KETEN. Het predicaat geeft een
     `tenantadmin` van tenant A inderdaad geen rol in tenant B. Maar sinds deze wijziging passeert
     die `tenantadmin` wel aanroeppunt 7, en daarachter zit `POST /admin/create_user` /
     `POST /admin/assign_role/{user_id}`, dat een rolnaam uit de request body accepteert. Daarmee
     kan hij zichzelf een `system_admin`-account aanmaken, en `system_admin` mag via
     `_enforce_tenant_access` en `override_tenant_id` wel de tenant-grens over. Zie sectie L.

   De juiste conclusie is dus: het predicaat verliest de grens niet, maar de verbreding geeft
   toegang tot endpoints die de rol kunnen uitgeven die de grens legitiem oversteekt. Dat is geen
   van de vier punten die ik als afgesloten kan rapporteren.

---

## L. Twee escalatiepaden die deze wijziging NIET veroorzaakt maar wel vergroot

Gevonden door de security-review op deze wijziging, en door mij nagemeten in de code. Allebei
PRE-EXISTING: ze bestaan onafhankelijk van OP-40. Ze staan hier omdat de consolidatie hun bereik
vergroot van enkele poorten naar alle zeven, en omdat de beslissing over de brede rolverzameling
niet los van deze twee te beoordelen is.

**L1. `POST /api/v1/auth/register` accepteert een vrije rolnaam en MAAKT de rol aan.**
Nagemeten: `UserCreate.role_name: str = "user"` (`auth_service.py:24`) heeft geen validator, en
`create_user` doet bij een onbekende rolnaam `role = Role(name=requested_role, tenant_id=...)`
plus `db.add(role)` (`auth_service.py:175-179`). Er is dus geen allowlist en geen reserved-name
check. Wie deze route kan aanroepen, kan een account met de rolnaam `admin`, `system_admin` of
`tenantadmin` laten aanmaken.

**L2. `POST /admin/create_user` en `POST /admin/assign_role/{user_id}` nemen de rolnaam uit de
request body.** `users_router.py:33` heeft `role: str = "admin"` als body-veld, zonder allowlist.
Achter aanroeppunt 7, dat sinds deze wijziging ook `tenantadmin` en superuser doorlaat. Een
tenantbeheerder kan zo een `system_admin` minten, en `system_admin` mag via
`admin_learning_endpoints._enforce_tenant_access` en `admin_digital_twin.override_tenant_id` de
tenant-grens over.

**Waarom niet in deze commit gefixt.** Beide vragen een eigen rode test, een eigen fix en een
besluit over wat een legitieme rolnaam is (allowlist? privilege-escalatie-verbod: je kunt niet
uitdelen wat je zelf niet hebt?). Dat is een aparte wijziging en geen bijvangst van een
consolidatie -- Karpathy regel 3. De borging is dat ze hier staan, in het rapport aan Rakesh, en
dat de vier cross-tenant-poorten die het escalatiepad afmaken onder
`test_the_cross_tenant_checks_did_not_widen_to_the_broad_definition` staan, zodat ze niet
stilletjes ook nog verbreden.

**Advies:** L1 en L2 als eigen OP-nummers registreren en met voorrang oppakken. L1 is een
zelfbedieningspad naar een beheerdersrol.

---

## K. Niet gedaan

- De ADR-036 registerrij OP-40 is niet bijgewerkt -- dat gebeurt centraal.
- Er is niet gemerged naar `develop` of `main` en er is geen tag aangemaakt.
- `src/core/api/v1/foundation/dependencies.py` (`PortalUser`) is niet aangeraakt; zie B.
- De spelling `tenant_admin` MET underscore, die in `src/core/api/domain_packs.py:86,102,122,159`
  en in `src/core/company/board_service.py:617` voorkomt, valt buiten `ADMIN_ROLE_NAMES`. Het
  besluit noemt `tenantadmin` zonder underscore; hem toevoegen zou het besluit verbreden. Gemeten
  en gerapporteerd, niet gewijzigd.
