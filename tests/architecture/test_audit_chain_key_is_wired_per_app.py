"""Als de auditsleutel op een app staat, komt hij via `--set-secrets` (ADR-036 OP-120).

**De valkuil die dit bewaakt, en die in dit project al eerder is opgetreden.**
Container-App-secrets zijn PER APP. Een `--set-env-vars "X=secretref:y"` zonder een bijbehorende
`--set-secrets "y=..."` op DEZELFDE app levert geen fout op: de omgevingsvariabele resolveert dan
naar de letterlijke string `"secretref:y"`. Die is 15+ tekens lang, komt dus door de
minimumlengte-eis heen, en wordt geaccepteerd als sleutel.

Gevolg: de HMAC-sleutel is een publiek bekende constante, en elke ketenhash is door iedereen na
te rekenen. De keten lijkt gesleuteld en is het niet -- precies de vorm van schijnzekerheid die
deze hele reeks opruimt. Dezelfde valkuil staat al beschreven bij
`TOOL_PAYLOAD_PSEUDONYM_KEY` in `cd-production.yml`.

**Waarom de sleutel NIET verplicht is.** Zonder sleutel valt de keten terug op SHA-256 -- de
bestaande toestand. Een blokkerende preflight zou dus een deploy tegenhouden voor een functie die
per ontwerp optioneel is. Deze guard eist alleen: als hij ergens wordt MEEGEGEVEN, dan correct.

**Mutatietest (2026-08-11, beide richtingen):** een `--set-env-vars` met de secretref toegevoegd
zonder bijbehorende `--set-secrets` -> ROOD. De hele variabele weggelaten -> GROEN (mag, dan draait
die app op legacy). Een app met beide -> GROEN.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
_ENV_VAR = "AUDIT_CHAIN_HMAC_KEY"
_SECRET_NAAM = "audit-chain-hmac-key"


def _containerapp_commandos() -> list[tuple[str, str]]:
    """Elk `az containerapp create|update`-commando in de CD-workflows, als (waar, tekst).

    Comments eruit en backslash-vervolgregels samengevoegd, zodat een commando dat over tien
    regels loopt als EEN geheel wordt beoordeeld. Zonder dat oordeelt de guard per regel en mist
    hij elke koppeling tussen `--set-env-vars` en `--set-secrets`.
    """
    uit: list[tuple[str, str]] = []
    for workflow in sorted((REPO_ROOT / ".github/workflows").glob("cd-*.y*ml")):
        parsed = yaml.safe_load(workflow.read_text(encoding="utf-8")) or {}
        for jobnaam, job in (parsed.get("jobs") or {}).items():
            for stap in job.get("steps") or []:
                script = str(stap.get("run", ""))
                if "containerapp" not in script:
                    continue
                zonder_comments = [
                    regel.split("#", 1)[0] if not regel.strip().startswith("#") else ""
                    for regel in script.splitlines()
                ]
                logische: list[str] = []
                buffer = ""
                for regel in zonder_comments:
                    buffer += regel.rstrip()
                    if buffer.endswith("\\"):
                        buffer = buffer[:-1] + " "
                        continue
                    logische.append(buffer)
                    buffer = ""
                if buffer:
                    logische.append(buffer)
                for commando in logische:
                    if "containerapp" in commando and (
                        " create" in commando or " update" in commando
                    ):
                        naam = f"{workflow.name}:{jobnaam}:{stap.get('name', '?')}"
                        uit.append((naam, commando))
    return uit


def test_the_scan_finds_containerapp_commands_at_all() -> None:
    """Vangnet: loopt de scan leeg, dan bewaakt de test hieronder niets."""
    gevonden = _containerapp_commandos()

    assert len(gevonden) >= 4, (
        f"Slechts {len(gevonden)} containerapp-commando's gevonden. Is de aanroepvorm veranderd? "
        "Zolang dit leegloopt zegt de test hieronder niets."
    )


def test_the_audit_key_is_never_a_dangling_secretref() -> None:
    """Een secretref zonder eigen `--set-secrets` maakt de sleutel een publieke constante."""
    zonder_definitie: list[str] = []
    for waar, commando in _containerapp_commandos():
        gebruikt_env = f"{_ENV_VAR}=secretref:{_SECRET_NAAM}" in commando
        definieert = f"{_SECRET_NAAM}=" in commando and "--set-secrets" in commando
        if gebruikt_env and not definieert:
            zonder_definitie.append(waar)

    assert not zonder_definitie, (
        f"Deze commando's verwijzen naar `secretref:{_SECRET_NAAM}` zonder het secret op DEZELFDE "
        f"app te definieren: {zonder_definitie}.\n\n"
        "Container-App-secrets zijn per app. Zonder eigen `--set-secrets` resolveert de env-var "
        f"naar de letterlijke string 'secretref:{_SECRET_NAAM}' -- lang genoeg om door de "
        "sterkte-eis te komen, en daarmee is de HMAC-sleutel een publiek bekende constante. De "
        "keten lijkt dan gesleuteld en is het niet."
    )


def test_the_key_is_optional_so_apps_without_it_are_fine() -> None:
    """De tweede richting: een app ZONDER de sleutel is geen overtreding.

    Zonder sleutel valt de keten terug op SHA-256, de bestaande toestand. Zou deze guard de
    sleutel verplichten, dan blokkeert hij een deploy voor een functie die per ontwerp optioneel
    is -- en dan wordt hij uitgezet.
    """
    commandos = _containerapp_commandos()
    zonder_sleutel = [waar for waar, c in commandos if _ENV_VAR not in c]

    assert zonder_sleutel or not commandos, (
        "Elke app heeft de auditsleutel. Dat mag, maar deze test hoort te bewijzen dat een app "
        "ZONDER hem geen overtreding is -- anders is 'optioneel' een loze bewering."
    )


def _stappen_met_de_sleutel() -> list[tuple[str, str]]:
    """Elke deploystap die de auditsleutel noemt, als (waar, volledig script).

    Per STAP en niet per commando, want de wiring gebruikt conditionele arrays: het secret en de
    env-var worden samen in een `if`-blok gezet en pas daarna geexpandeerd op de commandoregel.
    Een controle die alleen naar de `containerapp`-regel kijkt ziet die strings dus niet en
    slaagt vacuum -- dat was deze guard tot 2026-08-11.

    Een stap komt hier overeen met een app: elke deploystap draait `containerapp` voor precies
    een `--name`.
    """
    uit: list[tuple[str, str]] = []
    for workflow in sorted((REPO_ROOT / ".github/workflows").glob("cd-*.y*ml")):
        parsed = yaml.safe_load(workflow.read_text(encoding="utf-8")) or {}
        for jobnaam, job in (parsed.get("jobs") or {}).items():
            for stap in job.get("steps") or []:
                script = str(stap.get("run", ""))
                if "containerapp" not in script or _ENV_VAR not in script:
                    continue
                uit.append((f"{workflow.name}:{jobnaam}:{stap.get('name', '?')}", script))
    return uit


def test_every_step_that_sets_the_env_var_also_defines_the_secret() -> None:
    """De echte pairing-controle: per app moeten beide er zijn, of geen van beide.

    Een `--set-env-vars "AUDIT_CHAIN_HMAC_KEY=secretref:audit-chain-hmac-key"` zonder een
    `--set-secrets "audit-chain-hmac-key=..."` op DEZELFDE app laat de variabele resolveren naar
    de letterlijke string `secretref:audit-chain-hmac-key`. Die is lang genoeg om door de
    sterkte-eis te komen, en dan is de HMAC-sleutel een publiek bekende constante.

    Uitzondering: de productie-backend krijgt zijn secret via een Key Vault-REFERENTIE in de
    ARM-patch (`keyVaultUrl`) in plaats van via `--set-secrets`. Dat is een geldige definitie.
    """
    ongepaard: list[str] = []
    for waar, script in _stappen_met_de_sleutel():
        zet_env = f"{_ENV_VAR}=secretref:{_SECRET_NAAM}" in script
        definieert = f"{_SECRET_NAAM}=${{AUDIT_KEY}}" in script or f'"{_SECRET_NAAM}"' in script
        if zet_env and not definieert:
            ongepaard.append(waar)

    assert not ongepaard, (
        f"Deze stappen zetten `{_ENV_VAR}` op een secretref zonder het secret op dezelfde app te "
        f"definieren: {ongepaard}. "
        f"De env-var resolveert dan naar de letterlijke string 'secretref:{_SECRET_NAAM}'. Die "
        "komt door de minimumlengte heen en wordt geaccepteerd als sleutel -- de keten lijkt "
        "gesleuteld en is het niet."
    )


def test_the_key_and_the_secret_are_set_in_the_same_conditional() -> None:
    """Ze mogen niet uit elkaar lopen bij een latere wijziging.

    Het secret en de env-var horen in EEN `if`-blok. Zet iemand er later twee losse condities
    van, dan kan de ene wel en de andere niet vuren -- en dat is exact de hangende secretref.
    """
    gescheiden: list[str] = []
    for waar, script in _stappen_met_de_sleutel():
        if f"{_SECRET_NAAM}=${{AUDIT_KEY}}" not in script:
            continue  # backend via Key Vault-referentie
        regels = script.splitlines()
        secret_regel = next(
            i for i, r in enumerate(regels) if f"{_SECRET_NAAM}=${{AUDIT_KEY}}" in r
        )
        env_regel = next(
            (i for i, r in enumerate(regels) if f'AUDIT_ENVVARS=("{_ENV_VAR}=secretref:' in r), None
        )
        if env_regel is None or abs(env_regel - secret_regel) > 2:
            gescheiden.append(waar)

    assert not gescheiden, (
        f"In deze stappen staan het secret en de env-var niet direct naast elkaar in hetzelfde "
        f"`if`-blok: {gescheiden}. Dan kunnen ze bij een latere wijziging uit elkaar lopen."
    )
