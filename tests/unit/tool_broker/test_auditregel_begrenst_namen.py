"""S3 (Gate 2): `tool_name` en `agent_id` zijn varchar(255); een langere waarde gaf geen regel.

De naam van een tool komt uit een taalmodel en `agent_id` uit de aanroeper. Een naam van 300 tekens
gaf `StringDataRightTruncationError` bij de insert, en dan ontstond er geen auditregel (best effort
slikte de fout). De repository begrenst nu BEIDE op een plek, voor het hashen, zodat de hash over
precies de opgeslagen waarde gaat. Een te lange naam wordt een korte voorvoegsel plus een digest van
de hele naam: twee verschillende lange namen blijven daardoor onderscheidbaar.
"""

from __future__ import annotations

import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.tool_broker import audit_repository as repo_module
from src.core.tool_broker.audit_repository import (
    KOLOM_LENGTE,
    ToolAuditRepository,
    begrens_kolomwaarde,
)


def _repository() -> tuple[ToolAuditRepository, list[object]]:
    db = MagicMock()
    resultaat = MagicMock()
    resultaat.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=resultaat)
    toegevoegd: list[object] = []
    db.add = toegevoegd.append
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return ToolAuditRepository(db, 7), toegevoegd


async def _schrijf(naam: str, agent: str) -> tuple[object, dict[str, object]]:
    repo, toegevoegd = _repository()
    gehasht: dict[str, object] = {}
    echte_hash = repo_module.compute_audit_hash

    def _spion(**kwargs: object) -> str:
        gehasht.update(kwargs)
        return echte_hash(**kwargs)  # type: ignore[arg-type]

    with patch.object(repo_module, "compute_audit_hash", _spion):
        await repo.log_execution(
            agent_id=agent,
            tool_name=naam,
            risk_level="low",
            tool_input={},
            tool_output=None,
            status="success",
            duration_seconds=0.0,
        )
    assert len(toegevoegd) == 1
    return toegevoegd[0], gehasht


@pytest.mark.unit
@pytest.mark.asyncio
class TestLangeNamenGevenTochEenRegel:
    async def test_een_toolnaam_van_300_tekens_past_in_de_kolom(self) -> None:
        regel, _ = await _schrijf("local__" + "x" * 293, "agent-1")
        assert len(regel.tool_name) <= KOLOM_LENGTE  # type: ignore[attr-defined]

    async def test_een_agent_id_van_300_tekens_past_in_de_kolom(self) -> None:
        regel, _ = await _schrijf("test__echo", "a" * 300)
        assert len(regel.agent_id) <= KOLOM_LENGTE  # type: ignore[attr-defined]

    async def test_de_hash_gaat_over_de_opgeslagen_waarde_niet_over_het_origineel(self) -> None:
        regel, gehasht = await _schrijf("local__" + "x" * 293, "a" * 300)
        assert gehasht["tool_name"] == regel.tool_name  # type: ignore[attr-defined]
        assert gehasht["agent_id"] == regel.agent_id  # type: ignore[attr-defined]

    async def test_een_korte_naam_blijft_ongewijzigd(self) -> None:
        regel, gehasht = await _schrijf("test__echo", "agent-1")
        assert (regel.tool_name, regel.agent_id) == ("test__echo", "agent-1")  # type: ignore[attr-defined]
        assert gehasht["tool_name"] == "test__echo"


@pytest.mark.unit
class TestBegrensKolomwaarde:
    def test_precies_255_blijft_ongewijzigd(self) -> None:
        assert begrens_kolomwaarde("x" * 255) == "x" * 255

    def test_256_wordt_begrensd_op_255(self) -> None:
        assert len(begrens_kolomwaarde("x" * 256)) == 255

    def test_twee_lange_namen_met_dezelfde_kop_blijven_onderscheidbaar(self) -> None:
        a = begrens_kolomwaarde("x" * 300 + "a")
        b = begrens_kolomwaarde("x" * 300 + "b")
        assert a != b

    def test_het_resultaat_is_deterministisch_en_bevat_de_digest_van_het_geheel(self) -> None:
        naam = "y" * 400
        uitkomst = begrens_kolomwaarde(naam)
        assert uitkomst == begrens_kolomwaarde(naam)
        assert uitkomst.endswith(hashlib.sha256(naam.encode("utf-8")).hexdigest()[:64])

    def test_tekens_buiten_ascii_tellen_als_tekens_niet_als_bytes(self) -> None:
        # varchar(255) telt tekens, niet bytes.
        assert begrens_kolomwaarde("\u00e9" * 255) == "\u00e9" * 255
