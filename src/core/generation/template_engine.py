"""
Template Engine - Advanced template processing and rendering system
Provides flexible template management with variable substitution and logic
"""

import ast
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TypedDict
from collections.abc import Callable

from src.core.shared.production_logging import SafeLogger

logger = SafeLogger(__name__)


class TemplateEngineStats(TypedDict):
    """Typed statistics dictionary for TemplateEngine."""

    templates_loaded: int
    renders_performed: int
    render_errors: int
    available_templates: int
    render_success_rate: float


class TemplateType(Enum):
    """Types of templates"""

    TEXT = "text"
    HTML = "html"
    JSON = "json"
    MARKDOWN = "markdown"
    CODE = "code"


class VariableType(Enum):
    """Types of template variables"""

    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    LIST = "list"
    OBJECT = "object"
    DATE = "date"


@dataclass
class TemplateVariable:
    """Template variable definition"""

    name: str
    variable_type: VariableType
    default_value: object = None
    required: bool = False
    description: str = ""
    validation_pattern: str | None = None

    def validate(self, value: object) -> bool:
        """Validate variable value"""
        try:
            # Type validation
            if self.variable_type == VariableType.STRING:
                if not isinstance(value, str):
                    return False
            elif self.variable_type == VariableType.NUMBER:
                if not isinstance(value, (int, float)):
                    return False
            elif self.variable_type == VariableType.BOOLEAN:
                if not isinstance(value, bool):
                    return False
            elif self.variable_type == VariableType.LIST:
                if not isinstance(value, list):
                    return False
            elif self.variable_type == VariableType.OBJECT:
                if not isinstance(value, dict):
                    return False

            # Pattern validation for strings
            if self.validation_pattern and isinstance(value, str):
                if not re.match(self.validation_pattern, value):
                    return False

            return True

        except Exception as e:
            logger.warning(f"Variable validation failed: {e}")
            return False


@dataclass
class TemplateContext:
    """Context for template rendering"""

    variables: dict[str, object] = field(default_factory=dict)
    functions: dict[str, Callable[..., object]] = field(default_factory=dict)
    global_context: dict[str, object] = field(default_factory=dict)

    def get_variable(self, name: str, default: object = None) -> object:
        """Get variable value with fallback to global context"""
        if name in self.variables:
            return self.variables[name]
        elif name in self.global_context:
            return self.global_context[name]
        else:
            return default

    def set_variable(self, name: str, value: object) -> None:
        """Set variable value"""
        self.variables[name] = value

    def add_function(self, name: str, func: Callable[..., object]) -> None:
        """Add custom function to context"""
        self.functions[name] = func


