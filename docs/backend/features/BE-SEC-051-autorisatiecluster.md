# BE-SEC-051 -- Autorisatiecluster (ADR-036 OP-254/255/256/257/258, OP-189, OP-199)

**Status:** geimplementeerd, gepusht naar `develop` na goedkeuring door Rakesh
**Sprint:** ADR-036 open-punten, autorisatiecluster
**Branch:** `iter/op154-inlogpad`
**Datum:** 2026-09-18

---

## A. Build Summary

Zeven registerrijen in een reeks, met een gemeenschappelijke vorm: **iets dat groen leest
terwijl het niets doet.** Een cache die niemand kon zien, een endpoint dat altijd faalde,
een conditie die zichzelf ophief, een tweede schrijfpad, een privilege-as zonder definitie,
en een test die zijn eigen invoer aan beide kanten verzon.

Register 84 -> 77 open. Nieuw open: geen.

| OP | Wat |
| --- | --- |
| 254 | De permissiecache is VERWIJDERD; een ingetrokken recht werkte tot een uur door |
| 255 | `add_permission_to_role` kon nooit slagen (NOT NULL `tenant_id` ontbrak) |
| 256 | Rechten wijzigen controleerde niet of de rol bij de klant van de aanvrager hoort |
| 257 | Een voorwaardelijk recht zonder resourcecontext viel door naar "toegestaan" |
| 258 | Rollen toewijzen bestond twee keer; nu een deur (`RBACService.vervang_rollen`) |
| 189 | `User.is_superuser` had geen definitie; nu `is_platform_superuser`, 17 plekken |
| 199 | De superuser-bypass had geen werkende verificatie; beide oude tests waren stuk |

---

## B. OP-254 -- de cache, en waarom hij weg is in plaats van gerepareerd

`user_has_permission` bewaarde elke autorisatiebeslissing onder
`perm:{tenant}:{user}:{permission}:{resource_type}:{resource_id}` met een TTL van
`config.redis_cache_ttl` (default 3600s), in Redis zodra `REDIS_URL` gezet is -- op staging
dus gedeeld over replicas en bestand tegen een containerherstart.

Gemeten via de ECHTE servicemethodes tegen PostgreSQL:

| Handeling | Antwoord daarna |
| --- | --- |
| `assign_role()` | bleef False -- het toegekende recht werkte niet |
| `remove_permission_from_role()` | bleef True -- **het ingetrokken recht werkte door** |

De tweede regel is de ernstigste: dat is geen vertraging maar een actieve
autorisatie-bypass, tot een uur lang, zonder noodrem behalve handmatig ingrijpen.

**Vier metingen achter het besluit om te verwijderen in plaats van invalidatie bij te
bouwen:**

1. De cache leverde mediaan 2,18 ms en p95 2,85 ms per controle, bij een of twee controles
   per verzoek en nul aanroepers in een lus.
2. Hij kostte tot een uur verkeerde autorisatie.
3. Van de zes plekken die rechten wijzigen deed er EEN de invalidatie (`revoke_role`, met
   een CRITICAL-comment erboven). De plicht was dus al vijf van de zes keer vergeten.
4. **Geen enkele test kon hem zien.** Het cache-LEESpad stond achter
   `if not self.is_testing:` en `tests/conftest.py:58` zet `TESTING=1`. Een bewaker erop
   was per constructie hol.

Meeverwijderd: dat testluik en de Redis-client die per verzoek werd gemaakt en nooit
gesloten.

Gate 2 gaf tweemaal CHANGES_REQUESTED op het OORSPRONKELIJKE ontwerp (invalidatie
bijbouwen); beide reviewers adviseerden onafhankelijk eerst te meten of de cache zijn prijs
waard was. Die meting leidde tot het kleinere besluit.

**Correctie op mijn eigen tussenrapportage:** ik meldde eerst dat ook de revoke-richting
cache-blijvend was. Dat was ONJUIST -- ik had de rol met rauwe SQL verwijderd en daarmee de
invalidatie in `revoke_role` omzeild. Hermeten via de echte methodes en gecorrigeerd.

---

## C. OP-255 en OP-256 -- waarom die samen moesten

`add_permission_to_role` bouwde een `RolePermission` ZONDER `tenant_id`, terwijl die kolom
`nullable=False` is zonder default. Gemeten: `NotNullViolationError`, gevangen door de eigen
except, methode gaf `False`, endpoint gaf HTTP 400. Een rol een recht geven via de API was
onmogelijk.

Beide methodes namen `role_id` bovendien rauw uit het URL-pad. De route was dus dicht door
een BUG, niet door een controle -- en wie de bug repareert zonder de controle, opent hem.
Daarom in een wijziging.

De rol wordt nu geladen met `Role.id == role_id AND Role.tenant_id == tenant_id` en een
onbekende rol geeft `NotFoundError` (404, bewust geen 403: een 403 bevestigt dat die rol
ergens bestaat).

**Waarom dit maandenlang groen stond:** de twee tests die dit pad raken vervangen precies de
kapotte methode door een nepversie die True geeft (`monkeypatch.setattr` in
`tests/integration/test_rbac_middleware_coverage.py:502` en `:741`). Ze toetsen de bedrading
van de router en nooit de methode.

