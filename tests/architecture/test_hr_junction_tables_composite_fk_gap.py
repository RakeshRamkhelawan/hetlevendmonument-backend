"""HR-koppeltabellen missen composite foreign keys (ADR-005 par. 5, toegevoegd 2026-08-21).

ADR-005 par. 5 (`docs/adr/005-db-level-hardening-tenantid-notnull-and-rls-roadmap.md`) eist dat
elke koppeltabel een samengestelde foreign key `(tenant_id, x_id) -> x(tenant_id, id)` draagt,
zodat de database zelf een cross-tenant koppeling onmogelijk maakt (niet alleen de
ORM-laag/RLS). `docs/audits/MULTI_TENANT_INTEGRITY_AND_RLS_AUDIT_2026-08-21.md` kwantificeert
dit repo-breed: 70 tabellen met alleen enkelvoudige FKs.

**Deze guard is bewust NIET repo-breed.** Dat is de bredere remediatie (de audit hierboven,
een eigen, latere Hardening Sprint) -- niet iets om half te doen middenin een 4-daagse
feature-sprint. Deze guard bewaakt alleen de koppeltabellen in `hr_skills_models.py` en
`hr_training_models.py`, waar dit gat vandaag daadwerkelijk zit en waarvan Rakesh's beslissing
(2026-08-22, Fase 3) is: bewust NIET als eerste in isolatie fixen, wel registreren zodat het
niet stilzwijgend kan uitbreiden.

**Twee assertiegroepen, precies zoals het patroon dat faalde als er maar EEN was
(`test_agent_actions_pass_council.py`, ADR-036 D5):**
1. `test_a_known_table_still_lacks_the_composite_fk` -- staleness-check: als iemand een van
   de drie tabellen alsnog een composite FK geeft, moet DEZE test ROOD worden (niet stilletjes
   groen blijven met een verouderde lijst).
2. `test_no_new_hr_junction_table_is_untracked` -- vangt een NIEUWE, ongemelde koppeltabel in
   dezelfde twee modules (bv. een zesde tabel later toegevoegd zonder dit bestand bij te
   werken).

**Mutatiebewijs (2026-08-22), een regel per bewaakt element, in beide richtingen:**
- Elk van de drie tabelnamen tijdelijk uit `KNOWN_SINGLE_FK_JUNCTION_TABLES` verwijderd (om de
  beurt) -> `test_no_new_hr_junction_table_is_untracked` wordt ROOD (de tabel wordt gezien als
  een ongemelde nieuwe koppeltabel). Hersteld -> GROEN.
- `role_id`/`skill_id` op `role_required_skills` tijdelijk vervangen door een composite
  `ForeignKeyConstraint(["tenant_id", "role_id"], ["roles.tenant_id", "roles.id"])` (in een
  kopie van het model, niet het echte bestand) -> `test_a_known_table_still_lacks_the_
  composite_fk` wordt ROOD voor die tabel (de staleness-check betrapt de fix). Hersteld ->
  GROEN.
- **Correctie na Gate 2 (security-reviewer, 2026-08-22): de eerste versie van deze mutatie
  loste een reeel scoping-gat NIET op.** `test_no_new_hr_junction_table_is_untracked` filterde
  destijds via een hardcoded namenlijst (`{"skills", "role_required_skills", ...}`) VOOR de
  vergelijking met `KNOWN_SINGLE_FK_JUNCTION_TABLES` -- een koppeltabel met een compleet NIEUWE
  naam viel daardoor al buiten die lijst en kon nooit als "untracked" gerapporteerd worden. De
  toen beschreven mutatie ("een vierde, fictieve klasse... zonder hem in de lijst te zetten")
  werkte alleen omdat hij toevallig een AL-BEKENDE naam hergebruikte, niet een nieuwe. Bewijs:
  een tijdelijke klasse `_MutationTestCertification` (tabel `employee_certifications_
  MUTATION_TEST`, tenant_id + user_id-FK + training_id-FK, een compleet nieuwe naam) toegevoegd
  aan `hr_training_models.py` -- met de OUDE, hardcoded-namenlijst-versie bleef de test GROEN
  (het gat); met de HUIDIGE, dynamische versie (`_tables_defined_in_hr_modules()`, via
  `Base.registry.mappers`/`__module__` in plaats van een naam-allowlist) wordt hij ROOD.
  Bestand hersteld via `cp`-backup (nooit `git checkout --`, gedeelde working-copy), `git
  status` bevestigt de herstelde inhoud identiek aan de bedoelde eindstaat.
"""

from __future__ import annotations

import pytest
from sqlalchemy import ForeignKeyConstraint

# Tabelnaam -> gedateerde reden. Expliciet benoemd, geen kale set: precies zoals
# `.claude/rules/quality-gates.md`'s "guard-met-gedateerde-uitzondering"-patroon vereist.
KNOWN_SINGLE_FK_JUNCTION_TABLES: dict[str, str] = {
    "role_required_skills": (
        "2026-08-15 (hr_skills_models.py) -- role_id/skill_id zijn enkelvoudige FKs, geen "
        "composite naar (tenant_id, id). Bekend gat, gedeeld met de twee andere hier genoemde "
        "tabellen, bewust niet als eerste in isolatie gefixed (Rakesh, 2026-08-22)."
    ),
    "employee_skills": (
        "2026-08-15 (hr_skills_models.py) -- user_id/skill_id zijn enkelvoudige FKs. Zelfde "
        "gat en zelfde reden als role_required_skills."
    ),
    "employee_trainings": (
        "2026-08-22 (hr_training_models.py, BE-AGT-058) -- user_id/training_id zijn "
        "enkelvoudige FKs. Bewust hetzelfde patroon als de twee bestaande tabellen gevolgd "
        "i.p.v. een derde, inconsistente aanpak te introduceren vooruitlopend op de bredere "
        "Hardening Sprint."
    ),
    "training_proposals": (
        "2026-10-11 (hr_training_models.py, HR-pilot dag 2) -- user_id/skill_id/training_id zijn "
        "enkelvoudige FKs, net als employee_trainings: een composite FK vraagt een unieke sleutel "
        "(id, tenant_id) op `skills` en `trainings`, en de dagbrief liet bestaande tabellen "
        "ongemoeid. De repository filtert elke query expliciet op tenant_id en de tabel heeft RLS."
    ),
}


