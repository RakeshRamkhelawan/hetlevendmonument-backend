"""ADR-036 D12.5 / OP-162 (CRITICAL/P0, ADR-036-VOLLEDIGE-AUDIT-2026-08-18):
meerdere "Phase 4 Autonomous Systems"-endpoints konden een 2xx geven zonder
ooit GovernanceContract.is_action_permitted() aan te roepen. Deze guard faalt
zolang een bewaakte functie een 2xx-pad kan bereiken zonder governance-
aanroep EN zonder een onvoorwaardelijke disable.

Oorspronkelijk gevonden op precies 1 endpoint (POST /agents/create). Tijdens
de Gate 2-documentatiereview van die fix (2026-08-18) bleek dezelfde
governance-leemte te bestaan op 4 andere muterende endpoints, elk in twee
implementaties (het actieve pad onder src/core/api/v1/autonomous/, en een
legacy duplicaat in src/core/api/autonomous_endpoints.py dat zichzelf al
"vervangen" noemt maar nooit is opgeruimd). De read-only endpoints in
dezelfde bestanden (templates/metrics/status/behaviors/intelligence-levels)
zijn NIET bewaakt -- die scheppen of wijzigen geen state, conform de
oorspronkelijke scoping van de audit zelf (die ook alleen de CREATE-actie
vlagde, niet de READ-endpoints in hetzelfde bestand).

**Expliciet benoemde verzameling (BEWAAKTE_FUNCTIES), 1 testcase per element:**
- agents_router.create_autonomous_agent / autonomous_endpoints.create_autonomous_agent
  (POST /agents/create -- kan een agent aanmaken)
- healing_router.report_system_failure / autonomous_endpoints.report_system_failure
  (POST /healing/report-failure -- kan met auto_repair=true een reparatie UITVOEREN)
- healing_router.execute_repair / autonomous_endpoints.execute_repair
  (POST /healing/execute-repair/{id} -- voert een reparatieplan uit, ADMIN_ALL)
- code_router.generate_code / autonomous_endpoints.generate_code
  (POST /code/generate -- genereert code)
- emergence_router.facilitate_emergence / autonomous_endpoints.facilitate_emergence
  (POST /emergence/facilitate -- faciliteert emergent gedrag tussen agents)

Mutatiebewijs (beide richtingen, uitgevoerd op synthetische AST's, niet op
onvoorwaardelijk-productiegedrag dat om andere redenen kan veranderen):
- Een functie met GEEN is_action_permitted-aanroep en GEEN vroege
  onvoorwaardelijke 503-raise wordt door de guard afgekeurd
  (test_a_function_without_governance_or_disable_is_rejected).
- Een functie met een is_action_permitted-aanroep DIE DE CONTROLEFLOW STUURT
  (in een if-test, met een raise/return in de deny-tak) wordt door de guard
  goedgekeurd (test_a_function_with_a_governance_check_is_accepted).
- Een functie die is_action_permitted() aanroept maar het resultaat NEGEERT
  (niet in een if-test, geen afdwinging) wordt AFGEKEURD -- dit is de
  concrete bypass die Gate 2-review (code-reviewer, 2026-08-18) aantoonde:
  de oorspronkelijke guard keurde dit ten onrechte goed omdat hij alleen op
  AANWEZIGHEID van de aanroep toetste, niet op AFDWINGING
  (test_a_governance_call_whose_result_is_discarded_is_rejected).
- Een functie die onvoorwaardelijk een 503 raiset als allereerste statement
  (na een eventuele docstring) wordt door de guard goedgekeurd
  (test_a_function_disabled_with_an_unconditional_503_is_accepted).
- Een functie die WEL een HTTPException(503) raiset, maar niet als eerste
  statement (er loopt eerst bedrijfslogica), wordt AFGEKEURD -- de guard
  toetst positie, niet alleen aanwezigheid
  (test_a_503_that_is_not_the_first_statement_is_rejected).

Let op de import: `src.core.api.v1.autonomous.__init__` doet zelf
`from .agents_router import agents_router` (de APIRouter-INSTANTIE), waardoor
`from src.core.api.v1.autonomous import agents_router` per ongeluk die
instantie i.p.v. de submodule oplevert. Daarom hier expliciete
`importlib`-imports van de submodules.
"""

