"""De staging-uitrol hangt af van een job die `scripts/pre-deploy-check.sh` draait (OP-227).

Gemeten 2026-10-23 op 5b7eef65: `scripts/pre-deploy-check.sh` werd alleen in `cd-production.yml`
aangeroepen (een workflow die op een versietag draait en bewust uit staat). `cd-staging.yml`
riep hem niet aan, dus de uitrolcontrole -- compose-structuur, Docker-bestanden in git, de
migratieketen op een echte database -- draaide bij geen enkele uitrol die vandaag kan plaatsvinden.

**Wat deze test bewaakt.** Elke job die het script echt AANROEPT (een `run:`-regel die geen
commentaar is) en waar `deploy-staging` van afhangt via `needs`, direct of via andere jobs. Een
job die het script alleen noemt in commentaar, of die mag falen (`continue-on-error`), of die
overgeslagen kan worden (`if:`), telt niet: dan staat de uitrol er niet echt van af.

Benoemde verzameling: aanroep, needs, continue-on-error, if. Een mutatie per element.

MUTATIEBEWIJS (2026-10-24, op een kopie van cd-staging.yml):
    de `run:`-regel met het script weghalen                      -> ROOD
    het script alleen nog in een `#`-regel noemen                -> ROOD
    `pre-deploy-check` uit `needs` van `deploy-staging` halen    -> ROOD
    `continue-on-error: true` op de job                          -> ROOD
    `if: github.ref == 'refs/heads/nooit'` op de job             -> ROOD
    `bash scripts/pre-deploy-check.sh || true`                   -> ROOD
    `echo scripts/pre-deploy-check.sh`                           -> ROOD
    `continue-on-error` of `if` op de STAP                       -> ROOD
    legitiem: de job anders noemen                               -> GROEN
    legitiem: de afhankelijkheid via een tussenliggende job      -> GROEN
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
STAGING = REPO_ROOT / ".github/workflows/cd-staging.yml"
SCRIPT = "scripts/pre-deploy-check.sh"
UITROL_JOB = "deploy-staging"
_CHECK = "jobs:\n  check:\n{kop}    steps:\n      - run: bash scripts/pre-deploy-check.sh\n"
_UITROL = "  deploy-staging:\n    needs: {needs}\n    steps: []\n"


def _jobs(tekst: str) -> dict[str, dict[str, Any]]:
    return yaml.safe_load(tekst)["jobs"]


def _needs(job: dict[str, Any]) -> list[str]:
    needs = job.get("needs", [])
    return [needs] if isinstance(needs, str) else list(needs)


#: Een echte aanroep: alleen `bash scripts/pre-deploy-check.sh` (of `sh`), zonder `|| true`, `;` of
#: andere staart. Een regel die de naam noemt (`echo ...`) of de uitslag wegslikt telt niet.
_AANROEP = re.compile(r"^(bash|sh)\s+scripts/pre-deploy-check\.sh\s*$")


def _roept_het_script_aan(job: dict[str, Any]) -> bool:
    for stap in job.get("steps", []):
        # Een stap die mag falen of overgeslagen kan worden, blokkeert niets.
        if stap.get("continue-on-error") or "if" in stap:
            continue
        for regel in str(stap.get("run", "")).splitlines():
            if _AANROEP.match(regel.strip()):
                return True
    return False


def _kan_niet_blokkeren(job: dict[str, Any]) -> bool:
    return bool(job.get("continue-on-error")) or "if" in job


def _afhankelijkheden(jobs: dict[str, dict[str, Any]], start: str) -> set[str]:
    gezien: set[str] = set()
    todo = list(_needs(jobs[start]))
    while todo:
        naam = todo.pop()
        if naam in gezien or naam not in jobs:
            continue
        gezien.add(naam)
        todo.extend(_needs(jobs[naam]))
    return gezien


def uitrolcontrole_problemen(tekst: str) -> list[str]:
    jobs = _jobs(tekst)
    if UITROL_JOB not in jobs:
        return [f"de job {UITROL_JOB} bestaat niet meer"]
    aanroepers = [naam for naam, job in jobs.items() if _roept_het_script_aan(job)]
    if not aanroepers:
        return [f"geen enkele job in cd-staging.yml roept {SCRIPT} aan"]
    afhankelijk = _afhankelijkheden(jobs, UITROL_JOB)
    bindend = [n for n in aanroepers if n in afhankelijk and not _kan_niet_blokkeren(jobs[n])]
    if not bindend:
        return [
            f"{UITROL_JOB} hangt van geen enkele job af die {SCRIPT} draait en echt kan "
            f"blokkeren (aanroepers: {aanroepers}; continue-on-error of if telt niet)"
        ]
    return []


@pytest.fixture
def staging_tekst() -> str:
    return STAGING.read_text(encoding="utf-8")


def test_de_staging_uitrol_hangt_af_van_een_job_die_de_uitrolcontrole_draait(
    staging_tekst: str,
) -> None:
    assert uitrolcontrole_problemen(staging_tekst) == []


def test_de_uitrolcontrole_wordt_echt_aangeroepen_en_niet_alleen_genoemd() -> None:
    tekst = (
        "jobs:\n  check:\n    steps:\n      - run: |\n"
        "          # bash scripts/pre-deploy-check.sh\n          echo hallo\n"
    ) + _UITROL.format(needs="[check]")

    assert uitrolcontrole_problemen(tekst) == [
        "geen enkele job in cd-staging.yml roept scripts/pre-deploy-check.sh aan"
    ]


@pytest.mark.parametrize(
    "stap",
    [
        "      - run: bash scripts/pre-deploy-check.sh || true\n",
        "      - run: echo scripts/pre-deploy-check.sh\n",
        "      - continue-on-error: true\n        run: bash scripts/pre-deploy-check.sh\n",
        "      - if: always() && false\n        run: bash scripts/pre-deploy-check.sh\n",
    ],
    ids=["or-true", "echo", "stap-continue-on-error", "stap-if"],
)
def test_een_stap_die_de_uitslag_wegslikt_of_niets_draait_telt_niet(stap: str) -> None:
    tekst = "jobs:\n  check:\n    steps:\n" + stap + _UITROL.format(needs="[check]")

    assert len(uitrolcontrole_problemen(tekst)) == 1


def test_een_job_die_mag_falen_telt_niet() -> None:
    tekst = _CHECK.format(kop="    continue-on-error: true\n") + _UITROL.format(needs="[check]")

    assert len(uitrolcontrole_problemen(tekst)) == 1


def test_een_job_die_overgeslagen_kan_worden_telt_niet() -> None:
    kop = "    if: github.ref == 'refs/heads/nooit'\n"
    tekst = _CHECK.format(kop=kop) + _UITROL.format(needs="[check]")

    assert len(uitrolcontrole_problemen(tekst)) == 1


def test_een_uitrol_die_niet_van_de_job_afhangt_wordt_betrapt() -> None:
    tekst = _CHECK.format(kop="") + _UITROL.format(needs="[]")

    assert len(uitrolcontrole_problemen(tekst)) == 1


def test_een_andere_jobnaam_is_goed() -> None:
    tekst = (_CHECK.format(kop="")).replace("  check:", "  uitrolcontrole:") + _UITROL.format(
        needs="uitrolcontrole"
    )

    assert uitrolcontrole_problemen(tekst) == []


def test_afhankelijkheid_via_een_tussenliggende_job_is_goed() -> None:
    tekst = (
        _CHECK.format(kop="")
        + "  build:\n    needs: [check]\n    steps: []\n"
        + _UITROL.format(needs="[build]")
    )

    assert uitrolcontrole_problemen(tekst) == []
