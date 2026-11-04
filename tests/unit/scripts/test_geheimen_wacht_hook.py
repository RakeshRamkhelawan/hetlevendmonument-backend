"""De geheimenwacht weigert commando's die geheimen in de tool-uitvoer zetten.

WAAROM DIT BESTAAT
------------------
Een subagent draaide `docker compose config`; die ingevulde versie zette echte API-sleutels in
de tool-uitvoer, en daarmee bij het model. De sleutels zijn ingetrokken. Deze tests draaien het
ECHTE hookscript (`scripts/hooks/geheimen_wacht.py`) als subproces met de JSON-invoer die Claude
Code een PreToolUse-hook geeft, en toetsen op de exitcode: 2 is geweigerd, 0 is doorgelaten.
Geen enkel commando hieronder wordt uitgevoerd; alleen de hook leest de tekst.

Daarnaast: de hook moet in `.claude/settings.json` hangen op Bash EN PowerShell. Een hook die
in de repo staat maar niet is aangesloten draait nooit (CLAUDE.md, gemeten 2026-09-27).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
HOOK = REPO / "scripts" / "hooks" / "geheimen_wacht.py"
SETTINGS = REPO / ".claude" / "settings.json"

GEWEIGERD = [
    # docker compose config met ingevulde waarden
    "docker compose config",
    "docker-compose config",
    "docker compose -f docker-compose.yml config",
    "docker compose --env-file .env.production config",
    "cd infra && docker compose config",
    "docker compose ps; docker compose config | head -50",
    "(docker compose config)",
    "echo $(docker compose config)",
    'bash -c "docker compose config"',
    # docker inspect en env in een container
    "docker inspect backend",
    "docker container inspect sanskritisetu-api-1",
    "docker exec backend env",
    "docker exec -it backend printenv",
    "docker compose exec api env",
    "docker compose run --rm api printenv OPENAI_API_KEY",
    # .env lezen
    "cat .env",
    "cat ./config/.env.local",
    "type .env",
    "Get-Content .env",
    "Get-Content -Path .env.production",
    "gc .env",
    "more .env",
    "less .env.staging",
    "head -5 .env",
    "tail -n 3 .env",
    "grep API_KEY .env",
    "rg KEY .env.local",
    "findstr KEY .env",
    "Select-String -Pattern KEY -Path .env",
    "sed -n 1,5p .env",
    "awk -F= '{print $1}' .env",
    "cat .env*",
    "git status && cat .env",
    "ls | grep foo; tail .env",
    "while read l; do echo $l; done < .env",
    """python -c "print(open('.env').read())\"""",
    """python3 -c "import pathlib; print(pathlib.Path('.env.local').read_text())\"""",
    "sh -c 'cat .env'",
    "powershell -Command \"Get-Content .env\"",
    # losse omgevingsdumps
    "env",
    "printenv",
    "printenv OPENAI_API_KEY",
    "set",
    "export -p",
    "Get-ChildItem env:",
    "gci env:",
    "dir env:",
    "Get-ChildItem -Path Env:",
    "git log -1 | env",
    "sudo env",
]

TOEGESTAAN = [
    "docker compose ps",
    "docker compose config --no-interpolate",
    "docker compose config --services",
    "docker compose config --volumes",
    "docker compose config --images",
    "docker compose -f docker-compose.yml config --no-interpolate",
    "docker compose up -d api",
    "docker compose logs --tail 50 api",
    "docker ps --format '{{.Names}} {{.Status}}'",
    "docker image inspect python:3.12-slim",
    "cat .env.example",
    "cat .env.single-tenant.example",
    "Get-Content .env.example",
    "grep foo src/x.py",
    "rg TODO src",
    "git status",
    "echo $PATH",
    "echo $env:PATH",
    "set -euo pipefail",
    "env PYTHONPATH=src pytest tests/unit -q",
    "python -c \"import os; print(os.environ.get('PATH'))\"",
    "ls -la",
    "cat README.md && git diff --stat",
    "python scripts/push_gate.py status",
    "pytest tests/unit/scripts -q",
]


def _hook(commando: str, tool: str = "Bash") -> subprocess.CompletedProcess[str]:
    invoer = {"tool_name": tool, "tool_input": {"command": commando}}
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(invoer),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_de_tabellen_zijn_groot_genoeg() -> None:
    assert len(GEWEIGERD) >= 25
    assert len(TOEGESTAAN) >= 15


@pytest.mark.parametrize("commando", GEWEIGERD)
def test_geweigerd(commando: str) -> None:
    uit = _hook(commando)
    assert uit.returncode == 2, f"niet geweigerd: {commando!r}\n{uit.stderr}"
    assert "Geweigerd" in uit.stderr
    assert "uitvoer" in uit.stderr or "toont" in uit.stderr


@pytest.mark.parametrize("commando", TOEGESTAAN)
def test_toegestaan(commando: str) -> None:
    uit = _hook(commando)
    assert uit.returncode == 0, f"onterecht geweigerd: {commando!r}\n{uit.stderr}"


def test_ook_via_het_powershell_gereedschap() -> None:
    assert _hook("Get-Content .env", tool="PowerShell").returncode == 2
    assert _hook("Get-Content .env.example", tool="PowerShell").returncode == 0


def test_de_weigering_noemt_het_veilige_alternatief() -> None:
    assert "--no-interpolate" in _hook("docker compose config").stderr
    assert ".env.example" in _hook("cat .env").stderr


def test_kapotte_invoer_wordt_geweigerd() -> None:
    uit = subprocess.run(
        [sys.executable, str(HOOK)], input="geen json", capture_output=True, text=True, check=False
    )
    assert uit.returncode == 2


def test_de_hook_hangt_in_settings_op_bash_en_powershell() -> None:
    instellingen = json.loads(SETTINGS.read_text(encoding="utf-8"))
    gevonden: set[str] = set()
    for blok in instellingen["hooks"]["PreToolUse"]:
        for h in blok["hooks"]:
            if "scripts/hooks/geheimen_wacht.py" in h.get("command", ""):
                gevonden.update(blok["matcher"].split("|"))
    assert {"Bash", "PowerShell"} <= gevonden, f"geheimenwacht hangt op: {gevonden or 'niets'}"


def test_env_bestanden_staan_in_de_deny_regels() -> None:
    deny = set(json.loads(SETTINGS.read_text(encoding="utf-8"))["permissions"]["deny"])
    for regel in ("Read(**/.env)", "Read(**/.env.*)", "Edit(**/.env)", "Edit(**/.env.*)"):
        assert regel in deny
