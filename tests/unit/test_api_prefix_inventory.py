from pathlib import Path

import pytest

from src.core.config.api_prefix_inventory import (
    ApiPrefixInventory,
    ApiPrefixOccurrence,
    ApiPrefixScanner,
)


def test_api_prefix_inventory_happy_path_classifies_occurrences(tmp_path: Path) -> None:
    frontend_root = tmp_path / "frontend" / "src"
    (frontend_root / "lib").mkdir(parents=True)
    (frontend_root / "hooks" / "__tests__").mkdir(parents=True)
    (frontend_root / "components").mkdir(parents=True)

    (frontend_root / "lib" / "api.ts").write_text(
        "const path = '/api/v1/auth/me';\n",
        encoding="utf-8",
    )
    (frontend_root / "hooks" / "__tests__" / "useApi.test.ts").write_text(
        "expect(call).toBe('/api/v1/workflows');\n",
        encoding="utf-8",
    )
    (frontend_root / "components" / "Help.tsx").write_text(
        "// POST /api/v1/privacy/export for support docs\n"
        "const wsUrl = `ws://${window.location.host}/api/v1/ws/copilot/chat`;\n",
        encoding="utf-8",
    )

    inventory = ApiPrefixScanner().scan(frontend_root)

    assert isinstance(inventory, ApiPrefixInventory)
    assert inventory.total_occurrences == 4
    assert inventory.count_by_category["production"] == 1
    assert inventory.count_by_category["test"] == 1
    assert inventory.count_by_category["docs"] == 1
    assert inventory.count_by_category["websocket"] == 1


def test_api_prefix_inventory_unhappy_path_handles_no_matches(tmp_path: Path) -> None:
    frontend_root = tmp_path / "frontend" / "src"
    frontend_root.mkdir(parents=True)
    (frontend_root / "clean.ts").write_text("const path = '/health';\n", encoding="utf-8")

    inventory = ApiPrefixScanner().scan(frontend_root)

    assert inventory.total_occurrences == 0
    assert inventory.occurrences == []
    assert inventory.count_by_category == {}


def test_api_prefix_inventory_treats_markdown_code_block_as_docs(tmp_path: Path) -> None:
    frontend_root = tmp_path / "frontend" / "src"
    (frontend_root / "docs").mkdir(parents=True)
    (frontend_root / "docs" / "api.md").write_text(
        """
# API docs

```ts
const endpoint = '/api/v1/privacy/export';
```
""".strip()
        + "\n",
        encoding="utf-8",
    )

    inventory = ApiPrefixScanner().scan(frontend_root)

    assert inventory.total_occurrences == 1
    assert inventory.occurrences[0].category == "docs"


def test_api_prefix_inventory_skips_non_utf8_files_without_crashing(tmp_path: Path) -> None:
    frontend_root = tmp_path / "frontend" / "src"
    frontend_root.mkdir(parents=True)
    (frontend_root / "bad.ts").write_bytes(b"\xff\xfe\x00\x00")

    inventory = ApiPrefixScanner().scan(frontend_root)

    assert inventory.total_occurrences == 0


def test_api_prefix_inventory_does_not_mark_workflows_path_as_websocket(tmp_path: Path) -> None:
    frontend_root = tmp_path / "frontend" / "src"
    frontend_root.mkdir(parents=True)
    (frontend_root / "workflow.ts").write_text(
        "const path = '/api/v1/workflows';\n",
        encoding="utf-8",
    )

    inventory = ApiPrefixScanner().scan(frontend_root)

    assert inventory.total_occurrences == 1
    assert inventory.occurrences[0].category == "production"


def test_api_prefix_occurrence_snippet_is_preserved() -> None:
    occurrence = ApiPrefixOccurrence(
        path=Path("frontend/src/lib/api.ts"),
        line_number=12,
        category="production",
        snippet="const path = '/api/v1/auth/me';",
    )

    assert occurrence.snippet.endswith("/api/v1/auth/me';")
