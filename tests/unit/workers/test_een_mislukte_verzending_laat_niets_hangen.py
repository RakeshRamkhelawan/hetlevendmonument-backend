"""Een mislukte `.send()` geeft een duidelijke fout en laat niets eeuwig hangen (ADR-036 OP-13, brief 2026-10-21).

**Wat er mis was.** Sinds OP-13 gaat `.send()` naar een echte Redis en faalt hij zichtbaar als die weg is. Drie plekken
in `src/` vingen dat niet af en lieten een object achter dat nooit meer verder kwam:

- `documents/processing_router.py`: de status stond al op "processing" (gecommit) en bleef daar voor altijd;
- `copilot/api/audit_endpoints.py`: een auditrapport-opdracht stond op "pending" en bleef daar voor altijd;
- `copilot/api/contest_service.py`: het bezwaar was al opgeslagen en de klant kreeg alsnog een 500.

**Wat hier bewezen wordt.**
1. Documentverwerking: een mislukte verzending geeft 503 met een Nederlandse melding, de status gaat terug naar wat
   hij was, en de fout staat met `exc_info` in het log.
2. Auditrapport: 503, de opdracht staat op "failed" en blijft niet "pending".
3. Bezwaar: het bezwaar BLIJFT bewaard, er komt geen 500, en het antwoord zegt eerlijk dat de melding aan de
   beheerders niet is verstuurd.
Telkens ook de goede kant: lukt het versturen, dan verandert er niets aan het gedrag.

**Mutatiebewijs:** zie de oplevering van de brief (per element, beide richtingen).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.core.api.v1.documents import processing_router
from src.core.copilot.api import audit_endpoints, contest_service
from tests.helpers.limiet_request import echte_request

_REDIS_WEG = ConnectionError("Error 10061 connecting to localhost:6379")


def _db() -> MagicMock:
    db = MagicMock()
    db.commit = AsyncMock()
    db.execute = AsyncMock()
    db.get = AsyncMock()
    db.rollback = AsyncMock()
    return db


def _document(status: str = "ready") -> SimpleNamespace:
    return SimpleNamespace(id=5, status=status, updated_at=None)


async def _verwerk(doc: SimpleNamespace, send: MagicMock) -> Any:
    db = _db()
    resultaat = MagicMock()
    resultaat.scalar_one_or_none.return_value = doc
    db.execute.return_value = resultaat
    actor = MagicMock()
    actor.send = send
    gebruiker = SimpleNamespace(id=9, tenant_id=1)
    with (
        patch("src.workers.actors.process_document_async", actor),
        patch.object(processing_router.audit_service, "log_action", AsyncMock()),
    ):
        return await processing_router.process_document(
            doc_id=5, db=db, tenant_id=1, current_user=gebruiker
        )


class TestDocumentVerwerking:
    async def test_een_mislukte_verzending_geeft_een_503_met_een_nederlandse_melding(self) -> None:
        with pytest.raises(HTTPException) as fout:
            await _verwerk(_document(), MagicMock(side_effect=_REDIS_WEG))

        assert (fout.value.status_code, fout.value.detail["error"]["code"]) == (
            503,
            "WACHTRIJ_NIET_BESCHIKBAAR",
        )

    async def test_de_melding_is_nederlands_en_noemt_een_nieuwe_poging(self) -> None:
        with pytest.raises(HTTPException) as fout:
            await _verwerk(_document(), MagicMock(side_effect=_REDIS_WEG))

        assert "opnieuw" in fout.value.detail["error"]["message"]

    async def test_de_status_blijft_niet_op_processing_staan(self) -> None:
        doc = _document(status="ready")

        with pytest.raises(HTTPException):
            await _verwerk(doc, MagicMock(side_effect=_REDIS_WEG))

        assert doc.status == "ready"

    async def test_de_fout_staat_met_exc_info_in_het_log(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.ERROR):
            with pytest.raises(HTTPException):
                await _verwerk(_document(), MagicMock(side_effect=_REDIS_WEG))

        assert [
            r.exc_info is not None for r in caplog.records if "niet verstuurd" in r.getMessage()
        ] == [True]

    async def test_lukt_het_versturen_dan_blijft_de_status_processing(self) -> None:
        doc = _document(status="ready")

        antwoord = await _verwerk(doc, MagicMock())

        assert (doc.status, antwoord["data"]["status"]) == ("processing", "processing")


class TestAuditRapport:
    @staticmethod
    async def _start(send: MagicMock, job: SimpleNamespace) -> None:
        db = _db()
        db.get.return_value = job
        actor = MagicMock()
        actor.send = send
        with patch.object(audit_endpoints, "generate_audit_report", actor):
            await audit_endpoints._start_rapportopdracht(
                db=db,
                job_id=uuid.uuid4(),
                tenant_id=1,
                user_id=9,
                from_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
                to_date=datetime(2026, 2, 1, tzinfo=timezone.utc),
                format="json",
            )

    async def test_een_mislukte_verzending_geeft_een_503(self) -> None:
        job = SimpleNamespace(status="pending")

        with pytest.raises(HTTPException) as fout:
            await self._start(MagicMock(side_effect=_REDIS_WEG), job)

        assert fout.value.status_code == 503

    async def test_de_opdracht_staat_dan_op_failed_en_niet_op_pending(self) -> None:
        job = SimpleNamespace(status="pending")

        with pytest.raises(HTTPException):
            await self._start(MagicMock(side_effect=_REDIS_WEG), job)

        assert job.status == "failed"

    async def test_lukt_het_versturen_dan_blijft_de_opdracht_pending(self) -> None:
        job = SimpleNamespace(status="pending")

        await self._start(MagicMock(), job)

        assert job.status == "pending"


class TestBezwaar:
    @staticmethod
    async def _dien_in(send: MagicMock) -> tuple[MagicMock, Any]:
        db = _db()
        beslissing = SimpleNamespace(decision_id=uuid.uuid4(), tenant_id=1)
        gebruiker = SimpleNamespace(id=9)
        actor = MagicMock()
        actor.send = send
        with (
            patch.object(contest_service, "notify_tenant_admins_of_contest", actor),
            patch.object(contest_service.AuditService, "log_event", AsyncMock()),
        ):
            bezwaar = await contest_service.submit_contest(
                db=db,
                decision=beslissing,  # type: ignore[arg-type]
                user=gebruiker,  # type: ignore[arg-type]
                reason_category="factual_error",
                reason_text="Een voldoende lange reden voor het bezwaar.",
            )
        return db, bezwaar

    async def test_een_mislukte_melding_geeft_geen_fout_en_het_bezwaar_blijft_bewaard(self) -> None:
        db, bezwaar = await self._dien_in(MagicMock(side_effect=_REDIS_WEG))

        assert (bezwaar.status, db.commit.await_count >= 1) == ("pending", True)

    async def test_het_antwoord_zegt_eerlijk_dat_de_melding_mislukt_is(self) -> None:
        _, bezwaar = await self._dien_in(MagicMock(side_effect=_REDIS_WEG))

        assert bezwaar.admin_notification == "mislukt"

    async def test_de_fout_staat_met_exc_info_in_het_log(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.ERROR):
            await self._dien_in(MagicMock(side_effect=_REDIS_WEG))

        assert [
            r.exc_info is not None for r in caplog.records if "beheerders" in r.getMessage()
        ] == [True]

    async def test_lukt_het_versturen_dan_is_de_melding_verzonden(self) -> None:
        _, bezwaar = await self._dien_in(MagicMock())

        assert bezwaar.admin_notification == "verzonden"

    async def test_het_eindpunt_geeft_de_status_van_de_melding_door(self) -> None:
        beslissing = SimpleNamespace(decision_id=uuid.uuid4(), tenant_id=1, user_id=9)
        resultaat = MagicMock()
        resultaat.scalar_one_or_none.return_value = beslissing
        db = _db()
        db.execute.return_value = resultaat
        gebruiker = SimpleNamespace(id=9, roles=["user"], is_superuser=False, tenant_id=1)
        voorstel = SimpleNamespace(
            contest_id=uuid.uuid4(),
            status="pending",
            submitted_at=datetime.now(timezone.utc),
            admin_notification="mislukt",
        )
        with patch.object(audit_endpoints, "submit_contest", AsyncMock(return_value=voorstel)):
            antwoord = await audit_endpoints.contest_decision(
                request=echte_request(),
                decision_id=beslissing.decision_id,
                body=audit_endpoints.ContestRequest(
                    reason_category="factual_error",
                    reason_text="Een voldoende lange reden voor het bezwaar.",
                ),
                current_user=gebruiker,  # type: ignore[arg-type]
                db=db,
                tenant_id=1,
            )

        assert (antwoord.admin_notification, "beheerders" in (antwoord.message or "")) == (
            "mislukt",
            True,
        )
