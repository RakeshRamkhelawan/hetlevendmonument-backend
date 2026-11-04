"""Goedkeuren is een procesbevoegdheid: elke HIGH-actie heeft een recht, en niemand valt terug op "beheerder".

ADR-039 F1/F2/F7, besluit Rakesh 2026-10-09. `src/core/auth/approval_rights.py` kent twee tabellen
(tool -> recht, agent -> recht); een actie die er niet in staat wordt geweigerd. Deze bewaker houdt
vast dat die tabellen kloppen met wat het systeem werkelijk kent.

Wat hij bewaakt (de benoemde verzamelingen, een mutatie per element hieronder):
  1. `RECHT_PER_TOOL` en `RECHT_PER_AGENT`: elk recht heeft de actie `approve`
     (alleen die actie is expliciet, zie `EXPLICIT_ACTIONS`).
  2. Elke tool in `RECHT_PER_TOOL` is HIGH-risk in `tool_risk_levels.yml` (anders komt er
     nooit een ticket voor).
  3. Elke HIGH-tool heeft een recht (geen uitzonderingslijst meer sinds 2026-10-10) en elk
     procesrecht wordt in PRECIES de verwachte standaardrol gezaaid (AST, per rol).
  4. `_require_approver` in `tool_broker/hitl_router.py` en `gatekeeper/gatekeeper_hitl_router.py`
     bevat geen `is_tenant_admin`/`is_admin` meer (structuur: een AST-zoektocht naar aanroepen en
     namen binnen DIE functie, zonder docstring).

Mutatiebewijs (2026-10-09; kopie als terugweg, nooit `git checkout --`):
  ROOD:
    send_payment_reminder uit RECHT_PER_TOOL halen -> test 3 (HIGH-tool zonder recht)
    `"hr:*"` als recht in de agenttabel                    -> test 1 (actie is geen `approve`)
    een niet-HIGH tool (`list_receivables`) in de tooltabel -> test 2
    config:approve van de rol admin naar goedkeurder verplaatst in de zaailijst  -> test 5
    `is_tenant_admin(current_user)` terug in `_require_approver` van de gatekeeperrouter -> test 4
    idem in de tool-broker-router                          -> test 4
  GROEN, legitiem blijft toegestaan:
    een NIEUW recht `receivables:approve` voor een extra HIGH-tool toevoegen    -> test 1, 2, 3
    een docstring in `_require_approver` die `is_tenant_admin` noemt            -> test 4
"""

from __future__ import annotations

import ast
from pathlib import Path

import yaml

from src.core.auth.approval_rights import (
    ALLE_PROCESRECHTEN,
    RECHT_PER_AGENT,
    RECHT_PER_TOOL,
)
from src.core.services.rbac_service import EXPLICIT_ACTIONS

REPO = Path(__file__).resolve().parents[2]
RISK_LEVELS = REPO / "src" / "core" / "config" / "tool_risk_levels.yml"
ROUTERS = (
    REPO / "src" / "core" / "api" / "v1" / "tool_broker" / "hitl_router.py",
    REPO / "src" / "core" / "api" / "v1" / "gatekeeper" / "gatekeeper_hitl_router.py",
)

def _high_tools() -> set[str]:
    data = yaml.safe_load(RISK_LEVELS.read_text(encoding="utf-8"))
    return {
        naam for naam, niveau in data["tool_risk_levels"].items() if str(niveau).lower() == "high"
    }


def test_every_approval_right_uses_an_explicit_action() -> None:
    acties = {recht.split(":", 1)[1] for recht in ALLE_PROCESRECHTEN}
    assert acties <= set(EXPLICIT_ACTIONS), (
        f"Een goedkeurrecht met een andere actie dan {sorted(EXPLICIT_ACTIONS)}: {sorted(acties)}. "
        "Dan valt het onder de wildcard van de beheerder en is goedkeuren weer een beheerdersrecht."
    )


def test_the_two_tables_are_not_empty() -> None:
    """Een lege tabel laat elke test hieronder groen zonder iets te meten."""
    assert RECHT_PER_TOOL and RECHT_PER_AGENT


def test_every_tool_with_an_approval_right_is_high_risk() -> None:
    hoog = _high_tools()
    geen_ticket = sorted(set(RECHT_PER_TOOL) - hoog)
    assert not geen_ticket, (
        f"Deze tools hebben een goedkeurrecht maar zijn niet HIGH in tool_risk_levels.yml, dus "
        f"er komt nooit een ticket: {geen_ticket}"
    )


def test_every_high_tool_has_an_approval_right() -> None:
    """Geen uitzonderingen meer (besluit Rakesh 2026-10-10): een ticket voor elke HIGH-tool moet
    door iemand beslist kunnen worden."""
    zonder = sorted(_high_tools() - set(RECHT_PER_TOOL))
    assert not zonder, (
        f"HIGH-tool(s) zonder goedkeurrecht: {zonder}. Een ticket ervoor kan door niemand worden "
        "beslist. Voeg een regel toe aan RECHT_PER_TOOL in src/core/auth/approval_rights.py en zaai "
        "het recht in een standaardrol."
    )


#: In WELKE standaardrol elk procesrecht hoort te zitten (besluit Rakesh 2026-10-09/10). Een recht in
#: de verkeerde rol, of nergens, laat de bewaker falen; het recht komt nooit via een wildcard.
VERWACHTE_ROL_PER_PROCESRECHT: dict[str, str] = {
    "receivables:approve": "goedkeurder",
    "governance:approve": "goedkeurder",
    "hr:approve": "goedkeurder_hr",
    "config:approve": "admin",
    # Crediteuren dag 2 (2026-10-24): een uitzondering van de crediteurenagent goedkeuren, in dezelfde rol als de debiteuren.
    "payables:approve": "goedkeurder",
}


