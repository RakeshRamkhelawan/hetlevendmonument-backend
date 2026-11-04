"""De retentietaak gaat categorieen af die hij ook DAADWERKELIJK kan opruimen.

WAAROM DEZE BEWAKER BESTAAT
---------------------------
Tot 2026-09-17 ging `cleanup_by_jurisdiction` een HANDMATIGE lijst van vijf categorieen af:

    USER_DATA, ACTIVITY_LOGS, AI_INTERACTIONS, DOCUMENTS, ANALYTICS

Geen van die vijf heeft een retentiebeleid in `DEFAULT_POLICIES`, en geen van die vijf heeft
een doeltabel in `RetentionCleanupService._get_table_info`. Gemeten: de doorsnede van die
lijst met "heeft beleid EN doeltabel" was LEEG. De taak kon dus nooit een rij verwijderen,
in geen enkele jurisdictie, en dat is zo gebleven zolang hij bestaat.

Zo zag een echte run op staging eruit:

    "total_records_deleted": 0, "total_errors": 0, "completed": true

Nul verwijderd, nul fouten, geslaagd. De reden stond in het veld `skipped` -- vijf keer
"heeft geen doeltabel" per jurisdictie -- maar niemand leest de uitvoer van een nachtelijke
taak die meldt dat hij geslaagd is. Precies waar het runbook voor waarschuwt: "een worker
die nul rijen ziet meldt vrolijk 0 verwerkt".

WAT DEZE TESTS WEL EN NIET ZEGGEN
----------------------------------
Zij toetsen dat de taak WERK HEEFT: elke categorie die hij afgaat heeft een bewaartermijn
en een doeltabel, en het zijn er meer dan nul. Zij toetsen NIET dat er daadwerkelijk rijen
verdwijnen -- daar is een database voor nodig, en dat is op 2026-09-17 apart gemeten tegen
staging (zie de registerrij).

EEN EERDERE VERSIE VAN DIT BESTAND WAS HOL, EN DAT HOORT HIER TE STAAN
-----------------------------------------------------------------------
De eerste versie toetste alleen `te_verwerken_categorieen()` -- de functie die ik zelf net
had geschreven. Toen ik ter controle de OUDE handmatige lijst terugzette in
`cleanup_by_jurisdiction`, bleven alle tests GROEN: ze keken naar de helper, niet naar wat
de taak er daadwerkelijk mee doet. Dat is precies de valkuil "een guard koppelt te grof".

`test_de_taak_gebruikt_die_categorieen_ook_echt` sluit dat gat: die draait
`cleanup_by_jurisdiction` met een testdubbel voor de opruimdienst en kijkt WELKE categorieen
er langskomen. Zonder die test zegt dit bestand niets over de taak.

MUTATIEBEWIJS (2026-09-17, beide richtingen)
---------------------------------------------
    de oude handmatige lijst terugzetten in `cleanup_by_jurisdiction`
        -> ROOD op `test_de_taak_gebruikt_die_categorieen_ook_echt` (vijf jurisdicties)
    `te_verwerken_categorieen` een lege lijst laten geven
        -> ROOD op `test_de_taak_heeft_werk_in_elke_jurisdictie`
    een categorie zonder doeltabel in de lijst laten glippen
        -> ROOD op `test_elke_categorie_heeft_een_doeltabel`
    ongewijzigd
        -> GROEN
"""

from __future__ import annotations

import pytest

from src.core.governance.retention_cleanup import (
    DEFAULT_POLICIES,
    DataCategory,
    RetentionCleanupService,
    RetentionJurisdiction,
)
from src.core.jobs.retention_cleanup_job import _NIET_AUTOMATISCH, te_verwerken_categorieen


def _heeft_doeltabel(categorie: DataCategory) -> bool:
    dienst = RetentionCleanupService.__new__(RetentionCleanupService)
    try:
        return bool(dienst._get_table_info(categorie))
    except Exception:  # noqa: BLE001 -- geen doeltabel is hier het antwoord, geen storing
        return False


@pytest.mark.parametrize("jurisdiction", list(RetentionJurisdiction))
def test_de_taak_heeft_werk_in_elke_jurisdictie(jurisdiction: RetentionJurisdiction) -> None:
    """Nul categorieen betekent een taak die elke nacht niets doet en dat niet meldt."""
    categorieen = te_verwerken_categorieen(jurisdiction)

    assert categorieen, (
        f"De retentietaak gaat voor {jurisdiction.value} NUL categorieen af. Dan verwijdert "
        "hij niets, meldt hij 'completed: true, total_records_deleted: 0', en ziet dat er "
        "precies zo uit als een schone database. Dat is de toestand waarin deze taak tot "
        "2026-09-17 verkeerde."
    )


