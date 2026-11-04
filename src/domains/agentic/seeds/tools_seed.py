from typing import Any

"""
Tool Definitions Seed Data

Matches ToolDefinition model fields exactly:
- name (String, required, unique)
- display_name (String, required)
- description (Text, required)
- category (String, required)
- function_schema (JSON, required) - OpenAI-compatible
- implementation_type (String, default "internal")
- implementation_config (JSON, optional)
- required_permissions (JSON, optional)
- is_active (Boolean)
"""

TOOL_DEFINITIONS: list[dict[str, Any]] = [  # TODO(TYPE): replace Any with concrete type
    {
        "name": "web_search",
        "display_name": "Web Search",
        "description": "Search the web for current information using various search engines.",
        "category": "search",
        "function_schema": {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "num_results": {
                    "type": "integer",
                    "default": 5,
                    "description": "Number of results",
                },
                "region": {
                    "type": "string",
                    "description": "Region for localized results",
                },
            },
        },
        "implementation_type": "internal",
        "implementation_config": {
            "module_path": "src.core.tools.web_search",
            "function_name": "search",
        },
        "required_permissions": [],
        "is_active": True,
    },
    {
        "name": "calculate",
        "display_name": "Calculator",
        "description": "Perform mathematical calculations and expressions.",
        "category": "utility",
        "function_schema": {
            "type": "object",
            "required": ["expression"],
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Mathematical expression to evaluate",
                }
            },
        },
        "implementation_type": "internal",
        "implementation_config": {
            "module_path": "src.core.tools.calculator",
            "function_name": "calculate",
        },
        "required_permissions": [],
        "is_active": True,
    },
    {
        "name": "code_executor",
        "display_name": "Code Executor",
        "description": "Execute code in a sandboxed environment.",
        "category": "development",
        "function_schema": {
            "type": "object",
            "required": ["code", "language"],
            "properties": {
                "code": {"type": "string", "description": "Code to execute"},
                "language": {
                    "type": "string",
                    "enum": ["python", "javascript", "typescript"],
                    "description": "Programming language",
                },
                "timeout": {
                    "type": "integer",
                    "default": 30,
                    "description": "Execution timeout in seconds",
                },
            },
        },
        "implementation_type": "internal",
        "implementation_config": {
            "module_path": "src.core.tools.code_executor",
            "function_name": "execute",
        },
        "required_permissions": ["code:execute"],
        "is_active": True,
    },
    {
        "name": "git_tool",
        "display_name": "Git Operations",
        "description": "Perform Git operations like status, diff, log, and branch management.",
        "category": "development",
        "function_schema": {
            "type": "object",
            "required": ["operation"],
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["status", "diff", "log", "branch"],
                    "description": "Git operation",
                },
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Additional arguments",
                },
            },
        },
        "implementation_type": "internal",
        "implementation_config": {
            "module_path": "src.core.tools.git_tool",
            "function_name": "execute_git",
        },
        "required_permissions": ["code:read"],
        "is_active": True,
    },
    {
        "name": "text_analyzer",
        "display_name": "Text Analyzer",
        "description": "Analyze text for sentiment, readability, and key phrases.",
        "category": "content",
        "function_schema": {
            "type": "object",
            "required": ["text"],
            "properties": {
                "text": {"type": "string", "description": "Text to analyze"},
                "metrics": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Metrics to compute",
                },
            },
        },
        "implementation_type": "internal",
        "implementation_config": {
            "module_path": "src.core.tools.text_analyzer",
            "function_name": "analyze",
        },
        "required_permissions": [],
        "is_active": True,
    },
    {
        "name": "data_query",
        "display_name": "Data Query",
        "description": "Execute SQL queries against connected databases.",
        "category": "data",
        "function_schema": {
            "type": "object",
            "required": ["sql"],
            "properties": {
                "sql": {"type": "string", "description": "SQL query to execute"},
                "database": {"type": "string", "description": "Target database name"},
                "limit": {
                    "type": "integer",
                    "default": 100,
                    "description": "Maximum rows to return",
                },
            },
        },
        "implementation_type": "internal",
        "implementation_config": {
            "module_path": "src.core.tools.data_query",
            "function_name": "query",
        },
        "required_permissions": ["data:read"],
        "is_active": True,
    },
    {
        "name": "chart_generator",
        "display_name": "Chart Generator",
        "description": "Generate charts and visualizations from data.",
        "category": "data",
        "function_schema": {
            "type": "object",
            "required": ["data", "chart_type"],
            "properties": {
                "data": {"type": "object", "description": "Data to visualize"},
                "chart_type": {
                    "type": "string",
                    "enum": ["bar", "line", "pie", "scatter", "heatmap"],
                    "description": "Type of chart",
                },
                "title": {"type": "string", "description": "Chart title"},
            },
        },
        "implementation_type": "internal",
        "implementation_config": {
            "module_path": "src.core.tools.chart_generator",
            "function_name": "generate",
        },
        "required_permissions": [],
        "is_active": True,
    },
    {
        "name": "workflow_engine",
        "display_name": "Workflow Engine",
        "description": "Create and manage automated workflows.",
        "category": "automation",
        "function_schema": {
            "type": "object",
            "required": ["action"],
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "update", "delete", "trigger", "status"],
                    "description": "Workflow action",
                },
                "workflow_id": {"type": "string", "description": "Workflow identifier"},
                "definition": {"type": "object", "description": "Workflow definition"},
            },
        },
        "implementation_type": "internal",
        "implementation_config": {
            "module_path": "src.core.tools.workflow_engine",
            "function_name": "manage_workflow",
        },
        "required_permissions": ["workflow:manage"],
        "is_active": True,
    },
    {
        "name": "translation_engine",
        "display_name": "Translation Engine",
        "description": "Translate text between languages.",
        "category": "content",
        "function_schema": {
            "type": "object",
            "required": ["text", "target_language"],
            "properties": {
                "text": {"type": "string", "description": "Text to translate"},
                "source_language": {
                    "type": "string",
                    "description": "Source language code",
                },
                "target_language": {
                    "type": "string",
                    "description": "Target language code",
                },
            },
        },
        "implementation_type": "internal",
        "implementation_config": {
            "module_path": "src.core.tools.translation_engine",
            "function_name": "translate",
        },
        "required_permissions": [],
        "is_active": True,
    },
    {
        "name": "seo_checker",
        "display_name": "SEO Checker",
        "description": "Analyze content for SEO optimization.",
        "category": "content",
        "function_schema": {
            "type": "object",
            "required": ["content"],
            "properties": {
                "content": {"type": "string", "description": "Content to analyze"},
                "target_keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Target keywords",
                },
            },
        },
        "implementation_type": "internal",
        "implementation_config": {
            "module_path": "src.core.tools.seo_checker",
            "function_name": "analyze",
        },
        "required_permissions": [],
        "is_active": True,
    },
    {
        "name": "document_parser",
        "display_name": "Document Parser",
        "description": "Parse and extract content from documents.",
        "category": "content",
        "function_schema": {
            "type": "object",
            "required": ["document_url"],
            "properties": {
                "document_url": {
                    "type": "string",
                    "description": "URL or path to the document",
                },
                "format": {
                    "type": "string",
                    "enum": ["pdf", "docx", "html", "txt"],
                    "description": "Document format",
                },
            },
        },
        "implementation_type": "internal",
        "implementation_config": {
            "module_path": "src.core.tools.document_parser",
            "function_name": "parse",
        },
        "required_permissions": ["content:read"],
        "is_active": True,
    },
    {
        "name": "image_generator",
        "display_name": "Image Generator",
        "description": "Generate images from text descriptions.",
        "category": "content",
        "function_schema": {
            "type": "object",
            "required": ["prompt"],
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Text description for image generation",
                },
                "style": {"type": "string", "description": "Image style"},
                "size": {
                    "type": "string",
                    "enum": ["256x256", "512x512", "1024x1024"],
                    "description": "Image dimensions",
                },
            },
        },
        "implementation_type": "external",
        "implementation_config": {"provider": "openai", "model": "dall-e-3"},
        "required_permissions": ["content:create"],
        "is_active": True,
    },
    {
        "name": "image_editor",
        "display_name": "Image Editor",
        "description": "Edit and manipulate images.",
        "category": "content",
        "function_schema": {
            "type": "object",
            "required": ["image_url", "operation"],
            "properties": {
                "image_url": {
                    "type": "string",
                    "description": "URL or path to the image",
                },
                "operation": {
                    "type": "string",
                    "enum": ["resize", "crop", "filter", "overlay"],
                    "description": "Edit operation",
                },
                "parameters": {"type": "object", "description": "Operation parameters"},
            },
        },
        "implementation_type": "internal",
        "implementation_config": {
            "module_path": "src.core.tools.image_editor",
            "function_name": "edit",
        },
        "required_permissions": ["content:create"],
        "is_active": True,
    },
    {
        "name": "scheduler",
        "display_name": "Task Scheduler",
        "description": "Schedule tasks and reminders.",
        "category": "automation",
        "function_schema": {
            "type": "object",
            "required": ["action", "schedule"],
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "update", "delete", "list"],
                    "description": "Scheduler action",
                },
                "schedule": {
                    "type": "string",
                    "description": "Cron expression or ISO datetime",
                },
                "task_id": {"type": "string", "description": "Task identifier"},
            },
        },
        "implementation_type": "internal",
        "implementation_config": {
            "module_path": "src.core.tools.scheduler",
            "function_name": "schedule",
        },
        "required_permissions": ["workflow:manage"],
        "is_active": True,
    },
    {
        "name": "webhook_sender",
        "display_name": "Webhook Sender",
        "description": "Send HTTP webhooks to external services.",
        "category": "automation",
        "function_schema": {
            "type": "object",
            "required": ["url", "method"],
            "properties": {
                "url": {"type": "string", "description": "Webhook URL"},
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PUT", "DELETE"],
                    "description": "HTTP method",
                },
                "headers": {"type": "object", "description": "HTTP headers"},
                "body": {"type": "object", "description": "Request body"},
            },
        },
        "implementation_type": "internal",
        "implementation_config": {
            "module_path": "src.core.tools.webhook_sender",
            "function_name": "send",
        },
        "required_permissions": ["workflow:manage"],
        "is_active": True,
    },
]
