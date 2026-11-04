"""Unit tests for scripts/run_righttyper.py."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts"
_SPEC = importlib.util.spec_from_file_location(
    "run_righttyper",
    _SCRIPTS_DIR / "run_righttyper.py",
)
assert _SPEC is not None, "Could not locate run_righttyper.py"
assert _SPEC.loader is not None, "Module spec has no loader"
_MOD = importlib.util.module_from_spec(_SPEC)
sys.modules["run_righttyper"] = _MOD
_SPEC.loader.exec_module(_MOD)  # type: ignore[union-attr]

resolve_targets = _MOD.resolve_targets
build_command = _MOD.build_command


@pytest.mark.unit
def test_resolve_targets_from_paths(tmp_path: Path) -> None:
    root = tmp_path
    (root / "src" / "core").mkdir(parents=True)
    file_a = root / "src" / "core" / "a.py"
    file_b = root / "src" / "core" / "b.txt"
    file_a.write_text("x = 1\n")
    file_b.write_text("text\n")

    targets = resolve_targets(
        paths=[root / "src"],
        since=None,
        exclude_patterns=(),
        root=root,
    )
    assert targets == [file_a]


@pytest.mark.unit
def test_resolve_targets_with_exclude(tmp_path: Path) -> None:
    root = tmp_path
    (root / "src" / "core").mkdir(parents=True)
    (root / "src" / "alembic").mkdir(parents=True)
    file_a = root / "src" / "core" / "a.py"
    file_mig = root / "src" / "alembic" / "migration.py"
    file_a.write_text("x = 1\n")
    file_mig.write_text("pass\n")

    targets = resolve_targets(
        paths=[root / "src"],
        since=None,
        exclude_patterns=(r"(^|/)alembic/",),
        root=root,
    )
    assert targets == [file_a]


@pytest.mark.unit
def test_resolve_targets_empty_paths_defaults_to_src(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path
    (root / "src").mkdir()
    file_a = root / "src" / "a.py"
    file_a.write_text("x = 1\n")

    monkeypatch.chdir(root)
    targets = resolve_targets(
        paths=None,
        since=None,
        exclude_patterns=(),
        root=root,
    )
    assert targets == [file_a]


@pytest.mark.unit
def test_resolve_targets_no_files_returns_empty(tmp_path: Path) -> None:
    root = tmp_path
    (root / "empty").mkdir()
    targets = resolve_targets(
        paths=[root / "empty"],
        since=None,
        exclude_patterns=(),
        root=root,
    )
    assert targets == []


@pytest.mark.unit
def test_build_command_dry_run() -> None:
    targets = [Path("src/core/a.py")]
    cmd = build_command(targets, apply=False, output_dir=Path(".tmp/righttyper"))
    assert cmd[0] == sys.executable
    assert cmd[1:4] == ["-m", "righttyper", "--verbose"]
    assert "--no-output-files" in cmd
    assert "--output-files" not in cmd
    assert any("src" in part and "a.py" in part for part in cmd)


@pytest.mark.unit
def test_build_command_apply() -> None:
    targets = [Path("src/core/a.py"), Path("src/core/b.py")]
    cmd = build_command(targets, apply=True, output_dir=Path(".tmp/righttyper"))
    assert "--output-files" in cmd
    assert "--no-output-files" not in cmd
    assert len(cmd) >= 2
    assert all("src" in part and part.endswith(".py") for part in cmd[-2:])


@pytest.mark.unit
def test_main_without_righttyper_exits_with_hint(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(_MOD, "_has_righttyper", lambda: False)
    exit_code = _MOD.main([])
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "righttyper is not installed" in captured.err
    assert "pip install righttyper" in captured.err
