"""GDPR-002: CVA gesprekken moeten aanwezig zijn in de portability export.

RED tests -- moeten falen tot GDPR-002 gefixed is.
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.unit
def test_gdpr_service_loads_cva_conversations() -> None:
    """gdpr_service.py moet CVA conversations laden in export_user_data().

    GDPR-002: Art. 20 portability -- CVA gesprekken zijn persoonsdata en moeten
    exporteerbaar zijn. Momenteel exporteert export_user_data() alleen learning data.
    Fix: voeg _load_cva_conversations() toe en neem resultaat op in export.data.
    """
    source = (_REPO_ROOT / "src/core/learning/gdpr_service.py").read_text(encoding="utf-8")
    assert "_load_cva_conversations" in source, (
        "gdpr_service.py heeft geen _load_cva_conversations() methode. "
        "GDPR-002: CVA gesprekken ontbreken in portability export. "
        "Fix: voeg _load_cva_conversations(tenant_id, user_id) toe die Conversation ORM laadt."
    )


@pytest.mark.unit
def test_gdpr_export_data_contains_conversations_key() -> None:
    """export_user_data() moet 'conversations' sleutel bevatten in data dict.

    GDPR-002: Art. 20 -- alle persoonsdata exporteerbaar, incl. CVA chat history.
    """
    source = (_REPO_ROOT / "src/core/learning/gdpr_service.py").read_text(encoding="utf-8")
    assert '"conversations"' in source or "'conversations'" in source, (
        "gdpr_service.py bevat geen 'conversations' sleutel in export data. "
        "GDPR-002: voeg conversations toe aan UserDataExport.data dict."
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_export_user_data_returns_conversations() -> None:
    """export_user_data() retourneert een 'conversations' sleutel in data.

    Runtime-test: verifieert dat de conversations daadwerkelijk in de export zitten.
    """
    from src.core.learning.gdpr_service import LearningGDPRService

    mock_session = AsyncMock()

    svc = LearningGDPRService(session=mock_session)

    with (
        patch.object(svc, "_load_observations", return_value=[]),
        patch.object(svc, "_load_user_patterns", return_value=[]),
        patch.object(svc, "_load_user_rules", return_value=[]),
        patch.object(svc, "_load_user_insights", return_value=[]),
        patch.object(svc, "_load_cva_conversations", return_value=[]),
        patch("src.core.learning.gdpr_service.log_learning_audit_event", new_callable=AsyncMock),
    ):
        mock_session.commit = AsyncMock()
        result = await svc.export_user_data(
            user_id="42",
            tenant_id=1,
            requested_by_user_id=1,
        )

    assert "conversations" in result.data, (
        "export_user_data retourneert geen 'conversations' sleutel. "
        "GDPR-002: CVA gesprekken moeten in de export staan."
    )
