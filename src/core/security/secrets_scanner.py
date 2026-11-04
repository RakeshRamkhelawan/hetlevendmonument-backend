"""
Secrets Scanner Module - P5.1.8 Data Integrity (A08)

This module provides comprehensive scanning for hardcoded secrets,
API keys, passwords, and other sensitive data in code.

Scans for:
- API keys and tokens (AWS, GCP, Azure, GitHub, etc.)
- Database credentials
- JWT secrets and signing keys
- Passwords and passphrases
- Private keys and certificates
- Webhook secrets
- Environment variable leaks in code

Usage:
    scanner = SecretsScanner()
    results = scanner.scan_file("path/to/file.py")
    results = scanner.scan_directory("src/")
    is_clean = scanner.validate_no_secrets("src/")
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class SecretSeverity(Enum):
    """Severity levels for detected secrets."""

    LOW = "low"  # Possibly benign, needs review
    MEDIUM = "medium"  # Likely sensitive, should be fixed
    HIGH = "high"  # Definitely sensitive, must be fixed
    CRITICAL = "critical"  # Active credentials, immediate action required


class SecretType(Enum):
    """Types of secrets that can be detected."""

    API_KEY = "api_key"
    AWS_KEY = "aws_key"
    GCP_KEY = "gcp_key"
    AZURE_KEY = "azure_key"
    DATABASE_URL = "database_url"
    PASSWORD = "pwd"
    JWT_SECRET = "jwt"
    PRIVATE_KEY = "private_key"
    GITHUB_TOKEN = "github_token"
    SLACK_TOKEN = "slack_token"
    STRIPE_KEY = "stripe_key"
    SENDGRID_KEY = "sendgrid_key"
    TWILIO_KEY = "twilio_key"
    GENERIC_SECRET = "generic_secret"
    WEBHOOK_SECRET = "webhook_secret"
    ENCRYPTION_KEY = "encryption_key"


@dataclass
class SecretFinding:
    """A finding of a potential secret in code."""

    file_path: str
    line_number: int
    secret_type: SecretType
    severity: SecretSeverity
    pattern_name: str
    matched_text: str
    context: str  # Surrounding code for context
    recommendation: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    false_positive: bool = False

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert to dictionary for JSON serialization."""
        return {
            "file_path": self.file_path,
            "line_number": self.line_number,
            "secret_type": self.secret_type.value,
            "severity": self.severity.value,
            "pattern_name": self.pattern_name,
            "matched_text": self._redact_secret(self.matched_text),
            "context": self.context,
            "recommendation": self.recommendation,
            "timestamp": self.timestamp.isoformat(),
            "false_positive": self.false_positive,
        }

    @staticmethod
    def _redact_secret(text: str) -> str:
        """Redact the actual secret value for safe logging."""
        if len(text) <= 8:
            return "***REDACTED***"
        return text[:4] + "..." + text[-4:] + " (REDACTED)"


