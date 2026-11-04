"""De opruimactor weigert te verwijderen zonder tenant (ADR-036 OP-123).

**De bevinding.** `_delete_expired_records` voegde de tenantconditie alleen toe als
`self.tenant_id is not None`:

    if self.tenant_id is not None:
        query += f" AND {tenant_col} = :tenant_id"

Bij `None` werd het dus `DELETE FROM <tabel> WHERE <datum> < :cutoff` -- over ALLE tenants.
De query gaat via `text()`, dus de ORM-tenantfilter grijpt hier niet in; die `if` was de enige
isolatie.

**Waarom dat erger is dan het lijkt.** De vijf categorieen die de dagelijkse job opruimt
(`USER_DATA`, `ACTIVITY_LOGS`, `AI_INTERACTIONS`, `DOCUMENTS`, `ANALYTICS`) staan geen van alle
in `table_mapping` en vallen door naar de default -- en die wijst naar `audit_logs` (OP-115). De
latente route wijst dus naar precies de keten waar het hele OP-108-traject over ging, en een
verwijderde rij breekt die keten door AFWEZIGHEID.

**Categoriekeuze in deze tests (2026-08-30).** Ze gebruikten `ANALYTICS`, een categorie zonder
doeltabel. Sinds OP-115 golf 2 weigert `_get_table_info` zo'n categorie VOOR de tenantcontrole
wordt bereikt, en dan meet deze test niet meer wat hij wil meten. Ze draaien nu op `AUDIT_LOG`:
gemapt, en meteen de tabel waar de bevinding over gaat.

**Vandaag latent, niet actief.** Het enige productiepad (`run_retention_cleanup` ->
`cleanup_by_jurisdiction(db, jurisdiction, tenant_id=tenant_id)`) geeft altijd een concrete
tenant mee. Maar `cleanup_by_jurisdiction` heeft `tenant_id: int | None = None` als default, en
de docstring noemt de parameter niet eens.

**Waarom weigeren en niet stilzwijgend alles opruimen.** Een cross-tenant DELETE hoort een
expliciete `TenantFilterBypass` te vragen. Een default die per ongeluk alles raakt is precies de
vorm die dit project elders al heeft opgeruimd.

**Wat hier stond en niets deed.** `test_cleanup_respects_tenant_isolation` in
`test_retention_cleanup_service.py` heet alsof het dit dekt, maar de functie eindigt op een
comment en bevat NUL assertions -- hij kan niet falen. Die is vervangen; zie daar.

**Mutatietest (2026-08-11, beide richtingen):** de weigering weggehaald -> ROOD. De weigering ook
op het TEL-pad gezet -> ROOD op `test_counting_without_a_tenant_still_works` (dat pad is bewust
ongemoeid gelaten, zie de toelichting daar). En met een tenant -> gewoon verwijderen, anders zou
"weiger altijd" een geldige oplossing zijn.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.governance.retention_cleanup import (
    DataCategory,
    RetentionCleanupService,
    RetentionJurisdiction,
)

_CUTOFF = datetime(2019, 1, 1, tzinfo=timezone.utc)


def _sessie() -> AsyncMock:
    sessie = AsyncMock()
    sessie.execute = AsyncMock(return_value=MagicMock(rowcount=3, scalar=MagicMock(return_value=0)))
    return sessie


@pytest.mark.asyncio
class TestTheCleanupRefusesWithoutATenant:
    async def test_deleting_without_a_tenant_is_refused(self) -> None:
        """De kern: zonder tenant is dit een DELETE over alle tenants."""
        dienst = RetentionCleanupService(_sessie())  # geen tenant_id
        tabel = {"table": "audit_logs", "date_column": "timestamp", "tenant_column": "tenant_id"}

        with pytest.raises(ValueError, match="tenant"):
            await dienst._delete_expired_records(tabel, _CUTOFF)

    async def test_the_scheduled_path_still_deletes(self) -> None:
        """De tweede richting: met een tenant moet het gewoon werken.

        Zonder deze test zou "weiger altijd" een geldige oplossing zijn, en dan draait de
        retentie nergens meer -- een GDPR-verplichting die stil stopt.
        """
        sessie = _sessie()
        dienst = RetentionCleanupService(sessie, tenant_id=7)
        tabel = {"table": "audit_logs", "date_column": "timestamp", "tenant_column": "tenant_id"}

        verwijderd = await dienst._delete_expired_records(tabel, _CUTOFF)

        assert verwijderd == 3
        sql = str(sessie.execute.await_args_list[0].args[0])
        assert "tenant_id = :tenant_id" in sql, (
            f"De tenantconditie ontbreekt in de DELETE. SQL was:\n{sql}"
        )
        assert sessie.execute.await_args_list[0].args[1]["tenant_id"] == 7

    async def test_the_full_cleanup_path_refuses_too(self) -> None:
        """Niet alleen de private methode -- ook de weg die de job neemt."""
        dienst = RetentionCleanupService(_sessie())

        with pytest.raises(ValueError, match="tenant"):
            await dienst.cleanup_expired_data(
                category=DataCategory.AUDIT_LOG,
                jurisdiction=RetentionJurisdiction.EU,
            )

    async def test_a_dry_run_without_a_tenant_is_refused_as_well(self) -> None:
        """Ook deze test legde het tegenovergestelde vast, en die redenering klopte niet.

        De vorige versie heette `test_a_dry_run_without_a_tenant_is_still_allowed` met als
        argument: een dry-run verwijdert niets, en je hebt hem nodig om te meten hoeveel er
        opgeruimd zou worden zonder eerst een tenant te kiezen.

        Dat argument gaat voorbij aan wat een dry-run WEL doet: hij telt. Zonder tenant telt hij
        over alle tenants, en dat is precies de cross-tenant lezing die OP-129 dichtzet. Het
        "gereedschap om de bevinding te onderzoeken" was dus zelf een instantie van de bevinding.

        Meten kan nog steeds -- met een tenant. Wie een totaal over alle tenants wil, vraagt
        expliciet om een `TenantFilterBypass`; dan staat die keuze in de code in plaats van in een
        weggelaten `if`.
        """
        dienst = RetentionCleanupService(_sessie())

        with pytest.raises(ValueError, match="tenant"):
            await dienst.cleanup_expired_data(
                category=DataCategory.AUDIT_LOG,
                jurisdiction=RetentionJurisdiction.EU,
                dry_run=True,
            )

    async def test_a_dry_run_with_a_tenant_still_measures(self) -> None:
        """De tweede richting: met een tenant blijft de dry-run gewoon meten."""
        dienst = RetentionCleanupService(_sessie(), tenant_id=7)

        uitkomst = await dienst.cleanup_expired_data(
            category=DataCategory.AUDIT_LOG,
            jurisdiction=RetentionJurisdiction.EU,
            dry_run=True,
        )

        assert uitkomst.dry_run is True

    async def test_counting_without_a_tenant_is_refused_too(self) -> None:
        """Hier stond het TEGENOVERGESTELDE, en dat is nu weerlegd (ADR-036 OP-129).

        De vorige versie heette `test_counting_without_a_tenant_still_works` en legde vast dat de
        vier LEZENDE methodes bewust ongemoeid bleven. De reden daarvoor was dat
        `get_retention_summary` de service bewust zonder tenant construeert, en dat de vraag of een
        cross-tenant TOTAAL daar mag niet uit de code te beantwoorden viel.

        Gemeten op 2026-08-11: `get_retention_summary` heeft NUL aanroepers -- niet in `src/`, niet
        in `scripts/`, ook niet dynamisch op naam. Een eerdere type-audit noteerde dat al
        (`docs/type-audit/batch-03/02b-callers/downstream-caller-check.md:50`). De enige
        rechtvaardiging voor de uitzondering was dus dode code, en daarmee vervalt de vraag: tellen
        over alle tenants heeft geen aanroeper die het nodig heeft.

        Een telling zonder tenant is een cross-tenant LEZING -- een datalek in plaats van
        dataverlies, maar wel over dezelfde tabellen die via de default `audit_logs` zijn (OP-115).
        """
        dienst = RetentionCleanupService(_sessie())
        tabel = {"table": "audit_logs", "date_column": "timestamp", "tenant_column": "tenant_id"}

        with pytest.raises(ValueError, match="tenant"):
            await dienst._count_expired_records(tabel, _CUTOFF)

        with pytest.raises(ValueError, match="tenant"):
            await dienst._count_all_records(tabel)

        with pytest.raises(ValueError, match="tenant"):
            await dienst._count_near_expiry_records(tabel, _CUTOFF, _CUTOFF)

        with pytest.raises(ValueError, match="tenant"):
            await dienst.count_expiring_soon(
                category=DataCategory.AUDIT_LOG,
                jurisdiction=RetentionJurisdiction.EU,
            )

    async def test_counting_with_a_tenant_still_works(self) -> None:
        """De tweede richting: met een tenant moet tellen gewoon werken.

        Zonder deze helft zou "weiger altijd" een geldige oplossing zijn, en dan is de
        retentierapportage stuk in plaats van veilig.
        """
        sessie = _sessie()
        dienst = RetentionCleanupService(sessie, tenant_id=7)
        tabel = {"table": "audit_logs", "date_column": "timestamp", "tenant_column": "tenant_id"}

        await dienst._count_expired_records(tabel, _CUTOFF)

        sql = str(sessie.execute.await_args_list[0].args[0])
        assert "tenant_id = :tenant_id" in sql, (
            f"De tenantconditie ontbreekt in de telling. SQL was:\n{sql}"
        )
        assert sessie.execute.await_args_list[0].args[1]["tenant_id"] == 7
