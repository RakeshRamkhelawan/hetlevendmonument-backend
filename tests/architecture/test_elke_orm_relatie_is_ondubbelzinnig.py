"""Elke ORM-relatie moet te configureren zijn -- anders valt hij pas in gebruik om.

WAAROM DEZE TEST BESTAAT
------------------------
SQLAlchemy bouwt een relatie pas op het moment dat hij hem NODIG heeft. Tot dat moment
kan een kapotte relatie ongemerkt in de modellen staan. Dat ging op 2026-09-15/16 mis en
het kostte de hele poort:

Voor ADR-036 OP-160 zijn twee SAMENGESTELDE foreign keys aan
`user_persona_preferences` toegevoegd, zodat het model beschrijft wat de database al
afdwingt. Daarmee wees die tabel op TWEE manieren naar `personas`:

    persona_id                -> personas.id                     (enkelvoudig)
    (persona_id, tenant_id)   -> personas(id, tenant_id)          (samengesteld)

`relationship("Persona", back_populates="user_preferences")` zonder `foreign_keys` kan
dan niet meer bepalen waarop gekoppeld moet worden en werpt `AmbiguousForeignKeysError`.

Het verraderlijke zit in WANNEER dat gebeurt. Op 2026-09-15 bleef de fout onzichtbaar,
want in de meeste testruns werden die twee modellen niet samen geladen. Op 2026-09-16
trokken een paar nieuwe imports de rest van de modelgraaf wel mee, en toen sloeg dezelfde
regel code ineens op **371 tests** toe -- in bestanden die niets met persona's te maken
hebben. Een dag zoeken in de verkeerde hoek, om iets dat al die tijd in de modellen stond.

`configure_mappers()` dwingt SQLAlchemy om ELKE relatie meteen op te bouwen. Dat is
precies de aanroep die dit soort fouten van "valt om zodra iemand de verkeerde twee
modellen samen importeert" terugbrengt naar "valt om in de poort, met de naam erbij".

MUTATIEBEWIJS (2026-09-16, beide richtingen)
--------------------------------------------
- `foreign_keys` weggehaald bij `Persona.user_preferences`     -> ROOD
  (AmbiguousForeignKeysError, met `personas` en `user_persona_preferences` bij naam)
- `foreign_keys` weggehaald bij `UserPersonaPreference.persona` -> ROOD
- ongewijzigde boom                                             -> GROEN
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import configure_mappers


@pytest.mark.architecture
def test_alle_ormrelaties_zijn_te_configureren() -> None:
    """Elke `relationship()` in de codebase moet ondubbelzinnig zijn.

    De import van `import_all_models` is het punt: die registreert ALLE modellen op
    dezelfde metadata. Zonder die import zou `configure_mappers()` alleen de modellen
    toetsen die toevallig al geladen waren -- en dat is precies de blinde vlek die deze
    test opheft.
    """
    import src.core.database.import_all_models  # noqa: F401  (vult de modelregistratie)

    try:
        configure_mappers()
    except Exception as fout:  # noqa: BLE001 -- de soort fout is hier niet te voorspellen
        pytest.fail(
            "Een ORM-relatie kan niet worden opgebouwd. Dit valt in productie pas om "
            "zodra de betrokken modellen samen worden geladen, en dan op een plek die "
            "niets met de oorzaak te maken heeft.\n\n"
            f"{type(fout).__name__}: {fout}\n\n"
            "Meestal betekent dit dat er meer dan een foreign key tussen dezelfde twee "
            "tabellen bestaat (bijvoorbeeld een enkelvoudige EN een samengestelde voor "
            "tenant-integriteit). Geef de relatie dan een expliciete `foreign_keys` of "
            "`primaryjoin` -- zie `src/core/models/persona_models.py` voor het voorbeeld "
            "dat deze test heeft opgeleverd (ADR-036 OP-160)."
        )
