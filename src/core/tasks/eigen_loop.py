"""Een async taak draaien in een eigen event loop met een eigen, poolloze engine.

Elke Dramatiq-actor is synchroon en doet `asyncio.run(...)`: een nieuwe event loop per run.
`db_manager` heeft een processen-brede engine met connectiepool, en een gepoolde asyncpg-
verbinding hoort bij de loop waarin hij is gemaakt. Een tweede run haalt dan een verbinding uit
de pool die aan een gesloten loop hangt (`attached to a different loop`). Daarom krijgt elke run
hier een eigen `NullPool`-engine (`db_manager.create_poolless_engine()`) die in `finally` wordt
vrijgegeven; de gedeelde engine wordt niet aangeraakt.

Verplaatst uit `debiteuren_tasks.py` (Keten B nazorg, punt B) zodat debiteuren, audit en cva
dezelfde route gebruiken.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

SessieFabriek = Callable[[], AbstractAsyncContextManager[AsyncSession]]


def draai_in_eigen_loop(taak: Callable[[SessieFabriek], Awaitable[None]]) -> None:
    """Draait een async taak in een verse event loop met een EIGEN engine, en ruimt die op.

    De taak krijgt een `sessie_fabriek`: elke aanroep levert een sessie die bij een normaal
    einde commit en bij een fout terugdraait. Elke actor-run is een eigen `asyncio.run`, dus een
    eigen loop; eerder deden deze actors `dispose()` op de gedeelde engine, en dat raakte elke
    andere actor die er tegelijk of daarna op draaide.
    """

    @asynccontextmanager
    async def _fabriek(maker: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
        async with maker() as sessie:
            try:
                yield sessie
                await sessie.commit()
            except Exception:
                await sessie.rollback()
                raise

    async def _run() -> None:
        from src.core.database.database import db_manager
        from src.core.noodstop.guard import gebruik_eigen_run_engine

        engine = db_manager.create_poolless_engine()
        maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
        try:
            # De noodstopcontrole hergebruikt de engine van deze run (met een semafoor) in plaats
            # van er per controle een te bouwen (Gate 2 ronde 2, punt 3).
            with gebruik_eigen_run_engine(engine):
                await taak(lambda: _fabriek(maker))
        finally:
            await engine.dispose()

    asyncio.run(_run())
