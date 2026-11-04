"""ADR-036 D2-002/OP-38 (fix-sprint dag 6, bijvangst): `HallucinationGuard.check()` logde de
GEMATCHTE bestandsnaam (potentieel een persoonsnaam, bv. "jan_jansen_salaris.pdf") als los
`file=`-veld via `loguru`, bij het DEFAULT log-niveau (INFO), ook in productie (JSON naar
stdout, zie `src/core/logging/loguru_config.py`). Gevonden door de blinde reviewronde van
dag 6, tijdens het beoordelen van de `sanity_officer.py`-fix voor exact dezelfde databron.

**Waarom alleen `absolute_claim` nog wel `matched=` logt.** Die regel matcht tegen een
ECHT gesloten, vaste woordenlijst (`_ABSOLUTE_CLAIMS`: "always"/"never"/"100%"/...) zonder
enige cijfer- of vrije-tekstcomponent -- de gematchte tekst IS de patroon-classificatie en
kan geen persoonsgegeven bevatten. `_FILE_REFERENCE` matcht een open bestandsnaam-vorm uit
vrije modeltekst, die net als een `action_params`-waarde aanvallerbeinvloed/modelgeschreven
is. **Correctie na blinde reviewronde 2 (2026-08-20)**: de oorspronkelijke tekst hier
beweerde dat `_FABRICATED_STATS` ALS GEHEEL ook een gesloten cijferpatroon was en dus geen
persoonsgegeven kon bevatten. Dat hield niet stand voor de "Nx faster/slower/..."-tak
(`\\d+x ...`): die heeft een ONBEGRENSDE cijferreeks (zelf nagemeten: "0612345678x faster"
matcht), in tegenstelling tot de begrensde percentage-tak (`\\d{2,3}%`, max 3 cijfers). Zie
`test_fabricated_stat_matches_are_not_logged_as_a_field` hieronder voor de fix.

**Wat WEL en NIET verandert.** De RETURN-waarde (`reason_str`, bv.
`"ungrounded_file_ref:jan_jansen_salaris.pdf"`) blijft ongewijzigd -- de aanroeper
(`SanityOfficer`) heeft die nodig om zelf te bepalen wat er niet klopte, en redigeert het al
tot een categorie voordat het de ADR-019-hashketen ingaat (BE-AGT-054). Alleen het LOG-record
verliest het losse veld, voor zowel `ungrounded_file_ref` als `fabricated_stat`.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.core.learning.safety.hallucination_guard import HallucinationGuard


@pytest.mark.unit
def test_the_matched_filename_is_not_logged_as_a_field() -> None:
    """`.py` en niet `.pdf`: `_FILE_REFERENCE` herkent alleen een vaste lijst extensies
    (py/ts/tsx/js/jsx/yaml/yml/json/toml/md) -- zelf nagemeten, niet aangenomen."""
    with patch("src.core.learning.safety.hallucination_guard.logger") as mock_logger:
        is_safe, reason = HallucinationGuard.check("See jan_jansen_salaris.py for details.", {})

    assert is_safe is False
    assert reason == "ungrounded_file_ref:jan_jansen_salaris.py", (
        "De retourwaarde moet de bestandsnaam nog wel bevatten -- de aanroeper heeft die "
        "nodig om zelf te redigeren tot een categorie (zie BE-AGT-054)."
    )

    mock_logger.info.assert_called_once_with("hallucination_guard_ungrounded_file_ref")
    for call in mock_logger.info.call_args_list:
        rendered = str(call)
        assert "jan_jansen_salaris.py" not in rendered, (
            "De gematchte bestandsnaam staat nog in de log-aanroep -- dat kan een "
            "persoonsgegeven zijn en gaat bij het default log-niveau (INFO) ook in productie "
            "als JSON naar stdout."
        )


@pytest.mark.unit
def test_absolute_claim_matches_still_log_the_matched_word() -> None:
    """Regressie: deze tak is NIET gewijzigd -- een vaste woordenlijst kan geen
    persoonsgegeven zijn, dus loggen blijft hier veilig en nuttig voor observability.

    Engelse triggerwoorden, met opzet: `_ABSOLUTE_CLAIMS` matcht alleen de letterlijke
    Engelse woorden ("always", niet "altijd") -- zelf nagemeten, niet aangenomen."""
    with patch("src.core.learning.safety.hallucination_guard.logger") as mock_logger:
        is_safe, reason = HallucinationGuard.check("This always works perfectly.", {})

    assert is_safe is False
    assert reason is not None and reason.startswith("absolute_claim:")
    mock_logger.info.assert_called_once_with("hallucination_guard_absolute_claim", matched="always")


@pytest.mark.unit
def test_fabricated_stat_matches_are_not_logged_as_a_field() -> None:
    """Correctie na blinde reviewronde 2 (2026-08-20): de aanname hieronder (module-docstring,
    "geen van beide kan een persoonsgegeven bevatten") hield niet stand voor deze tak.
    `_FABRICATED_STATS`' percentage-alternatief is begrensd (`\\d{2,3}%`, max 3 cijfers), maar
    de "Nx faster"-tak (`\\d+x\\s+(?:faster|...)`) heeft een ONBEGRENSDE cijferreeks -- zelf
    nagemeten dat `"0612345678x faster"` matcht. Een aanvallergestuurde tekst kan zo een
    telefoonnummer-achtige reeks verbatim laten loggen, dezelfde klasse lek als
    `ungrounded_file_ref`. Fix: zelfde behandeling -- alleen het FEIT dat de regel triggerde
    wordt gelogd. `absolute_claim` blijft WEL ongewijzigd (zie de test hierboven): die matcht
    een echt gesloten, vaste woordenlijst zonder enige cijfer- of vrije-tekstcomponent."""
    with patch("src.core.learning.safety.hallucination_guard.logger") as mock_logger:
        is_safe, reason = HallucinationGuard.check("This runs 0612345678x faster than before.", {})

    assert is_safe is False
    assert reason == "fabricated_stat:0612345678x faster", (
        "De retourwaarde moet de match nog wel bevatten -- ongewijzigd gedrag, alleen het "
        "logrecord verandert."
    )

    mock_logger.info.assert_called_once_with("hallucination_guard_fabricated_stat")
    for call in mock_logger.info.call_args_list:
        rendered = str(call)
        assert "0612345678" not in rendered, (
            "De onbegrensde cijferreeks staat nog in de log-aanroep -- kan een "
            "telefoonnummer-achtig persoonsgegeven zijn en gaat bij het default log-niveau "
            "(INFO) ook in productie als JSON naar stdout."
        )


@pytest.mark.unit
def test_a_bare_percentage_triggers_the_fabricated_stat_rule() -> None:
    """Zie de xfail-reason. Asserteert het GEWENSTE gedrag (een los percentage is een
    fabricated-stat-signaal), niet het huidige kapotte gedrag -- consistent met hoe OP-170
    (forensics.py, zelfde sessie) is vastgelegd."""
    is_safe, reason = HallucinationGuard.check("This is 95% faster than the old version.", {})

    assert is_safe is False and reason is not None and reason.startswith("fabricated_stat:"), (
        "Een los percentage triggerde de fabricated_stat-regel niet zoals bedoeld."
    )
