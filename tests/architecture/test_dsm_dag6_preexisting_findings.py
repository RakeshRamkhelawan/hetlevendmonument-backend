"""SP-DSM-DAG6: Backlog-marker tests voor pre-existing bevindingen uit Laag A review.

KRITIEK (F1): admin_digital_twin.py gebruikt text(f"...{int(tenant_id)}...") --
  de int()-cast maakt injectie onmogelijk maar het patroon moet weg
  (SQLAlchemy bind-param: text("...= :tid"), {"tid": str(tenant_id)}).

MEDIUM (F2): GET /admin/digital-twin/stats heeft geen rate-limit decorator.
  Fix: voeg @consent_read_limit toe (ADR-026, patroon in admin_learning_endpoints.py).

Beide tests staan ROOD totdat de fix geland is.
"""

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_TWIN_FILE = _ROOT / "src" / "core" / "api" / "admin_digital_twin.py"


def test_admin_digital_twin_no_text_fstring() -> (
    None
):  # TODO(SP-DSM-DAG6): fix admin_digital_twin.py line 55
    """KRITIEK: text(f"...") patroon in admin_digital_twin.py moet vervangen worden door bind-param.

    Huidig: text(f"SET LOCAL app.current_tenant = '{int(tenant_id)}'")
    Fix:    text("SET LOCAL app.current_tenant = :tid"), {"tid": str(tenant_id)}
    """
    source = _TWIN_FILE.read_text(encoding="utf-8")
    violations = [
        lineno + 1
        for lineno, line in enumerate(source.splitlines())
        if "text(f" in line or 'text(f"' in line or "text(f'" in line
    ]
    assert violations == [], (
        f'admin_digital_twin.py: text(f"...") patroon gevonden op regels {violations}. '
        'Fix: vervang door text("...:param") + bind-dict. SP-DSM-DAG6 backlog.'
    )


def test_admin_digital_twin_stats_has_rate_limit() -> (
    None
):  # TODO(SP-DSM-DAG6): rate-limit op GET /stats
    """MEDIUM: GET /admin/digital-twin/stats mist rate-limit decorator.

    Fix: voeg @consent_read_limit toe ONDER @router.get('/stats') --
    zie admin_learning_endpoints.py als voorbeeld. De limiet moet onder de routedecorator staan:
    decorators worden van onder naar boven toegepast, dus een limiet erboven wordt nooit
    uitgevoerd (de router registreert dan de ongewrapte functie; gemeten 2026-10-26).
    """
    source = _TWIN_FILE.read_text(encoding="utf-8")
    lines = source.splitlines()

    get_stats_line: int | None = None
    for i, line in enumerate(lines):
        if "@router.get" in line and "stats" in line:
            get_stats_line = i
            break

    assert get_stats_line is not None, "GET /stats endpoint niet gevonden in admin_digital_twin.py"

    # De decorators NA de route-regel, tot de functie zelf: daar hoort de limiet te staan.
    decorator_window = []
    for line in lines[get_stats_line + 1 :]:
        if line.startswith(("def ", "async def ")):
            break
        decorator_window.append(line)
    has_rate_limit = any(
        "rate_limit" in line or "consent_read_limit" in line for line in decorator_window
    )

    assert has_rate_limit, (
        f"admin_digital_twin.py regel {get_stats_line + 1}: @router.get('/stats') heeft geen "
        "rate-limit decorator onder de routedecorator. Fix: voeg @consent_read_limit toe "
        "ONDER @router.get. SP-DSM-DAG6 backlog."
    )
