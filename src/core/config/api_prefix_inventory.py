from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ApiPrefixOccurrence:
    path: Path
    line_number: int
    category: str
    snippet: str


@dataclass(frozen=True)
class ApiPrefixInventory:
    occurrences: list[ApiPrefixOccurrence] = field(default_factory=list)

    @property
    def total_occurrences(self) -> int:
        return len(self.occurrences)

    @property
    def count_by_category(self) -> dict[str, int]:
        counts = Counter(occurrence.category for occurrence in self.occurrences)
        return dict(counts)


class ApiPrefixScanner:
    TARGET = "/api/v1"
    INCLUDE_SUFFIXES = {".ts", ".tsx", ".js", ".jsx", ".md"}

    def scan(self, root: str | Path) -> ApiPrefixInventory:
        root_path = Path(root)
        occurrences: list[ApiPrefixOccurrence] = []

        for file_path in root_path.rglob("*"):
            if not file_path.is_file() or file_path.suffix not in self.INCLUDE_SUFFIXES:
                continue

            try:
                lines = file_path.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                continue

            for line_number, line in enumerate(lines, start=1):
                if self.TARGET not in line:
                    continue
                occurrences.append(
                    ApiPrefixOccurrence(
                        path=file_path,
                        line_number=line_number,
                        category=self._categorize(file_path, line),
                        snippet=line.strip(),
                    )
                )

        return ApiPrefixInventory(occurrences=occurrences)

    def _categorize(self, file_path: Path, line: str) -> str:
        normalized_path = file_path.as_posix().lower()
        stripped = line.strip()

        if self._is_test_file(normalized_path):
            return "test"
        if file_path.suffix == ".md" or self._is_docs_line(stripped):
            return "docs"
        if self._is_websocket_line(stripped):
            return "websocket"
        return "production"

    @staticmethod
    def _is_test_file(normalized_path: str) -> bool:
        return (
            "/__tests__/" in normalized_path
            or "/tests/" in normalized_path
            or normalized_path.endswith(".test.ts")
            or normalized_path.endswith(".test.tsx")
            or normalized_path.endswith(".spec.ts")
            or normalized_path.endswith(".spec.tsx")
        )

    @staticmethod
    def _is_docs_line(stripped: str) -> bool:
        return stripped.startswith(("//", "/*", "*", "#"))

    @staticmethod
    def _is_websocket_line(stripped: str) -> bool:
        lowered = stripped.lower()
        return "ws://" in lowered or "wss://" in lowered or "/ws/" in lowered