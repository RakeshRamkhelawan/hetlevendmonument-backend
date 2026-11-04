"""`receivables` krijgt in een ACTIEVE migratie RLS aan en een policy (debiteurenagent dag 1).

**Hergebruik, geen tweede variant.** De analyse is `dekking_van` uit
`test_user_roles_has_row_level_security_in_an_active_migration.py` (OP-190): elk bestand in
`src/alembic/versions/` wordt met `ast` geparsed, alleen SQL in `.execute(...)` buiten
`downgrade()` telt, docstrings en commentaar (Python en SQL) tellen niet, en `{tabel}` in een
f-string wordt opgelost via de omsluitende `for`-lus of de argumenten van een hulpfunctie.
De legacy-map `alembic/` telt niet. Dezelfde mutatiematrix wordt hier op `receivables`
toegepast (`MUTANTEN` met de tabelnaam vervangen).

**De bredere eis -- ELKE tabel met een `tenant_id` die in de keten ontstaat heeft een policy
-- is al bewaakt** door
`tests/integration/security/test_the_application_role_is_confined_to_its_tenant.py::`
`TestThePolicyCoverageIsComplete::test_every_table_with_a_tenant_column_has_a_policy`, op een
database uit `alembic upgrade head`. Die wordt niet nagebouwd; hij is rood geworden toen de
tabel zonder policy bestond (zie het rapport van dag 1) en groen met de policy.

**Bewaakte elementen (twee):**

1. `ALTER TABLE receivables ENABLE ROW LEVEL SECURITY` in `upgrade()`
2. `CREATE POLICY <naam> ON receivables` in `upgrade()`

**Mutatiebewijs, een regel per element, beide richtingen.**

Op de PRODUCTIECODE (de echte migratie `20261005_receivables_rls.py`, gemuteerd op een kopie
van `src/alembic/versions/` in een tijdelijke map; de echte boom niet aangeraakt), 2026-10-04:

| Mutatie in de echte migratie | Element 1 (ENABLE) | Element 2 (POLICY) |
| --- | --- | --- |
| ongewijzigd | gevonden | gevonden |
| `ENABLE` -> `DISABLE` | ROOD | gevonden |
| `CREATE POLICY` verwijderd | gevonden | ROOD |
| beide statements naar `downgrade()` verplaatst | ROOD | ROOD |
| lus-tuple `_RLS_TABELLEN` noemt `receivables_x` | ROOD | ROOD |

Gemeten met `test_the_real_migration_mutants` hieronder (geparametriseerd, dus herhaalbaar).

Synthetische mutanten (de matrix van OP-190, op deze tabel): zie `MUTANTEN`; elk is een
testcase met een eigen naam in `test_enable_is_detected_exactly_when_it_is_really_there` en
`test_policy_is_detected_exactly_when_it_is_really_there`.

**Wat deze guard NIET zegt.** Of de policy de juiste expressie heeft en of hij in beide
richtingen werkt: dat meet
`tests/integration/security/test_receivables_is_confined_to_its_tenant.py`.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tests.architecture.test_user_roles_has_row_level_security_in_an_active_migration import (
    _ACTIEVE_MAP,
    MUTANTEN as _MUTANTEN_USER_ROLES,
    dekking_van,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TABEL = "receivables"
_MIGRATIE = "20261005_receivables_rls.py"

MUTANTEN: dict[str, tuple[str, bool, bool]] = {
    naam.replace("user-roles", "receivables"): (bron.replace("user_roles", _TABEL), enable, policy)
    for naam, (bron, enable, policy) in _MUTANTEN_USER_ROLES.items()
}


def test_receivables_has_row_level_security_enabled_in_an_active_migration() -> None:
    """Element 1."""
    dekking = dekking_van(_TABEL, _REPO_ROOT)

    assert dekking.enable, (
        f"Geen migratie in {_ACTIEVE_MAP.as_posix()} zet ROW LEVEL SECURITY aan op `{_TABEL}`. "
        "Een policy op een tabel met RLS UIT wordt nooit geevalueerd."
    )


def test_receivables_has_a_policy_in_an_active_migration() -> None:
    """Element 2."""
    dekking = dekking_van(_TABEL, _REPO_ROOT)

    assert dekking.policy, (
        f"Geen migratie in {_ACTIEVE_MAP.as_posix()} maakt een policy op `{_TABEL}`. Onder de "
        "applicatierol is de tabel dan voor elke tenant open."
    )


def test_the_mutation_matrix_is_about_receivables() -> None:
    """De vervanging heeft echt iets vervangen; anders toetst de matrix nog `user_roles`."""
    assert not [n for n, (bron, _, _) in MUTANTEN.items() if "user_roles" in bron], (
        "Een mutant noemt nog `user_roles`."
    )
    assert sum(1 for bron, _, _ in MUTANTEN.values() if _TABEL in bron) >= 10


def _plaats(repo_root: Path, bron: str, onder: Path = _ACTIEVE_MAP) -> None:
    map_ = repo_root / onder
    map_.mkdir(parents=True, exist_ok=True)
    (map_ / "mutant.py").write_text(bron, encoding="utf-8")


@pytest.mark.parametrize("naam", sorted(MUTANTEN))
def test_enable_is_detected_exactly_when_it_is_really_there(naam: str, tmp_path: Path) -> None:
    bron, verwacht, _ = MUTANTEN[naam]
    _plaats(tmp_path, bron)

    gevonden = bool(dekking_van(_TABEL, tmp_path).enable)

    assert gevonden is verwacht, f"Mutant `{naam}`: ENABLE gevonden={gevonden}, verwacht={verwacht}."


@pytest.mark.parametrize("naam", sorted(MUTANTEN))
def test_policy_is_detected_exactly_when_it_is_really_there(naam: str, tmp_path: Path) -> None:
    bron, _, verwacht = MUTANTEN[naam]
    _plaats(tmp_path, bron)

    gevonden = bool(dekking_van(_TABEL, tmp_path).policy)

    assert gevonden is verwacht, f"Mutant `{naam}`: policy gevonden={gevonden}, verwacht={verwacht}."


def test_a_migration_in_the_legacy_folder_does_not_count(tmp_path: Path) -> None:
    bron, _, _ = MUTANTEN["beide-direct-in-upgrade"]
    _plaats(tmp_path, bron, onder=Path("alembic") / "versions")

    dekking = dekking_van(_TABEL, tmp_path)

    assert not dekking.enable and not dekking.policy, "De legacy-map telt mee."


def _echte_migratie() -> str:
    return (_REPO_ROOT / _ACTIEVE_MAP / _MIGRATIE).read_text(encoding="utf-8")


def _verplaats_naar_downgrade(bron: str) -> str:
    """Wissel de namen van upgrade() en downgrade(): de statements staan dan in downgrade()."""
    return (
        bron.replace("def upgrade()", "def __wissel()")
        .replace("def downgrade()", "def upgrade()")
        .replace("def __wissel()", "def downgrade()")
    )


def _zonder_policy(bron: str) -> str:
    regels = [r for r in bron.splitlines() if "CREATE POLICY" not in r]
    return "\n".join(regels) + "\n"


# naam -> (mutatiefunctie, ENABLE verwacht, POLICY verwacht)
_ECHTE_MUTANTEN = {
    "ongewijzigd": (lambda b: b, True, True),
    "enable-wordt-disable": (
        lambda b: b.replace("ENABLE ROW LEVEL SECURITY", "DISABLE ROW LEVEL SECURITY"),
        False,
        True,
    ),
    "policy-verwijderd": (_zonder_policy, True, False),
    "beide-naar-downgrade": (_verplaats_naar_downgrade, False, False),
    "andere-tabelnaam": (
        lambda b: b.replace('_RLS_TABELLEN = ("receivables",)', '_RLS_TABELLEN = ("receivables_x",)'),
        False,
        False,
    ),
}


@pytest.mark.parametrize("naam", sorted(_ECHTE_MUTANTEN))
def test_the_real_migration_mutants(naam: str, tmp_path: Path) -> None:
    """Muteer de ECHTE migratie op een kopie van de keten; de guard volgt elke mutatie."""
    mutatie, verwacht_enable, verwacht_policy = _ECHTE_MUTANTEN[naam]
    shutil.copytree(_REPO_ROOT / _ACTIEVE_MAP, tmp_path / _ACTIEVE_MAP)
    (tmp_path / _ACTIEVE_MAP / _MIGRATIE).write_text(mutatie(_echte_migratie()), encoding="utf-8")

    dekking = dekking_van(_TABEL, tmp_path)

    assert (bool(dekking.enable), bool(dekking.policy)) == (verwacht_enable, verwacht_policy), (
        f"Echte-migratiemutant `{naam}`: (enable, policy) = "
        f"({bool(dekking.enable)}, {bool(dekking.policy)}), verwacht "
        f"({verwacht_enable}, {verwacht_policy})."
    )
