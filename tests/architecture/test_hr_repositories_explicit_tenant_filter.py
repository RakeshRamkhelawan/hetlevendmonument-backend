"""Elke DB-aanroepende methode op de hr-import-repositories filtert expliciet op `tenant_id`
(Fase 3 dag 4, BE-AGT-061 -- doc-review BE-AGT-058, bevinding High).

**Waarom deze guard bestaat in plaats van de `TenantFilterBypass`-WARNING te bewaken.** De
dag-4-integratietest zag een `WARNING BYPASS: Tenant filter DISABLED`-logregel op elke GET-
aanvraag, getraceerd tot `TenantFilterBypass` binnen de auth-resolutieketen
(`get_current_user` moet een gebruikers tenant_id opzoeken VOORDAT enige tenant-context
bestaat -- een legitiem, gedocumenteerd gebruik van die class, bevestigd door twee
onafhankelijke Gate-2-reviewers). Een guard die DIE logregel bewaakt zou dus een vals
signaal bewaken, niet de echte beveiliging. Een mutatietest tijdens dag 4 bewees dat de
ECHTE, werkende veiligheidslaag de EXPLICIETE `tenant_id`-vergelijking in elke repository-
methode is (het verwijderen van `Skill.tenant_id == tenant_id` uit `list_skills` liet de
tenant-isolatietest ROOD gaan; herstellen liet hem weer GROEN gaan). Deze guard maakt die
eenmalige, handmatige mutatietest permanent en geautomatiseerd, zodat een latere wijziging
die diezelfde vergelijking uit een van de 7 methoden verwijdert, bij de volgende CI-run
gevangen wordt -- in plaats van pas bij een volgende handmatige mutatietest.

**Mutatiebewijs (beide richtingen):**
1. Rood: `Skill.tenant_id == tenant_id` tijdelijk verwijderd uit `list_skills` ->
   `test_every_method_compares_a_model_tenant_id_column_to_its_own_parameter` faalde met
   `list_skills` in de meldingslijst (geverifieerd tijdens het schrijven van deze test).
2. Groen: de ongewijzigde, huidige broncode van beide repositories -> test slaagt voor alle
   7 methoden.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_TARGET_FILES = [
    REPO_ROOT / "src" / "core" / "repositories" / "hr_skills_import_repository.py",
    REPO_ROOT / "src" / "core" / "repositories" / "hr_trainings_repository.py",
]


def _methods_with_a_tenant_id_parameter(tree: ast.Module) -> list[ast.AsyncFunctionDef]:
    methods: list[ast.AsyncFunctionDef] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        param_names = {arg.arg for arg in node.args.args}
        if "tenant_id" in param_names:
            methods.append(node)
    return methods


def _compares_a_tenant_id_column_to_its_own_parameter(method: ast.AsyncFunctionDef) -> bool:
    """True als de methode-body een `<Model>.tenant_id == tenant_id`-vergelijking bevat --
    een Attribute-toegang met attr=='tenant_id', vergeleken met '==' tegen een Name met
    dezelfde naam als de methode's eigen `tenant_id`-parameter."""
    for node in ast.walk(method):
        if not isinstance(node, ast.Compare):
            continue
        if len(node.ops) != 1 or not isinstance(node.ops[0], ast.Eq):
            continue
        left = node.left
        right = node.comparators[0]
        left_is_tenant_column = isinstance(left, ast.Attribute) and left.attr == "tenant_id"
        right_is_tenant_param = isinstance(right, ast.Name) and right.id == "tenant_id"
        if left_is_tenant_column and right_is_tenant_param:
            return True
    return False


def test_every_method_compares_a_model_tenant_id_column_to_its_own_parameter() -> None:
    """Elke methode met een `tenant_id`-parameter op de hr-import-repositories moet die
    parameter daadwerkelijk gebruiken in een `<Model>.tenant_id == tenant_id`-vergelijking --
    niet alleen aannemen, maar elke methode individueel controleren (aanscherping 2026-08-14:
    "een guard itereert over een expliciet benoemde verzameling, met een regel per element")."""
    violations: list[str] = []
    checked_methods: list[str] = []

    for path in _TARGET_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for method in _methods_with_a_tenant_id_parameter(tree):
            checked_methods.append(f"{path.name}::{method.name}")
            if not _compares_a_tenant_id_column_to_its_own_parameter(method):
                violations.append(f"{path.name}::{method.name}")

    # Bewijst dat de scan geen lege verzameling controleert (zou de guard vacuous maken).
    assert len(checked_methods) == 7, (
        f"Verwachtte 7 methoden met een tenant_id-parameter, vond {len(checked_methods)}: "
        f"{checked_methods}. Nieuwe/verwijderde repository-methoden moeten dit getal "
        "bewust bijwerken."
    )
    assert not violations, (
        f"{len(violations)} methode(n) met een tenant_id-parameter vergelijken die nooit "
        f"expliciet met een model-kolom: {violations}. Elke DB-lezende/schrijvende methode "
        "op de hr-import-repositories moet `<Model>.tenant_id == tenant_id` gebruiken -- "
        "zie de module-docstring voor het mutatiebewijs dat dit de daadwerkelijk werkende "
        "tenant-isolatielaag is."
    )