import ast
import importlib
import inspect
import textwrap

import pytest

FuncDef = ast.FunctionDef | ast.AsyncFunctionDef

_agents_router_module = importlib.import_module("src.core.api.v1.autonomous.agents_router")
_healing_router_module = importlib.import_module("src.core.api.v1.autonomous.healing_router")
_code_router_module = importlib.import_module("src.core.api.v1.autonomous.code_router")
_emergence_router_module = importlib.import_module("src.core.api.v1.autonomous.emergence_router")
_autonomous_endpoints_module = importlib.import_module("src.core.api.autonomous_endpoints")

# Expliciete verzameling: (leesbare naam, module, functienaam). Elk element
# krijgt zijn eigen testcase via parametrize -- geen enkel element verstopt
# zich achter een gedeelde assert.
BEWAAKTE_FUNCTIES = [
    ("agents_router.create_autonomous_agent", _agents_router_module, "create_autonomous_agent"),
    (
        "autonomous_endpoints.create_autonomous_agent (legacy)",
        _autonomous_endpoints_module,
        "create_autonomous_agent",
    ),
    ("healing_router.report_system_failure", _healing_router_module, "report_system_failure"),
    (
        "autonomous_endpoints.report_system_failure (legacy)",
        _autonomous_endpoints_module,
        "report_system_failure",
    ),
    ("healing_router.execute_repair", _healing_router_module, "execute_repair"),
    (
        "autonomous_endpoints.execute_repair (legacy)",
        _autonomous_endpoints_module,
        "execute_repair",
    ),
    ("code_router.generate_code", _code_router_module, "generate_code"),
    (
        "autonomous_endpoints.generate_code (legacy)",
        _autonomous_endpoints_module,
        "generate_code",
    ),
    ("emergence_router.facilitate_emergence", _emergence_router_module, "facilitate_emergence"),
    (
        "autonomous_endpoints.facilitate_emergence (legacy)",
        _autonomous_endpoints_module,
        "facilitate_emergence",
    ),
]


def _as_funcdef(node: ast.stmt) -> FuncDef:
    assert isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    return node


def _parse_single_function(source: str) -> FuncDef:
    tree = ast.parse(textwrap.dedent(source))
    return _as_funcdef(tree.body[0])


def _function_ast(func: object) -> FuncDef:
    source = textwrap.dedent(inspect.getsource(func))  # type: ignore[arg-type]
    tree = ast.parse(source)
    return _as_funcdef(tree.body[0])


def _contains_is_action_permitted_call(expr: ast.AST) -> bool:
    for node in ast.walk(expr):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "is_action_permitted":
                return True
    return False


def _stops_execution(body: list[ast.stmt]) -> bool:
    return any(isinstance(stmt, (ast.Raise, ast.Return)) for stmt in body)


def _calls_is_action_permitted_and_enforces_it(func_ast: FuncDef) -> bool:
    """Vereist dat de aanroep de controleflow stuurt, niet alleen aanwezig is.

    De aanroep moet in de `test`-expressie van een `if` staan, en minstens een
    van de twee takken (body of orelse) moet de uitvoering stoppen
    (raise/return) -- ongeacht welke polariteit (`if not toegestaan: raise`
    of `if toegestaan: ... else: raise`).
    """
    for node in ast.walk(func_ast):
        if isinstance(node, ast.If) and _contains_is_action_permitted_call(node.test):
            if _stops_execution(node.body) or _stops_execution(node.orelse):
                return True
    return False