---

## D. OP-257 -- fail-secure waar het eerst fail-open was

`_evaluate_conditions` eindigde op een comment "Default: conditions met" gevolgd door
`return True`. De takken voor `owner_only` en `same_tenant` eisen allebei `resource_id` EN
`resource_type`; ontbreekt er een, dan werden ze overgeslagen en gaf de staart `True`. Een
permissierij met `owner_only` werd dus ONVOORWAARDELIJK toegekend zodra de aanroeper geen
resource meegaf.

Gemeten onbereikbaar vandaag: geen enkele aanroeper geeft resourcecontext mee, en er staat
nul permissierijen met condities in de database. Gedicht voordat iemand de eerste
conditionele rij aanmaakt.

---

## E. OP-258 -- een handeling, een deur

`user_management/crud_router.py::assign_user_roles` verving de rolset met rauwe
`user_roles.delete()` plus N `insert()` en raakte `RBACService` nergens aan. Zelf nagemeten
wat dat pad WEL deed: het controleerde per rol `Role.tenant_id` en schreef een auditregel.
Er was dus geen klantlek en geen ontbrekende audit.

Het probleem is de VORM. Bij OP-254 bleek een noodzakelijke stap op EEN van de zes
schrijfplekken te staan, precies omdat de andere vijf niet door dezelfde deur gingen.

`RBACService.vervang_rollen` is nu die deur; het gedrag is bewust IDENTIEK gehouden,
inclusief het overslaan van een rol die niet bij deze klant hoort.

**Bewust blijvend**, gedateerd met staleness-test: `crud_router.create_user` en
`AuthService.create_user` kennen rollen toe BINNEN de transactie die de gebruiker aanmaakt,
voor de enige commit. `vervang_rollen` committeert zelf, dus die erin schuiven zou de
aanmaak niet langer atomair maken. Eigen besluit, eigen risico.

---

## F. OP-189 -- de tweede privilege-as

Dit systeem heeft er twee, en ze beantwoorden verschillende vragen:

    is_admin               -- mag deze gebruiker beheren BINNEN zijn eigen tenant?
    is_platform_superuser  -- mag deze gebruiker BUITEN zijn tenant kijken en handelen?

De tweede stond op 17 beslissende plekken in 9 bestanden los uitgeschreven (de registerrij
zei 19 over 10; hermeten op de actuele boom). Alle 17 gaan nu door de centrale functie, via
de domein-facade van hun eigen domein -- rechtstreeks uit `auth.api_deps` importeren brak
het ADR-033 fan-out-budget van `core_api` (gemeten 560 tegen 557, en die guard had gelijk).

**Drie metingen die de ernst bijstellen:**

1. `is_superuser` wordt NERGENS via een API gezet. Geen request-schema in `src/` kent het
   veld; de enige schrijvers zijn `database/seed.py:276` en `ensure_demo_user.py:115`. Het
   is een bootstrapvlag van de platformeigenaar, geen escalatiepad.
2. De vlag is NIET dezelfde as als de ROL met de naam `superuser`. Die rol wordt nergens
   aangemaakt of geseed (nul treffers in `database/` en de rolseeder), terwijl twee checks
   in `api/v1/system/` erop toetsen -- die kunnen dus alleen via `admin` slagen.
3. `RBACService._user_is_superuser` bevroeg precies die nooit-bestaande rol, had nul
   aanroepers, en gaf altijd False terwijl zijn eigen comment zei dat hij "in production" de
   KOLOM zou moeten lezen. VERWIJDERD, niet gerepareerd: een tweede stil altijd-false
   antwoord op deze vraag is gevaarlijker dan geen antwoord.

---

## G. OP-199 -- de bevinding was erger dan de registerrij zei

De rij noemde twee kapotte tests en als oplossing "het patchdoel bijwerken". Bij het lezen
bleek test (b) HOL: hij patchte `log_security_event`, riep die functie DAARNA zelf aan, en
toetste vervolgens dat de mock was aangeroepen. De productiecode kwam er niet in voor. **Het
patchdoel repareren had hem groen gemaakt zonder dat hij ooit iets toetste.**

Test (a) droeg een skip met reden "Flaky: passes in isolation, fails in full suite". Die
reden klopte niet meer: hij patchte een module die niet bestaat, dus hij zou deterministisch
falen en niet wisselend. En hij toetste alleen `result == 1`, nooit de auditregel.

Beide verwijderd, met een geschreven reden op hun plek. De vervanger loopt over de echte
producent en staat in `tests/unit/`, BINNEN de testpoort -- `tests/security` valt daarbuiten,
en dat is de reden dat niemand de kapotte test zag.

Bevestigd dat het pad dood blijft: `require_permission_with_tenant_bypass` heeft nul
aanroepers in `src/`. De test bewaakt dat de auditregel er nog staat als iemand het pad weer
in gebruik neemt.

---

## H. Trainingssamenvatting

**Actor:** een beheerder van een klant, en (voor OP-189) de platformeigenaar.

