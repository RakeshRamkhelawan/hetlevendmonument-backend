"""AUDIT-ARCH-2026-07-02 Dag 2 losse P1 -- DEVOPS-001 /
devops-predeploy-check-not-wired-in-cicd.

`scripts/pre-deploy-check.sh` (dat Day 1's FA-001-migratieblocker reproduceerbaar
aantoonde -- zie BE-DATA-001) werd nergens in de CI/CD-pipeline aangeroepen.
Rakesh moest het altijd handmatig draaien voor elke deploy; een vergeten
handmatige stap is precies het soort regressie dat dit script had moeten
voorkomen.
"""

from pathlib import Path

WORKFLOW_FILE = Path(".github/workflows/cd-production.yml").resolve()


def test_pre_deploy_check_script_is_invoked_in_cd_pipeline() -> None:
    content = WORKFLOW_FILE.read_text(encoding="utf-8")
    assert "scripts/pre-deploy-check.sh" in content, (
        "scripts/pre-deploy-check.sh wordt nergens aangeroepen in cd-production.yml (DEVOPS-001)."
    )


def test_build_jobs_depend_on_pre_deploy_check() -> None:
    """De build-jobs moeten wachten op een groene pre-deploy-check voordat er
    dure Docker-builds/deploys starten (fail-fast, geen tijd verspild aan builds
    die toch geblokkeerd worden door een kapotte migratie-keten of compose-config)."""
    content = WORKFLOW_FILE.read_text(encoding="utf-8")
    for job in ("build-backend", "build-frontend", "build-worker"):
        job_start = content.index(f"  {job}:")
        job_block = content[job_start : job_start + 400]
        assert "pre-deploy-check" in job_block, (
            f"{job} heeft geen 'needs: [..., pre-deploy-check]' -- de pre-deploy-check "
            "kan falen zonder de build/deploy te blokkeren."
        )
