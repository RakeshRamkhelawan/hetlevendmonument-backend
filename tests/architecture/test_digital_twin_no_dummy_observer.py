"""Architecture test: ADR-026 -- _DummyObserver verbod in digital_twin service.

_DummyObserver is een test-only stub. In productie-code moet altijd de echte
LLM failover chain (LLMFailoverChain) gebruikt worden.
"""

from pathlib import Path


def test_digital_twin_service_file_exists() -> None:
    """ADR-026: digital_twin/service.py moet bestaan voor DummyObserver check."""
    service_file = Path("src/core/api/v1/digital_twin/service.py")
    assert service_file.exists(), (
        "src/core/api/v1/digital_twin/service.py ontbreekt -- "
        "kan ADR-026 _DummyObserver verbod niet verifieren."
    )


def test_no_dummy_observer_in_digital_twin_service() -> None:
    """ADR-026: digital_twin/service.py mag geen _DummyObserver instantieren."""
    service_file = Path("src/core/api/v1/digital_twin/service.py")
    assert service_file.exists(), "src/core/api/v1/digital_twin/service.py ontbreekt"

    content = service_file.read_text(encoding="utf-8", errors="ignore")
    assert "_DummyObserver" not in content, (
        "_DummyObserver gevonden in digital_twin/service.py (ADR-026 schending). "
        "Gebruik LLMFailoverChain als LLM-provider."
    )


def test_no_dummy_observer_in_production_src() -> None:
    """ADR-026: _DummyObserver mag nergens in src/ voorkomen zonder # test-only markering."""
    unreadable: list[str] = []
    scanned = 0
    violations: list[str] = []

    for src_file in Path("src/").rglob("*.py"):
        try:
            content = src_file.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            unreadable.append(f"{src_file}: {exc}")
            continue
        scanned += 1
        if "_DummyObserver" in content and "# test-only" not in content:
            violations.append(
                f"_DummyObserver in productie-bestand zonder # test-only: {src_file} "
                "(ADR-026 schending)"
            )

    assert scanned >= 1500, (
        f"Slechts {scanned} bestanden gescand onder src/ -- dat lijkt een (bijna) lege "
        "boom. Verkeerd pad? Deze guard controleert dan vrijwel niets."
    )
    assert not unreadable, (
        "Deze bestanden konden niet gelezen worden en zijn NIET gecontroleerd op "
        "_DummyObserver:\n" + "\n".join(f"  - {f}" for f in unreadable)
    )
    assert not violations, "\n".join(violations)
