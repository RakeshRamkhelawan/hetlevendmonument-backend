"""ADR-039 "Standaardinstelling vier ogen" (Rakesh, 2026-10-05), debiteurenagent dag 3.

Een NIEUWE omgeving krijgt vier ogen AAN voor HR (Annex III), betalingen, IBAN wijzigen,
afboeken en overdracht aan incasso, en UIT voor herinneringen en aanmaningen. Bestaande
omgevingen worden niet aangeraakt: daar blijft "geen sleutel = UIT".

Gemeten aanmaakpaden (dag-3-brief): registratie (`registratie_omgeving.maak_omgeving`),
tenantbeheer (`crud_router.create_tenant`), de servicelaag (`TenantService.create_tenant`) en
de single-tenant opstart (`seed._ensure_default_tenant`).
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import src.core.database.import_all_models  # noqa: F401
from src.core.governance.four_eyes import (
    FOUR_EYES_SETTINGS_KEY,
    default_four_eyes_actions,
    four_eyes_from_settings,
    with_four_eyes_defaults,
)

AAN = {
    "query_hr_database",
    "analyze_skill_gap",
    "schedule_training",
    "make_payment",
    "change_iban",
    "write_off_receivable",
    "transfer_to_debt_collection",
}


@pytest.mark.unit
class TestDeStandaard:
    def test_the_default_is_on_for_hr_and_money(self) -> None:
        assert set(default_four_eyes_actions()) == AAN

    def test_the_default_is_off_for_a_reminder(self) -> None:
        assert four_eyes_from_settings(with_four_eyes_defaults({}), "send_payment_reminder") is False

    def test_a_setting_given_by_the_creator_is_kept(self) -> None:
        uit = with_four_eyes_defaults({FOUR_EYES_SETTINGS_KEY: ["send_payment_reminder"]})
        assert uit[FOUR_EYES_SETTINGS_KEY] == ["send_payment_reminder"]

    def test_an_existing_tenant_without_the_key_stays_off(self) -> None:
        """Geen stille betekeniswijziging voor bestaande omgevingen."""
        assert four_eyes_from_settings({}, "schedule_training") is False


@pytest.mark.unit
@pytest.mark.asyncio
class TestDeAanmaakpaden:
    async def test_registration_writes_the_default(self, db_session: AsyncSession) -> None:
        from src.core.auth.registratie_omgeving import maak_omgeving
        from src.core.models.rbac_models import Tenant

        tenant_id = await maak_omgeving(db_session)

        tenant = await db_session.get(Tenant, tenant_id)
        assert tenant is not None
        assert set(tenant.settings[FOUR_EYES_SETTINGS_KEY]) == AAN

    async def test_the_service_layer_writes_the_default(self) -> None:
        """Een stub-sessie die vastlegt wat er wordt toegevoegd; wat er daarna gebeurt telt niet."""
        from src.core.models.rbac_models import Tenant
        from src.core.services.tenant_service import TenantService

        toegevoegd: list[Any] = []

        class _Leeg:
            def scalar_one_or_none(self) -> None:
                return None

        class _Sessie:
            async def execute(self, *_a: Any, **_k: Any) -> Any:
                return _Leeg()

            def add(self, obj: Any) -> None:
                toegevoegd.append(obj)

            async def flush(self) -> None:
                raise RuntimeError("stop na het toevoegen")

            async def commit(self) -> None:
                raise RuntimeError("stop na het toevoegen")

        service = TenantService.__new__(TenantService)
        service.db = _Sessie()  # type: ignore[assignment]
        data: Any = type(
            "Data",
            (),
            {
                "name": "Nieuw bv",
                "slug": "nieuw-bv",
                "domain": None,
                "settings": None,
                "max_users": 5,
                "max_agents": 5,
                "max_storage_gb": 1,
                "subscription_tier": "free",
                "data_residency": "eu",
            },
        )()
        with pytest.raises(Exception):  # noqa: B017 -- de stub stopt bewust na `add`
            await service.create_tenant(data)

        tenants = [o for o in toegevoegd if isinstance(o, Tenant)]
        assert set(tenants[0].settings[FOUR_EYES_SETTINGS_KEY]) == AAN

    async def test_single_tenant_startup_writes_the_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import json

        from src.core.database import seed

        geschreven: dict[str, Any] = {}

        class _Rij:
            def fetchone(self) -> Any:
                return (1,) if geschreven else None

        class _Sessie:
            async def execute(self, statement: Any, params: Any = None) -> Any:
                if "INSERT INTO tenants" in str(statement):
                    geschreven.update(params)
                return _Rij()

            async def flush(self) -> None:
                return None

        async def kolommen(_s: Any, _t: str) -> set[str]:
            return {"name", "slug", "is_active", "settings"}

        monkeypatch.setattr(seed, "_get_table_columns", kolommen)

        await seed._ensure_default_tenant(_Sessie())  # type: ignore[arg-type]

        assert set(json.loads(geschreven["settings"])[FOUR_EYES_SETTINGS_KEY]) == AAN
