# Sanskriti Backend

Extracted from stichting-backend-ai project.

## Structure

```text
sanskriti-backend/
├── core/                 # Core backend functionality
│   ├── api/             # FastAPI endpoints
│   ├── auth/            # Authentication & RBAC
│   ├── database/        # Database layer
│   ├── collaboration/   # Agent coordination
│   ├── autonomy/        # Autonomous agents
│   └── ...
├── agents/              # Agent modules
│   ├── knowledge_agent/
│   ├── sentiment_agent/
│   ├── diagnostics_agent/
│   └── translation_agent/
├── main.py             # Application entry point
└── config.py           # Configuration

```text

## Setup

1. Create virtual environment:

   ```bash

   python -m venv venv
   source venv/bin/activate  # or venv\Scripts\activate on Windows
```python

2. Install dependencies:

   ```bash

   pip install -r requirements.txt
```bash

3. Configure environment:

   ```bash

   cp .env.example .env

   # Edit .env with your settings

```bash

4. Run database migrations:

   ```bash

   alembic upgrade head
```bash

5. Start the server:

   ```bash

   python main.py
```python

## Testing

```bash

pytest tests/ -v
```bash

## Migration Notes

This codebase was extracted from stichting-backend-ai on $(date +%Y-%m-%d).

Changes made:

- Copied core/ directory (309 files)
- Copied 4 required agent directories (34 files)
- Fixed hardcoded paths in mcp_client.py
- Updated package references in config files

## Known Issues

1. Circular dependency between core/auth/rbac.py and core/api/auth_endpoints.py
   - Workaround: Uses lazy imports
   - TODO: Refactor to break cycle

2. Requires agents/ directory for task_distributor.py
   - Required agents are included in this extraction
