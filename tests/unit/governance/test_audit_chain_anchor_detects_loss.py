"""Een anker per tenant maakt verwijderen en hash-strippen zichtbaar (ADR-036 OP-118/OP-119).

**De twee bevindingen.**

- OP-119: `DELETE FROM audit_logs WHERE tenant_id = X` gaf `is_valid=True`, en een lege keten
  heet in `get_chain_status` letterlijk `status="healthy", health_percentage=100.0`. Vier
  verifiers zeggen onafhankelijk "leeg = in orde". Er was geen anker: geen opgeslagen ketenkop,
  geen rijtelling.
- OP-118: een aanvaller die een rij wijzigt en daarna `audit_hash` leegmaakt op de LAATSTE rij
  levert `tampering_detected=False, unhashed_entries=1` -- ononderscheidbaar van een oud
  dekkingsgat.

**Waarom het anker in de JOB zit en niet in de verifier.** Een verifier die alleen de tabel leest
KAN niet weten dat er rijen zijn verdwenen -- afwezigheid heeft geen hash. Dat is geen fout in
`verify_chain`; het is de grens van een staatloze controle. Alleen iets dat de VORIGE toestand
onthoudt kan een daling zien. `get_chain_status` blijft dus zeggen wat het ziet, en de job
vergelijkt dat met wat er de vorige keer stond.

**De eerlijke grens, en die hoort in ADR-019 te staan.** Dit anker staat in dezelfde database die
de aanvaller kan schrijven. Het vangt een kapotte opruimjob, een ongeluk, en een aanvaller die het
anker niet kent. Het vangt GEEN aanvaller die het anker meebijwerkt. Pas als de ankerrij zelf is
ondertekend (OP-120, stap 5) is hij niet meer te herschrijven zonder sleutel -- en zelfs dan blijft
VERWIJDEREN van alle ankers een reset van de nulmeting.

**Waarom deze tests een ECHTE sessie gebruiken.** De bestaande tests van deze job
(`tests/unit/test_audit_verification_job.py:311-343`) zetten `mock_tenant.last_verified_at` op een
`MagicMock` en asserteren daarna dat het attribuut niet `None` is. Dat slaagt ook als de kolom
nooit bestaat -- en dat was precies het geval: `Tenant.last_verified_at` bestaat niet, niet op het
model en niet in enige migratie. `store_result()` deed in de praktijk een SELECT en een commit.
Een mock kan dat verschil per constructie niet zien.

**Mutatietest (2026-08-10, beide richtingen):** de vergelijking met het opgeslagen anker
weggehaald -> ROOD op de drie verliestests. Het anker overschreven VOOR de vergelijking -> ROOD.
En de andere kant: een eerste run op een lege tenant -> GROEN, anders zou elke nieuwe tenant een
vals alarm geven.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from src.core.governance.models import AuditChainAnchor
from src.core.jobs.audit_verification import AuditTrailVerificationJob, TenantVerificationResult


def _uitkomst(
    tenant_id: int = 1,
    *,
    total: int,
    head: str | None,
    unhashed: int = 0,
    epoch: int | None = None,
) -> TenantVerificationResult:
    from datetime import datetime, timezone

    return TenantVerificationResult(
        tenant_id=tenant_id,
        is_valid=True,
        total_entries=total,
        verified_entries=total - unhashed,
        broken_at_entry_id=None,
        checked_at=datetime(2026, 8, 10, 3, 0, 0, tzinfo=timezone.utc),
        verification_time_ms=1.0,
        head_hash=head,
        unhashed_entries=unhashed,
        first_keyed_entry_id=epoch,
    )


@pytest.mark.asyncio
class TestTheAnchorDetectsLoss:
    async def test_the_anchor_is_actually_persisted(self, db_session) -> None:
        """Tegen een ECHTE sessie, want een mock accepteert elk attribuut.

        Dit is de test die de oude opzet niet had: `store_result` schreef naar
        `tenant.last_verified_at`, een kolom die niet bestaat. SQLAlchemy kende hem niet, dus er
        werd niets gevlagd en niets weggeschreven -- en de mocktest meldde groen.
        """
        job = AuditTrailVerificationJob(db_session=db_session)

        await job.store_result(_uitkomst(total=42, head="a" * 64))

        anker = (
            await db_session.execute(
                select(AuditChainAnchor).where(AuditChainAnchor.tenant_id == 1)
            )
        ).scalar_one_or_none()

        assert anker is not None, "Er is geen ankerrij weggeschreven."
        assert anker.row_count == 42
        assert anker.head_hash == "a" * 64

    async def test_the_first_run_does_not_alarm(self, db_session) -> None:
        """De tweede richting: zonder dit zou 'meld altijd verlies' een geldige oplossing zijn."""
        job = AuditTrailVerificationJob(db_session=db_session)

        afwijkingen = await job.store_result(_uitkomst(total=10, head="b" * 64))

        assert afwijkingen == [], (
            f"Een eerste run op een tenant zonder anker meldt {afwijkingen}. Elke nieuwe tenant "
            "zou dan een vals alarm geven, en dan gelooft niemand het signaal nog."
        )

    async def test_a_row_count_drop_is_detected(self, db_session) -> None:
        """OP-119: de kern. Rijen verdwijnen is vandaag volledig onzichtbaar."""
        job = AuditTrailVerificationJob(db_session=db_session)
        await job.store_result(_uitkomst(total=500, head="c" * 64))

        afwijkingen = await job.store_result(_uitkomst(total=10, head="d" * 64))

        assert any(a.soort == "row_count_drop" for a in afwijkingen), (
            f"Een daling van 500 naar 10 auditregels wordt niet gemeld. Gevonden: {afwijkingen}. "
            "Zonder dit is `DELETE FROM audit_logs WHERE tenant_id = X` onzichtbaar -- de "
            "verifier meldt dan 'healthy, 100%' over een lege tabel."
        )

    async def test_an_emptied_chain_is_the_loudest_case(self, db_session) -> None:
        """De vorm uit OP-119 letterlijk: alles weg, en de verifier noemt dat gezond."""
        job = AuditTrailVerificationJob(db_session=db_session)
        await job.store_result(_uitkomst(total=500, head="c" * 64))

        afwijkingen = await job.store_result(_uitkomst(total=0, head=None))

        assert any(a.soort == "row_count_drop" for a in afwijkingen), (
            "Een tenant waarvan de HELE auditketen is verdwenen levert geen melding op."
        )

    async def test_a_rewritten_head_with_the_same_count_is_detected(self, db_session) -> None:
        """Zelfde aantal rijen, andere kop: iemand heeft geschiedenis herschreven.

        Een telling alleen is niet genoeg -- wie een rij vervangt houdt het aantal gelijk.
        """
        job = AuditTrailVerificationJob(db_session=db_session)
        await job.store_result(_uitkomst(total=100, head="e" * 64))

        # Zelfde aantal, maar de kop is een andere: de keten is niet gegroeid maar veranderd.
        afwijkingen = await job.store_result(_uitkomst(total=100, head="f" * 64))

        assert any(a.soort == "head_changed_without_growth" for a in afwijkingen), (
            f"De kop is veranderd terwijl het aantal rijen gelijk bleef, en dat wordt niet "
            f"gemeld. Gevonden: {afwijkingen}."
        )

    async def test_growth_with_a_new_head_is_normal(self, db_session) -> None:
        """De tweede richting op de vorige test: gewoon doorschrijven is geen afwijking."""
        job = AuditTrailVerificationJob(db_session=db_session)
        await job.store_result(_uitkomst(total=100, head="e" * 64))

        afwijkingen = await job.store_result(_uitkomst(total=140, head="f" * 64))

        assert afwijkingen == [], (
            f"Een keten die groeit krijgt een nieuwe kop -- dat is de normale gang van zaken en "
            f"mag geen melding geven. Gevonden: {afwijkingen}."
        )

    async def test_new_unhashed_rows_are_detected(self, db_session) -> None:
        """OP-118: het watermerk.

        Nu alle schrijvers de keten vullen, is elke NIEUWE ongehashte rij per definitie verdacht.
        Zonder watermerk is hash-strippen niet te onderscheiden van een oud dekkingsgat.
        """
        job = AuditTrailVerificationJob(db_session=db_session)
        await job.store_result(_uitkomst(total=100, head="e" * 64, unhashed=7))

        afwijkingen = await job.store_result(_uitkomst(total=110, head="f" * 64, unhashed=9))

        assert any(a.soort == "unhashed_increase" for a in afwijkingen), (
            f"Twee nieuwe ongehashte rijen worden niet gemeld. Gevonden: {afwijkingen}. Het "
            "bestaande aantal is een bekend gat (OP-108); een TOENAME is dat niet."
        )

    async def test_a_stable_unhashed_count_is_not_an_alarm(self, db_session) -> None:
        """De tweede richting: het bekende gat uit OP-108 mag niet elke dag afgaan."""
        job = AuditTrailVerificationJob(db_session=db_session)
        await job.store_result(_uitkomst(total=100, head="e" * 64, unhashed=7))

        afwijkingen = await job.store_result(_uitkomst(total=110, head="f" * 64, unhashed=7))

        assert afwijkingen == [], (
            f"Een ONVERANDERD aantal ongehashte rijen geeft een melding: {afwijkingen}. Dat getal "
            "is per constructie hoger dan nul voor elke bestaande tenant, dus dan gaat het alarm "
            "elke dag af en zet iemand het uit."
        )


def test_the_dead_result_class_is_gone() -> None:
    """`AuditVerificationResult` was een klasse zonder `Base` en zonder `__tablename__`.

    Nul gebruikers in `src/` en `tests/`, en de naam suggereerde dat er iets werd opgeslagen
    terwijl dat niet zo was. Dat is precies het soort code dat een lezer laat denken dat een gat
    gedekt is.
    """
    import src.core.jobs.audit_verification as job_module

    assert not hasattr(job_module, "AuditVerificationResult"), (
        "De dode klasse `AuditVerificationResult` bestaat nog. Hij wekt de indruk dat "
        "verificatieresultaten worden opgeslagen; dat gebeurde niet."
    )


@pytest.mark.asyncio
class TestTheEpochIsRecordedOnce:
    """Het knippunt voor OP-120 wordt automatisch vastgelegd en daarna nooit verlaagd.

    Zonder knippunt is teruggaan naar het sleutelloze algoritme een geldige manier om de HMAC te
    omzeilen: schrijf een legacy-rij met een kloppende SHA-256 en alles verifieert. Het knippunt
    maakt zo'n rij NA de omschakeling zelf tot een afwijking.

    **Waarom het nooit omlaag mag.** Zou het meebewegen met de laagste gesleutelde rij, dan
    verschuift een aanvaller het knippunt simpelweg door een oude rij te vervangen -- en dan valt
    alles ervoor weer buiten de controle.

    **Mutatietest (2026-08-11, beide richtingen):** de "niet verlagen"-voorwaarde weggehaald ->
    ROOD. Het zetten van het knippunt weggehaald -> ROOD. En de andere kant: een tenant zonder
    enige gesleutelde rij krijgt GEEN knippunt, anders zou elke legacy-tenant zichzelf als
    afwijkend melden.
    """

    async def test_the_epoch_is_set_once_the_first_keyed_row_appears(self, db_session) -> None:
        job = AuditTrailVerificationJob(db_session=db_session)
        await job.store_result(_uitkomst(total=10, head="a" * 64))

        await job.store_result(_uitkomst(total=12, head="b" * 64, epoch=11))

        anker = (
            await db_session.execute(
                select(AuditChainAnchor).where(AuditChainAnchor.tenant_id == 1)
            )
        ).scalar_one_or_none()
        assert anker is not None and anker.chain_epoch_id == 11, (
            "Het knippunt wordt niet vastgelegd zodra de eerste gesleutelde rij bestaat. Zonder "
            "knippunt is terugvallen op het oude algoritme een geldige omzeiling van de sleutel."
        )

    async def test_the_epoch_is_never_lowered(self, db_session) -> None:
        """De tweede richting op de belangrijkste eigenschap."""
        job = AuditTrailVerificationJob(db_session=db_session)
        await job.store_result(_uitkomst(total=12, head="b" * 64, epoch=11))

        await job.store_result(_uitkomst(total=14, head="c" * 64, epoch=3))

        anker = (
            await db_session.execute(
                select(AuditChainAnchor).where(AuditChainAnchor.tenant_id == 1)
            )
        ).scalar_one_or_none()
        assert anker is not None and anker.chain_epoch_id == 11, (
            f"Het knippunt is verlaagd naar {anker.chain_epoch_id if anker else None}. Dan "
            "verschuift een aanvaller het simpelweg door een oude rij te vervangen, en valt "
            "alles ervoor weer buiten de controle."
        )

    async def test_a_tenant_without_keyed_rows_gets_no_epoch(self, db_session) -> None:
        """Anders zou elke bestaande, nog niet omgeschakelde tenant zichzelf als afwijkend melden."""
        job = AuditTrailVerificationJob(db_session=db_session)
        await job.store_result(_uitkomst(total=10, head="a" * 64))

        anker = (
            await db_session.execute(
                select(AuditChainAnchor).where(AuditChainAnchor.tenant_id == 1)
            )
        ).scalar_one_or_none()
        assert anker is not None and anker.chain_epoch_id is None
