"""
Regression Test Suite
=====================

This package contains regression tests for known bug fixes.

Every critical (P0/P1) bug fix MUST have a corresponding regression test
to prevent the bug from reoccurring in future releases.

Regression Test Policy:
- Each test documents the original bug (issue number, severity, description)
- Each test explains the root cause and the fix
- Each test is marked with @pytest.mark.regression
- Critical regressions are marked with @pytest.mark.critical
- Regression tests run on EVERY CI build (fast gate)

Test Execution:
    # Run all regression tests
    pytest tests/regression/ -v -m regression

    # Run critical regression tests only
    pytest tests/regression/ -v -m "regression and critical"

    # Run specific regression test
    pytest tests/regression/test_p5_critical_bug_fixes.py::test_regression_workflow_cycle_detection -v
"""
