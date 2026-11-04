"""PreToolUse-hook (Bash en PowerShell): weigert commando's die geheimen in de tool-uitvoer zetten.

WAAROM DIT BESTAAT
------------------
Een subagent draaide `docker compose config`. Die ingevulde versie toonde echte API-sleutels uit
`.env` in de uitvoer van de tool, en alles wat in die uitvoer staat gaat naar het model. Rakesh
heeft de sleutels ingetrokken. Een regel in CLAUDE.md alleen houdt dit niet tegen; deze hook wel.

WAT HIJ WEIGERT (exitcode 2, reden op stderr, met het veilige alternatief)
-----------------------------------------------------------------------
- `docker compose config` / `docker-compose config` zonder `--no-interpolate`, `--services`,
  `--volumes`, `--images` of `-q/--quiet`
- `docker inspect` en `docker container inspect`
- `docker exec ... env|printenv` en `docker compose exec|run ... env|printenv`
- een .env-bestand lezen (`.env`, `.env.*`; NIET `.env.example` en `.env.*.example`) met cat, type,
  Get-Content, gc, more, less, head, tail, grep, rg, findstr, Select-String, sed, awk (en
  verwanten), met een invoer-redirect `< .env`, of met `python -c "...open('.env')..."`
- losse `env`, `printenv`, `set` zonder argumenten, `export`/`export -p`,
  `Get-ChildItem env:`, `gci env:`, `dir env:`, `ls env:`

HOE HIJ LEEST
-------------
Het commando wordt gesplitst op `&&`, `||`, `;`, `|`, `&`, regeleinden, `$(`, backticks en
haakjes, zodat elk deel afzonderlijk wordt getoetst. `bash -c "..."`, `sh -c`, `pwsh -Command`,
`powershell -c` en `cmd /c` worden recursief gelezen; `sudo`, `env VAR=x`, `command` en `exec`
voor een commando worden overgeslagen.

BEKENDE GRENZEN (zie ook het rapport bij de commit die dit invoerde)
-------------------------------------------------------------------
Dit is een tekstfilter, geen sandbox. Wie een geheim WIL tonen komt er omheen: via een
tussenkopie (`cp .env x && cat x`), via variabele-indirectie (`f=.env; cat $f`), via een script
in een bestand, of via een programma dat zelf .env laadt en zijn configuratie logt. Recursief
zoeken (`grep -r KEY .`) leest .env mee en wordt niet geweigerd.
"""

from __future__ import annotations

import json
import re
import shlex
import sys

# Programma's die de inhoud van een bestand naar de uitvoer brengen.
LEZERS = frozenset(
    {
        "cat", "type", "get-content", "gc", "more", "less", "head", "tail", "grep", "egrep",
        "fgrep", "rg", "findstr", "select-string", "sls", "sed", "awk", "gawk", "bat", "nl",
        "strings", "xxd", "od", "hexdump", "tac", "cut", "sort", "uniq", "diff", "vi", "vim",
        "nano", "view", "jq", "yq", "dotenv", "base64",
    }
)
SHELLS = frozenset({"bash", "sh", "zsh", "dash", "pwsh", "powershell", "cmd", "wsl"})
VOORVOEGSELS = frozenset({"sudo", "command", "exec", "nohup", "time", "xargs", "call", "&", "."})
VEILIGE_CONFIG_VLAGGEN = frozenset(
    {"--no-interpolate", "--services", "--volumes", "--images", "-q", "--quiet"}
)
ENV_LISTERS = frozenset({"get-childitem", "gci", "dir", "ls", "get-item", "gi", "get-content", "gc"})

SCHEIDERS = frozenset(";|&\n\r`(){}")
ENV_NAAM = re.compile(r"^\.env(\.[^/\\]+)?$", re.IGNORECASE)
# `.env`, `.env.local` -- maar niet `os.environ`
ENV_IN_CODE = re.compile(r"\.env(?:\.[A-Za-z0-9_.-]+)?(?![A-Za-z0-9_])", re.IGNORECASE)

ALTERNATIEF_ENV = (
    "Veilig alternatief: lees `.env.example` voor de namen van de sleutels; is de waarde nodig, "
    "vraag Rakesh. Geheimen worden nooit weergegeven, ook niet gedeeltelijk."
)
INLINE_CODE = re.compile(
    r"""(?:^|[\s;&|(])(?:python[0-9.]*|py|node|ruby|perl|deno|bun)(?:\.exe)?\s+(?:-\S+\s+)*?"""
    r"""(?:-c|-e|--eval)\s+(["'])(.*?)\1""",
    re.IGNORECASE | re.S,
)


class Geweigerd(Exception):
    """Een deel van het commando zou geheimen tonen."""


