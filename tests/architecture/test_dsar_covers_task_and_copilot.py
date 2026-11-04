"""Architecture guard -- DSAR dekt agentic_tasks + copilot-sessies (GDPR-A17-004).

Dag 7 (BE-A17-004) breidde de DSAR-service uit zodat een erasure/export ook de
`agentic_tasks` van de gebruiker en zijn copilot conversation-memory omvat -- anders
blijven persoonsgegevens achter na een art.-17-verzoek.

Deze guard faalt als die dekking verdwijnt: `delete_user_data` moet zowel de
agentic_tasks-delete als de copilot-sessie-clear aanroepen, en `export_user_data`
moet de agentic_tasks meenemen. Regressie-guard voor SP dag 7 BE-A17-004.
Alleen stdlib (pathlib, re) -- geen src-imports.
"""

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DSAR_SERVICE = _REPO_ROOT / "src" / "core" / "governance" / "dsar_service.py"


def _func_body(name: str) -> str:
    assert _DSAR_SERVICE.exists(), (
        f"Bestand niet gevonden: {_DSAR_SERVICE}. Pad incorrect of bestand verplaatst."
    )
    source = _DSAR_SERVICE.read_text(encoding="utf-8")
    match = re.search(
        rf"async def {name}\b.*?(?=\n    async def |\n    def |\nclass |\Z)",
        source,
        re.DOTALL,
    )
    assert match is not None, (
        f"BE-A17-004 [REGRESSION]: {name} niet gevonden in "
        f"{_DSAR_SERVICE.relative_to(_REPO_ROOT)}. De DSAR-service moet deze methode "
        "bevatten om taak-/copilot-data te dekken."
    )
    return match.group(0)


def test_delete_user_data_erases_agentic_tasks() -> None:
    """delete_user_data wist de agentic_tasks van de gebruiker. [BE-A17-004]"""
    body = _func_body("delete_user_data")
    assert "_delete_agentic_tasks" in body, (
        "BE-A17-004 [REGRESSION]: delete_user_data roept _delete_agentic_tasks niet meer aan. "
        "Een art.-17-erasure laat dan de agentic_tasks van de gebruiker achter. "
        "Fixt door SP dag 7 BE-A17-004."
    )


def test_delete_user_data_clears_copilot_sessions() -> None:
    """delete_user_data wist de copilot-sessies van de gebruiker. [BE-A17-004]"""
    body = _func_body("delete_user_data")
    assert "_clear_copilot_sessions" in body, (
        "BE-A17-004 [REGRESSION]: delete_user_data roept _clear_copilot_sessions niet meer aan. "
        "Copilot conversation-memory blijft dan achter na een art.-17-erasure. "
        "Fixt door SP dag 7 BE-A17-004."
    )


def test_export_user_data_includes_agentic_tasks() -> None:
    """export_user_data neemt de agentic_tasks van de gebruiker mee. [BE-A17-004]"""
    body = _func_body("export_user_data")
    assert "agentic_tasks" in body, (
        "BE-A17-004 [REGRESSION]: export_user_data neemt 'agentic_tasks' niet meer op in de "
        "data-export. Het art.-15/20-inzage/portabiliteitsrecht mist dan de taakdata. "
        "Fixt door SP dag 7 BE-A17-004."
    )
