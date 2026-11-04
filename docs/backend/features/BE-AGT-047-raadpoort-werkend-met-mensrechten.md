# BE-AGT-047 -- De raadpoort werkend, met het recht van de aanvragende mens

| | |
|---|---|
| ID | BE-AGT-047 |
| Sprint | SP-COUNCIL-GATE-001 |
| ADR | ADR-036 (D2, D3, D7, D10), ADR-015, ADR-017, ADR-027 |
| Branch | `fix/council-gate` |
| Commits | `94b5f53f` (rode tests), `ecfe5ff0` (implementatie), `08bbc69d` (ronde 2), plus de commit van ronde 3 |
| Datum | 2026-08-16 |

---

## 1. Het probleem in een zin

De governancelaag die moest voorkomen dat een AI-agent iets ongewenst doet, weigerde
**alles** -- geen enkele skill heeft ooit een tool uitgevoerd, en op het copilot-pad werd elk
verzoek uitgesteld.

## 2. Wat er precies mis was

Gemeten op 2026-08-15 tegen een echte PostgreSQL, met de productie-ingang
`request_council_decision_for_agent` en de payload die `specialist_base._council_rejection`
daadwerkelijk meestuurt. Vier officieren blokkeerden tegelijk:

| Officier | Oordeel | Reden |
|---|---|---|
| ComplianceOfficer | `APPROVE_WITH_MODIFICATION` | `MISSING_AI_DISCLOSURE` |
| SecurityOfficer | `VETO` | `MISSING_SCOPE` |
| ResourceOfficer | `DEFER` | `PRANA_BUDGET_EMPTY` |
| SanityOfficer | `VETO` | `HALLUCINATION_DETECTED` / `empty_suggestion` |

De coordinator maakt van elke MODIFY een `MODIFIED` en de agent-poort laat uitsluitend
`APPROVED` door -- terecht, want hij kan een gevraagde parameterwijziging niet toepassen.

De onderliggende oorzaken:

1. **Het budgetmodel bestond niet.** `PranaGuard` leest `tenants.prana_budget` en
   `prana_spent` sinds maart 2026. Die kolommen stonden in geen enkel model, geen migratie en
   geen database: de migratie die ze aanmaakte (`archive/698adff2b1af`) is uit de keten
   gehaald en `a10bd0ad9807` liet ze door een autogenerate vallen. Elke aanroep gaf
   `AttributeError`; `_run_within_budget()` vertaalde dat naar een mislukte uitvoering.
2. **De budgetadapter keek in het verkeerde woordenboek.** `_PranaAdapter.has_budget()` zocht
   de ACTIENAAM op in `ContractManager._prana_ledger`, dat blijkens `a2a_contracts.py:223` op
   `agent_id` is gesleuteld en alleen door onderlinge afrekening tussen agents wordt gevuld.
   Een actienaam kan daar per definitie niet in staan, en het was leeg.
3. **Het voorstel was onvolledig.** Er ging geen `ai_disclosure` mee, en geen `message` --
   die parameter bestond niet eens op `request_council_decision_for_agent`.
4. **De rechtencontrole kende alleen chat-acties.** `user_has_scope_for()` toetste tegen
   `_COUNCIL_ALLOWED_ACTION_TYPES` en negeerde `user_id`, wat blijkens de eigen docstring
   ("unused for MVP") en `docs/backend/review/review-BE-GOV-001.md` (MINOR-1) bekend was.

## 3. De keuze die het meeste uitmaakt

Oorzaak 4 had op twee manieren opgelost kunnen worden.

**Wat we NIET hebben gedaan:** de toolnamen aan `_COUNCIL_ALLOWED_ACTION_TYPES` toevoegen. Dat
is een regel werk en maakt de poort open -- maar dan mag iedere gebruiker via een agent iedere
tool draaien, inclusief een leesactie op personeelsgegevens. De agent wordt daarmee een omweg
om de rechten van de aanvrager heen.

**Wat we WEL hebben gedaan:** de actie erft het recht van de mens die haar aanvroeg. Per tool
staat in `src/core/config/tool_risk_levels.yml` welk recht vereist is, naast het risiconiveau
dat daar al stond -- zodat een nieuwe tool zijn drempel op dezelfde plek meekrijgt als zijn
risico.

Twee eigenschappen die daarbij horen:

- **Zonder tenant geen antwoord.** `user_has_scope_for(user_id, action_type, *, tenant_id)`
  heeft geen terugval op de tenant-ContextVar. Die is ambient en hoort in een Dramatiq-worker
  of een geneste aanroep niet gegarandeerd bij dit voorstel.
- **Een tool zonder regel wordt voor iedereen geweigerd**, ook voor een beheerder. Een
  terugval op "het strengste bestaande recht" zou betekenen dat een nieuwe tool zichzelf opent
  zolang niemand eraan denkt hem te classificeren.

## 4. Wat er is gebouwd

