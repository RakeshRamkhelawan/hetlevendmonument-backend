"""
Architecture tests: single-tenant deployment artefacts (AUDIT-ST-02).
"""

from pathlib import Path


def test_single_tenant_compose_exists():
    assert Path("docker-compose.single-tenant.yml").exists()


def test_single_tenant_env_example_exists():
    assert Path(".env.single-tenant.example").exists()


def test_single_tenant_guide_exists():
    assert Path("docs/deployment/single-tenant-guide.md").exists()
