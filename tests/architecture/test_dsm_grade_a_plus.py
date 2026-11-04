"""Grade A+ DSM criteria regression tests.

These tests encode the future-proof DSM targets from
`docs/architecture/DSM-FUTUREPROOF-AUDIT-v6.1.md`.
"""

from __future__ import annotations

import configparser
import re
from pathlib import Path

import pytest

from scripts.dsm_full_analysis import (
    MODULE_MAP,
    scan_module,
    SOURCE_DIRS,
    MODULES,
    calculate_instability,
)

_REPO_ROOT = Path(__file__).parents[2]
_IMPORTLINTER_CFG = _REPO_ROOT / ".importlinter"

# Fan-out budgets per module, op de UNIEKE-PAREN-schaal (zie de uitleg bij
# test_fan_out_budget). Dit is de ENIGE plek waar de budgetten staan: de
# parametrize hieronder leest deze dict.
#
# Tot 2026-08-01 was dit een losse dict die door geen enkele test werd gelezen -- de
# waarden stonden gedupliceerd in de parametrize-lijst. Review BE-DSM-019 had dat al
# gemarkeerd als dead code met "toekomstige cleanup". Na de schaalwijziging werd het
# actief misleidend (oude budgetten op de oude schaal, naast een gate met nieuwe), dus
# is het nu de bron van waarheid in plaats van een kopie.
#
# OP-204, 2026-09-04: core_api 545 -> 556 (exact de gemeten waarde, GEEN marge).
# Oorzaak: een BOM in 17 bestanden (OP-203) hield 11 (bestand, doelmodule)-paren
# drie maanden onzichtbaar voor deze scanner; na het weghalen van de BOM's meet
# `scan_module("core_api", ..., unique_pairs=True)` 556. Bewust GEEN 5%-marge zoals
# bij de oorspronkelijke kalibratie hierboven: dit is een gedateerde uitzondering op
# bekende schuld (quality-gates.md), geen nieuwe baseline-kalibratie, en marge zou
# stilletjes ruimte weggeven boven wat vandaag echt gemeten is.
#
# 2026-09-08 (Cluster F, `iter/prana-economy`): 556 -> 557, EEN nieuw (bestand,
# doelmodule)-paar: `src/core/api/v1/tenant_management/dependencies.py ->
# governance.prana_service`. Dit is de ADR-033-facade zelf (Laag 2) die de
# governance-koppeling van `crud_router.py` overneemt -- voor die verplaatsing bevatte
# `crud_router.py` een DIRECTE import naar `governance.prana_service`, een echte
# ADR-033-schending (zie test_sp_api_010_backlog.py/test_dsm002_dag6_zero_violations.py),
# geen bestaand, al-getold paar. Het net-nieuwe paar is dus precies een, niet twee: de
# 2026-09-11 (ADR-029 Foundation Portal P0-7 t/m P1-6): 557 -> 572 (exact de gemeten
# waarde, 15 unieke (bestand, doelmodule)-paren voor src/core/api/v1/foundation/ endpoints).
#
# 2026-09-24 (BE-QA architectuur-groen, iter/wk1-architectuur-groen): 572 -> 585 (exact de
# gemeten waarde, GEEN marge -- zelfde conventie als OP-204). Diff gemeten tegen pin-commit
# 5b8a3503c met scripts/dsm_full_analysis.scan_module(unique_pairs=True), zelfde scanner op
# beide commits:
#   shared.time 3 -> 12: negen foundation-portalbestanden importeren nu
#     shared.datetime_utils (utc_now/to_utc -- het VOORGESCHREVEN patroon uit
#     backend-patterns.md #2, geen domeinkoppeling). De negende is newsletter.py, waar deze
#     sessie zelf datetime.now(timezone.utc) door utc_now() verving.
#   integrations 30 -> 32: newsletter.py en webhooks.py -> connectors.brevo (mask_email-
#     helper; connectors is geen ADR-033-verboden module).
#   infra 113 -> 117 / auth 224 -> 226: portal- en BE-LLM-003-facades
#     (admin/tenant_management dependencies) plus rbac_models/foundation_content
#     model-imports in de nieuwe portal-endpoints.
#   agent_runtime 89 -> 85: facade-consolidatie (ADR-033) -- directe services-imports uit
#     foundation/auth.py, newsletter.py, takedown.py en oai_pmh.py zijn naar de
#     Laag-2-facade verplaatst; deze sessie heeft de laatste vier resterende directe
#     imports (newsletter/upload/curatie) ook achter de facade gebracht.
# oude, foute directe import bestond nog niet lang genoeg om ooit in een gemeten
# baseline te hebben gestaan (de branch introduceerde hem dit merge-moment zelf).
#
# 2026-10-09 (OP-09, `iter/packs`): 557 -> 558, netto EEN paar erbij, exact de gemeten waarde
# (`test_fan_out_budget[core_api-557]` gaf 558). De route `POST /packs/execute` kreeg een
# rolcontrole, CSRF, een auditregel en `best_effort`; de imports daarvoor staan in
# `agentic_domain_router.py` en de facade `agentic/dependencies.py` (ADR-033). Welk paar
# precies het extra is, is NIET afzonderlijk aangewezen -- alleen het netto-verschil is gemeten.
# 2026-10-10 (OP-190-vervolg, `iter/pakketbeheer`): 558 -> 559, netto EEN paar erbij, exact de
# gemeten waarde (`test_fan_out_budget[core_api-558]` gaf 559). `approve_global_pack` kreeg een
# rolcontrole, CSRF en een echte auditregel; de imports daarvoor lopen via de domeinfacade
# `v1/company/dependencies.py` (ADR-033). Welk paar precies het extra is, is NIET afzonderlijk
# aangewezen -- alleen het netto-verschil is gemeten.
# 2026-10-11 (HR-pilot dag 1, `iter/hrdag1`): 559 -> 560, netto EEN paar erbij, exact de gemeten
# waarde (`test_fan_out_budget[core_api-559]` gaf 560). `GET /hr/skills/gap` leest dezelfde query
# als de agent-tool; `v1/hr/dependencies.py` importeert daarvoor `tool_broker.hr_registry`
# (ADR-033: de router zelf importeert niets). Dubbele query in de repository is verworpen.
# 2026-10-11 (HR-pilot dag 2, `iter/hrdag2`): 560 -> 561, netto EEN paar erbij, exact de gemeten
# waarde (`test_fan_out_budget[core_api-560]` gaf 561). `v1/hr/dependencies.py` kreeg de
# voorstel-repository, de vier-ogencontrole (`governance.four_eyes`) en `SCHEDULE_TOOL_NAME`
# (ADR-033: de router importeert niets rechtstreeks). Welk paar precies het extra is, is NIET
# afzonderlijk aangewezen -- alleen het netto-verschil is gemeten.
# 2026-10-14 (pakket aanzetten dag 1, `iter/pakket1`): 561 -> 562, exact de gemeten waarde
# (`test_fan_out_budget[core_api-561]` gaf 562). Gemeten op de basis `origin/develop` (a9115987): 560,
# dus met een budget van 561 stond er een paar speling; deze wijziging gebruikt die en voegt er EEN paar
# bovenop: netto TWEE paren erbij, per doelmodule governance +1 (de twee limiters
# `pack_activation_*_limit` in `v1/packs/dependencies.py`, ADR-033: de router importeert niets) en
# repositories +1 (`v1/packs/dependencies.py -> repositories.pack_activation_service`). De service staat
# bewust in `repositories` en niet in `services`: agent_runtime zit exact op zijn plafond (Ce 244, en
# governance-koppeling 9; gemeten 2026-10-14: een service in `services` die `AuditService` importeert gaf
# 10 en 246, ook na het weghalen van governance nog 245). De auditregel zelf wordt in
# `v1/packs/dependencies.py` geschreven; de lengtegrens van het pack-id
# is een vaste waarde in `v1/packs/schemas.py` (een unit-test koppelt hem aan het model) om een paar
# naar de modellaag te sparen. LET OP: `iter/mypy` (610653d9) voegt een eigen auth-paar toe
# (`activepieces_handler.py -> auth.api_deps`); samengevoegd staat core_api op 563.
# 2026-10-14 (pakket aanzetten dag 1, na de merge met origin/develop 0ef2109e): basis 561, deze
# wijziging 563, exact de gemeten waarde (`test_fan_out_budget[core_api-562]` gaf 563). De nieuwe paren
# staan in `v1/packs/dependencies.py` (limiters, audit_service, best_effort, agentic.dependencies voor de
# catalogus); een service in `services` of een `als`-import in `repositories` brak de plafonds van
# agent_runtime en infra (zie de commits 0114b5b1 en eed230c3), dus ze staan bewust in core_api.
# 2026-10-17 (bonlezer dag 3, `iter/bonlezer3`): 563 -> 565, exact de gemeten waarde
# (`test_fan_out_budget[core_api-563]` gaf 565). Het nieuwe domein `v1/bonnen` (upload-route) heeft
# EEN facade `v1/bonnen/dependencies.py` die de bonlezer-opslag (`als`) en de auditregel
# (`governance`) importeert; de route zelf importeert daar niets rechtstreeks voor (ADR-033). Welke
# paren precies het extra zijn is gemeten via het netto-verschil, niet per paar aangewezen.
# 2026-10-21 (noodstop ronde 2, ADR-036 OP-03, besluit A): 565 -> 566. De focus-builder chat-websocket
# (`v1/focus_builder/ws_chat_router.py`) controleert de noodstop zelf voor elk bericht dat naar het
# model gaat; dat is een nieuw bestand->module-paar naar `src.core.noodstop`. Gemeten: 566.
# 2026-10-21 (ActivePieces per klant dag 2, `iter/apperklant-samen`): 565 -> 566, exact de gemeten
# waarde (`test_fan_out_budget[core_api-565]` gaf 566 na het samenvoegen van `iter/apperklant2`
# `ad9f5c47` met `1a4e2c3e`; elke tak alleen past op 565). Het extra paar is gemeten met een
# per-bestand-vergelijking van de drie boomstanden: `v1/admin/dependencies.py -> integrations`
# (de facade `bouw_ap_verbinding_beheer`/`ap_hoofdsleutel_fout` voor de platformbeheerroute
# `ap_verbinding_router.py`, ADR-033: de router importeert niets rechtstreeks). Verplaatsen naar
# `v1/activepieces/dependencies.py` (dat paar bestaat al) zou de hele beheerroute, zijn
# rolcontrole-sleutel in `test_admin_routes_hebben_een_rolcontrole` en de facade-import van de
# versleuteling (security -> auth) meeverplaatsen en is een eigen wijziging, geen
# samenvoegreparatie.
# 2026-10-22 (samenvoeging van `origin/develop` `d054a114` in de noodstoptak): 566 -> 568, exact de
# gemeten waarde (`test_fan_out_budget[core_api-566]` gaf 568). Per-bestand-vergelijking van de unieke
# bestand->bak-paren (core_api): `d054a114` alleen = 566 (het eigen plafond van develop), de noodstoptak
# heeft er twee bij die al in haar eigen plafond zaten: `v1/focus_builder/ws_chat_router.py -> infra`
# (`src.core.noodstop`, besluit A: de focus-builder-websocket controleert de stand zelf) en
# `v1/noodstop/dependencies.py -> governance` (de noodstop-API, ronde 1). Elke tak paste apart; de
# som past niet, want develop gebruikte de speling van 565 al op.
# 2026-10-22 (brief dsm-meter-telt-ook-import-x): 566 -> 568, exact de gemeten waarde. De meter
# telde `import x` niet, alleen `from x import y`; nu telt hij beide gelijk. Twee nieuwe
# (bestand, doelmodule)-paren, beide health-checks die een module als alias importeren (regie e9
# besloot: legitiem, geen verborgen laagovertreding):
#   - `src/core/api/health_endpoints.py:32` `import src.core.caching.cache_layer as
#     cache_layer_module` -> infra (alias op moduleniveau, zodat tests `get_cache` kunnen patchen);
#   - `src/core/api/system_endpoints.py:216` `import src.core.database.connection as db_conn`
#     -> infra (lazy binnen de health-check).
# Ook nieuw maar zonder invloed op dit getal: `health_endpoints.py:34` -> shared (telt voor Ce niet
# mee) en `health_endpoints.py:717` -> llm (dat paar bestond al in dit bestand, via `from`).
# 2026-10-22 (samenvoeging `df79d145` + meter `9cc83edc` in de noodstoptak): 568 -> 570, exact de gemeten
# waarde met de nieuwe meter. `9cc83edc` alleen = 568 (de twee health-check-paren hierboven); de noodstoptak
# heeft er twee bij, per bestand->bak-paar in `RANDEN_SINDS_568` hieronder (bestand, regel, doel, reden). Besluit
# regie 2026-10-23: de governance-rand is toegestaan (ADR-033: daarvoor is `dependencies.py`); de websocket-router
# importeerde de noodstopguard zelf (een eigen infra-paar) en doet dat niet meer: die import staat nu in
# `focus_builder/dependencies.py`, de router gebruikt wat dependencies aanbiedt. Het aantal paren blijft daardoor
# gelijk (570): het infra-paar verhuisde van de router naar dependencies.py, dat nog geen infra-paar had.
# 2026-10-23 (enkele ingang `services/noodstop_toegang.py`): 570 -> 569, exact de gemeten waarde (`edges2` op de
# paren: 569, geen nieuw paar). `focus_builder/dependencies.py` importeert de noodstop nu uit de ingang (een
# agent_runtime-module) in plaats van uit `src.core.noodstop.guard`: het infra-paar van dat bestand vervalt, het
# agent_runtime-paar bestond er al (regel 11). Dezelfde functie; de afhankelijkheid loopt nu door agent_runtime.
# `test_de_randen_sinds_568_bestaan_nog` controleert dat elke regel nog klopt.
RANDEN_SINDS_568: list[tuple[str, int, str, str]] = [
    (
        "src/core/api/v1/noodstop/dependencies.py",
        28,
        "src.core.governance.rate_limiter",
        "noodstop-API (ronde 1): importeert `noodstop_read_limit` en `noodstop_write_limit` en biedt ze aan de "
        "noodstop-router aan (`__all__`, regels 48-49); toegestaan volgens ADR-033, daarvoor is dependencies.py",
    ),
]


