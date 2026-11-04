"""Een dubbel voor `_get_llm_service()`, dat sinds BE-LLM-004 ASYNC is.

**Waarom deze helper bestaat en niet vijf keer een lambda.** `BaseSpecialistAgent._get_llm_service()`
was synchroon en werd in de tests vervangen met `agent._get_llm_service = lambda: dubbel`. Sinds
fase 2b haalt die methode de providerketen van de tenant op en is hij dus async; de aanroepplek
doet `await (await self._get_llm_service()).generate(...)`. Een synchrone lambda levert daar een
object op dat niet te awaiten is, en dat faalt met `TypeError: object LLMService can't be used in
'await' expression` -- een melding die niets zegt over de oorzaak.

Vijf testbestanden vervingen die methode op dezelfde manier. Een gedeelde helper houdt ze gelijk;
wie de handtekening ooit weer wijzigt, past EEN plek aan in plaats van vijf die stil uit elkaar
kunnen lopen.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def als_async(dubbel: Any) -> Callable[[], Any]:  # TODO(TYPE): replace Any with concrete type
    """Geef een async functie terug die `dubbel` oplevert.

    Geen `AsyncMock(return_value=...)`: die telt aanroepen en nodigt uit tot asserties op het
    dubbel zelf in plaats van op het gedrag. Deze vorm doet precies een ding.
    """

    async def _lever() -> Any:  # TODO(TYPE): replace Any with concrete type
        return dubbel

    return _lever
