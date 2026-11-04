"""
Endpoint Audit Script
Scans all integration tests for expected endpoints and compares with implemented endpoints
"""

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple


def extract_endpoints_from_tests(test_dir: Path) -> Dict[str, List[Tuple[str, str]]]:
    """Extract all endpoint calls from integration tests"""
    endpoint_pattern = re.compile(
        r'(?:async_client|authenticated_api)\.(get|post|put|delete|patch)\(["\']([^"\']+)'
    )

    endpoints_by_file = {}

    for test_file in test_dir.glob("test_sprint*.py"):
        endpoints = []
        content = test_file.read_text(encoding="utf-8")

        for match in endpoint_pattern.finditer(content):
            method = match.group(1).upper()
            path = match.group(2)
            endpoints.append((method, path))

        if endpoints:
            endpoints_by_file[test_file.name] = endpoints

    return endpoints_by_file


def extract_implemented_endpoints(api_dir: Path) -> Dict[str, List[Tuple[str, str]]]:
    """Extract all implemented endpoints from API files"""
    router_pattern = re.compile(r'router\s*=\s*APIRouter\(prefix=["\']([^"\']+)')
    endpoint_pattern = re.compile(r'@router\.(get|post|put|delete|patch)\(["\']([^"\']*)')

    endpoints_by_file = {}

    for api_file in api_dir.rglob("*_endpoints.py"):
        if api_file.name == "__init__.py":
            continue

        content = api_file.read_text(encoding="utf-8")

        # Find router prefix
        prefix_match = router_pattern.search(content)
        if not prefix_match:
            continue

        prefix = prefix_match.group(1)
        endpoints = []

        # Find all endpoints
        for match in endpoint_pattern.finditer(content):
            method = match.group(1).upper()
            path = match.group(2)

            # Construct full path
            if path.startswith("/"):
                full_path = prefix + path
            else:
                full_path = prefix + "/" + path if path else prefix

            # Normalize path
            full_path = full_path.replace("//", "/")
            endpoints.append((method, full_path))

        if endpoints:
            endpoints_by_file[api_file.name] = endpoints

    return endpoints_by_file


def normalize_endpoint(path: str) -> str:
    """Normalize endpoint path for comparison"""
    # Replace path parameters with {param}
    path = re.sub(r"\{[^}]+\}", "{id}", path)
    # Remove trailing slash
    path = path.rstrip("/")
    return path


def compare_endpoints(test_endpoints: Dict, impl_endpoints: Dict) -> Dict:
    """Compare test expectations with implementation"""
    # Flatten implemented endpoints
    implemented = set()
    for endpoints in impl_endpoints.values():
        for method, path in endpoints:
            normalized = normalize_endpoint(path)
            implemented.add(f"{method} {normalized}")

    # Check test endpoints
    missing_by_test = {}

    for test_file, endpoints in test_endpoints.items():
        missing = []
        for method, path in endpoints:
            normalized = normalize_endpoint(path)
            endpoint_sig = f"{method} {normalized}"

            if endpoint_sig not in implemented:
                missing.append((method, path))

        if missing:
            missing_by_test[test_file] = missing

    return missing_by_test


