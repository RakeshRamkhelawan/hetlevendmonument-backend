"""SP-DSM-002 Dag 6: zero violations in api/v1/ domeinen.

TODO(SP-DSM-002): Rood totdat alle 35 violations in agentic/als/cva/focus_builder/sync
zijn verwijderd via dependencies.py uitbreidingen en dsm:exempt annotaties.
"""


def test_all_v1_violations_resolved() -> None:
    """SP-DSM-002 Dag 6: alle violations in v1/-domeinen moeten 0 zijn."""
    from scripts.dsm_api_violation_finder import find_violations

    v1_violations = [
        (p, line, mod)
        for p, line, mod in find_violations()
        if "api/v1/" in str(p).replace("\\", "/")
    ]
    assert len(v1_violations) == 0, (
        f"{len(v1_violations)} violations resterend in api/v1/: "
        + ", ".join(f"{p}:{line}" for p, line, _ in v1_violations[:5])
    )
