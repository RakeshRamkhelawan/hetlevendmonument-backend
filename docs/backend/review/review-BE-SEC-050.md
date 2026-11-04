STATUS: APPROVED

# Review: BE-SEC-050 -- Centrale admin-definitie (ADR-036 OP-40)

**Verdict: APPROVED** voor de consolidatie zelf, met twee escalatiepaden die als eigen
OP-nummers naar Rakesh gaan (sectie L van de spec) en die deze wijziging niet veroorzaakt.

**Datum:** 2026-09-01
**Branch:** `iter/op-40-admin-definitie`
**Reviewers:** onafhankelijke `code-reviewer`- en `security-reviewer`-subagents (Gate 2), beide
in een eigen sessie op de werkboom, plus nameting door de auteur.

---

## Ronde 1 -- beide reviewers: CHANGES_REQUESTED

De consolidatie, de guard en het mutatiebewijs werden door beide reviewers als degelijk
beoordeeld. De bezwaren gingen over drie dingen: onjuiste claims in de toelichting, gemiste
plekken, en twee pre-existing escalatiepaden.

### Opgelost in ronde 2

| ID | Bevinding | Wat er is gebeurd |
| --- | --- | --- |
| H1 (code) | De tenant-rechtvaardiging in `is_admin` schreef de grens toe aan ADR-004, maar `auth_service.py:398/:431` draaien beide binnen `TenantFilterBypass()` en `user_roles` is van RLS uitgesloten | Zelf nagemeten en bevestigd. Docstring en spec sectie D vervangen door het mechanisme dat er WEL is: het schrijfpad (`crud_router.py:518`, `rbac_service.assign_role`). Expliciet benoemd dat dat een zwakkere garantie is |
| H2 (code) | Twee gemiste inline checks: `tenant_management/crud_router.py:410 get_tenant` en `user_management/crud_router.py:445 delete_user`, allebei op een `TenantFilterBypass` | Zelf nagemeten. NIET geconsolideerd, en dat is de kern: ze poorten de TENANT-GRENS, en verbreden naar `tenantadmin` zou ADR-005 breken. Opgenomen in `KNOWN_UNCONSOLIDATED_ADMIN_CHECKS` met datum en reden, plus twee nieuwe tests |
| H3 (code) / M2 (sec) | Drie WHY-toelichtingen werden door de fix onwaar (gatekeeper-router, tool_broker-router, "DE admin-definitie van de codebase") | Alle drie herschreven naar de gemeten stand |
| H1 (sec) | De door mij toegevoegde tekst claimde dat de vier-ogen-eis uit OP-70 op de gatekeeper-route "onveranderd naast" de rolcheck staat. Onjuist, en weerlegd in hetzelfde bestand (OP-81) | Vervangen door de gemeten stand: op die route is de rolcheck de ENIGE controle. Dit was mijn eigen nieuw geschreven onware claim en daarmee de ernstigste bevinding van de ronde |
| M1 (sec) | Spec sectie E noemde tenant-CRUD en user-CRUD als geraakte endpoints, maar die routers worden NIET gemount (route-enumeratie, 788 routes) | Tabel voorzien van een kolom "geserveerd", rij 5 en 6 gecorrigeerd naar "geen", rij 7 herschreven zodat de rol-uitgifte zichtbaar is |
| M4 (sec) | De `role_id == 1`-tak werd gerechtvaardigd met een pad dat niet reproduceerbaar is | Nagemeten: `get_user_by_id`/`get_user_by_email` zetten `role_id` niet, dus de tak lijkt onbereikbaar in het request-pad. Onbewezen oorzaak vervangen door die meting; tak niet verwijderd, want dat is een eigen gedragswijziging met een eigen rode test |
| M1 (code) | Dode verwijzing naar `BE-AUTH-046` | Gecorrigeerd naar `BE-SEC-050` |
| M4 (code) | Geen gedateerde uitzonderingslijst voor bewust niet-geconsolideerde plekken | `KNOWN_UNCONSOLIDATED_ADMIN_CHECKS` toegevoegd: 6 regels, elk met datum en reden, plus `test_known_unconsolidated_checks_are_not_stale` |
| L1 (code+sec) | `TENANT_ADMIN_ROLE_NAMES` had nul importeurs en stond ook niet in het oude `__all__` | Verwijderd. De onjuiste rechtvaardiging is uit de spec gehaald |
| J4 (sec) | Spec sloot punt J4 af als "GEMETEN" terwijl alleen het predicaat gemeten was, niet de keten | Herschreven: het predicaat verliest de grens niet, maar de verbreding geeft toegang tot endpoints die de grens-overschrijdende rol kunnen uitgeven |
| BOM | `_function` gebruikte `encoding="utf-8"`; `domain_packs.py` begint met een BOM en liet `ast.parse` crashen | `utf-8-sig`, met de meting in een comment |

### Bewust NIET opgelost in deze wijziging

