"""Het auditspoor van `get_secret()` MOET de werkelijke herkomst noemen (ADR-036 OP-243).

**De bevinding.** `SecretProvider.get_secret()` keert bij een cache-hit vroeg terug en logde
tot 2026-09-15 altijd `source=SecretSource.ENV_VAR`. De cache wordt echter na ELKE geslaagde
lookup gevuld, dus vanaf de tweede aanroep voor dezelfde sleutel meldde het spoor
`env_var` ongeacht of de waarde uit een omgevingsvariabele, een `.env`-bestand, een
Kubernetes-secret, een gegenereerde willekeurige waarde of een default kwam.

Waarom dat erger is dan geen spoor: ADR-019 leunt op de auditketen, en een lezer meet niet
opnieuw. Een gegenereerd secret dat als `env_var` geboekt staat, verbergt bovendien dat het
efemeer is en per proces verschilt.

**Beide richtingen, met opzet.** Zonder de tweede test zou "log altijd `DOTENV_FILE`" of
"log altijd `NOT_FOUND`" een geldige oplossing zijn -- en dan is het spoor nog steeds onwaar,
alleen op een andere manier.

**Mutatiebewijs (2026-09-15):** deze twee tests zijn ROOD gedraaid tegen de commit-inhoud van
`dd8869b1` (via `git stash`, niet tegen een kopie) en groen na de wijziging.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from src.core.config.secret_provider import SecretProvider, SecretSource


def _laatste_bron(provider: SecretProvider, sleutel: str) -> SecretSource:
    """De herkomst uit de LAATSTE auditregel voor deze sleutel."""
    regels = [e for e in provider.audit_log if e.secret_key == sleutel]
    assert regels, f"Geen auditregel gevonden voor {sleutel!r}."
    return regels[-1].source


def test_een_waarde_uit_een_dotenv_bestand_heet_geen_omgevingsvariabele(
    tmp_path: Path, monkeypatch
) -> None:
    """Een `.env`-waarde MOET als bestand in het spoor staan, niet als env_var."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("OP243_UIT_BESTAND=waarde-uit-bestand\n", encoding="utf-8")

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("OP243_UIT_BESTAND", None)
        provider = SecretProvider(environment="development")

        assert provider.get_secret("OP243_UIT_BESTAND") == "waarde-uit-bestand"

        bron = _laatste_bron(provider, "OP243_UIT_BESTAND")
        assert bron == SecretSource.DOTENV_FILE, (
            f"De waarde komt uit {tmp_path / '.env'} maar het auditspoor noemt {bron.value!r}. "
            "ADR-019 leunt op dit spoor; een onjuiste herkomst is erger dan geen herkomst."
        )


def test_een_echte_omgevingsvariabele_blijft_env_var_heten(tmp_path: Path, monkeypatch) -> None:
    """De andere richting: correcte gevallen mogen NIET worden omgelabeld.

    Zonder deze helft zou "log altijd DOTENV_FILE" de test hierboven halen, en dan is het
    spoor nog steeds onwaar -- alleen de andere kant op.
    """
    monkeypatch.chdir(tmp_path)  # geen .env-bestanden in deze map

    with patch.dict(os.environ, {"OP243_UIT_OMGEVING": "waarde-uit-omgeving"}):
        provider = SecretProvider(environment="development")

        assert provider.get_secret("OP243_UIT_OMGEVING") == "waarde-uit-omgeving"
        # Tweede aanroep: NU komt hij uit de cache, en juist daar ging het mis.
        assert provider.get_secret("OP243_UIT_OMGEVING") == "waarde-uit-omgeving"

        bron = _laatste_bron(provider, "OP243_UIT_OMGEVING")
        assert bron == SecretSource.ENV_VAR, (
            f"De waarde komt uit os.environ maar het auditspoor noemt {bron.value!r}."
        )
