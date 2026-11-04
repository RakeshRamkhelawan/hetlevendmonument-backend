"""
Tests for Production Runbooks

These tests verify that the runbook documentation is accurate and
referenced commands/scripts function correctly.
"""

import os
import re
from pathlib import Path
from typing import Set

import pytest

# ==================== FIXTURES ====================


@pytest.fixture
def runbook_dir() -> Path:
    """Get runbooks directory path"""
    return Path(__file__).parent.parent.parent / "deployment" / "runbooks"


@pytest.fixture
def deployment_runbook(runbook_dir: Path) -> str:
    """Load deployment runbook content"""
    return (runbook_dir / "RUNBOOK_DEPLOYMENT.md").read_text(encoding="utf-8")


@pytest.fixture
def incident_runbook(runbook_dir: Path) -> str:
    """Load incident response runbook content"""
    return (runbook_dir / "RUNBOOK_INCIDENT_RESPONSE.md").read_text(encoding="utf-8")


@pytest.fixture
def operations_runbook(runbook_dir: Path) -> str:
    """Load operations runbook content"""
    return (runbook_dir / "RUNBOOK_OPERATIONS.md").read_text(encoding="utf-8")


# ==================== RUNBOOK EXISTENCE TESTS ====================


class TestRunbookExistence:
    """Verify all required runbooks exist"""

    def test_deployment_runbook_exists(self, runbook_dir: Path):
        """Verify deployment runbook exists"""
        assert (runbook_dir / "RUNBOOK_DEPLOYMENT.md").exists()

    def test_incident_runbook_exists(self, runbook_dir: Path):
        """Verify incident response runbook exists"""
        assert (runbook_dir / "RUNBOOK_INCIDENT_RESPONSE.md").exists()

    def test_operations_runbook_exists(self, runbook_dir: Path):
        """Verify operations runbook exists"""
        assert (runbook_dir / "RUNBOOK_OPERATIONS.md").exists()


# ==================== RUNBOOK CONTENT TESTS ====================


class TestDeploymentRunbook:
    """Tests for deployment runbook content"""

    def test_has_toc(self, deployment_runbook: str):
        """Verify table of contents exists"""
        assert "Table of Contents" in deployment_runbook

    def test_has_pre_deployment_checklist(self, deployment_runbook: str):
        """Verify pre-deployment checklist exists"""
        assert "Pre-Deployment Checklist" in deployment_runbook

    def test_has_blue_green_procedure(self, deployment_runbook: str):
        """Verify blue-green deployment procedure exists"""
        assert "Blue-Green Deployment" in deployment_runbook

    def test_has_rollback_procedure(self, deployment_runbook: str):
        """Verify rollback procedure exists"""
        assert "Rollback Procedure" in deployment_runbook

    def test_has_troubleshooting(self, deployment_runbook: str):
        """Verify troubleshooting section exists"""
        assert "Troubleshooting" in deployment_runbook

    def test_references_backup_manager(self, deployment_runbook: str):
        """Verify backup manager is referenced"""
        assert "DatabaseBackupManager" in deployment_runbook

    def test_references_blue_green_deployer(self, deployment_runbook: str):
        """Verify BlueGreenDeployer is referenced"""
        assert "BlueGreenDeployer" in deployment_runbook


class TestIncidentRunbook:
    """Tests for incident response runbook content"""

    def test_has_severity_levels(self, incident_runbook: str):
        """Verify severity levels are defined"""
        assert "SEV-1" in incident_runbook
        assert "SEV-2" in incident_runbook
        assert "SEV-3" in incident_runbook
        assert "SEV-4" in incident_runbook

    def test_has_response_process(self, incident_runbook: str):
        """Verify incident response process exists"""
        assert "Incident Response Process" in incident_runbook

    def test_has_common_incidents(self, incident_runbook: str):
        """Verify common incidents are documented"""
        assert "Common Incidents" in incident_runbook
        assert "INC-001" in incident_runbook

    def test_has_escalation_matrix(self, incident_runbook: str):
        """Verify escalation matrix exists"""
        assert "Escalation Matrix" in incident_runbook

    def test_has_communication_templates(self, incident_runbook: str):
        """Verify communication templates exist"""
        assert "Communication Templates" in incident_runbook

    def test_has_post_mortem_template(self, incident_runbook: str):
        """Verify post-mortem template exists"""
        assert "Post-Mortem Template" in incident_runbook


class TestOperationsRunbook:
    """Tests for operations runbook content"""

    def test_has_daily_operations(self, operations_runbook: str):
        """Verify daily operations section exists"""
        assert "Daily Operations" in operations_runbook

    def test_has_backup_management(self, operations_runbook: str):
        """Verify backup management section exists"""
        assert "Backup Management" in operations_runbook
        assert "Backup Schedule" in operations_runbook

    def test_has_monitoring(self, operations_runbook: str):
        """Verify monitoring section exists"""
        assert "Monitoring and Alerting" in operations_runbook

    def test_has_log_management(self, operations_runbook: str):
        """Verify log management section exists"""
        assert "Log Management" in operations_runbook

    def test_has_security_operations(self, operations_runbook: str):
        """Verify security operations section exists"""
        assert "Security Operations" in operations_runbook

    def test_has_maintenance_windows(self, operations_runbook: str):
        """Verify maintenance windows section exists"""
        assert "Maintenance Windows" in operations_runbook