_HR_MODULES = frozenset(
    {
        "src.core.models.hr_skills_models",
        "src.core.models.hr_training_models",
    }
)


def _tables_defined_in_hr_modules() -> set[str]:
    """Tabelnamen waarvan de MAPPED CLASS in een van de twee HR-modules staat.

    Dynamisch via `Base.registry.mappers`, NIET een hardcoded naam-lijst: een koppeltabel met
    een compleet nieuwe naam moet automatisch in scope komen. Een hardcoded namenlijst zou een
    NIEUWE tabel juist FILTEREN VOOR de "staat hij in KNOWN_..." check ooit wordt bereikt --
    precies het gat dat Gate 2 (security-reviewer, 2026-08-22) vond in een eerdere versie van
    deze functie: de untracked-check gebruikte toen `{"skills", "role_required_skills", ...}`
    als filter, waardoor een zesde tabel met een andere naam nooit als "untracked" kon worden
    gerapporteerd -- hij werd al voor die vergelijking weggefilterd. Bevestigd met een
    synthetische tabel `employee_certifications`: met de oude, hardcoded lijst bleef de test
    GROEN; met deze dynamische versie wordt hij ROOD (zie mutatiebewijs in de moduledocstring).
    """
    import src.core.models.hr_skills_models  # noqa: F401
    import src.core.models.hr_training_models  # noqa: F401
    from src.core.database.database import Base

    return {
        mapper.local_table.name
        for mapper in Base.registry.mappers
        if mapper.class_.__module__ in _HR_MODULES
    }


def _hr_junction_candidates() -> dict[str, list[str]]:
    """Tabellen in de twee HR-modules met `tenant_id` PLUS >=2 andere, enkelvoudige FK-kolommen.

    Enkelvoudige FK = een `ForeignKeyConstraint` die precies EEN kolom omvat. Een tabel met
    `tenant_id` en maar EEN andere FK-kolom (bv. `trainings.skill_id`) is geen koppeltabel in
    de zin van ADR-005 par. 5 -- die par. gaat over koppelingen TUSSEN twee andere entiteiten,
    niet over een enkele optionele referentie op een catalogusrij.
    """
    import src.core.models.hr_skills_models  # noqa: F401
    import src.core.models.hr_training_models  # noqa: F401
    from src.core.database.database import Base

    candidates: dict[str, list[str]] = {}
    for name, table in Base.metadata.tables.items():
        if "tenant_id" not in table.columns:
            continue
        single_col_fk_columns = [
            list(fk.columns)[0].name
            for fk in table.constraints
            if isinstance(fk, ForeignKeyConstraint)
            and len(fk.columns) == 1
            and list(fk.columns)[0].name != "tenant_id"
        ]
        if len(single_col_fk_columns) >= 2:
            candidates[name] = sorted(single_col_fk_columns)
    return candidates


@pytest.mark.parametrize("table_name", sorted(KNOWN_SINGLE_FK_JUNCTION_TABLES))
def test_a_known_table_still_lacks_the_composite_fk(table_name: str) -> None:
    """Staleness-check: als dit gat gefixed is, moet de lijst hierboven bijgewerkt worden."""
    candidates = _hr_junction_candidates()
    assert table_name in candidates, (
        f"`{table_name}` staat in KNOWN_SINGLE_FK_JUNCTION_TABLES, maar heeft nu WEL "
        "composite FKs (of is helemaal geen koppeltabel meer). Verwijder deze regel uit de "
        "gedateerde uitzonderingslijst -- het gat is gedicht."
    )


def test_no_new_hr_junction_table_is_untracked() -> None:
    """Een NIEUWE, ongemelde koppeltabel in de HR-modules moet hier eerst geregistreerd worden."""
    candidates = _hr_junction_candidates()
    hr_table_names = _tables_defined_in_hr_modules()
    untracked = {
        name: cols
        for name, cols in candidates.items()
        if name in hr_table_names and name not in KNOWN_SINGLE_FK_JUNCTION_TABLES
    }
    assert not untracked, (
        f"Nieuwe HR-koppeltabel(len) zonder composite FK en zonder registratie: {untracked}. "
        "Voeg ze toe aan KNOWN_SINGLE_FK_JUNCTION_TABLES met een gedateerde reden, of geef ze "
        "de composite FK die ADR-005 par. 5 vereist."
    )


def test_the_guard_is_not_vacuous() -> None:
    """Een lege verzameling maakt beide tests hierboven trivially groen."""
    assert KNOWN_SINGLE_FK_JUNCTION_TABLES, "geen tabellen benoemd"
    candidates = _hr_junction_candidates()
    assert candidates, "de scan vindt geen enkele HR-koppeltabel -- meet deze guard nog iets?"