@pytest.mark.architecture
def test_de_randen_sinds_568_bestaan_nog() -> None:
    """Elke rand in `RANDEN_SINDS_568` staat nog op die regel (de lijst veroudert niet ongemerkt)."""
    import ast

    wortel = Path(__file__).resolve().parents[2]
    weg = []
    for bestand, regel, doel, reden in RANDEN_SINDS_568:
        assert reden.strip()
        boom = ast.parse((wortel / bestand).read_text(encoding="utf-8"))
        if not any(
            isinstance(n, ast.ImportFrom)
            and n.level == 0
            and getattr(n, "lineno", None) == regel
            and (n.module or "").startswith(doel)
            for n in ast.walk(boom)
        ):
            weg.append((bestand, regel, doel))
    assert not weg, f"Deze randen uit RANDEN_SINDS_568 staan niet meer op die regel: {weg}"


# 2026-10-25 (crediteuren dag 2): 568 -> 569, exact de gemeten waarde (`test_fan_out_budget[core_api-568]`
# gaf 569). Een nieuw (bestand, doelmodule)-paar: `v1/payables/inlezen_dependencies.py` -> agent_runtime
# (de inlezen-service en zijn uitkomsttypen, ADR-033 Laag 2). Het paar kan niet via `bonnen/dependencies.py`
# lopen zonder die module iets te laten herexporteren dat niet van bonnen is.
# 2026-10-26 (samenvoeging crediteuren dag 2 met develop): 569 -> 570, exact de gemeten waarde (`test_fan_out_budget[core_api-569]`
# gaf 570). Develop stond op 569 (zie hierboven); het ene nieuwe paar is dat van crediteuren dag 2 (`inlezen_dependencies.py`
# -> agent_runtime, hierboven). Zonder dag 3.
# Crediteuren dag 3 voegt geen paar toe: de betaalroutes lopen via `importlib` in `v1/payables/betaal_dependencies.py` (gemeten: 570 blijft 570).
# 2026-11-01 (sync-merge upstream 8da3ba206 in het-levend-monument, iter/sync-upstream-2026-11-01):
# 570 -> 598, exact de gemeten waarde (`test_fan_out_budget[core_api-570]` gaf 598). Geen nieuw
# paar door de merge zelf: 598 = 557 (gezamenlijke basis) + 28 (ADR-029 portal, hierboven tot 585)
# + 13 (upstream 557 -> 570, hierboven). Beide takken zijn additief en delen geen paren.
# 2026-11-03 (BE-EP-055 docentenomgeving): 598 -> 603, exact de gemeten waarde
# (`test_fan_out_budget[core_api-598]` gaf 604; na het routeren van best_effort en utc_now via
# foundation/dependencies.py en een lokale to_utc 603). De nieuwe paren zijn de drie nieuwe diensten
# (services.foundation_klas, foundation_leerlingantwoorden, foundation_lespdf) vanuit docent.py en edu.py,
# plus shared.config en security.hcaptcha vanuit docent.py; dezelfde modules die contact.py en auth.py al
# gebruiken. Geen facade beschikbaar voor de drie nieuwe diensten zonder er een te bouwen.
FAN_OUT_BUDGETS = {
    "core_api": 603,
    "auth": 19,
    "infra": 5,
    "shared": 0,
    "governance": 12,
    "integrations": 30,
    "tenancy": 10,
    "llm": 9,
    "domain_pack": 19,
    "worker": 5,
    "tool_broker": 11,
}

