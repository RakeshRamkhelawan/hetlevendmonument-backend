"""Unit tests for scripts/audit_agent_yaml.py -- TDD Taak 1.2 (RED phase)."""

import textwrap
from pathlib import Path



class TestAuditResult:
    """Tests for the AuditResult dataclass."""

    def test_valid_result_fields(self):
        """AuditResult has filename, key, status, and error fields."""
        from scripts.audit_agent_yaml import AuditResult

        r = AuditResult(filename="test.yaml", normalized_key="testagent", status="ok")
        assert r.filename == "test.yaml"
        assert r.normalized_key == "testagent"
        assert r.status == "ok"
        assert r.error is None

    def test_error_result_stores_message(self):
        """AuditResult with status='error' stores the error message."""
        from scripts.audit_agent_yaml import AuditResult

        r = AuditResult(
            filename="bad.yaml",
            normalized_key=None,
            status="error",
            error="Missing agent name",
        )
        assert r.status == "error"
        assert r.error == "Missing agent name"
        assert r.normalized_key is None

    def test_duplicate_result_has_key(self):
        """AuditResult for a duplicate has normalized_key set."""
        from scripts.audit_agent_yaml import AuditResult

        r = AuditResult(
            filename="old_agent.yaml",
            normalized_key="oldagent",
            status="duplicate",
        )
        assert r.status == "duplicate"
        assert r.normalized_key == "oldagent"


class TestAuditReport:
    """Tests for the AuditReport dataclass."""

    def test_report_counts_categories(self, tmp_path):
        """AuditReport counts ok, error, and duplicate results correctly."""
        from scripts.audit_agent_yaml import AuditReport, AuditResult

        results = [
            AuditResult("a.yaml", "a", "ok"),
            AuditResult("b.yaml", "b", "ok"),
            AuditResult("c.yaml", None, "error", "Bad YAML"),
            AuditResult("d.yaml", "d", "duplicate"),
        ]
        report = AuditReport(results=results, agent_dir=str(tmp_path))
        assert report.total == 4
        assert report.ok_count == 2
        assert report.error_count == 1
        assert report.duplicate_count == 1

    def test_report_duplicates_property(self, tmp_path):
        """AuditReport.duplicates returns only duplicate results."""
        from scripts.audit_agent_yaml import AuditReport, AuditResult

        results = [
            AuditResult("old.yaml", "foo", "duplicate"),
            AuditResult("new.yaml", "foo", "ok"),
            AuditResult("bar.yaml", "bar", "ok"),
        ]
        report = AuditReport(results=results, agent_dir=str(tmp_path))
        dupes = report.duplicates
        assert len(dupes) == 1
        assert dupes[0].filename == "old.yaml"

    def test_report_errors_property(self, tmp_path):
        """AuditReport.errors returns only error results."""
        from scripts.audit_agent_yaml import AuditReport, AuditResult

        results = [
            AuditResult("broken.yaml", None, "error", "Parse error"),
            AuditResult("good.yaml", "good", "ok"),
        ]
        report = AuditReport(results=results, agent_dir=str(tmp_path))
        assert len(report.errors) == 1
        assert report.errors[0].filename == "broken.yaml"


