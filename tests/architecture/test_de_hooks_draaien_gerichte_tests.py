"""De git-hooks roepen de impact-selectie ook echt aan.

**Waarom deze bewaker in tests/architecture/ staat en niet bij de unittests.** Hij toetst
geen functielogica maar een structurele eigenschap van de repo: dat de pre-commit en de
pre-push hook het selectiescript daadwerkelijk UITVOEREN. Een selectie die nergens wordt
aangeroepen bewaakt niets.

Er is ook een regel-reden. `.claude/rules/quality-gates.md` regel 411 eist dat een guard in
`tests/architecture/` staat -- de eis is daar op LOCATIE geformuleerd. `.claude/skills/
valkuilen/SKILL.md` regel 725 formuleert dezelfde eis op FUNCTIE: alles wat werk BLOKKEERT
krijgt een guard met mutatiebewijs in twee richtingen. Deze bewaking blokkeert commits en
pushes, maar stond aanvankelijk in `tests/unit/scripts/` -- en viel daarmee tussen die twee
formuleringen van dezelfde regel in. Aangewezen door een tweede sessie op 2026-09-25, zelf
nagemeten op beide regelnummers, en hier rechtgezet. Dat de twee formuleringen ZELF gelijk
moeten worden getrokken staat als taak in
`docs/agent-briefs/generated/2026-09-24-sprint-dag-het-meetinstrument-wordt-zelf-nooit-gemuteerd.md`.

De unittests op de selectielogica blijven waar ze horen:
`tests/unit/scripts/test_impact_tests.py`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _uitvoerbare_regels(inhoud: str) -> str:
    """De hook zonder commentaar en zonder meldingen.

    **Waarom dit nodig is, gemeten op deze test zelf.** De eerste versie toetste of de
    tekst `scripts/impact_tests.py` ergens in de hook voorkwam. De mutatie "vervang de
    aanroep door een lege waarde" bleef GROEN, omdat de hook dat pad ook in een HELPREGEL
    noemt (`echo "python scripts/impact_tests.py --staged"`). Een bewaker die een woord
    zoekt in plaats van een handeling -- exact de faalvorm waar dit project een eigen brief
    over heeft, gemaakt op dezelfde dag als deze test.
    """
    behouden = []
    for regel in inhoud.splitlines():
        gestript = regel.strip()
        if gestript.startswith("#"):
            continue
        if gestript.startswith(("echo ", "info ", "fail ", "ok ")):
            continue
        behouden.append(regel)
    return "\n".join(behouden)


@pytest.mark.parametrize("hook", ["pre-commit", "pre-push"])
def test_de_hook_roept_de_selectie_echt_aan(hook: str) -> None:
    """De les van 2026-09-24, hier meteen toegepast.

    Bij de reparatie van de ratchet-metrieken bleef de mutatie "zet de aanroep terug naar de
    oude vorm" GROEN, omdat de tests de hulpfunctie rechtstreeks aanriepen en niet de plek
    waar hij gebruikt wordt. Een selectie die nergens wordt aangeroepen bewaakt niets.
    """
    uitvoerbaar = _uitvoerbare_regels(
        (REPO_ROOT / "scripts" / "hooks" / hook).read_text(encoding="utf-8")
    )

    assert "scripts/impact_tests.py" in uitvoerbaar, (
        f"de {hook} hook roept scripts/impact_tests.py niet meer aan in een UITVOERBARE "
        "regel; dan draait er bij een wijziging geen enkele test meer voordat hij wordt "
        "vastgelegd (een vermelding in een comment of een echo telt hier niet)"
    )
    assert "pytest" in uitvoerbaar, (
        f"de {hook} hook selecteert misschien nog tests, maar draait ze niet"
    )
