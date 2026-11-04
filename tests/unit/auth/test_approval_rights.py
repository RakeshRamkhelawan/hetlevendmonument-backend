"""Het goedkeurrecht per tool en per agent (ADR-039), zonder database.

`has_approval_right` (de opzoeking in `role_permissions`) wordt vervangen; de mapping en de
weigering zijn de echte code uit `src/core/auth/approval_rights.py`. Het recht zelf met een echte
database: `tests/integration/test_goedkeuren_is_een_procesbevoegdheid.py`.

Besluit Rakesh 2026-10-10: `serena__admin_config` gaat naar de beheerder (`config:approve`);
`local__send_email`, `serena__delete_document` en `delete_task` naar de goedkeurder
(`governance:approve`).
"""

from __future__ import annotations

import pytest

from src.core.auth import approval_rights
from src.core.exceptions import ApprovalRightRequiredError

TOOL_RECHTEN = [
    ("send_payment_reminder", "receivables:approve"),
    ("schedule_training", "hr:approve"),
    ("propose_supplier_invoice", "payables:approve"),
    ("propose_payment_run", "payables:approve"),
    ("local__send_email", "governance:approve"),
    ("serena__delete_document", "governance:approve"),
    ("delete_task", "governance:approve"),
    ("serena__admin_config", "config:approve"),
    # ActivePieces-acties naar buiten (ADR-040 B12): zelfde recht als `local__send_email`.
    ("gmail.send_email", "governance:approve"),
    ("slack.send_message", "governance:approve"),
    ("google-calendar.create_event", "governance:approve"),
]


@pytest.fixture
def rechten(monkeypatch: pytest.MonkeyPatch) -> dict[str, set[str]]:
    gekozen: dict[str, set[str]] = {"nu": set()}

    async def _heeft(db: object, user: object, right: str) -> bool:
        return right in gekozen["nu"]

    monkeypatch.setattr(approval_rights, "has_approval_right", _heeft)
    return gekozen


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(("tool", "recht"), TOOL_RECHTEN)
async def test_the_right_of_the_tool_is_enough(
    tool: str, recht: str, rechten: dict[str, set[str]]
) -> None:
    rechten["nu"] = {recht}

    await approval_rights.require_approval_right_for_tool(None, None, tool)  # type: ignore[arg-type]


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(("tool", "recht"), TOOL_RECHTEN)
async def test_every_other_approval_right_is_refused(
    tool: str, recht: str, rechten: dict[str, set[str]]
) -> None:
    rechten["nu"] = set(approval_rights.ALLE_PROCESRECHTEN) - {recht}

    with pytest.raises(ApprovalRightRequiredError) as fout:
        await approval_rights.require_approval_right_for_tool(None, None, tool)  # type: ignore[arg-type]

    assert fout.value.status_code == 403


@pytest.mark.unit
@pytest.mark.asyncio
async def test_an_unknown_tool_is_refused_even_with_every_right(
    rechten: dict[str, set[str]],
) -> None:
    rechten["nu"] = set(approval_rights.ALLE_PROCESRECHTEN)

    with pytest.raises(ApprovalRightRequiredError) as fout:
        await approval_rights.require_approval_right_for_tool(None, None, "onbekende_tool")  # type: ignore[arg-type]

    assert fout.value.status_code == 403


@pytest.mark.unit
def test_the_table_covers_every_tool() -> None:
    assert {tool for tool, _ in TOOL_RECHTEN} == set(approval_rights.RECHT_PER_TOOL)


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("rechten_van_de_gebruiker", "verwachte_tools"),
    [
        ({"config:approve"}, ["serena__admin_config"]),
        (
            {"governance:approve"},
            [
                "delete_task",
                "gmail.send_email",
                "google-calendar.create_event",
                "local__send_email",
                "serena__delete_document",
                "slack.send_message",
            ],
        ),
        ({"receivables:approve"}, ["send_payment_reminder"]),
        ({"payables:approve"}, ["propose_payment_run", "propose_supplier_invoice"]),
        ({"hr:approve"}, ["schedule_training"]),
        (set(), []),
    ],
)
async def test_the_pending_list_only_covers_tools_the_user_may_decide(
    rechten_van_de_gebruiker: set[str],
    verwachte_tools: list[str],
    rechten: dict[str, set[str]],
) -> None:
    """De beheerder (alleen `config:approve`) ziet geen debiteurenbrief in de lijst."""
    rechten["nu"] = rechten_van_de_gebruiker

    tools = await approval_rights.tools_the_user_may_decide(None, None)  # type: ignore[arg-type]

    assert tools == verwachte_tools