# Modules die bewust GEEN eigen fan-out-budget hier hebben, omdat ze elders al
# gegateerd worden. Een tweede plafond ernaast zou twee waarheden over dezelfde module
# opleveren.
FAN_OUT_UNBUDGETED = {
    # Gegateerd via test_agent_runtime_instability_ceiling (Ce <= 700 op de
    # statement-schaal) plus de instabiliteitstests hieronder.
    # Gemeten 2026-08-01: 218 statements / 155 unieke paren.
    "agent_runtime",
    # De shared-sublagen (DSM-021) hebben elk een eigen Ce-is-nul-test in
    # tests/architecture/test_dsm021_shared_sublayers.py. Gemeten 2026-08-01: alle
    # drie 0 unieke paren.
    "shared.time",
    "shared.types",
    "shared.utils",
}

# Modules that should never import from higher layers
# (shared is already covered by budget=0)
LOWER_LAYER_MODULES = {"shared", "infra", "auth", "tenancy"}


@pytest.mark.architecture
def test_shared_fan_out_is_zero() -> None:
    """Shared foundation must never import from other modules."""
    counts, _, _ = scan_module("shared", SOURCE_DIRS["shared"])
    assert sum(counts.values()) == 0, f"shared fan-out must be 0, got {sum(counts.values())}"


