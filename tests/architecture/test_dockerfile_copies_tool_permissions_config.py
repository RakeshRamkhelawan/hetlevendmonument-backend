"""Elke runtime-stage die src/ kopieert moet ook config/ naar /app/config/ kopieren.

WHY: permission_manager.py leest config/tool_permissions.yml relatief aan de
broncode (/app/config/ in de image). Ontbreekt dat bestand, dan valt de broker
terug op alles-weigeren en ontstaat nooit een HITL-ticket (meetlat scenario 5).
"""

from __future__ import annotations

import re
from pathlib import Path

DOCKERFILE = Path(__file__).resolve().parents[2] / "Dockerfile"

_COPY_SRC = re.compile(r"^COPY\b.*\bsrc/\s+\./src/", re.MULTILINE)
_COPY_CONFIG = re.compile(
    r"^COPY\b.*\bconfig/(tool_permissions\.yml)?\s+(\./config/|/app/config/)",
    re.MULTILINE,
)


def _stages() -> list[tuple[str, str]]:
    text = DOCKERFILE.read_text(encoding="utf-8")
    parts = re.split(r"^FROM\s+\S+\s+AS\s+(\S+)\s*$", text, flags=re.MULTILINE)
    return list(zip(parts[1::2], parts[2::2], strict=True))


def test_runtime_stages_copy_config_dir() -> None:
    stages = _stages()
    src_stages = [name for name, body in stages if _COPY_SRC.search(body)]
    assert src_stages, "geen stage gevonden die src/ kopieert; parser klopt niet meer"
    missing = [
        name for name, body in stages if _COPY_SRC.search(body) and not _COPY_CONFIG.search(body)
    ]
    assert not missing, f"stages kopieren src/ maar niet config/ naar /app/config/: {missing}"


def test_dockerignore_whitelists_config_dir() -> None:
    """.dockerignore sluit alles uit (`*`) en whitelist daarna; config/ moet erbij.

    Zonder deze regel faalt `COPY config/` met '"/config": not found' (gemeten 2026-10-04).
    """
    lines = [
        ln.split("#", 1)[0].strip()
        for ln in (DOCKERFILE.parent / ".dockerignore").read_text(encoding="utf-8").splitlines()
    ]
    if "*" not in lines:
        return
    after_star = lines[len(lines) - 1 - lines[::-1].index("*") :]
    assert {"!config/", "!config", "!config/tool_permissions.yml"} & set(after_star), (
        ".dockerignore sluit config/ uit; voeg '!config/' toe na de '*'-regel"
    )
