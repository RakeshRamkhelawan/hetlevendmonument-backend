"""De publicatiejob weigert items die niet zeggen of ze fictie zijn (metadata.fictief).

Lesmateriaal (fictief=false) en verhalen (fictief=true) staan naast elkaar op de site;
het label "Fictief verhaal" mag nooit stilzwijgend ontbreken.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]

_PAD = Path(__file__).resolve().parents[3] / "scripts" / "seed" / "publiceer_levend_monument.py"


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("publiceer_levend_monument", _PAD)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _bestand(tmp_path: Path, metadata: dict[str, object]) -> Path:
    pad = tmp_path / "items.json"
    pad.write_text(
        json.dumps({"items": [{"slug": "x", "title_nl": "X", "metadata": metadata}]}),
        encoding="utf-8",
    )
    return pad


@pytest.mark.parametrize("metadata", [{}, {"fictief": "ja"}, {"fictief": None}])
async def test_item_zonder_fictief_vlag_wordt_geweigerd(
    tmp_path: Path, metadata: dict[str, object]
) -> None:
    sessie = MagicMock()
    sessie.execute = AsyncMock()
    with pytest.raises(ValueError, match="fictief"):
        await _module()._verhalen(sessie, 3, 1, _bestand(tmp_path, metadata))
    sessie.execute.assert_not_awaited()


async def test_lesmateriaal_met_fictief_false_wordt_geaccepteerd(tmp_path: Path) -> None:
    sessie = MagicMock()
    bestaand = MagicMock()
    resultaat = MagicMock()
    resultaat.scalar_one_or_none = MagicMock(return_value=bestaand)
    sessie.execute = AsyncMock(return_value=resultaat)
    pad = tmp_path / "items.json"
    pad.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "slug": "les",
                        "title_nl": "Les",
                        "visibility": "edu",
                        "metadata": {"fictief": False},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    assert await _module()._verhalen(sessie, 3, 1, pad) == 0
    assert bestaand.metadata_ == {"fictief": False}
