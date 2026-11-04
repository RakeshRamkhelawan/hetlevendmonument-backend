"""De globale tenantfilter-listener moet weg te halen zijn -- en daarna weer aan te zetten.

**Waarom dit bestaat (ADR-036 OP-20, oorzaak).** `init_tenant_auto_filtering()` hangt met
`@event.listens_for(Session, "do_orm_execute", propagate=True)` een listener aan de
`Session`-KLASSE. Dat is procesbreed: zodra een test hem registreert, krijgt ELKE sessie in dat
proces een automatisch tenantfilter, ook een eigen in-memory-SQLite-sessie van een ander
testbestand. En het filter is fail-secure -- zonder tenant in de ContextVar levert het NUL rijen.

Er was geen manier om hem te verwijderen. Gevolg, gemeten op 2026-08-11: zodra
`tests/unit/test_database_coverage.py` (via `db_manager.initialize()` ->
`register_query_guard()`) hem registreerde, viel
`test_sp_e01_password_reset_email.py::test_forgot_password_calls_email_service` om -- het endpoint
vond de gebruiker niet, gaf 200 en verstuurde niets. Geen exception, geen log. Reproductie in
3,29 s door alleen de listener te registreren en daarna uitsluitend die test te draaien.

De ContextVar is NIET het lek: `_do_global_reset()` (RC5 in tests/conftest.py) zet hem al voor en
na elke test op `None`. Die hygiene-reset maakt de fail-secure tak juist zeker. Twee individueel
correcte dingen die samen fataal zijn.

**De val in de fix, en waarom de tweede test hieronder bestaat.**
`tenant_query_guard._GUARD_REGISTERED` is een eenrichtingslatch die nergens werd gereset. Wie de
listener verwijdert zonder die vlag terug te zetten, zorgt dat een latere `register_query_guard()`
vroegtijdig terugkeert en het tenantfilter PERMANENT afwezig is. Een fail-secure filter wordt dan
geen filter -- tenant-isolatietests blijven groen terwijl ze niets handhaven. Dat is de gevaarlijke
richting, en zonder die tweede test zou "listener weggooien en nooit terugzetten" een geldige
oplossing zijn.
"""

from __future__ import annotations

import pytest

from src.core.database import tenant_query_filter as tqf
from src.core.database import tenant_query_guard as guard


@pytest.fixture(autouse=True)
def _schone_registratiestaat():
    """Begin en eindig zonder listener, zodat deze tests elkaar niet beinvloeden."""
    guard.remove_query_guard()
    yield
    guard.remove_query_guard()


def test_the_listener_can_be_registered_and_removed() -> None:
    """Registreren maakt hem actief, verwijderen maakt hem inactief."""
    assert tqf.tenant_auto_filtering_is_active() is False

    tqf.init_tenant_auto_filtering()
    assert tqf.tenant_auto_filtering_is_active() is True

    tqf.remove_tenant_auto_filtering()
    assert tqf.tenant_auto_filtering_is_active() is False


def test_registering_twice_does_not_stack_two_listeners() -> None:
    """Idempotent, want anders is een enkele `event.remove` niet genoeg.

    `app_lifespan.py` roept `init_tenant_auto_filtering()` direct aan terwijl
    `register_query_guard()` datzelfde doet achter zijn eigen vlag. In een proces waar beide paden
    lopen zouden er zonder deze eigenschap TWEE listeners hangen, en dan laat verwijderen er een
    staan -- het filter lijkt dan weg maar werkt nog.
    """
    tqf.init_tenant_auto_filtering()
    tqf.init_tenant_auto_filtering()

    tqf.remove_tenant_auto_filtering()
    assert tqf.tenant_auto_filtering_is_active() is False, (
        "Na een dubbele registratie liet een enkele verwijdering nog een listener staan."
    )


def test_the_filter_can_be_switched_back_on_after_removal() -> None:
    """DE GEVAARLIJKE RICHTING: verwijderen mag het filter niet permanent uitzetten.

    `_GUARD_REGISTERED` is een eenrichtingslatch. Wordt die niet meegereset, dan slaat
    `register_query_guard()` de registratie over en handhaaft de applicatie daarna niets meer.
    """
    guard.register_query_guard(None)
    assert tqf.tenant_auto_filtering_is_active() is True

    guard.remove_query_guard()
    assert tqf.tenant_auto_filtering_is_active() is False

    guard.register_query_guard(None)
    assert tqf.tenant_auto_filtering_is_active() is True, (
        "Na verwijderen kon het tenantfilter niet meer worden aangezet. Een fail-secure filter is "
        "dan geen filter meer, en tenant-isolatietests blijven groen terwijl ze niets handhaven."
    )
