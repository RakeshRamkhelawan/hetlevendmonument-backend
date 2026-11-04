"""SP-WE-18: HTTP 503 guard voor ff_manager ontbrekend in app.state.

RED tests: falen voor de fix (directe attribute access aanwezig).
GREEN na fix: getattr patroon aanwezig, geen directe access meer.
"""

from __future__ import annotations

from pathlib import Path
import pytest

_ROOT = Path(__file__).parent.parent.parent


@pytest.mark.unit
class TestFFManagerGetattr503Guard:
    """Bewijst dat de getattr+503 guard aanwezig is in feature_flags_endpoints."""

    def _get_source(self) -> str:
        # ADR-033: logic moved to v1/feature_flags sub-routers
        return (_ROOT / "src/core/api/v1/feature_flags/tenant_router.py").read_text(
            encoding="utf-8"
        )

    def test_no_direct_ff_manager_attribute_access(self) -> None:
        """RED: directe request.app.state.ff_manager access moet verdwijnen na fix."""
        source = self._get_source()
        # Na fix: geen directe attribute access meer (zonder getattr)
        direct_access_lines = [
            ln
            for ln in source.splitlines()
            if "request.app.state.ff_manager" in ln and "getattr" not in ln
        ]
        assert len(direct_access_lines) == 0, (
            "Directe attribute access gevonden (AttributeError risico):\n"
            + "\n".join(direct_access_lines)
            + "\nVervang door: getattr(request.app.state, 'ff_manager', None)"
        )

    def test_getattr_pattern_present(self) -> None:
        """Na fix: getattr(..., 'ff_manager', None) patroon aanwezig."""
        source = self._get_source()
        assert (
            'getattr(request.app.state, "ff_manager", None)' in source
            or "getattr(request.app.state, 'ff_manager', None)" in source
        ), "getattr patroon ontbreekt in feature_flags router"

    def test_503_guard_present(self) -> None:
        """Na fix: HTTPException(status_code=503) guard aanwezig na getattr."""
        source = self._get_source()
        assert "503" in source and "ff_manager is None" in source, (
            "503 guard ontbreekt. Voeg toe: if ff_manager is None: raise HTTPException(503)"
        )

    def test_feature_flags_manager_also_fixed(self) -> None:
        """Na fix: ook manager.py gebruikt geen directe access."""
        source = (_ROOT / "src/core/feature_flags/manager.py").read_text(encoding="utf-8")
        direct = [
            ln
            for ln in source.splitlines()
            if "request.app.state.ff_manager" in ln and "getattr" not in ln
        ]
        assert len(direct) == 0, "Directe access ook in manager.py:\n" + "\n".join(direct)
