import io
from unittest.mock import MagicMock

import pytest

from src.core.als.infrastructure.signal_bus import Signal, SignalTier
from src.core.services.storage.attachments import AttachmentService


def test_signal_serialization_with_attachments():
    attachment = {
        "id": "123",
        "filename": "receipt.jpg",
        "content_type": "image/jpeg",
        "storage_path": "data/uploads/1/123.jpg",
    }

    signal = Signal(
        tenant_id=1,
        source_agent_id="test",
        target_agent_ids=[],
        tier=SignalTier.REFLEX,
        payload={"msg": "check this"},
        attachments=[attachment],
    )

    json_data = signal.to_json()
    assert "receipt.jpg" in json_data

    new_signal = Signal.from_json(json_data)
    assert len(new_signal.attachments) == 1
    assert new_signal.attachments[0]["id"] == "123"


@pytest.mark.asyncio
async def test_attachment_tenant_isolation(tmp_path):
    service = AttachmentService(base_path=str(tmp_path))

    # Use real bytes for the mock file
    mock_file = MagicMock()
    mock_file.filename = "test.txt"
    mock_file.content_type = "text/plain"
    mock_file.file = io.BytesIO(b"dummy data")

    meta = await service.store_attachment(tenant_id=99, file=mock_file)

    assert "99" in meta["storage_path"]
    assert service.get_attachment_path(99, meta["storage_path"]) is not None
    assert service.get_attachment_path(88, meta["storage_path"]) is None
