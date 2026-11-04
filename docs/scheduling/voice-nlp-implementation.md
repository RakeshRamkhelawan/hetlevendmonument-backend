# Voice NLP Implementation Documentation

## Overview

This document describes the complete implementation of the Voice NLP system for the SanskritiSetu Scheduling Core Capability. The system supports both English and Dutch languages for voice-controlled scheduling operations.

**Implementation Phases:**
- **Phase 1**: Basic Entity Extraction (Complete ✓)
- **Phase 2**: Dutch Language Support & Advanced NLP (Complete ✓)

---

## Architecture

```
Voice Input
    ↓
VoiceIntentParser (NLU)
    ├── Intent Classification
    ├── Entity Extraction
    ├── DutchDateNormalizer
    └── ReferenceResolver
    ↓
SchedulingVoiceAgent (OODA Loop)
    ├── Observe: Parse input
    ├── Orient: Validate constraints
    ├── Decide: Choose strategy
    └── Act: Execute & respond
    ↓
CalendarEventRepository
    └── Database operations
```

---

## Components

### 1. DutchDateNormalizer

Normalizes Dutch date/time expressions to concrete datetimes.

**Location**: `src/core/scheduling/voice/nlu.py`

**Supported Expressions:**

| Dutch Expression | English | Result |
|------------------|---------|--------|
| vandaag | today | Current date |
| morgen | tomorrow | Tomorrow's date |
| overmorgen | day after tomorrow | +2 days |
| gisteren | yesterday | -1 day |
| eergisteren | day before yesterday | -2 days |
| ochtend | morning | 09:00 |
| middag | afternoon | 14:00 |
| vanmiddag | this afternoon | 14:00 |
| namiddag | late afternoon | 15:00 |
| avond | evening | 18:00 |
| nacht | night | 20:00 |
| morgenochtend | tomorrow morning | Tomorrow 09:00 |
| maandag-zondag | Monday-Sunday | Next occurrence |
| volgende week | next week | +7 days |
| komende week | coming week | +7 days |

**Usage:**
```python
from src.core.scheduling.voice.nlu import DutchDateNormalizer

normalizer = DutchDateNormalizer()
date, time = normalizer.normalize("morgenochtend")
# Returns: (tomorrow's date, 09:00)
```

---

### 2. ReferenceResolver

Resolves references like "de 1-op-1 met de CTO" to specific calendar events.

**Location**: `src/core/scheduling/voice/nlu.py`

**Features:**
- Extracts meeting types: "1-op-1", "1:1", "team meeting", "standup"
- Extracts roles: CTO, CEO, CFO, COO, manager, director
- Searches upcoming events (30 days)
- Returns best match with confidence score

**Usage:**
```python
from src.core.scheduling.voice.nlu import ReferenceResolver

resolver = ReferenceResolver(db)
result = await resolver.resolve_event_reference(
    "de 1-op-1 met de CTO",
    user_id="user-123",
    tenant_id=1
)
# Returns: {"event_id": "...", "title": "...", "confidence": 2.0}
```

---

### 3. VoiceIntentParser

Main NLU parser that handles intent classification and entity extraction.

**Location**: `src/core/scheduling/voice/nlu.py`

**Supported Intents:**

| Intent | English Patterns | Dutch Patterns |
|--------|-----------------|----------------|
| SCHEDULE_MEETING | schedule/book/plan a meeting | plan/maak/zet een afspraak |
| RESCHEDULE_MEETING | reschedule/move/change meeting | verplaats/verzet/wijzig |
| CANCEL_MEETING | cancel/delete/remove meeting | annuleer/verwijder/afgelasten |
| CHECK_AVAILABILITY | when available/check availability | wanneer beschikbaar/vrije tijd |
| LIST_MEETINGS | what meetings/show my meetings | wat staat op agenda/afspraken |
| SUGGEST_TIMES | suggest times/when should we meet | suggesteer tijden |
| BLOCK_FOCUS_TIME | block focus time | blokkeer focus tijd |

**Entity Extraction:**
- **Participants**: "with Alice", "met de CTO"
- **Dates**: "tomorrow", "morgen", "next week", "volgende week"
- **Times**: "3pm", "vanmiddag", "morning", "ochtend"
- **Durations**: "30 minutes", "een uur", "half hour", "kwartier"
- **Meeting titles**: "called [title]", "genaamd [titel]"