@pytest.mark.parametrize("jurisdiction", list(RetentionJurisdiction))
def test_elke_categorie_heeft_een_bewaartermijn(jurisdiction: RetentionJurisdiction) -> None:
    """Zonder beleid is er geen grens om op te ruimen."""
    zonder = [
        c.value
        for c in te_verwerken_categorieen(jurisdiction)
        if (jurisdiction, c) not in DEFAULT_POLICIES
    ]

    assert not zonder, (
        f"Deze categorieen worden afgegaan voor {jurisdiction.value} maar hebben daar geen "
        f"bewaartermijn in DEFAULT_POLICIES: {zonder}."
    )


@pytest.mark.parametrize("jurisdiction", list(RetentionJurisdiction))
def test_elke_categorie_heeft_een_doeltabel(jurisdiction: RetentionJurisdiction) -> None:
    """Zonder doeltabel wordt de categorie overgeslagen -- dan is afgaan zinloos."""
    zonder = [c.value for c in te_verwerken_categorieen(jurisdiction) if not _heeft_doeltabel(c)]

    assert not zonder, (
        f"Deze categorieen worden afgegaan voor {jurisdiction.value} maar hebben geen "
        f"doeltabel in `_get_table_info`: {zonder}. Ze worden dus overgeslagen, en de taak "
        "meldt vervolgens 'geslaagd, 0 verwijderd'."
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("jurisdiction", list(RetentionJurisdiction))
async def test_de_taak_gebruikt_die_categorieen_ook_echt(
    jurisdiction: RetentionJurisdiction, monkeypatch: pytest.MonkeyPatch
) -> None:
    """De taak MOET de afgeleide lijst afgaan -- niet een eigen lijst ernaast.

    Dit is de test die het gat dekt waar de eerste versie van dit bestand in viel: de
    helper kan perfect zijn terwijl `cleanup_by_jurisdiction` iets heel anders afgaat.
    Daarom een testdubbel voor de opruimdienst die NOTEERT welke categorieen langskomen.
    """
    from src.core.jobs import retention_cleanup_job as taak

    gevraagd: list[DataCategory] = []

    class _DienstDubbel:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def cleanup_expired_data(
            self, category: DataCategory, jurisdiction: RetentionJurisdiction
        ) -> object:
            gevraagd.append(category)

            class _Uitkomst:
                records_deleted = 0

            return _Uitkomst()

    monkeypatch.setattr(taak, "RetentionCleanupService", _DienstDubbel)
    await taak.cleanup_by_jurisdiction(db=None, jurisdiction=jurisdiction)  # type: ignore[arg-type]

    verwacht = te_verwerken_categorieen(jurisdiction)
    assert gevraagd, (
        f"`cleanup_by_jurisdiction` vroeg voor {jurisdiction.value} NUL categorieen op. "
        "Die taak doet dan elke nacht niets en meldt 'geslaagd'."
    )
    assert gevraagd == verwacht, (
        f"`cleanup_by_jurisdiction` gaat voor {jurisdiction.value} andere categorieen af "
        f"dan `te_verwerken_categorieen` oplevert.\n"
        f"  afgegaan : {[c.value for c in gevraagd]}\n"
        f"  verwacht : {[c.value for c in verwacht]}\n"
        "Een tweede, handmatige lijst naast de afgeleide is precies hoe deze taak tot "
        "2026-09-17 nul rijen opruimde zonder dat iemand het zag."
    )


def test_de_bewuste_uitsluitingen_hebben_een_reden_en_bestaan_nog() -> None:
    """Een uitsluiting zonder reden is een vergeten regel; een uitsluiting van een
    categorie die niet meer bestaat is dode tekst die de volgende lezer misleidt."""
    zonder_reden = [c.value for c, reden in _NIET_AUTOMATISCH.items() if len(reden.strip()) < 40]
    assert not zonder_reden, f"Uitsluiting zonder inhoudelijke reden: {zonder_reden}"

    geen_tabel = [c.value for c in _NIET_AUTOMATISCH if not _heeft_doeltabel(c)]
    assert not geen_tabel, (
        f"Deze uitsluitingen slaan nergens meer op -- de categorie heeft toch al geen "
        f"doeltabel, dus uitsluiten voegt niets toe: {geen_tabel}."
    )