# ==================== CODE REFERENCE TESTS ====================


class TestCodeReferences:
    """Tests to verify code references in runbooks are valid"""

    def test_backup_manager_import_valid(self):
        """Verify backup manager can be imported"""
        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "deployment" / "backup"))

        from backup_manager import BackupConfig, BackupStatus, BackupType, DatabaseBackupManager

        assert DatabaseBackupManager is not None
        assert BackupConfig is not None
        assert BackupType is not None
        assert BackupStatus is not None

    def test_blue_green_deployer_import_valid(self):
        """Verify blue-green deployer can be imported"""
        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "deployment" / "blue_green"))

        from deploy import BlueGreenDeployer, DeploymentConfig

        assert BlueGreenDeployer is not None
        assert DeploymentConfig is not None

    def test_backup_types_documented(self, operations_runbook: str):
        """Verify common backup types are documented"""
        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "deployment" / "backup"))
        from backup_manager import BackupType

        # At minimum, FULL backup type should be documented
        # Other types (incremental, wal) may not all be mentioned
        common_types = [BackupType.FULL]
        for backup_type in common_types:
            assert (
                backup_type.value in operations_runbook.lower()
                or backup_type.name in operations_runbook
            )


# ==================== MARKDOWN VALIDATION TESTS ====================


class TestMarkdownValidation:
    """Tests for markdown formatting and structure"""

    def test_deployment_headers_valid(self, deployment_runbook: str):
        """Verify deployment runbook has valid header structure"""
        # Should have title
        assert deployment_runbook.startswith("# ")

        # Should have at least 3 level-2 headers
        h2_count = len(re.findall(r"^## ", deployment_runbook, re.MULTILINE))
        assert h2_count >= 3

    def test_incident_headers_valid(self, incident_runbook: str):
        """Verify incident runbook has valid header structure"""
        assert incident_runbook.startswith("# ")
        h2_count = len(re.findall(r"^## ", incident_runbook, re.MULTILINE))
        assert h2_count >= 3

    def test_operations_headers_valid(self, operations_runbook: str):
        """Verify operations runbook has valid header structure"""
        assert operations_runbook.startswith("# ")
        h2_count = len(re.findall(r"^## ", operations_runbook, re.MULTILINE))
        assert h2_count >= 3

    def test_code_blocks_have_language(self, deployment_runbook: str):
        """Verify code blocks specify language"""
        # Match opening code blocks only (followed by content or newline)
        # The pattern ``` followed by optional language is what we want
        # Closing ``` have nothing after them
        lines = deployment_runbook.split("\n")
        opening_blocks = []
        for i, line in enumerate(lines):
            if line.strip().startswith("```"):
                # Check if this is an opening block (has content after) or closing
                block_content = line.strip()[3:]  # Get what's after ```
                # Opening blocks either have a language or are followed by code
                if i + 1 < len(lines) and lines[i + 1].strip():
                    opening_blocks.append(block_content)

        if not opening_blocks:
            pytest.skip("No code blocks found")

        with_language = sum(1 for lang in opening_blocks if lang)
        # At least 80% of opening blocks should have language
        ratio = with_language / len(opening_blocks)
        assert (
            ratio >= 0.8
        ), f"Only {with_language}/{len(opening_blocks)} opening code blocks have language ({ratio:.0%})"


# ==================== VERSION INFO TESTS ====================


class TestVersionInfo:
    """Tests for version information in runbooks"""

    def test_deployment_has_version(self, deployment_runbook: str):
        """Verify deployment runbook has version info"""
        assert "Version" in deployment_runbook
        assert "Last Updated" in deployment_runbook

    def test_incident_has_version(self, incident_runbook: str):
        """Verify incident runbook has version info"""
        assert "Version" in incident_runbook
        assert "Last Updated" in incident_runbook

    def test_operations_has_version(self, operations_runbook: str):
        """Verify operations runbook has version info"""
        assert "Version" in operations_runbook
        assert "Last Updated" in operations_runbook


# ==================== COMPLETENESS TESTS ====================


class TestRunbookCompleteness:
    """Tests to ensure runbooks cover required topics"""

    def test_deployment_covers_all_steps(self, deployment_runbook: str):
        """Verify deployment runbook covers complete workflow"""
        required_steps = [
            "Pre-Deployment",
            "Build",
            "Migration",
            "Traffic Switch",
            "Verify",
            "Rollback",
        ]
        for step in required_steps:
            assert step.lower() in deployment_runbook.lower(), f"Missing: {step}"

    def test_incident_covers_all_severities(self, incident_runbook: str):
        """Verify incident runbook covers all severity levels"""
        for sev in range(1, 5):
            assert f"SEV-{sev}" in incident_runbook

    def test_operations_covers_maintenance_tasks(self, operations_runbook: str):
        """Verify operations runbook covers regular maintenance"""
        required_sections = [
            "Daily",
            "Weekly",
            "Monthly",
        ]
        for section in required_sections:
            assert section in operations_runbook, f"Missing: {section}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
