"""Fixture: een tenant in de executiecontext voor tests die echt een tool uitvoeren.

Sinds BE-AGT-045 ronde 2 weigert `ToolBrokerService.execute_tool` een uitvoering waarvoor geen
tenant uit de executiecontext te bepalen is. Dat is geen extra strengheid om de strengheid: de
pseudonimiseringsscope van de payload hangt eraan, en de vorige terugval was
`payload.get("tenant_id", "unscoped")` -- dus de payload, die door een taalmodel wordt
geschreven. Zolang die terugval bestond koos het model zijn eigen scope, en deelden alle
aanroepers zonder context een scope. Zie ADR-036 OP-27 en `test_pseudonymisation_leaks.py`.

In productie is er altijd een tenant: de tenant-middleware zet de ADR-003 ContextVar op elk
HTTP-pad, en de agent-paden geven `context={"tenant_id": ...}` mee. Een unittest die een tool
uitvoert zonder tenant modelleert dus een aanroep die per ADR-005 niet bestaat.

Deze fixture zet die ContextVar in plaats van 61 losse aanroepen een `context=` te geven: het is
dezelfde eigenschap, een keer uitgelegd, en het toetst en passant het ContextVar-pad dat in
productie het meest gebruikte is. Tests waarin de tenant ZELF het onderwerp is (HITL
tenant-isolatie) geven hem expliciet mee en gebruiken deze fixture niet.

Gebruik:

    from tests.fixtures.tool_execution_tenant import tool_execution_tenant  # noqa: F401
"""

from collections.abc import Iterator

import pytest

#: De tenant die deze fixture zet. Elke waarde werkt; hij moet alleen bestaan en positief zijn.
FIXTURE_TENANT_ID = 1


@pytest.fixture(autouse=True)
def tool_execution_tenant() -> Iterator[int]:
    """Zet de ADR-003 tenant-ContextVar, en ruim hem op voor EN na.

    Opruimen aan beide kanten: een gezette ContextVar lekt anders naar elke latere test in
    dezelfde xdist-worker -- het patroon dat OP-20 blootlegde.
    """
    from src.core.middleware.tenant_context import set_tenant_id

    set_tenant_id(None)
    set_tenant_id(FIXTURE_TENANT_ID)
    yield FIXTURE_TENANT_ID
    set_tenant_id(None)