| Onderdeel | Bestand |
|---|---|
| Budgetkolommen op `tenants` | `src/core/models/rbac_models.py` |
| Migratie (BigInteger, defaults uit de gearchiveerde migratie) | `src/alembic/versions/20260815_tenant_prana_budget.py` |
| Afrekening telt op in de database, rowcount-controle | `src/core/governance/prana_guard.py` |
| Budgetadapter raadpleegt de echte bewaker, fail-closed | `src/core/copilot/council/factory.py` |
| `message` als parameter en op het `Proposal` | `src/core/copilot/council/background_gate.py` |
| Bekendmaking, afdeling en bericht op het voorstel | `src/core/als/agents/specialist_base.py` |
| Vereist recht per tool | `src/core/config/tool_risk_levels.yml` |
| `required_permission()` (geen prefix, geen default) | `src/core/tool_broker/risk_classifier.py` |
| Rechtencontrole met tenant en rol-unie | `src/core/auth/rbac.py` |
| Tenant meegeven op beide officierspaden | `src/core/copilot/council/members/security_officer.py` |
| `user_id` in de cachesleutel | `src/core/copilot/council/cache.py` |

## 5. Grenzen die uitdrukkelijk blijven staan

- **Modeltekst gaat niet mee.** `action_params` draagt alleen de toolnaam en de SLEUTELNAMEN
  (BE-AGT-043). Het `message`-veld bevat uitsluitend systeemtekst: agent-id en toolnaam, geen
  argumentnamen. Reden: die namen komen uit `json.loads()` van modeluitvoer, `message` gaat
  ONGEREDIGEERD de ADR-019-hashketen in, en een sleutel die `always` heet of op `.py` eindigt
  zou `HallucinationGuard` laten weigeren -- dan kiest het model zijn eigen oordeel.
- **De bekendmaking wordt door het systeem gezet.** Een payload die zelf `ai_disclosure`
  meebrengt, overschrijft die niet. Anders zet een prompt-injectie met
  `{"ai_disclosure": true}` de ComplianceOfficer stil.
- **Alleen `APPROVED` laat de actie door.** `MODIFIED` blijft een weigering: de poort kan geen
  parameters teruggeven, dus doorlaten zou de ONGEWIJZIGDE actie uitvoeren en precies de
  inperking negeren waar een officier om vroeg.

## 5a. Wat de tweede reviewronde vond -- en waarom dat de belangrijkste vondst van de dag is

Beide reviewers gaven ronde 1 CHANGES_REQUESTED; na verwerking gaven ze ronde 2 opnieuw
CHANGES_REQUESTED, met een defect dat in ronde 1 nog niet kon bestaan.

**De blokker: de rolnaam werd hoofdlettergevoelig vergeleken.** `RoleSeeder` schrijft
`role_def.name` weg -- `Admin`, `Editor`, `Viewer` -- terwijl `ROLE_PERMISSIONS` op kleine
letters is gesleuteld. Overlap: **nul**. In een tenant die via de productie-seeder is ingericht
kreeg dus ook de beheerder een lege rechtenverzameling, werd elke broker-tool geweigerd, en
bleef de piloot staan op `MISSING_SCOPE`. De hoofdbewering van deze wijziging hield in die
configuratie geen stand.

Waarom geen enkele test dat zag: **elke test maakte zijn rollen zelf aan, met kleine letters.**
De invoer werd aan beide kanten van de vergelijking verzonnen, dus de tests bewezen alleen dat
de functie deterministisch is. En de guard die het had moeten vangen vergeleek de
dict-SLEUTELS van `DEFAULT_ROLES` in plaats van de weggeschreven NAMEN -- vals groen op precies
het punt waarvoor hij was geschreven.

Opgelost met `.strip().lower()` (de bestaande conventie in `auth_service.py:511` en
`dependencies.py:501`), een guard die de namen vergelijkt, en
`test_the_real_seeder_produces_usable_roles`: een test die over de **echte producent** loopt in
plaats van over zelfgemaakte invoer.

Verder uit ronde 2 verwerkt:

| Bevinding | Wat er mee is gedaan |
|---|---|
| `specialisation` las `config["role"]`, een sleutel die het manifest niet levert -- en de toelichting eronder claimde een effect dat er meetbaar niet is | Leest nu `name`; de comment zegt wat gemeten is (de classificatie verandert vandaag NIET, dat is OP-144). Test erbij |
| Een gedeactiveerde rol gaf nog steeds `admin`, en daarmee toegang tot personeelsgegevens | `Role.is_active` en `Role.tenant_id` worden nu per rol getoetst; test erbij, mutatie bewezen |
| `ToolRiskClassifier()` werd per autorisatievraag opgebouwd: blokkerende schijf-I/O binnen het budget van 300 ms van de officier | `@lru_cache`, zelfde patroon als `_get_rbac_service()` |
| `charge_prana` gooide na AL geleverd werk | Gevangen en gelogd met stacktrace; het resultaat gaat niet verloren |
| De migratie-guard bleef groen als een kolom later weer wordt gedropt | Leest nu de EINDtoestand en draait in een subproces met returncode-controle. Dat loste meteen drie errors op die alleen in de volledige suite optraden |
| `list_tasks` verandert wel degelijk van gedrag op het copilot-pad | Behouden (het was kapot, nu werkt het), gedocumenteerd, en de guard heeft er een tweede richting bij die elke volgende zo'n wijziging blokkeert |
| Twee OP-verwijzingen in de broncode wezen naar het verkeerde nummer | Gecorrigeerd naar OP-143 |
| Drie testdocstrings beweerden meer dan ze aantonen | Herschreven naar wat ze werkelijk bewijzen |

