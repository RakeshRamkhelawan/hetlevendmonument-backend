"""SQLAlchemy Unit of Work compatibility implementation."""

from __future__ import annotations

import inspect
from contextlib import asynccontextmanager
from itertools import count
from types import TracebackType
from typing import Any
from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

_SAVEPOINT_COUNTER = count(1)


class Savepoint:
    """Minimal async savepoint handle bound to a unit of work session."""

    def __init__(self, session: AsyncSession, name: str) -> None:
        self._session = session
        self.name = name

    async def rollback(self) -> None:
        await self._session.execute(text(f"ROLLBACK TO SAVEPOINT {self.name}"))

    async def release(self) -> None:
        await self._session.execute(text(f"RELEASE SAVEPOINT {self.name}"))


class SQLAlchemyRepository:
    """Minimal repository wrapper around a SQLAlchemy async session."""

    def __init__(self, session: AsyncSession, model: type[Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        self._session = session
        self._model = model

    async def get(self, entity_id: Any) -> Any:  # TODO(TYPE): replace Any with concrete type
        from sqlalchemy import select

        result = await self._session.execute(select(self._model).where(self._model.id == entity_id))
        return result.scalar_one_or_none()

    def add(self, entity: Any) -> None:  # TODO(TYPE): replace Any with concrete type
        self._session.add(entity)


class SQLAlchemyUnitOfWork:
    """Request-scoped async unit of work around an async session factory."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], auto_commit: bool = False
    ) -> None:
        self._session_factory = session_factory
        self._auto_commit = auto_commit
        self._session: AsyncSession | None = None
        self._committed = False
        self._rolled_back = False
        self._events: list[Any] = []  # TODO(TYPE): replace Any with concrete type

    async def __aenter__(self) -> SQLAlchemyUnitOfWork:
        self._session = self._session_factory()
        self._committed = False
        self._rolled_back = False
        self._events = []
        begin = getattr(self._session, "begin", None)
        if begin is not None:
            result = begin()
            if inspect.isawaitable(result):
                await result
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._session is None:
            return
        try:
            if exc_type is not None:
                if not self._rolled_back:
                    await self._session.rollback()
                    self._rolled_back = True
                self._events.clear()
            elif self._auto_commit and not self._committed:
                await self.commit()
            elif not self._committed and not self._rolled_back:
                await self._session.rollback()
                self._rolled_back = True
                self._events.clear()
        finally:
            await self._session.close()
            self._session = None

    async def commit(self) -> None:
        if self._session is None:
            raise RuntimeError("No active session")
        if self._committed:
            raise RuntimeError("Transaction already committed")
        await self._session.commit()
        self._committed = True
        await self._emit_events()

    async def rollback(self) -> None:
        if self._session is None:
            raise RuntimeError("No active session")
        await self._session.rollback()
        self._rolled_back = True
        self._events.clear()

    def add_event(self, event: Any) -> None:  # TODO(TYPE): replace Any with concrete type
        self._events.append(event)

    async def savepoint(self, name: str | None = None) -> Savepoint:
        if self._session is None:
            raise RuntimeError("No active session")
        savepoint_name = name or f"sp_{next(_SAVEPOINT_COUNTER)}"
        await self._session.execute(text(f"SAVEPOINT {savepoint_name}"))
        return Savepoint(self._session, savepoint_name)

    async def _emit_events(self) -> None:
        pending_events = list(self._events)
        self._events.clear()
        for event in pending_events:
            emitter = getattr(event, "emit", None)
            if emitter is None:
                continue
            try:
                result = emitter()
                if inspect.isawaitable(result):
                    await result
            except Exception:
                continue

    @property
    def session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("Unit of work not started - use inside 'async with'")
        return self._session


@asynccontextmanager
async def unit_of_work(
    session_factory: async_sessionmaker[AsyncSession],
    auto_commit: bool = False,
) -> AsyncGenerator[SQLAlchemyUnitOfWork]:
    """Convenience async context manager that yields a unit of work."""

    async with SQLAlchemyUnitOfWork(session_factory, auto_commit=auto_commit) as uow:
        yield uow


__all__ = [
    "SQLAlchemyRepository",
    "SQLAlchemyUnitOfWork",
    "Savepoint",
    "unit_of_work",
]
