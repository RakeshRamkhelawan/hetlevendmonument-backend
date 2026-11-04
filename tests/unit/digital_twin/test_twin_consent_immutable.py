"""Unit tests: DigitalTwinService consent immutable log -- AUDIT-DB14b.

ADR-026: consent-wijzigingen worden opgeslagen als onveranderlijke log-records
(INSERT, nooit UPDATE). Twee update_consent() calls moeten twee records opleveren.

Rode tests voor aanvang implementatie. Alle tests falen zolang
src/core/api/v1/digital_twin/service.py niet bestaat.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock


def test_digital_twin_service_importable() -> None:
    """AUDIT-DB14b: DigitalTwinService moet importeerbaar zijn."""
    from src.core.api.v1.digital_twin.service import DigitalTwinService  # noqa: F401


def test_digital_twin_service_accepts_db_and_tenant_id() -> None:
    """AUDIT-DB14b: DigitalTwinService(db=..., tenant_id=...) moet werken."""
    from src.core.api.v1.digital_twin.service import DigitalTwinService

    mock_db = MagicMock()
    svc = DigitalTwinService(db=mock_db, tenant_id=1)
    assert svc.tenant_id == 1


@pytest.mark.asyncio
async def test_consent_update_inserts_new_record_not_update() -> None:
    """ADR-026: update_consent() moet een nieuw record aanmaken, nooit UPDATE.

    Twee opeenvolgende calls met verschillende settings moeten twee
    afzonderlijke db.add()-aanroepen opleveren.
    """
    from src.core.api.v1.digital_twin.service import DigitalTwinService, ConsentSettings

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.flush = AsyncMock()

    svc = DigitalTwinService(db=mock_db, tenant_id=1)
    svc._verify_agent_ownership = AsyncMock()  # IDOR-check bypassen in unit test
    await svc.update_consent(agent_id=10, consent=ConsentSettings(observe=True))
    await svc.update_consent(agent_id=10, consent=ConsentSettings(observe=False))

    assert mock_db.add.call_count == 2, (
        f"db.add() werd {mock_db.add.call_count}x aangeroepen, verwacht 2. "
        "Gebruik INSERT (db.add(new_record)) niet UPDATE."
    )


@pytest.mark.asyncio
async def test_consent_update_never_uses_db_execute_update() -> None:
    """ADR-026: update_consent() mag nooit db.execute(update(...)) aanroepen."""
    from src.core.api.v1.digital_twin.service import DigitalTwinService, ConsentSettings

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()

    svc = DigitalTwinService(db=mock_db, tenant_id=1)
    svc._verify_agent_ownership = AsyncMock()  # IDOR-check bypassen in unit test
    await svc.update_consent(agent_id=5, consent=ConsentSettings(observe=True))

    # ADR-026: consent MOET via db.add() (INSERT), nooit via db.execute(update(...))
    mock_db.add.assert_called_once()
    # Verifieer dat geen enkel execute-argument een SQLAlchemy Update is
    from sqlalchemy.sql.dml import Update as SqlAlchemyUpdate

    for call in mock_db.execute.call_args_list:
        stmt = call.args[0] if call.args else None
        assert not isinstance(stmt, SqlAlchemyUpdate), (
            "db.execute() werd aangeroepen met een UPDATE statement (ADR-026 schending)"
        )


def test_agent_twin_consent_event_model_importable() -> None:
    """AUDIT-DB14b (Optie B): AgentTwinConsentEvent SQLAlchemy model moet bestaan."""
    from src.core.models.digital_twin_models import AgentTwinConsentEvent  # noqa: F401
