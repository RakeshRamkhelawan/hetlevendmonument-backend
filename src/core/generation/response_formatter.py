"""
Response Formatter - Advanced response formatting and structuring system
ASCII-only compliance enforced
"""

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from collections.abc import Callable
from typing import Any, Protocol, cast


class _CacheLayer(Protocol):
    """Structural interface for cache backends used by ResponseFormatter."""

    def get(self, key: str) -> object | None: ...
    def set(self, key: str, value: object, ttl: int = 0) -> None: ...


logger = logging.getLogger(__name__)


class FormatType(Enum):
    """Supported response format types."""

    JSON = "json"
    XML = "xml"
    YAML = "yaml"
    HTML = "html"
    MARKDOWN = "markdown"
    PLAIN_TEXT = "plain_text"
    STRUCTURED = "structured"
    CUSTOM = "custom"


@dataclass
class FormattingOptions:
    """Configuration options for response formatting."""

    indent_size: int = 2
    include_metadata: bool = True
    include_timestamps: bool = True
    include_source: bool = False
    max_line_length: int = 80
    escape_html: bool = True
    pretty_print: bool = True
    custom_headers: dict[str, str] = field(default_factory=dict)
    custom_footers: dict[str, str] = field(default_factory=dict)
    template_variables: dict[str, object] = field(default_factory=dict)


@dataclass
class FormatRule:
    """Formatting rule for specific content types."""

    pattern: str
    replacement: str
    flags: int = 0
    apply_order: int = 0


@dataclass
class FormattingResult:
    """Result of response formatting operation."""

    formatted_content: str
    format_type: FormatType
    metadata: dict[str, object]
    applied_rules: list[str]
    processing_time: float
    error_message: str | None = None
    warnings: list[str] = field(default_factory=list)


