"""Zonder tenantcontext mag de filter alleen TENANT-tabellen leegmaken (ADR-036 OP-157, D1).

`src/core/database/tenant_query_filter.py` heeft twee takken die dezelfde vraag
beantwoorden -- "hoort deze entiteit bij een tenant?" -- en ze doen dat verschillend:

    MET tenant    (regel ~204): `if entity_class and hasattr(entity_class, "tenant_id")`
                                -> een tabel zonder die kolom wordt met rust gelaten
    ZONDER tenant (regel ~157): `statement.where(literal(False))`
                                -> ALLES wordt leeggemaakt, ook tabellen zonder tenant_id

Die divergentie is het defect. Een tabel zonder `tenant_id` bevat per definitie geen
gegevens van een andere klant; leegmaken beschermt niets en breekt wel.

**Wat het in productie deed, gemeten 2026-08-17 tegen echte PostgreSQL:**

    rij staat in de database (raw SQL)                : 1
    ORM ZONDER tenantcontext (= het /api/v1/auth-pad) : None
    ORM MET tenantcontext                             : <TokenBlacklist(...)>

    >> _is_token_blacklisted() geeft: False   ("niet ingetrokken")
    >> is_token_valid() geeft dan   : True

`token_blacklist` heeft geen `tenant_id`, en `/api/v1/auth/*` is bij ontwerp van
tenantcontext uitgesloten (`tenant_middleware.py:75-82`). Uitloggen en tokenintrekking
deden daardoor niets: de INSERT slaagt (de filter raakt INSERT niet aan, regel ~171) maar
de SELECT vindt hem nooit.

Deze module toetst het GEDRAG, niet de implementatie: een andere oplossing die
tenantloze tabellen met rust laat en tenant-tabellen wel afschermt, mag deze tests net zo
goed halen.

**Mutatiebewijs (2026-08-17), per bewaakt element en in beide richtingen:**
- De entiteitscontrole uit de geen-tenant-tak gehaald ->
  `test_a_table_without_a_tenant_column_is_readable_without_tenant_context` ROOD.
- `hasattr(..., "tenant_id")` omgedraaid naar `not hasattr(...)` ->
  `test_a_tenant_table_still_returns_nothing_without_tenant_context` ROOD. Zonder die
  helft zou "filter nooit iets" een geldige oplossing zijn, en dat is het lek zelf.
- `audit_logs` uit de uitzondering gehaald -> `test_audit_logs_stays_readable` ROOD.
- Ongewijzigd -> GROEN.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import Integer, String, create_engine, event, select
from sqlalchemy.orm import Mapped, Session, declarative_base, mapped_column

from src.core.database.tenant_query_filter import init_tenant_auto_filtering
from src.core.middleware.tenant_context import clear_tenant_context, set_tenant_id

_Base = declarative_base()


class _ZonderTenant(_Base):  # type: ignore[misc, valid-type]
    """Zoals `token_blacklist`: een tabel die niets met tenants te maken heeft."""

    __tablename__ = "proef_zonder_tenant"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    jti: Mapped[str] = mapped_column(String(64))


class _MetTenant(_Base):  # type: ignore[misc, valid-type]
    """Zoals `users`: tenant-gescheiden, moet WEL worden afgeschermd."""

    __tablename__ = "proef_met_tenant"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(Integer)


class _AuditAchtig(_Base):  # type: ignore[misc, valid-type]
    """Zoals `audit_logs`: heeft een tenant_id maar is bewust tenant-overstijgend."""

    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(Integer)


@pytest.fixture
def sessie() -> Iterator[Session]:
    """Een echte SQLite-sessie met de guard erop -- geen mocks.

    SQLite kent geen Row Level Security, maar deze hook is de APPLICATIElaag en werkt
    daar identiek. Daarmee draait dit bewijs mee in de blokkerende CI-stap in plaats van
    achter een `skipif(not postgres)`.
    """
    engine = create_engine("sqlite://")
    _Base.metadata.create_all(engine)
    # De listener hangt aan de Session-KLASSE met propagate=True: laat staan en hij
    # filtert elke ORM-query in dit proces, ook die van een ander testbestand (ADR-036
    # OP-20). Vandaar de expliciete opruiming in het `finally`.
    listener = init_tenant_auto_filtering()

    with Session(engine) as s:
        s.add_all(
            [
                _ZonderTenant(id=1, jti="ingetrokken-token"),
                _MetTenant(id=1, tenant_id=1),
                _MetTenant(id=2, tenant_id=2),
                _AuditAchtig(id=1, tenant_id=1),
            ]
        )
        s.commit()
        clear_tenant_context()
        try:
            yield s
        finally:
            clear_tenant_context()
            event.remove(Session, "do_orm_execute", listener)


@pytest.mark.unit
def test_a_table_without_a_tenant_column_is_readable_without_tenant_context(
    sessie: Session,
) -> None:
    """De kern: geen tenant_id-kolom betekent niets af te schermen.

    Dit is precies het pad waarop `_is_token_blacklisted` een ingetrokken token niet meer
    terugvond.
    """
    gevonden = sessie.execute(
        select(_ZonderTenant).where(_ZonderTenant.jti == "ingetrokken-token")
    ).scalar_one_or_none()

    assert gevonden is not None, (
        "Een tabel ZONDER tenant_id werd leeggemaakt omdat er geen tenantcontext was. Die "
        "tabel bevat per definitie geen gegevens van een andere klant, dus dit beschermt "
        "niets en breekt wel: op dit pad bleven ingetrokken tokens geldig."
    )


@pytest.mark.unit
def test_a_tenant_table_still_returns_nothing_without_tenant_context(sessie: Session) -> None:
    """De tegenrichting: tenant-tabellen blijven WEL dicht.

    Zonder deze helft zou "filter nooit iets" de test hierboven halen, en dat is het lek
    dat de hele hook moet voorkomen.
    """
    rijen = sessie.execute(select(_MetTenant)).scalars().all()

    assert list(rijen) == [], (
        f"Een tabel MET tenant_id gaf {len(list(rijen))} rijen zonder tenantcontext. "
        "Fail-secure betekent hier nul rijen."
    )


@pytest.mark.unit
def test_a_tenant_table_is_filtered_when_there_is_a_tenant(sessie: Session) -> None:
    """En met een tenant komt de eigen rij wel terug -- anders is de filter een blokkade."""
    set_tenant_id(1)
    try:
        rijen = sessie.execute(select(_MetTenant)).scalars().all()
        ids = sorted(r.id for r in rijen)
    finally:
        clear_tenant_context()

    assert ids == [1], f"verwachtte alleen de rij van tenant 1, kreeg {ids}"


@pytest.mark.unit
def test_audit_logs_stays_readable(sessie: Session) -> None:
    """`audit_logs` is bewust tenant-overstijgend, ook zonder tenantcontext.

    De auditketen moet ook een verzoek zonder geldige tenant kunnen vastleggen en
    teruglezen. De met-tenant-tak zondert hem al uit (regel ~206); de geen-tenant-tak moet
    dat ook doen, anders is de uitzondering de helft van de tijd afwezig.
    """
    gevonden = sessie.execute(select(_AuditAchtig)).scalars().all()

    assert list(gevonden), (
        "audit_logs werd leeggemaakt zonder tenantcontext, terwijl de tak MET tenant hem "
        "expliciet uitzondert. Dezelfde uitzondering hoort in beide takken te gelden."
    )
