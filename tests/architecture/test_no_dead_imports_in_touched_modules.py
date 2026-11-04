"""Dode imports blijven onzichtbaar omdat `F401` projectbreed uitstaat (ADR-036 OP-86).

**Hoe dit gevonden is.** Na het verwijderen van het tokenendpoint (OP-61) bleven tien imports in
`tool_broker/router.py` achter die nergens meer werden gebruikt -- `os`, `jwt_handler`,
`get_settings`, `TokenRequest`, `TokenResponse` en nog vijf. De blinde code-review vond ze met
`ruff check --select F401`. De normale poort zag ze niet: `F401` staat in `pyproject.toml`
projectbreed genegeerd.

**Waarom dat erger is dan rommel.** Een dode import naar `jwt_handler` in een bestand waar net een
authenticatie-omzeiling uit is gehaald, leest als "hier gebeurt nog iets met tokens". En de imports
`ToolHITLApproval`/`ToolHITLRejection` suggereerden dat dit bestand nog steeds het HITL-schrijfpad
is, terwijl dat sinds OP-37 in een eigen router zit. Verkeerde signalen op precies de plek waar
iemand naar veiligheid zoekt.

**Waarom een LIJST en geen projectbrede regel.** `F401` staat om een reden uit: `__init__.py`- en
facade-bestanden exporteren bewust namen die ze zelf niet gebruiken, en er zijn honderden van die
bestanden. Die uitzondering hier omdraaien zou een enorme, ongerelateerde opruimactie zijn. Deze
guard bewaakt daarom de modules die deze sprint heeft aangeraakt en waar dode imports een
inhoudelijk verkeerd signaal geven -- een gedateerde lijst die kan groeien wanneer dat nuttig is.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Modules waar een dode import een verkeerd signaal geeft over wat er gebeurt.
#:
#: Bewust geen `__init__.py` of `*/dependencies.py`: die exporteren met opzet namen die ze zelf
#: niet gebruiken, en dat is het patroon dat ADR-033 voorschrijft.
WATCHED = (
    "src/core/tool_broker/router.py",
    "src/core/tool_broker/service.py",
    "src/core/tool_broker/hitl_repository.py",
    "src/core/tool_broker/hitl_store.py",
    "src/core/tool_broker/hitl_notifier.py",
    "src/core/tool_broker/redaction.py",
    "src/core/api/v1/tool_broker/hitl_router.py",
    "src/core/api/v1/gatekeeper/gatekeeper_hitl_router.py",
    "src/core/governance/retention_cleanup.py",
    "src/workers/scheduler.py",
)


def test_the_watched_modules_still_exist() -> None:
    """Vangnet: een hernoemd bestand mag niet stil uit de bewaking vallen."""
    ontbreekt = [name for name in WATCHED if not (REPO_ROOT / name).exists()]

    assert not ontbreekt, (
        f"Deze bewaakte modules bestaan niet meer: {ontbreekt}. Hernoemd of verwijderd? Werk de "
        "lijst bij; anders bewaakt deze guard stilletjes minder dan hij belooft."
    )


def test_no_dead_imports_in_the_watched_modules() -> None:
    """`F401` gericht aanzetten voor de modules waar het uitmaakt."""
    result = subprocess.run(
        [
            "python",
            "-m",
            "ruff",
            "check",
            "--select",
            "F401",
            "--output-format=concise",
            *WATCHED,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    # De returncode MOET kloppen (ADR-036 OP-97). Deze guard negeerde hem en filterde alleen op
    # "F401" in stdout. Gemeten: een onbekende vlag geeft rc=2 met LEGE stdout -- en dan meldde de
    # guard groen. Een hernoemde optie in een latere ruff, een ontbrekende ruff of een parse-fout
    # liet dus stil door. 0 = schoon, 1 = overtredingen gevonden; al het andere is kapot.
    assert result.returncode in (0, 1), (
        f"ruff eindigde met returncode {result.returncode} in plaats van 0 of 1. Deze guard kan dan "
        f"niets vaststellen en hoort niet groen te melden.\nstderr:\n{result.stderr}"
    )

    meldingen = [line for line in result.stdout.split("\n") if "F401" in line]

    assert not meldingen, (
        "Dode imports gevonden in modules waar dat een verkeerd signaal geeft:\n"
        + "\n".join(meldingen)
        + "\n\nDe normale poort ziet deze niet: `F401` staat projectbreed genegeerd in "
        "pyproject.toml. Ruim ze op met `python -m ruff check --select F401 --fix <bestand>`."
    )