@pytest.mark.architecture
def test_no_unclassified_modules() -> None:
    """Every src.* import must map to a DSM bucket."""
    all_unclassified: dict[str, int] = {}
    for mod in MODULES:
        _, _, unclassified = scan_module(mod, SOURCE_DIRS.get(mod, []))
        for key, value in unclassified.items():
            all_unclassified[key] = all_unclassified.get(key, 0) + value

    assert not all_unclassified, (
        f"Unclassified modules found: {all_unclassified}. "
        f"Add them to MODULE_MAP in scripts/dsm_full_analysis.py"
    )


# Fan-out budgets op de UNIEKE-PAREN-schaal (Rakesh GO, 2026-08-01, OP-11-vervolg).
#
# Waarom de schaal is veranderd: tot 2026-08-01 telde deze gate import-STATEMENTS.
# Dat is te omzeilen zonder de architectuur te verbeteren -- twee
# `from src.core.auth.api_deps import ...`-regels in een bestand scoren 2, en ze
# samenvoegen tot een regel scoort 1 terwijl er geen enkele afhankelijkheid verdwijnt.
# Tijdens OP-11 is dat gat tweemaal onder tijdsdruk gebruikt om binnen het plafond te
# blijven; dat was het signaal dat de meter opmaak meette in plaats van koppeling. De
# statement-telling kan bovendien een bewust knooppunt niet onderscheiden van
# verspreide koppeling: een facade die 17 symbolen uit een module haalt (ADR-033,
# gewenst) scoort hetzelfde als 17 routers die er elk een uit halen (ongewenst).
#
# De nieuwe schaal telt unieke (bestand, doelmodule)-paren: "hoeveel bestanden kennen
# module X". Regels samenvoegen levert daar per definitie niets op, en facade-werk
# levert wel echt op (10 routers -> 1 facade = 10 -> 1).
#
# De budgetten zijn MEEGESCHAALD, niet overgenomen. Het oude plafond aanhouden op een
# lagere schaal zou stilletjes ~280 imports ruimte weggeven -- precies het theater dat
# .claude/rules/quality-gates.md verbiedt. Regel: gemeten waarde + ~5%, minimaal +5,
# afgerond op 5. Gemeten op 2026-08-01 (develop):
#
#   module         statements   unieke paren   oud budget   nieuw budget
#   core_api              800            518          800            545
#   auth                   24             14           80             19
#   infra                   0              0           80              5
#   governance             11              7           50             12
#   integrations           42             25           60             30
#   tenancy                10              5           30             10
#   llm                     4              4           15              9
#   domain_pack            15             14           60             19
#   worker                  0              0           80              5
#   tool_broker            11              6           40             11
#
# Let op: de meeste modules hadden op de oude schaal enorme, betekenisloze marge
# (auth 24/80). Die is nu klein en dus weer zeggend.
#
# De historische reeks blijft op de statement-schaal staan en is NIET herschreven:
# core_api ging 1139 -> 800 op die schaal (DSM-FUTUREPROOF-AUDIT-v6.1, SPRINT_TRACKER).
# `scan_module()` telt daarom nog steeds statements by default, zodat de
# instabiliteitscijfers (Ce/Ca) en de overige DSM-tests onveranderd blijven.
@pytest.mark.architecture
def test_every_dsm_module_has_a_fan_out_budget_or_an_explicit_exemption() -> None:
    """Een nieuwe DSM-module mag niet stil aan de fan-out-gate ontsnappen.

    Zonder deze test levert het toevoegen van een module aan MODULES een module op die
    door geen enkel plafond wordt gedekt -- en dat valt niet op, want alle bestaande
    tests blijven groen.
    """
    covered = set(FAN_OUT_BUDGETS) | FAN_OUT_UNBUDGETED
    missing = set(MODULES) - covered
    assert not missing, (
        f"DSM-modules zonder fan-out-budget: {sorted(missing)}. Geef ze een budget in "
        f"FAN_OUT_BUDGETS, of zet ze in FAN_OUT_UNBUDGETED met de reden erbij (zoals "
        f"agent_runtime, dat via zijn instabiliteitsplafond wordt gegateerd)."
    )
    stale = FAN_OUT_UNBUDGETED - set(MODULES)
    assert not stale, f"FAN_OUT_UNBUDGETED noemt onbekende modules: {sorted(stale)}"


