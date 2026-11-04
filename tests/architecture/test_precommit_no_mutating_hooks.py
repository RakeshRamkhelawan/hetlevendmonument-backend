"""Geen muterende pre-commit hook mag bij een gewone commit draaien (BE-CI-006).

Achtergrond. `.pre-commit-config.yaml` bevat zes hooks die bestanden HERSCHRIJVEN. Gemeten
op 2026-08-13 met --check, dus zonder iets te wijzigen:

    black          818 van 2222 bestanden in src/ zouden worden herschreven
    ruff-format    717 -- en niet dezelfde 717; de twee formatters zijn het oneens
    isort en ruff --fix              extra herschrijvingen bovenop
    trailing-whitespace              geen files:-filter, dus alle 12538 getrackte bestanden
    end-of-file-fixer                idem

Zolang die hooks in de pre-commit stage staan, herschrijft `pre-commit install` gevolgd door
een gewone commit honderden regels die de committer niet heeft aangeraakt. Dat is verboden per
.claude/rules/quality-gates.md, en bovendien zou de ene formatter het werk van de andere
meteen omgooien. Een repo-brede normalisatie naar EEN formatter is een aparte beslissing;
tot die gemaakt is mag geen hook het per ongeluk doen.

Mutatiebewijs (uitgevoerd op een kopie van .pre-commit-config.yaml, daarna teruggezet):

    `stages: [manual]` van black weghalen          -> test_no_mutating_hook_runs_on_commit rood
    `stages: [manual]` van trailing-whitespace af  -> zelfde test rood
    onveranderd bestand                            -> groen

De tweede richting is nodig: zonder de eis dat het onveranderde bestand groen is, zou
"verbied alle hooks" ook een geldige oplossing zijn.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG = REPO_ROOT / ".pre-commit-config.yaml"

# Hooks die de inhoud van bestanden aanpassen in plaats van alleen rapporteren.
MUTATING_HOOK_IDS = frozenset(
    {
        "black",
        "isort",
        "ruff",  # met --fix
        "ruff-format",
        "trailing-whitespace",
        "end-of-file-fixer",
    }
)

# pre-commit kent zowel de oude naam ('commit') als de nieuwe ('pre-commit').
COMMIT_STAGES = frozenset({"commit", "pre-commit"})


def _hooks() -> list[dict[str, object]]:
    assert CONFIG.exists(), f"Configuratiebestand ontbreekt: {CONFIG}"
    data = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    return [hook for repo in data["repos"] for hook in repo["hooks"]]


def _runs_on_commit(hook: dict[str, object]) -> bool:
    """Een hook zonder `stages` draait in ALLE stages, dus ook bij een commit."""
    stages = hook.get("stages")
    if stages is None:
        return True
    return bool(COMMIT_STAGES & set(stages))  # type: ignore[arg-type]


@pytest.mark.architecture
class TestPrecommitHasNoMutatingHooksOnCommit:
    def test_no_mutating_hook_runs_on_commit(self) -> None:
        """Elke muterende hook staat op een expliciete niet-commit stage (manual)."""
        offending = [
            str(hook.get("id"))
            for hook in _hooks()
            if str(hook.get("id")) in MUTATING_HOOK_IDS and _runs_on_commit(hook)
        ]
        assert not offending, (
            f"Deze hooks herschrijven bestanden en draaien bij een gewone commit: "
            f"{offending}. Zet ze op `stages: [manual]`. Gemeten 2026-08-13: black alleen "
            "al zou 818 bestanden in src/ herschrijven, waarvan de committer er meestal "
            "een of twee heeft aangeraakt. Zie BE-CI-006 en "
            ".claude/rules/quality-gates.md."
        )

    def test_the_mutating_hooks_still_exist(self) -> None:
        """De hooks zijn op manual gezet, niet verwijderd.

        Zonder deze assertie zou de vorige test ook groen zijn door de formatters gewoon
        weg te gooien -- dan is de mogelijkheid om bewust te formatteren stil verdwenen.
        """
        present = {str(hook.get("id")) for hook in _hooks()}
        missing = sorted(MUTATING_HOOK_IDS - present)
        assert not missing, (
            f"Deze hooks zijn uit .pre-commit-config.yaml verdwenen: {missing}. Ze horen "
            "aanwezig te zijn op `stages: [manual]`, zodat formatteren nog wel BEWUST kan "
            "met `pre-commit run --hook-stage manual`."
        )

    def test_config_documents_why_the_hooks_are_manual(self) -> None:
        """De reden staat in het bestand zelf, niet alleen in een commit-boodschap.

        Een volgende lezer die `stages: [manual]` ziet zonder uitleg haalt het weg omdat het
        op een vergissing lijkt.
        """
        content = CONFIG.read_text(encoding="utf-8")
        assert "manual" in content and "818" in content, (
            "De kop van .pre-commit-config.yaml moet uitleggen waarom de muterende hooks op "
            "manual staan, met het gemeten aantal bestanden erbij."
        )
