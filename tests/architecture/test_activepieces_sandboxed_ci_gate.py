"""CI-gate tegen herhaling van de F-09-regressie (AUDIT-ARCH-2026-07-02 SEC-ARCH-001).

F-09 (commit 27a9bbf0, 2026-05-26) zette AP_EXECUTION_MODE op SANDBOXED in
cd-production.yml en cd-staging.yml, met AP_WORKER_TYPE=THREAD als mitigatie voor de
Azure Container Apps DinD-beperking. Commit e6c67529 (CI/CD pipeline redesign,
cherry-pick vanaf main) heeft dit stilzwijgend teruggedraaid naar UNSANDBOXED in
beide productie/staging-deploy-workflows. Deze test faalt zodra dat patroon opnieuw
in een deploy-workflow verschijnt.
"""

from pathlib import Path

WORKFLOWS_DIR = Path("src").resolve().parent / ".github" / "workflows"

PROD_STAGING_WORKFLOWS = [
    WORKFLOWS_DIR / "cd-production.yml",
    WORKFLOWS_DIR / "cd-staging.yml",
]


def test_no_unsandboxed_activepieces_in_deploy_workflows() -> None:
    """AP_EXECUTION_MODE=UNSANDBOXED mag nergens in een prod/staging deploy-workflow staan."""
    violations = []
    for workflow in PROD_STAGING_WORKFLOWS:
        assert workflow.exists(), f"Workflow-bestand ontbreekt: {workflow}"
        content = workflow.read_text(encoding="utf-8")
        if "AP_EXECUTION_MODE=UNSANDBOXED" in content:
            violations.append(str(workflow))

    assert not violations, (
        "AP_EXECUTION_MODE=UNSANDBOXED gevonden in: "
        f"{violations}. Dit is een regressie van F-09 (commit 27a9bbf0) -- "
        "moet AP_EXECUTION_MODE=SANDBOXED zijn."
    )


def test_activepieces_sandboxed_mode_present_in_deploy_workflows() -> None:
    """AP_EXECUTION_MODE=SANDBOXED + AP_WORKER_TYPE=THREAD moeten aanwezig zijn (F-09-mitigatie)."""
    for workflow in PROD_STAGING_WORKFLOWS:
        content = workflow.read_text(encoding="utf-8")
        assert "AP_EXECUTION_MODE=SANDBOXED" in content, (
            f"{workflow} mist AP_EXECUTION_MODE=SANDBOXED (F-09-fix, commit 27a9bbf0)"
        )
        assert "AP_WORKER_TYPE=THREAD" in content, (
            f"{workflow} mist AP_WORKER_TYPE=THREAD "
            "(expliciete DinD-mitigatie uit de F-09-fix, commit 27a9bbf0)"
        )