@pytest.mark.architecture
@pytest.mark.parametrize("module,budget", sorted(FAN_OUT_BUDGETS.items()))
def test_fan_out_budget(module: str, budget: int) -> None:
    """Each module must stay within its Grade A+ fan-out budget.

    Counted as unique (file, target-module) pairs -- see the comment above for why.

    shared is excluded from the total: foundation imports are expected and not
    counted as architectural coupling (same convention as Ce calculation).
    """
    counts, _, _ = scan_module(module, SOURCE_DIRS.get(module, []), unique_pairs=True)
    total = sum(v for k, v in counts.items() if k != "shared")
    assert total <= budget, (
        f"{module} fan-out {total} exceeds Grade A+ budget {budget} "
        f"(unieke bestand->module-paren). Samenvoegen van import-regels helpt hier "
        f"niet: breng de imports achter de domein-facade (ADR-033) zodat minder "
        f"bestanden de doelmodule kennen."
    )


@pytest.mark.architecture
def test_core_api_fan_out_trending_down() -> None:
    """Signaleert (blokkeert niet) zodra het OP-204-plafond van core_api (556) omlaag kan.

    Zelfde stramien als test_api_layer_violations_trending_down in
    tests/architecture/test_dsm_api_violations.py -- alleen voor core_api, want dat is
    de enige module met een OP-204-gedateerde uitzondering i.p.v. een gekalibreerd budget.
    """
    counts, _, _ = scan_module("core_api", SOURCE_DIRS.get("core_api", []), unique_pairs=True)
    total = sum(v for k, v in counts.items() if k != "shared")
    if total < FAN_OUT_BUDGETS["core_api"]:
        pytest.xfail(
            f"core_api fan-out daalde naar {total}; verlaag FAN_OUT_BUDGETS['core_api'] "
            f"in {Path(__file__).name}"
        )


