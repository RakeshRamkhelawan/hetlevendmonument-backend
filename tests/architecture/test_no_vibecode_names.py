"""
Architecture test: geen vibe-code bestandsnamen in src/core/agents/.

Gebouwd als onderdeel van M&A readiness opschoning 2026-06-25.
Voorkomt dat nieuwe AI-sessies iteratieve namen als 'perfect_' of 'ultimate_'
opnieuw introduceren in Python-bestanden.
"""

from pathlib import Path

FORBIDDEN_PREFIXES = (
    "perfect_",
    "ultimate_",
    "enhanced_",
)

AGENTS_DIR = Path("src/core/agents")


def test_no_vibecode_prefixes_in_agents_dir():
    """Python-bestanden in src/core/agents/ mogen geen vibe-code prefixes hebben."""
    violations = [
        str(py_file)
        for py_file in AGENTS_DIR.rglob("*.py")
        if py_file.name.startswith(FORBIDDEN_PREFIXES)
    ]

    assert violations == [], (
        "Vibe-code bestandsnamen gevonden in {}:\n".format(AGENTS_DIR)
        + "\n".join("  - {}".format(v) for v in violations)
        + "\n\nHernoem naar semantische namen (zie M&A readiness plan 2026-06-25)."
    )
