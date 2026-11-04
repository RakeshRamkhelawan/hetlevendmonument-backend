"""IP-reputatie: een score per IP in Redis, en pas boven een drempel een tijdelijke blokkade.

Waarom (plan nazorg, deel I, punten a en b). Tot 2026-10-08 zette een enkele treffer van de
SQL-regex het IP in een `set` in het geheugen van het proces, zonder einde. Gewone invoer zoals
`?color=#fff` of `?q=update address` was genoeg om iemand buiten te sluiten tot de herstart,
en met meerdere gunicorn-workers gold de blokkade alleen in dat ene proces.

Nu:
- Een signaal (bijvoorbeeld een SQL-patroon in een queryparameter) telt punten op in
  `{prefix}score:{ip}` (INCRBY + EXPIRE, een venster van `score_window_seconds`).
- Komt de score op of boven `threshold`, dan volgt `{prefix}block:{ip}` met SET EX NX.
  De aanvraag die de drempel passeert krijgt zelf al 403.
- De duur loopt op per herhaling: `{prefix}strikes:{ip}` (INCR, vervalt na
  `strike_window_seconds`); duur = basis * 4^(strikes-1), begrensd op `block_max_seconds`.
  Met de standaardwaarden: 15 minuten, 1 uur, 4 uur, en daarna 24 uur.
- Een adres in `exempt_cidrs` wordt nooit geblokkeerd (interne adressen, health probes).
  Een beheerder met een geldig token ook niet; dat beslist de middleware.
- Valt Redis uit, dan gaat het verkeer door (fail-open) en komt er een waarschuwing in de log.
  Dit is een heuristiek, geen toegangscontrole: authenticatie en autorisatie blijven
  fail-closed en staan hier los van.

Een blokkade staat in Redis, dus elke worker en elke replica ziet dezelfde blokkade.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
from dataclasses import dataclass, field
from collections.abc import AsyncIterator
from typing import Protocol, cast

logger = logging.getLogger(__name__)

#: Factor waarmee de blokkadeduur per herhaling groeit.
STRIKE_FACTOR = 4


class RedisLike(Protocol):
    """De Redis-commando's die deze module gebruikt (redis.asyncio.Redis of een nep)."""

    async def incrby(self, name: str, amount: int) -> int: ...
    async def incr(self, name: str) -> int: ...
    async def expire(self, name: str, time: int) -> bool: ...
    async def set(
        self, name: str, value: str, ex: int | None = None, nx: bool = False
    ) -> bool | None: ...
    async def get(self, name: str) -> str | None: ...
    async def delete(self, *names: str) -> int: ...
    async def ttl(self, name: str) -> int: ...
    def scan_iter(self, match: str, count: int = 10) -> AsyncIterator[str]: ...