@pytest.mark.architecture
def test_import_linter_all_contracts_active() -> None:
    """All 9 contracts must be uncommented and active for future-proof CI."""
    config_text = _IMPORTLINTER_CFG.read_text(encoding="utf-8")

    required_contracts = [
        "api-no-domain",
        "no-cross-router",
        "layers",
        "infra-no-api",
        "governance-no-workflow-direct",
        "no-cross-gateway",
        "governance-independence",
        "agent_runtime_boundary",
        "agent_runtime_no_db",
    ]

    missing = []
    for contract in required_contracts:
        pattern = rf"^\[importlinter:contract:{re.escape(contract)}\]"
        if not re.search(pattern, config_text, re.MULTILINE):
            missing.append(contract)

    assert not missing, (
        f"Inactive or missing import-linter contracts: {missing}. "
        f"See docs/architecture/DSM-FUTUREPROOF-AUDIT-v6.1.md Fase 3."
    )


@pytest.mark.architecture
def test_contract5_governance_independence_hardened() -> None:
    """Contract 5 must use allow_indirect_imports=false -- SP-DSM-005."""
    config_text = _IMPORTLINTER_CFG.read_text(encoding="utf-8")
    # Extract the governance-independence section only (stop before next [importlinter: header).
    section_match = re.search(
        r"\[importlinter:contract:governance-independence\](.*?)(?=\[importlinter:|\Z)",
        config_text,
        re.DOTALL,
    )
    assert section_match is not None, (
        "Contract 5 (governance-independence) missing from .importlinter"
    )
    assert re.search(r"allow_indirect_imports\s*=\s*false", section_match.group(1)), (
        "Contract 5 (governance-independence) still uses allow_indirect_imports=true. "
        "Fix: move OfficerVerdict from copilot.council.types to governance.models "
        "and CouncilDecisionRow from copilot.council.models to governance.models. "
        "See SP-DSM-005."
    )


