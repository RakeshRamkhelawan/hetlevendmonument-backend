"""Terminal dependencies -- schemas, constants and helper functions."""

import asyncio
import logging
import os
import shlex
import tempfile
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class TerminalRequest(BaseModel):
    """Request model for terminal command execution."""

    command: str


class TerminalResponse(BaseModel):
    """Response model for terminal command execution."""

    stdout: str
    stderr: str
    return_code: int


# Production guard configuration
_ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
_TERMINAL_ENABLED = os.getenv("FEATURE_FLAG_TERMINAL_ENABLED", "").lower() in (
    "1",
    "true",
    "yes",
)


#: Omgevingen waarin dit endpoint mag bestaan. Een TOELAATLIJST, geen blokkeerlijst
#: (ADR-036 OP-125).
#:
#: Hier stond `if env == "production"`. De vloot draait ook `staging`, `blue` en `green`, en
#: blue/green is een PRODUCTIETECHNIEK met echte data -- op die drie stond de deur dus open,
#: terwijl er `env` en `python` in de commandolijst zaten. Elke ingelogde gebruiker kon zo alle
#: secrets uitlezen.
#:
#: Dezelfde correctie als `redaction.py:314-320`, met dezelfde reden: een NIEUWE omgevingsnaam
#: hoort per constructie dicht te zijn, niet per ongeluk open.
TERMINAL_ALLOWED_ENVIRONMENTS: frozenset[str] = frozenset({"development", "test", "local"})


def _require_terminal_enabled() -> None:
    """Sta de terminal alleen toe in een ontwikkelomgeving (ADR-036 OP-125)."""
    env = os.getenv("ENVIRONMENT", "development").lower()
    enabled = os.getenv("FEATURE_FLAG_TERMINAL_ENABLED", "").lower() in ("1", "true", "yes")
    if env not in TERMINAL_ALLOWED_ENVIRONMENTS and not enabled:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Terminal endpoint is disabled in environment '{env}'. Only "
                f"{sorted(TERMINAL_ALLOWED_ENVIRONMENTS)} are allowed. Set "
                "FEATURE_FLAG_TERMINAL_ENABLED=true to override (not recommended)."
            ),
        )


#: Toegestane commando's. Bewust ZONDER alles wat de omgeving kan tonen of code kan draaien.
#:
#: Verwijderd op 2026-08-10 (ADR-036 OP-125), met de reden per groep:
#: - `env` printte letterlijk elke sleutel in het proces;
#: - `python`, `node`, `npm`, `pip` zijn volledige codeuitvoering, dus elke andere grens eromheen
#:   is decoratie;
#: - `curl` en `wget` maken uitgaand verkeer mogelijk, en dus exfiltratie van wat hier gelezen is.
ALLOWED_COMMANDS = {
    "ls",
    "dir",
    "cat",
    "head",
    "tail",
    "grep",
    "echo",
    "pwd",
    "whoami",
    "git",
    "date",
    "which",
    "uname",
}

#: Paden die de omgeving van een proces prijsgeven. `cat`/`head`/`tail`/`grep` mogen blijven --
#: ze zijn nuttig en onschuldig op gewone bestanden -- maar niet hierheen wijzen: dat is dezelfde
#: volledige dump als `env`, alleen langs een andere weg.
_FORBIDDEN_PATH_FRAGMENTS = ("/proc/", "/environ")

# Maximum output size (prevent memory issues)
MAX_OUTPUT_SIZE = 100 * 1024  # 100KB

# Command timeout
COMMAND_TIMEOUT = 30  # seconds


def is_command_allowed(command: str) -> bool:
    """Staat dit commando toe? Toetst het basiscommando EN de argumenten (ADR-036 OP-125)."""
    parts = shlex.split(command)
    if not parts:
        return False

    base_command = parts[0].split("/")[-1]  # Get basename
    if base_command not in ALLOWED_COMMANDS:
        return False

    # Ook de argumenten toetsen. `cat` is onschuldig, `cat /proc/self/environ` is een volledige
    # secretsdump -- het commando alleen zegt hier dus niet genoeg.
    return not any(
        fragment in argument for argument in parts[1:] for fragment in _FORBIDDEN_PATH_FRAGMENTS
    )


async def execute_command(command: str) -> tuple[str, str, int]:
    """
    Execute a command in a subprocess.
    Returns (stdout, stderr, return_code)
    """
    try:
        args = shlex.split(command)
        if not args:
            return "", "Empty command", -1

        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            # EXPLICIETE minimale omgeving (ADR-036 OP-125). Hier stond `**os.environ`, dus
            # elk toegestaan commando erfde de pseudonimiseringssleutel, DATABASE_URL,
            # JWT_SECRET_KEY, SECRET_KEY en de LLM-sleutel. Een toelaatlijst van commando's
            # helpt niet als het proces de secrets gewoon meekrijgt.
            env={
                "HOME": tempfile.gettempdir(),
                "PATH": "/usr/local/bin:/usr/bin:/bin",
                "LANG": os.environ.get("LANG", "C.UTF-8"),
            },
        )

        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=COMMAND_TIMEOUT)
        except TimeoutError:
            process.kill()
            return "", f"Command timed out after {COMMAND_TIMEOUT} seconds", -1

        stdout_str = stdout.decode("utf-8", errors="replace")[:MAX_OUTPUT_SIZE]
        stderr_str = stderr.decode("utf-8", errors="replace")[:MAX_OUTPUT_SIZE]

        return stdout_str, stderr_str, process.returncode or 0

    except OSError as exc:
        logger.error("Command execution OS error: %s", exc)
        return "", str(exc), -1
    except ValueError as exc:
        logger.error("Command execution value error: %s", exc)
        return "", str(exc), -1
