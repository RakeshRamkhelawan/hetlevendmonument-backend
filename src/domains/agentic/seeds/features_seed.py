from typing import Any

"""
Platform Features Seed Data

Matches Feature model fields exactly:
- id (String, PK)
- name (String, required)
- description (Text, required)
- category (String, required)
- icon, color (optional)
- keywords, example_queries, capabilities (JSON, optional)
- intent_keywords, route_patterns, domain_context (optional)
- is_active (Boolean)
"""

PLATFORM_FEATURES: list[dict[str, Any]] = [  # TODO(TYPE): replace Any with concrete type
    {
        "id": "assistant",
        "name": "General Assistant",
        "description": "A helpful AI assistant for general questions and tasks. Provides informative responses, explains concepts, and helps with research.",
        "category": "knowledge_mgmt",
        "icon": "message-circle",
        "color": "#3B82F6",
        "keywords": ["help", "question", "explain", "assist", "general"],
        "example_queries": [
            "How do I reset my password?",
            "What is machine learning?",
            "Help me understand this concept",
        ],
        "capabilities": ["answer_questions", "explain_concepts", "provide_guidance"],
        "intent_keywords": {
            "en": ["help", "question", "what is", "how to", "explain"],
            "nl": ["help", "vraag", "wat is", "hoe kan", "uitleg"],
        },
        "route_patterns": ["/chat", "/assistant"],
        "domain_context": None,
        "is_active": True,
    },
    {
        "id": "content_writer",
        "name": "Content Writer",
        "description": "Professional content creation for blogs, articles, marketing copy, and social media. Adapts tone and style to target audience.",
        "category": "content_creation",
        "icon": "edit-3",
        "color": "#10B981",
        "keywords": ["write", "blog", "article", "content", "copy", "marketing"],
        "example_queries": [
            "Write a blog post about AI trends",
            "Create social media content for our product launch",
            "Draft an email newsletter",
        ],
        "capabilities": ["blog_posts", "social_media", "email_copy", "seo_content"],
        "intent_keywords": {
            "en": ["write", "create", "draft", "compose", "blog", "article"],
            "nl": ["schrijf", "maak", "opstellen", "blog", "artikel"],
        },
        "route_patterns": ["/content", "/writer"],
        "domain_context": None,
        "is_active": True,
    },
    {
        "id": "code_assistant",
        "name": "Code Assistant",
        "description": "Programming help for all skill levels. Code generation, debugging, code review, and technical documentation.",
        "category": "code_dev",
        "icon": "code",
        "color": "#8B5CF6",
        "keywords": ["code", "programming", "debug", "develop", "script"],
        "example_queries": [
            "Write a Python function to parse JSON",
            "Debug this JavaScript error",
            "Review my code for best practices",
        ],
        "capabilities": [
            "code_generation",
            "debugging",
            "code_review",
            "documentation",
        ],
        "intent_keywords": {
            "en": ["code", "program", "debug", "function", "script", "develop"],
            "nl": ["code", "programmeer", "debug", "functie", "script"],
        },
        "route_patterns": ["/code", "/dev"],
        "domain_context": None,
        "is_active": True,
    },
    {
        "id": "data_analyst",
        "name": "Data Analyst",
        "description": "Data analysis and visualization. Transform raw data into actionable insights with charts, statistics, and reports.",
        "category": "data_analytics",
        "icon": "bar-chart-2",
        "color": "#F59E0B",
        "keywords": ["data", "analysis", "chart", "statistics", "report", "visualize"],
        "example_queries": [
            "Analyze this dataset for trends",
            "Create a chart showing monthly sales",
            "Generate a statistical report",
        ],
        "capabilities": ["data_analysis", "visualization", "statistics", "reporting"],
        "intent_keywords": {
            "en": ["analyze", "data", "chart", "graph", "statistics", "report"],
            "nl": ["analyseer", "data", "grafiek", "statistieken", "rapport"],
        },
        "route_patterns": ["/data", "/analytics"],
        "domain_context": None,
        "is_active": True,
    },
    {
        "id": "workflow_builder",
        "name": "Workflow Builder",
        "description": "Automation design and implementation. Create, manage, and optimize automated workflows and business processes.",
        "category": "system_ops",
        "icon": "git-branch",
        "color": "#EC4899",
        "keywords": ["workflow", "automation", "process", "integrate", "schedule"],
        "example_queries": [
            "Create an automation that sends daily reports",
            "Build a workflow for customer onboarding",
            "Set up a scheduled data sync",
        ],
        "capabilities": ["workflow_design", "automation", "scheduling", "integration"],
        "intent_keywords": {
            "en": ["workflow", "automate", "schedule", "trigger", "process"],
            "nl": ["workflow", "automatiseer", "schema", "trigger", "proces"],
        },
        "route_patterns": ["/workflows", "/automation"],
        "domain_context": "workflows",
        "is_active": True,
    },
    {
        "id": "summarizer",
        "name": "Document Summarizer",
        "description": "Intelligent summarization of documents, articles, and long texts. Extract key points and generate concise summaries.",
        "category": "knowledge_mgmt",
        "icon": "file-text",
        "color": "#06B6D4",
        "keywords": ["summarize", "summary", "tldr", "digest", "condense"],
        "example_queries": [
            "Summarize this 50-page report",
            "Give me the key points from this article",
            "Create an executive summary",
        ],
        "capabilities": ["text_summarization", "key_extraction", "digest_creation"],
        "intent_keywords": {
            "en": ["summarize", "summary", "key points", "tldr", "brief"],
            "nl": ["samenvatten", "samenvatting", "hoofdpunten", "kort"],
        },
        "route_patterns": ["/summarize"],
        "domain_context": None,
        "is_active": True,
    },
    {
        "id": "translator",
        "name": "Translator",
        "description": "Multi-language translation with cultural context awareness. Translate text while preserving meaning and tone.",
        "category": "content_creation",
        "icon": "globe",
        "color": "#14B8A6",
        "keywords": ["translate", "language", "localize", "convert"],
        "example_queries": [
            "Translate this email to Dutch",
            "Convert this document to Spanish",
            "Localize this content for the German market",
        ],
        "capabilities": ["translation", "localization", "cultural_adaptation"],
        "intent_keywords": {
            "en": ["translate", "convert", "language", "localize"],
            "nl": ["vertaal", "converteer", "taal", "lokaliseer"],
        },
        "route_patterns": ["/translate"],
        "domain_context": None,
        "is_active": True,
    },
    {
        "id": "image_generator",
        "name": "Image Generator",
        "description": "AI-powered image creation and editing. Generate images from text descriptions and perform image manipulation.",
        "category": "content_creation",
        "icon": "image",
        "color": "#A855F7",
        "keywords": ["image", "generate", "picture", "visual", "create"],
        "example_queries": [
            "Generate an image of a sunset over mountains",
            "Create a logo concept for my business",
            "Design a banner for social media",
        ],
        "capabilities": ["image_generation", "image_editing", "visual_design"],
        "intent_keywords": {
            "en": ["image", "picture", "generate", "create visual", "design"],
            "nl": ["afbeelding", "plaatje", "genereer", "visueel", "ontwerp"],
        },
        "route_patterns": ["/images", "/generate"],
        "domain_context": None,
        "is_active": True,
    },
]
