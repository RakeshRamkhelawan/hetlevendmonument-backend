"""Waarde-dragende secrets gaan via `env:`, niet via de shell-tekst (ADR-036 MEDIUM-6).

**De bevinding.** In `Deploy scheduler` stonden `PROD_DATABASE_URL` en `ACR_PASSWORD`
rechtstreeks in de `run:`-tekst, terwijl diezelfde stap voor twee andere geheimen al `env:`
gebruikte. Zelfde klasse als OP-94/OP-98.

**Wat `env:` wel en niet oplost, want dat verschil hoort hier te staan.** Wel: de waarde staat
niet meer in het tijdelijke scriptbestand dat de runner op schijf zet en dat elke andere stap in
dezelfde job kan lezen. Niet: de waarde wordt daarna nog steeds argv van `az`
(`--registry-password "$X"`), en staat dus in `/proc/<pid>/cmdline` zolang die aanroep loopt.
`.github/scripts/az-retry.sh` documenteert dat residu al voor zijn eigen echo. Deze guard sluit
de eerste helft; de tweede is een eigenschap van de Azure CLI.

**Waarom alleen WAARDE-dragende secrets.** Gemeten op 2026-08-09: 16 stappen in
`cd-production.yml` en 18 in `cd-staging.yml` noemen `secrets.*` binnen `run:`. Verreweg de
meeste daarvan zijn NAMEN (`secrets.PROD_BACKEND_APP`, `secrets.STAGING_RESOURCE_GROUP`) --
geen geheim, en die in een uitzonderingslijst zetten zou een lijst van veertien regels
opleveren. Een uitzonderingslijst die het merendeel bevat, bewaakt niets. Daarom een expliciete
lijst van wat een GEHEIM DRAAGT.

**Mutatietest (2026-08-09, beide richtingen):**
- `--secrets "database-url=${{ secrets.PROD_DATABASE_URL }}"` teruggezet -> ROOD.
- `--registry-password "${{ secrets.ACR_PASSWORD }}"` teruggezet -> ROOD.
- `set -x` in een CD-`run:` gezet -> ROOD (de shell-trace expandeert `${DB_URL}` in argv, en
  daarmee is de hele opbrengst van deze guard weg).
- LEGITIEM: `secrets.PROD_BACKEND_APP` in de shell-tekst (een NAAM, geen geheim) -> GROEN.
"""

from __future__ import annotations

import re

from tests.architecture._ci_workflow import CD_GLOB, WORKFLOW_DIR, cd_stappen

#: Wat een geheim DRAAGT. Namen van apps en resourcegroepen staan hier bewust niet in.
_GEHEIM_PATRONEN = (
    re.compile(r"secrets\.\w*DATABASE_URL\b"),
    re.compile(r"secrets\.\w*ACR_PASSWORD\b"),
    re.compile(r"secrets\.\w*SECRET_KEY\b"),
    re.compile(r"secrets\.\w*JWT_SECRET\w*\b"),
    re.compile(r"secrets\.\w*REDIS_URL\b"),
    re.compile(r"secrets\.\w*PSEUDONYM_KEY\b"),
    re.compile(r"secrets\.\w*API_KEY\b"),
    re.compile(r"secrets\.AZURE_CREDENTIALS\b"),
    re.compile(r"secrets\.\w*ENCRYPTION_KEY\b"),
    # 2026-10-23 (Gate 2 staging-uitrol): de bonlezer-Redis, de opslagsleutel en het mailwachtwoord
    # stonden niet in deze lijst; ze lopen nu wel via `env:`, maar niets bewaakte dat.
    re.compile(r"secrets\.\w*(?:STORAGE_KEY|REDIS_PASSWORD|SMTP_PASSWORD)\b"),
)

#: Stappen waar een geheim in de shell-tekst onvermijdelijk is, met datum en reden per regel.
KNOWN_INLINE_SECRETS: dict[str, str] = {}
# Leeg sinds 2026-10-24 (brief uitrol-nazorg-2): alle acht uitzonderingen (Check required secrets, Login ACR,
# Validate AZURE_CREDENTIALS JSON, Push secrets to Key Vault, in beide workflows) zijn naar `env:` verplaatst.
# Elke nieuwe uitzondering komt hier met datum en reden terug; `test_cd_geheimen_alleen_via_env` bewaakt
# bovendien ALLE `${{ secrets.X }}` in `run:`, ook namen, zonder uitzonderingslijst.

#: Shell-tracing zet elke geexpandeerde variabele in het CI-log. Dat maakt `env:` zinloos.
_TRACE = re.compile(r"^\s*set\s+-[a-z]*x|^\s*bash\s+-[a-z]*x", re.MULTILINE)


def _sleutel(workflow: str, stap: str) -> str:
    return f"{workflow}:{stap}"