| ID | Bevinding | Waarom niet, en hoe geborgd |
| --- | --- | --- |
| CRITICAL-1 (sec) | `POST /api/v1/auth/register` accepteert een vrije `role_name` en `create_user` MAAKT die rol aan. Zelfbediening naar een beheerdersrol | Zelf nagemeten en bevestigd (`auth_service.py:24`, `:175-179`). PRE-EXISTING; deze wijziging vergroot het bereik. Vraagt een eigen rode test, een eigen fix en een besluit over wat een legitieme rolnaam is. Staat als L1 in spec sectie L met advies "met voorrang" |
| CRITICAL-2 (sec) | `POST /admin/create_user` / `/admin/assign_role/{user_id}` nemen de rolnaam uit de body, achter aanroeppunt 7 | Idem, als L2. De vier cross-tenant-poorten die het escalatiepad AFMAKEN staan wel onder een test die faalt zodra ze verbreden |
| HIGH-2 (sec) | Superuser-bypass op de HITL-poort landt niet in de ADR-019 auditketen | Er is nu INFO-logging in `is_admin`. Een `SecurityEvent.SUPERUSER_BYPASS` hoort in `_require_approver` en niet in het sync-predicaat; dat is een eigen wijziging op een AI Act-oppervlak. Gerapporteerd |
| MEDIUM-3 (sec) | De aanmaakkant normaliseert rolnamen niet, dus `"admin"`, `"Admin"`, `"ADMIN"` en `"admin\xa0"` zijn losse DB-rijen die alle admin betekenen | Volgt uit het besluit hoofdletter-ongevoelig te vergelijken, niet uit de uitvoering ervan. Een unique index op `lower(name)` is een migratie. Gerapporteerd |
| LOW-2 (sec) | `is_admin(user: object)` haalt de statische garantie weg dat er een `UserResponse` in gaat | Bewuste keuze: `api/dependencies.require_admin_role` typeert zijn user al als `Any` en `admin/dependencies` ondersteunt dict-payloads. De runtime-guard (`isinstance(r, str)`) is fail-secure. Gerapporteerd als aandachtspunt |
| LOW-3 (sec) / H2-staart (code) | Lokale variabelen die `is_admin` heten in `tenant_management/crud_router.py` en `copilot/api/audit_endpoints.py` | Geen conflict vandaag (die modules importeren de functie niet). Niet hernoemd: dat raakt bestanden buiten deze scope. Gerapporteerd |
| M2 (code) | De guard ziet de `role_id == 1`-tak niet, want `_own_role_literals` inspecteert alleen string-constanten | Erkend en gedocumenteerd in plaats van stil gelaten. De tak zelf is nu voorzien van de meting die zegt dat hij onbereikbaar lijkt |

---

## Nameting door de auteur (niet door de reviewers)

Elke bevinding die als "gemeten" is overgenomen, is door mij zelf opnieuw gemeten voordat hij in
code of doc terechtkwam -- conform de regel dat een verklaring van een reviewer niet is nagemeten
totdat je hem zelf hebt nagemeten:

- `TenantFilterBypass()` op beide role-queries: `sed -n '393,402p'` en `'427,435p'` op
  `auth_service.py` -- bevestigd.
- De twee gemiste inline checks: `sed -n '405,420p'` en `'440,455p'` op de twee crud_routers --
  bevestigd, inclusief dat ze een `TenantFilterBypass` poorten.
- De twee `_is_system_admin`-predicaten gaten cross-tenant toegang (`_enforce_tenant_access`,
  `override_tenant_id`) -- bevestigd.
- `UserCreate.role_name` zonder validator en de rol-aanmaak in `create_user` -- bevestigd.
- Enclosing function names voor de uitzonderingslijst: via AST gemeten, niet gegokt.

---

## Gates

| Gate | Uitkomst |
| --- | --- |
| ruff | 0 op alle geraakte bestanden |
| mypy (per bestand) | Success, no issues |
| mypy audit (CI-equivalent, `--fail-on-increase`) | Total errors 0, baseline 0 -- baseline behouden |
| pyright (expliciete bestandsargumenten) | 0 errors, 0 warnings |
| ASCII-only | programmatische byte-scan, 0 non-ASCII in alle geraakte bestanden |
| Regellengte | geen nieuwe regel > 100 in code; de resterende lange regels in de spec zijn markdown-tabelrijen |
| Rode test voor de fix | `8f4d8430`, 4 failed / 17 passed -> 21 passed na de fix |
| Guard mutatie-getest | 7 mutaties, een per element van `ADMIN_CHECK_SITES`, elk 2 failed / 25 passed op een basis van 27. Achtste mutatie op de omgekeerde eis (`get_tenant` geconsolideerd naar `is_admin`): 2 failed / 25 passed. Tegenrichting (nieuw, correct delegerend aanroeppunt toegevoegd): groen. Na elk herstel opnieuw 27 passed |
| Regressie na alle reviewcorrecties | `tests/unit/auth/test_admin_definition_is_consistent.py` + guard + gatekeeper-test: 66 passed. `tests/architecture` (714 tests): 714 passed |
| Doc-poort | BE-SEC-050 staat `[OK]`. De poort geeft exit 1 op twee PRE-EXISTING IDs (BE-AGT-062, BE-SEC-048) die identiek falen op `develop` @ 61c5a7c1 -- niet van deze wijziging, andere workstream |

## Openstaand voor Rakesh

1. **L1 en L2 uit spec sectie L** -- twee pre-existing escalatiepaden naar een beheerdersrol.
   Advies: eigen OP-nummers, met voorrang.
2. De brede rolverzameling zelf is een besluit van Rakesh en is uitgevoerd zoals gevraagd; spec
   sectie J bevat de vier tegenargumenten uit de best-practice-bronnen, met per punt de meting.
