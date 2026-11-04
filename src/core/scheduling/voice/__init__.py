"""
Voice UI module for hands-free scheduling.

Provides natural language voice interface for calendar operations
using the OODA loop decision pattern.
"""

from src.core.scheduling.voice.agent import SchedulingVoiceAgent
from src.core.scheduling.voice.intents import VoiceIntent, VoiceIntentType
from src.core.scheduling.voice.nlu import VoiceIntentParser

__all__ = [
    "SchedulingVoiceAgent",
    "VoiceIntent",
    "VoiceIntentType",
    "VoiceIntentParser",
]