def _stappen_met_geheim_in_de_tekst() -> list[str]:
    gevonden: list[str] = []
    for stap in cd_stappen():
        if any(patroon.search(stap.script) for patroon in _GEHEIM_PATRONEN):
            gevonden.append(_sleutel(stap.workflow, stap.naam))
    return gevonden


def test_the_scan_finds_cd_steps_at_all() -> None:
    """Vangnet: loopt de scan leeg, dan bewaakt de rest niets."""
    stappen = cd_stappen()

    workflows = {stap.workflow for stap in stappen}
    ontbreekt = sorted({"cd-production.yml", "cd-staging.yml"} - workflows)
    assert not ontbreekt, (
        f"Deze CD-workflows leveren geen enkele stap op: {ontbreekt}. Gevonden: "
        f"{sorted(workflows)}. Zolang een workflow ontbreekt bewaakt deze guard daar niets."
    )


def test_the_secret_patterns_still_match_something() -> None:
    """Tweede vangnet: herkennen de patronen nog een echt geheim?

    Zonder deze toets zou een typefout in een patroon (of een hernoemd secret) de guard
    stilzwijgend leegmaken -- hij meldt dan groen omdat hij niets meer HERKENT, niet omdat er
    niets meer fout is.
    """
    # De RUWE workflowtekst, niet alleen `run:`: sinds 2026-10-24 staat er geen geheim meer in een
    # `run:`-blok (het staat in `env:`), dus in `stap.script` zoeken zou hier altijd niets vinden.
    alle_tekst = "\n".join(
        pad.read_text(encoding="utf-8") for pad in sorted(WORKFLOW_DIR.glob(CD_GLOB))
    )
    rakend = [p.pattern for p in _GEHEIM_PATRONEN if p.search(alle_tekst)]

    assert rakend, (
        "Geen enkel geheim-patroon vindt nog iets in de CD-workflows. Dat betekent niet dat "
        "alles goed staat -- het betekent dat deze guard niets meer meet. Zijn de secrets "
        "hernoemd? Werk _GEHEIM_PATRONEN bij."
    )


def test_no_value_bearing_secret_is_interpolated_into_shell_text() -> None:
    """De kern: een geheim hoort in `env:`, niet in het scriptbestand op de runner."""
    overtreders = sorted(set(_stappen_met_geheim_in_de_tekst()) - set(KNOWN_INLINE_SECRETS))

    assert not overtreders, (
        f"Deze CD-stappen interpoleren een waarde-dragend secret rechtstreeks in hun "
        f"shell-tekst: {overtreders}.\n\n"
        "Daarmee staat de waarde in het tijdelijke scriptbestand dat de runner op schijf zet, "
        "en dat kan elke andere stap in dezelfde job lezen. Zet het geheim in het `env:`-blok "
        "van de stap en verwijs met ${NAAM} (ADR-036 MEDIUM-6, zelfde klasse als OP-94/OP-98).\n\n"
        "Is het onvermijdelijk -- de stap ZET of CONTROLEERT het geheim zelf -- zet hem dan met "
        "datum en reden in KNOWN_INLINE_SECRETS."
    )


def test_no_cd_step_enables_shell_tracing() -> None:
    """`set -x` maakt de hele opbrengst van deze guard ongedaan.

    De shell-trace schrijft elke geexpandeerde variabele naar het CI-log, dus ook `${DB_URL}`
    die we net uit de scripttekst hebben gehaald. Gemeten 2026-08-09: nul voorkomens in
    `.github/`. Dat is precies het moment om het vast te leggen -- niet nadat iemand het voor
    een debugsessie heeft aangezet en laten staan.
    """
    met_trace = [
        _sleutel(stap.workflow, stap.naam) for stap in cd_stappen() if _TRACE.search(stap.script)
    ]

    assert not met_trace, (
        f"Deze CD-stappen zetten shell-tracing aan: {met_trace}. Dan expandeert de shell elke "
        "variabele naar het CI-log, inclusief de geheimen die via `env:` binnenkomen. Gebruik "
        "gerichte `echo`-regels zonder geheimen."
    )


def test_known_inline_secrets_is_not_stale() -> None:
    """Een uitzondering die is opgelost MOET eruit, anders rot de lijst dicht."""
    nog_nodig = set(_stappen_met_geheim_in_de_tekst())
    opgelost = sorted(set(KNOWN_INLINE_SECRETS) - nog_nodig)

    assert not opgelost, (
        f"Deze stappen staan in KNOWN_INLINE_SECRETS maar hebben geen geheim meer in hun "
        f"shell-tekst: {opgelost}. Haal ze uit de lijst; anders suggereert die lijst een "
        "uitzondering die nergens op slaat."
    )
