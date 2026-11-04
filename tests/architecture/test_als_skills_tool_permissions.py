"""Architecture test: ALS skills with tool execution must have a permission profile.

Background (AUDIT-008, 2026-07-30):
- All 135 skill manifests carried a system-prompt stopgap ("without attempting
  a TOOL_CALL") because 0 of the skills had a profile in
  config/tool_permissions.yml -- every tool call would be default-deny'd.
- The pilot skill (skillsgaptraining) is the first to get a real profile, so
  its stopgap is removed. The other 134 skills keep the stopgap until they get
  their own profile in a later sprint.

This test keeps the gap structurally visible (prevention measure from the
ADR-036 audit-to-fix plan): it enforces the INVARIANT, not the current state.

Rules:
1. Stopgap removed  =>  profile required. A skill whose manifest no longer
   forbids TOOL_CALL can attempt tool execution; without a broker-side
   profile every such attempt is default-deny'd at runtime (ADR-015).
2. Profile present  =>  stopgap forbidden + manifest must exist. A profile
   for a skill whose prompt still forbids TOOL_CALL is inconsistent (the
   skill can never use the granted permissions), and a profile without a
   manifest points at a nonexistent skill.
3. Least privilege: profile.allowed_tools must be a subset of the manifest's
   declared allowed_tools -- the broker may never allow more than the skill
   itself declares.

The "copilot" and "workflow_engine" profiles are out of scope: they are not ALS skills (no manifest). The
latter is the identity of a workflow step (ADR-036 OP-13); its tools are least-privilege by hand in
`config/tool_permissions.yml` and covered by `tests/unit/workflow/test_workflowstappen_via_de_deuren.py`.
"""

from pathlib import Path

import yaml

SKILL_MANIFESTS_DIR = Path("src/core/als/agents/skills/manifests")
TOOL_PERMISSIONS_YML = Path("config/tool_permissions.yml")
# Marker sentence of the Gate 2/3 stopgap (commit 33b4dd8c).
STOPGAP_MARKER = "without attempting a TOOL_CALL"
NON_SKILL_PROFILES = {"copilot", "workflow_engine"}


def _registered_profiles() -> dict[str, set[str]]:
    """Return {agent_id: set(allowed_tools)} from tool_permissions.yml."""
    if not TOOL_PERMISSIONS_YML.exists():
        return {}
    with TOOL_PERMISSIONS_YML.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    profiles = (data or {}).get("agent_profiles", []) or []
    return {
        p["agent_id"]: set(p.get("allowed_tools") or [])
        for p in profiles
        if isinstance(p, dict) and "agent_id" in p
    }


def _load_manifests() -> dict[str, dict[str, object]]:
    """Return {skill_id: manifest-dict} for all ALS skill manifests."""
    manifests: dict[str, dict[str, object]] = {}
    for path in sorted(SKILL_MANIFESTS_DIR.glob("*.yml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "skill_id" in data:
            manifests[str(data["skill_id"])] = data
    return manifests


def test_permission_config_paths_exist() -> None:
    """Vangnet: een verhuisd configbestand of manifestmap mag de twee tests hieronder
    niet stilzwijgend vacuum maken.

    `_registered_profiles()` geeft stil `{}` terug als `TOOL_PERMISSIONS_YML` ontbreekt,
    en `_load_manifests()` doet hetzelfde als `SKILL_MANIFESTS_DIR` ontbreekt (`Path.glob`
    op een niet-bestaande map itereert leeg, zonder fout). Een lege verzameling laat
    `test_skill_profiles_are_consistent_with_manifests` trivially slagen: de for-lus over
    `registered.items()` doet dan niets, ook als er echte least-privilege-schendingen
    bestaan die alleen niet meer gelezen worden.
    """
    missing = [str(p) for p in (SKILL_MANIFESTS_DIR, TOOL_PERMISSIONS_YML) if not p.exists()]
    assert not missing, (
        f"Deze paden bestaan niet: {missing}. Verplaatst of hernoemd? Beide tests hieronder "
        "lezen dan een lege verzameling en controleren NIETS meer."
    )


def test_skills_without_stopgap_have_permission_profile() -> None:
    """Rule 1: stopgap removed => profile required (ADR-015 default-deny)."""
    registered = _registered_profiles()
    violations: list[str] = []

    for skill_id, manifest in _load_manifests().items():
        prompt = str(manifest.get("system_prompt") or "")
        if STOPGAP_MARKER in prompt:
            continue  # stopgap present: skill cannot attempt TOOL_CALL -- safe
        if skill_id not in registered:
            violations.append(
                f"{skill_id}: manifest-stopgap verwijderd maar geen profiel in "
                f"{TOOL_PERMISSIONS_YML} -- elke TOOL_CALL wordt default-deny'd"
            )

    assert not violations, (
        "ALS-skills zonder system-prompt-stopgap MOETEN een tool-permissieprofiel "
        "hebben (AUDIT-008 preventie-regel):\n"
        + "\n".join(f"  - {v}" for v in violations)
    )


def test_skill_profiles_are_consistent_with_manifests() -> None:
    """Rules 2+3: profile => manifest exists, no stopgap, least privilege."""
    registered = _registered_profiles()
    manifests = _load_manifests()
    violations: list[str] = []

    for agent_id, profile_tools in registered.items():
        if agent_id in NON_SKILL_PROFILES:
            continue
        manifest = manifests.get(agent_id)
        if manifest is None:
            violations.append(
                f"{agent_id}: heeft een profiel maar geen skill-manifest in "
                f"{SKILL_MANIFESTS_DIR}"
            )
            continue
        prompt = str(manifest.get("system_prompt") or "")
        if STOPGAP_MARKER in prompt:
            violations.append(
                f"{agent_id}: heeft een profiel maar de manifest-stopgap staat nog -- "
                "de skill kan de verleende tools nooit gebruiken"
            )
        raw_manifest_tools = manifest.get("allowed_tools")
        manifest_tools = set(raw_manifest_tools) if isinstance(raw_manifest_tools, list) else set()
        excess = profile_tools - manifest_tools
        if excess:
            violations.append(
                f"{agent_id}: profiel staat meer toe dan het manifest declareert "
                f"(least-privilege schending): {sorted(excess)}"
            )

    assert not violations, (
        "Tool-permissieprofielen voor ALS-skills moeten consistent zijn met hun "
        "manifest (AUDIT-008 preventie-regel):\n"
        + "\n".join(f"  - {v}" for v in violations)
    )
