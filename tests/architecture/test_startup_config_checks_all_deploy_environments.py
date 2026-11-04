"""Architecture test: de opstartcontrole dekt elke omgeving waar we deployen (ADR-036 OP-30).

`ConfigValidator.validate()` doorloopt `PRODUCTION_REQUIRED_VARS` alleen als `ENVIRONMENT`
`production` of `staging` is. De vloot gebruikt ook `blue` en `green` -- en blue/green is een
PRODUCTIETECHNIEK. Daar draait de controle dus niet, en een ontbrekende verplichte variabele
wordt daar pas een storing in plaats van een deploy-fout.

Dezelfde blocklist-vorm die binnen OP-27 al eens is omgedraaid naar een allowlist, een laag
hoger.

**Waarom dit een groene guard met uitzondering is en geen fix.** De omgevingslijst verbreden
raakt ALLE variabelen in `PRODUCTION_REQUIRED_VARS`, niet alleen die van OP-27, en kan een
blue/green-deploy laten falen op een variabele die er vandaag doorheen komt. Dat vraagt eerst een
meting van wat er in zo'n omgeving daadwerkelijk gezet is. Conform de uitzonderingsparagraaf in
`.claude/rules/quality-gates.md`: gedateerd, met reden per regel, plus een staleness-test.

**Waarom dit bestand er toch is.** OP-30 stond alleen in de ADR en had geen enkele test, terwijl
de bevinding ernaast (OP-28) er wel een kreeg. Dat is precies de NOOIT-regel die zegt dat een
bevinding zonder fix borging vereist. Beide Gate 2-reviewers noemden het, en mijn eigen
guard-docstring in `test_tool_results_are_registered_as_open.py` verwijt hetzelfde aan ronde 1.

Voor `TOOL_PAYLOAD_PSEUDONYM_KEY` is het gat niet gevaarlijk: `tool_broker/redaction.py` gebruikt
een eigen ALLOWLIST van omgevingen en faalt in blue/green dus wel closed. Voor de andere drie
variabelen is dat niet nagegaan -- vandaar de uitzondering en niet een gerustheid.
"""

#: Omgevingen die uit een CD-workflow of compose-bestand komen en niet uit een compose-bestand
#: te lezen zijn. `production`/`staging` staan als `ENVIRONMENT: production` in de CD-workflows.
_ENVIRONMENTS_FROM_WORKFLOWS: frozenset[str] = frozenset({"production", "staging"})


def _deploy_environments() -> frozenset[str]:
    """De omgevingen waar we deployen, GELEZEN uit de deploy-configuratie.

    Was een handmatig literaal `{"production", "staging", "blue", "green"}` (aangepast 2026-08-04,
    ronde 5). Dat is dezelfde steekproef-fout als bij `_IMPLEMENTATIONS`: een VIJFDE
    deploy-omgeving in een nieuw compose-bestand was voor deze guard onzichtbaar, terwijl de test
    `test_no_deploy_environment_skips_the_startup_check_unregistered` heet.

    `blue`/`green` komen uit `deployment/blue_green/docker-compose.*.yml` -- de bestandsnaam IS de
    omgevingsnaam, en dat is wat we hier uitlezen. `production`/`staging` staan alleen in de
    CD-workflows als `ENVIRONMENT`-waarde en blijven een constante.
    """
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    blue_green = repo_root / "deployment" / "blue_green"

    from_compose = {
        path.name.removeprefix("docker-compose.").removesuffix(".yml")
        for path in blue_green.glob("docker-compose.*.yml")
    }
    return frozenset(_ENVIRONMENTS_FROM_WORKFLOWS | from_compose)


