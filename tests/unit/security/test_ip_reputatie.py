"""IP-reputatie: score, drempel, tijdelijke blokkade, herhaling, allowlist (plan nazorg, punt b).

Een kleine nep-Redis met een eigen klok, zodat verlopen zonder wachten te toetsen is. Het gedrag
tegen een echte Redis (twee processen, verlopen in echte tijd, Redis uit) staat in
`tests/integration/security/test_ip_blokkade_redis.py`.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.core.security.ip_reputation import IpReputation, IpReputationSettings
from tests.fixtures.nep_redis import KapotteRedis, NepRedis

IP = "203.0.113.7"


def _reputatie(redis: Any, **instellingen: Any) -> IpReputation:
    return IpReputation(IpReputationSettings(**instellingen), client=redis)


@pytest.mark.unit
class TestScoreEnDrempel:
    async def test_below_the_threshold_nothing_is_blocked(self) -> None:
        rep = _reputatie(NepRedis(), threshold=15)
        for _ in range(4):
            assert await rep.record(IP, 3, "sql") is False
        assert await rep.is_blocked(IP) is False

    async def test_reaching_the_threshold_blocks_for_the_base_duration(self) -> None:
        redis = NepRedis()
        rep = _reputatie(redis, threshold=15, block_base_seconds=900)
        uitslagen = [await rep.record(IP, 3, "sql") for _ in range(5)]
        assert uitslagen == [False, False, False, False, True]
        assert await rep.block_seconds_left(IP) == 900

    async def test_the_score_expires_after_its_window(self) -> None:
        redis = NepRedis()
        rep = _reputatie(redis, threshold=15, score_window_seconds=900)
        for _ in range(4):
            await rep.record(IP, 3, "sql")
        redis.nu += 901
        assert await rep.record(IP, 3, "sql") is False
        assert await rep.is_blocked(IP) is False

    async def test_the_block_expires(self) -> None:
        redis = NepRedis()
        rep = _reputatie(redis, threshold=3, block_base_seconds=900)
        assert await rep.record(IP, 3, "sql") is True
        redis.nu += 899
        assert await rep.is_blocked(IP) is True
        redis.nu += 2
        assert await rep.is_blocked(IP) is False

    async def test_another_ip_is_not_affected(self) -> None:
        rep = _reputatie(NepRedis(), threshold=3)
        await rep.record(IP, 3, "sql")
        assert await rep.is_blocked("198.51.100.1") is False


@pytest.mark.unit
class TestHerhaling:
    async def test_each_repeat_blocks_longer_up_to_the_maximum(self) -> None:
        redis = NepRedis()
        rep = _reputatie(
            redis, threshold=3, block_base_seconds=900, block_max_seconds=86_400
        )
        duren = []
        for _ in range(5):
            assert await rep.record(IP, 3, "sql") is True
            seconden = await rep.block_seconds_left(IP)
            assert seconden is not None
            duren.append(seconden)
            redis.nu += seconden + 1
        assert duren == [900, 3600, 14_400, 57_600, 86_400]

    async def test_strikes_expire_after_their_window(self) -> None:
        redis = NepRedis()
        rep = _reputatie(redis, threshold=3, block_base_seconds=900, strike_window_seconds=3600)
        await rep.record(IP, 3, "sql")
        redis.nu += 3601
        await rep.record(IP, 3, "sql")
        assert await rep.block_seconds_left(IP) == 900


@pytest.mark.unit
class TestAllowlist:
    async def test_an_address_in_an_exempt_network_is_never_blocked(self) -> None:
        rep = _reputatie(NepRedis(), threshold=3, exempt_cidrs=("10.0.0.0/8", "fd00::/8"))
        for ip in ("10.1.2.3", "fd00::1"):
            assert await rep.record(ip, 99, "sql") is False
            assert await rep.is_blocked(ip) is False

    async def test_an_address_outside_the_network_is_blocked(self) -> None:
        rep = _reputatie(NepRedis(), threshold=3, exempt_cidrs=("10.0.0.0/8",))
        assert await rep.record("11.0.0.1", 3, "sql") is True

    def test_an_invalid_network_is_ignored_not_fatal(self) -> None:
        rep = _reputatie(NepRedis(), exempt_cidrs=("geen-netwerk", "10.0.0.0/8"))
        assert rep.is_exempt("10.0.0.1") is True
        assert rep.is_exempt("unknown") is False


@pytest.mark.unit
class TestBeheer:
    async def test_unblock_lifts_the_block_and_resets_the_score(self) -> None:
        rep = _reputatie(NepRedis(), threshold=6)
        await rep.record(IP, 6, "sql")
        assert await rep.unblock(IP) is True
        assert await rep.is_blocked(IP) is False
        assert await rep.record(IP, 3, "sql") is False

    async def test_unblock_forgives_the_strikes_so_the_next_block_is_the_base_duration(
        self,
    ) -> None:
        """B4-1: na deblokkeren door een beheerder begint de herhalingsteller opnieuw."""
        redis = NepRedis()
        rep = _reputatie(redis, threshold=3, block_base_seconds=900)
        assert await rep.record(IP, 3, "sql") is True
        assert await rep.block_seconds_left(IP) == 900
        assert await rep.unblock(IP) is True
        assert await rep.record(IP, 3, "sql") is True
        assert await rep.block_seconds_left(IP) == 900

    async def test_list_blocks_shows_reason_and_time_left(self) -> None:
        rep = _reputatie(NepRedis(), threshold=3, block_base_seconds=900)
        await rep.record(IP, 3, "sql_injection_signal")
        [blokkade] = await rep.list_blocks()
        assert (blokkade.ip, blokkade.reason, blokkade.seconds_left) == (
            IP,
            "sql_injection_signal",
            900,
        )

    async def test_a_manual_block_refuses_an_exempt_address(self) -> None:
        rep = _reputatie(NepRedis(), exempt_cidrs=("10.0.0.0/8",))
        with pytest.raises(ValueError):
            await rep.block("10.0.0.1", "manual")


@pytest.mark.unit
class TestRedisUit:
    async def test_recording_fails_open_and_logs(self, caplog: pytest.LogCaptureFixture) -> None:
        rep = _reputatie(KapotteRedis(), threshold=3)
        assert await rep.record(IP, 99, "sql") is False
        assert "Redis niet bereikbaar" in caplog.text

    async def test_the_block_check_fails_open_and_logs(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        rep = _reputatie(KapotteRedis())
        assert await rep.is_blocked(IP) is False
        assert "verkeer gaat door" in caplog.text


class TestRedisUrl:
    """Welke URL de echte client krijgt: de meegegeven URL, anders `REDIS_URL`, anders de standaard.

    mypy 2.3 las de oude vorm (`os.getenv("REDIS_URL", default)`) als `str | None`; de keten eindigt
    nu op een vaste tekst. Een LEGE `REDIS_URL` valt daardoor op de standaard terug."""

    @staticmethod
    def _gebruikte_url(monkeypatch: pytest.MonkeyPatch, **kwargs: Any) -> list[str]:
        import redis.asyncio

        gezien: list[str] = []

        def nep_from_url(url: str, **_opties: Any) -> object:
            gezien.append(url)
            return object()

        monkeypatch.setattr(redis.asyncio, "from_url", nep_from_url)
        IpReputation(IpReputationSettings.from_config(), **kwargs)._redis()
        return gezien

    async def test_an_explicit_url_wins_over_the_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("REDIS_URL", "redis://uit-omgeving:6379/1")

        assert self._gebruikte_url(monkeypatch, redis_url="redis://expliciet:6379/2") == [
            "redis://expliciet:6379/2"
        ]

    async def test_the_environment_is_used_without_an_explicit_url(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("REDIS_URL", "redis://uit-omgeving:6379/1")

        assert self._gebruikte_url(monkeypatch) == ["redis://uit-omgeving:6379/1"]

    @pytest.mark.parametrize("waarde", [None, ""])
    async def test_without_a_url_the_default_is_used(
        self, monkeypatch: pytest.MonkeyPatch, waarde: str | None
    ) -> None:
        if waarde is None:
            monkeypatch.delenv("REDIS_URL", raising=False)
        else:
            monkeypatch.setenv("REDIS_URL", waarde)

        assert self._gebruikte_url(monkeypatch) == ["redis://localhost:6379/0"]