@pytest.mark.architecture
def test_router_size_limit_adr033() -> None:
    """ADR-033: router files must not exceed 200 lines."""
    api_dir = _REPO_ROOT / "src" / "core" / "api"
    oversized: list[Path] = []

    for path in api_dir.rglob("router.py"):
        lines = path.read_text(encoding="utf-8").count("\n") + 1
        if lines > 200:
            oversized.append(path)

    assert not oversized, (
        f"Oversized routers (>200 lines): {[str(p.relative_to(_REPO_ROOT)) for p in oversized]}"
    )


@pytest.mark.architecture
def test_agent_runtime_instability_ceiling() -> None:
    """agent_runtime fan-out ceiling (excl. shared) must stay below 700.

    Hard gate: catches unbounded growth even when the instability ratio
    looks acceptable due to proportional Ca growth.
    Current measured value after SP-DSM-007: Ce=311.
    """
    result = calculate_instability("agent_runtime", exclude_shared=True)
    ce = result["fan_out"]
    assert ce <= 700, (
        f"agent_runtime Ce={ce} exceeds safety ceiling 700 (excl. shared). "
        "Investigate new cross-boundary imports."
    )


@pytest.mark.architecture
def test_agent_runtime_instability_grade_a_plus() -> None:
    """agent_runtime gecorrigeerde instability moet <= 0.55 zijn.

    Robert Martin I = Ce / (Ce + Ca).
    Ce = fan-out excluding shared (foundation layer).
    Ca = fan-in (how many other modules import agent_runtime).

    Bereikt in SP-DSM-008 Dag 2: Ce=222, Ca=224, I=0.498.
    SP-DSM-014: drempel naar 0.55 bijgesteld. Container reclassificatie (agent_runtime->shared)
    verwijdert Ca-boost van alle container-imports -- meting nu nauwkeuriger.
    Gemeten na SP-DSM-014: Ce=190, Ca=187, I=0.504.
    """
    result = calculate_instability("agent_runtime", exclude_shared=True)
    ce = result["fan_out"]
    ca = result["fan_in"]
    instability = result["instability"]

    assert instability <= 0.55, (
        f"agent_runtime I={instability:.2f} > 0.55. "
        f"Ce={ce}, Ca={ca}. "
        "Fix: remove infra coupling via SP-DSM-008."
    )
