"""`cd-production.yml` eist `MASTER_ENCRYPTION_KEY` en zet hem door naar elke app (brief 2026-10-23).

Gemeten 2026-10-23 op 5b7eef65: in `cd-staging.yml` stond de sleutel 13 keer, in
`docker-compose.prod.yml` 4 keer, in `cd-production.yml` NUL keer. Zonder de sleutel weigert de
applicatie (`HoofdsleutelOntbreekt`, `src/core/security/tenant_secret_encryption.py`): providerbeheer
en de AP-verbinding per klant zijn dan onbruikbaar. De workflow staat bewust uit; dit legt vast dat
hij er, zodra hij aangaat, niet pas bij de eerste klant achter komt.

**Benoemde verzameling (een mutatie per element, zie hieronder):** `ELEMENTEN` -- de preflight, het
zetten van het geheim in Key Vault, en per app (backend, worker, scheduler) het DEFINIEREN van het
geheim en het gebruik ervan in een env-var. De scheduler heeft twee vormen (update en create via
yaml); beide worden apart bewaakt, want de valkuil uit `cd-production.yml` zelf geldt hier: een
secretref zonder eigen definitie resolveert naar de LETTERLIJKE tekst `secretref:...`.

Commentaarregels tellen niet mee (`#`), zodat de naam in een toelichting de test niet groen houdt.

MUTATIEBEWIJS (2026-10-24, op een kopie van cd-production.yml; per element een run):
    elk element uit `ELEMENTEN` apart weghalen                       -> precies dat element ROOD
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCTIE = REPO_ROOT / ".github/workflows/cd-production.yml"

_ENV = r"MASTER_ENCRYPTION_KEY=secretref:master-encryption-key"

#: (job, stapnaam, label, patroon). Het patroon wordt gezocht in de `run:`-tekst zonder commentaar.
ELEMENTEN: tuple[tuple[str, str, str, str], ...] = (
    (
        "preflight",
        "Check required secrets",
        "preflight eist PROD_MASTER_ENCRYPTION_KEY",
        r'check_secret\s+"[A-Z_]+"\s+\\?\s*"\$\{GH_PROD_MASTER_ENCRYPTION_KEY\}"',
    ),
    (
        "deploy-production",
        "Push secrets to Key Vault",
        "Key Vault krijgt master-encryption-key",
        r"--name master-encryption-key\s*\\\s*\n\s*--value\s+\"\$\{GH_PROD_MASTER_ENCRYPTION_KEY\}\"",
    ),
    (
        "deploy-production",
        "Deploy backend",
        "backend definieert het geheim",
        r'"name":\s*"master-encryption-key"',
    ),
    ("deploy-production", "Deploy backend", "backend zet de env-var", _ENV),
    (
        "deploy-production",
        "Deploy worker",
        "worker definieert het geheim",
        r'"master-encryption-key=',
    ),
    ("deploy-production", "Deploy worker", "worker zet de env-var", _ENV),
    (
        "deploy-production",
        "Deploy scheduler (productie)",
        "scheduler (update) definieert het geheim",
        r'"master-encryption-key=',
    ),
    (
        "deploy-production",
        "Deploy scheduler (productie)",
        "scheduler (update) zet de env-var",
        _ENV,
    ),
    (
        "deploy-production",
        "Deploy scheduler (productie)",
        "scheduler (create) definieert het geheim",
        r"-\s+name:\s+master-encryption-key\s*\n\s+value:",
    ),
    (
        "deploy-production",
        "Deploy scheduler (productie)",
        "scheduler (create) zet de env-var",
        r"-\s+name:\s+MASTER_ENCRYPTION_KEY\s*\n\s+secretRef:\s+master-encryption-key",
    ),
)


def _zonder_commentaar(tekst: str) -> str:
    return "\n".join(r for r in tekst.splitlines() if not r.strip().startswith("#"))


def _stap(workflow: dict[str, Any], job: str, naam: str) -> str | None:
    for stap in workflow["jobs"].get(job, {}).get("steps", []):
        if stap.get("name") == naam:
            return _zonder_commentaar(str(stap.get("run", "")))
    return None


def ontbrekend(tekst: str) -> list[str]:
    workflow = yaml.safe_load(tekst)
    gemist: list[str] = []
    for job, stapnaam, label, patroon in ELEMENTEN:
        run = _stap(workflow, job, stapnaam)
        if run is None:
            gemist.append(f"{label}: de stap '{stapnaam}' bestaat niet meer")
        elif not re.search(patroon, run):
            gemist.append(label)
    return gemist


def test_de_productie_cd_zet_de_hoofdsleutel_overal_door() -> None:
    assert ontbrekend(PRODUCTIE.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize("element", ELEMENTEN, ids=[e[2] for e in ELEMENTEN])
def test_elk_element_is_apart_te_betrappen(element: tuple[str, str, str, str]) -> None:
    """Zonder dit is 'weiger alles' een geldige guard: elk element moet los rood kunnen worden."""
    job, stapnaam, label, _ = element
    voorbeeld = (
        f"jobs:\n  {job}:\n    steps:\n      - name: {stapnaam}\n        run: |\n"
        "          echo hallo\n"
    )

    assert label in ontbrekend(voorbeeld)


@pytest.mark.parametrize("stapnaam", ["Deploy worker", "Deploy scheduler (productie)"])
def test_de_hoofdsleutel_komt_uit_het_juiste_geheim(stapnaam: str) -> None:
    """`MASTER_KEY` in de env van de stap moet naar `PROD_MASTER_ENCRYPTION_KEY` wijzen."""
    workflow = yaml.safe_load(PRODUCTIE.read_text(encoding="utf-8"))
    stappen = workflow["jobs"]["deploy-production"]["steps"]
    stap = next(s for s in stappen if s.get("name") == stapnaam)

    assert stap["env"]["MASTER_KEY"] == "${{ secrets.PROD_MASTER_ENCRYPTION_KEY }}"


@pytest.mark.parametrize(
    ("job", "stapnaam"),
    [("preflight", "Check required secrets"), ("deploy-production", "Push secrets to Key Vault")],
)
def test_de_gh_variabele_wijst_naar_het_juiste_geheim(job: str, stapnaam: str) -> None:
    """Sinds 2026-10-24 komt de waarde via `env:`; de variabele moet naar het goede geheim wijzen."""
    workflow = yaml.safe_load(PRODUCTIE.read_text(encoding="utf-8"))
    stappen = workflow["jobs"][job]["steps"]
    stap = next(s for s in stappen if s.get("name") == stapnaam)

    assert (
        stap["env"]["GH_PROD_MASTER_ENCRYPTION_KEY"] == "${{ secrets.PROD_MASTER_ENCRYPTION_KEY }}"
    )


def test_de_naam_in_een_commentaarregel_telt_niet() -> None:
    voorbeeld = (
        "jobs:\n  deploy-production:\n    steps:\n      - name: Deploy backend\n        run: |\n"
        "          # MASTER_ENCRYPTION_KEY=secretref:master-encryption-key\n"
    )

    assert "backend zet de env-var" in ontbrekend(voorbeeld)
