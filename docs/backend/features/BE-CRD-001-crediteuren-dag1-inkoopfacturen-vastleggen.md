# Backend Feature Specification

## Metadata

- **Feature ID:** BE-CRD-001
- **Feature naam:** Crediteuren dag 1: leveranciers en inkoopfacturen vastleggen, per klant afgeschermd, tot "gecontroleerd"
- **Status:** Geimplementeerd (Gate 2: twee reviewers, een ronde, bevindingen verwerkt; zie review-BE-CRD-001)
- **Auteur:** bouwer (tak `iter/crediteuren`)
- **Reviewers:** security-reviewer en code-reviewer (Gate 2, een ronde)
- **Datum:** 2026-10-24
- **Gerelateerde brief:** `docs/agent-briefs/generated/2026-10-24-sprint-dag-crediteuren-dag1-inkoopfacturen-vastleggen.md`; meetlat Keten F (`docs/meetlat.md`, toegevoegd 2026-10-23 in opdracht van Rakesh)
- **Gerelateerde frontend:** FE-PGS-037
- **Gerelateerde modules:** `src/core/models/payable_models.py`, `src/core/repositories/payable_repository.py`, `src/core/api/v1/payables/`, `src/core/api/registries/payables.py`, `src/alembic/versions/20261024_payables_rls.py`, `src/core/services/rbac_service.py`
- **Database:** migratie `20261024_payables_rls` (interlock 1: alleen TOEVOEGEN, werkende `downgrade()`, door de regie bij Rakesh aangekondigd)

---

## Doel en scope

### Doel

Een klant kan inkoopfacturen en hun leveranciers vastleggen, ze zien en een factuur als "gecontroleerd" markeren, zonder dat een andere klant er iets van ziet. Dit is dag 1 van vier voor Keten F ("Jeroen's crediteuren, betalen met rem erop"). Goedkeuren met vier ogen (dag 3), het SEPA-betaalbestand en afboeken op het bankafschrift (dag 4) en het inlezen van een factuur (dag 2) staan er bewust niet.

### Besluit

1. **Datamodel.** `suppliers` (naam, IBAN, e-mail) en `payables` (leverancier, factuurnummer van de leverancier, bedrag in centen, valuta, factuurdatum, vervaldatum, status, wie en wanneer vastgelegd en gecontroleerd). Beide met `tenant_id NOT NULL`, een index en Row Level Security zoals bij debiteuren.
2. **Een factuur kan niet naar de leverancier van een ander bedrijf wijzen.** `payables (tenant_id, supplier_id)` verwijst naar `suppliers (tenant_id, id)`. RLS schermt de rijen af voor de applicatierol; deze sleutel houdt de relatie zelf binnen een tenant, ook voor de eigenaar (de applicatie verbindt nu als eigenaar, OP-151).
3. **Geld is een geheel aantal centen** (`BIGINT`, groter dan nul, hoogstens 1 miljard euro via de API). Nooit float, nooit tekst; het scherm rekent met de cijfers van wat de klant typt.
4. **Geen dubbele factuur, geen dubbele leverancier, hoofdletterongevoelig.** Unieke indexen op `(tenant_id, lower(name))` en `(tenant_id, supplier_id, lower(invoice_number))`; de repository en het schema halen spaties aan de randen weg. Dubbel betalen is het echte risico van crediteuren (Gate 2).
5. **Statusverloop** `ontvangen -> gecontroleerd -> goedgekeurd -> in_betaalbestand -> betaald`, plus `afgewezen`. Alleen toegestane overgangen; een eigen validatiefout met een Nederlandse tekst (`ValidatieFout`, BE-API-046). Dag 1 zet alleen `gecontroleerd`; voor elke latere stap zegt de repository in het Nederlands dat hij nog niet beschikbaar is.
6. **Rechten.** `payables:read` en `payables:write`, rol `crediteuren` met alleen die twee (geen goedkeurrecht, geen `tools:read`). `payables` is een eigen resource zoals `hr` (`EXPLICIT_RESOURCES`): een jokerrecht `*:read` dekt het NIET, alleen een recht op de resource zelf of `*:*` (Gate 2, HIGH).
7. **API** onder `/api/v1/payables`: lijst (met paginering en een statusfilter), een factuur vastleggen, status wijzigen; `/api/v1/payables/suppliers`: lijst en leverancier vastleggen. `tenant_id` komt alleen uit het token.
8. **Audit** na de commit in `best_effort`; geen IBAN en geen bedrag in de auditregel. Het antwoord wordt VOOR de auditregel opgebouwd (zie "Gemeten").