def _first_statement_is_unconditional_503(func_ast: FuncDef) -> bool:
    body = list(func_ast.body)
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(getattr(body[0], "value", None), ast.Constant)
    ):
        body = body[1:]  # skip een docstring
    if not body or not isinstance(body[0], ast.Raise):
        return False
    exc = body[0].exc
    if not (
        isinstance(exc, ast.Call)
        and isinstance(exc.func, ast.Name)
        and exc.func.id == "HTTPException"
    ):
        return False
    for kw in exc.keywords:
        if kw.arg == "status_code" and isinstance(kw.value, ast.Constant) and kw.value.value == 503:
            return True
    if exc.args and isinstance(exc.args[0], ast.Constant) and exc.args[0].value == 503:
        return True
    return False


def _is_gated(func_ast: FuncDef) -> bool:
    return _calls_is_action_permitted_and_enforces_it(
        func_ast
    ) or _first_statement_is_unconditional_503(func_ast)


@pytest.mark.parametrize(
    "naam,module,func_name",
    BEWAAKTE_FUNCTIES,
    ids=[naam for naam, _, _ in BEWAAKTE_FUNCTIES],
)
def test_bewaakte_functie_kan_geen_2xx_geven_zonder_governance_of_disable(
    naam: str, module: object, func_name: str
) -> None:
    func_ast = _function_ast(getattr(module, func_name))
    assert _is_gated(func_ast), (
        f"{naam} kan een 2xx geven zonder afgedwongen "
        "GovernanceContract.is_action_permitted() en zonder een onvoorwaardelijke "
        "503-disable vooraan de functie. ADR-036 D12.5 (CRITICAL/P0) -- zie "
        "docs/reports/ADR-036-VOLLEDIGE-AUDIT-2026-08-18.md."
    )


def test_a_function_without_governance_or_disable_is_rejected() -> None:
    func_ast = _parse_single_function(
        """
        async def create_autonomous_agent(request, current_user, _):
            factory = get_agent_factory()
            agent_id = await factory.create_agent(request.archetype, request.name)
            return {"success": True, "agent_id": agent_id}
        """
    )
    assert not _is_gated(func_ast)


def test_a_function_with_a_governance_check_is_accepted() -> None:
    func_ast = _parse_single_function(
        """
        async def create_autonomous_agent(request, current_user, _):
            contract = GovernanceContract(agent_id=request.name, tenant_id=current_user.tenant_id)
            if not contract.is_action_permitted("agents_router.create_agent"):
                raise HTTPException(status_code=403, detail="Not permitted")
            factory = get_agent_factory()
            agent_id = await factory.create_agent(request.archetype, request.name)
            return {"success": True, "agent_id": agent_id}
        """
    )
    assert _is_gated(func_ast)


def test_a_governance_call_whose_result_is_discarded_is_rejected() -> None:
    """Reproduceert de bypass uit Gate 2-review (code-reviewer, 2026-08-18):
    de aanroep is aanwezig maar het resultaat wordt nergens getoetst, dus er
    is geen echte afdwinging."""
    func_ast = _parse_single_function(
        """
        async def create_autonomous_agent(request, current_user, _):
            contract = GovernanceContract(agent_id=request.name, tenant_id=current_user.tenant_id)
            contract.is_action_permitted("agents_router.create_agent")
            factory = get_agent_factory()
            agent_id = await factory.create_agent(request.archetype, request.name)
            return {"success": True, "agent_id": agent_id}
        """
    )
    assert not _is_gated(func_ast)


def test_a_function_disabled_with_an_unconditional_503_is_accepted() -> None:
    func_ast = _parse_single_function(
        '''
        async def create_autonomous_agent(request, current_user, _):
            """Docstring die vooraf mag staan."""
            raise HTTPException(status_code=503, detail="niet beschikbaar")
        '''
    )
    assert _is_gated(func_ast)


def test_a_503_that_is_not_the_first_statement_is_rejected() -> None:
    func_ast = _parse_single_function(
        """
        async def create_autonomous_agent(request, current_user, _):
            factory = get_agent_factory()
            if factory is None:
                raise HTTPException(status_code=503, detail="niet beschikbaar")
            agent_id = await factory.create_agent(request.archetype, request.name)
            return {"success": True, "agent_id": agent_id}
        """
    )
    assert not _is_gated(func_ast)
