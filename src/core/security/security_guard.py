import logging
from collections.abc import Callable
from typing import Any

from packaging.version import parse as parse_version

logger = logging.getLogger(__name__)


class SecurityGuard:
    def __init__(self, notify_admin_callback: Callable[..., Any] | None = None) -> None:  # TODO(TYPE): replace Any with concrete type
        self.notify_admin = notify_admin_callback or (
            lambda msg: logger.warning(f"Admin Notify: {msg}")
        )

    # TODO(SECURITY): replace stub with pip-audit integration or vulnerability API.
    # Official vulnerability gating is enforced via pip-audit in CI.
    _DEFAULT_CVE_DB: dict[str, list[dict[str, str]]] = {
        "requests": [
            {"id": "CVE-2023-32681", "vulnerable_versions": "<=2.30.0", "severity": "MEDIUM"}
        ],
        "urllib3": [
            {"id": "CVE-2023-45803", "vulnerable_versions": "<=2.0.6", "severity": "HIGH"}
        ],
        "pillow": [
            {"id": "CVE-2023-44271", "vulnerable_versions": "<=10.0.0", "severity": "HIGH"}
        ],
        "pyyaml": [
            {"id": "CVE-2020-14343", "vulnerable_versions": "<=5.3.1", "severity": "CRITICAL"}
        ],
        "cryptography": [
            {"id": "CVE-2023-49083", "vulnerable_versions": "<=41.0.5", "severity": "HIGH"}
        ],
    }

    async def _fetch_cve_db(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Fetches the CVE database for vulnerability checking.
        Returns curated vulnerability data with known high-impact advisory signatures.
        """
        return {k: list(v) for k, v in self._DEFAULT_CVE_DB.items()}

    async def scan_skills(self, skills: list[dict[str, Any]]) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """
        Scans a list of skills for vulnerable dependencies and disables them if found.
        """
        try:
            cve_db = await self._fetch_cve_db()
        except Exception as e:
            logger.error(f"Failed to fetch CVE DB: {e}")
            for skill in skills:
                skill["warnings"] = f"Warning: CVE scan skipped due to DB error: {e}"
            return skills

        updated_skills: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for skill in skills:
            updated_skill = dict(skill)
            updated_skill["audit_notice"] = (
                "Notice: In-process CVE scan is a development stub. "
                "Official vulnerability gating is enforced via pip-audit in CI."
            )
            dependencies = updated_skill.get("dependencies", {})
            is_vulnerable = False
            vulnerability_reason = ""

            for pkg, version in dependencies.items():
                if pkg in cve_db:
                    for vuln in cve_db[pkg]:
                        # Simple naive version check for the demonstration.
                        # Real implementation uses python-packaging or packaging.specifiers
                        vuln_ver_spec = vuln["vulnerable_versions"]
                        if vuln_ver_spec.startswith("<="):
                            max_ver = vuln_ver_spec[2:]
                            if parse_version(version) <= parse_version(max_ver):
                                is_vulnerable = True
                                vulnerability_reason = (
                                    f"Dependency {pkg} {version} is vulnerable to {vuln['id']}"
                                )
                                break

            if is_vulnerable:
                updated_skill["status"] = "Disabled"
                updated_skill["reason"] = vulnerability_reason
                self.notify_admin(f"BadSkill disabled: {vulnerability_reason}")

            updated_skills.append(updated_skill)

        return updated_skills
