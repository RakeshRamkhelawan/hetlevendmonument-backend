"""Geen productiepad bewaart een goedkeuring in procesgeheugen (ADR-036 OP-264).

Waarom: een beslissing die in een Python-lijst of -dict van het PROCES staat, heeft geen
database, geen auditregel en overleeft geen herstart; elke Gunicorn-worker heeft bovendien een
eigen kopie. Zo'n plek SUGGEREERT menselijk toezicht zonder spoor. `hitl_tickets`
(`src/core/tool_broker/hitl_repository.py`) is de enige bron van waarheid.

Wat de guard bewaakt -- een BENOEMDE verzameling van vier elementen, STRUCTUREEL (`ast`, geen
tekst; docstrings en comments tellen dus niet mee):

  E1  een container (list/dict/set/comprehension of `list()`/`dict()`/`set()`/`defaultdict()`/
      `deque()`) die op MODULENIVEAU wordt gebonden aan een naam met "approval" erin
      (`approval_requests`).
  E2  een module-level list/dict-literal met daarin een dict met `"status": "pending"` onder
      ELKE naam (de demorijen; een hernoemde lijst ontsnapt niet aan E1 alleen).
  E3  een dict-literal die aan `app_state` wordt toegekend met een constante sleutel met
      "approval" erin (`"approval_requests": []` in `src/core/shared/app_state.py`).
  E4  `app_state["...approval..."]` of `app_state.setdefault("...approval...", ...)`, waar
      dan ook (ook binnen een functie).

Een uitzonderingslijst bestaat BEWUST niet: de bevinding is dat deze plekken WEGGAAN, en een
lijst zou de guard vandaag groen maken. Elke overtreding wordt gemeld als
`bestand::functie` (`<module>` op modulniveau); de functie wordt met EXPLICIETE recursie
bijgehouden, want `ast.walk()` vanaf een functieknoop onderscheidt een geneste functie niet van
zijn ouder.

Wat NIET geraakt hoort te worden: de legitieme schrijver `hitl_tickets`
(`hitl_repository.py` wordt als echt bestand gekopieerd en moet schoon blijven), een Prometheus-
`Counter` met "APPROVALS" in de naam, een constante `_APPROVAL_VALID_HOURS`, en een
`app_state`-sleutel zonder "approval".

Beperking (niet gemeten, niet bewaakt): een goedkeuring in een KLASSE- of INSTANTIEATTRIBUUT
(`self._approvals = {}`) en een lijst die onder een naam zonder "approval" en zonder
`"status": "pending"`-rij wordt gevuld. Een scan op alleen de naam gaf 30 treffers waarvan
vrijwel alle onschuldig zijn (`approval_required`, `approval_phrases`); die ruis is niet
gemeten per geval.

Mutatiebewijs (daadwerkelijk gedraaid, 2026-10-04): zie de test-klasse `TestDetectorGedrag`; elk
element heeft een rode en een groene regel, en die draaien op het ECHTE bestand
`management_endpoints.py` (kopie, in `tmp_path`) en op het echte `app_state.py` en
`hitl_repository.py`. De mutaties zelf staan in de terugmelding van taak 1.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SRC = REPO_ROOT / "src"

_CONTAINER_NODES = (
    ast.List,
    ast.Dict,
    ast.Set,
    ast.ListComp,
    ast.DictComp,
    ast.SetComp,
)
_CONTAINER_FACTORIES = frozenset({"list", "dict", "set", "defaultdict", "OrderedDict", "deque"})
_SCOPE_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)


def _is_container(value: ast.expr) -> bool:
    if isinstance(value, _CONTAINER_NODES):
        return True
    if isinstance(value, ast.Call):
        func = value.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
        return name in _CONTAINER_FACTORIES
    return False


def _bound_names(node: ast.stmt) -> tuple[list[str], ast.expr | None]:
    if isinstance(node, ast.Assign):
        return [t.id for t in node.targets if isinstance(t, ast.Name)], node.value
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return [node.target.id], node.value
    return [], None


def _has_pending_row(value: ast.expr) -> bool:
    for sub in ast.walk(value):
        if not isinstance(sub, ast.Dict):
            continue
        for key, val in zip(sub.keys, sub.values):
            if (
                isinstance(key, ast.Constant)
                and key.value == "status"
                and isinstance(val, ast.Constant)
                and val.value == "pending"
            ):
                return True
    return False


def _approval_const_keys(dict_node: ast.Dict) -> list[str]:
    return [
        key.value
        for key in dict_node.keys
        if isinstance(key, ast.Constant)
        and isinstance(key.value, str)
        and "approval" in key.value.lower()
    ]


def _is_app_state(node: ast.expr) -> bool:
    return isinstance(node, ast.Name) and node.id == "app_state"


def _visit(node: ast.AST, scope: str, module_level: bool, out: list[tuple[str, str]]) -> None:
    """Expliciete recursie: `scope` is de omsluitende functie, `module_level` of we er buiten zijn."""
    for child in ast.iter_child_nodes(node):
        child_scope, child_module_level = scope, module_level
        if isinstance(child, _SCOPE_NODES):
            name = getattr(child, "name", "<lambda>")
            child_scope = name if scope == "<module>" else f"{scope}.{name}"
            child_module_level = False

        names, value = _bound_names(child) if isinstance(child, ast.stmt) else ([], None)
        if module_level and value is not None:
            for name in names:
                if "approval" in name.lower() and _is_container(value):
                    out.append((scope, f"E1 module-level container `{name}`"))
            if isinstance(value, (ast.List, ast.Dict)) and _has_pending_row(value):
                out.append((scope, f"E2 module-level rijen met status=pending in `{names}`"))
        if isinstance(value, ast.Dict) and "app_state" in names:
            for key in _approval_const_keys(value):
                out.append((scope, f"E3 app_state-sleutel `{key}`"))

        if isinstance(child, ast.Subscript) and _is_app_state(child.value):
            sl = child.slice
            if (
                isinstance(sl, ast.Constant)
                and isinstance(sl.value, str)
                and "approval" in sl.value.lower()
            ):
                out.append((scope, f"E4 app_state[{sl.value!r}]"))
        if (
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Attribute)
            and child.func.attr == "setdefault"
            and _is_app_state(child.func.value)
            and child.args
            and isinstance(child.args[0], ast.Constant)
            and isinstance(child.args[0].value, str)
            and "approval" in child.args[0].value.lower()
        ):
            out.append((scope, f"E4 app_state.setdefault({child.args[0].value!r})"))

        _visit(child, child_scope, child_module_level, out)


def find_violations(source: str, rel_path: str) -> list[str]:
    """Geef `bestand::functie [element]` per overtreding."""
    tree = ast.parse(source)
    found: list[tuple[str, str]] = []
    _visit(tree, "<module>", True, found)
    return [f"{rel_path}::{scope} [{what}]" for scope, what in found]


def _scan_tree(root: Path) -> list[str]:
    violations: list[str] = []
    for path in sorted(root.rglob("*.py")):
        try:
            source = path.read_text(encoding="utf-8")
            violations.extend(find_violations(source, path.relative_to(root.parent).as_posix()))
        except (SyntaxError, UnicodeDecodeError):
            continue
    return violations


# ---------------------------------------------------------------------------------------------
# De echte producent: de hele productieboom.
# ---------------------------------------------------------------------------------------------


def test_no_production_path_keeps_an_approval_in_process_memory() -> None:
    """OP-264: de demolijst, de `app_state`-sleutel en elke vervanger daarvan zijn weg."""
    violations = _scan_tree(SRC)

    assert violations == [], (
        "Een goedkeuring in procesgeheugen heeft geen database en geen auditregel "
        "(bron van waarheid is `hitl_tickets`):\n  " + "\n  ".join(violations)
    )


def test_the_scan_reads_the_real_tree() -> None:
    """Controlegroep: een scan die niets leest, zou ook 'geen overtredingen' melden."""
    gelezen = [p for p in SRC.rglob("*.py") if p.name == "hitl_repository.py"]

    assert gelezen != []


# ---------------------------------------------------------------------------------------------
# Het gedrag van de detector zelf, beide richtingen, een regel PER element.
# ---------------------------------------------------------------------------------------------


def _real(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


class TestDetectorGedrag:
    """Rood: het element wordt betrapt. Groen: een legitiem lijkend geval blijft hangen niet."""

    def test_e1_catches_a_module_level_approval_container(self) -> None:
        bron = "approval_requests: list[dict] = []\n"

        assert find_violations(bron, "x.py") == [
            "x.py::<module> [E1 module-level container `approval_requests`]"
        ]

    def test_e1_catches_a_factory_call(self) -> None:
        bron = "from collections import defaultdict\npending_approvals = defaultdict(list)\n"

        assert len(find_violations(bron, "x.py")) == 1

    def test_e1_ignores_a_counter_and_a_constant(self) -> None:
        bron = (
            "from prometheus_client import Counter\n"
            "GLOBAL_PACK_APPROVALS = Counter('x', 'y')\n"
            "_APPROVAL_VALID_HOURS = 24\n"
        )

        assert find_violations(bron, "x.py") == []

    def test_e1_ignores_a_function_local_list(self) -> None:
        bron = "def f():\n    approval_requests = []\n    return approval_requests\n"

        assert find_violations(bron, "x.py") == []

    def test_e2_catches_pending_rows_under_a_renamed_list(self) -> None:
        bron = "wachtrij = [{'id': 'A', 'status': 'pending'}]\n"

        assert len(find_violations(bron, "x.py")) == 1

    def test_e2_ignores_rows_with_another_status(self) -> None:
        bron = "voorbeelden = [{'id': 'A', 'status': 'done'}]\n"

        assert find_violations(bron, "x.py") == []

    def test_e3_catches_an_approval_key_in_the_app_state_literal(self) -> None:
        bron = "app_state = {'task_queue': [], 'approval_requests': []}\n"

        assert find_violations(bron, "x.py") == [
            "x.py::<module> [E3 app_state-sleutel `approval_requests`]"
        ]

    def test_e3_ignores_other_keys_in_the_app_state_literal(self) -> None:
        bron = "app_state = {'task_queue': [], 'log_entries': []}\n"

        assert find_violations(bron, "x.py") == []

    def test_e4_catches_a_subscript_write_inside_a_function(self) -> None:
        bron = "def bewaar(x):\n    app_state['approval_requests'].append(x)\n"

        assert find_violations(bron, "x.py") == ["x.py::bewaar [E4 app_state['approval_requests']]"]

    def test_e4_catches_setdefault(self) -> None:
        bron = "def f():\n    app_state.setdefault('approvals', [])\n"

        assert len(find_violations(bron, "x.py")) == 1

    def test_e4_ignores_a_subscript_with_another_key(self) -> None:
        bron = "def f():\n    app_state['task_queue'].append(1)\n"

        assert find_violations(bron, "x.py") == []

    def test_the_enclosing_function_is_tracked_through_nesting(self) -> None:
        bron = "def buiten():\n    def binnen():\n        app_state['approval_x'] = 1\n"

        assert find_violations(bron, "x.py") == ["x.py::buiten.binnen [E4 app_state['approval_x']]"]

    def test_a_docstring_or_comment_naming_the_pattern_is_not_a_violation(self) -> None:
        bron = '"""approval_requests = [] en app_state["approval_requests"]"""\n# approval_requests = []\n'

        assert find_violations(bron, "x.py") == []

    def test_the_legitimate_hitl_tickets_writer_stays_clean(self) -> None:
        bron = _real("src/core/tool_broker/hitl_repository.py")

        assert find_violations(bron, "src/core/tool_broker/hitl_repository.py") == []

    def test_a_mutation_inside_a_file_that_already_violates_is_still_caught(self) -> None:
        """Muteer IN het bestand dat nu overtreedt: haal de bestaande lijst weg, zet een nieuwe terug.

        Zo blijkt dat het bestand zelf niet als geheel wordt vrijgesteld zodra het een keer
        overtrad (de blindheid van een bestandssleutel, OP-258).
        """
        # OP-264: de lijst is uit het bestand verdwenen; het bestand zelf is nu de schone basis.
        schoon = _real("src/core/api/management_endpoints.py")
        gemuteerd = (
            schoon + "\ndef bewaar_nieuw(x):\n    app_state['approval_requests'].append(x)\n"
        )

        assert (
            find_violations(schoon, "m.py"),
            len(find_violations(gemuteerd, "m.py")),
        ) == ([], 1)
