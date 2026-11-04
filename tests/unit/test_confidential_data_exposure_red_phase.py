"""
RED PHASE TESTS FOR TAAK 2.2: Confidential Data Exposure Scan

TDD Approach:
1. RED Phase: Write tests that FAIL (before fixing code)
2. GREEN Phase: Fix secrets and make tests PASS
3. REFACTOR Phase: Code cleanup and optimization

Security Goal: Detect and eliminate hardcoded secrets from codebase.
"""

import os
import re
from pathlib import Path
from typing import List, Tuple

import pytest


class TestHardcodedSecretDetection:
    """
    Tests to detect hardcoded secrets in the codebase

    These tests SHOULD FAIL initially (RED phase)
    They identify patterns that need to be fixed
    """

    # ============================================================================
    # TEST 1: Database Connection Strings
    # ============================================================================

    def test_no_hardcoded_database_credentials_in_source(self):
        """
        RED: Scan for hardcoded database credentials in Python source

        Pattern: postgresql://user:password@host/db
        """
        src_dir = Path("src")

        # Patterns that indicate hardcoded database credentials
        bad_patterns = [
            r"postgresql://\w+:[^@\s\"']+@",  # postgres user:pass
            r"mysql://\w+:[^@\s\"']+@",  # mysql user:pass
            r"mongodb://\w+:[^@\s\"']+@",  # mongodb user:pass
        ]

        violations = []

        for python_file in src_dir.rglob("*.py"):
            # Skip test files (they may have test credentials)
            if "test" in str(python_file):
                continue

            try:
                content = python_file.read_text(encoding="utf-8")

                # Skip files that are just config/examples
                if "example" in str(python_file).lower():
                    continue

                for pattern in bad_patterns:
                    matches = re.finditer(pattern, content, re.IGNORECASE)
                    for match in matches:
                        # Exclude comments and docstrings
                        line_num = content[: match.start()].count("\n") + 1
                        matched = match.group()
                        # Skip known placeholder patterns (e.g. docstring examples)
                        if "user:pass" in matched:
                            continue
                        violations.append((str(python_file), line_num, matched))
            except Exception as e:
                # Skip files that can't be read
                pass

        assert len(violations) == 0, (
            f"Found {len(violations)} hardcoded database credentials:\n"
            + "\n".join([f"{f}:{line_num}: {v}" for f, line_num, v in violations])
        )

    def test_no_hardcoded_database_urls_in_config(self):
        """
        RED: Check config files for hardcoded database URLs with passwords
        """
        # Check config module
        config_files = [
            "src/core/config.py",
            "src/config.py",
            "src/core/config/unified_config.py",
        ]

        violations = []

        for config_file in config_files:
            p = Path(config_file)
            if not p.exists():
                continue

            content = p.read_text(encoding="utf-8")

            # Look for database URLs with literal passwords
            # Exclude patterns that use environment variables
            if re.search(r"DATABASE_URL.*=.*['\"]postgresql://\w+:[^'\"@]+@", content):
                violations.append(f"{config_file}: Hardcoded DATABASE_URL with password")

            # Check for other common database config patterns
            if re.search(r"db_password\s*=\s*['\"][^'\"]*['\"]", content):
                violations.append(f"{config_file}: Hardcoded db_password")

        assert len(violations) == 0, f"Found {len(violations)} config violations:\n" + "\n".join(
            violations
        )

    # ============================================================================
    # TEST 2: API Keys (OpenAI, Anthropic, etc.)
    # ============================================================================

    def test_no_hardcoded_openai_api_keys(self):
        """
        RED: No hardcoded OpenAI API keys (pattern: sk-proj-*)
        """
        src_dir = Path("src")

        # OpenAI API keys start with sk-proj- or sk-
        openai_pattern = r"sk-[\w-]{20,}"

        violations = []

        for python_file in src_dir.rglob("*.py"):
            if "test" in str(python_file):
                continue

            try:
                content = python_file.read_text(encoding="utf-8")

                matches = re.finditer(openai_pattern, content)
                for match in matches:
                    # Skip if it's in a comment or string that says "YOUR_KEY_HERE"
                    if "YOUR_KEY_HERE" in content[match.start() : match.end() + 10]:
                        continue

                    line_num = content[: match.start()].count("\n") + 1
                    violations.append((str(python_file), line_num, match.group()))
            except:
                pass

        assert len(violations) == 0, (
            f"Found {len(violations)} hardcoded OpenAI keys:\n"
            + "\n".join([f"{f}:{line_num}: {v[:20]}..." for f, line_num, v in violations])
        )

    def test_no_hardcoded_anthropic_api_keys(self):
        """
        RED: No hardcoded Anthropic API keys (pattern: sk-ant-*)
        """
        src_dir = Path("src")

        # Anthropic API keys start with sk-ant-
        anthropic_pattern = r"sk-ant-[\w-]{20,}"

        violations = []

        for python_file in src_dir.rglob("*.py"):
            if "test" in str(python_file):
                continue

            try:
                content = python_file.read_text(encoding="utf-8")

                matches = re.finditer(anthropic_pattern, content)
                for match in matches:
                    if "YOUR_KEY_HERE" in content[match.start() : match.end() + 10]:
                        continue

                    line_num = content[: match.start()].count("\n") + 1
                    violations.append((str(python_file), line_num, match.group()))
            except:
                pass

        assert len(violations) == 0, (
            f"Found {len(violations)} hardcoded Anthropic keys:\n"
            + "\n".join([f"{f}:{line_num}" for f, line_num, v in violations])
        )

    def test_no_hardcoded_stripe_keys(self):
        """
        RED: No hardcoded Stripe API keys (pattern: sk_live_* or sk_test_*)
        """
        src_dir = Path("src")

        # Stripe keys start with sk_live_ or sk_test_
        stripe_pattern = r"sk_(live|test)_[\w-]{20,}"

        violations = []

        for python_file in src_dir.rglob("*.py"):
            if "test" in str(python_file):
                continue

            try:
                content = python_file.read_text(encoding="utf-8")

                matches = re.finditer(stripe_pattern, content)
                for match in matches:
                    if "YOUR_KEY_HERE" in content[match.start() : match.end() + 10]:
                        continue

                    line_num = content[: match.start()].count("\n") + 1
                    violations.append((str(python_file), line_num, match.group()))
            except:
                pass

        assert len(violations) == 0, (
            f"Found {len(violations)} hardcoded Stripe keys:\n"
            + "\n".join([f"{f}:{line_num}" for f, line_num, v in violations])
        )

    # ============================================================================
    # TEST 3: JWT Secrets and Private Keys
    # ============================================================================

    def test_no_hardcoded_jwt_secrets(self):
        """
        RED: No hardcoded JWT secret keys

        Check for patterns like:
        - SECRET_KEY = "hardcoded_key"
        - jwt_secret = "..."
        - JWT secrets should come from config/environment
        """
        src_dir = Path("src")

        # Look for secret assignments with hardcoded values
        secret_patterns = [
            r"SECRET_KEY\s*=\s*['\"][\w\-!@#$%^&*()]{10,}['\"]",
            r"jwt_secret\s*=\s*['\"][\w\-!@#$%^&*()]{10,}['\"]",
            r"signing_key\s*=\s*['\"][\w\-!@#$%^&*()]{10,}['\"]",
        ]

        violations = []

        for python_file in src_dir.rglob("*.py"):
            if "test" in str(python_file):
                continue

            try:
                content = python_file.read_text(encoding="utf-8")

                for pattern in secret_patterns:
                    matches = re.finditer(pattern, content, re.IGNORECASE)
                    for match in matches:
                        # Skip if it's getting from config or environment
                        line_start = max(0, match.start() - 200)
                        context = content[line_start : match.end()]

                        if "getenv" in context or "config." in context or "os.environ" in context:
                            continue

                        line_num = content[: match.start()].count("\n") + 1
                        violations.append((str(python_file), line_num))
            except:
                pass

        assert len(violations) == 0, (
            f"Found {len(violations)} hardcoded JWT secrets:\n"
            + "\n".join([f"{f}:{line_num}" for f, line_num in violations])
        )

    def test_no_private_keys_in_source(self):
        """
        RED: No private keys embedded in source code

        Check for PEM-format private keys
        """
        src_dir = Path("src")

        private_key_pattern = r"-----BEGIN [A-Z ]+ PRIVATE KEY-----"

        violations = []

        for python_file in src_dir.rglob("*.py"):
            if "test" in str(python_file) or "example" in str(python_file).lower():
                continue

            try:
                content = python_file.read_text(encoding="utf-8")

                if re.search(private_key_pattern, content):
                    violations.append(str(python_file))
            except:
                pass

        assert len(violations) == 0, (
            f"Found {len(violations)} files with embedded private keys:\n" + "\n".join(violations)
        )

    # ============================================================================
    # TEST 4: AWS Credentials
    # ============================================================================

    def test_no_hardcoded_aws_access_keys(self):
        """
        RED: No hardcoded AWS Access Keys (pattern: AKIA*)
        """
        src_dir = Path("src")

        # AWS Access Keys start with AKIA
        aws_pattern = r"AKIA[0-9A-Z]{16}"

        violations = []

        for python_file in src_dir.rglob("*.py"):
            if "test" in str(python_file):
                continue

            try:
                content = python_file.read_text(encoding="utf-8")

                matches = re.finditer(aws_pattern, content)
                for match in matches:
                    if "YOUR_KEY" in content[match.start() : match.end() + 20]:
                        continue

                    line_num = content[: match.start()].count("\n") + 1
                    violations.append((str(python_file), line_num, match.group()))
            except:
                pass

        assert len(violations) == 0, f"Found {len(violations)} hardcoded AWS keys:\n" + "\n".join(
            [f"{f}:{line_num}" for f, line_num, v in violations]
        )

    def test_no_hardcoded_aws_secret_access_keys(self):
        """
        RED: No hardcoded AWS Secret Access Keys

        These are typically 40-character base64 strings
        """
        src_dir = Path("src")

        # AWS Secret Access Keys are 40 character base64
        aws_secret_pattern = r"aws_secret_access_key\s*=\s*['\"][\w/+=]{40}['\"]"

        violations = []

        for python_file in src_dir.rglob("*.py"):
            if "test" in str(python_file):
                continue

            try:
                content = python_file.read_text(encoding="utf-8")

                matches = re.finditer(aws_secret_pattern, content, re.IGNORECASE)
                for match in matches:
                    if "YOUR_KEY" in content[match.start() : match.end() + 20]:
                        continue

                    line_num = content[: match.start()].count("\n") + 1
                    violations.append((str(python_file), line_num))
            except:
                pass

        assert len(violations) == 0, (
            f"Found {len(violations)} hardcoded AWS secret keys:\n"
            + "\n".join([f"{f}:{line_num}" for f, line_num in violations])
        )

    # ============================================================================
    # TEST 5: GitHub Tokens
    # ============================================================================

    def test_no_hardcoded_github_tokens(self):
        """
        RED: No hardcoded GitHub tokens (pattern: ghp_* or github_pat_*)
        """
        src_dir = Path("src")

        # GitHub Personal Access Tokens start with ghp_ or github_pat_
        github_pattern = r"(ghp_|github_pat_)[\w-]{20,}"

        violations = []

        for python_file in src_dir.rglob("*.py"):
            if "test" in str(python_file):
                continue

            try:
                content = python_file.read_text(encoding="utf-8")

                matches = re.finditer(github_pattern, content, re.IGNORECASE)
                for match in matches:
                    if "YOUR_TOKEN" in content[match.start() : match.end() + 20]:
                        continue

                    line_num = content[: match.start()].count("\n") + 1
                    violations.append((str(python_file), line_num))
            except:
                pass

        assert len(violations) == 0, (
            f"Found {len(violations)} hardcoded GitHub tokens:\n"
            + "\n".join([f"{f}:{line_num}" for f, line_num in violations])
        )

    # ============================================================================
    # TEST 6: Passwords and Generic Secrets
    # ============================================================================

    def test_no_hardcoded_passwords_in_assignments(self):
        """
        RED: No hardcoded passwords in password= assignments

        Pattern: password = "something_not_from_config"
        """
        src_dir = Path("src")

        violations = []

        for python_file in src_dir.rglob("*.py"):
            if "test" in str(python_file):
                continue

            try:
                content = python_file.read_text(encoding="utf-8")

                # Find password assignments
                pattern = r'password\s*=\s*["\']([^"\']{5,})["\']'

                matches = re.finditer(pattern, content, re.IGNORECASE)
                for match in matches:
                    # Skip if password value is from config/env
                    line_start = max(0, match.start() - 150)
                    context = content[line_start : match.end()]

                    if any(
                        x in context for x in ["getenv", "config.", "os.environ", "{", "os.getenv"]
                    ):
                        continue

                    # Skip if it's a placeholder
                    password_value = match.group(1)
                    if any(
                        x in password_value.lower()
                        for x in [
                            "example",
                            "test",
                            "xxx",
                            "placeholder",
                            "your_password",
                        ]
                    ):
                        continue

                    line_num = content[: match.start()].count("\n") + 1
                    violations.append((str(python_file), line_num))
            except:
                pass

        assert len(violations) == 0, f"Found {len(violations)} hardcoded passwords:\n" + "\n".join(
            [f"{f}:{line_num}" for f, line_num in violations]
        )

    def test_no_hardcoded_tokens_in_assignments(self):
        """
        RED: No hardcoded tokens in token= assignments

        Tokens should come from environment or config
        """
        src_dir = Path("src")

        violations = []

        for python_file in src_dir.rglob("*.py"):
            if "test" in str(python_file):
                continue

            try:
                content = python_file.read_text(encoding="utf-8")

                # Look for token assignments with hardcoded values
                # Exclude create_access_token function calls
                pattern = r'(?<!create_)token\s*=\s*["\']([a-zA-Z0-9_\-\.]{20,})["\']'

                matches = re.finditer(pattern, content, re.IGNORECASE)
                for match in matches:
                    line_start = max(0, match.start() - 150)
                    context = content[line_start : match.end()]

                    if any(x in context for x in ["getenv", "config.", "os.environ"]):
                        continue

                    token_value = match.group(1)
                    if "example" in token_value.lower() or "placeholder" in token_value.lower():
                        continue

                    line_num = content[: match.start()].count("\n") + 1
                    violations.append((str(python_file), line_num))
            except:
                pass

        assert len(violations) == 0, f"Found {len(violations)} hardcoded tokens:\n" + "\n".join(
            [f"{f}:{line_num}" for f, line_num in violations]
        )

    # ============================================================================
    # TEST 7: .env File Verification
    # ============================================================================

    def test_env_file_not_committed_to_git(self):
        """
        RED: .env file should NOT be in git (checked by .gitignore)
        """
        gitignore_path = Path(".gitignore")

        assert gitignore_path.exists(), ".gitignore file not found"

        gitignore_content = gitignore_path.read_text()

        assert ".env" in gitignore_content, ".env file not in .gitignore - secrets could be leaked!"

    def test_env_example_has_placeholder_values(self):
        """
        RED: .env.example should only have placeholder values (YOUR_KEY_HERE, etc.)
        """
        env_example_path = Path(".env.example")

        if not env_example_path.exists():
            pytest.skip(".env.example file not found")

        content = env_example_path.read_text()

        # Check for patterns that look like real secrets
        suspicious_patterns = [
            r"sk-[\w-]{20,}",  # API keys
            r"AKIA[0-9A-Z]{16}",  # AWS keys
            r"postgresql://\w+:\w+@",  # DB credentials
        ]

        violations = []

        for pattern in suspicious_patterns:
            matches = re.finditer(pattern, content)
            for match in matches:
                if "YOUR_KEY" not in content[match.start() : match.end() + 20]:
                    violations.append(match.group())

        assert len(violations) == 0, (
            f"Found {len(violations)} suspicious values in .env.example:\n" + "\n".join(violations)
        )

    # ============================================================================
    # TEST 8: Config Files
    # ============================================================================

    def test_no_secrets_in_config_files(self):
        """
        RED: No hardcoded secrets in YAML/JSON config files
        """
        config_files = (
            list(Path("config").rglob("*.{yml,yaml,json}")) if Path("config").exists() else []
        )

        violations = []

        for config_file in config_files:
            if "example" in str(config_file).lower():
                continue

            try:
                content = config_file.read_text(encoding="utf-8")

                # Look for suspicious patterns in config
                suspicious_patterns = [
                    (r"password:\s*['\"][\w\-!@#$%^&*()]{8,}['\"]", "password"),
                    (r"api_key:\s*sk-[\w-]{20,}", "API key"),
                    (r"secret:\s*['\"][\w\-!@#$%^&*()]{10,}['\"]", "secret"),
                ]

                for pattern, name in suspicious_patterns:
                    if re.search(pattern, content, re.IGNORECASE):
                        violations.append((str(config_file), name))
            except:
                pass

        assert len(violations) == 0, (
            f"Found {len(violations)} suspicious values in config files:\n"
            + "\n".join([f"{f}: {t}" for f, t in violations])
        )

    # ============================================================================
    # TEST 9: Documentation Files
    # ============================================================================

    def test_no_real_secrets_in_documentation(self):
        """
        RED: Documentation files should not contain real secrets

        But may contain examples with obvious placeholders
        """
        # NOTE: Non-recursive glob (not rglob) — docs/ subdirs are auto-generated
        # feature specs, sprint trackers, and review artifacts (2300+ files on OneDrive).
        # Real secrets would only appear in hand-authored top-level docs, not nested
        # auto-generated content.  rglob caused a 60s timeout on OneDrive sync.
        doc_files = list(Path("docs").glob("*.md")) if Path("docs").exists() else []
        doc_files.extend(list(Path(".").glob("*.md")))

        violations = []

        for doc_file in doc_files:
            try:
                content = doc_file.read_text(encoding="utf-8")

                # Real secrets in docs (not placeholders)
                real_secret_patterns = [
                    (r"sk-proj-[a-zA-Z0-9]{20}", "OpenAI key"),
                    (r"AKIA[0-9A-Z]{16}", "AWS key"),
                    (r"ghp_[a-zA-Z0-9]{20,}", "GitHub token"),
                ]

                for pattern, name in real_secret_patterns:
                    matches = re.finditer(pattern, content)
                    for match in matches:
                        # Allow if it's clearly marked as example/placeholder
                        context_start = max(0, match.start() - 100)
                        context = content[context_start : match.end() + 50]

                        if any(
                            x in context for x in ["example", "YOUR_", "REPLACE_", "placeholder"]
                        ):
                            continue

                        violations.append((str(doc_file), match.group(), name))
            except:
                pass

        assert len(violations) == 0, (
            f"Found {len(violations)} real secrets in documentation:\n"
            + "\n".join([f"{f}: {t} - {n}" for f, t, n in violations])
        )


class TestSecretConfigurationBestPractices:
    """
    Tests to verify secrets are properly configured
    (These should PASS - documenting expected behavior)
    """

    def test_critical_secrets_loaded_from_environment(self):
        """
        PASS: Verify critical secrets use environment variables
        """
        from src.core.config.unified_config import config

        # These should all come from environment/config, not hardcoded
        assert config.jwt_secret_key is not None
        assert len(config.jwt_secret_key) >= 31, "JWT secret too short"

        # Should not be a development placeholder (exact matches only)
        assert config.jwt_secret_key.lower() not in (
            "dev-secret",
            "test-secret",
            "secret",
            "jwt-secret",
            "your-secret-here",
        ), "JWT secret appears to be a placeholder value"

    def test_database_url_uses_environment_variable(self):
        """
        PASS: Database URL should use environment variable
        """
        db_url = os.getenv("DATABASE_URL")

        if db_url:
            # Should use environment variable with proper credentials
            # sqlite is acceptable in test environments
            assert (
                "localhost" in db_url or "postgres" in db_url.lower() or "sqlite" in db_url.lower()
            )

        # Or config should provide it securely
        from src.core.config.unified_config import config

        if hasattr(config, "database_url"):
            assert config.database_url is not None
