"""
Test CI Skip Documentation Compliance (Fase 4.4)

Valideert dat elke skip/ignore/deselect directive in CI een gedocumenteerde
reden heeft in een comment (# SKIP: <reden>).

Dit voorkomt dat tests stilzwijgend worden overgeslagen zonder duidelijke
rationale, wat technische schuld veroorzaakt.
"""

import re
from pathlib import Path

import pytest


class TestCISkipDocumentation:
    """Test suite voor CI skip directive documentatie compliance."""

    CI_FILE_PATH = Path(".github/workflows/ci-feature.yml")

    @pytest.fixture
    def ci_content(self) -> str:
        """Laad de CI YAML content."""
        if not self.CI_FILE_PATH.exists():
            pytest.skip("CI file not found at expected path")
        return self.CI_FILE_PATH.read_text(encoding="utf-8")

    @pytest.fixture
    def pytest_ini_content(self) -> str:
        """Laad de pytest.ini content."""
        pytest_ini = Path("pytest.ini")
        if not pytest_ini.exists():
            pytest_ini = Path("pytest.ini.bak")
        if not pytest_ini.exists():
            pytest.skip("pytest.ini not found")
        return pytest_ini.read_text(encoding="utf-8")

    def _extract_skip_directives(self, content: str) -> list[dict]:
        """
        Extract alle skip directives met hun context.

        Returns:
            List van dicts met 'line', 'directive', 'comment_above'
        """
        lines = content.split("\n")
        directives = []

        for i, line in enumerate(lines):
            stripped = line.strip()

            # Check voor skip directives
            skip_patterns = [
                r"^\s*--ignore=",
                r"^\s*--deselect\s+",
                r"^\s*-m\s+\"?not\s+",
            ]

            is_skip = any(re.match(pattern, stripped) for pattern in skip_patterns)

            if is_skip:
                # Zoek commentaar erboven (binnen 2 regels)
                comment_above = ""
                for j in range(max(0, i - 3), i):
                    prev_line = lines[j].strip()
                    if prev_line.startswith("#"):
                        comment_above = prev_line
                    elif prev_line and not prev_line.startswith("-"):
                        # Reset als we non-comment, non-directive content vinden
                        comment_above = ""

                directives.append(
                    {
                        "line_num": i + 1,
                        "line": stripped,
                        "comment_above": comment_above,
                    }
                )

        return directives

    def _is_valid_skip_comment(self, comment: str, directive: str) -> bool:
        """
        Valideer dat een skip comment een reden bevat.

        Een geldige comment moet:
        - Starten met # SKIP:
        - Een reden bevatten waarom de test wordt overgeslagen
        """
        if not comment:
            return False

        # Moet SKIP: marker bevatten
        if "SKIP:" not in comment:
            return False

        # Extraheer reden na SKIP:
        match = re.search(r"SKIP:\s*(.+)", comment)
        if not match:
            return False

        reason = match.group(1).strip()
        # Reden moet minimaal 10 karakters zijn (betekenisvolle uitleg)
        return len(reason) >= 10

    def test_ci_file_exists(self):
        """Test dat het CI bestand bestaat."""
        assert self.CI_FILE_PATH.exists(), f"CI file not found at {self.CI_FILE_PATH}"

    def test_all_skip_directives_have_documentation(self, ci_content: str):
        """
        Test dat elke skip directive in CI een gedocumenteerde reden heeft.

        Gate: Fase 4.4 - Documenteer alle skipped tests in CI.
        """
        directives = self._extract_skip_directives(ci_content)

        # Filter alleen pytest run directives (niet env vars)
        pytest_directives = [
            d
            for d in directives
            if "pytest" in ci_content.split("\n")[d["line_num"] - 2].lower()
            or any(pattern in d["line"] for pattern in ["--ignore", "--deselect", '-m "not'])
        ]

        undocumented = []
        for directive in pytest_directives:
            if not self._is_valid_skip_comment(directive["comment_above"], directive["line"]):
                undocumented.append(f"Line {directive['line_num']}: {directive['line']}")

        if undocumented:
            pytest.fail(
                f"Found {len(undocumented)} undocumented skip directives:\n"
                + "\n".join(f"  - {u}" for u in undocumented)
                + "\n\nEach skip must have a comment above it with format: "
                "# SKIP: <reason why this test is skipped>"
            )

    def test_no_bare_skip_markers(self, ci_content: str):
        """
        Test dat er geen 'bare' skip directives zijn zonder context.

        Elke skip moet duidelijk zijn en niet verborgen in lange command chains.
        """
        lines = ci_content.split("\n")

        for i, line in enumerate(lines, 1):
            stripped = line.strip()

            # Check voor --ignore zonder comment
            if "--ignore" in stripped and "# SKIP:" not in stripped:
                # Check of er een comment op dezelfde regel of erboven is
                has_comment = False
                if "#" in stripped:
                    comment_part = stripped.split("#", 1)[1]
                    if "SKIP:" in comment_part:
                        has_comment = True

                if not has_comment:
                    # Check regels erboven
                    for j in range(max(0, i - 3), i - 1):
                        if "# SKIP:" in lines[j]:
                            has_comment = True
                            break

                    if not has_comment:
                        pytest.fail(f"Line {i}: --ignore without # SKIP: comment: {stripped}")

    def test_skip_reason_meaningful(self, ci_content: str):
        """
        Test dat skip redenen betekenisvol zijn (niet leeg of te kort).
        """
        skip_pattern = re.compile(r"#\s*SKIP:\s*(.+)")
        lines = ci_content.split("\n")

        for i, line in enumerate(lines, 1):
            match = skip_pattern.search(line)
            if match:
                reason = match.group(1).strip()
                if len(reason) < 10:
                    pytest.fail(f"Line {i}: Skip reason too short (min 10 chars): '{reason}'")
                if reason.lower() in ["todo", "fixme", "unknown", "tbd"]:
                    pytest.fail(f"Line {i}: Skip reason is placeholder: '{reason}'")

    def test_pytest_ini_skip_documentation(self, pytest_ini_content: str):
        """
        Test dat pytest.ini ignore directives ook gedocumenteerd zijn.

        Skip directives in pytest.ini moeten ook een reden hebben.
        """
        lines = pytest_ini_content.split("\n")

        for i, line in enumerate(lines, 1):
            stripped = line.strip()

            # Check voor --ignore in pytest.ini
            if stripped.startswith("--ignore="):
                # Check voor comment erboven
                has_comment = False
                for j in range(max(0, i - 3), i - 1):
                    prev_line = lines[j].strip()
                    if prev_line.startswith("#") and len(prev_line) > 2:
                        has_comment = True
                        break

                if not has_comment:
                    pytest.fail(f"pytest.ini Line {i}: --ignore without comment: {stripped}")
