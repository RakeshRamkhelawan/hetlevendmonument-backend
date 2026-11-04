"""Een nep-Redis met eigen klok, en een kapotte Redis (voor de IP-reputatie)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any


class NepRedis:
    """Precies de commando's die `IpReputation` gebruikt, met verloop op `self.nu`."""

    def __init__(self) -> None:
        self.nu = 0.0
        self.data: dict[str, str] = {}
        self.verloop: dict[str, float] = {}

    def _ruim(self, sleutel: str) -> None:
        if sleutel in self.verloop and self.verloop[sleutel] <= self.nu:
            self.data.pop(sleutel, None)
            self.verloop.pop(sleutel, None)

    async def incrby(self, sleutel: str, n: int) -> int:
        self._ruim(sleutel)
        waarde = int(self.data.get(sleutel, "0")) + n
        self.data[sleutel] = str(waarde)
        return waarde

    async def incr(self, sleutel: str) -> int:
        return await self.incrby(sleutel, 1)

    async def expire(self, sleutel: str, seconden: int) -> bool:
        self._ruim(sleutel)
        if sleutel not in self.data:
            return False
        self.verloop[sleutel] = self.nu + seconden
        return True

    async def set(
        self, sleutel: str, waarde: str, ex: int | None = None, nx: bool = False
    ) -> bool | None:
        self._ruim(sleutel)
        if nx and sleutel in self.data:
            return None
        self.data[sleutel] = waarde
        if ex is not None:
            self.verloop[sleutel] = self.nu + ex
        else:
            self.verloop.pop(sleutel, None)
        return True

    async def get(self, sleutel: str) -> str | None:
        self._ruim(sleutel)
        return self.data.get(sleutel)

    async def delete(self, *sleutels: str) -> int:
        weg = 0
        for sleutel in sleutels:
            self._ruim(sleutel)
            if self.data.pop(sleutel, None) is not None:
                weg += 1
            self.verloop.pop(sleutel, None)
        return weg

    async def ttl(self, sleutel: str) -> int:
        self._ruim(sleutel)
        if sleutel not in self.data:
            return -2
        if sleutel not in self.verloop:
            return -1
        return int(self.verloop[sleutel] - self.nu)

    async def scan_iter(self, match: str, count: int = 10) -> AsyncIterator[str]:
        voorvoegsel = match.rstrip("*")
        for sleutel in list(self.data):
            self._ruim(sleutel)
            if sleutel in self.data and sleutel.startswith(voorvoegsel):
                yield sleutel


class KapotteRedis:
    """Elke aanroep faalt, zoals een Redis die onbereikbaar is."""

    def __getattr__(self, naam: str) -> Any:
        async def _faal(*args: Any, **kwargs: Any) -> Any:
            raise ConnectionError("redis down")

        return _faal
