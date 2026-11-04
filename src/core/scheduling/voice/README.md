# Voice Scheduling Module

Voice-controlled scheduling for SanskritiSetu using Natural Language Understanding (NLU).

## Quick Start

```python
from src.core.scheduling.voice.agent import SchedulingVoiceAgent
from src.core.scheduling.voice.intents import VoiceContext

# Initialize agent
agent = SchedulingVoiceAgent(tenant_id=1, db=db_session)

# Create context
context = VoiceContext(
    user_id="user-123",
    tenant_id=1,
    timezone="Europe/Amsterdam"
)

# Process voice input
result = await agent.process_voice_input(
    "Schedule a meeting with Alice tomorrow at 2pm",
    context
)

print(result.response_text)
```

## Module Structure

```
voice/
├── __init__.py
├── agent.py          # OODA loop voice agent
├── intents.py        # Intent definitions & context
├── nlu.py           # Natural Language Understanding
├── session_store.py  # Redis-backed session storage
└── README.md        # This file
```

## Supported Languages

- **English**: Full support for all operations
- **Dutch**: Full support for all operations

## Supported Operations

### 1. Schedule Meeting
```
English: "Schedule a meeting with John tomorrow at 3pm"
Dutch:   "Plan een meeting met John morgen om 3 uur"
```

### 2. Reschedule Meeting
```
English: "Move my meeting to Friday"
Dutch:   "Verplaats mijn meeting naar vrijdag"
```

### 3. Cancel Meeting
```
English: "Cancel my team standup"
Dutch:   "Annuleer mijn team standup"
```

### 4. Check Availability
```
English: "When am I free tomorrow?"
Dutch:   "Wanneer ben ik vrij morgen?"
```

### 5. List Meetings
```
English: "What meetings do I have today?"
Dutch:   "Welke afspraken heb ik vandaag?"
```

## Dutch Date/Time Expressions

### Relative Dates
- `vandaag` - today
- `morgen` - tomorrow
- `overmorgen` - day after tomorrow
- `gisteren` - yesterday
- `volgende week` - next week

### Time Periods
- `ochtend` / `morgenochtend` - morning (9:00)
- `middag` / `vanmiddag` - afternoon (14:00)
- `namiddag` - late afternoon (15:00)
- `avond` - evening (18:00)
- `nacht` - night (20:00)

### Weekdays
- `maandag` through `zondag` - Monday through Sunday

## API Endpoints

See full API documentation in: `docs/scheduling/voice-nlp-implementation.md`

Key endpoints:
- `POST /api/v1/scheduling/voice/process` - Process voice input
- `POST /api/v1/scheduling/voice/confirm` - Confirm pending action
- `GET /api/v1/scheduling/voice/health` - Health check
- `GET /api/v1/scheduling/voice/intents` - List available intents

## Testing

Run voice tests:
```bash
# All voice tests
pytest tests/integration/scheduling/ -k voice -v

# Dutch tests
pytest tests/integration/scheduling/test_voice_dutch.py -v

# Comprehensive tests
pytest tests/integration/scheduling/test_voice_comprehensive_integration.py -v
```

## Configuration

Environment variables:
```bash
# Redis (optional, falls back to local)
REDIS_URL=redis://localhost:6379/0

# Feature flag
FEATURE_FLAG_VOICE_SCHEDULING=true
```

## Implementation Status

| Feature | Status |
|---------|--------|
| Intent Classification | ✅ Complete |
| Entity Extraction | ✅ Complete |
| Dutch Language Support | ✅ Complete |
| Reference Resolution | ✅ Complete |
| Session Management | ✅ Complete |
| API Endpoints | ✅ Complete |
| Integration Tests | ✅ 60/60 Passing |
| Code Review | ✅ Approved (A-) |

## Architecture

This module uses the OODA loop pattern:
1. **Observe**: Parse voice input
2. **Orient**: Validate & determine approach
3. **Decide**: Choose execution strategy
4. **Act**: Execute & generate response

See `docs/scheduling/voice-nlp-implementation.md` for detailed architecture documentation.