class TemplateParser:
    """Parses template syntax and extracts components"""

    def __init__(self) -> None:
        # Template syntax patterns
        self.variable_pattern = r"\{\{\s*([^}]+)\s*\}\}"
        self.conditional_pattern = r"\{\%\s*if\s+([^%]+)\s*\%\}(.*?)\{\%\s*endif\s*\%\}"
        self.loop_pattern = r"\{\%\s*for\s+(\w+)\s+in\s+([^%]+)\s*\%\}(.*?)\{\%\s*endfor\s*\%\}"
        self.function_pattern = r"\{\{\s*(\w+)\((.*?)\)\s*\}\}"

    def extract_variables(self, template_content: str) -> list[str]:
        """Extract all variable names from template"""
        variables = set()

        # Extract simple variables
        simple_vars = re.findall(self.variable_pattern, template_content)
        for var in simple_vars:
            var_name = var.split(".")[0].split("|")[0].strip()
            if var_name and not var_name.startswith("("):
                variables.add(var_name)

        # Extract variables from conditionals
        conditionals = re.findall(self.conditional_pattern, template_content, re.DOTALL)
        for condition, _ in conditionals:
            condition_vars = re.findall(r"\b(\w+)\b", condition)
            variables.update(condition_vars)

        # Extract variables from loops
        loops = re.findall(self.loop_pattern, template_content, re.DOTALL)
        for _, iterable, _ in loops:
            iterable_vars = re.findall(r"\b(\w+)\b", iterable)
            variables.update(iterable_vars)

        return list(variables)

    def extract_functions(self, template_content: str) -> list[str]:
        """Extract all function calls from template"""
        functions = re.findall(self.function_pattern, template_content)
        return [func_name for func_name, _ in functions]

    def validate_syntax(self, template_content: str) -> tuple[bool, list[str]]:
        """Validate template syntax"""
        errors: list[str] = []
        try:
            # Check for unmatched braces
            open_braces = template_content.count("{{")
            close_braces = template_content.count("}}")
            if open_braces != close_braces:
                errors.append(f"Unmatched braces: {open_braces} opening, {close_braces} closing")

            # Check for unmatched conditionals
            if_count = len(re.findall(r"\{\%\s*if\s+", template_content))
            endif_count = len(re.findall(r"\{\%\s*endif\s*\%\}", template_content))
            if if_count != endif_count:
                errors.append(f"Unmatched conditionals: {if_count} if, {endif_count} endif")

            # Check for unmatched loops
            for_count = len(re.findall(r"\{\%\s*for\s+", template_content))
            endfor_count = len(re.findall(r"\{\%\s*endfor\s*\%\}", template_content))
            if for_count != endfor_count:
                errors.append(f"Unmatched loops: {for_count} for, {endfor_count} endfor")

            return len(errors) == 0, errors

        except Exception as e:
            logger.error(f"Syntax validation failed: {e}")
            return False, [f"Validation error: {str(e)}"]