def _is_env_bestand(token: str) -> bool:
    """`.env`, `.env.local`, `config/.env.prod` -- maar niet `.env.example` of `.env.x.example`."""
    t = token.strip().strip("'\"")
    # `--file=.env`, `-Path:.env`
    for deel in re.split(r"[=:]", t) if not re.match(r"^[A-Za-z]:[\\/]", t) else [t]:
        naam = re.split(r"[\\/]", deel)[-1]
        if not naam:
            continue
        if "*" in naam or "?" in naam:
            # `.env*` of `.env.*` treft ook `.env`
            if naam.lower().startswith(".env"):
                return True
            continue
        if ENV_NAAM.match(naam) and not naam.lower().endswith(".example"):
            return True
    return False


def _tokens(deel: str) -> list[str]:
    try:
        return shlex.split(deel, posix=True)
    except ValueError:
        return deel.split()


def _naam(token: str) -> str:
    n = re.split(r"[\\/]", token)[-1].lower()
    return n[:-4] if n.endswith(".exe") else n


def _weiger(reden: str) -> None:
    raise Geweigerd(reden)


def _toets_docker(t: list[str]) -> None:
    naam = _naam(t[0])
    rest = [x.lower() for x in t[1:]]
    compose = naam == "docker-compose" or (naam == "docker" and "compose" in rest)
    if compose:
        na = rest[rest.index("compose") + 1 :] if naam == "docker" else rest
        if "config" in na and not (VEILIGE_CONFIG_VLAGGEN & set(na)):
            _weiger(
                "Geweigerd: `docker compose config` vult .env in en toont echte geheimen in de "
                "uitvoer, en die uitvoer gaat naar het model. Gebruik "
                "`docker compose config --no-interpolate` (structuur zonder ingevulde waarden) of "
                "`docker compose config --services` / `--volumes` / `--images`."
            )
        if ("exec" in na or "run" in na) and ({"env", "printenv"} & set(na)):
            _weiger(
                "Geweigerd: `env`/`printenv` in een container toont alle omgevingsvariabelen, "
                "geheimen inbegrepen. Toets een losse niet-geheime variabele, of controleer of een "
                "sleutel gezet is met `docker compose exec <svc> sh -c 'test -n \"$NAAM\" && echo gezet'`."
            )
        return
    if naam != "docker":
        return
    if rest[:1] == ["inspect"] or rest[:2] == ["container", "inspect"]:
        _weiger(
            "Geweigerd: `docker inspect` op een container toont onder Config.Env alle "
            "omgevingsvariabelen, geheimen inbegrepen. Gebruik `docker ps`, "
            "`docker compose ps` of `docker logs`; voor de status: "
            "`docker inspect` is niet nodig, gebruik `docker ps --format '{{.Names}} {{.Status}}'`."
        )
    if (rest[:1] == ["exec"] or rest[:2] == ["container", "exec"]) and (
        {"env", "printenv"} & set(rest)
    ):
        _weiger(
            "Geweigerd: `docker exec ... env/printenv` toont alle omgevingsvariabelen van de "
            "container, geheimen inbegrepen. Controleer of een sleutel gezet is zonder hem te "
            "tonen: `docker exec <c> sh -c 'test -n \"$NAAM\" && echo gezet'`."
        )


