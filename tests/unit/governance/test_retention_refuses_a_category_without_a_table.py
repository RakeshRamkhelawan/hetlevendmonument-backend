"""Een categorie zonder doeltabel levert een weigering op, geen opruiming van `audit_logs`.

**De bevinding (ADR-036 OP-115, hermeten 2026-08-29).** `_get_table_info` eindigde op

    return table_mapping.get(category, {"table": "audit_logs", ...})

Vijf categorieen die de dagelijkse job doorloopt stonden niet in die afbeelding, en
`FINANCIAL` en `HEALTH` wezen er zelfs expliciet naar met de comment `# Fallback to
audit_logs`. Voor die twee was de route naar de auditketen dus niet latent maar de actieve
configuratie.

Drie gevolgen, alle drie zonder enige foutmelding:

1. de retentie voor die categorieen draaide NIET, terwijl de job succes meldde;
2. een `DELETE` richtte zich op `audit_logs` -- en een verwijderde rij breekt de hashketen
   door AFWEZIGHEID, wat geen enkele hash-reparatie herstelt;
3. het retentierapport telde voor ELKE ongemapte categorie dezelfde `audit_logs`-rijen mee,
   dus zowel `total_records` als de uitsplitsing per categorie waren onjuist.

**Wat hier wordt vastgelegd.** Weigeren in plaats van gokken, en het verschil tussen "niets te
verwijderen" en "niet beslist waar" zichtbaar houden: in het rapport als
`categories_without_table`, in de job als `skipped`.

**Wat bewust NIET wordt vastgelegd.** Welke tabel elk van die categorieen zou moeten krijgen.
Dat is een inhoudelijke keuze (waar staan financiele en medische gegevens?) en staat open;
`tests/architecture/test_retention_categories_have_a_table.py` bewaakt de lijst.

**Mutatietest (2026-08-30, beide richtingen):** de `.get(category, {...})`-vorm teruggezet ->
ROOD op alle drie de tests hieronder. Weer weggehaald -> GROEN. En de tegenrichting: een
GEMAPTE categorie (`AUDIT_LOG`) moet gewoon werken, anders zou "weiger altijd" een geldige
oplossing zijn en ruimt het systeem nergens meer iets op.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.governance.retention_cleanup import (
    DataCategory,
    RetentieDoeltabelOntbreekt,
    RetentionCleanupService,
    RetentionJurisdiction,
)


def _sessie() -> AsyncMock:
    sessie = AsyncMock()
    sessie.execute = AsyncMock(
        return_value=MagicMock(rowcount=3, scalar=MagicMock(return_value=0))
    )
    return sessie


@pytest.mark.unit
class TestEenCategorieZonderDoeltabel:
    def test_de_afbeelding_weigert_in_plaats_van_te_gokken(self) -> None:
        """De kern: geen sleutel betekent geen antwoord."""
        dienst = RetentionCleanupService(_sessie(), tenant_id=7)

        with pytest.raises(RetentieDoeltabelOntbreekt, match="analytics"):
            dienst._get_table_info(DataCategory.ANALYTICS)

    def test_financial_en_health_wijzen_niet_meer_naar_de_auditketen(self) -> None:
        """Deze twee stonden expliciet op `audit_logs`; dat was de actieve configuratie."""
        dienst = RetentionCleanupService(_sessie(), tenant_id=7)

        for categorie in (DataCategory.FINANCIAL, DataCategory.HEALTH):
            with pytest.raises(RetentieDoeltabelOntbreekt):
                dienst._get_table_info(categorie)

    def test_een_gemapte_categorie_werkt_gewoon(self) -> None:
        """De tegenrichting: zonder deze helft zou "weiger altijd" ook slagen."""
        dienst = RetentionCleanupService(_sessie(), tenant_id=7)

        info = dienst._get_table_info(DataCategory.AUDIT_LOG)

        assert info["table"] == "audit_logs"
        assert info["date_column"] == "timestamp"

    @pytest.mark.asyncio
    async def test_het_rapport_telt_een_ongemapte_categorie_niet_stil_mee(self) -> None:
        """Het rapport benoemt wat het niet kon meten, in plaats van audit_logs op te tellen."""
        dienst = RetentionCleanupService(_sessie(), tenant_id=7)

        rapport = await dienst.generate_retention_report(RetentionJurisdiction.EU)

        assert "analytics" in rapport.categories_without_table
        assert "financial" in rapport.categories_without_table
        assert "health" in rapport.categories_without_table
        assert "analytics" not in rapport.records_by_category, (
            "Een categorie zonder doeltabel hoort niet met een getal in het rapport te staan; "
            "dat getal zou de rijen van `audit_logs` zijn (ADR-036 OP-115)."
        )
        assert "audit_log" in rapport.records_by_category, (
            "De gemapte categorieen moeten er WEL in staan, anders is het rapport leeg "
            "gemaakt in plaats van eerlijk."
        )
