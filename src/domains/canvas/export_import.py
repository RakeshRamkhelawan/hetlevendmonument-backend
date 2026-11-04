"""
Canvas Export & Import System

Provides functionality to export canvases in various formats:
- JSON (native format)
- PDF (for sharing/printing)
- PNG/SVG (images)
- Markdown (documentation)
- HTML (interactive export)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from io import BytesIO
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from loguru import logger
from pydantic import BaseModel


class ExportFormat(str, Enum):
    """Available export formats."""

    JSON = "json"  # Native format with full data
    PDF = "pdf"  # PDF document
    PNG = "png"  # PNG image
    SVG = "svg"  # SVG vector image
    MARKDOWN = "markdown"  # Markdown documentation
    HTML = "html"  # Interactive HTML


class ImportFormat(str, Enum):
    """Available import formats."""

    JSON = "json"
    MARKDOWN = "markdown"


@dataclass
class ExportResult:
    """Result of an export operation."""

    format: ExportFormat
    content: str | bytes
    filename: str
    mime_type: str
    size_bytes: int
    generated_at: datetime


class CanvasExporter:
    """
    Export canvases to various formats.

    Handles the conversion of canvas data to external formats
    for sharing, backup, or documentation purposes.
    """

    MIME_TYPES = {
        ExportFormat.JSON: "application/json",
        ExportFormat.PDF: "application/pdf",
        ExportFormat.PNG: "image/png",
        ExportFormat.SVG: "image/svg+xml",
        ExportFormat.MARKDOWN: "text/markdown",
        ExportFormat.HTML: "text/html",
    }

    EXTENSIONS = {
        ExportFormat.JSON: ".json",
        ExportFormat.PDF: ".pdf",
        ExportFormat.PNG: ".png",
        ExportFormat.SVG: ".svg",
        ExportFormat.MARKDOWN: ".md",
        ExportFormat.HTML: ".html",
    }

    async def export_canvas(
        self,
        canvas_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        format: ExportFormat,
        options: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> ExportResult:
        """
        Export canvas to specified format.

        Args:
            canvas_data: Full canvas data including blocks and connections
            format: Target export format
            options: Format-specific options

        Returns:
            ExportResult with the exported content
        """
        options = options or {}

        content: str | bytes
        if format == ExportFormat.JSON:
            content = await self._export_json(canvas_data, options)
        elif format == ExportFormat.MARKDOWN:
            content = await self._export_markdown(canvas_data, options)
        elif format == ExportFormat.HTML:
            content = await self._export_html(canvas_data, options)
        elif format == ExportFormat.SVG:
            content = await self._export_svg(canvas_data, options)
        elif format == ExportFormat.PNG:
            content = await self._export_png(canvas_data, options)
        elif format == ExportFormat.PDF:
            content = await self._export_pdf(canvas_data, options)
        else:
            raise ValueError(f"Unsupported export format: {format}")

        # Calculate size
        if isinstance(content, str):
            size_bytes = len(content.encode("utf-8"))
        else:
            size_bytes = len(content)

        # Generate filename
        canvas_name = canvas_data.get("name", "canvas")
        safe_name = "".join(c if c.isalnum() or c in (" ", "-", "_") else "_" for c in canvas_name)
        filename = f"{safe_name}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}{self.EXTENSIONS[format]}"

        logger.info(f"Exported canvas '{canvas_name}' to {format.value} ({size_bytes} bytes)")

        return ExportResult(
            format=format,
            content=content,
            filename=filename,
            mime_type=self.MIME_TYPES[format],
            size_bytes=size_bytes,
            generated_at=datetime.now(timezone.utc),
        )

    async def _export_json(
        self,
        canvas_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        options: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> str:
        """Export to JSON format."""
        export_data = {
            "version": "1.0",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "canvas": canvas_data,
        }

        # Add pretty printing option
        indent = 2 if options.get("pretty", True) else None
        return json.dumps(export_data, indent=indent, default=str)

    async def _export_markdown(
        self,
        canvas_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        options: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> str:
        """Export to Markdown format."""
        lines: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Title
        canvas_name = canvas_data.get("name", "Untitled Canvas")
        lines.append(f"# {canvas_name}")
        lines.append("")

        # Metadata
        lines.append(f"*Exported: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC*")
        lines.append("")

        # Description if present
        if canvas_data.get("description"):
            lines.append(canvas_data["description"])
            lines.append("")

        # Blocks
        lines.append("## Blocks")
        lines.append("")

        blocks = canvas_data.get("blocks", [])
        for block in blocks:
            block_type = block.get("type", "unknown")
            content = block.get("content", {})

            if block_type == "text":
                title = content.get("title", "")
                text = content.get("text", "")
                if title:
                    lines.append(f"### {title}")
                if text:
                    lines.append(text)
                lines.append("")

            elif block_type == "metric":
                label = content.get("label", "")
                value = content.get("value", "")
                change = content.get("change", "")
                lines.append(f"**{label}**: {value} ({change})")
                lines.append("")

            elif block_type in ("task", "agent_task"):
                title = content.get("title", "Task")
                lines.append(f"- [ ] {title}")
                lines.append("")

            else:
                # Generic block representation
                lines.append(f"### {block_type.title()} Block")
                if content:
                    lines.append("```json")
                    lines.append(json.dumps(content, indent=2))
                    lines.append("```")
                lines.append("")

        # Connections
        connections = canvas_data.get("connections", [])
        if connections:
            lines.append("## Connections")
            lines.append("")
            for conn in connections:
                source = conn.get("source_block_id", "?")
                target = conn.get("target_block_id", "?")
                label = conn.get("label", "connects to")
                lines.append(f"- `{source}` {label} `{target}`")
            lines.append("")

        return "\n".join(lines)

    async def _export_html(
        self,
        canvas_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        options: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> str:
        """Export to interactive HTML format."""
        canvas_name = canvas_data.get("name", "Untitled Canvas")
        blocks = canvas_data.get("blocks", [])
        connections = canvas_data.get("connections", [])

        # Calculate canvas bounds
        max_x = max((b.get("x", 0) + b.get("width", 200) for b in blocks), default=800)
        max_y = max((b.get("y", 0) + b.get("height", 100) for b in blocks), default=600)

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{canvas_name}</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f5f5f5;
            padding: 20px;
        }}
        .canvas-container {{
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            padding: 20px;
            overflow: auto;
        }}
        .canvas-title {{
            font-size: 24px;
            font-weight: 600;
            margin-bottom: 20px;
            color: #333;
        }}
        .canvas-area {{
            position: relative;
            width: {max_x + 100}px;
            height: {max_y + 100}px;
            background: #fafafa;
            border: 1px solid #e0e0e0;
            border-radius: 4px;
        }}
        .block {{
            position: absolute;
            background: white;
            border: 1px solid #ddd;
            border-radius: 6px;
            padding: 12px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            overflow: hidden;
        }}
        .block-title {{
            font-weight: 600;
            font-size: 14px;
            margin-bottom: 8px;
            color: #333;
        }}
        .block-content {{
            font-size: 13px;
            color: #666;
            line-height: 1.4;
        }}
        .block-metric {{
            text-align: center;
        }}
        .metric-value {{
            font-size: 24px;
            font-weight: 700;
            color: #2563eb;
        }}
        .metric-label {{
            font-size: 12px;
            color: #666;
            text-transform: uppercase;
        }}
        .connection {{
            position: absolute;
            pointer-events: none;
        }}
        .footer {{
            margin-top: 20px;
            font-size: 12px;
            color: #999;
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="canvas-container">
        <h1 class="canvas-title">{canvas_name}</h1>
        <div class="canvas-area">
"""

        # Add blocks
        for block in blocks:
            block_type = block.get("type", "unknown")
            x = block.get("x", 0)
            y = block.get("y", 0)
            width = block.get("width", 200)
            height = block.get("height", 100)
            content = block.get("content", {})

            style = f"left: {x}px; top: {y}px; width: {width}px; height: {height}px;"

            if block_type == "metric":
                label = content.get("label", "")
                value = content.get("value", "")
                html += f"""
            <div class="block block-metric" style="{style}">
                <div class="metric-value">{value}</div>
                <div class="metric-label">{label}</div>
            </div>"""
            else:
                title = content.get("title", block_type.title())
                text = content.get("text", "")[:100]  # Truncate
                html += f"""
            <div class="block" style="{style}">
                <div class="block-title">{title}</div>
                <div class="block-content">{text}</div>
            </div>"""

        html += f"""
        </div>
        <div class="footer">
            Exported from SanskritiSetu Canvas on {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")} UTC
        </div>
    </div>
</body>
</html>"""

        return html

    async def _export_svg(
        self,
        canvas_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        options: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> str:
        """Export to SVG format."""
        blocks = canvas_data.get("blocks", [])
        connections = canvas_data.get("connections", [])

        # Calculate bounds
        max_x = max((b.get("x", 0) + b.get("width", 200) for b in blocks), default=800)
        max_y = max((b.get("y", 0) + b.get("height", 100) for b in blocks), default=600)

        svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {max_x + 50} {max_y + 50}" width="{max_x + 50}" height="{max_y + 50}">
  <defs>
    <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="1" dy="1" stdDeviation="2" flood-opacity="0.2"/>
    </filter>
  </defs>
  <rect width="100%" height="100%" fill="#fafafa"/>
"""

        # Draw connections
        for conn in connections:
            # Simplified: just draw lines (in production, calculate proper paths)
            svg += '  <line x1="0" y1="0" x2="100" y2="100" stroke="#999" stroke-width="2"/>\n'

        # Draw blocks
        for block in blocks:
            x = block.get("x", 0)
            y = block.get("y", 0)
            width = block.get("width", 200)
            height = block.get("height", 100)
            content = block.get("content", {})
            title = content.get("title", block.get("type", "Block"))

            # Block rectangle
            svg += f'  <rect x="{x}" y="{y}" width="{width}" height="{height}" '
            svg += 'fill="white" stroke="#ddd" stroke-width="1" rx="4" filter="url(#shadow)"/>\n'

            # Block title
            svg += f'  <text x="{x + 10}" y="{y + 20}" font-family="sans-serif" '
            svg += f'font-size="14" font-weight="bold" fill="#333">{title}</text>\n'

        svg += "</svg>"
        return svg

    async def _export_png(
        self,
        canvas_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        options: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> bytes:
        """Export to PNG format."""
        # Placeholder - would use PIL or similar in production
        logger.warning("PNG export not fully implemented - returning placeholder")
        return b"PNG placeholder"

    async def _export_pdf(
        self,
        canvas_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        options: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> bytes:
        """Export to PDF format."""
        # Placeholder - would use reportlab or similar in production
        logger.warning("PDF export not fully implemented - returning placeholder")
        return b"PDF placeholder"


class CanvasImporter:
    """
    Import canvases from various formats.

    Handles validation and conversion of external formats to
    native canvas data.
    """

    async def import_canvas(
        self,
        content: str | bytes,
        format: ImportFormat,
        options: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Import canvas from specified format.

        Args:
            content: The content to import
            format: Source format
            options: Format-specific options

        Returns:
            Canvas data dictionary
        """
        options = options or {}

        if format == ImportFormat.JSON:
            return await self._import_json(content, options)
        elif format == ImportFormat.MARKDOWN:
            return await self._import_markdown(content, options)
        else:
            raise ValueError(f"Unsupported import format: {format}")

    async def _import_json(
        self,
        content: str | bytes,
        options: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Import from JSON format."""
        if isinstance(content, bytes):
            content = content.decode("utf-8")

        data = json.loads(content)

        # Handle both wrapped and unwrapped formats
        if "canvas" in data:
            return data["canvas"]  # type: ignore[no-any-return]

        return data  # type: ignore[no-any-return]

    async def _import_markdown(
        self,
        content: str | bytes,
        options: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Import from Markdown format."""
        if isinstance(content, bytes):
            content = content.decode("utf-8")

        lines = content.split("\n")

        canvas_name = "Imported Canvas"
        blocks: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        y_pos = 50

        for line in lines:
            line = line.strip()

            if line.startswith("# ") and not canvas_name:
                canvas_name = line[2:].strip()

            elif line.startswith("### "):
                # Block title
                title = line[4:].strip()
                blocks.append(
                    {
                        "id": str(__import__("uuid").uuid4()),
                        "type": "text",
                        "x": 50,
                        "y": y_pos,
                        "width": 400,
                        "height": 80,
                        "content": {"title": title, "text": ""},
                    }
                )
                y_pos += 100

            elif line.startswith("- [ ]"):
                # Task
                task_text = line[5:].strip()
                blocks.append(
                    {
                        "id": str(__import__("uuid").uuid4()),
                        "type": "task",
                        "x": 50,
                        "y": y_pos,
                        "width": 400,
                        "height": 60,
                        "content": {"title": task_text, "completed": False},
                    }
                )
                y_pos += 80

        return {
            "name": canvas_name,
            "blocks": blocks,
            "connections": [],
        }


# Global instances
canvas_exporter = CanvasExporter()
canvas_importer = CanvasImporter()