### Gemeten (2026-10-24)

- Er was geen datamodel voor inkoopfacturen; alleen de niet aangesloten catalogusagent `AccountsReceivablePayable`.
- **Een falende auditregel gaf een 500 voor iets dat WEL was vastgelegd** (de code-reviewer beredeneerde het, ik heb het gemeten): `best_effort` draait bij een fout de sessie terug, het geladen object verloopt en het antwoord kon er niet meer uit worden opgebouwd (`MissingGreenlet`). Vier tests rood (leverancier, factuur, lijst, controleren), nu groen met het antwoord voor de audit. **Hetzelfde patroon staat in `api/v1/receivables/router.py`** (debiteuren); niet aangeraakt, wel gemeld.
- **Een jokerrecht gaf toegang:** een rol met alleen `*:read` kreeg een 200 op `GET /api/v1/payables` en de leveranciers (met IBAN). In bestaande omgevingen heeft de rol `user` dat jokerrecht. Gemeten met een eigen test, daarna dichtgezet.
- Een nieuwe databaseverbinding naar `localhost` kost op deze machine 2,1 s (zie BE-CNL-001); voor crediteuren niet relevant, wel voor wie de acceptatie lokaal draait.

### In scope / out of scope

In scope: wat hierboven staat. Out of scope: goedkeuren, vier ogen, betaalbestand, afboeken, inlezen van een factuur (dag 2 tot 4), een agent voor crediteuren, bewerken of verwijderen van een leverancier, een IBAN-wijzigingshistorie.

---

## Technische beschrijving

- `payable_repository.py`: `SupplierRepository` en `PayableRepository`. Elke methode heeft `tenant_id` als parameter en filtert zelf; de invoerobjecten hebben geen tenantveld. Een gelijktijdige dubbele invoer loopt via een savepoint (`begin_nested`), zodat de sessie bruikbaar blijft; alleen een botsing op DE unieke index heet "al vastgelegd", elke andere `IntegrityError` wordt gelogd en doorgegeven. `set_status` leest de rij met een rijslot (`FOR UPDATE OF payables`), zodat twee gelijktijdige wijzigingen niet allebei de oude stand lezen.
- IBAN: spaties eruit, hoofdletters, vorm, controlesom modulo 97 en voor de SEPA-landen de lengte per land. Een land dat niet in de tabel staat houdt alleen de controlesom; het betaalbestand (dag 4) filtert op SEPA.
- Invoer: `extra="forbid"`, spaties aan de randen eraf, en in naam en factuurnummer geen tekens uit de Unicode-categorieen `Cc`, `Cf`, `Zl`, `Zp` (stuurtekens, onzichtbare tekens, bidi-omkering, regel- en alineascheiders): die verdraaien tekst in een scherm, brief of betaalbestand.
- Migratie: twee tabellen, de samengestelde sleutel (`RESTRICT`), de CHECKs op status, bedrag, valuta en vervaldatum, de hoofdletterongevoelige unieke indexen, en RLS in het lus-idioom van `20260915_rls_resterende_tabellen.py` (geen `FORCE`). `downgrade()` laat precies deze twee tabellen vallen. De migratie is NA de eerste commit nog aangepast (de unieke sleutels, Gate 2); ze is op geen enkele omgeving buiten wegwerp- en testdatabases uitgevoerd.
- Router: `router.py` 160 regels, `suppliers_router.py` 85 regels, registry 11 regels; alles via `dependencies.py` en de facade `admin/dependencies.py`, zodat het fan-out-budget van `core_api` niet stijgt.

## Acceptatiecriteria

- Een inkoopfactuur vastleggen en terugvinden in de lijst van de eigen klant; klant B ziet hem niet (repository, API en RLS onder de applicatierol `sanskritisetu_app`, beide richtingen).
- Een tweede factuur van dezelfde leverancier met hetzelfde nummer, ook in andere hoofdletters of met spaties, wordt geweigerd met "Deze factuur van deze leverancier is al vastgelegd."
- Een niet toegestane statusovergang geeft een Nederlandse melding; goedkeuren, het betaalbestand en afboeken zijn nog niet te zetten.
- De rol `crediteuren` mag lezen en schrijven maar niets goedkeuren; `debiteuren`, `goedkeurder`, `goedkeurder_hr` en een rol met alleen `*:read` komen er niet in.
- Een falende auditregel geeft de klant geen fout.
- `alembic heads` geeft een kop; upgrade, downgrade en upgrade slagen op een wegwerpdatabase.