**Voorwaarde:** de beheerder is ingelogd en heeft `TENANT_ADMIN` op zijn eigen klant.

**Actie:** een rol een recht geven of afnemen, de rolset van een gebruiker vervangen, of een
handeling doen die de klantgrens overschrijdt.

**Systeemreactie:** de wijziging werkt METEEN door -- er is geen cache meer. Een rol die bij
een andere klant hoort bestaat voor deze beheerder niet. Een rolwijziging loopt via een
plek. Een handeling over de klantgrens vraagt de platformvlag, via een definitie.

**Succes:** de rechtenwijziging is zichtbaar bij de eerstvolgende controle; response 200 met
de resulterende rolnamen.

**Fout:** een rol van een andere klant geeft 404 (bewust geen 403 -- dat zou bevestigen dat
de rol bestaat). Een voorwaardelijk recht zonder resourcecontext geeft "nee". Een `role_id`
dat niet bestaat wordt bij het vervangen van een rolset overgeslagen met een waarschuwing,
niet geweigerd -- bestaand gedrag, bewust niet veranderd in deze wijziging.

**Uitzonderingen:** twee plekken schrijven bewust nog rauw op `user_roles`, beide binnen de
aanmaaktransactie van een gebruiker; gedateerd met staleness-test.

---

## I. Tests

| Bestand | Wat het bewaakt |
| --- | --- |
| `tests/unit/rbac/test_de_permissiecontrole_heeft_geen_cache.py` | structureel: er is geen cache meer |
| `tests/integration/security/test_een_rechtenwijziging_werkt_meteen.py` | gedrag, beide richtingen, echte database |
| `tests/unit/rbac/test_een_rol_van_een_andere_klant_wordt_geweigerd.py` | OP-255 en OP-256 |
| `tests/unit/rbac/test_een_conditie_zonder_context_weigert.py` | OP-257, plus de tegenrichting |
| `tests/architecture/test_rollen_toewijzen_gaat_door_een_deur.py` | OP-258, AST, uitzondering per `bestand::functie` |
| `tests/architecture/test_de_superuservlag_heeft_een_definitie.py` | OP-189, AST plus een gedragstest op de functie zelf |
| `tests/unit/auth/test_de_superuser_bypass_wordt_gelogd.py` | OP-199, over de echte producent |

Alle guards zijn in BEIDE richtingen mutatie-getest, met een regel per bewaakt element; het
bewijs staat in de docstrings.

Meetuitkomsten: pyright 0 errors, ruff schoon, gerichte regressiesets 1695 en 1689 passed
met 0 failed, volledige testpoort 16657 passed / 0 failed.

---

## J. Wat ik anders zou doen, en waarom

**De guard-uitzondering meteen fijnmazig maken.** Mijn eerste versie van de OP-258-guard had
het BESTANDSPAD als sleutel. Alle drie de voorwaartse mutaties bleven groen, omdat
`crud_router.py` al op de lijst stond wegens `create_user`. Zonder het mutatiebewijs was een
blinde bewaker ingecheckt. De les staat nu in `.claude/rules/quality-gates.md`.

**Eerder meten of een cache zijn prijs waard is.** Mijn eerste ontwerp was invalidatie
bijbouwen op zes plekken -- precies de vorm die het probleem veroorzaakte. Twee reviewers
moesten dat onafhankelijk tegenspreken voor ik ging meten.

**Een registerrij eerder hermeten.** Twee van de zeven rijen klopten niet meer. Beide waren
waar op hun meetdatum; hermeten hoort vooraan te staan, niet halverwege.

**Het bewijs niet weggooien.** Ik haalde de uitvoer van een push door `tail`, waardoor de
exitcode verdween en een GEWEIGERDE push als geslaagd las. Die valkuil stond al in mijn eigen
aantekeningen.

---

## K. Niet gedaan

- **De rest van het omheinde P0-cluster** (OP-182 t/m OP-188, OP-190 t/m OP-193). OP-189 is
  er op aanwijzing van Rakesh los uit gehaald; de rest wacht op zijn moment.
- **Een guard op het SCHRIJFpad van `is_superuser`.** Gemeten dat geen request-schema het
  veld kent, maar niets dwingt dat af. Wie het aan een update-schema toevoegt, maakt van een
  bootstrapvlag een escalatiepad en geen enkele test wordt daarvan rood. **Dit is het
  scherpste open risico van deze reeks.**
- **De twee resterende rauwe schrijfplekken op `user_roles`** -- bewust, transactioneel,
  gedateerd met staleness-test.
- **Een vergelijkingstest tussen het oude en het nieuwe rol-toewijspad.** "Gedrag identiek"
  bij OP-258 is gelezen, niet bewezen; het oude pad bestaat niet meer.
- **Het gedrag waarbij een onbekende rol stil wordt overgeslagen** bij het vervangen van een
  rolset. Discutabel (een beheerder krijgt 200 terwijl een gevraagde rol niet is toegekend),
  maar het is bestaand gedrag en veranderen hoort bij een eigen besluit met een eigen rij.
