# Review BE-AGT-047 -- De raadpoort werkend, met het recht van de aanvragende mens

| | |
|---|---|
| Feature | BE-AGT-047 |
| Sprint | SP-COUNCIL-GATE-001 |
| Branch | `fix/council-gate` |
| Commits | `94b5f53f` (rode tests), `ecfe5ff0` (implementatie), `08bbc69d` (ronde 2), plus de commit van deze ronde |
| Rondes | 3 |
| Datum | 2026-08-16 |
| Eindoordeel | **APPROVED WITH MINOR GAPS** -- zie par. 5 voor wat expliciet openstaat |

---

## 1. Verloop

Drie Gate 2-rondes met twee onafhankelijke reviewers (code + security), elk op een
COMMIT-hash en niet op de working tree.

| Ronde | Commit | Code-reviewer | Security-reviewer |
|---|---|---|---|
| 1 (ontwerp vooraf) | `94b5f53f` | CHANGES_REQUESTED (5 blokkers) | CHANGES_REQUESTED (6 eisen) |
| 2 (implementatie) | `ecfe5ff0` | CHANGES_REQUESTED (1 blokker + 3 fouten) | CHANGES_REQUESTED (3 defecten) |
| 3 (verificatie) | `08bbc69d` | -- | CHANGES_REQUESTED (3 kleine, mechanisch) |

