"""De tenantcontext-listener, zonder database (ADR-036 OP-151).

Deze tests toetsten eerder `get_db()`, dat de RLS-context eenmalig met `SET LOCAL` zette
direct na het aanmaken van de sessie. Die opzet is op 2026-08-16 vervangen door een
`begin`-event op de klasse `Engine`, om twee gemeten redenen:

- `SET LOCAL` is transactie-gebonden en verdween bij de eerste `commit()` van het
  endpoint. Gemeten: direct na het zetten `'42'`, na `commit()` `''`.
- De codebase bouwt zestien engines naast `db_manager`; een listener per sessie dekte die
  geen van alle.

**Twee verwachtingen zijn daarbij BEWUST omgedraaid.** Ze staan hieronder met de reden,
zodat een latere lezer ziet dat het een beslissing was en geen verslapping:

1. *Voorheen:* zonder tenant werd er NIETS gezet. *Nu:* er wordt een LEGE waarde gezet.
   Zou de listener niets doen, dan blijft een eerdere sessie-brede `SET` op dezelfde
   poolverbinding staan en erft het volgende verzoek de tenant van het vorige. Dat is een
   cross-tenant lek; een lege waarde geeft via `NULLIF(..., '')` netjes nul rijen.
2. *Voorheen:* een fout bij het zetten werd gelogd als waarschuwing en de sessie ging
   door. *Nu:* de fout gaat omhoog en de transactie faalt. Onder een applicatierol
   verandert "kon de context niet zetten" anders in stille nul-rijen, en dan is het
   verschil tussen "geen gegevens" en "geen context" onzichtbaar.

De integratiekant (werkt dit tegen een echte PostgreSQL, en overleeft het een commit)
staat in `tests/integration/database/test_the_tenant_context_survives_a_commit.py`. Deze
module heeft geen database nodig en draait dus mee in de blokkerende CI-stap.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.core.database.database import _zet_tenantcontext


def _verbinding(dialect: str = "postgresql") -> MagicMock:
    """Een nagebootste SQLAlchemy-Connection die haar aanroepen onthoudt."""
    conn = MagicMock()
    conn.dialect.name = dialect
    return conn


def _gezette_waarde(conn: MagicMock) -> str | None:
    """De waarde die de listener aan `app.current_tenant` gaf, of None als hij niets deed."""
    for aanroep in conn.execute.call_args_list:
        statement = str(aanroep.args[0])
        if "app.current_tenant" in statement:
            parameters = aanroep.args[1] if len(aanroep.args) > 1 else {}
            return str(parameters.get("t"))
    return None


@pytest.mark.unit
def test_the_listener_sets_the_tenant_from_the_context_var() -> None:
    """Met een tenant in de ContextVar komt die waarde in de instelling terecht."""
    conn = _verbinding()

    with patch("src.core.middleware.tenant_context.get_tenant_id", return_value=42):
        _zet_tenantcontext(conn)

    assert _gezette_waarde(conn) == "42"


@pytest.mark.unit
def test_the_listener_binds_the_value_instead_of_formatting_it() -> None:
    """De tenant gaat als BINDPARAMETER mee, niet als tekst in de SQL.

    Twee redenen. Injectie is er een van, maar de directe aanleiding is dat de oude vorm
    -- `SET LOCAL app.current_tenant = :t` -- op het echte pad helemaal niet werkt:
    PostgreSQL accepteert geen bindparameter in een utility-statement. Gemeten via asyncpg:
    `PostgresSyntaxError`. `set_config(...)` is een gewone functie en accepteert hem wel.
    """
    conn = _verbinding()

    with patch("src.core.middleware.tenant_context.get_tenant_id", return_value=99):
        _zet_tenantcontext(conn)

    statement = str(conn.execute.call_args.args[0])
    parameters = conn.execute.call_args.args[1]

    assert "set_config" in statement, f"verwachtte set_config, kreeg: {statement}"
    assert "99" not in statement, (
        f"de tenantwaarde staat in de SQL-tekst in plaats van in een parameter: {statement}"
    )
    assert parameters == {"t": "99"}


@pytest.mark.unit
def test_the_listener_casts_the_tenant_to_an_integer() -> None:
    """Een tenant die als string binnenkomt wordt door int() gehaald.

    De ContextVar is getypeerd als int, maar de cast is de laatste wering voor het geval
    er ooit iets anders in belandt: een waarde die geen geheel getal is hoort de
    transactie te laten falen, niet in de instelling terecht te komen.
    """
    conn = _verbinding()

    with patch("src.core.middleware.tenant_context.get_tenant_id", return_value="7"):
        _zet_tenantcontext(conn)

    assert _gezette_waarde(conn) == "7"

    kwaadaardig = _verbinding()
    with patch("src.core.middleware.tenant_context.get_tenant_id", return_value="1; DROP"):
        with pytest.raises(ValueError):
            _zet_tenantcontext(kwaadaardig)


@pytest.mark.unit
def test_the_listener_sets_an_empty_value_when_there_is_no_tenant() -> None:
    """Zonder tenant wordt er een LEGE waarde gezet -- niet niets.

    Dit is de eerste bewust omgedraaide verwachting (zie de moduletoelichting). Zou de
    listener hier niets doen, dan blijft een eerdere sessie-brede `SET` op dezelfde
    poolverbinding staan en ziet dit verzoek de gegevens van de vorige tenant.
    """
    conn = _verbinding()

    with patch("src.core.middleware.tenant_context.get_tenant_id", return_value=None):
        _zet_tenantcontext(conn)

    assert _gezette_waarde(conn) == "", (
        "zonder tenant hoort er een lege waarde te worden gezet, zodat een hergebruikte "
        "verbinding geen tenant van een vorig verzoek meesleept"
    )


@pytest.mark.unit
def test_the_listener_does_nothing_on_sqlite() -> None:
    """SQLite kent `set_config` niet; de unit-tests draaien daarop.

    De tegenrichting van de test hierboven: zonder deze grens zou "zet het altijd, overal"
    een geldige oplossing zijn en breekt elke SQLite-sessie.
    """
    conn = _verbinding(dialect="sqlite")

    with patch("src.core.middleware.tenant_context.get_tenant_id", return_value=42):
        _zet_tenantcontext(conn)

    conn.execute.assert_not_called()


@pytest.mark.unit
def test_a_failure_to_set_the_context_is_not_swallowed() -> None:
    """Een fout gaat omhoog; de transactie hoort niet door te gaan.

    Dit is de tweede bewust omgedraaide verwachting. Voorheen logde `get_db()` een
    waarschuwing en gaf de sessie tOch uit. Onder een applicatierol betekent een
    ontbrekende tenantcontext nul rijen, en dan is een waarschuwing in een logbestand het
    enige verschil tussen "deze klant heeft geen gegevens" en "wij konden niet vaststellen
    wie deze klant is".
    """
    conn = _verbinding()
    conn.execute.side_effect = RuntimeError("verbinding weggevallen")

    with patch("src.core.middleware.tenant_context.get_tenant_id", return_value=7):
        with pytest.raises(RuntimeError, match="verbinding weggevallen"):
            _zet_tenantcontext(conn)