class TemplateRenderer:
    """Renders templates with variable substitution and logic"""

    def __init__(self) -> None:
        self.parser = TemplateParser()
        self.builtin_functions: dict[str, Callable[..., object]] = {
            "upper": lambda x: str(x).upper(),
            "lower": lambda x: str(x).lower(),
            "length": lambda x: len(x) if hasattr(x, "__len__") else 0,
            "default": lambda x, d: x if x is not None else d,
            "format_date": self._format_date,
            "format_number": self._format_number,
            "join": lambda x, sep=", ": (
                sep.join(str(i) for i in x) if isinstance(x, list) else str(x)
            ),
        }

    async def render(self, template_content: str, context: TemplateContext) -> str:
        """Render template with given context"""
        try:
            # Validate syntax first
            is_valid, errors = self.parser.validate_syntax(template_content)
            if not is_valid:
                logger.warning(f"Template syntax errors: {errors}")

            # Process template in stages
            rendered = template_content

            # 1. Process loops
            rendered = await self._process_loops(rendered, context)

            # 2. Process conditionals
            rendered = await self._process_conditionals(rendered, context)

            # 3. Process function calls
            rendered = await self._process_functions(rendered, context)

            # 4. Process simple variables
            rendered = await self._process_variables(rendered, context)

            # Ensure ASCII compliance
            ascii_rendered = rendered.encode("ascii", errors="ignore").decode("ascii")

            return ascii_rendered

        except Exception as e:
            logger.error(f"Template rendering failed: {e}")
            return f"Template rendering error: {str(e)}"

    async def _process_loops(self, content: str, context: TemplateContext) -> str:
        """Process for loops in template"""
        try:
            loop_pattern = r"\{\%\s*for\s+(\w+)\s+in\s+([^%]+)\s*\%\}(.*?)\{\%\s*endfor\s*\%\}"

            def replace_loop(match: re.Match[str]) -> str:
                var_name = match.group(1)
                iterable_name = match.group(2).strip()
                loop_content = match.group(3)

                # Get iterable from context
                iterable = context.get_variable(iterable_name, [])

                if not isinstance(iterable, (list, tuple)):
                    logger.warning(f"Loop variable {iterable_name} is not iterable")
                    return ""

                # Render loop content for each item
                loop_result: list[str] = []
                for item in iterable:
                    # Create new context with loop variable
                    loop_context = TemplateContext(
                        variables={**context.variables, var_name: item},
                        functions=context.functions,
                        global_context=context.global_context,
                    )

                    # Process loop content with loop context
                    rendered_item = loop_content
                    rendered_item = self._substitute_variables(rendered_item, loop_context)
                    loop_result.append(rendered_item)

                return "".join(loop_result)

            return re.sub(loop_pattern, replace_loop, content, flags=re.DOTALL)

        except Exception as e:
            logger.error(f"Loop processing failed: {e}")
            return content

    async def _process_conditionals(self, content: str, context: TemplateContext) -> str:
        """Process conditional statements in template"""
        try:
            conditional_pattern = r"\{\%\s*if\s+([^%]+)\s*\%\}(.*?)\{\%\s*endif\s*\%\}"

            def replace_conditional(match: re.Match[str]) -> str:
                condition = match.group(1).strip()
                conditional_content = match.group(2)

                # Evaluate condition
                try:
                    if self._evaluate_condition(condition, context):
                        return conditional_content
                    else:
                        return ""
                except Exception as e:
                    logger.warning(f"Condition evaluation failed: {e}")
                    return ""

            return re.sub(conditional_pattern, replace_conditional, content, flags=re.DOTALL)

        except Exception as e:
            logger.error(f"Conditional processing failed: {e}")
            return content

    async def _process_functions(self, content: str, context: TemplateContext) -> str:
        """Process function calls in template"""
        try:
            function_pattern = r"\{\{\s*(\w+)\((.*?)\)\s*\}\}"

            def replace_function(match: re.Match[str]) -> str:
                func_name = match.group(1)
                args_str = match.group(2)

                # Get function
                if func_name in context.functions:
                    func = context.functions[func_name]
                elif func_name in self.builtin_functions:
                    func = self.builtin_functions[func_name]
                else:
                    logger.warning(f"Unknown function: {func_name}")
                    return f"{{{{ {func_name}(???) }}}}"

                # Parse arguments
                try:
                    args = self._parse_function_args(args_str, context)
                    result = func(*args)
                    return str(result)
                except Exception as e:
                    logger.warning(f"Function call failed: {func_name}: {e}")
                    return f"{{{{ {func_name}(error) }}}}"

            return re.sub(function_pattern, replace_function, content)

        except Exception as e:
            logger.error(f"Function processing failed: {e}")
            return content

    async def _process_variables(self, content: str, context: TemplateContext) -> str:
        """Process simple variable substitution"""
        return self._substitute_variables(content, context)

    def _substitute_variables(self, content: str, context: TemplateContext) -> str:
        """Substitute variables in content"""
        try:
            variable_pattern = r"\{\{\s*([^}]+)\s*\}\}"

            def replace_variable(match: re.Match[str]) -> str:
                var_expression = match.group(1).strip()

                # Handle filters (variable|filter)
                if "|" in var_expression:
                    var_name, filter_name = var_expression.split("|", 1)
                    var_name = var_name.strip()
                    filter_name = filter_name.strip()

                    value = context.get_variable(var_name, "")

                    # Apply filter
                    if filter_name in self.builtin_functions:
                        try:
                            value = self.builtin_functions[filter_name](value)
                        except Exception as e:
                            logger.warning(f"Filter application failed: {e}")

                    return str(value)
                else:
                    # Simple variable substitution
                    value = context.get_variable(var_expression, "")
                    return str(value)

            return re.sub(variable_pattern, replace_variable, content)

        except Exception as e:
            logger.error(f"Variable substitution failed: {e}")
            return content

    def _evaluate_condition(self, condition: str, context: TemplateContext) -> bool:
        """Evaluate conditional expression"""
        try:
            # Simple condition evaluation
            # Replace variables with their values
            for var_name in re.findall(r"\b(\w+)\b", condition):
                var_value = context.get_variable(var_name)
                if var_value is not None:
                    if isinstance(var_value, str):
                        condition = condition.replace(var_name, f'"{var_value}"')
                    else:
                        condition = condition.replace(var_name, str(var_value))

            # Safe evaluation of simple expressions

            # Check if condition contains only allowed elements
            condition_clean = re.sub(r'["\'].*?["\']', '""', condition)  # Replace strings
            condition_clean = re.sub(r"\d+", "0", condition_clean)  # Replace numbers
            condition_clean = re.sub(r"[<>=!]+", "", condition_clean)  # Remove operators

            if re.search(r"[a-zA-Z_]\w*", condition_clean):
                # Contains variables not replaced - unsafe
                return False

            # SECURITY FIX: Replace eval() with safe AST-based evaluation
            result = self._safe_eval_condition(condition)
            return bool(result)

        except Exception as e:
            logger.warning(f"Condition evaluation error: {e}")
            return False

    def _safe_eval_condition(self, condition: str) -> bool:
        """Safely evaluate a condition using AST parsing instead of eval()"""
        try:
            # Parse the condition into an AST
            tree = ast.parse(condition, mode="eval")

            # Validate that only safe operations are used
            for node in ast.walk(tree):
                # Allow only comparison, boolean operations, and literals
                if not isinstance(
                    node,
                    (
                        ast.Expression,
                        ast.Compare,
                        ast.BoolOp,
                        ast.UnaryOp,
                        ast.And,
                        ast.Or,
                        ast.Not,
                        ast.Eq,
                        ast.NotEq,
                        ast.Lt,
                        ast.LtE,
                        ast.Gt,
                        ast.GtE,
                        ast.In,
                        ast.NotIn,
                        ast.Is,
                        ast.IsNot,
                        ast.Constant,
                        ast.Str,
                        ast.Num,
                        ast.NameConstant,
                        ast.List,
                        ast.Tuple,
                    ),
                ):
                    logger.warning(f"Unsafe AST node in condition: {node.__class__.__name__}")
                    return False

            # Compile and evaluate safely
            # SECURITY: Already validated via AST - only safe comparison/boolean ops allowed
            # eval() is safe here because:
            # 1. Input is parsed and validated via AST whitelist (lines 391-402)
            # 2. Builtins are completely disabled (empty dict)
            # 3. No variables in scope (empty dict)
            # 4. Only literal values and comparison operators allowed
            code = compile(tree, "<condition>", "eval")
            result = eval(code, {"__builtins__": {}}, {})  # nosec B307
            return bool(result)

        except Exception as e:
            logger.warning(f"Safe condition evaluation error: {e}")
            return False

    def _parse_function_args(
        self, args_str: str, context: TemplateContext
    ) -> list[str | int | float | bool]:
        """Parse function arguments"""
        if not args_str.strip():
            return []

        try:
            # Split arguments by comma (simple parsing)
            arg_parts: list[str] = []
            current_arg = ""
            paren_depth = 0
            in_quotes = False
            quote_char = None

            for char in args_str:
                if char in ['"', "'"] and not in_quotes:
                    in_quotes = True
                    quote_char = char
                elif char == quote_char and in_quotes:
                    in_quotes = False
                    quote_char = None
                elif char == "(" and not in_quotes:
                    paren_depth += 1
                elif char == ")" and not in_quotes:
                    paren_depth -= 1
                elif char == "," and paren_depth == 0 and not in_quotes:
                    arg_parts.append(current_arg.strip())
                    current_arg = ""
                    continue

                current_arg += char

            if current_arg.strip():
                arg_parts.append(current_arg.strip())

            # Convert arguments to appropriate types
            args: list[str | int | float | bool] = []
            for arg in arg_parts:
                arg = arg.strip()

                # String literal
                if (arg.startswith('"') and arg.endswith('"')) or (
                    arg.startswith("'") and arg.endswith("'")
                ):
                    args.append(arg[1:-1])
                # Number
                elif arg.isdigit():
                    args.append(int(arg))
                elif re.match(r"^\d+\.\d+$", arg):
                    args.append(float(arg))
                # Boolean
                elif arg.lower() == "true":
                    args.append(True)
                elif arg.lower() == "false":
                    args.append(False)
                # Variable -- get_variable may return Any; cast to str as fallback
                else:
                    args.append(str(context.get_variable(arg, arg)))

            return args

        except Exception as e:
            logger.warning(f"Argument parsing failed: {e}")
            return []

    def _format_date(
        self, date_value: datetime | str | object, format_str: str = "%Y-%m-%d"
    ) -> str:
        """Format date value"""
        try:
            if isinstance(date_value, datetime):
                return date_value.strftime(format_str)
            elif isinstance(date_value, str):
                return date_value
            else:
                return str(date_value)
        except Exception:
            return str(date_value)

    def _format_number(self, number_value: int | float | object, precision: int = 2) -> str:
        """Format number value"""
        try:
            if isinstance(number_value, (int, float)):
                return f"{number_value:.{precision}f}"
            else:
                return str(number_value)
        except Exception:
            return str(number_value)


