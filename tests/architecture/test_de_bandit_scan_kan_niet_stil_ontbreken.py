"""De lokale beveiligingsscan MOET falen als bandit ontbreekt (ADR-036 OP-244).

**De bevinding, gemeten 2026-09-15.** `scripts/ci-local-fast.sh` riep bandit aan met
`|| true`, stuurde stderr naar `/dev/null`, en telde de bevindingen met een kale
`except Exception: print(0)`. Ontbrak bandit, dan werd het JSON-rapport nooit geschreven,
gaf de teller 0, en meldde het script: "Bandit: geen HIGH+HIGH findings."

Bandit stond op dat moment NIET in `requirements-test.txt` en was niet geinstalleerd. Sinds
het stilleggen van GitHub Actions is deze hook de enige plek waar die scan nog zou draaien --
de enige overgebleven beveiligingsscan gaf dus een valse veiligverklaring.

Toen bandit eenmaal was geinstalleerd, gaf de echte scan 0 HIGH+HIGH bevindingen over
347.715 regels. Het antwoord klopte dus toevallig, en dat is precies waarom een guard die
niet kan falen niets waard is.

**Mutatiebewijs (2026-09-15), beide richtingen:**
  1. De aanwezigheidscontrole uit het script verwijderd -> deze test ROOD.
  2. De onaangeroerde boom -> GROEN.
  3. Handmatig nagespeeld met een nep-interpreter die `-m bandit` laat falen: het script
     zet `FAILED=1` in plaats van "geen bevindingen" te melden.
"""

from __future__ import annotations

import re
from pathlib import Path

_SCRIPT = Path("scripts/ci-local-fast.sh")
_REQUIREMENTS = Path("requirements-test.txt")


def _regels_zonder_commentaar() -> list[str]:
    """Alleen uitvoerbare regels -- een toelichting die bandit noemt telt niet mee."""
    return [
        r for r in _SCRIPT.read_text(encoding="utf-8").splitlines() if not r.strip().startswith("#")
    ]


def test_het_script_controleert_of_bandit_bestaat() -> None:
    """Zonder deze controle leest een ontbrekende bandit als 'geen bevindingen'."""
    uitvoerbaar = "\n".join(_regels_zonder_commentaar())
    assert re.search(r"-m bandit --version", uitvoerbaar), (
        f"{_SCRIPT} roept bandit aan zonder eerst te controleren of hij bestaat. Met "
        "`|| true`, stderr naar /dev/null en een kale `except Exception: print(0)` wordt een "
        "ontbrekende bandit dan gerapporteerd als 'geen HIGH+HIGH findings' -- een valse "
        "veiligverklaring in de enige beveiligingsscan die dit project nog heeft "
        "(ADR-036 OP-244)."
    )


def test_het_script_controleert_of_er_een_rapport_is_geschreven() -> None:
    """Een bandit die halverwege omvalt laat hetzelfde lege gat achter als een die ontbreekt."""
    uitvoerbaar = "\n".join(_regels_zonder_commentaar())
    assert re.search(r"\[\s*!\s*-s\s+\"\$BANDIT_JSON\"\s*\]", uitvoerbaar), (
        f"{_SCRIPT} controleert niet of bandit daadwerkelijk een rapport heeft geschreven."
    )


def test_bandit_staat_gepind_in_requirements() -> None:
    """Een controle die faalt bij ontbreken is pas nuttig als het pakket ook geleverd wordt."""
    inhoud = _REQUIREMENTS.read_text(encoding="utf-8")
    assert re.search(r"^bandit==", inhoud, re.MULTILINE), (
        f"bandit staat niet gepind in {_REQUIREMENTS}, terwijl {_SCRIPT} en "
        ".github/workflows/ci-feature.yml hem allebei aanroepen. Dan faalt de nieuwe "
        "controle bij iedereen die de omgeving vers opzet, en dat is geen reparatie."
    )