class TestAuditAgentYaml:
    """Tests for the audit_agent_yaml() function."""

    def _write_flat_yaml(self, path: Path, name: str) -> None:
        """Write a flat-format YAML (new style)."""
        content = textwrap.dedent(
            f"""\
            agent_id: "dept.{name.lower()}.001"
            name: "{name}Agent"
            department: "software_engineering"
            technology: "LLM"
            class_name: "{name}Agent"
            description: "Test {name} agent."
            is_active: true
            priority: "MEDIUM"
            """
        )
        path.write_text(content, encoding="utf-8")

    def _write_nested_yaml(self, path: Path, name: str) -> None:
        """Write a nested-format YAML (old style with agent: block)."""
        content = textwrap.dedent(
            f"""\
            agent:
              id: 1
              name: {name}Agent
              version: 1.0.0
              status: active
            classification:
              department: Software Engineering
              category: Technical
            technical:
              technology: LLM
              class_name: {name}Agent
            """
        )
        path.write_text(content, encoding="utf-8")

    def test_valid_flat_yaml_returns_ok(self, tmp_path):
        """A single valid flat-format YAML file returns an ok result."""
        from scripts.audit_agent_yaml import audit_agent_yaml

        self._write_flat_yaml(tmp_path / "test-agent.yaml", "Test")
        report = audit_agent_yaml(tmp_path)

        assert report.total == 1
        assert report.ok_count == 1
        assert report.error_count == 0
        assert report.duplicate_count == 0

    def test_malformed_yaml_returns_error(self, tmp_path):
        """A YAML file with invalid syntax returns an error result."""
        from scripts.audit_agent_yaml import audit_agent_yaml

        bad = tmp_path / "broken.yaml"
        bad.write_text("key: [unclosed\n  - item", encoding="utf-8")
        report = audit_agent_yaml(tmp_path)

        assert report.error_count == 1
        assert report.errors[0].filename == "broken.yaml"
        assert report.errors[0].error is not None

    def test_missing_name_returns_error(self, tmp_path):
        """A YAML missing agent name returns an error result."""
        from scripts.audit_agent_yaml import audit_agent_yaml

        empty_yaml = tmp_path / "empty.yaml"
        empty_yaml.write_text("some_field: value\n", encoding="utf-8")
        report = audit_agent_yaml(tmp_path)

        assert report.error_count == 1
        assert "empty.yaml" in report.errors[0].filename

    def test_duplicate_keys_detected(self, tmp_path):
        """Two files normalizing to the same key are flagged as duplicate."""
        from scripts.audit_agent_yaml import audit_agent_yaml

        # Both normalize to key 'foo'
        self._write_flat_yaml(tmp_path / "foo_new.yaml", "Foo")
        self._write_nested_yaml(tmp_path / "foo_old.yaml", "Foo")

        report = audit_agent_yaml(tmp_path)
        assert report.duplicate_count == 1
        # The duplicate is the file that was seen second (first one is ok)
        dupe_names = {r.filename for r in report.duplicates}
        # One of the two foo files is flagged as duplicate
        assert bool(dupe_names & {"foo_new.yaml", "foo_old.yaml"})

    def test_no_yml_files_returns_empty_report(self, tmp_path):
        """Empty directory returns a report with zero results."""
        from scripts.audit_agent_yaml import audit_agent_yaml

        report = audit_agent_yaml(tmp_path)
        assert report.total == 0
        assert report.ok_count == 0

    def test_ignores_non_yaml_files(self, tmp_path):
        """Non-.yaml files are ignored."""
        from scripts.audit_agent_yaml import audit_agent_yaml

        (tmp_path / "notes.txt").write_text("ignore me", encoding="utf-8")
        (tmp_path / "readme.md").write_text("# ignore", encoding="utf-8")
        self._write_flat_yaml(tmp_path / "real.yaml", "Real")

        report = audit_agent_yaml(tmp_path)
        assert report.total == 1
        assert report.ok_count == 1

    def test_multiple_valid_files(self, tmp_path):
        """Multiple valid YAML files with unique keys all return ok."""
        from scripts.audit_agent_yaml import audit_agent_yaml

        for name in ["Alpha", "Beta", "Gamma"]:
            self._write_flat_yaml(tmp_path / f"{name.lower()}.yaml", name)

        report = audit_agent_yaml(tmp_path)
        assert report.total == 3
        assert report.ok_count == 3
        assert report.duplicate_count == 0


class TestAuditAgentYamlCli:
    """Tests for the main() CLI entry point."""

    def test_main_exits_zero_on_clean_dir(self, tmp_path):
        """main() exits 0 when no errors and no duplicates."""
        import subprocess
        import sys

        flat = tmp_path / "clean.yaml"
        flat.write_text(
            textwrap.dedent(
                """\
                agent_id: "dept.clean.001"
                name: "CleanAgent"
                department: "software_engineering"
                technology: "LLM"
                class_name: "CleanAgent"
                description: "Clean agent."
                is_active: true
                priority: "MEDIUM"
                """
            ),
            encoding="utf-8",
        )

        result = subprocess.run(
            [sys.executable, "-m", "scripts.audit_agent_yaml", str(tmp_path)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"

    def test_main_exits_nonzero_on_errors(self, tmp_path):
        """main() exits non-zero when there are errors."""
        import subprocess
        import sys

        bad = tmp_path / "broken.yaml"
        bad.write_text("key: [unclosed\n  - item", encoding="utf-8")

        result = subprocess.run(
            [sys.executable, "-m", "scripts.audit_agent_yaml", str(tmp_path)],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0

    def test_main_exits_nonzero_on_duplicates(self, tmp_path):
        """main() exits non-zero when there are duplicate keys."""
        import subprocess
        import sys
        import textwrap as tw

        flat1 = tmp_path / "dup1.yaml"
        flat1.write_text(
            tw.dedent(
                """\
                agent_id: "dept.dup.001"
                name: "DupAgent"
                department: "software_engineering"
                technology: "LLM"
                class_name: "DupAgent"
                description: "First dup."
                is_active: true
                priority: "MEDIUM"
                """
            ),
            encoding="utf-8",
        )
        flat2 = tmp_path / "dup2.yaml"
        flat2.write_text(
            tw.dedent(
                """\
                agent_id: "dept.dup.002"
                name: "DupAgent"
                department: "software_engineering"
                technology: "LLM"
                class_name: "DupAgent"
                description: "Second dup."
                is_active: true
                priority: "MEDIUM"
                """
            ),
            encoding="utf-8",
        )

        result = subprocess.run(
            [sys.executable, "-m", "scripts.audit_agent_yaml", str(tmp_path)],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