**Usage:**
```python
from src.core.scheduling.voice.nlu import VoiceIntentParser
from src.core.scheduling.voice.intents import VoiceContext

parser = VoiceIntentParser(db)
context = VoiceContext(user_id="user-123", tenant_id=1)

intent = await parser.parse(
    "Verplaats de 1-op-1 met de CTO van vanmiddag naar morgenochtend",
    context
)
```

---

### 4. SchedulingVoiceAgent

OODA-loop based voice agent for processing scheduling requests.

**Location**: `src/core/scheduling/voice/agent.py`

**OODA Loop:**
1. **Observe**: Parse voice input, extract entities
2. **Orient**: Determine intent, validate constraints, check confidence
3. **Decide**: Choose execution strategy (execute/confirm/clarify)
4. **Act**: Execute scheduling operation, generate response

**Actions:**
- `create_meeting`: Schedule new meeting
- `reschedule_meeting`: Move existing meeting
- `cancel_meeting`: Cancel meeting
- `check_availability`: Query free times
- `list_meetings`: Show upcoming meetings

---

## API Endpoints

### Voice Processing

#### POST /api/v1/scheduling/voice/process
Process voice input and return scheduling response.

**Request:**
```json
{
  "transcript": "Schedule a meeting with John tomorrow at 2pm",
  "session_id": "optional-session-id",
  "timezone": "UTC"
}
```

**Response:**
```json
{
  "success": true,
  "response_text": "I'll schedule a meeting with John for tomorrow at 2 PM for 30 minutes. Sound good?",
  "action_taken": "confirm",
  "requires_follow_up": true,
  "intent": "schedule_meeting",
  "entities": {
    "participants": ["John"],
    "date_expression": "tomorrow",
    "time_expression": "2pm",
    "duration_minutes": 30
  },
  "session_id": "session-id",
  "suggested_responses": ["Yes", "No", "Change the time"]
}
```

#### POST /api/v1/scheduling/voice/confirm
Confirm a pending action.

**Request:**
```json
{
  "session_id": "session-id",
  "confirmed": true
}
```

#### DELETE /api/v1/scheduling/voice/session/{session_id}
End voice session.

#### GET /api/v1/scheduling/voice/health
Health check with Redis status.

#### GET /api/v1/scheduling/voice/intents
List available voice intents.

---

## Use Cases

### Use-Case 1: Executive Assistant (Complete ✓)

**Scenario**: Reschedule a 1:1 meeting with the CTO

**Dutch Command:**
```
"Verplaats de 1-op-1 met de CTO van vanmiddag naar morgenochtend"
```

**Processing:**
1. Intent: RESCHEDULE_MEETING ("verplaats")
2. Reference: "de 1-op-1 met de CTO" → finds meeting
3. From date: "vanmiddag" → today 14:00
4. To date: "morgenochtend" → tomorrow 09:00
5. Action: Reschedule meeting

**Response:**
```
"Ik heb de '1-op-1 with CTO' verplaatst van [vandaag] naar [morgen]."
```

---

## Test Suite

### Comprehensive Integration Tests

**Location**: `tests/integration/scheduling/`

#### test_voice_comprehensive_integration.py (21 tests)
- Dutch date normalizer (all expressions)
- Voice intent parser (English & Dutch)
- API integration (full flows)
- Session store operations
- Reference resolution with DB

#### test_voice_dutch.py (16 tests)
- Dutch date normalization
- Dutch intent recognition
- Dutch entity extraction
- End-to-end Dutch API tests

#### test_voice_integration.py (23 tests)
- Basic voice processing
- Session management
- Conversational flows
- Entity extraction
- Error handling

### Test Results

| Suite | Tests | Status |
|-------|-------|--------|
| Comprehensive | 21/21 | ✅ Pass |
| Dutch | 16/16 | ✅ Pass |
| Integration | 23/23 | ✅ Pass |
| **Total** | **60/60** | **✅ 100%** |

### Running Tests

```bash
# All voice tests
python -m pytest tests/integration/scheduling/ -k voice -v

# Dutch tests only
python -m pytest tests/integration/scheduling/test_voice_dutch.py -v

# Comprehensive tests
python -m pytest tests/integration/scheduling/test_voice_comprehensive_integration.py -v
```

---

## Configuration

### Environment Variables

```bash
# Database (required for integration tests)
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5435/sanskritisetu

# Redis (optional, falls back to local storage)
REDIS_URL=redis://localhost:6379/0

# Feature flag
FEATURE_FLAG_VOICE_SCHEDULING=true
```

### Session Store

