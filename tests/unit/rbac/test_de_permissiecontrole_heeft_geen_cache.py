"""`RBACService` houdt geen enkele staat vast naast de databasesessie (ADR-036 OP-254).

WAAROM DEZE BEWAKER BESTAAT
---------------------------
Tot 2026-09-18 cachete `user_has_permission` elke autorisatiebeslissing een uur lang
(`config.redis_cache_ttl`, default 3600s), in Redis zodra `REDIS_URL` gezet was. Gemeten
gevolg via de echte methodes: een recht dat met `remove_permission_from_role` van een rol
werd afgenomen bleef `True` geven, en een rol die met `assign_role` werd toegekend bleef
`False` geven -- allebei tot een uur lang, over alle replicas, en bestand tegen een
herstart van de container.

De cache is verwijderd in plaats van gerepareerd. De vier metingen onder dat besluit staan
in de docstring van `RBACService`; de kern is dat hij 2,18 ms per controle opleverde en
daarvoor een invalidatieplicht legde op elke huidige en toekomstige schrijfplek -- een
plicht die op dat moment al op vijf van de zes plekken was vergeten.

WAT DEZE TEST WEL EN NIET TOETST
--------------------------------
WEL: dat de dienst geen staat meebrengt waarin een antwoord bewaard KAN worden. Dat is een
structurele eigenschap (`vars(dienst)`), geen tekstzoekactie -- een cache die onder een
andere naam terugkomt wordt net zo goed betrapt.

NIET: dat een rechtenwijziging daadwerkelijk meteen doorwerkt. Dat vraagt een database en
staat in `tests/integration/security/test_een_rechtenwijziging_werkt_meteen.py`.

**Let op waarom een gedragstest hier vroeger onmogelijk was.** `tests/conftest.py:58` zet
`TESTING=1` bij import, en `user_has_permission` sloeg het cache-LEESpad over zodra
`TESTING=1` of `POSTGRES_DB=test_db`. Geen enkele test in dit project kon die cache dus
ooit zien; een bewaker erop zou per constructie hol zijn geweest. Dat luik is met de cache
meeverdwenen -- komt het terug, dan is deze test weer waardeloos en moet hij mee veranderen.

MUTATIEBEWIJS (2026-09-18, beide richtingen, een regel per bewaakt element)
--------------------------------------------------------------------------
    `self._perm_cache: dict = {}` terug in `__init__`        -> ROOD (extra attribuut)
    `self._redis = Aioredis.from_url(...)` terug in `__init__` -> ROOD (extra attribuut)
    een gewone niet-cache-hulpvariabele toevoegen             -> ROOD, en dat is terecht:
        deze dienst hoort per verzoek te worden gemaakt en niets vast te houden
    ongewijzigd                                               -> GROEN
"""

from __future__ import annotations

from unittest.mock import MagicMock

from src.core.services.rbac_service import RBACService

#: De ENIGE toestand die deze dienst mag dragen.
TOEGESTANE_ATTRIBUTEN = {"db"}


def test_de_dienst_draagt_alleen_de_databasesessie() -> None:
    """Elk extra attribuut is een plek waar een antwoord kan blijven hangen."""
    dienst = RBACService(MagicMock())

    extra = sorted(set(vars(dienst)) - TOEGESTANE_ATTRIBUTEN)

    assert not extra, (
        f"`RBACService` draagt naast de databasesessie ook: {extra}.\n\n"
        "Tot 2026-09-18 was dat een permissiecache met een TTL van een uur, en die liet een "
        "ingetrokken recht een uur doorwerken (ADR-036 OP-254). Komt hier weer staat bij, "
        "dan hoort daar een meting bij die laat zien dat 2,18 ms per controle te duur is, "
        "EN een invalidatie die niet aan elke toekomstige schrijfplek hangt -- een "
        "generatieteller in de sleutel, geen wisactie per mutator."
    )


def test_de_dienst_bouwt_geen_eigen_verbinding() -> None:
    """Geen client naar Redis of iets anders: die werd per verzoek gemaakt en nooit gesloten."""
    dienst = RBACService(MagicMock())

    verdacht = [
        naam
        for naam, waarde in vars(dienst).items()
        if naam not in TOEGESTANE_ATTRIBUTEN and waarde is not None
    ]

    assert not verdacht, (
        f"`RBACService` bouwt in `__init__` een eigen object op: {verdacht}. De vorige versie "
        "maakte per verzoek een Redis-client die nergens werd gesloten; onder verkeer liep "
        "dat op. Een gedeelde client hoort uit de applicatiestate te komen, niet uit de "
        "constructor van een dienst die per verzoek wordt gemaakt."
    )
