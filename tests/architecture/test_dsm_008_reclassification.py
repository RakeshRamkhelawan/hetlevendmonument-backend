"""DSM-008 reclassificatie voortgang tests.

Dag 1 target: Ce reductie van 311 naar <=285 via config/tracing/di reclassificatie.
Dag 2 target: Ce reductie naar <=223 (I<=0.50, Grade A+) via database+resilience reclassificatie.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from scripts.dsm_full_analysis import calculate_instability

_ROOT = Path(__file__).resolve().parents[2]

# De randen (bestand, regel, doelmodule, reden) die agent_runtime Ce sinds het goedgekeurde plafond 247
# (e96087f3, oude meter) hebben verhoogd tot de huidige 250 (meter van `9cc83edc`, die `import x` ook telt).
# De test `test_de_randen_sinds_247_bestaan_nog` controleert elke regel: staat op dat bestand en die regel nog
# steeds een import van die module? Zo kan de lijst niet ongemerkt verouderen, en een nieuwe rand moet hier
# met een reden bij (de som hieronder is wat de plafondverhoging verklaart).
#
# Boekhouding 247 -> 258, daarna 250 (alle verhogingen verklaard):
#   +6  develop (acf5470c): 11 randen erbij (hieronder, "develop") en 5 weg (llm.* in agents, geen reden nodig,
#       want ze verlagen Ce). Gemeten: dezelfde rijen staan op `d054a114` en niet op e96087f3.
#   +1  develop (df79d145): `workflow/providers.py` -> `tool_broker.workflow_identiteit`.
#   +1  de meter zelf (`9cc83edc` telt `import x`): `workers/scheduler.py` -> `src.workers.actors`.
#   +3  noodstop, variant A (hertoets): de drie opstartpunten die in agent_runtime vallen.
# De tien noodstop-deuren (ronde 1 en 2) zaten al in 247. Na de enkele ingang (`services/noodstop_toegang.py`)
# zijn negen daarvan er niet meer (elk een eigen rand naar `src.core.noodstop`), en staat er een rand voor de
# ingang zelf (+1): 258 -> 250 (-8). Alleen `cva_tasks.py` (weggegooid) blijft rechtstreeks. Dezelfde controle,
# een andere importroute: de afhankelijkheid van agent_runtime op de noodstop bestaat nog, via een rand.
#
# Per rand: (bestand, regel, doelmodule (of voorvoegsel), reden). De regelnummers zijn die van de stand na
# de samenvoeging met `9cc83edc`.
RANDEN_SINDS_247: list[tuple[str, int, str, str]] = [
    # --- develop: `workflow_actor` maakt een functie tot dramatiq-actor op een wachtrij (+5) ---
    (
        "src/core/copilot/audit/integrity_check_actor.py",
        13,
        "src.core.tasks.dramatiq_broker",
        'develop: `@workflow_actor(queue_name="maintenance", max_retries=3)` (regel 25) maakt van de functie een dramatiq-actor',
    ),
    (
        "src/core/copilot/audit/report_jobs.py",
        5,
        "src.core.tasks.dramatiq_broker",
        'develop: `@workflow_actor(queue_name="audit_reports", time_limit=1800000)` (regel 16), rapportjob als actor',
    ),
    (
        "src/core/tasks/cva_tasks.py",
        13,
        "src.core.tasks.dramatiq_broker",
        'develop: `@workflow_actor(queue_name="cva_queue")` (regel 23)',
    ),
    (
        "src/core/tasks/workflow_tasks.py",
        8,
        "src.core.tasks.dramatiq_broker",
        "develop: kale `@workflow_actor` (regel 15) op de workflowtaak",
    ),
    (
        "src/domains/memory/tasks.py",
        41,
        "src.core.tasks.dramatiq_broker",
        "develop: `@workflow_actor(` (regel 43) op de geheugentaak",
    ),
    # --- develop: nieuwe debiteurentijdlijn (+5) ---
    (
        "src/core/services/debiteur_tijdlijn.py",
        22,
        "src.core.models.outgoing_message_models",
        "develop: `GEANNULEERD_VOORVOEGSEL` (regels 112, 123) herkent uit `foutreden` een geannuleerd bericht",
    ),
    (
        "src/core/services/debiteur_tijdlijn.py",
        231,
        "src.core.models.outgoing_message_models",
        "develop: `OutgoingMessage` (regels 248-253) leest de berichten van de vordering van de tenant",
    ),
    (
        "src/core/services/debiteur_tijdlijn.py",
        232,
        "src.core.models.rbac_models",
        "develop: `User` (regel 316) haalt de e-mailadressen op van gebruikers die in de tijdlijn voorkomen",
    ),
    (
        "src/core/services/debiteur_tijdlijn.py",
        233,
        "src.core.models.receivable_models",
        "develop: `Receivable` (regels 238-239) leest de vordering zelf, gefilterd op tenant",
    ),
    (
        "src/core/services/debiteur_tijdlijn.py",
        234,
        "src.core.tool_broker.models",
        "develop: `HITLTicket` (regels 299-300) leest de goedkeuringstickets die bij de vordering horen",
    ),
    # --- develop: taalmodelkeuze van de tenant (+1) ---
    (
        "src/core/services/llm/tenant_deur.py",
        336,
        "src.core.database.session",
        "develop: `get_db_session` (regel 340) opent een sessie om de taalmodelkeuze van de tenant te lezen",
    ),
    # --- develop (df79d145): workflow-identiteit (+1) ---
    # 2026-10-24: sinds de starter-wijziging (f9e1f3af) staat de import als `from src.core.tool_broker import
    # workflow_identiteit`; dezelfde rand agent_runtime -> tool_broker, andere schrijfwijze (het doel is dus de module).
    (
        "src/core/workflow/providers.py",
        24,
        "src.core.tool_broker",
        "develop: bouwt de tool-broker (`workflow_identiteit.bouw_workflow_broker()`), identiteit `WORKFLOW_IDENTITEIT`, foutreden in gewone taal (`reden_in_gewone_taal(e)`) en het starterrecht",
    ),
    # --- de meter (9cc83edc): `import x` telt nu (+1) ---
    (
        "src/workers/scheduler.py",
        643,
        "src.workers.actors",
        "meter: `import src.workers.actors as _actors_module` (lazy, in de geplande-taak-opzet) was voor de oude meter onzichtbaar",
    ),
    # --- noodstop: de enkele ingang (-9 deuren, +1 ingang): agent_runtime heeft EEN rand naar de noodstop ---
    (
        "src/core/services/noodstop_toegang.py",
        23,
        "src.core.noodstop",
        "noodstop: de enkele ingang (`from src.core.noodstop import guard, metrics`); de deuren in agent_runtime importeren "
        "hieruit en niet meer rechtstreeks (bewaakt door test_agent_runtime_importeert_noodstop_alleen_via_de_ingang)",
    ),
    (
        "src/core/tasks/cva_tasks.py",
        9,
        "src.core.noodstop.weggegooid",
        "noodstop: teller, logregel en auditregel voor een weggegooid CVA-bericht; blijft rechtstreeks omdat de ingang "
        "via AuditService een importcyclus zou geven",
    ),
    # --- noodstop, hertoets variant A (+3): het opstartpunt meldt de modeldeur-controle aan ---
    (
        "src/core/als/bonlezer/worker.py",
        48,
        "src.core.noodstop",
        "noodstop (variant A): opstartpunt van de bonlezer-worker laadt de adapter van de modeldeur (`from src.core.noodstop import model_deur`)",
    ),
    (
        "src/core/learning/worker.py",
        63,
        "src.core.noodstop",
        "noodstop (variant A): opstartpunt van de learning-worker laadt de adapter van de modeldeur",
    ),
    (
        "src/workers/scheduler.py",
        29,
        "src.core.noodstop",
        "noodstop (variant A): opstartpunt van de scheduler laadt de adapter van de modeldeur",
    ),
    # --- crediteuren dag 2 (+1) ---
    (
        "src/core/services/inkoopfactuur_inlezen.py",
        33,
        "src.core.repositories.payable_repository",
        "crediteuren dag 2: de inleesservice schrijft de factuur via `payable_repository` (echte afhankelijkheid tijdens "
        "het draaien; het modeltype staat onder TYPE_CHECKING en telt niet mee)",
    ),
    # --- crediteuren dag 3 (+1) ---
    (
        "src/core/services/sepa_betaalbestand.py",
        28,
        "src.core.repositories.payable_repository",
        "crediteuren dag 3: het betaalbestand gebruikt `is_sepa_iban` en `probeer_iban` van `payable_repository` (echte afhankelijkheid "
        "tijdens het draaien)",
    ),
]


def _importeert_op_regel(bestand: str, regel: int, doel: str) -> bool:
    boom = ast.parse((_ROOT / bestand).read_text(encoding="utf-8"))
    for knoop in ast.walk(boom):
        if getattr(knoop, "lineno", None) != regel:
            continue
        if (
            isinstance(knoop, ast.ImportFrom)
            and knoop.level == 0
            and (knoop.module or "").startswith(doel)
        ):
            return True
        if isinstance(knoop, ast.Import) and any(a.name.startswith(doel) for a in knoop.names):
            return True
    return False


@pytest.mark.architecture
def test_de_randen_sinds_247_bestaan_nog() -> None:
    """Elke rand in `RANDEN_SINDS_247` staat nog op die regel (de lijst veroudert niet ongemerkt)."""
    weg = [(b, r, d) for b, r, d, _ in RANDEN_SINDS_247 if not _importeert_op_regel(b, r, d)]
    assert not weg, (
        "Deze randen uit RANDEN_SINDS_247 staan niet meer op die regel; werk de regelnummers bij of haal "
        f"de rand weg (en verlaag dan ook het Ce-plafond): {weg}"
    )
    assert all(reden.strip() for _, _, _, reden in RANDEN_SINDS_247)


@pytest.mark.architecture
def test_agent_runtime_ce_dag1_intermediate_target() -> None:
    """SP-DSM-008 Dag 1: Ce na config+tracing+di reclassificatie moet <=285 zijn.

    Behaalde reductie: 311 -> 285 (-26).
    Reclassificaties: src.config, src.core.config (incl. feature_flags override),
    src.core.di, src.core.observability.tracing -> shared.

    src.core.models is NIET herclassificeerd: models/__init__.py importeert
    uit auth en governance -- herclassificatie als shared is architectureel incorrect
    totdat de aggregator-import verwijderd is.

    Dag 2 target: Ce <= 223 (I <= 0.50) via src.core.database reclassificatie.
    """
    result = calculate_instability("agent_runtime", exclude_shared=True)
    ce = result["fan_out"]
    assert ce <= 285, (
        f"agent_runtime Ce={ce} > Dag 1 ceiling 285. "
        "Regressie gedetecteerd: controleer recente MODULE_MAP wijzigingen "
        "of nieuwe infra-imports in agent_runtime bestanden."
    )


@pytest.mark.architecture
def test_agent_runtime_ce_dag2_final_target() -> None:
    """SP-DSM-008 Dag 2 + SP-DSM-009 + BE-AGT-057 reclassificatie: Ce moet <=227.

    SP-DSM-008 Dag 2 bereikte Ce=222 via database.database+resilience -> shared.
    SP-DSM-009 reclassificeerde container.py naar agent_runtime SOURCE_DIRS (+3 Ce):
    container.py's cross-bucket imports (infra, integrations) tellen nu mee als
    agent_runtime Ce. Dit is de verwachte trade-off voor het sluiten van agent_runtime<->infra.

    **Plafond opgehoogd 2026-08-21 (fix-sprint dag 8, BE-AGT-057/ADR036-ADR015-001/OP-24,
    +2 Ce, 225 -> 227).** `EnhancedBaseAgent.execute_tool()` kreeg een agent-laag
    denylist-precheck (defense-in-depth naast de al-bestaande broker-laag-blokkade) die
    `src.core.tool_broker.exceptions.ToolExecutionException` en (voor de isinstance-guard-
    fallback) `src.core.tool_broker.permission_manager.ToolPermissionManager` importeert --
    twee nieuwe, bewuste `agent_runtime -> tool_broker`-edges voor een security-relevante
    functie, geen incidentele koppeling. Zelf gemeten dat de instability-grens niet raakt:
    `I = Ce/(Ce+Ca) = 227/(227+193) = 0,5405`, ruim onder de actuele 0,55-drempel uit
    SP-DSM-014 (`test_dsm_grade_a_plus.py::test_agent_runtime_instability_grade_a_plus`) --
    de `I<=0,50`-vermelding in deze docstring en in module-docstring hierboven was al voor
    vandaag verouderd t.o.v. die latere, gezaghebbende drempel-aanpassing en werd door geen
    enkele test hier daadwerkelijk afgedwongen (zelf bevestigd: alle Grade-A+-tests bleven
    groen voor en na deze wijziging).

    **Plafond opgehoogd 2026-09-16 (ADR-036 OP-153, +7 Ce, 227 -> 234.)** De oorzaak is
    per bestand gemeten door de infra-imports van `agent_runtime` te vergelijken met
    `origin/develop`; ALLE nieuwe randen zijn dezelfde import:

        from src.core.database.bypass_session import adopt_tenant

    in `als/agents/memory.py`, `als/collective/collective_memory.py`,
    `learning/worker.py`, `services/tenant_service.py`,
    `domains/agentic/seeds/run_seeds.py` en `seeder.py`, plus
    `agents/adapters/tenant_context.py`. Reden: deze modules schrijven in tabellen met een
    afschermingsregel en draaien buiten elk verzoek, dus zonder aangenomen klant raken hun
    UPDATEs en DELETEs na de omschakeling naar `sanskritisetu_app` nul rijen ZONDER
    foutmelding (gemeten 2026-09-15 op PostgreSQL 15.19).

    Dit is dezelfde soort afweging als de ophoging van 2026-08-21 hierboven: bewuste,
    security-relevante koppeling, geen incidentele. Zelf nagemeten dat de gezaghebbende
    grens niet wordt geraakt: `I = Ce/(Ce+Ca) = 234/(234+197) = 0,5429`, onder de
    0,55-drempel uit SP-DSM-014
    (`test_dsm_grade_a_plus.py::test_agent_runtime_instability_grade_a_plus`), en Ce=234
    ligt ruim onder het Ce<=700-plafond van `test_agent_runtime_instability_ceiling`.

    **Plafond opgehoogd 2026-09-22 (InputGuard, +2 Ce, 234 -> 236.)** Twee nieuwe randen
    `agent_runtime -> governance`, allebei dezelfde import:

        from src.core.governance.input_guard import beoordeel

    in `als/agents/specialist_base.py::_reject_before_council` en
    `copilot/service.py::handle_turn` -- de twee deuren waar vrije tekst het systeem
    binnenkomt. Reden: de Council beoordeelt de VORM van een actie en krijgt per ontwerp
    alleen de toolnaam en de argumentNAMEN (BE-AGT-043, ADR-036 OP-25), omdat alles wat hij
    ziet de onuitwisbare ADR-019-keten in gaat. Een BSN in een vrije opdracht reisde daardoor
    ongehinderd langs de hele governance-laag; op het chatpad stond zelfs helemaal geen
    inhoudscontrole (gemeten 2026-09-21: nul treffers op `detect_pii` in `copilot/service.py`).

    Zelf nagemeten dat de gezaghebbende grens niet wordt geraakt: `I = Ce/(Ce+Ca) =
    236/(236+201) = 0,5400`, onder de 0,55-drempel uit SP-DSM-014
    (`test_dsm_grade_a_plus.py::test_agent_runtime_instability_grade_a_plus`), die bij deze
    Ca pas bij Ce=245 breekt. Ce=236 ligt ruim onder het Ce<=700-plafond van
    `test_agent_runtime_instability_ceiling`.

    Overwogen en NIET gedaan: de wachter in de `shared`-bak zetten. Die telt niet mee in de
    fan-out, dus het getal was op 234 gebleven -- en precies daarom is het verkeerd. Een
    inhoudswachter die AVG-categorieen toetst is een governance-zorg en hoort naast
    `gdpr_enforcer.py`, wiens detector hij hergebruikt. Hem elders parkeren om de meter te
    ontwijken is de optimalisatie waar de docstring van `scan_module` zelf voor waarschuwt.

    Overwogen en NIET gedaan: alle zes de plekken door een enkele doorgang laten lopen om
    het getal laag te houden. Deze bestanden zitten in verschillende pakketten (`als`,
    `learning`, `services`, `domains/agentic`) en horen alleen in DEZE bucket bij elkaar;
    een gedeelde doorgang zou een kunstmatige koppeling zijn die alleen de meter dient.
    De docstring van `scan_module` waarschuwt zelf voor precies dat soort optimalisatie.

    **Plafond opgehoogd 2026-09-23 (BE-LLM-004, +4 Ce, 236 -> 240).** Drie randen komen uit EEN
    functie, `tenant_llm_provider_service.bouw_tenant_llm_service()`:

        from src.core.repositories.tenant_llm_provider_repository import ...   (infra, 103->104)
        from src.core.security.llm_endpoint_policy import ...                  (auth, 15->16)
        from src.core.security.tenant_secret_encryption import ...             (auth, 16->17)

    De vierde kwam er bij in de Gate 2-ronde, en het is de interessantste:

        from src.core.database.session import get_db_session                   (infra, 104->105)

    in `als/agents/specialist_base.py`. Die module werd daar al gebruikt, maar via
    `importlib.import_module` met als opgeschreven reden "om het koppelingsbudget van
    agent_runtime niet te belasten". Een reviewer legde die regel naast de alinea hieronder,
    waarin staat dat verstoppen achter `importlib` bewust NIET is gedaan. Twee teksten in
    dezelfde wijziging die elkaar tegenspreken, en de code volgde de verkeerde. Nu staat de
    import er gewoon en is de rand betaald.

    Gemeten door de bak op `origin/develop` (0a69e1ab) en op deze wijziging te scannen en de
    uitkomsten per doelbak te vergelijken -- niet afgeleid uit de diff.

    Reden dat deze koppeling ECHT is en geen boekhouding: fase 2b laat een agent het taalmodel
    van zijn eigen klant gebruiken. Daarvoor moet de opgeslagen sleutel worden ONTSLEUTELD
    (security), moet het opgeslagen adres opnieuw worden GECONTROLEERD (security) en moet de
    rij uit de opslag komen (infra). Dat zijn geen incidentele imports maar de drie dingen die
    het gebruik van een klantsleutel per definitie vereist.

    Overwogen en NIET gedaan: de drie imports via `importlib.import_module` binnenhalen. Dat
    werkt -- deze codebase doet het op drie plekken en de scanner ziet ze dan niet -- en het is
    precies daarom fout: het verlaagt de meter zonder de afhankelijkheid te verlagen. Betalen
    en opschrijven is eerlijker dan verstoppen.

    Overwogen en NIET gedaan: de montage in de API-laag laten (waar hij al stond) en de agent
    hem laten meekrijgen. Die laag bestaat niet op het agentpad -- een agent draait in een
    worker, buiten elk verzoek. De randen zouden dan alleen van bestand verhuizen, niet
    verdwijnen.

    Zelf nagemeten dat de gezaghebbende grens niet wordt geraakt: `I = Ce/(Ce+Ca) =
    240/(240+201) = 0,5442`, onder de 0,55-drempel, die bij deze Ca pas bij Ce=245 breekt.
    Er is dus nog ruimte voor vijf randen; wie de zesde nodig heeft, heeft een
    architectuurgesprek en geen plafondverhoging.

    **Plafond opgehoogd 2026-10-07 (debiteuren Keten B, +2 Ce, 240 -> 242).** Twee nieuwe
    import-statements in `src/workers/scheduler.py`, in de lazy runners (bak agent_runtime ->
    worker):

        from src.core.tasks.debiteuren_tasks import verstuur_klare_berichten   (regel 422)
        from src.core.tasks.debiteuren_tasks import volg_debiteuren_op         (regel 428)

    Gemeten: de test slaagt op 9ba375b2 en 6496951d en faalt op b66264fd (Ce=241) en op
    e518ce3d (Ce=242). Er komt geen nieuwe afhankelijkheid tussen bakken bij: de scheduler
    importeerde al actors uit de worker-bak. Kanttekening: `scripts/dsm_full_analysis.py::
    scan_module` telt import-STATEMENTS, dus elke nieuwe ingeplande job verhoogt Ce met 1.
    Overwogen en NIET gedaan: de import verstoppen via `get_actor` (afhankelijkheid blijft,
    de meter wordt blind) en `debiteuren_tasks` herclassificeren naar agent_runtime
    (onderbouwing te dun).

    **Plafond opgehoogd 2026-10-08 (wfb-dag1 stap 1, +1 Ce, 242 -> 243).** Een nieuw
    import-statement in `src/domains/flows/service.py` (bak agent_runtime -> integrations):

        from src.core.activepieces.stappencontrole import (...)

    De focus-builderdienst moet een flow met een uitgaande stap weigeren VOOR hij hem lokaal
    opslaat (de AP-sync daarna slikt elke fout in). Geen nieuw bakkenpaar: dezelfde module
    importeerde al `activepieces.client` en `activepieces.transformer`. Gemeten: Ce=243 met deze
    wijziging, 242 zonder. I = 243/(243+201) = 0,547, onder 0,55. Overwogen en NIET gedaan: de
    namen via `activepieces.client` laten lopen (meter lager, afhankelijkheid gelijk).
    """
    result = calculate_instability("agent_runtime", exclude_shared=True)
    ce = result["fan_out"]
    # 2026-10-07: 240 -> 242 voor twee nieuwe scheduler-imports van debiteuren_tasks (regel 422
    # en 428 in src/workers/scheduler.py). Geen nieuwe afhankelijkheid tussen bakken; de meter
    # telt import-statements, niet bakparen.
    # 2026-10-08: 242 -> 243 voor de stappencontrole in src/domains/flows/service.py (wfb-dag1).
    # 2026-10-12: 243 -> 244 voor de lazy import van `signaleer_hr_termijnen` in
    # src/workers/scheduler.py (HR-pilot dag 4). Elke nieuwe ingeplande job is +1 (zie 2026-10-07);
    # geen nieuw bakkenpaar, de scheduler importeerde al taken uit src/core/tasks.
    # 2026-10-25: 245 -> 246 voor `src/core/services/inkoopfactuur_inlezen.py` -> `payable_repository` (crediteuren dag 2; gemeten Ce=246,
    # echte afhankelijkheid tijdens het draaien; het modeltype staat onder TYPE_CHECKING en telt niet mee).
    # 2026-10-17: 244 -> 245 voor de lazy import van `ruim_bonnen_op` in src/workers/scheduler.py
    # (bonlezer dag 4, opruiming van bonnen na 30 dagen). Gemeten: met de scheduler van cdc17f3a op
    # dezelfde boom slaagt de test (244), met de nieuwe regel is Ce=245. Zelfde regel als 2026-10-07:
    # een nieuwe ingeplande job is +1, geen nieuw bakkenpaar.
    # 2026-10-21: 245 -> 247 voor de noodstop-chatdeuren (ADR-036 OP-03, ronde 2, besluit A).
    # Gemeten: zonder deze ronde is Ce=245, met de nieuwe guard-imports 247. De nieuwe paren (afgeleid uit de diff, niet per paar gemeten) zijn
    # `core/copilot/service.py` en `domains/agentic/services/chat_service.py` naar `src.core.noodstop`
    # (elke chat-ingang MOET de stand controleren; de architectuurtest
    # test_elke_deur_controleert_de_noodstop dwingt dat af, dus een facade verbergt de rand alleen)
    # en de lazy import in `core/tasks/eigen_loop.py` (de actor-run-engine). Bewuste veiligheidsranden.
    # 2026-10-22: 247 -> 258 bij de samenvoeging van `origin/develop` (`df79d145`) en de nieuwe meter
    # (`9cc83edc`, telt `import x`) in de noodstoptak, EXACT de gemeten waarde met die meter:
    # `9cc83edc` alleen = 245 (develop 243 + providers 1 + meter 1), de noodstoptak heeft er 13 bij: de
    # tien deuren van ronde 1 en 2 (`from src.core.noodstop...`) en de drie opstartpunten die in agent_runtime
    # vallen (bonlezer-worker, learning-worker, scheduler; hertoets variant A). I = 258/(258+212) = 0,549, onder
    # 0,55 zonder die grens te wijzigen. ELKE verhoging sinds 247 staat per rand (bestand, regel, doel, reden)
    # in `RANDEN_SINDS_247` bovenaan dit bestand, en `test_de_randen_sinds_247_bestaan_nog` controleert die lijst.
    # Een oudere remark ("adapter-imports op opstartpunten zijn `import x` en tellen niet") is vervallen: de meter
    # telt `import x` sinds `9cc83edc`.
    # 2026-10-23: 258 -> 250 (enkele ingang `services/noodstop_toegang.py`), gemeten: Ce=250, Ca=207, I=0,5470
    # (na samenvoeging van `76934611`, dat Ca van 212 naar 207 bracht: zonder ingang was I = 258/465 = 0,5548 > 0,55).
    # Negen deur-imports van `src.core.noodstop` werden een import van de ingang (-8 netto). De afhankelijkheid
    # bestaat nog: ze loopt door een rand. `test_agent_runtime_importeert_noodstop_alleen_via_de_ingang` houdt
    # de directe koppeling eruit. De grens van 0,55 is niet gewijzigd.
    # 2026-10-26: 250 -> 252 na de samenvoeging van `origin/develop` (4b5ef97c) in de crediteurentak, gemeten: Ce=252 (develop 250;
    # de test gaf 252 > 250). Twee randen, afgeleid uit de diff en niet per paar gemeten: `services/inkoopfactuur_inlezen.py` en
    # `services/sepa_betaalbestand.py` importeren beide `payable_repository` (crediteuren dag 2 en 3; echte afhankelijkheden tijdens het
    # draaien, de modeltypen staan onder TYPE_CHECKING). I = 252/(252+207) = 0,5490, onder 0,55 zonder die grens te wijzigen.
    # 2026-11-03: 252 -> 255 (Het Levend Monument, akkoord eigenaar), gemeten: Ce=254 op
    # iter/sync-upstream-2026-11-01 (290b4f023, twee randen uit de upstream-sync) en Ce=255 op
    # feat/verhaal-insturen. De ene eigen rand: `services/foundation_accounts.py` ->
    # `models.foundation_content` (BE-EP-056, opruimen van ongebruikte bezoekersaccounts in de
    # nachtelijke job). De twee sync-randen zijn niet per paar uitgezocht; dat hoort bij de
    # volgende samenvoeging met develop.
    assert ce <= 255, (
        f"agent_runtime Ce={ce} > ceiling 255. "
        "Regressie gedetecteerd: controleer recente MODULE_MAP wijzigingen "
        "of nieuwe imports in agent_runtime bestanden."
    )