Tests: `tests/unit/repositories/test_payable_repository.py`, `tests/integration/test_crediteuren_dag1_vastleggen.py`, `tests/integration/api/test_payables_rechten_per_rol.py`, `tests/integration/security/test_payables_is_confined_to_its_tenant.py`, `tests/migrations/test_payables_migratie.py`, plus de aangepaste pins `test_agentic_alembic_chain_complete.py`, `test_role_permissions_cover_every_seeded_role.py` en `test_het_rolprimitief_maakt_geen_rollen_aan.py`. Mutatiebewijs: zie review-BE-CRD-001.

## Trainingssamenvatting

### Een inkoopfactuur vastleggen

- Actor: crediteurenadministrateur (rol `crediteuren`) of beheerder
- Voorwaarde: de leverancier staat in de lijst
- Actie: kiest de leverancier en vult factuurnummer, bedrag, factuurdatum en vervaldatum in
- Systeemreactie: de factuur staat op "Ontvangen" in de lijst; er komt een auditregel
- Succes: "Inkoopfactuur <nummer> vastgelegd."
- Fout: "Deze factuur van deze leverancier is al vastgelegd." bij een dubbele; "Het bedrag moet groter zijn dan nul." bij een bedrag van nul; "De vervaldatum mag niet voor de factuurdatum liggen."
- Uitzonderingen: een leverancier van een ander bedrijf bestaat hier niet ("Deze leverancier bestaat niet.")

### Een factuur als gecontroleerd markeren

- Actor: crediteurenadministrateur
- Voorwaarde: de factuur staat op "Ontvangen"
- Actie: kiest "Gecontroleerd" bij de factuur
- Systeemreactie: de status wordt "Gecontroleerd"; wie en wanneer worden vastgelegd
- Succes: "Factuur <nummer> staat op gecontroleerd."
- Fout: een tweede keer controleren geeft "De status kan niet van 'gecontroleerd' naar 'gecontroleerd' worden gezet."
- Uitzonderingen: goedkeuren en betalen kunnen nog niet; de melding zegt dat het een latere stap is

## Bewust laten liggen (ontwerpinput voor dag 3 en 4)

| Punt                                                                                                                    | Reden                                                                                                                                             |
| ----------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| Wie goedkeurde is na een AVG-wissing niet meer aantoonbaar (`SET NULL` op `created_by_user_id` en `checked_by_user_id`) | dag 1 keurt niets goed; voor dag 3 een eigen bewaarplek voor de goedkeurder en een controle dat goedkeurder, invoerder en controleur verschillen  |
| Een IBAN-wijziging laat geen spoor na (er is geen wijzigroute; `supplier_created` legt het IBAN bewust niet vast)       | voor dag 3 en 4: bij goedkeuren een vingerafdruk van bedrag, IBAN en leverancier op de factuur bewaren, en een IBAN-wijziging gehasht registreren |
| De auditregel staat na de commit (best_effort)                                                                          | zo staat het in backend-patterns par. 3; voor geldmutaties van dag 3 en 4 liever in dezelfde transactie of met een alarm                          |
| Factuurnummers of namen die met `=`, `+`, `-` of `@` beginnen                                                           | schoonmaken of weigeren hoort bij het schrijven van het betaalbestand (dag 4)                                                                     |
| Valuta: elke drie hoofdletters is toegestaan; het scherm kent alleen EUR                                                | dag 4 filtert op EUR en SEPA voor het betaalbestand                                                                                               |
| Een onbekend statusfilter geeft 409 met de Nederlandse tekst                                                            | consistent met debiteuren; geen risico, een 422 is netter                                                                                         |
| RLS beschermt feitelijk niets zolang de applicatie als eigenaar verbindt (OP-151)                                       | niet nieuw; de isolatie rust op de repositoryfilters en de samengestelde sleutel, beide getest                                                    |
| `api/v1/receivables/router.py` heeft het audit-faalpad van H1 ook (500 na een geslaagde commit)                         | niet van deze brief; gemeld aan de regie                                                                                                          |

## Niet gemeten

- Gelijktijdigheid met twee echte verzoeken tegelijk (alleen de SQL met `FOR UPDATE` is bewezen).
- Staging en productie.
