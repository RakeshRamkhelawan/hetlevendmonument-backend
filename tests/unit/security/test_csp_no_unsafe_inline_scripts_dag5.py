"""AUDIT-SEC-001-BE: script-src mag geen 'unsafe-inline' bevatten."""

from pathlib import Path


def test_csp_script_src_has_no_unsafe_inline() -> None:
    """script-src unsafe-inline is verwijderd uit ProductionSecurityManager (AUDIT-SEC-001-BE)."""
    src = Path("src/core/security/security_manager.py").read_text(encoding="utf-8")
    lines = [ln for ln in src.splitlines() if "Content-Security-Policy" in ln]
    assert lines, "Content-Security-Policy header niet gevonden in security_manager.py"
    for line in lines:
        if "script-src" not in line:
            continue
        # Isoleer de script-src directive (alles tot de volgende ; of einde string)
        csp_value = line.split("script-src", 1)[1].split(";")[0]
        assert "'unsafe-inline'" not in csp_value, (
            f"script-src bevat nog 'unsafe-inline': {line.strip()}"
        )
