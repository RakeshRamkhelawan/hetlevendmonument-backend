"""De nieuwe kolommen van Keten B dag 1: bestaan ze op het model, met het verwachte type?

Gemeten op het MODEL en op een echt weggeschreven rij (SQLite via `create_all`). De Alembic-
migratie zelf is hier NIET gemeten: de unit-database bouwt zijn tabellen uit het model.

Opstelling: root-conftest-autouse-fixtures (tenantfilter save/restore, TESTING=1); geen die
kolommen of defaults raakt. Geen conftest in `tests/unit/debiteuren/`.
"""

from __future__ import annotations

import pytest
from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.ext.asyncio import AsyncSession

import src.core.database.import_all_models  # noqa: F401
from src.core.models.outgoing_message_models import OutgoingMessage
from src.core.models.receivable_models import Receivable


def _kolom(model: type, naam: str):  # type: ignore[no-untyped-def]
    kolommen = model.__table__.columns  # type: ignore[attr-defined]
    assert naam in kolommen, (
        f"{model.__name__} mist kolom {naam!r}; heeft {sorted(kolommen.keys())}"
    )
    return kolommen[naam]


@pytest.mark.unit
class TestKolommenOpHetModel:
    @pytest.mark.parametrize(
        ("model", "naam"),
        [
            (Receivable, "herinnerd_op"),
            (Receivable, "betaald_op"),
            (OutgoingMessage, "verzonden_op"),
        ],
    )
    def test_tijdstempelkolom_is_nullable_en_kent_een_tijdzone(
        self, model: type, naam: str
    ) -> None:
        kolom = _kolom(model, naam)

        assert isinstance(kolom.type, DateTime) and kolom.type.timezone is True
        assert kolom.nullable is True

    def test_pogingen_is_een_verplichte_integer(self) -> None:
        kolom = _kolom(OutgoingMessage, "pogingen")

        assert isinstance(kolom.type, Integer) and kolom.nullable is False

    def test_foutreden_is_een_nullable_tekstkolom(self) -> None:
        kolom = _kolom(OutgoingMessage, "foutreden")

        assert isinstance(kolom.type, (Text, String)) and kolom.nullable is True


@pytest.mark.unit
@pytest.mark.asyncio
class TestStandaardwaarden:
    async def test_pogingen_staat_op_nul_voor_een_nieuw_bericht(
        self, db_session: AsyncSession
    ) -> None:
        from src.core.models.rbac_models import Tenant

        db_session.add(Tenant(id=1, name="T1", slug="deb-kol-1"))
        await db_session.flush()
        bericht = OutgoingMessage(
            tenant_id=1,
            channel="email",
            kind="herinnering",
            recipient="k@klant.example",
            subject="Onderwerp",
            body="Tekst",
            status="klaar",
        )
        db_session.add(bericht)
        await db_session.flush()
        await db_session.refresh(bericht)

        assert (bericht.pogingen, bericht.verzonden_op, bericht.foutreden) == (0, None, None)

    def test_de_bestaande_statussen_van_een_bericht_blijven_ongewijzigd(self) -> None:
        """Andere kant op: dag 1 raakt de CHECK van `outgoing_messages` niet."""
        from src.core.models.outgoing_message_models import OUTGOING_MESSAGE_STATUSES

        assert OUTGOING_MESSAGE_STATUSES == ("klaar", "verzonden", "mislukt")