Uses Redis-backed session store with local fallback for development:
- **TTL**: 1 hour (3600 seconds)
- **Fallback**: Local in-memory storage
- **Persistence**: Across requests, not across server restarts

---

## Examples

### Example 1: Schedule Meeting (English)

```bash
curl -X POST "http://localhost:8000/api/v1/scheduling/voice/process" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "transcript": "Schedule a meeting with Alice tomorrow at 3pm for 45 minutes",
    "session_id": "my-session",
    "timezone": "Europe/Amsterdam"
  }'
```

### Example 2: Reschedule Meeting (Dutch)

```bash
curl -X POST "http://localhost:8000/api/v1/scheduling/voice/process" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "transcript": "Verplaats mijn meeting met Bob naar vrijdagmiddag",
    "timezone": "Europe/Amsterdam"
  }'
```

### Example 3: Cancel Meeting

```bash
curl -X POST "http://localhost:8000/api/v1/scheduling/voice/process" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "transcript": "Cancel my team standup"
  }'
```

### Example 4: Check Availability

```bash
curl -X POST "http://localhost:8000/api/v1/scheduling/voice/process" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "transcript": "When am I free tomorrow?"
  }'
```

---

## Implementation Details

### Date/Time Parsing Logic

1. **DutchDateNormalizer.normalize(text)**:
   - Match relative dates with regex (word boundaries)
   - Match time periods (sorted by length, longest first)
   - Handle combined expressions ("morgenochtend")
   - Return (date, time) tuple

2. **VoiceIntentParser.parse_date_expression()**:
   - Try Dutch normalization first
   - Fall back to English expressions
   - Return datetime object

3. **VoiceIntentParser.resolve_relative_date()**:
   - Combine date and time expressions
   - Return concrete datetime
   - Handle timezone

### Intent Classification

1. Compile regex patterns for each intent
2. Search transcript for pattern matches
3. Calculate confidence based on match quality
4. Fallback to keyword detection for simple matches

### Entity Extraction

1. **Participants**: Pattern matching for "with/met [Name]"
2. **Dates**: Regex for date expressions
3. **Times**: Regex for time expressions + Dutch periods
4. **Durations**: Pattern matching with multipliers
5. **Titles**: Pattern matching for "called/about/genaamd/over"

---

## Future Enhancements

### Phase 3: Complex Constraints (Planned)
- RRULE parsing for recurring meetings
- Team/department entity resolution
- Time window constraints ("find 2 hours in the afternoon")
- Travel buffer calculation

### Phase 4: Advanced Features (Planned)
- Multi-language support (French, German)
- Context-aware disambiguation
- Natural language generation improvements
- Voice response optimization

---

## Troubleshooting

### Common Issues

**Issue**: Dutch expressions not recognized
**Solution**: Check word boundaries in regex patterns

**Issue**: Reference resolution fails
**Solution**: Ensure events exist in database with matching keywords

**Issue**: Session not persisting
**Solution**: Check Redis connection or use local fallback

### Debug Logging

Enable debug logging:
```python
import logging
logging.getLogger("src.core.scheduling.voice").setLevel(logging.DEBUG)
```

---

## References

- **Main Module**: `src/core/scheduling/voice/`
- **NLU**: `src/core/scheduling/voice/nlu.py`
- **Agent**: `src/core/scheduling/voice/agent.py`
- **API Routes**: `src/core/scheduling/api/voice_routes.py`
- **Tests**: `tests/integration/scheduling/test_voice_*.py`

---

## Changelog

### Phase 1 - Basic Entity Extraction
- ✅ Intent classification (7 intents)
- ✅ Entity extraction (participants, dates, times, durations)
- ✅ Session store (Redis + local fallback)
- ✅ API endpoints (process, confirm, health, intents)
- ✅ OODA loop agent implementation

### Phase 2 - Dutch Language Support
- ✅ DutchDateNormalizer class
- ✅ ReferenceResolver class
- ✅ Dutch intent patterns (40+ patterns)
- ✅ Dutch entity patterns (30+ patterns)
- ✅ Relative date parsing (vandaag, morgen, overmorgen)
- ✅ Time period parsing (ochtend, middag, avond)
- ✅ Comprehensive test suite (60 tests)

### Code Review Fixes
- ✅ Fixed regex word boundaries for time matching
- ✅ Added type hints for database parameters
- ✅ Removed duplicate timezone imports
- ✅ Verified time format consistency (%I:%M %p)

---

**Document Version**: 1.0
**Last Updated**: March 21, 2026
**Status**: Complete (Phase 1 & 2)
