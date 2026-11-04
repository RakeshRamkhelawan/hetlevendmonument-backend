"""
SP-H08: Compliance test quality gate (B-020).

Verifieert dat tests/compliance/test_gdpr_compliance.py echte service-aanroepen
bevat en niet langer uit louter mock-assertions bestaat.
"""

import ast
import pathlib

import pytest


@pytest.mark.unit
class TestComplianceTestQuality:
    def test_gdpr_compliance_tests_are_not_only_mocks(self):
        """Compliance tests raken echte code (geen assert-only stubs)."""
        source = pathlib.Path(
            "tests/compliance/test_gdpr_compliance.py"
        ).read_text(encoding="utf-8")

        tree = ast.parse(source)
        has_real_calls = False

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = ""
                if isinstance(func, ast.Name):
                    name = func.id
                elif isinstance(func, ast.Attribute):
                    name = func.attr
                if name in ("TwinConsentManager", "GDPREnforcer", "DSARService"):
                    has_real_calls = True
                    break

        assert has_real_calls, (
            "Compliance tests zijn nog steeds mock-assertions "
            "zonder echte service-calls (B-020)"
        )

    def test_gdpr_compliance_has_minimum_real_tests(self):
        """Minimaal 5 echte compliance tests aanwezig."""
        source = pathlib.Path(
            "tests/compliance/test_gdpr_compliance.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)
        real_tests = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.AsyncFunctionDef)
            and node.name.startswith("test_")
        ]
        assert len(real_tests) >= 5, (
            f"Slechts {len(real_tests)} async tests -- "
            "minimaal 5 echte compliance tests vereist"
        )