class Template:
    """Template class that encapsulates template content and metadata"""

    def __init__(
        self,
        template_id: str,
        content: str,
        template_type: TemplateType = TemplateType.TEXT,
    ) -> None:
        self.template_id = template_id
        self.content = content
        self.template_type = template_type
        self.created_at = datetime.now(timezone.utc)
        self.variables: list[TemplateVariable] = []
        self.metadata: dict[str, object] = {}

        # Initialize parser and extract variables
        self.parser = TemplateParser()
        self._extract_template_info()

    def _extract_template_info(self) -> None:
        """Extract information about template variables and functions"""
        try:
            # Extract variable names
            var_names = self.parser.extract_variables(self.content)

            # Create basic variable definitions
            for var_name in var_names:
                self.variables.append(
                    TemplateVariable(
                        name=var_name, variable_type=VariableType.STRING, required=True
                    )
                )

            # Extract function names
            func_names = self.parser.extract_functions(self.content)
            self.metadata["required_functions"] = func_names

        except Exception as e:
            logger.warning(f"Template info extraction failed: {e}")

    def add_variable(self, variable: TemplateVariable) -> None:
        """Add variable definition to template"""
        # Remove existing variable with same name
        self.variables = [v for v in self.variables if v.name != variable.name]
        self.variables.append(variable)

    def validate_context(self, context: TemplateContext) -> tuple[bool, list[str]]:
        """Validate that context provides all required variables"""
        errors: list[str] = []
        for variable in self.variables:
            if variable.required:
                value = context.get_variable(variable.name)
                if value is None:
                    errors.append(f"Required variable '{variable.name}' is missing")
                elif not variable.validate(value):
                    errors.append(f"Variable '{variable.name}' has invalid value")

        return len(errors) == 0, errors

    def to_dict(self) -> dict[str, object]:
        """Convert template to dictionary"""
        return {
            "template_id": self.template_id,
            "content": self.content,
            "template_type": self.template_type.value,
            "created_at": self.created_at.isoformat(),
            "variables": [
                {
                    "name": var.name,
                    "type": var.variable_type.value,
                    "required": var.required,
                    "description": var.description,
                }
                for var in self.variables
            ],
            "metadata": self.metadata,
        }