def test_the_expected_roles_cover_every_approval_right() -> None:
    assert set(VERWACHTE_ROL_PER_PROCESRECHT) == set(ALLE_PROCESRECHTEN)


def test_every_approval_right_is_seeded_in_exactly_its_default_role() -> None:
    """Gelezen uit de zaailijst van `ensure_default_roles` (AST, per rol), niet uit tekst."""
    from tests.architecture.test_role_permissions_cover_every_seeded_role import _gezaaide_rijen

    rollen = _gezaaide_rijen()
    fout = []
    for recht, rol in VERWACHTE_ROL_PER_PROCESRECHT.items():
        resource, _, actie = recht.partition(":")
        houders = sorted(naam for naam, rijen in rollen.items() if (resource, actie) in rijen)
        if houders != [rol]:
            fout.append(f"{recht}: verwacht alleen {rol!r}, gezaaid in {houders}")
    assert not fout, "Procesrecht in de verkeerde of geen standaardrol: " + "; ".join(fout)


def _require_approver_zonder_docstring(pad: Path) -> ast.AsyncFunctionDef:
    boom = ast.parse(pad.read_text(encoding="utf-8"))
    for knoop in ast.walk(boom):
        if isinstance(knoop, ast.AsyncFunctionDef) and knoop.name == "_require_approver":
            if (
                knoop.body
                and isinstance(knoop.body[0], ast.Expr)
                and isinstance(knoop.body[0].value, ast.Constant)
                and isinstance(knoop.body[0].value.value, str)
            ):
                knoop.body = knoop.body[1:]
            return knoop
    raise AssertionError(f"{pad.name} heeft geen async _require_approver meer")


def test_require_approver_never_asks_for_an_admin_role() -> None:
    verboden = {"is_tenant_admin", "is_admin", "require_admin"}
    gevonden: list[str] = []
    for pad in ROUTERS:
        functie = _require_approver_zonder_docstring(pad)
        namen = {n.id for n in ast.walk(functie) if isinstance(n, ast.Name)} | {
            n.attr for n in ast.walk(functie) if isinstance(n, ast.Attribute)
        }
        gevonden += [f"{pad.name}: {naam}" for naam in sorted(namen & verboden)]
    assert not gevonden, (
        f"_require_approver gebruikt weer een beheerdersbegrip: {gevonden}. Goedkeuren is een "
        "procesbevoegdheid (ADR-039): het recht komt uit role_permissions."
    )


# Plekken in src/core/api die een rol toewijzen namens een ingelogde gebruiker: de auditregel moet
# de TOEWIJZER dragen (ADR-039: een persoon mag alle rollen hebben, bewust en gelogd).
TOEWIJS_ROUTERS = (
    REPO / "src" / "core" / "api" / "v1" / "admin" / "users_router.py",
    REPO / "src" / "core" / "api" / "v1" / "rbac" / "assignment_router.py",
)


# Per aanroep het keyword dat de actor draagt: toewijzen -> assigned_by, intrekken -> revoked_by.
_TOEWIJZER_SLEUTEL = {
    "assign_role": "assigned_by",
    "bulk_assign_roles": "assigned_by",
    "revoke_role": "revoked_by",
    "bulk_revoke_roles": "revoked_by",
}


def _toewijsaanroepen_zonder_toewijzer(pad: Path) -> list[int]:
    boom = ast.parse(pad.read_text(encoding="utf-8"))
    return [
        k.lineno
        for k in ast.walk(boom)
        if isinstance(k, ast.Call)
        and isinstance(k.func, ast.Attribute)
        and k.func.attr in _TOEWIJZER_SLEUTEL
        and _TOEWIJZER_SLEUTEL[k.func.attr] not in {kw.arg for kw in k.keywords}
    ]


def test_every_role_assignment_route_passes_the_assigner() -> None:
    zonder = {
        p.name: regels for p in TOEWIJS_ROUTERS if (regels := _toewijsaanroepen_zonder_toewijzer(p))
    }
    assert not zonder, (
        f"Roltoewijzing of -intrekking zonder `assigned_by=`/`revoked_by=` (de auditregel kent de actor niet): {zonder}"
    )


def test_the_assignment_routes_contain_assignment_calls() -> None:
    """Een lege inventaris laat de test hierboven groen zonder iets te meten."""
    for pad in TOEWIJS_ROUTERS:
        boom = ast.parse(pad.read_text(encoding="utf-8"))
        aanroepen = [
            k
            for k in ast.walk(boom)
            if isinstance(k, ast.Call)
            and isinstance(k.func, ast.Attribute)
            and k.func.attr in _TOEWIJZER_SLEUTEL
        ]
        assert aanroepen, f"{pad.name} bevat geen roltoewijzing meer: werk TOEWIJS_ROUTERS bij"


def test_the_admin_role_names_in_the_rbac_service_equal_the_central_definition() -> None:
    """`rbac_service` schrijft de beheerdersrolnamen zelf uit (geen auth-import, DSM-meting);
    een verschil met de centrale definitie zou de laatste-beheerder-bewaking stil verleggen."""
    from src.core.auth.dependencies import ADMIN_ROLE_NAMES
    from src.core.services.rbac_service import BEHEERDERSROLNAMEN

    assert BEHEERDERSROLNAMEN == ADMIN_ROLE_NAMES