def test_the_deploy_environments_are_read_from_the_deploy_configuration() -> None:
    """Vangnet: vindt de scan de compose-bestanden uberhaupt?

    Zonder deze test maakt een verplaatste map de verzameling stil kleiner, en dan meldt de guard
    hieronder niets over de omgevingen die hij niet meer ziet.
    """
    found = _deploy_environments()

    assert {"blue", "green"} <= found, (
        f"blue/green niet gevonden in deployment/blue_green/ (gevonden: {sorted(found)}). Is de map "
        "verplaatst? Zolang de scan ze niet ziet, bewaakt deze guard alleen production en staging."
    )


#: Omgevingen die de opstartcontrole vandaag NIET doorloopt. Gedateerd, met reden per regel.
#: Leeg sinds OP-30 is opgelost (2026-08-27, commit <zie ADR-036 OP-30-rij>): `blue`/`green`
#: zijn gemeten (API_BASE_URL/FRONTEND_URL stonden in geen van beide compose-bestanden),
#: daarna geprovisioneerd in `docker-compose.blue.yml`/`docker-compose.green.yml`, en pas
#: DAARNA is de omgevingscheck in `ConfigValidator.validate()` verbreed -- in die volgorde,
#: zodat het verbreden zelf geen deploy kon laten falen.
KNOWN_UNCHECKED_ENVIRONMENTS: dict[str, str] = {}


def _checked_environments() -> set[str]:
    """De omgevingen waarvoor `validate()` de productielijst doorloopt.

    Uit de BRONCODE en niet uit een aanname: de test in `validate()` is een `in`-vergelijking
    tegen een tuple literal, en die lezen we uit de AST. Zo betrapt deze guard ook een wijziging
    die de tuple uitbreidt zonder deze lijst bij te werken.
    """
    import ast
    import inspect

    from src.core.config.config_validator import ConfigValidator

    source = inspect.getsource(ConfigValidator.validate)
    tree = ast.parse(source.lstrip())

    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        if not any(isinstance(op, ast.In) for op in node.ops):
            continue
        for comparator in node.comparators:
            if isinstance(comparator, (ast.Tuple, ast.List, ast.Set)):
                found |= {
                    element.value
                    for element in comparator.elts
                    if isinstance(element, ast.Constant) and isinstance(element.value, str)
                }
    return found


def test_the_guard_actually_finds_the_environment_check() -> None:
    """Vangnet: een guard die de vergelijking niet vindt, bewijst niets.

    Zou de AST-analyse stilvallen -- bijvoorbeeld doordat de check naar een constante of een
    helper verhuist -- dan zou de test hieronder groen zijn door LEEGTE.
    """
    checked = _checked_environments()

    assert "production" in checked, (
        f"De omgevingscheck in ConfigValidator.validate() is niet gevonden; gelezen: "
        f"{sorted(checked)}. Verplaatst naar een constante of helper? Werk deze guard bij."
    )


def test_no_deploy_environment_skips_the_startup_check_unregistered() -> None:
    """Een nieuwe deploy-omgeving mag niet stil buiten de opstartcontrole vallen."""
    unchecked = sorted(_deploy_environments() - _checked_environments())
    new = sorted(set(unchecked) - set(KNOWN_UNCHECKED_ENVIRONMENTS))

    assert not new, (
        f"Deze deploy-omgevingen doorlopen PRODUCTION_REQUIRED_VARS niet: {new}. Een verplichte "
        "variabele die daar ontbreekt wordt geen deploy-fout maar een storing tijdens gebruik. "
        "Neem de omgeving op in de check, of zet hem met datum en reden in "
        "KNOWN_UNCHECKED_ENVIRONMENTS."
    )


def test_known_unchecked_environments_is_not_stale() -> None:
    """Een uitzondering die is opgelost MOET uit de lijst, anders rot hij dicht."""
    checked = _checked_environments()
    stale = sorted(name for name in KNOWN_UNCHECKED_ENVIRONMENTS if name in checked)

    assert not stale, (
        f"Deze omgevingen doorlopen de controle inmiddels wel: {stale}. Haal ze uit "
        "KNOWN_UNCHECKED_ENVIRONMENTS."
    )
