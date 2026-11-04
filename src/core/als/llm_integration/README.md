# ALS LLM Integration

LLM integration for the Agent Learning System (ALS), enabling AI-powered agents in swarms.

## Features

- **Multi-Provider Support**: DeepSeek and Gemini (Google)
- **Automatic Model Selection**: Gemini provider automatically selects the latest available model
- **Fallback Support**: If a model fails, automatically tries alternative models
- **Agent Personas**: Role-based system prompts for different swarm roles
- **GDPR Compliant**: All interactions are logged with data minimization

## Supported Models

### DeepSeek
- `deepseek-chat` (default)

### Gemini (Auto-Selection)
Priority order (newest first):
1. `gemini-2.0-flash-exp` - Latest experimental
2. `gemini-2.0-flash` - Latest stable
3. `gemini-1.5-pro` - High quality
4. `gemini-1.5-flash` - Fast & economical
5. `gemini-1.5-pro-latest` - Fallback
6. `gemini-1.0-pro` - Legacy

## Quick Start

```python
from src.core.als.swarm import SwarmOrchestrator, SwarmRole
from src.core.als.llm_integration import LLMAgentAdapter

# Initialize
swarm = SwarmOrchestrator(tenant_id=999)
llm = LLMAgentAdapter(swarm, provider_name="deepseek")

# Register agent with role
await llm.register_agent(
    agent_id="conservator_01",
    role=SwarmRole.LEADER,
    specialization="manuscript_restoration"
)

# Execute task with AI
result = await llm.execute_task(
    agent_id="conservator_01",
    task=task_data,
    context={"artifact": "15th century manuscript"}
)

print(result.result_data["detailed_output"])
```

## Provider Selection

### DeepSeek (Recommended - Working)
```python
llm = LLMAgentAdapter(swarm, provider_name="deepseek")
```

### Gemini (Auto-Select Latest Model)
```python
# Auto-select best available model
llm = LLMAgentAdapter(swarm, provider_name="gemini")

# Or specify specific model
from src.core.als.llm_integration import GeminiProvider
provider = GeminiProvider(model="gemini-2.0-flash")
llm = LLMAgentAdapter(swarm, provider=provider)
```

## Environment Variables

```bash
# DeepSeek
DEEPSEEK_API_KEY=sk-your-key

# Gemini
GOOGLE_API_KEY=your-key
```

## Agent Personas

Built-in personas for swarm roles:
- **LEADER**: Coordinates team, makes decisions
- **STRATEGIST**: Plans approach, analyzes situation
- **EXECUTOR**: Performs restoration work
- **REVIEWER**: Quality-checks all work
- **SPECIALIST**: Deep expertise in specific areas
- **SUPPORT**: Assists and enables team

## Testing

### Test API Keys
```bash
python tests/als/live_demo/test_llm_apis.py
```

### Test Gemini Model Selection
```bash
python tests/als/live_demo/test_gemini_models.py
```

### Full ALS+LLM Demo
```bash
python tests/als/live_demo/als_llm_demo.py
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    SWARM ORCHESTRATOR                        │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐    │
│  │  Leader     │  │  Strategist  │  │  Executor       │    │
│  │  (LLM)      │  │  (LLM)       │  │  (LLM)          │    │
│  └──────┬──────┘  └──────┬───────┘  └────────┬────────┘    │
└─────────┼────────────────┼───────────────────┼─────────────┘
          │                │                   │
          └────────────────┴───────────────────┘
                           │
                  ┌────────┴────────┐
                  │  LLM ADAPTER    │
                  │  - Personas     │
                  │  - Prompt gen   │
                  │  - Result parse │
                  └────────┬────────┘
                           │
            ┌──────────────┼──────────────┐
            │              │              │
       ┌────┴────┐   ┌────┴────┐   ┌────┴────┐
       │DEEPSEEK │   │GEMINI   │   │GEMINI   │
       │API      │   │2.0-flash│   │1.5-pro  │
       └─────────┘   └─────────┘   └─────────┘
```

## API Status

| Provider | Status | Notes |
|----------|--------|-------|
| DeepSeek | ✅ Working | Fully functional |
| Gemini 2.0 | ❌ API Key Invalid | Need valid API key |
| Gemini 1.5 | ❌ API Key Invalid | Need valid API key |

## Dependencies

```bash
# Required
pip install requests

# For Gemini (new, recommended)
pip install google-genai

# For Gemini (legacy fallback)
pip install google-generativeai
```

## GDPR Compliance

- All agent IDs are pseudonymized (SHA-256 hashed)
- Audit trail with minimal data retention
- No PII stored in logs
- 30-day retention policy

## Future Enhancements

- [ ] Add OpenAI GPT-4 support
- [ ] Add Claude (Anthropic) support
- [ ] Streaming responses
- [ ] Multi-modal input (images)
- [ ] Fine-tuned models for cultural heritage