@dataclass(frozen=True)
class IpReputationSettings:
    """De instelbare waarden; `from_config` leest ze uit `UnifiedConfig`."""

    threshold: int = 15
    score_window_seconds: int = 900
    block_base_seconds: int = 900
    block_max_seconds: int = 86_400
    strike_window_seconds: int = 7 * 86_400
    sql_signal_points: int = 3
    exempt_cidrs: tuple[str, ...] = ()
    key_prefix: str = "sec:"
    networks: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = field(
        default=(), init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        netten: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
        for cidr in self.exempt_cidrs:
            try:
                netten.append(ipaddress.ip_network(cidr.strip(), strict=False))
            except ValueError:
                logger.warning("SECURITY_BLOCK_EXEMPT_CIDRS: ongeldig netwerk %r genegeerd", cidr)
        object.__setattr__(self, "networks", tuple(netten))

    @classmethod
    def from_config(cls) -> IpReputationSettings:
        from src.core.config.unified_config import get_config

        cfg = get_config()
        cidrs = tuple(c for c in str(cfg.security_block_exempt_cidrs).split(",") if c.strip())
        return cls(
            threshold=int(cfg.security_ip_block_threshold),
            score_window_seconds=int(cfg.security_ip_score_window_seconds),
            block_base_seconds=int(cfg.security_ip_block_base_seconds),
            block_max_seconds=int(cfg.security_ip_block_max_seconds),
            strike_window_seconds=int(cfg.security_ip_strike_window_seconds),
            sql_signal_points=int(cfg.security_sql_signal_points),
            exempt_cidrs=cidrs,
        )


@dataclass(frozen=True)
class IpBlock:
    ip: str
    reason: str
    seconds_left: int


class IpReputation:
    """Score, blokkade en deblokkade per IP, gedeeld via Redis."""

    def __init__(
        self,
        settings: IpReputationSettings | None = None,
        *,
        redis_url: str | None = None,
        client: RedisLike | None = None,
    ) -> None:
        self._settings = settings
        self._redis_url = redis_url
        self._vaste_client = client
        self._client: RedisLike | None = None
        self._client_loop: asyncio.AbstractEventLoop | None = None

    @property
    def settings(self) -> IpReputationSettings:
        if self._settings is None:
            self._settings = IpReputationSettings.from_config()
        return self._settings

    def _sleutel(self, soort: str, ip: str) -> str:
        return f"{self.settings.key_prefix}{soort}:{ip}"

    def _redis(self) -> RedisLike:
        """Een client per event loop: een redis.asyncio-verbinding hoort bij de loop waarin hij
        ontstond. Productie heeft een loop per worker; tests starten er meer."""
        if self._vaste_client is not None:
            return self._vaste_client
        loop = asyncio.get_running_loop()
        if self._client is None or self._client_loop is not loop:
            import redis.asyncio

            # Eindigt op een vaste tekst, dus nooit `None` voor `from_url` (mypy 2.3 las de
            # `os.getenv(..., default)`-vorm als `str | None`). Een LEGE `REDIS_URL` valt nu terug
            # op de standaardwaarde in plaats van een lege URL aan `from_url` te geven.
            url = self._redis_url or os.getenv("REDIS_URL") or "redis://localhost:6379/0"
            self._client = cast(
                RedisLike,
                redis.asyncio.from_url(
                    url, decode_responses=True, socket_connect_timeout=0.5, socket_timeout=0.5
                ),
            )
            self._client_loop = loop
        return self._client

    def is_exempt(self, ip: str) -> bool:
        """Staat dit adres in de allowlist (`SECURITY_BLOCK_EXEMPT_CIDRS`)?"""
        try:
            adres = ipaddress.ip_address(ip)
        except ValueError:
            return False
        return any(adres in netwerk for netwerk in self.settings.networks)

    def _duur(self, strikes: int) -> int:
        s = self.settings
        duur = s.block_base_seconds * (STRIKE_FACTOR ** max(0, strikes - 1))
        return int(min(duur, s.block_max_seconds))

    async def record(self, ip: str, points: int, reason: str) -> bool:
        """Tel `points` op bij de score van `ip`. True als het IP nu (of al) geblokkeerd is.

        Fail-open: bij een Redis-fout False en een waarschuwing.
        """
        if points <= 0 or self.is_exempt(ip):
            return False
        s = self.settings
        try:
            r = self._redis()
            score_sleutel = self._sleutel("score", ip)
            score = int(await r.incrby(score_sleutel, points))
            await r.expire(score_sleutel, s.score_window_seconds)
            if score < s.threshold:
                return False
            strike_sleutel = self._sleutel("strikes", ip)
            strikes = int(await r.incr(strike_sleutel))
            await r.expire(strike_sleutel, s.strike_window_seconds)
            duur = self._duur(strikes)
            gezet = await r.set(self._sleutel("block", ip), reason, ex=duur, nx=True)
            await r.delete(score_sleutel)
            if gezet:
                logger.warning(
                    "SECURITY IP %s geblokkeerd voor %s s (score %s, herhaling %s): %s",
                    ip,
                    duur,
                    score,
                    strikes,
                    reason,
                )
            return True
        except Exception as exc:  # noqa: BLE001 -- fail-open is hier de bedoeling
            logger.warning(
                "SECURITY IP-reputatie: Redis niet bereikbaar, signaal niet geteld (%s)",
                type(exc).__name__,
            )
            return False

    async def block_seconds_left(self, ip: str) -> int | None:
        """Resterende seconden van de blokkade, None als er geen is (of Redis uitvalt)."""
        if self.is_exempt(ip):
            return None
        try:
            ttl = int(await self._redis().ttl(self._sleutel("block", ip)))
        except Exception as exc:  # noqa: BLE001 -- fail-open
            logger.warning(
                "SECURITY IP-reputatie: Redis niet bereikbaar, verkeer gaat door (%s)",
                type(exc).__name__,
            )
            return None
        # -2: bestaat niet; -1: bestaat zonder verloop (mag niet voorkomen, telt als blokkade).
        if ttl == -2:
            return None
        return max(ttl, 1)

    async def is_blocked(self, ip: str) -> bool:
        return await self.block_seconds_left(ip) is not None

    async def block(self, ip: str, reason: str, seconds: int | None = None) -> int:
        """Handmatige blokkade door een beheerder. Geeft de duur in seconden terug.

        Overschrijft een bestaande blokkade (geen NX): de beheerder beslist. Een adres uit de
        allowlist wordt ook dan niet geblokkeerd (ValueError), anders zou de blokkade stil
        niets doen.
        """
        if self.is_exempt(ip):
            raise ValueError("IP is on the exempt list")
        duur = int(seconds or self.settings.block_base_seconds)
        await self._redis().set(self._sleutel("block", ip), reason, ex=duur)
        return duur

    async def unblock(self, ip: str) -> bool:
        """Haal blokkade, score en strikes weg. True als er een blokkade was.

        Deblokkeren door een beheerder betekent dat het IP vergeven is: ook de teller van
        herhaalde overtredingen gaat weg, zodat een volgende blokkade weer de basisduur krijgt
        en niet 4x zo lang (B4-1).
        """
        r = self._redis()
        verwijderd = int(await r.delete(self._sleutel("block", ip)))
        await r.delete(self._sleutel("score", ip), self._sleutel("strikes", ip))
        return verwijderd > 0

    async def list_blocks(self, limit: int = 500) -> list[IpBlock]:
        r = self._redis()
        voorvoegsel = self._sleutel("block", "")
        blokkades: list[IpBlock] = []
        async for sleutel in r.scan_iter(match=f"{voorvoegsel}*", count=200):
            ip = str(sleutel)[len(voorvoegsel):]
            reden = await r.get(sleutel)
            ttl = int(await r.ttl(sleutel))
            if reden is None or ttl == -2:
                continue
            blokkades.append(IpBlock(ip=ip, reason=str(reden), seconds_left=max(ttl, 1)))
            if len(blokkades) >= limit:
                break
        return sorted(blokkades, key=lambda b: b.ip)


_ip_reputation: IpReputation | None = None


def get_ip_reputation() -> IpReputation:
    """De gedeelde instantie per proces (de toestand zelf staat in Redis)."""
    global _ip_reputation
    if _ip_reputation is None:
        _ip_reputation = IpReputation()
    return _ip_reputation