## 6. Wat NIET is opgelost (met borging)

Zeven regels toegevoegd aan het ADR-036-register, elk met een guard:

| OP | Wat | Borging |
|---|---|---|
| OP-139 | Het budget kan nergens worden bijgevuld of gereset; na ~1.000 uitvoeringen staat een tenant stil | `test_prana_budget_has_no_refill_path_yet.py` |
| OP-140 | De migratieketen mist 104 modeltabellen, 62 kolommen; `alembic check` kan daardoor geen CI-poort worden | `test_named_columns_exist_in_the_migration_chain.py` (kolommen, niet tabellen) |
| OP-141 | `check_budget` + `charge_prana` zijn een check-then-act; overschrijding begrensd tot een enkele actie | `test_prana_guard_reads_the_tenant_budget.py` |
| OP-142 | `create_task`/`update_task`/`delete_task` zijn tegelijk chat-actie en tool; de chat-lijst wint | `test_council_action_names_do_not_shadow_tool_permissions.py` |
| OP-143 | Twee rolsystemen die elkaar bijna niet raken; `role_permissions`-tabel wordt nooit gelezen | `test_role_permissions_cover_every_seeded_role.py` |
| OP-144 | Twaalf agents lezen personeelsgegevens en verklaren `annex_iii_classification: none` | `test_hr_agents_declare_their_annex_iii_classification.py` |
| OP-145 | De oordeel-cache was gebruiker-blind (GESLOTEN in deze commit) | `test_the_verdict_cache_separates_users.py` |

**Beslissing die openstaat voor Rakesh:** het koppelingsplafond `agent_runtime -> governance`
gaat van 7 naar 8, omdat de budgetadapter de echte bewaker moet kunnen raadplegen. De richting
copilot -> governance is by design (ADR-027; import-linter Contract 5 verbiedt alleen de
omgekeerde richting). Het plafond staat nu op het GEMETEN aantal zonder buffer, met een
opsomming per import -- de oude tekst verantwoordde er zes terwijl het er zeven waren.

## 7. Verificatie

| Wat | Uitkomst |
|---|---|
| `pytest tests/unit tests/architecture tests/core -n 4` | 15.656 geslaagd, 215 overgeslagen, 19 xfailed |
| `pytest tests/integration/copilot/test_agent_actions_reach_the_council_unmocked.py` | 4 geslaagd tegen echte PostgreSQL |
| `python -m pyright` | 0 errors (baseline 0) |
| `python scripts/run_mypy_audit.py` | 0 errors (baseline 0) |
| `ruff check` | schoon |
| Any-poort | 0 nieuwe |
| `alembic heads` | 1 (`20260815_tenant_prana_budget`) |

Na de fix, gemeten tegen echte PostgreSQL: alle zeven officieren keuren goed voor een
gebruiker MET het vereiste recht; de SecurityOfficer weigert met `MISSING_SCOPE` voor een
gebruiker ZONDER. Beide richtingen staan in de integratietest.

Elke nieuwe of gewijzigde guard is in BEIDE richtingen mutatie-getest; het bewijs staat per
guard in zijn docstring, met een regel per element van de bewaakte verzameling.

## Trainingssamenvatting

- Actor: HR-medewerker met de rol `admin`
- Voorwaarde: de agent `skillsgaptraining` is actief, de tenant heeft prana-budget over, en de
  medewerker is als initiator aan de uitvoering gekoppeld
- Actie: de medewerker vraagt een vaardighedenkloof-analyse aan; de agent wil daarvoor de tool
  `query_hr_database` uitvoeren
- Systeemreactie: de Council beoordeelt het voorstel met zeven officieren. De bekendmaking, de
  afdeling en het bericht zijn door het systeem toegevoegd; de rechtencontrole ziet dat de
  aanvrager `admin` heeft en dat de tool dat recht vereist. Uitkomst `APPROVED`, de tool draait
  en het verbruik wordt afgeboekt op het tenantbudget
- Succes: de analyse verschijnt, en de beslissing staat met alle zeven oordelen in de
  auditketen
- Fout: heeft de aanvrager het recht niet, dan geeft de SecurityOfficer `MISSING_SCOPE` en
  wordt de actie geweigerd met een uitleg die de betrokkene kan lezen (AVG art. 13-15)
- Uitzonderingen: staat de tool op de harde denylist van de agent, dan wordt de Council niet
  eens geraadpleegd. Is er geen initiator bekend, dan wordt de actie geweigerd (AI Act art. 14).
  Is het budget op, dan stelt de ResourceOfficer uit -- en zolang OP-139 openstaat is er geen
  ingebouwde manier om dat budget bij te vullen
