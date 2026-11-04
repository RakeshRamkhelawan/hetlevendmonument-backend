"""Ensure seed.py never contains a hardcoded password fallback."""

from __future__ import annotations

import ast
import pathlib

import pytest


@pytest.mark.security
def test_seed_password_has_no_hardcoded_fallback() -> None:
    source = pathlib.Path("src/core/database/seed.py").read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Attribute) and node.func.attr == "getenv"):
            continue
        if len(node.args) < 2:
            continue
        arg_name = node.args[0]
        fallback = node.args[1]
        if (
            isinstance(arg_name, ast.Constant)
            and "PASSWORD" in str(arg_name.value).upper()
            and isinstance(fallback, ast.Constant)
            and fallback.value not in (None, "")
        ):
            pytest.fail(
                f"os.getenv('{arg_name.value}') heeft hardcoded fallback "
                f"in seed.py — verwijder het of gebruik None"
            )


@pytest.mark.security
def test_seed_database_raises_when_password_env_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """seed_database() moet falen als DEFAULT_ADMIN_PASSWORD niet gezet is."""
    monkeypatch.delenv("DEFAULT_ADMIN_PASSWORD", raising=False)

    import importlib

    import src.core.database.seed as seed_module

    importlib.reload(seed_module)

    assert not seed_module.DEFAULT_ADMIN_PASSWORD, (
        "DEFAULT_ADMIN_PASSWORD zonder env-var moet None of leeg zijn, niet een hardcoded string"
    )