class TemplateEngine:
    """
    Main template engine that manages templates and rendering
    """

    def __init__(self) -> None:
        self.templates: dict[str, Template] = {}
        self.renderer = TemplateRenderer()
        self.global_context = TemplateContext()
        self._initialized = False
        self._stats = {
            "templates_loaded": 0,
            "renders_performed": 0,
            "render_errors": 0,
        }

    async def initialize(self) -> bool:
        """Initialize template engine"""
        try:
            # Load default templates
            await self._load_default_templates()

            # Setup global context
            self._setup_global_context()

            self._initialized = True
            logger.info("Template Engine initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize template engine: {e}")
            return False

    async def load_template(
        self,
        template_id: str,
        content: str,
        template_type: TemplateType = TemplateType.TEXT,
    ) -> bool:
        """Load template into engine"""
        try:
            template = Template(template_id, content, template_type)
            self.templates[template_id] = template
            self._stats["templates_loaded"] += 1

            logger.debug(f"Template loaded: {template_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to load template {template_id}: {e}")
            return False

    async def render_template(
        self,
        template_id: str,
        variables: dict[str, object] | None = None,
        functions: dict[str, Callable[..., object]] | None = None,
    ) -> str:
        """Render template with provided context"""
        if not self._initialized:
            await self.initialize()

        try:
            if template_id not in self.templates:
                logger.error(f"Template not found: {template_id}")
                return f"Template '{template_id}' not found"

            template = self.templates[template_id]

            # Create rendering context
            context = TemplateContext(
                variables=variables or {},
                functions=functions or {},
                global_context=self.global_context.variables,
            )

            # Validate context
            is_valid, errors = template.validate_context(context)
            if not is_valid:
                logger.warning(f"Template context validation failed: {errors}")

            # Render template
            rendered_content = await self.renderer.render(template.content, context)

            self._stats["renders_performed"] += 1
            return rendered_content

        except Exception as e:
            logger.error(f"Template rendering failed: {e}")
            self._stats["render_errors"] += 1
            return f"Template rendering error: {str(e)}"

    async def get_template_info(self, template_id: str) -> dict[str, object] | None:
        """Get information about a template"""
        if template_id in self.templates:
            return self.templates[template_id].to_dict()
        return None

    async def list_templates(self) -> list[str]:
        """List all available template IDs"""
        return list(self.templates.keys())

    async def get_template_stats(
        self,
    ) -> TemplateEngineStats:
        """Get template engine statistics"""
        return {
            "templates_loaded": self._stats["templates_loaded"],
            "renders_performed": self._stats["renders_performed"],
            "render_errors": self._stats["render_errors"],
            "available_templates": len(self.templates),
            "render_success_rate": (self._stats["renders_performed"] - self._stats["render_errors"])
            / max(1, self._stats["renders_performed"])
            * 100,
        }

    def set_global_variable(self, name: str, value: object) -> None:
        """Set global variable available to all templates"""
        self.global_context.set_variable(name, value)

    def add_global_function(self, name: str, func: Callable[..., object]) -> None:
        """Add global function available to all templates"""
        self.global_context.add_function(name, func)

    async def _load_default_templates(self) -> None:
        """Load default templates"""
        try:
            default_templates = {
                "simple_response": {
                    "content": "Response: {{ response_text }}",
                    "type": TemplateType.TEXT,
                },
                "basic_documentation": {
                    "content": """# {{ title }}

## Overview
{{ overview }}

## Details
{% if details %}{{ details }}{% endif %}

## Usage
{{ usage }}""",
                    "type": TemplateType.MARKDOWN,
                },
                "error_message": {
                    "content": "Error: {{ error_type }} - {{ error_message }}{% if suggestions %}\nSuggestions: {{ suggestions|join }}{% endif %}",
                    "type": TemplateType.TEXT,
                },
                "list_format": {
                    "content": """{{ title }}:
{% for item in items %}- {{ item }}
{% endfor %}""",
                    "type": TemplateType.TEXT,
                },
            }

            for template_id, template_data in default_templates.items():
                await self.load_template(
                    template_id,
                    str(template_data["content"]),
                    TemplateType(template_data["type"]),
                )

            logger.debug(f"Loaded {len(default_templates)} default templates")

        except Exception as e:
            logger.warning(f"Failed to load default templates: {e}")

    def _setup_global_context(self) -> None:
        """Setup global context with common variables and functions"""
        try:
            # Global variables
            self.set_global_variable(
                "current_date", datetime.now(timezone.utc).strftime("%Y-%m-%d")
            )
            self.set_global_variable(
                "current_time", datetime.now(timezone.utc).strftime("%H:%M:%S")
            )

            # Global functions
            self.add_global_function("now", lambda: datetime.now(timezone.utc).isoformat())
            self.add_global_function(
                "escape_html",
                lambda x: str(x).replace("<", "&lt;").replace(">", "&gt;"),
            )

        except Exception as e:
            logger.warning(f"Global context setup failed: {e}")


# Global template engine instance
_global_template_engine: TemplateEngine | None = None


async def get_template_engine() -> TemplateEngine:
    """Get global template engine instance"""
    global _global_template_engine

    if _global_template_engine is None:
        _global_template_engine = TemplateEngine()
        await _global_template_engine.initialize()

    return _global_template_engine