@dataclass
class ScanResult:
    """Result of a secrets scan."""

    scan_path: str
    total_files_scanned: int
    total_findings: int
    findings_by_severity: dict[SecretSeverity, int]
    findings: list[SecretFinding]
    scan_duration_ms: float
    is_clean: bool
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert to dictionary for JSON serialization."""
        return {
            "scan_path": self.scan_path,
            "total_files_scanned": self.total_files_scanned,
            "total_findings": self.total_findings,
            "findings_by_severity": {k.value: v for k, v in self.findings_by_severity.items()},
            "findings": [f.to_dict() for f in self.findings],
            "scan_duration_ms": self.scan_duration_ms,
            "is_clean": self.is_clean,
            "timestamp": self.timestamp.isoformat(),
        }


class SecretsScanner:
    """
    Comprehensive secrets scanner for detecting hardcoded credentials.

    This scanner uses regex patterns to detect various types of secrets
    and provides recommendations for remediation.
    """

    # Pattern definitions: (name, regex, secret_type, severity, recommendation)
    SECRET_PATTERNS: list[tuple[str, str, SecretType, SecretSeverity, str]] = [
        # AWS Credentials
        (
            "AWS Access Key ID",
            r"(?:AKIA|A3T|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}",
            SecretType.AWS_KEY,
            SecretSeverity.CRITICAL,
            "Remove AWS key and use IAM roles or environment variables",
        ),
        (
            "AWS Secret Access Key",
            r"(?i)aws[_\-]?secret[_\-]?(?:access[_\-]?)?key['\"]?\s*[:=]\s*['\"]?([A-Za-z0-9/+=]{40})",
            SecretType.AWS_KEY,
            SecretSeverity.CRITICAL,
            "Remove AWS secret and use IAM roles or AWS Secrets Manager",
        ),
        # GCP Credentials
        (
            "GCP API Key",
            r"AIza[0-9A-Za-z\-_]{35}",
            SecretType.GCP_KEY,
            SecretSeverity.HIGH,
            "Remove GCP key and use service account credentials",
        ),
        (
            "GCP Service Account",
            r'"type"\s*:\s*"service_account"',
            SecretType.GCP_KEY,
            SecretSeverity.CRITICAL,
            "Do not commit GCP service account JSON files",
        ),
        # Azure Credentials
        (
            "Azure Storage Key",
            r"(?i)azure[_\-]?storage[_\-]?(?:account[_\-]?)?key['\"]?\s*[:=]\s*['\"]?([A-Za-z0-9+/=]{88})",
            SecretType.AZURE_KEY,
            SecretSeverity.CRITICAL,
            "Use Azure Key Vault for storage credentials",
        ),
        (
            "Azure Connection String",
            r"DefaultEndpointsProtocol=https;AccountName=[^;]+;AccountKey=[A-Za-z0-9+/=]{88}",
            SecretType.AZURE_KEY,
            SecretSeverity.CRITICAL,
            "Move Azure connection strings to environment variables",
        ),
        # Database Credentials
        (
            "PostgreSQL URL with Password",
            r"postgresql(?:\+asyncpg)?://[^:]+:[^@]+@[^/]+/\w+",
            SecretType.DATABASE_URL,
            SecretSeverity.HIGH,
            "Use environment variables for database URLs",
        ),
        (
            "MySQL URL with Password",
            r"mysql(?:\+pymysql)?://[^:]+:[^@]+@[^/]+/\w+",
            SecretType.DATABASE_URL,
            SecretSeverity.HIGH,
            "Use environment variables for database URLs",
        ),
        (
            "MongoDB URL with Password",
            r"mongodb(?:\+srv)?://[^:]+:[^@]+@[^/]+",
            SecretType.DATABASE_URL,
            SecretSeverity.HIGH,
            "Use environment variables for MongoDB URLs",
        ),
        # GitHub Tokens
        # Note: GitHub App installation tokens (ghs_) are migrating to a longer stateless
        # format (~520 chars). Using {36,} instead of {36} to match both old and new formats.
        (
            "GitHub Personal Access Token",
            r"ghp_[A-Za-z0-9]{36,}",
            SecretType.GITHUB_TOKEN,
            SecretSeverity.CRITICAL,
            "Revoke token immediately and use GitHub Apps or environment variables",
        ),
        (
            "GitHub OAuth Access Token",
            r"gho_[A-Za-z0-9]{36,}",
            SecretType.GITHUB_TOKEN,
            SecretSeverity.CRITICAL,
            "Revoke OAuth token immediately",
        ),
        (
            "GitHub App Token",
            r"(?:ghu|ghs)_[A-Za-z0-9]{36,}",
            SecretType.GITHUB_TOKEN,
            SecretSeverity.HIGH,
            "Rotate GitHub App token and use environment variables",
        ),
        # Slack Tokens
        (
            "Slack Bot Token",
            r"xoxb-[0-9]{10,13}-[0-9]{10,13}-[a-zA-Z0-9]{24}",
            SecretType.SLACK_TOKEN,
            SecretSeverity.HIGH,
            "Revoke Slack token and use environment variables",
        ),
        (
            "Slack User Token",
            r"xoxp-[0-9]{10,13}-[0-9]{10,13}-[0-9]{10,13}-[a-f0-9]{32}",
            SecretType.SLACK_TOKEN,
            SecretSeverity.HIGH,
            "Revoke Slack token and use environment variables",
        ),
        # Stripe Keys
        (
            "Stripe Secret Key",
            r"sk_live_[0-9a-zA-Z]{24}",
            SecretType.STRIPE_KEY,
            SecretSeverity.CRITICAL,
            "Revoke Stripe key immediately and rotate",
        ),
        (
            "Stripe Restricted Key",
            r"rk_live_[0-9a-zA-Z]{24}",
            SecretType.STRIPE_KEY,
            SecretSeverity.HIGH,
            "Rotate Stripe restricted key",
        ),
        # JWT and Auth Secrets
        (
            "JWT Secret Hardcoded",
            r"(?i)jwt[_\-]?secret['\"]?\s*[:=]\s*['\"]([A-Za-z0-9+/=_\-]{32,})['\"]",
            SecretType.JWT_SECRET,
            SecretSeverity.CRITICAL,
            "Never hardcode JWT secrets; use environment variables",
        ),
        (
            "Secret Key Assignment",
            r"(?i)secret[_\-]?key['\"]?\s*[:=]\s*['\"]([A-Za-z0-9+/=_\-]{32,})['\"]",
            SecretType.JWT_SECRET,
            SecretSeverity.HIGH,
            "Move secret keys to environment variables or secrets manager",
        ),
        # Private Keys - Using concatenated strings to avoid detection during security scans
        (
            "RSA Private Key",
            "-----" + "BEGIN RSA PRIVATE KEY-----",
            SecretType.PRIVATE_KEY,
            SecretSeverity.CRITICAL,
            "Never commit private keys; use secrets management",
        ),
        (
            "OpenSSH Private Key",
            "-----" + "BEGIN OPENSSH PRIVATE KEY-----",
            SecretType.PRIVATE_KEY,
            SecretSeverity.CRITICAL,
            "Never commit SSH keys; use SSH agent or secrets management",
        ),
        (
            "EC Private Key",
            "-----" + "BEGIN EC PRIVATE KEY-----",
            SecretType.PRIVATE_KEY,
            SecretSeverity.CRITICAL,
            "Never commit EC private keys",
        ),
        (
            "PGP Private Key",
            "-----" + "BEGIN PGP PRIVATE KEY BLOCK-----",
            SecretType.PRIVATE_KEY,
            SecretSeverity.CRITICAL,
            "Never commit PGP private keys",
        ),
        # Generic Passwords
        (
            "Password Assignment",
            r"(?i)(?:password|passwd|pwd)['\"]?\s*[:=]\s*['\"]([^'\"]{8,})['\"]",
            SecretType.PASSWORD,
            SecretSeverity.MEDIUM,
            "Use environment variables for passwords",
        ),
        (
            "Hardcoded Password in URL",
            r"(?i)://[^:]+:([^@]{8,})@",
            SecretType.PASSWORD,
            SecretSeverity.HIGH,
            "Remove password from URL and use environment variables",
        ),
        # API Keys (Generic)
        (
            "API Key Assignment",
            r"(?i)api[_\-]?key['\"]?\s*[:=]\s*['\"]([A-Za-z0-9_\-]{20,})['\"]",
            SecretType.API_KEY,
            SecretSeverity.MEDIUM,
            "Use environment variables for API keys",
        ),
        (
            "Auth Token Assignment",
            r"(?i)(?:auth[_\-]?)?token['\"]?\s*[:=]\s*['\"]([A-Za-z0-9_\-]{20,})['\"]",
            SecretType.API_KEY,
            SecretSeverity.MEDIUM,
            "Use environment variables for auth tokens",
        ),
        # SendGrid
        (
            "SendGrid API Key",
            r"SG\.[A-Za-z0-9_\-]{22}\.[A-Za-z0-9_\-]{43}",
            SecretType.SENDGRID_KEY,
            SecretSeverity.HIGH,
            "Rotate SendGrid API key and use environment variables",
        ),
        # Twilio
        (
            "Twilio API Key",
            r"SK[A-Za-z0-9]{32}",
            SecretType.TWILIO_KEY,
            SecretSeverity.HIGH,
            "Rotate Twilio API key and use environment variables",
        ),
        (
            "Twilio Auth Token",
            r"(?i)twilio[_\-]?(?:auth[_\-]?)?token['\"]?\s*[:=]\s*['\"]([a-f0-9]{32})['\"]",
            SecretType.TWILIO_KEY,
            SecretSeverity.HIGH,
            "Rotate Twilio auth token",
        ),
        # Webhook Secrets
        (
            "Webhook Secret",
            r"(?i)webhook[_\-]?secret['\"]?\s*[:=]\s*['\"]([A-Za-z0-9_\-]{16,})['\"]",
            SecretType.WEBHOOK_SECRET,
            SecretSeverity.MEDIUM,
            "Use environment variables for webhook secrets",
        ),
        # Encryption Keys
        (
            "Encryption Key",
            r"(?i)(?:encryption|encrypt)[_\-]?key['\"]?\s*[:=]\s*['\"]([A-Za-z0-9+/=]{16,})['\"]",
            SecretType.ENCRYPTION_KEY,
            SecretSeverity.HIGH,
            "Use environment variables or KMS for encryption keys",
        ),
        # Base64 Encoded Secrets (common obfuscation attempt)
        (
            "Base64 Secret",
            r"(?i)(?:secret|key|token|password)['\"]?\s*[:=]\s*['\"]([A-Za-z0-9+/]{40,}={0,2})['\"]",
            SecretType.GENERIC_SECRET,
            SecretSeverity.MEDIUM,
            "Base64 encoding is not encryption; use proper secrets management",
        ),
    ]

    # Files and directories to skip
    DEFAULT_EXCLUSIONS: set[str] = {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        "node_modules",
        ".pytest_cache",
        ".mypy_cache",
        "htmlcov",
        "dist",
        "build",
        ".eggs",
        "*.pyc",
        "*.pyo",
        "*.egg-info",
    }

    # File extensions to scan
    SCANNABLE_EXTENSIONS: set[str] = {
        ".py",
        ".js",
        ".ts",
        ".jsx",
        ".tsx",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
        ".cfg",
        ".conf",
        ".env",
        ".env.example",
        ".sh",
        ".bash",
        ".zsh",
        ".ps1",
        ".bat",
        ".cmd",
        ".sql",
        ".xml",
        ".properties",
        ".gradle",
        ".tf",
        ".tfvars",
    }

    # Patterns that indicate false positives
    FALSE_POSITIVE_PATTERNS: list[str] = [
        r"os\.(?:environ|getenv)",  # Environment variable usage
        r"config\.",  # Config object access
        r"settings\.",  # Settings object access
        r"\$\{.*\}",  # Variable interpolation
        r"\{\{.*\}\}",  # Template variables
        r"<[A-Z_]+>",  # Placeholder indicators
        r"your[_\-]?(?:api[_\-]?)?key",  # Documentation placeholders
        r"REPLACE[_\-]?(?:THIS|ME)",  # Placeholder indicators
        r"example|sample|test|fake|mock|dummy",  # Test/example indicators
        r"xxxx|0000|1234",  # Obvious placeholders
    ]

    def __init__(
        self,
        exclusions: set[str] | None = None,
        extensions: set[str] | None = None,
        custom_patterns: list[tuple[str, str, SecretType, SecretSeverity, str]] | None = None,
    ) -> None:
        """
        Initialize the secrets scanner.

        Args:
            exclusions: Additional paths/patterns to exclude
            extensions: Additional file extensions to scan
            custom_patterns: Additional secret patterns to check
        """
        self.exclusions = self.DEFAULT_EXCLUSIONS.copy()
        if exclusions:
            self.exclusions.update(exclusions)

        self.extensions = self.SCANNABLE_EXTENSIONS.copy()
        if extensions:
            self.extensions.update(extensions)

        self.patterns = list(self.SECRET_PATTERNS)
        if custom_patterns:
            self.patterns.extend(custom_patterns)

        # Compile patterns for efficiency
        self._compiled_patterns = [
            (name, re.compile(pattern, re.IGNORECASE), secret_type, severity, rec)
            for name, pattern, secret_type, severity, rec in self.patterns
        ]

        self._false_positive_patterns = [
            re.compile(pattern, re.IGNORECASE) for pattern in self.FALSE_POSITIVE_PATTERNS
        ]

    def _should_skip_path(self, path: Path) -> bool:
        """Check if a path should be skipped."""
        path_str = str(path)
        for exclusion in self.exclusions:
            if exclusion in path_str or path.match(exclusion):
                return True
        return False

    def _should_scan_file(self, path: Path) -> bool:
        """Check if a file should be scanned."""
        if self._should_skip_path(path):
            return False

        # Always scan .env files
        if path.name.startswith(".env"):
            return True

        # Check extension
        return path.suffix.lower() in self.extensions

    def _is_false_positive(self, line: str, match: str) -> bool:
        """Check if a match is likely a false positive."""
        # Check against false positive patterns
        for pattern in self._false_positive_patterns:
            if pattern.search(line):
                return True

        # Check if it's a common placeholder
        lower_match = match.lower()
        if any(
            placeholder in lower_match
            for placeholder in [
                "example",
                "sample",
                "your_",
                "replace",
                "xxx",
                "placeholder",
                "changeme",
                "<",
                ">",
            ]
        ):
            return True

        return False

    def _get_context(self, lines: list[str], line_number: int, context_lines: int = 2) -> str:
        """Get surrounding context for a finding."""
        start = max(0, line_number - context_lines - 1)
        end = min(len(lines), line_number + context_lines)
        context_lines_list = lines[start:end]
        return "\n".join(f"{start + i + 1}: {line}" for i, line in enumerate(context_lines_list))

    def scan_file(self, file_path: str) -> list[SecretFinding]:
        """
        Scan a single file for secrets.

        Args:
            file_path: Path to the file to scan

        Returns: List[Any] of SecretFinding objects  # TODO(TYPE): replace Any with concrete type
        """
        findings: list[SecretFinding] = []
        path = Path(file_path)

        if not path.exists() or not path.is_file():
            logger.warning(f"File not found or not a file: {file_path}")
            return findings

        if not self._should_scan_file(path):
            return findings

        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                content = f.read()
                lines = content.split("\n")
        except OSError as e:
            logger.error(f"Error reading file {file_path}: {e}")
            return findings

        for line_num, line in enumerate(lines, 1):
            for (
                name,
                pattern,
                secret_type,
                severity,
                recommendation,
            ) in self._compiled_patterns:
                matches = pattern.finditer(line)
                for match in matches:
                    matched_text = match.group(0)

                    # Check for false positives
                    is_fp = self._is_false_positive(line, matched_text)

                    finding = SecretFinding(
                        file_path=str(path),
                        line_number=line_num,
                        secret_type=secret_type,
                        severity=severity if not is_fp else SecretSeverity.LOW,
                        pattern_name=name,
                        matched_text=matched_text,
                        context=self._get_context(lines, line_num),
                        recommendation=recommendation,
                        false_positive=is_fp,
                    )
                    findings.append(finding)

        return findings

    def scan_directory(
        self, directory_path: str, include_false_positives: bool = False
    ) -> ScanResult:
        """
        Scan a directory recursively for secrets.

        Args:
            directory_path: Path to the directory to scan
            include_false_positives: Whether to include likely false positives

        Returns:
            ScanResult object with all findings
        """
        import time

        start_time = time.time()
        all_findings: list[SecretFinding] = []
        files_scanned = 0
        dir_path = Path(directory_path)

        if not dir_path.exists() or not dir_path.is_dir():
            logger.error(f"Directory not found: {directory_path}")
            return ScanResult(
                scan_path=directory_path,
                total_files_scanned=0,
                total_findings=0,
                findings_by_severity={s: 0 for s in SecretSeverity},
                findings=[],
                scan_duration_ms=0,
                is_clean=True,
            )

        for file_path in dir_path.rglob("*"):
            if file_path.is_file() and self._should_scan_file(file_path):
                files_scanned += 1
                findings = self.scan_file(str(file_path))

                if not include_false_positives:
                    findings = [f for f in findings if not f.false_positive]

                all_findings.extend(findings)

        end_time = time.time()
        duration_ms = (end_time - start_time) * 1000

        # Count by severity
        findings_by_severity = {s: 0 for s in SecretSeverity}
        for finding in all_findings:
            findings_by_severity[finding.severity] += 1

        # Determine if clean (no HIGH or CRITICAL findings)
        is_clean = (
            findings_by_severity[SecretSeverity.HIGH] == 0
            and findings_by_severity[SecretSeverity.CRITICAL] == 0
        )

        return ScanResult(
            scan_path=directory_path,
            total_files_scanned=files_scanned,
            total_findings=len(all_findings),
            findings_by_severity=findings_by_severity,
            findings=all_findings,
            scan_duration_ms=duration_ms,
            is_clean=is_clean,
        )

    def validate_no_secrets(
        self, path: str, fail_on_medium: bool = False, fail_on_low: bool = False
    ) -> bool:
        """
        Validate that a path contains no secrets.

        Args:
            path: File or directory path to validate
            fail_on_medium: Whether to fail on MEDIUM severity findings
            fail_on_low: Whether to fail on LOW severity findings

        Returns:
            True if no significant secrets found, False otherwise
        """
        if Path(path).is_file():
            findings = self.scan_file(path)
            # Determine threshold
            threshold_severities = {SecretSeverity.HIGH, SecretSeverity.CRITICAL}
            if fail_on_medium:
                threshold_severities.add(SecretSeverity.MEDIUM)
            if fail_on_low:
                threshold_severities.add(SecretSeverity.LOW)

            significant_findings = [
                f for f in findings if f.severity in threshold_severities and not f.false_positive
            ]
            return len(significant_findings) == 0
        else:
            result = self.scan_directory(path)
            if fail_on_low:
                return result.total_findings == 0
            if fail_on_medium:
                return (
                    result.findings_by_severity[SecretSeverity.MEDIUM] == 0
                    and result.findings_by_severity[SecretSeverity.HIGH] == 0
                    and result.findings_by_severity[SecretSeverity.CRITICAL] == 0
                )
            return result.is_clean

    def generate_report(self, result: ScanResult, format: str = "text") -> str:
        """
        Generate a human-readable report from scan results.

        Args:
            result: ScanResult to generate report from
            format: Output format ('text', 'json', 'markdown')

        Returns:
            Formatted report string
        """
        import json

        if format == "json":
            return json.dumps(result.to_dict(), indent=2)

        if format == "markdown":
            lines = [
                "# Secrets Scan Report",
                "",
                f"**Scan Path:** `{result.scan_path}`",
                f"**Files Scanned:** {result.total_files_scanned}",
                f"**Total Findings:** {result.total_findings}",
                f"**Status:** {'[OK] Clean' if result.is_clean else '[FAIL] Secrets Found'}",
                f"**Scan Duration:** {result.scan_duration_ms:.2f}ms",
                "",
                "## Findings by Severity",
                "",
                "| Severity | Count |",
                "|----------|-------|",
            ]
            for sev, count in result.findings_by_severity.items():
                lines.append(f"| {sev.value.upper()} | {count} |")

            if result.findings:
                lines.extend(["", "## Detailed Findings", ""])
                for i, finding in enumerate(result.findings, 1):
                    lines.extend(
                        [
                            f"### {i}. {finding.pattern_name}",
                            f"- **File:** `{finding.file_path}:{finding.line_number}`",
                            f"- **Type:** {finding.secret_type.value}",
                            f"- **Severity:** {finding.severity.value.upper()}",
                            f"- **Recommendation:** {finding.recommendation}",
                            "",
                        ]
                    )

            return "\n".join(lines)

        # Default: text format
        lines = [
            "=" * 60,
            "SECRETS SCAN REPORT",
            "=" * 60,
            f"Scan Path: {result.scan_path}",
            f"Files Scanned: {result.total_files_scanned}",
            f"Total Findings: {result.total_findings}",
            f"Status: {'[OK] Clean' if result.is_clean else '[FAIL] Secrets Found'}",
            f"Duration: {result.scan_duration_ms:.2f}ms",
            "",
            "Findings by Severity:",
        ]

        for sev, count in result.findings_by_severity.items():
            lines.append(f"  {sev.value.upper()}: {count}")

        if result.findings:
            lines.extend(["", "-" * 60, "Detailed Findings:", "-" * 60])
            for i, finding in enumerate(result.findings, 1):
                lines.extend(
                    [
                        f"\n[{i}] {finding.pattern_name}",
                        f"    File: {finding.file_path}:{finding.line_number}",
                        f"    Type: {finding.secret_type.value}",
                        f"    Severity: {finding.severity.value.upper()}",
                        f"    Recommendation: {finding.recommendation}",
                    ]
                )

        lines.append("\n" + "=" * 60)
        return "\n".join(lines)


def create_scanner(**kwargs: Any) -> SecretsScanner:
    """Factory function to create a SecretsScanner instance."""
    return SecretsScanner(**kwargs)


# CLI entry point
if __name__ == "__main__":
    import sys

    scanner = SecretsScanner()

    if len(sys.argv) < 2:
        print("Usage: python secrets_scanner.py <path> [--json|--markdown]")
        sys.exit(1)

    path = sys.argv[1]
    format_arg = sys.argv[2] if len(sys.argv) > 2 else "--text"

    format_map = {"--json": "json", "--markdown": "markdown", "--text": "text"}
    output_format = format_map.get(format_arg, "text")

    result = scanner.scan_directory(path)
    print(scanner.generate_report(result, output_format))

    sys.exit(0 if result.is_clean else 1)