def _toets_deel(deel: str, diepte: int) -> None:
    t = _tokens(deel)
    # Invoer-redirect vanuit een .env-bestand, ook als `<.env`
    for i, tok in enumerate(t):
        if tok == "<" and i + 1 < len(t) and _is_env_bestand(t[i + 1]):
            _weiger("Geweigerd: invoer-redirect uit een .env-bestand toont geheimen. " + ALTERNATIEF_ENV)
        if tok.startswith("<") and len(tok) > 1 and _is_env_bestand(tok.lstrip("<")):
            _weiger("Geweigerd: invoer-redirect uit een .env-bestand toont geheimen. " + ALTERNATIEF_ENV)
    # Voorvoegsels en VAR=x-toewijzingen overslaan
    while t and (
        _naam(t[0]) in VOORVOEGSELS or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", t[0])
    ):
        t = t[1:]
    if not t:
        return
    naam = _naam(t[0])
    args = t[1:]

    if naam in SHELLS and diepte < 5:
        for i, a in enumerate(args):
            if a.lower() in {"-c", "-command", "/c", "/k", "-lc", "-ic", "--"} and i + 1 < len(args):
                toets(" ".join(args[i + 1 :]), diepte + 1)
                return
        return

    if naam == "env":
        # `env VAR=x cmd` start een commando; `env` / `env -0` toont alles
        overig = [a for a in args if not a.startswith("-")]
        while overig and "=" in overig[0]:
            overig = overig[1:]
        if not overig:
            _weiger(
                "Geweigerd: `env` zonder commando toont alle omgevingsvariabelen, geheimen "
                "inbegrepen. Toon een enkele niet-geheime variabele, bijvoorbeeld `echo $PATH`."
            )
        _toets_deel(" ".join(shlex.quote(a) for a in overig), diepte)
        return
    if naam == "printenv":
        _weiger(
            "Geweigerd: `printenv` toont omgevingsvariabelen, geheimen inbegrepen. Toon een "
            "enkele niet-geheime variabele met `echo $PATH`, of toets of een sleutel gezet is: "
            "`test -n \"$NAAM\" && echo gezet`."
        )
    if naam == "set" and not args:
        _weiger(
            "Geweigerd: `set` zonder argumenten toont alle variabelen, geheimen inbegrepen. "
            "Gebruik `echo $PATH` voor een enkele niet-geheime variabele."
        )
    if naam in {"export", "declare", "typeset"} and (
        not args or all(a in {"-p", "-x", "-px", "-xp"} for a in args)
    ):
        _weiger(
            f"Geweigerd: `{naam}` zonder namen toont alle geexporteerde variabelen, geheimen "
            "inbegrepen. Gebruik `echo $PATH` voor een enkele niet-geheime variabele."
        )
    if naam in ENV_LISTERS:
        for a in args:
            a2 = a.strip("'\"").lower()
            if a2.startswith("-path:") or a2.startswith("-literalpath:"):
                a2 = a2.split(":", 1)[1]
            if a2 == "env:" or a2.startswith("env:") or a2.startswith("env:\\") or a2 == "env:\\":
                _weiger(
                    "Geweigerd: de PowerShell-schijf `env:` uitlezen toont alle "
                    "omgevingsvariabelen, geheimen inbegrepen. Gebruik `$env:PATH` voor een "
                    "enkele niet-geheime variabele."
                )
    if naam == "docker" or naam == "docker-compose":
        _toets_docker(t)
    if naam in LEZERS and any(_is_env_bestand(a) for a in args if not a.startswith("-") or "=" in a or ":" in a):
        _weiger(f"Geweigerd: `{naam}` op een .env-bestand toont geheimen. " + ALTERNATIEF_ENV)
    if naam.startswith("python") or naam in {"py", "node", "ruby", "perl", "deno", "bun"}:
        for i, a in enumerate(args):
            if a in {"-c", "-e", "--eval"} and i + 1 < len(args):
                code = " ".join(args[i + 1 :])
                for m in ENV_IN_CODE.finditer(code):
                    if not m.group(0).lower().endswith(".example"):
                        _weiger(
                            "Geweigerd: inline-code die een .env-bestand opent toont geheimen. "
                            + ALTERNATIEF_ENV
                        )


def _splits(commando: str) -> list[str]:
    """Knip op `&&`, `||`, `;`, `|`, `&`, regeleinden, haakjes, `$(` en backticks.

    Buiten aanhalingstekens op al die tekens; binnen dubbele aanhalingstekens alleen op `$(` en
    backticks (daar voert de shell nog steeds uit); binnen enkele aanhalingstekens niet.
    """
    delen: list[str] = []
    huidig: list[str] = []
    quote = ""
    i = 0
    while i < len(commando):
        c = commando[i]
        knip = False
        if quote == "'":
            if c == "'":
                quote = ""
        elif quote == '"':
            if c == '"':
                quote = ""
            elif c == "`" or commando.startswith("$(", i):
                knip = True
        elif c in "'\"":
            quote = c
        elif c in SCHEIDERS or commando.startswith("$(", i):
            knip = True
        if knip:
            delen.append("".join(huidig))
            huidig = []
            i += 2 if commando.startswith("$(", i) else 1
            continue
        huidig.append(c)
        i += 1
    delen.append("".join(huidig))
    return delen


def toets(commando: str, diepte: int = 0) -> None:
    """Werpt `Geweigerd` als een deel van het commando geheimen zou tonen."""
    # Inline-code eerst op de ruwe tekst: het splitsen op haakjes knipt `open('.env')` stuk
    for m in INLINE_CODE.finditer(commando):
        for e in ENV_IN_CODE.finditer(m.group(2)):
            if not e.group(0).lower().endswith(".example"):
                _weiger("Geweigerd: inline-code die een .env-bestand opent toont geheimen. " + ALTERNATIEF_ENV)
    for deel in _splits(commando):
        if deel.strip():
            _toets_deel(deel, diepte)
    # Daarnaast elke shell-wrapper als geheel, zodat de aanhalingstekens kloppen
    for m in re.finditer(r"""(?:-c|-Command|/c)\s+(["'])(.*?)\1""", commando, re.IGNORECASE | re.S):
        if diepte < 5:
            toets(m.group(2), diepte + 1)


def main() -> int:
    try:
        invoer = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        print("Geheimenwacht: hook-invoer is geen JSON; uit voorzorg geweigerd.", file=sys.stderr)
        return 2
    commando = (invoer.get("tool_input") or {}).get("command") or ""
    if not commando:
        return 0
    try:
        toets(commando)
    except Geweigerd as fout:
        print(str(fout), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
