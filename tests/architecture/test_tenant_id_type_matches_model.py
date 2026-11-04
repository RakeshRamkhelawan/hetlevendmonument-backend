"""Architecture test: het tenant_id-type in de code moet het KOLOMTYPE volgen.

Achtergrond (2026-07-31 / 2026-08-01):
`DomainPackRegistry._normalize_tenant_id` normaliseerde tenant_id naar een UUID en gooide
een `TypeError` op een int. Gevolg in productie: de health-check van die registry
(`health_endpoints.py`, `tenant_id=1`) faalde altijd. En zelfs zonder die TypeError zou de
"defense in depth"-filter een UUID-string vergelijken met een integer-tenant_id en dus
STIL een lege lijst opleveren -- erger dan een crash, want dan lijkt het alsof een tenant
geen packs heeft.

Het bleef staan omdat drie bronnen elkaar tegenspraken:
- de kolom (`Integer`), de repository (`int`) en beide productie-aanroepers (`int`);
- een testsuite van 480 regels die met `uuid4()`-tenants tegen een GEMOCKTE repository
  draaide en dus nooit een echte kolom raakte;
- een type-contract uit SP-TYPE-05 dat letterlijk `UUID | str` eiste.

Alle drie zijn op 2026-08-01 op int gezet. Deze test voorkomt dat ze opnieuw uit elkaar
lopen door de code-annotatie te KOPPELEN aan het datamodel: verandert de kolom ooit naar
UUID, dan faalt deze test totdat de code meebeweegt -- en andersom.
"""

import ast
from pathlib import Path

MODELS_FILE = Path("src/core/procedures/models.py")
REGISTRY_FILE = Path("src/core/procedures/domain_pack_registry.py")
REPOSITORY_FILE = Path("src/core/procedures/domain_pack_repository.py")

# SQLAlchemy-kolomtype -> het Python-type dat de code moet accepteren.
COLUMN_TO_PYTHON = {"Integer": "int", "BigInteger": "int", "String": "str", "UUID": "UUID"}


def _tenant_column_type(model_file: Path, class_name: str) -> str:
    """Het SQLAlchemy-kolomtype van tenant_id in het opgegeven model."""
    tree = ast.parse(model_file.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for item in node.body:
            if (
                isinstance(item, ast.AnnAssign)
                and isinstance(item.target, ast.Name)
                and item.target.id == "tenant_id"
                and isinstance(item.value, ast.Call)
            ):
                for arg in item.value.args:
                    name = getattr(arg, "id", None) or getattr(arg, "attr", None)
                    if name in COLUMN_TO_PYTHON:
                        return name
    raise AssertionError(f"tenant_id-kolom niet gevonden in {class_name} ({model_file})")


def _annotated_tenant_params(source_file: Path) -> list[tuple[str, str]]:
    """(functienaam, annotatie) voor elke parameter die tenant_id heet."""
    tree = ast.parse(source_file.read_text(encoding="utf-8"))
    found: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        args = node.args
        for arg in list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs):
            if arg.arg == "tenant_id" and arg.annotation is not None:
                found.append((node.name, ast.unparse(arg.annotation)))
    return found


def test_domain_pack_column_is_integer() -> None:
    """Vangnet: verandert het model, dan moet deze test bewust worden bijgewerkt."""
    assert _tenant_column_type(MODELS_FILE, "DomainPack") == "Integer", (
        "DomainPack.tenant_id is geen Integer meer. Werk COLUMN_TO_PYTHON bij EN pas de "
        "registry/repository aan -- anders ontstaat opnieuw de situatie waarin de code "
        "een ander tenant-type gebruikt dan de database."
    )


def test_registry_tenant_annotations_match_the_column() -> None:
    """Elke tenant_id-parameter in de registry moet het kolomtype toestaan."""
    expected = COLUMN_TO_PYTHON[_tenant_column_type(MODELS_FILE, "DomainPack")]

    problems: list[str] = []
    for func, annotation in _annotated_tenant_params(REGISTRY_FILE):
        parts = {p.strip() for p in annotation.replace("|", " ").split()}
        if expected not in parts:
            problems.append(f"{func}: `{annotation}` accepteert geen {expected}")
        if "UUID" in parts and expected != "UUID":
            problems.append(
                f"{func}: `{annotation}` accepteert UUID terwijl de kolom {expected} is -- "
                "een UUID-tenant levert tegen een echte repository stil nul rijen op"
            )

    assert not problems, (
        f"tenant_id-annotaties in {REGISTRY_FILE.as_posix()} wijken af van het kolomtype "
        f"({expected}):\n" + "\n".join(f"  - {p}" for p in problems)
    )


def test_repository_tenant_annotations_match_the_column() -> None:
    """Dezelfde eis een laag lager -- daar zat de oorspronkelijke mismatch tussenin."""
    expected = COLUMN_TO_PYTHON[_tenant_column_type(MODELS_FILE, "DomainPack")]

    problems = [
        f"{func}: `{annotation}`"
        for func, annotation in _annotated_tenant_params(REPOSITORY_FILE)
        if expected not in {p.strip() for p in annotation.replace("|", " ").split()}
    ]
    assert not problems, (
        f"tenant_id-annotaties in {REPOSITORY_FILE.as_posix()} accepteren geen {expected}:\n"
        + "\n".join(f"  - {p}" for p in problems)
    )


def test_scan_finds_tenant_parameters() -> None:
    """Vangnet tegen een vacuum-pass als de parameters worden hernoemd."""
    total = len(_annotated_tenant_params(REGISTRY_FILE)) + len(
        _annotated_tenant_params(REPOSITORY_FILE)
    )
    assert total >= 4, (
        f"Verwacht minimaal 4 geannoteerde tenant_id-parameters in registry+repository, "
        f"gevonden {total} -- de scan matcht niet meer."
    )
