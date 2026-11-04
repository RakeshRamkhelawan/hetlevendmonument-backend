"""Expliciete weigering voor agent-besturingsknoppen die geen mechanisme achter zich hebben.

ADR-036 golf 1 WS1 (2026-08-31). `pause`, `resume` en `restart` schreven een logregel en
retourneerden `{"status": "success"}` zonder een agent, wachtrij of circuit breaker aan te raken.
Een toezichtsknop die altijd slaagt en nooit werkt is misleidender dan geen knop.

Waarom hier geen echte pauze staat, gemeten en niet aangenomen. Er zijn TWEE kandidaten en geen
van beide is een operator-hold:

1. `AgentCircuitBreaker` (`src/core/als/infrastructure/agent_circuit_breaker.py`). Openen kan
   alleen via de private `_open_circuit()`, en die zet `last_failure_time = now`, waarna `allow()`
   (`:86-93`) het circuit zelf naar HALF_OPEN draait zodra `reset_timeout_seconds` verstreken is --
   default 30 seconden (`agent_circuit_breaker.py:31`, doorgegeven vanuit `agent_runner.py:18`;
   `agent_runner.py:39` geeft de waarde alleen door en is dus niet de bron). Een pauze via die weg
   zou na een halve minuut stil vervallen. De breker wordt bovendien op precies een plek
   geraadpleegd: `agent_runner.py:82`.
2. `AgentConfig.is_active` (`src/core/models/agent_config.py:20`), per (tenant, agent) persistent
   en al muteerbaar via `PATCH /api/v1/agent_configs/{agent_id}`
   (`src/core/api/v1/agent_configs/router.py:87`). Ook onbruikbaar als hold: `AgentRunner.start()`
   laadt de actieve configs EENMALIG (`agent_runner.py:52`) en de lus daarna herleest ze nooit,
   dus een agent die al draait stopt niet door de vlag om te zetten.

En het argument dat boven beide uit gaat: **de pacemaker draait niet.** `git grep "AgentRunner("`
over `src/` en `scripts/` geeft nul treffers -- de klasse wordt in productiecode nergens
geinstantieerd -- en `agent_runner` komt in geen `docker-compose*.yml` en in geen workflow voor.
Ook een correct geopend circuit zou dus door niemand worden gelezen. Een echte pauze vereist een
nieuw, duurzaam hold-mechanisme plus een proces dat het raadpleegt; dat is een ontwerpbeslissing,
geen bijvangst van deze fix.

Tot dat mechanisme bestaat is fail-loud het eerlijke antwoord -- dezelfde afweging als OP-74:
liever expliciet weigeren dan stil doen alsof.

**Welke body de client feitelijk krijgt, gemeten op een app met `register_exception_handlers`.**
Niet de vorm die hieronder in `detail` staat: `src/core/exceptions/handlers.py:72-82` stopt het
hele dict-detail in `error.message`, dus top-level is het antwoord
`{"error": {"error_code": "HTTP_ERROR", "message": <dit detail>, ...}, "detail": <dit detail>}`.
Een client leest de foutcode dus op `body.detail.error.code`, niet op `body.error.code`. Dat is
bestaand platformgedrag en geldt voor elke `HTTPException` met een dict-detail (de precedent op
`src/core/api/v1/analytics/agents.py:37` heeft het ook); het staat hier opgeschreven omdat de
gedocumenteerde projectvorm `{"success": False, "error": {...}}` daarmee niet is wat er over de
lijn gaat.

Deze module importeert bewust alleen fastapi en logging, zodat zowel de geserveerde router
(`v1/management/agents_router.py`) als de legacy flat module (`management_endpoints.py`) hem kan
gebruiken zonder importcyclus.
"""

from __future__ import annotations

import logging
from typing import NoReturn

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

ERROR_CODE = "AGENT_CONTROL_NOT_IMPLEMENTED"

#: OpenAPI-beschrijving voor de 501 die `refuse_agent_control` altijd oplevert.
#:
#: Een gedeelde constante en geen zes kopieen. De tekst stond zes keer letterlijk in twee
#: routerbestanden; een correctie had dan op vijf plekken vergeten kunnen worden, en dat is
#: precies hoe de drie definities van "admin" in dit project uit elkaar zijn gelopen (OP-40).
#:
#: Engels, net als de rest van de OpenAPI in deze twee routers ("Get all agents status",
#: "Pause an agent"). De eerste versie was Nederlands en maakte de gepubliceerde specificatie
#: tweetalig -- een clientontwikkelaar leest dan de helft van de beschrijvingen in een taal
#: die hij niet hoeft te kennen.
UNAVAILABLE_RESPONSES: dict[int | str, dict[str, str]] = {
    status.HTTP_501_NOT_IMPLEMENTED: {
        "description": (
            "Agent control is not implemented. There is no durable per-agent hold mechanism, "
            "so this endpoint refuses instead of confirming an action it does not perform "
            "(ADR-036 OP-178)."
        )
    }
}


_MESSAGE = (
    "Agent {action} is not implemented. There is no durable per-agent hold mechanism yet, so this "
    "endpoint cannot stop, resume or restart agent '{agent_id}'. It refuses instead of confirming "
    "an action it does not perform (ADR-036 golf 1 WS1)."
)


def refuse_agent_control(action: str, agent_id: str, requested_by: str) -> NoReturn:
    """Weiger een besturingsactie met 501 in plaats van een ongedekt succes te melden.

    Args:
        action: de gevraagde actie, in de melding gebruikt ("pause", "resume", "restart").
        agent_id: de agent uit het pad; wordt alleen gelogd en teruggegeven, niet geresolved.
        requested_by: het GEBRUIKERSNUMMER van de aanvrager, niet zijn e-mailadres. Bewust geen
            PII: `.claude/rules/security.md` verbiedt persoonsgegevens in logs, en deze waarde
            gaat uitsluitend naar de applicatielog (regel hieronder) -- er is hier GEEN
            audit-entry, dus noem het ook geen auditspoor.

    Waarom een applicatielog hier volstaat en er geen audit-entry hoort, gevraagd in Gate 2
    (2026-08-31). Een 501 is GEEN autorisatiebesluit: de aanroeper is al door
    `require_scopes(OAuth2Scope.ADMIN_ALL)` gekomen voordat deze functie draait, dus er is geen
    weigering van rechten om vast te leggen -- alleen een functie die niet bestaat. De
    audit-keten van ADR-019 legt besluiten en gegevensmutaties vast; een onveranderde toestand
    plus een 501 is geen van beide. Zodra er wel een echt hold-mechanisme is, verandert dat:
    een geslaagde pauze is wel een besluit met effect en hoort dan wel in de audit-keten. Deze
    module heeft daar vandaag ook geen middelen voor -- ze importeert bewust alleen fastapi en
    logging (zie de modulekop) en de zes handlers krijgen geen DB-sessie.

    Raises:
        HTTPException: altijd, met status 501.
    """
    logger.warning(
        "agent_control_refused_not_implemented action=%s agent_id=%s requested_by=%s",
        action,
        agent_id,
        requested_by,
    )
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={
            "success": False,
            "error": {
                "code": ERROR_CODE,
                "message": _MESSAGE.format(action=action, agent_id=agent_id),
                "details": {"agent_id": agent_id, "action": action},
            },
        },
    )
