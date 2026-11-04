"""TODO(SP-DATA-ARCH-1): agentic seed scripts break under the new tenant_id NOT NULL
constraint (Sprint Dag 1 Groep 4, AUDIT-ARCH-2026-07-02).

DATA-001/DB-AUDIT-001 made tenant_id NOT NULL on Feature/ToolDefinition/PromptTemplate.
`src/domains/agentic/seeds/run_seeds.py` (seed_features, seed_tools,
seed_prompt_templates) and `src/domains/agentic/seeds/seeder.py` (seed_features,
seed_tools) construct these models without ever setting tenant_id -- confirmed via
code review this now raises IntegrityError on commit. These are real, documented,
operator-facing tools ("docker exec sanskritisetu_backend python -m
src.domains.agentic.seeds.run_seeds") -- not wired into CI/deploy today (pre-launch,
unused), so this is not a live regression, but it needs a design decision (seed
per-tenant via a CLI arg, or reintroduce a documented platform-wide exception) before
anyone runs these scripts again.

seeder.py::seed_prompts already has a `tenant_id` fallback (hardcoded to 1) -- not
ideal but functional, out of this test's scope.

This test intentionally FAILS until each listed function explicitly sets tenant_id.
"""

import ast
import inspect

# (module import path, [function names that construct Feature/ToolDefinition/
# PromptTemplate without a tenant_id today])
_BROKEN_SEED_FUNCTIONS = {
    "src.domains.agentic.seeds.run_seeds": ["seed_features", "seed_tools", "seed_prompt_templates"],
    "src.domains.agentic.seeds.seeder": ["seed_features", "seed_tools"],
}


def _function_source_sets_tenant_id(module_path: str, func_name: str) -> bool:
    import importlib

    module = importlib.import_module(module_path)
    func = getattr(module, func_name)
    source = inspect.getsource(func)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        # Keyword argument: Feature(..., tenant_id=...)
        if isinstance(node, ast.keyword) and node.arg == "tenant_id":
            return True
        # Dict assignment: data["tenant_id"] = ...
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Subscript)
            and isinstance(node.targets[0].slice, ast.Constant)
            and node.targets[0].slice.value == "tenant_id"
        ):
            return True
    return False


def test_agentic_seed_scripts_set_tenant_id() -> None:
    still_broken = []
    for module_path, func_names in _BROKEN_SEED_FUNCTIONS.items():
        for func_name in func_names:
            if not _function_source_sets_tenant_id(module_path, func_name):
                still_broken.append(f"{module_path}.{func_name}")

    assert not still_broken, (
        f"SP-DATA-ARCH-1 backlog not yet resolved -- these seed functions construct "
        f"agentic-domain models without tenant_id, which now raises IntegrityError: "
        f"{still_broken}. Decide: seed per-tenant (CLI arg) or document a platform-wide "
        f"exception, then update this test."
    )
