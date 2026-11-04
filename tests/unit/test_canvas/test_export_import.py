"""
Tests for Canvas Export & Import.
"""

import json
from datetime import datetime
from uuid import uuid4

import pytest

from src.domains.canvas.export_import import (
    CanvasExporter,
    CanvasImporter,
    ExportFormat,
    ExportResult,
    ImportFormat,
    canvas_exporter,
    canvas_importer,
)


@pytest.fixture
def sample_canvas_data():
    """Create sample canvas data for testing."""
    return {
        "id": str(uuid4()),
        "name": "Test Canvas",
        "description": "A test canvas for export",
        "template": "blank",
        "version": 1,
        "is_public": False,
        "blocks": [
            {
                "id": str(uuid4()),
                "type": "text",
                "x": 100,
                "y": 50,
                "width": 300,
                "height": 100,
                "content": {
                    "title": "Welcome",
                    "text": "This is a test canvas",
                },
            },
            {
                "id": str(uuid4()),
                "type": "metric",
                "x": 100,
                "y": 200,
                "width": 200,
                "height": 120,
                "content": {
                    "label": "Revenue",
                    "value": "$50,000",
                    "change": "+10%",
                },
            },
        ],
        "connections": [],
    }


class TestExportResult:
    """Test ExportResult dataclass."""

    def test_result_creation(self):
        """Create export result."""
        result = ExportResult(
            format=ExportFormat.JSON,
            content='{"test": true}',
            filename="test.json",
            mime_type="application/json",
            size_bytes=100,
            generated_at=datetime.utcnow(),
        )

        assert result.format == ExportFormat.JSON
        assert result.filename == "test.json"
        assert result.size_bytes == 100


class TestCanvasExporterJson:
    """Test JSON export."""

    async def test_export_json(self, sample_canvas_data):
        """Export canvas to JSON."""
        exporter = CanvasExporter()

        result = await exporter.export_canvas(
            sample_canvas_data,
            ExportFormat.JSON,
        )

        assert result.format == ExportFormat.JSON
        assert result.mime_type == "application/json"
        assert result.filename.endswith(".json")

        # Content should be valid JSON
        data = json.loads(result.content)
        assert "version" in data
        assert "exported_at" in data
        assert data["canvas"]["name"] == "Test Canvas"

    async def test_export_json_pretty(self, sample_canvas_data):
        """Export JSON with pretty printing."""
        exporter = CanvasExporter()

        result_pretty = await exporter.export_canvas(
            sample_canvas_data,
            ExportFormat.JSON,
            {"pretty": True},
        )

        result_compact = await exporter.export_canvas(
            sample_canvas_data,
            ExportFormat.JSON,
            {"pretty": False},
        )

        # Pretty should be larger due to whitespace
        assert len(result_pretty.content) > len(result_compact.content)


class TestCanvasExporterMarkdown:
    """Test Markdown export."""

    async def test_export_markdown(self, sample_canvas_data):
        """Export canvas to Markdown."""
        exporter = CanvasExporter()

        result = await exporter.export_canvas(
            sample_canvas_data,
            ExportFormat.MARKDOWN,
        )

        assert result.format == ExportFormat.MARKDOWN
        assert result.mime_type == "text/markdown"
        assert result.filename.endswith(".md")

        # Content should be markdown
        content = result.content
        assert "# Test Canvas" in content
        assert "## Blocks" in content

    async def test_export_markdown_content(self, sample_canvas_data):
        """Markdown contains block content."""
        exporter = CanvasExporter()

        result = await exporter.export_canvas(
            sample_canvas_data,
            ExportFormat.MARKDOWN,
        )

        content = result.content

        # Should have text block content
        assert "Welcome" in content or "Text Block" in content

        # Should have metric
        assert "Revenue" in content or "$50,000" in content


class TestCanvasExporterHtml:
    """Test HTML export."""

    async def test_export_html(self, sample_canvas_data):
        """Export canvas to HTML."""
        exporter = CanvasExporter()

        result = await exporter.export_canvas(
            sample_canvas_data,
            ExportFormat.HTML,
        )

        assert result.format == ExportFormat.HTML
        assert result.mime_type == "text/html"
        assert result.filename.endswith(".html")

        # Should be valid HTML
        content = result.content
        assert "<!DOCTYPE html>" in content
        assert "<html" in content
        assert "Test Canvas" in content

    async def test_export_html_structure(self, sample_canvas_data):
        """HTML has proper structure."""
        exporter = CanvasExporter()

        result = await exporter.export_canvas(
            sample_canvas_data,
            ExportFormat.HTML,
        )

        content = result.content

        # Should have styles
        assert "<style>" in content

        # Should have blocks
        assert "block" in content.lower()

        # Should have canvas area
        assert "canvas-area" in content or "canvas_area" in content


class TestCanvasExporterSvg:
    """Test SVG export."""

    async def test_export_svg(self, sample_canvas_data):
        """Export canvas to SVG."""
        exporter = CanvasExporter()

        result = await exporter.export_canvas(
            sample_canvas_data,
            ExportFormat.SVG,
        )

        assert result.format == ExportFormat.SVG
        assert result.mime_type == "image/svg+xml"
        assert result.filename.endswith(".svg")

        # Should be valid SVG
        content = result.content
        assert "<svg" in content
        assert "</svg>" in content

    async def test_export_svg_blocks(self, sample_canvas_data):
        """SVG contains block representations."""
        exporter = CanvasExporter()

        result = await exporter.export_canvas(
            sample_canvas_data,
            ExportFormat.SVG,
        )

        content = result.content

        # Should have rectangles for blocks
        assert "<rect" in content

        # Should have text
        assert "<text" in content


