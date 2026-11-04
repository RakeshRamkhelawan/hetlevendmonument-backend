"""`_check_all_agents` mag de tenant-lock niet opnieuw pakken (ADR-036 OP-195).

**De bevinding, gemeten door uitvoering op 2026-09-02 en niet door de code te lezen.**
`AgentLifecycleManager._check_all_agents()` hield `self._locks[tenant_id]` vast en riep binnen
dat blok `unregister_agent()` aan, die dezelfde lock opnieuw nam. `asyncio.Lock` is niet
reentrant, dus de coroutine wachtte op een lock die hij zelf vasthield: geen fout, geen timeout,
permanent. Het pad wordt betreden zodra een agent langer offline is dan
`MAX_OFFLINE_TIME_SECONDS`, en omdat `_health_monitor_loop` deze functie in zijn lus await,
stopte daarmee de agent-gezondheidsbewaking voor het hele proces -- stil.

**Waarom deze test hier staat en niet bij `tests/enterprise/agents/test_agent_lifecycle.py`.**
Die map draait in GEEN ENKELE CI-stap (de blokkerende poort draait `tests/unit`,
`tests/architecture`, `tests/core`, `tests/contracts` plus sinds 2026-09-07 `tests/safety` en
`tests/ml`). Een regressietest daar bewaakt niets -- dat is precies het patroon van OP-11
(`tests/core`), OP-54 en OP-180 (`tests/contracts`). De bestaande test in die map
(`TestAgentHealthMonitoring::test_auto_unregister_after_extended_offline`) HING op deze bug en
is bij de fix als onafhankelijke tweede meting gebruikt, maar hij is geen poort.

**Geen hang, altijd een failure.** Elke aanroep van `_check_all_agents()` staat in een
`asyncio.wait_for`. De poort draait `-x -n 2` met `timeout_method = "thread"`: daar neemt een
hangende test het HELE workerproces mee en rapporteert pytest een willekeurige andere test als
FAILED. Een regressie moet hier dus een `TimeoutError` geven en geen stilstand.

**`start()` wordt bewust niet aangeroepen.** De monitorlus is als oorzaak al uitgesloten (de
functie deadlockt ook zonder lus), `HEALTH_CHECK_INTERVAL_SECONDS` is 30 dus in twee seconden
draagt de lus niets bij, en zo blijft er geen dangling task achter onder
`filterwarnings = ["error"]`.

**Autouse-fixtures nagelopen** (de les "de testopstelling zet uit wat je meet"):
`tests/unit/als/conftest.py` herexporteert drie governance-stubs (`council_gate`,
`hitl_ticket_repository`, `prana_guard`) als autouse. Geen van drie raakt
`AgentLifecycleManager`, `asyncio.Lock` of `self._locks`. `tests/conftest.py` heeft
`enforce_testing_env`, `_reset_global_state` en een session-scoped event-looppolicy; ook die
raken niets van wat hier gemeten wordt.

**Mutatiebewijs (uitgevoerd, zie de final-approver brief van 2026-09-07).** Benoemde
verzameling, een element: "`_check_all_agents` neemt de tenant-lock niet opnieuw".
  - `await self._unregister_locked(` in `_check_all_agents` terugzetten naar
    `await self.unregister_agent(` -> test 1 ROOD (TimeoutError)
  - ongemuteerd -> alle drie GROEN
De tegenrichting zit in de tests zelf en niet alleen in het harnas: test 2 bewijst dat de
PUBLIEKE variant de lock wel neemt (anders zou "nooit locken" een geldige fix zijn) en test 3
bewijst dat een agent die nog niet lang genoeg offline is NIET wordt uitgeschreven (anders zou
"altijd uitschrijven" een geldige fix zijn).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from src.core.als.enterprise.agents.agent_lifecycle import (
    AgentLifecycleManager,
    AgentStatus,
    AgentType,
)

TENANT = 1
AGENT = "agent_1"


async def _manager_met_een_agent() -> AgentLifecycleManager:
    manager = AgentLifecycleManager()
    geregistreerd = await manager.register_agent(
        agent_id=AGENT,
        agent_type=AgentType.SPECIALIST,
        department="finance",
        tenant_id=TENANT,
    )
    assert geregistreerd, "de opstelling faalt al bij het registreren"
    return manager


def _zet_heartbeat_terug(manager: AgentLifecycleManager, seconden: float) -> None:
    """Backdate de heartbeat in plaats van te wachten -- deterministisch en snel."""
    health = manager._health[TENANT][AGENT]
    health.last_heartbeat = datetime.now(timezone.utc) - timedelta(seconds=seconden)


async def test_check_all_agents_unregisters_without_deadlocking_on_its_own_lock() -> None:
    """De auto-opruiming binnen de tenant-lock loopt af in plaats van te blijven hangen."""
    manager = await _manager_met_een_agent()
    manager.HEARTBEAT_TIMEOUT_SECONDS = 1
    manager.MAX_OFFLINE_TIME_SECONDS = 2
    _zet_heartbeat_terug(manager, 3600)

    await asyncio.wait_for(manager._check_all_agents(), timeout=2.0)

    assert AGENT not in manager.get_all_agents(TENANT), (
        "de agent stond lang genoeg offline en had uitgeschreven moeten worden"
    )
    assert manager._metrics["deregistered"] == 1


async def test_the_public_unregister_still_takes_the_tenant_lock() -> None:
    """Tegenrichting: "nooit locken" is geen geldige oplossing voor OP-195.

    De publieke variant MOET blijven wachten zolang een ander de tenant-lock vasthoudt, en
    daarna alsnog slagen. Zonder deze helft zou het weghalen van de lock uit
    `unregister_agent` de eerste test groen houden.
    """
    manager = await _manager_met_een_agent()
    lock = manager._locks[TENANT]

    await lock.acquire()
    taak = asyncio.create_task(manager.unregister_agent(AGENT, TENANT, "test"))
    try:
        await asyncio.sleep(0.05)
        assert not taak.done(), (
            "unregister_agent liep door terwijl de tenant-lock door een ander werd "
            "vastgehouden -- dan serialiseert hij niets"
        )
    finally:
        lock.release()

    assert await asyncio.wait_for(taak, timeout=2.0) is True
    assert AGENT not in manager.get_all_agents(TENANT)


async def test_an_agent_that_is_offline_but_not_long_enough_is_kept() -> None:
    """Tegenrichting: "altijd uitschrijven" is geen geldige oplossing voor OP-195."""
    manager = await _manager_met_een_agent()
    manager.HEARTBEAT_TIMEOUT_SECONDS = 1
    manager.MAX_OFFLINE_TIME_SECONDS = 3600
    _zet_heartbeat_terug(manager, 60)

    await asyncio.wait_for(manager._check_all_agents(), timeout=2.0)

    assert AGENT in manager.get_all_agents(TENANT), (
        "de agent stond 60s offline met een grens van 3600s en had moeten blijven staan"
    )
    assert manager.get_agent_health(AGENT, TENANT).status == AgentStatus.OFFLINE
    assert manager._metrics["deregistered"] == 0

async def test_check_all_agents_takes_the_real_tenant_lock() -> None:
    """Tegenrichting op de fix zelf: "geen echte lock nemen" is geen geldige oplossing.

    Toegevoegd 2026-09-07 na een blinde Gate 2-review (ADR-036 OP-195/OP-206). De drie tests
    hierboven meten de UITKOMST -- geen vastloper, agent verdwenen, agent blijft staan. Geen
    van drie meet WELKE lock `_check_all_agents` neemt. De reviewer wees erop dat regel 569
    daarmee ongestraft `async with asyncio.Lock():` kon worden: een verse lock per ronde,
    alle drie de tests groen, en de wederzijdse uitsluiting stil weg. Een vastloper is
    luidruchtig; een verloren lock niet.

    Deze test sluit dat gat door de tenant-lock van BUITEN vast te houden en aan te tonen dat
    `_check_all_agents()` dan niet doorloopt. Neemt hij een verse lock, dan loopt hij wel door
    en faalt deze assertie.

    Mutatiebewijs (uitgevoerd 2026-09-07): `async with self._lock_for(tenant_id)` in
    `_check_all_agents` vervangen door `async with asyncio.Lock()` -> ROOD hier, terwijl de
    andere drie tests GROEN blijven. Dat is precies het geval dat eerder niet gedekt was.
    """
    manager = await _manager_met_een_agent()
    manager.HEARTBEAT_TIMEOUT_SECONDS = 1
    manager.MAX_OFFLINE_TIME_SECONDS = 2
    _zet_heartbeat_terug(manager, 3600)

    lock = manager._lock_for(TENANT)
    await lock.acquire()
    taak = asyncio.create_task(manager._check_all_agents())
    try:
        await asyncio.sleep(0.05)
        assert not taak.done(), (
            "_check_all_agents liep door terwijl DE tenant-lock door een ander werd "
            "vastgehouden -- dan neemt hij een andere lock dan register_agent en "
            "unregister_agent, en serialiseert hij niets"
        )
    finally:
        lock.release()

    await asyncio.wait_for(taak, timeout=2.0)
    assert AGENT not in manager.get_all_agents(TENANT)
    assert manager._metrics["deregistered"] == 1


async def test_the_lock_helper_returns_the_same_lock_for_a_tenant() -> None:
    """`_lock_for` maakt de lock EEN keer aan en hergebruikt hem daarna.

    Zonder deze eigenschap is het hele lock-mechanisme decoratie: het oude construct
    `self._locks.get(tenant_id, asyncio.Lock())` gaf bij een ontbrekende sleutel elke keer een
    NIEUWE lock terug (ADR-036 OP-206). Twee tenants houden wel elk hun eigen lock.

    Mutatiebewijs (uitgevoerd 2026-09-07): de opslagregel in `_lock_for` terugzetten naar
    `return self._locks.get(tenant_id, asyncio.Lock())` -> ROOD hier.
    """
    manager = AgentLifecycleManager()

    eerste = manager._lock_for(7)
    tweede = manager._lock_for(7)
    andere_tenant = manager._lock_for(8)

    assert eerste is tweede, "_lock_for gaf twee verschillende locks voor dezelfde tenant"
    assert eerste is not andere_tenant, "twee tenants delen dezelfde lock"
    assert manager._locks[7] is eerste, "_lock_for slaat de lock niet op"
