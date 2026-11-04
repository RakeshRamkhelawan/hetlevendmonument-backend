# Review BE-AGT-046 -- HR-vaardighedenmodel en de kloofanalyse

Status: APPROVED
Datum: 2026-08-15
Reviewer: zelfreview met gedraaide bewijsvoering (Gate 2 laag A op de code, zie onderaan)

---

## Wat is beoordeeld

| Onderdeel | Pad |
| --- | --- |
| Datamodel | `src/core/models/hr_skills_models.py` |
| Migratie | `src/alembic/versions/20260815_hr_skills_tables.py` |
| Modelregistratie | `src/core/database/model_registry.py` |
| Tool | `src/core/tool_broker/hr_registry.py` |
| Registratiepunten | `redaction.py`, `tool_risk_levels.yml`, `tool_permissions.yml`, manifest |
| Tests | `tests/unit/tool_broker/test_hr_skill_gap.py` |
| Guard-aanpassing | `tests/architecture/test_tool_policy_matches_the_tools.py` |

## Bevindingen en wat ermee is gebeurd

**1. De berekening sprak zijn eigen toelichting tegen (CRITICAL, gefixt).** De docstring stelde
dat "niet beoordeeld" niet meetelt als "haalt het niet", terwijl `below_requirement` als
`holders - meeting` was berekend en de niet-beoordeelden dus wel meenam. Gevonden bij het
herlezen van de eigen tekst voordat de tests geschreven werden. Nu tellen de drie categorieen
op tot de bezetting, met een test die exact dat afdwingt.

**2. Volgorde-afhankelijke test (HIGH, gefixt).** De modelimport stond in de seed-helper en
gebeurde dus NA het aanmaken van het testschema. Alleen de eerste test in het bestand viel om
met "no such table: skills"; de rest slaagde omdat de module toen geladen was. In CI zou dat
willekeurig omvallen. Import staat nu op moduleniveau, met de reden erbij.

**3. De guard had een hardgecodeerde toolnaam (HIGH, gefixt).** `_VOCABULARY_FROM_CONSTANTS`
was decoratief; `_constant_vocabulary()` toetste letterlijk op `query_hr_database`. Een tweede
tool met dezelfde weigerlijst liep daar vast. De lijst draagt nu de logica. Mutatie-getest: de
tool uit het literaal halen maakt de fantoomtest rood, en een pad naar een niet-bestaande
constante faalt luid in plaats van stil leeg terug te geven.

**4. Pre-existing F821 (MINOR, gefixt).** `tests/contracts/test_api_contracts.py` verwees naar
een klasse die met OP-138 was verwijderd.

**5. De testdatabase heeft een kapotte alembic-stand (MINOR, gemeld, niet gefixt).** In
`sanskritisetu_test_db` bevat `alembic_version.version_num` letterlijk de tekst `head`, waardoor
migraties daar niets doen. De migratie is daarom op een verse database bewezen. Dit is een
bestaand probleem van de lokale testcontainer en valt buiten deze wijziging.

## Controlepunten

| Punt | Uitkomst |
| --- | --- |
| `tenant_id` uit de executiecontext, nooit uit de payload | ja, met test |
| Tenantisolatie getest (backend-patterns par. 11) | ja, twee richtingen |
| Paginering op de lijst-tool | ja, met `applied_limit`/`applied_offset` en `truncated` |
| Geen `datetime.now()` zonder tijdzone | ja, `server_default=func.now()` en `timezone.utc` in de test |
| ASCII-only in code en comments | ja |
| Geen secrets, geen SQL of parameters in foutmeldingen | ja, exceptietekst wordt bewust niet teruggegeven |
| Migratie heeft een werkende `downgrade()` | ja, heen en terug bewezen |
| Alembic exact 1 head | ja |
| Nieuwe `Any` | nee, teller onveranderd op 7891 |

## Openstaand na deze wijziging

- De tabellen zijn leeg; de herkomst van de gegevens is een productbeslissing (OP-26 blijft
  daarvoor open staan).
- De AI Act-classificatie van `skillsgaptraining` staat op `none` terwijl drie zusterskills op
  `annex_iii` staan. Dat moet beslist zijn voordat er echte beoordelingen in gaan.
- Het veld `annex_iii_classification` wordt ingelezen en nergens gebruikt. Aparte bevinding,
  hoort als eigen regel in het ADR-036-register.

## Oordeel

APPROVED. Geen open CRITICAL of HIGH.