class TestCanvasExporterPngPdf:
    """Test PNG and PDF exports (placeholders)."""

    async def test_export_png_placeholder(self, sample_canvas_data):
        """PNG export returns placeholder."""
        exporter = CanvasExporter()

        result = await exporter.export_canvas(
            sample_canvas_data,
            ExportFormat.PNG,
        )

        assert result.format == ExportFormat.PNG
        assert result.filename.endswith(".png")
        # Currently returns placeholder
        assert isinstance(result.content, bytes)

    async def test_export_pdf_placeholder(self, sample_canvas_data):
        """PDF export returns placeholder."""
        exporter = CanvasExporter()

        result = await exporter.export_canvas(
            sample_canvas_data,
            ExportFormat.PDF,
        )

        assert result.format == ExportFormat.PDF
        assert result.filename.endswith(".pdf")
        # Currently returns placeholder
        assert isinstance(result.content, bytes)


class TestCanvasExporterFilename:
    """Test filename generation."""

    async def test_filename_generation(self, sample_canvas_data):
        """Filename includes canvas name and timestamp."""
        exporter = CanvasExporter()

        result = await exporter.export_canvas(
            sample_canvas_data,
            ExportFormat.JSON,
        )

        assert "Test" in result.filename
        assert "Canvas" in result.filename
        assert result.filename.endswith(".json")
        # Should have timestamp (8 digits for YYYYMMDD)
        import re

        assert re.search(r"_\d{8}_\d{6}\.json$", result.filename)

    async def test_filename_special_chars(self):
        """Filename sanitizes special characters."""
        exporter = CanvasExporter()

        data = {
            "name": "Canvas: Test / Special <chars>!",
            "blocks": [],
            "connections": [],
        }

        result = await exporter.export_canvas(
            data,
            ExportFormat.JSON,
        )

        # Special chars should be replaced
        assert ":" not in result.filename
        assert "/" not in result.filename
        assert "<" not in result.filename
        assert ">" not in result.filename


class TestCanvasImporterJson:
    """Test JSON import."""

    async def test_import_json_wrapped(self):
        """Import JSON with canvas wrapper."""
        importer = CanvasImporter()

        content = json.dumps(
            {
                "version": "1.0",
                "canvas": {
                    "name": "Imported Canvas",
                    "blocks": [{"type": "text", "x": 0, "y": 0}],
                },
            }
        )

        result = await importer.import_canvas(content, ImportFormat.JSON)

        assert result["name"] == "Imported Canvas"
        assert len(result["blocks"]) == 1

    async def test_import_json_unwrapped(self):
        """Import JSON without wrapper."""
        importer = CanvasImporter()

        content = json.dumps(
            {
                "name": "Direct Import",
                "blocks": [],
                "connections": [],
            }
        )

        result = await importer.import_canvas(content, ImportFormat.JSON)

        assert result["name"] == "Direct Import"

    async def test_import_json_bytes(self):
        """Import JSON from bytes."""
        importer = CanvasImporter()

        content = json.dumps(
            {
                "name": "Bytes Import",
                "blocks": [],
            }
        ).encode("utf-8")

        result = await importer.import_canvas(content, ImportFormat.JSON)

        assert result["name"] == "Bytes Import"


class TestCanvasImporterMarkdown:
    """Test Markdown import."""

    async def test_import_markdown(self):
        """Import from Markdown."""
        importer = CanvasImporter()

        content = """
# My Canvas

## Blocks

### Section 1
Some content here.

### Section 2
More content.

- [ ] Task 1
- [ ] Task 2
"""

        result = await importer.import_canvas(content, ImportFormat.MARKDOWN)

        # Should have a name (either from title or default)
        assert "name" in result
        assert len(result["name"]) > 0
        # Should have created blocks
        assert len(result["blocks"]) > 0

    async def test_import_markdown_tasks(self):
        """Import tasks from Markdown."""
        importer = CanvasImporter()

        content = """
# Task List

- [ ] First task
- [ ] Second task
- [x] Completed task
"""

        result = await importer.import_canvas(content, ImportFormat.MARKDOWN)

        # Should have task blocks
        task_blocks = [b for b in result["blocks"] if b.get("type") == "task"]
        assert len(task_blocks) >= 2

    async def test_import_markdown_no_title(self):
        """Import Markdown without explicit title."""
        importer = CanvasImporter()

        content = "Some content without title"

        result = await importer.import_canvas(content, ImportFormat.MARKDOWN)

        assert "name" in result


class TestCanvasImporterErrors:
    """Test import error handling."""

    async def test_import_invalid_json(self):
        """Error on invalid JSON."""
        importer = CanvasImporter()

        with pytest.raises(json.JSONDecodeError):
            await importer.import_canvas("not valid json", ImportFormat.JSON)

    async def test_import_unsupported_format(self):
        """Error on unsupported format."""
        importer = CanvasImporter()

        with pytest.raises(ValueError, match="Unsupported"):
            # Cast to bypass type checking
            await importer.import_canvas("test", "xml")  # type: ignore


class TestGlobalInstances:
    """Test global exporter/importer instances."""

    def test_global_exporter(self):
        """Global exporter is available."""
        assert canvas_exporter is not None
        assert isinstance(canvas_exporter, CanvasExporter)

    def test_global_importer(self):
        """Global importer is available."""
        assert canvas_importer is not None
        assert isinstance(canvas_importer, CanvasImporter)
