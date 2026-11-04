"""`update_tenant` wist geen beheerde instellingen meer (gerichte security-review F1, 2026-10-20).

`PUT /api/v1/tenants/{id}` is voor een beheerder van de EIGEN tenant bereikbaar en zette `settings` als geheel; alleen
`llm_provider` bleef staan. Een ontbrekende vier-ogen-sleutel betekent UIT (`four_eyes_from_settings`), dus een gewone
wijziging van een andere instelling zette vier ogen STIL uit en wiste de escalatietermijn. Gemeten:

1. Een update zonder deze sleutels laat `four_eyes_actions` (ook een lege lijst: "bewust nergens"),
   `four_eyes_explanation_pending`, `escalatie_na_dagen` en `llm_provider` staan.
2. Een uitdrukkelijk meegegeven waarde wint (zoals bij `llm_provider`).
3. De sleutels in de lijst zijn dezelfde als die hun eigenaren gebruiken (drift-guard).
4. De tenantrij wordt met een rijslot en een verse rij gelezen (anders overschrijft een oude kopie een gelijktijdige wijziging).

Mutatiebewijs: zie de commitboodschap.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.schemas.tenant_schemas import TenantUpdate
from src.core.services.tenant_service import TenantService
from src.core.shared.tenant_instellingen import (
    ALLEEN_EIGEN_ROUTE,
    BEHEERDE_INSTELLINGEN,
    behoud_beheerde_instellingen,
    genegeerde_beheerde_instellingen,
)

_OUD: dict[str, object] = {
    "four_eyes_actions": ["send_payment_reminder"],
    "four_eyes_explanation_pending": True,
    "escalatie_na_dagen": 21,
    "llm_provider": "ollama",
    "thema": "donker",
}


class TestDeZuiverRegel:
    @pytest.mark.parametrize("sleutel", sorted(BEHEERDE_INSTELLINGEN))
    def test_a_managed_key_missing_from_the_new_settings_is_kept(self, sleutel: str) -> None:
        nieuw = behoud_beheerde_instellingen(_OUD, {"thema": "licht"})

        assert nieuw[sleutel] == _OUD[sleutel]

    def test_an_unrelated_key_is_replaced_as_before(self) -> None:
        assert behoud_beheerde_instellingen(_OUD, {"thema": "licht"})["thema"] == "licht"

    def test_an_empty_four_eyes_list_is_kept_and_not_read_as_missing(self) -> None:
        oud: dict[str, object] = {"four_eyes_actions": []}

        assert behoud_beheerde_instellingen(oud, {"thema": "licht"})["four_eyes_actions"] == []

    @pytest.mark.parametrize("sleutel", sorted(ALLEEN_EIGEN_ROUTE))
    def test_a_supplied_value_for_an_own_route_key_is_ignored(self, sleutel: str) -> None:
        # Besluit 2026-10-22: vier ogen en de termijn wijzig je ALLEEN via hun eigen route (lijst uit de catalogus, CSRF,
        # tempo, auditregel). Een meegestuurde waarde in `PUT /tenants/{id}` wordt genegeerd, geen fout.
        nieuw = behoud_beheerde_instellingen(_OUD, {sleutel: "iets anders", "thema": "licht"})

        assert nieuw[sleutel] == _OUD[sleutel]

    def test_four_eyes_cannot_be_switched_off_through_the_tenant_route(self) -> None:
        nieuw = behoud_beheerde_instellingen(_OUD, {"four_eyes_actions": []})

        assert nieuw["four_eyes_actions"] == ["send_payment_reminder"]

    def test_a_value_for_an_own_route_key_that_was_never_set_is_dropped(self) -> None:
        nieuw = behoud_beheerde_instellingen({"thema": "x"}, {"four_eyes_actions": [], "thema": "y"})

        assert nieuw == {"thema": "y"}

    def test_the_language_model_choice_still_wins_when_given_explicitly(self) -> None:
        # `llm_provider` heeft geen eigen route: `PUT /tenants/{id}` met het gevalideerde schema IS de route
        # (ADR-041 B14: per klant schakelbaar). Vergrendelen zou die keuze breken.
        nieuw = behoud_beheerde_instellingen(_OUD, {"llm_provider": "mistral"})

        assert nieuw["llm_provider"] == "mistral"

    def test_the_ignored_keys_are_named_without_their_values(self) -> None:
        genegeerd = genegeerde_beheerde_instellingen(
            _OUD, {"four_eyes_actions": [], "escalatie_na_dagen": 21, "thema": "licht"}
        )

        assert genegeerd == ["four_eyes_actions"]

    def test_nothing_is_reported_when_the_supplied_value_equals_the_old_one(self) -> None:
        assert genegeerde_beheerde_instellingen(_OUD, {"escalatie_na_dagen": 21}) == []

    def test_a_key_that_was_never_set_is_reported_when_supplied(self) -> None:
        assert genegeerde_beheerde_instellingen({"thema": "x"}, {"four_eyes_actions": []}) == [
            "four_eyes_actions"
        ]

    def test_without_old_settings_the_new_ones_are_unchanged(self) -> None:
        assert behoud_beheerde_instellingen(None, {"thema": "licht"}) == {"thema": "licht"}

    def test_a_key_that_was_never_set_is_not_invented(self) -> None:
        assert behoud_beheerde_instellingen({"thema": "x"}, {"a": 1}) == {"a": 1}

    def test_the_input_is_not_changed_in_place(self) -> None:
        nieuw: dict[str, object] = {"thema": "licht"}

        behoud_beheerde_instellingen(_OUD, nieuw)

        assert nieuw == {"thema": "licht"}


class TestDeSleutelsKomenOvereenMetHunEigenaars:
    def test_four_eyes_keys_equal_those_of_the_model(self) -> None:
        from src.core.models.rbac_models import (
            FOUR_EYES_EXPLANATION_PENDING_KEY,
            FOUR_EYES_SETTINGS_KEY,
        )

        assert {FOUR_EYES_SETTINGS_KEY, FOUR_EYES_EXPLANATION_PENDING_KEY} <= set(
            BEHEERDE_INSTELLINGEN
        )

    def test_the_escalation_key_equals_that_of_the_debtor_settings(self) -> None:
        from src.core.governance.debiteuren_instellingen import ESCALATIE_SETTINGS_KEY

        assert ESCALATIE_SETTINGS_KEY in BEHEERDE_INSTELLINGEN

    def test_the_language_model_key_equals_that_of_the_choice(self) -> None:
        from src.core.shared.tenant_llm_keuze import INSTELLING

        assert INSTELLING in BEHEERDE_INSTELLINGEN


def _dienst(tenant: SimpleNamespace) -> tuple[TenantService, MagicMock]:
    resultaat = MagicMock()
    resultaat.scalar_one_or_none.return_value = tenant
    db = MagicMock()
    db.execute = AsyncMock(return_value=resultaat)
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    context = SimpleNamespace(bypass_filter=True, require_tenant=lambda: 7)
    return TenantService(db, context), db  # type: ignore[arg-type]


async def _werk_bij(tenant: SimpleNamespace, data: TenantUpdate) -> MagicMock:
    dienst, db = _dienst(tenant)
    try:
        await dienst.update_tenant(7, data)
    except Exception:  # de antwoordvorm doet er niet toe, alleen wat er is opgeslagen
        pass
    return db


def _tenant() -> SimpleNamespace:
    return SimpleNamespace(id=7, settings=dict(_OUD), domain=None, updated_at=None)


@pytest.mark.asyncio
class TestUpdateTenant:
    async def test_an_update_of_another_setting_keeps_four_eyes(self) -> None:
        tenant = _tenant()

        await _werk_bij(tenant, TenantUpdate(settings={"thema": "licht"}))

        assert tenant.settings["four_eyes_actions"] == ["send_payment_reminder"]

    async def test_an_update_of_another_setting_keeps_the_escalation_term(self) -> None:
        tenant = _tenant()

        await _werk_bij(tenant, TenantUpdate(settings={"thema": "licht"}))

        assert tenant.settings["escalatie_na_dagen"] == 21

    async def test_an_update_of_another_setting_keeps_the_explanation_marker(self) -> None:
        tenant = _tenant()

        await _werk_bij(tenant, TenantUpdate(settings={"thema": "licht"}))

        assert tenant.settings["four_eyes_explanation_pending"] is True

    async def test_the_other_setting_is_stored(self) -> None:
        tenant = _tenant()

        await _werk_bij(tenant, TenantUpdate(settings={"thema": "licht"}))

        assert tenant.settings["thema"] == "licht"

    async def test_a_put_with_an_empty_four_eyes_list_leaves_four_eyes_on(self) -> None:
        tenant = _tenant()

        await _werk_bij(tenant, TenantUpdate(settings={"four_eyes_actions": [], "thema": "licht"}))

        assert tenant.settings["four_eyes_actions"] == ["send_payment_reminder"]

    async def test_a_put_that_tries_to_change_the_term_leaves_it_and_logs_the_key(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        tenant = _tenant()

        with caplog.at_level("WARNING"):
            await _werk_bij(tenant, TenantUpdate(settings={"escalatie_na_dagen": 3}))

        assert (tenant.settings["escalatie_na_dagen"], "escalatie_na_dagen" in caplog.text) == (21, True)

    async def test_the_log_line_does_not_contain_the_supplied_value(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level("WARNING"):
            await _werk_bij(_tenant(), TenantUpdate(settings={"escalatie_na_dagen": 987654}))

        assert "987654" not in caplog.text

    async def test_the_tenant_row_is_read_with_a_lock_and_a_fresh_row(self) -> None:
        db = await _werk_bij(_tenant(), TenantUpdate(settings={"thema": "licht"}))

        eerste: Any = db.execute.await_args_list[0].args[0]
        assert "FOR UPDATE" in str(eerste.compile()) and (
            eerste.get_execution_options().get("populate_existing") is True
        )
