"""Het toolresultaat in de council-auditketen wordt met een sleutel gehasht (ADR-036 OP-39).

`CouncilAuditWriter.bind_execution_result` hashte `result_data` met kaal, ongesleuteld
SHA-256. Voor een resultaat met weinig entropie (een boolean, een status, een klein getal) is
dat een bevestigingsorakel voor wie de rij kan lezen: hij kan kandidaten narekenen zonder de
sleutel te kennen. Dit dekken de eigenschappen die kaal SHA-256 niet had: hetzelfde resultaat
geeft in twee tenants een andere hash, en de hash is niet terug te rekenen tot de kale
`hashlib.sha256(canonical).hexdigest()` van de oude implementatie.

Op GEDRAGSNIVEAU: via `bind_execution_result` en de UPDATE die het uitvoert, niet via
`redaction.py` rechtstreeks -- dezelfde reden als `test_pseudonymisation_leaks.py`.
"""

from __future__ import annotations

import hashlib
import json
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.copilot.council.audit_writer import CouncilAuditWriter


def _make_writer(db: AsyncMock) -> CouncilAuditWriter:
    @asynccontextmanager
    async def factory() -> AsyncIterator[AsyncMock]:
        yield db

    return CouncilAuditWriter(factory)


def _bound_result_hash(db: AsyncMock) -> str | None:
    assert db.execute.await_args is not None, "er is geen UPDATE uitgevoerd"
    statement = db.execute.await_args[0][0]
    params = statement.compile().params
    assert "result_hash" in params, f"result_hash staat niet in de UPDATE: {params}"
    return params["result_hash"]


@pytest.mark.unit
@pytest.mark.asyncio
class TestTheHashIsTenantScoped:
    async def test_the_same_result_gives_a_different_hash_in_two_tenants(self) -> None:
        """Kaal SHA-256 gaf voor hetzelfde resultaat in elke tenant dezelfde hash -- een
        bevestigingsorakel dat over de tenantgrens werkt. Gesleuteld en tenant-gescheiden hoort
        dat te breken.
        """
        result_data: dict[str, object] = {"status": True}
        decision_id = uuid4()

        db_one = AsyncMock()
        await _make_writer(db_one).bind_execution_result(
            decision_id=decision_id, tenant_id=1, result_data=result_data
        )

        db_two = AsyncMock()
        await _make_writer(db_two).bind_execution_result(
            decision_id=decision_id, tenant_id=2, result_data=result_data
        )

        hash_one = _bound_result_hash(db_one)
        hash_two = _bound_result_hash(db_two)
        assert hash_one != hash_two, (
            "Dezelfde resultaatwaarde geeft in tenant 1 en tenant 2 dezelfde hash. Wie de "
            "auditrij kan lezen, kan dan kandidaten narekenen zonder de sleutel te kennen, en "
            "dat werkt bovendien over de tenantgrens."
        )


@pytest.mark.unit
@pytest.mark.asyncio
class TestTheHashIsKeyed:
    async def test_the_hash_is_not_the_bare_unkeyed_sha256(self) -> None:
        """De oude implementatie was `hashlib.sha256(canonical).hexdigest()` -- geen sleutel.

        Een lezer met alleen leestoegang tot de tabel kon dan voor een kandidaatwaarde dezelfde
        berekening maken en vergelijken (het bevestigingsorakel). Een gesleutelde HMAC kan dat
        niet zonder de sleutel.
        """
        result_data: dict[str, object] = {"count": 3}
        canonical = json.dumps(result_data, sort_keys=True, separators=(",", ":"))
        bare_sha256 = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

        db = AsyncMock()
        await _make_writer(db).bind_execution_result(
            decision_id=uuid4(), tenant_id=1, result_data=result_data
        )

        assert _bound_result_hash(db) != bare_sha256, (
            "result_hash is nog steeds de kale, ongesleutelde SHA-256 -- het "
            "bevestigingsorakel dat OP-39 sluit staat dan nog open."
        )


@pytest.mark.unit
@pytest.mark.asyncio
class TestAMissingKeyDegradesWithoutMaskingTheCaller:
    async def test_a_missing_pseudonymisation_key_writes_none_instead_of_raising(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`bind_execution_result` wordt ook aangeroepen vanuit een `except`-tak in
        `service.py` (het FALEN-pad van de aangeroepen tool). Zou deze methode zelf een
        RuntimeError gooien bij een ontbrekende sleutel, dan overschaduwt die de ORIGINELE fout
        van de aanroeper -- exact de OP-29-les, hier toegepast op hetzelfde soort aanroepplek.
        `result_hash` is nullable, dus `None` is de veilige, best-effort uitkomst.
        """

        def _no_key() -> bytes:
            raise RuntimeError("TOOL_PAYLOAD_PSEUDONYM_KEY ontbreekt")

        monkeypatch.setattr("src.core.tool_broker.redaction.pseudonymisation_key", _no_key)

        db = AsyncMock()
        writer = _make_writer(db)

        await writer.bind_execution_result(
            decision_id=uuid4(), tenant_id=1, result_data={"status": True}
        )

        assert _bound_result_hash(db) is None, (
            "Bij een ontbrekende sleutel hoort result_hash None te zijn, niet een geraiste "
            "exception die de aanroeper (mogelijk een except-tak die al een echte fout "
            "afhandelt) zou overschaduwen."
        )