class ResponseFormatter:
    """
    Advanced response formatting system for M-MDP architecture.
    Handles multiple output formats with customizable styling and templating.
    """

    def __init__(self, cache_layer: _CacheLayer | None = None) -> None:
        """Initialize the response formatter."""
        self.cache_layer = cache_layer
        self.format_rules: dict[FormatType, list[FormatRule]] = {}
        self.custom_formatters: dict[
            str, Callable[..., Any]
        ] = {}  # TODO(TYPE): replace Any with concrete type
        self.template_cache: dict[str, str] = {}
        self.stats = {
            "formats_processed": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "errors": 0,
            "average_processing_time": 0.0,
        }

        # Initialize default formatting rules
        self._initialize_default_rules()

        logger.info("ResponseFormatter initialized with cache support")

    def _initialize_default_rules(self) -> None:
        """Initialize default formatting rules for each format type."""

        # JSON formatting rules
        self.format_rules[FormatType.JSON] = [
            FormatRule(r"\s+", " ", 0, 1),  # Normalize whitespace
            FormatRule(r",\s*}", "}", 0, 2),  # Remove trailing commas
            FormatRule(r",\s*]", "]", 0, 3),  # Remove trailing commas in arrays
        ]

        # HTML formatting rules
        self.format_rules[FormatType.HTML] = [
            FormatRule(r"&", "&amp;", 0, 1),
            FormatRule(r"<", "&lt;", 0, 2),
            FormatRule(r">", "&gt;", 0, 3),
            FormatRule(r'"', "&quot;", 0, 4),
            FormatRule(r"'", "&#x27;", 0, 5),
        ]

        # Markdown formatting rules
        self.format_rules[FormatType.MARKDOWN] = [
            FormatRule(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", 0, 1),
            FormatRule(r"\*([^*]+)\*", r"<em>\1</em>", 0, 2),
            FormatRule(r"`([^`]+)`", r"<code>\1</code>", 0, 3),
        ]

        # Plain text formatting rules
        self.format_rules[FormatType.PLAIN_TEXT] = [
            FormatRule(r"<[^>]+>", "", 0, 1),  # Remove HTML tags
            FormatRule(r"\s+", " ", 0, 2),  # Normalize whitespace
            FormatRule(r"^\s+|\s+$", "", 0, 3),  # Trim whitespace
        ]

    def format_response(
        self,
        content: Any,  # TODO(TYPE): replace Any with concrete type
        format_type: FormatType,
        options: FormattingOptions | None = None,
    ) -> FormattingResult:
        """
        Format content according to specified format type and options.

        Args:
            content: Content to format
            format_type: Target format type
            options: Formatting options

        Returns:
            FormattingResult with formatted content and metadata
        """
        start_time = datetime.now(timezone.utc)

        try:
            if options is None:
                options = FormattingOptions()

            # Check cache first
            cache_key = self._generate_cache_key(content, format_type, options)
            if self.cache_layer:
                cached_result_raw: Any = self.cache_layer.get(  # TODO(TYPE): replace Any with concrete type
                    f"format_{cache_key}"
                )  # TODO(TYPE): replace Any with concrete type
                if cached_result_raw:
                    self.stats["cache_hits"] += 1
                    logger.debug(f"Cache hit for format operation: {cache_key}")
                    return cast(FormattingResult, cached_result_raw)

                self.stats["cache_misses"] += 1

            # Format content based on type
            formatted_content = self._format_content(content, format_type, options)

            # Apply formatting rules
            applied_rules = self._apply_formatting_rules(formatted_content, format_type)
            formatted_content = applied_rules["content"]

            # Add metadata if requested
            metadata: dict[str, object] = {}
            if options.include_metadata:
                metadata = self._generate_metadata(content, format_type, options)

            # Calculate processing time
            processing_time = (datetime.now(timezone.utc) - start_time).total_seconds()

            # Create result
            result = FormattingResult(
                formatted_content=formatted_content,
                format_type=format_type,
                metadata=metadata,
                applied_rules=applied_rules["rules"],
                processing_time=processing_time,
            )

            # Cache result
            if self.cache_layer:
                self.cache_layer.set(f"format_{cache_key}", result, ttl=3600)

            # Update statistics
            self._update_stats(processing_time)

            logger.debug(f"Formatted response for {format_type.value} in {processing_time:.3f}s")
            return result

        except Exception as e:
            self.stats["errors"] += 1
            error_msg = f"Formatting error: {str(e)}"
            logger.error(error_msg)

            return FormattingResult(
                formatted_content=str(content),
                format_type=format_type,
                metadata={},
                applied_rules=[],
                processing_time=(datetime.now(timezone.utc) - start_time).total_seconds(),
                error_message=error_msg,
            )

    def _format_content(
        self,
        content: Any,  # TODO(TYPE): replace Any with concrete type
        format_type: FormatType,
        options: FormattingOptions,  # TODO(TYPE): replace Any with concrete type
    ) -> str:
        """Format content according to the specified format type."""

        if format_type == FormatType.JSON:
            return self._format_json(content, options)
        if format_type == FormatType.XML:
            return self._format_xml(content, options)
        if format_type == FormatType.YAML:
            return self._format_yaml(content, options)
        if format_type == FormatType.HTML:
            return self._format_html(content, options)
        if format_type == FormatType.MARKDOWN:
            return self._format_markdown(content, options)
        if format_type == FormatType.PLAIN_TEXT:
            return self._format_plain_text(content, options)
        if format_type == FormatType.STRUCTURED:
            return self._format_structured(content, options)
        if format_type == FormatType.CUSTOM:
            return self._format_custom(content, options)

        return str(content)

    def _format_json(
        self, content: Any, options: FormattingOptions  # TODO(TYPE): replace Any with concrete type
    ) -> str:  # TODO(TYPE): replace Any with concrete type
        """Format content as JSON."""
        try:
            if options.pretty_print:
                return json.dumps(content, indent=options.indent_size, ensure_ascii=True)
            else:
                return json.dumps(content, ensure_ascii=True)
        except (TypeError, ValueError) as e:
            logger.warning(f"JSON formatting failed: {e}")
            return json.dumps({"content": str(content), "error": str(e)}, ensure_ascii=True)

    def _format_xml(
        self, content: Any, _options: FormattingOptions  # TODO(TYPE): replace Any with concrete type
    ) -> str:  # TODO(TYPE): replace Any with concrete type
        """Format content as XML."""

        def dict_to_xml(
            data: Any, root_name: str = "response"  # TODO(TYPE): replace Any with concrete type
        ) -> str:  # TODO(TYPE): replace Any with concrete type
            if isinstance(data, dict):
                xml_parts = [f"<{root_name}>"]
                for key, value in data.items():
                    # Ensure ASCII-only key names
                    safe_key = re.sub(r"[^a-zA-Z0-9_]", "_", str(key))
                    xml_parts.append(dict_to_xml(value, safe_key))
                xml_parts.append(f"</{root_name}>")
                return "\n".join(xml_parts)
            elif isinstance(data, list):
                xml_parts = [f"<{root_name}>"]
                for i, item in enumerate(data):
                    xml_parts.append(dict_to_xml(item, f"item_{i}"))
                xml_parts.append(f"</{root_name}>")
                return "\n".join(xml_parts)
            else:
                # Escape XML special characters
                escaped_content = (
                    str(data).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                )
                return f"<{root_name}>{escaped_content}</{root_name}>"

        if isinstance(content, (dict, list)):
            return dict_to_xml(content)
        else:
            return dict_to_xml({"content": content})

    def _format_yaml(
        self, content: Any, options: FormattingOptions  # TODO(TYPE): replace Any with concrete type
    ) -> str:  # TODO(TYPE): replace Any with concrete type
        """Format content as YAML (simplified implementation)."""

        def to_yaml(
            data: Any, indent: int = 0  # TODO(TYPE): replace Any with concrete type
        ) -> str:  # TODO(TYPE): replace Any with concrete type
            spaces = " " * indent
            if isinstance(data, dict):
                yaml_lines: list[str] = []
                for key, value in data.items():
                    if isinstance(value, (dict, list)):
                        yaml_lines.append(f"{spaces}{key}:")
                        yaml_lines.append(to_yaml(value, indent + options.indent_size))
                    else:
                        yaml_lines.append(f"{spaces}{key}: {value}")
                return "\n".join(yaml_lines)
            elif isinstance(data, list):
                list_lines: list[str] = []
                for item in data:
                    if isinstance(item, (dict, list)):
                        list_lines.append(f"{spaces}-")
                        list_lines.append(to_yaml(item, indent + options.indent_size))
                    else:
                        list_lines.append(f"{spaces}- {item}")
                return "\n".join(list_lines)
            else:
                return f"{spaces}{data}"

        if isinstance(content, (dict, list)):
            return to_yaml(content)
        else:
            return to_yaml({"content": content})

    def _format_html(
        self, content: Any, options: FormattingOptions  # TODO(TYPE): replace Any with concrete type
    ) -> str:  # TODO(TYPE): replace Any with concrete type
        """Format content as HTML."""
        html_parts: list[str] = []
        # Add custom headers
        for header_name, header_content in options.custom_headers.items():
            html_parts.append(f"<!-- {header_name}: {header_content} -->")

        html_parts.append("<html>")
        html_parts.append("<head><title>Response</title></head>")
        html_parts.append("<body>")

        if isinstance(content, dict):
            html_parts.append("<dl>")
            for key, value in content.items():
                html_parts.append(f"<dt>{self._escape_html(str(key))}</dt>")
                html_parts.append(f"<dd>{self._escape_html(str(value))}</dd>")
            html_parts.append("</dl>")
        elif isinstance(content, list):
            html_parts.append("<ul>")
            for item in content:
                html_parts.append(f"<li>{self._escape_html(str(item))}</li>")
            html_parts.append("</ul>")
        else:
            html_parts.append(f"<p>{self._escape_html(str(content))}</p>")

        # Add custom footers
        for footer_name, footer_content in options.custom_footers.items():
            html_parts.append(f"<!-- {footer_name}: {footer_content} -->")

        html_parts.append("</body>")
        html_parts.append("</html>")

        return "\n".join(html_parts)

    def _format_markdown(
        self, content: Any, options: FormattingOptions  # TODO(TYPE): replace Any with concrete type
    ) -> str:  # TODO(TYPE): replace Any with concrete type
        """Format content as Markdown."""
        md_parts: list[str] = []
        # Add custom headers
        for header_name, header_content in options.custom_headers.items():
            md_parts.append(f"<!-- {header_name}: {header_content} -->")

        md_parts.append("# Response")
        md_parts.append("")

        if isinstance(content, dict):
            for key, value in content.items():
                md_parts.append(f"## {key}")
                md_parts.append("")
                md_parts.append(str(value))
                md_parts.append("")
        elif isinstance(content, list):
            for i, item in enumerate(content, 1):
                md_parts.append(f"{i}. {item}")
        else:
            md_parts.append(str(content))

        # Add custom footers
        md_parts.append("")
        for footer_name, footer_content in options.custom_footers.items():
            md_parts.append(f"<!-- {footer_name}: {footer_content} -->")

        return "\n".join(md_parts)

    def _format_plain_text(
        self, content: Any, options: FormattingOptions  # TODO(TYPE): replace Any with concrete type
    ) -> str:  # TODO(TYPE): replace Any with concrete type
        """Format content as plain text."""
        if isinstance(content, dict):
            lines: list[str] = []
            for key, value in content.items():
                lines.append(f"{key}: {value}")
            return "\n".join(lines)
        elif isinstance(content, list):
            return "\n".join(str(item) for item in content)
        else:
            return str(content)

    def _format_structured(
        self, content: Any, options: FormattingOptions  # TODO(TYPE): replace Any with concrete type
    ) -> str:  # TODO(TYPE): replace Any with concrete type
        """Format content with structured layout."""
        lines: list[str] = []
        if options.include_timestamps:
            lines.append(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
            lines.append("-" * 40)

        lines.append("STRUCTURED RESPONSE")
        lines.append("=" * 40)

        if isinstance(content, dict):
            for key, value in content.items():
                lines.append(f"{key.upper()}:")
                lines.append(f"  {value}")
                lines.append("")
        elif isinstance(content, list):
            lines.append("ITEMS:")
            for i, item in enumerate(content, 1):
                lines.append(f"  {i}. {item}")
        else:
            lines.append("CONTENT:")
            lines.append(f"  {content}")

        lines.append("=" * 40)
        return "\n".join(lines)

    def _format_custom(
        self, content: Any, options: FormattingOptions  # TODO(TYPE): replace Any with concrete type
    ) -> str:  # TODO(TYPE): replace Any with concrete type
        """Format content using custom formatter if available."""
        # Try to find a custom formatter
        for formatter_name, formatter_func in self.custom_formatters.items():
            try:
                formatted: str = formatter_func(content, options)
                return formatted
            except Exception as e:
                logger.warning(f"Custom formatter {formatter_name} failed: {e}")

        # Fallback to plain text
        fallback: str = self._format_plain_text(content, options)
        return fallback

    def _escape_html(self, text: str) -> str:
        """Escape HTML special characters."""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#x27;")
        )

    def _apply_formatting_rules(
        self, content: str, format_type: FormatType
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Apply formatting rules to content."""
        applied_rules: list[str] = []
        result_content: str = content

        if format_type in self.format_rules:
            rules = sorted(self.format_rules[format_type], key=lambda r: r.apply_order)

            for rule in rules:
                try:
                    old_content = result_content
                    result_content = re.sub(
                        rule.pattern, rule.replacement, result_content, flags=rule.flags
                    )
                    if old_content != result_content:
                        applied_rules.append(f"Applied rule: {rule.pattern}")
                except Exception as e:
                    logger.warning(f"Failed to apply formatting rule {rule.pattern}: {e}")

        return {"content": result_content, "rules": applied_rules}

    def _generate_metadata(
        self,
        content: Any,  # TODO(TYPE): replace Any with concrete type
        format_type: FormatType,
        options: FormattingOptions,  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Generate metadata for the formatted response."""
        metadata: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "format_type": format_type.value,
            "content_type": type(content).__name__,
            "content_length": len(str(content)),
            "formatting_options": {
                "indent_size": options.indent_size,
                "include_metadata": options.include_metadata,
                "include_timestamps": options.include_timestamps,
                "pretty_print": options.pretty_print,
            },
        }

        if options.include_timestamps:
            metadata["timestamp"] = datetime.now(timezone.utc).isoformat()

        if options.include_source:
            metadata["source"] = "ResponseFormatter"

        # Add template variables if present
        if options.template_variables:
            metadata["template_variables"] = options.template_variables

        return metadata

    def _generate_cache_key(
        self,
        content: Any,  # TODO(TYPE): replace Any with concrete type
        format_type: FormatType,
        options: FormattingOptions,  # TODO(TYPE): replace Any with concrete type
    ) -> str:
        """Generate cache key for the formatting operation."""
        key_data = {
            "content": str(content)[:1000],  # Limit content length for key
            "format_type": format_type.value,
            "options": {
                "indent_size": options.indent_size,
                "pretty_print": options.pretty_print,
                "include_metadata": options.include_metadata,
                "include_timestamps": options.include_timestamps,
            },
        }

        key_string = json.dumps(key_data, sort_keys=True)
        return hashlib.md5(key_string.encode("ascii"), usedforsecurity=False).hexdigest()

    def _update_stats(self, processing_time: float) -> None:
        """Update formatting statistics."""
        self.stats["formats_processed"] += 1

        # Update running average
        current_avg = self.stats["average_processing_time"]
        count = self.stats["formats_processed"]
        self.stats["average_processing_time"] = (
            (current_avg * (count - 1)) + processing_time
        ) / count

    def add_format_rule(self, format_type: FormatType, rule: FormatRule) -> None:
        """Add a custom formatting rule."""
        if format_type not in self.format_rules:
            self.format_rules[format_type] = []

        self.format_rules[format_type].append(rule)
        logger.info(f"Added formatting rule for {format_type.value}: {rule.pattern}")

    def register_custom_formatter(
        self, name: str, formatter_func: Callable[..., Any]
    ) -> None:  # TODO(TYPE): replace Any with concrete type
        """Register a custom formatting function."""
        self.custom_formatters[name] = formatter_func
        logger.info(f"Registered custom formatter: {name}")

    def get_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get formatting statistics."""
        return self.stats.copy()

    def reset_stats(self) -> None:
        """Reset formatting statistics."""
        self.stats = {
            "formats_processed": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "errors": 0,
            "average_processing_time": 0.0,
        }
        logger.info("Formatting statistics reset")


def create_response_formatter(
    cache_layer: _CacheLayer | None = None,
) -> ResponseFormatter:
    """Factory function to create a ResponseFormatter instance."""
    return ResponseFormatter(cache_layer=cache_layer)