def generate_report(test_endpoints: Dict, impl_endpoints: Dict, missing_endpoints: Dict) -> str:
    """Generate comprehensive audit report"""
    lines = []
    lines.append("=" * 80)
    lines.append("ENDPOINT AUDIT REPORT")
    lines.append("=" * 80)
    lines.append("")

    # Summary
    total_test_endpoints = sum(len(eps) for eps in test_endpoints.values())
    total_impl_endpoints = sum(len(eps) for eps in impl_endpoints.values())
    total_missing = sum(len(eps) for eps in missing_endpoints.values())

    lines.append("[CHART] SUMMARY")
    lines.append(f"  - Total test endpoint calls: {total_test_endpoints}")
    lines.append(f"  - Total implemented endpoints: {total_impl_endpoints}")
    lines.append(f"  - Missing endpoints: {total_missing}")
    lines.append(f"  - Coverage: {100 - (total_missing / total_test_endpoints * 100):.1f}%")
    lines.append("")

    # Implemented endpoints by module
    lines.append("=" * 80)
    lines.append("[OK] IMPLEMENTED ENDPOINTS BY MODULE")
    lines.append("=" * 80)
    lines.append("")

    for api_file in sorted(impl_endpoints.keys()):
        endpoints = impl_endpoints[api_file]
        lines.append(f"[FOLDER] {api_file} ({len(endpoints)} endpoints)")

        # Group by prefix
        by_prefix = defaultdict(list)
        for method, path in endpoints:
            prefix = path.split("/")[1] if path.count("/") > 1 else path
            by_prefix[prefix].append(f"  {method:6} {path}")

        for prefix in sorted(by_prefix.keys()):
            for line in sorted(by_prefix[prefix]):
                lines.append(line)
        lines.append("")

    # Missing endpoints
    if missing_endpoints:
        lines.append("=" * 80)
        lines.append("[FAIL] MISSING ENDPOINTS (required by tests)")
        lines.append("=" * 80)
        lines.append("")

        # Group missing endpoints by category
        by_category = defaultdict(list)

        for test_file, endpoints in missing_endpoints.items():
            for method, path in endpoints:
                category = path.split("/")[2] if path.count("/") > 2 else "unknown"
                by_category[category].append((test_file, method, path))

        for category in sorted(by_category.keys()):
            lines.append(f"[FOLDER] /{category}/")
            for test_file, method, path in sorted(by_category[category]):
                lines.append(f"  {method:6} {path:50} (from {test_file})")
            lines.append("")

    # Missing endpoints by test file
    if missing_endpoints:
        lines.append("=" * 80)
        lines.append("[FAIL] MISSING ENDPOINTS BY TEST FILE")
        lines.append("=" * 80)
        lines.append("")

        for test_file in sorted(missing_endpoints.keys()):
            endpoints = missing_endpoints[test_file]
            lines.append(f"[U+0001F4C4] {test_file} ({len(endpoints)} missing)")
            for method, path in sorted(endpoints):
                lines.append(f"  {method:6} {path}")
            lines.append("")

    # Recommendations
    lines.append("=" * 80)
    lines.append("[IDEA] RECOMMENDATIONS")
    lines.append("=" * 80)
    lines.append("")

    if missing_endpoints:
        # Count by category
        category_counts = defaultdict(int)
        for endpoints in missing_endpoints.values():
            for _, path in endpoints:
                category = path.split("/")[2] if path.count("/") > 2 else "unknown"
                category_counts[category] += 1

        lines.append("Priority implementation (by missing count):")
        for category, count in sorted(category_counts.items(), key=lambda x: -x[1]):
            lines.append(f"  {count:2} endpoints needed for /{category}/")
        lines.append("")

        lines.append("Actions:")
        lines.append("  1. Implement missing critical endpoints (auth, tenants, users)")
        lines.append("  2. Add stub implementations for test-only endpoints")
        lines.append("  3. Mark tests as @pytest.mark.skip until endpoints available")
        lines.append("  4. Create endpoint implementation tickets in backlog")
    else:
        lines.append("  [OK] All test endpoints are implemented!")

    lines.append("")
    lines.append("=" * 80)

    return "\n".join(lines)


def main():
    base_path = Path(__file__).parent.parent
    test_dir = base_path / "tests" / "integration"
    api_dir = base_path / "src" / "core" / "api"

    print("[SEARCH] Scanning integration tests...")
    test_endpoints = extract_endpoints_from_tests(test_dir)

    print("[SEARCH] Scanning implemented endpoints...")
    impl_endpoints = extract_implemented_endpoints(api_dir)

    print("[SEARCH] Comparing...")
    missing_endpoints = compare_endpoints(test_endpoints, impl_endpoints)

    print("[NOTE] Generating report...")
    report = generate_report(test_endpoints, impl_endpoints, missing_endpoints)

    # Save report
    report_path = base_path / "ENDPOINT_AUDIT_REPORT.md"
    report_path.write_text(report, encoding="utf-8")

    print(f"\n[OK] Report saved to: {report_path}")
    print("\n" + report)

    return 0 if not missing_endpoints else 1


if __name__ == "__main__":
    exit(main())