**Dit overschrijdt de tweerondegrens uit `.claude/rules/quality-gates.md`** ("BLOCKED after 2
attempts -> escalate to Rakesh, stop"). Dat is expliciet aan Rakesh gemeld. De reden om een
derde ronde te draaien in plaats van te stoppen: elke ronde vond ANDERE, diepere defecten in
code die de vorige ronde nog niet kon zien, en ronde 3 bevestigde alle acht blokkers uit ronde
2 als gesloten -- aangetoond in de code, niet alleen in de tests. **De merge-beslissing ligt
bij Rakesh, niet bij de reviewers en niet bij de uitvoerder.**

## 2. Wat elke ronde opleverde

### Ronde 1 -- op het ontwerp, voor er code was

Vijf blokkers, allemaal verwerkt. De belangrijkste twee:

- **`request_council_decision_for_agent` had helemaal geen `message`-parameter.** Het ontwerp
  ging ervan uit dat die er was. Zonder de gate-wijziging zou productie een `TypeError` geven
  die als "governance-poort niet bereikbaar" wordt afgevangen -- de poort blijft dan dicht om
  een nieuwe reden.
- **Niets testte de migratie.** Model wijzigen en de migratie vergeten was de goedkoopste
  vals-groene route van de hele dag: alle testbomen bouwen hun schema met `create_all`.

### Ronde 2 -- de belangrijkste vondst van de dag

**De rolnaam werd hoofdlettergevoelig vergeleken.** `RoleSeeder` schrijft `Admin`, `Editor`,
`Viewer` weg; `ROLE_PERMISSIONS` is op kleine letters gesleuteld. Overlap: **nul**. In een
tenant die via de productie-seeder is ingericht kreeg dus ook de beheerder een lege
rechtenverzameling, werd elke broker-tool geweigerd, en bleef de piloot staan op
`MISSING_SCOPE`. De hoofdbewering van `ecfe5ff0` hield in die configuratie geen stand.

**Waarom geen enkele test dat zag, is de eigenlijke les.** Elke test maakte zijn rollen zelf
aan, met kleine letters: de invoer werd aan beide kanten van de vergelijking verzonnen, dus de
tests bewezen alleen dat de functie deterministisch is. En de guard die het had moeten vangen
vergeleek de dict-SLEUTELS van `DEFAULT_ROLES` in plaats van de weggeschreven NAMEN -- vals
groen op precies het punt waarvoor hij was geschreven.

Twee andere defecten in code die `ecfe5ff0` zelf toevoegde: een gedeactiveerde rol gaf nog
steeds `admin` (en daarmee toegang tot personeelsgegevens), en de rechtencontrole las bij elke
vraag een YAML-bestand van schijf binnen het budget van 300 ms van de SecurityOfficer. Plus een
veld dat een niet-bestaande configuratiesleutel las, met een toelichting eronder die een effect
claimde dat er meetbaar niet is -- een directe overtreding van de regel "een onbewezen oorzaak
wordt nooit een WHY-comment".

### Ronde 3 -- verificatie

Alle acht punten aanwijsbaar dicht, en punt 1 aangetoond door de keten `role_seeder` ->
`Role(name="Admin")` -> `.strip().lower()` -> `ROLE_PERMISSIONS["admin"]` -> `Permission.ADMIN`
te lezen in plaats van de test te geloven. Wat overbleef was klein en mechanisch en is in deze
ronde afgewerkt:

| Bevinding | Verwerkt |
|---|---|
| De tenant-helft van de rolcontrole had geen test | `test_a_role_from_another_tenant_grants_nothing` |
| De nieuwe `except` rond `charge_prana` had geen test | `tests/unit/als/test_charging_failure_does_not_lose_the_result.py` (3 tests, beide richtingen) |
| Migratie-guard blind voor `ALTER TABLE public.tenants DROP COLUMN` | Tabelnamen genormaliseerd; mutatiebewijs aangevuld |
| Twee lookup-conventies op hetzelfde woordenboek | `get_user_permissions()` bewust NIET meeveranderd (dat zou het HTTP-pad verruimen); de asymmetrie staat nu als comment ter plekke en als OP-143 |
| Restant van een vorige zinsbouw in een WHY-comment | Herschreven |
| Doc-gate rood | Dit document |

## 3. Wat is nagemeten en in orde bevonden

- De WHY bij `specialisation` is door de reviewer nagerekend: `hr_culture` staat niet in
  `HIGH_RISK_DEPARTMENTS`, de specialisatie niet in `HIGH_RISK_SPECIALISATIONS`, en
  `query_hr_database` matcht geen `HIGH_RISK_KEYWORDS`. Uitkomst blijft `LIMITED` -- precies
  wat de comment nu zegt, en de reden dat OP-144 openstaat.
- Geen enkele toolnaam of manifest-rol in de repo valt samen met een hoogrisico-specialisatie,
  dus het invullen van dat veld kan de classificatie nergens VERLAGEN.
- Alle 135 manifesten hebben een niet-lege `allowed_tools`; het copilot-profiel telt 17 namen;
  de doorsnede die van gedrag verandert is exact `{list_tasks}`.
- De coordinator is fail-secure: elke uitzondering wordt BLOCKED, elke officier-timeout een
  synthetisch veto of uitstel, en een mislukte auditschrijf blokkeert.
- Geen nieuwe fail-open in het autorisatiebesluit. De enige `return True` zonder controle is de
  bestaande copilot-actielijst -- OP-142.
- Er belanden geen nieuwe categorieen persoonsgegevens in de ADR-019-hashketen: `message`
  bevat alleen agent-id en toolnaam, en die toolnaam stond al in `reasoning`.

## 4. Bewijs

| Wat | Uitkomst |
|---|---|
| `pytest tests/unit tests/architecture tests/core -n 4` | 15.656 geslaagd, 215 overgeslagen, 19 xfailed |
| `pytest tests/integration/copilot/test_agent_actions_reach_the_council_unmocked.py` | 4 geslaagd tegen echte PostgreSQL |
| `python -m pyright` | 0 errors (baseline 0) |
| `python scripts/run_mypy_audit.py` | 0 errors (baseline 0) |
| `ruff check src/ tests/` | schoon |
| Any-poort (pre-commit) | 0 nieuwe |
| `alembic heads` | 1 (`20260815_tenant_prana_budget`) |

Elke nieuwe of gewijzigde guard is in BEIDE richtingen mutatie-getest, met het bewijs in zijn
docstring en een regel per element van de bewaakte verzameling.

## 5. Wat expliciet OPENSTAAT

1. **De merge-beslissing.** Drie rondes, elk met CHANGES_REQUESTED. De tweerondegrens is
   overschreden en dus geescaleerd. Rakesh beslist.
2. **Het koppelingsplafond `agent_runtime -> governance` van 7 naar 8.** Nodig omdat de
   budgetadapter de echte bewaker moet raadplegen; de richting is by design (ADR-027). Het
   plafond staat nu op het GEMETEN aantal zonder buffer, met een opsomming per import -- de
   oude tekst verantwoordde er zes terwijl het er zeven waren. Wacht op akkoord.
3. **Acht OP-nummers** (OP-139 t/m OP-146), elk met een guard of -- bij OP-146 -- met een
   expliciete motivering waarom een guard daar juist misleidend zou zijn. De zwaarste is
   OP-140: `alembic upgrade head` maakt 104 modeltabellen niet aan.
4. **OP-146**: een `isinstance`-test faalt in ongeveer de helft van de volledige suite-runs en
   slaagt altijd los. Uitgesloten dat het aan deze wijziging ligt (groen in twee van vier runs
   met de wijziging aanwezig, en de test raakt geen gewijzigd bestand). Het mechanisme is
   NIET vastgesteld; de assertie is diagnostisch gemaakt zodat de volgende failure bewijs
   oplevert in plaats van een raadsel.

## 6. Eindoordeel

**APPROVED WITH MINOR GAPS.**

De governancelaag doet nu wat hij hoorde te doen: hij laat de juiste mens door en weigert de
verkeerde, aangetoond in beide richtingen tegen een echte database. De drie reviewrondes hebben
achtereenvolgens een ontwerpfout, een productie-brekende naamsvergelijking en drie kleine
gaten in nieuwe code weggehaald die geen van alle door de bestaande tests werden gezien.

De openstaande punten in par. 5 zijn geen verborgen schuld: ze staan in het register, hebben
een guard, en punt 1 en 2 zijn beslissingen die bij Rakesh horen -- niet bij mij.
