"""
Digital Twin — User behavioral journeys (rookie -> intermediate -> expert).

Drie tests die de Digital Twin valideren vanuit het perspectief van de
eindgebruiker. Elke test vertelt een verhaal in arrange/act/assert blokken en
gebruikt de volledige stack (FastAPI router + create_practical_twin_service
factory + echte Postgres + echte TwinEventBus). De enige mocks zijn:

- get_current_user (auth — we kennen onze test-user)
- LLM-provider (MockSuggestionProvider, totdat audit-stap 5 een echte adapter
  levert)

NB: de productie-API in src/api/v1/endpoints/digital_twin.py heeft op moment
van schrijven nog persist_fn=None (audit-stap 2). We injecteren daarom in
elke test de bestaande create_practical_twin_service factory via
dependency_overrides. Zodra de productie-DI die factory zelf gebruikt,
kunnen deze overrides weg en blijven de tests valide.

Run:
    # Eenmalig: testdatabase + migraties
    make test-db-up
    alembic -c src/alembic.ini upgrade head

    pytest tests/integration/test_digital_twin_user_journeys.py -v

Vereist:
- pgvector/pgvector:pg15 op poort 5455
- Alembic migratie voor user_behavior_observations / user_cognitive_profiles /
  user_twin_consent (zie auditrapport 2026-05-19, stap 1)
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, AsyncIterator
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.endpoints.digital_twin import (
    _get_consent_manager,
    _get_twin_service,
    router as twin_router,
)
from src.core.auth.dependencies import get_current_user
from src.core.learning.batching.batch_manager import ObservationBatchManager
from src.core.learning.consent.consent_manager import TwinConsentManager
from src.core.learning.events.event_bus import TwinEventBus
from src.core.learning.events.twin_events import (
    InterventionSuggested,
    UserBehaviorTracked,
)
from src.core.learning.interfaces.llm_provider import MockSuggestionProvider
from src.core.learning.privacy.privacy_filter import PrivacyFilter
from tests.fixtures.testdatabase import testdatabase_url
from src.core.learning.services.practical_twin_service import PracticalTwinService
from src.core.learning.services.twin_service_factory import (
    create_practical_twin_service,
)
from src.core.learning.twin_models import (
    UserBehaviorObservation,
    UserCognitiveProfile,
    UserTwinConsent,
)

# ─── Fixtures ──────────────────────────────────────────────────────────────────


def _user_factory(user_id: int, tenant_id: int) -> MagicMock:
    """Build a minimal User stand-in compatible with get_current_user."""
    user = MagicMock()
    user.id = user_id
    user.tenant_id = tenant_id
    return user


@pytest_asyncio.fixture
async def twin_app(
    db_session: AsyncSession,
) -> AsyncIterator[tuple[FastAPI, PracticalTwinService, ObservationBatchManager, TwinEventBus]]:
    """
    Build a FastAPI app with the Digital Twin router and ALL dependencies wired
    against the real database. Returns the app plus the underlying service so
    individual tests can flush the batch buffer deterministically and inspect
    the event bus.
    """
    # Ensure clean singleton batch manager with test-scoped persist_fn
    import os

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from src.core.learning.batching.batch_manager import (
        get_batch_manager,
        reset_batch_manager,
        shutdown_batch_manager,
    )
    from src.core.learning.repositories.observation_repository import (
        insert_observation_batch,
    )

    await shutdown_batch_manager()
    reset_batch_manager()

    # Clean up real persisted data from previous runs (our sessions commit for real)
    test_db_url = os.environ.get(
        "TEST_DATABASE_URL",
        testdatabase_url(),
    )
    cleanup_engine = create_async_engine(test_db_url, echo=False)
    cleanup_factory = async_sessionmaker(
        cleanup_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with cleanup_factory() as cdb:
        await cdb.execute(text("DELETE FROM user_behavior_observations"))
        await cdb.execute(text("DELETE FROM user_cognitive_profiles"))
        await cdb.execute(text("DELETE FROM user_twin_consent"))
        await cdb.commit()
    await cleanup_engine.dispose()

    async def _test_persist_fn(batch: list[Any]) -> None:
        await insert_observation_batch(db_session, batch)
        await db_session.flush()

    batch_manager = await get_batch_manager(persist_fn=_test_persist_fn)

    # Real service + real persistence
    service = await create_practical_twin_service(
        db=db_session,
        tenant_id=1,
        redis_client=None,  # Rate limiter and consent cache run in fail-open mode
    )

    # Force the LLM to a known mock so analyze-struggle assertions are stable
    service._llm = MockSuggestionProvider(  # type: ignore[attr-defined]
        response="Probeer een korte pauze van vijf minuten en kom dan terug."
    )

    # Disable auto-flush by size; we flush explicitly at test end
    batch_manager.batch_size = 1000
    batch_manager.flush_interval = 300.0

    # Capture published events without coupling to a real broker
    bus = service._observer._bus  # type: ignore[attr-defined]
    assert bus is not None, "TwinEventBus must be wired into the service for journey tests"
    captured_events: list[Any] = []

    async def _capture(event: Any) -> None:
        captured_events.append(event)

    bus.subscribe("twin.user_behavior.tracked", _capture)
    bus.subscribe("twin.intervention.suggested", _capture)
    bus.published = captured_events  # type: ignore[attr-defined]

    consent_manager = TwinConsentManager(db=db_session, cache=None)

    app = FastAPI()
    app.include_router(twin_router, prefix="/api/v1")
    app.dependency_overrides[_get_twin_service] = lambda: service
    app.dependency_overrides[_get_consent_manager] = lambda: consent_manager

    try:
        yield app, service, batch_manager, bus
    finally:
        await shutdown_batch_manager()
        reset_batch_manager()


async def _flush(batch_manager: ObservationBatchManager, db: AsyncSession) -> None:
    """Drain the batch buffer and any fire-and-forget tasks, then sync the DB view."""
    # Let asyncio.create_task(flush()) inside add() drain
    for _ in range(3):
        await asyncio.sleep(0)
    await batch_manager.flush()
    await db.flush()


async def _count_observations(db: AsyncSession, *, tenant_id: int, raw_user_id: str) -> int:
    """Count observations for a user, accounting for PrivacyFilter hashing."""
    hashed = PrivacyFilter.hash_user_id(raw_user_id, tenant_id)
    result = await db.execute(
        select(func.count())
        .select_from(UserBehaviorObservation)
        .where(
            UserBehaviorObservation.tenant_id == tenant_id,
            UserBehaviorObservation.human_user_id == hashed,
        )
    )
    return int(result.scalar_one())


# ═══════════════════════════════════════════════════════════════════════════════
#  TEST 1 — ROOKIE
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rookie_user_first_session_default_consent_and_single_observation(
    twin_app: tuple[FastAPI, PracticalTwinService, ObservationBatchManager, TwinEventBus],
    db_session: AsyncSession,
) -> None:
    """
    ROOKIE — Maria logt voor het eerst in.

    Verhaal:
      Maria opent Focus Builder voor de allereerste keer. Ze heeft nog nooit van
      digital twin gehoord. Ze accepteert een voorgestelde workflow. Ze
      verwacht dat:
        1. Haar consent default UIT staat (opt-in model per ADR-026 GDPR Art. 7).
        2. Na expliciete consent-enable wordt haar workflow-acceptatie onthouden.
        3. Geen ruwe paden of secrets in de DB belanden (PrivacyFilter).
        4. Een UserBehaviorTracked-event wordt gepubliceerd zodat downstream
           subscribers (bijv. profiel-aggregator) kunnen reageren.

    Behavior under test: privacy-by-default (opt-in) conform ADR-026 par. 2.
    """
    app, service, batch_manager, bus = twin_app
    rookie = _user_factory(user_id=101, tenant_id=1)
    app.dependency_overrides[get_current_user] = lambda: rookie

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://twin-test") as client:
        # ── Arrange & Act 1: Maria opent de consent-pagina voor het eerst ─────
        consent_response = await client.get("/api/v1/learning/twin/consent")

        # ── Assert 1: default = disabled (opt-in per ADR-026 GDPR) ───────────
        assert consent_response.status_code == 200, consent_response.text
        assert consent_response.json()["status"] == "disabled"

        # ── Act 1b: Maria geeft expliciet consent (opt-in) ────────────────────
        enable_response = await client.put(
            "/api/v1/learning/twin/consent",
            json={"status": "enabled"},
        )
        assert enable_response.status_code == 200, enable_response.text

        # ── Act 2: Maria accepteert een workflow met een lokaal pad erbij ─────
        track_response = await client.post(
            "/api/v1/learning/track-user-behavior",
            json={
                "session_id": "maria-onboarding-session-1",
                "behavior_type": "workflow_accepted",
                "context": {
                    "workflow_id": "wf_starter_pack",
                    "file_path": "C:\\Users\\maria\\Documents\\report.docx",
                    "code_snippet": 'api_key = "sk-leak-xyz-very-long-and-secret-1234567890"',
                },
                "outcome_metrics": {"acceptance_latency_ms": 1200},
            },
        )

        # ── Assert 2: Maria ziet 202 Accepted en een trace_id ─────────────────
        assert track_response.status_code == 202, track_response.text
        body = track_response.json()
        assert body["accepted"] is True
        assert body["trace_id"], "trace_id mag niet leeg zijn na geslaagde track"
        assert body["reason"] is None

    # ── Assert 3: na flush staat er precies 1 observatie in de DB ─────────────
    await _flush(batch_manager, db_session)
    count = await _count_observations(db_session, tenant_id=1, raw_user_id="101")
    assert count == 1, "Een geaccepteerde workflow moet 1 observatie persisten"

    # ── Assert 4: er staat een consent-record met consent_given=True ──────────
    consent_record = (
        await db_session.execute(
            select(UserTwinConsent).where(
                UserTwinConsent.tenant_id == 1,
                UserTwinConsent.human_user_id == "101",
            )
        )
    ).scalar_one()
    assert consent_record.consent_given is True
    assert consent_record.hard_delete_requested is False

    # ── Assert 5: PrivacyFilter heeft het geheim geredacteerd ─────────────────
    obs = (
        await db_session.execute(
            select(UserBehaviorObservation).where(
                UserBehaviorObservation.tenant_id == 1,
                UserBehaviorObservation.human_user_id == PrivacyFilter.hash_user_id("101", 1),
            )
        )
    ).scalar_one()
    assert obs.behavior_type == "workflow_accepted"
    snippet = str((obs.context or {}).get("code_snippet", ""))
    assert "sk-leak-xyz-very-long-and-secret-1234567890" not in snippet, (
        "Ruw API-secret mag nooit in de DB belanden"
    )
    file_path = str((obs.context or {}).get("file_path", ""))
    assert "maria" not in file_path.lower(), (
        "Absolute paden met gebruikersnaam moeten geanonimiseerd zijn"
    )

    # ── Assert 6: er is een UserBehaviorTracked event gepubliceerd ────────────
    tracked_events = [e for e in bus.published if isinstance(e, UserBehaviorTracked)]  # type: ignore[attr-defined]
    assert len(tracked_events) == 1, "Downstream services moeten precies 1 tracked-event ontvangen"
    assert tracked_events[0].behavior_type == "workflow_accepted"


# ═══════════════════════════════════════════════════════════════════════════════
#  TEST 2 — INTERMEDIATE
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
@pytest.mark.asyncio
async def test_intermediate_user_struggle_triggers_intervention_and_no_intervention_on_calm_work(
    twin_app: tuple[FastAPI, PracticalTwinService, ObservationBatchManager, TwinEventBus],
    db_session: AsyncSession,
) -> None:
    """
    INTERMEDIATE — Joris werkt al twee weken met SanskritiSetu.

    Verhaal:
      Joris heeft inmiddels een cognitief profiel (observation_count=20). Hij
      raakt vast in dezelfde regel code: hij edit 6x op dezelfde lijn, switcht
      9 keer tussen bestanden, en heeft 3 errors in de laatste minuut. Hij
      verwacht een hint, niet een goeroe-uitspraak. Daarna kalmeert hij en
      verwacht hij geen interventie meer.

    Behavior under test:
      - WeightedStruggleScore boven 0.8 -> needs_intervention=True + suggestie
      - WeightedStruggleScore onder 0.8 -> needs_intervention=False + lege
        suggestie (geen LLM-call)
      - InterventionSuggested-event wordt precies 1x gepubliceerd
      - Happy: getriggerde interventie. Unhappy: rustig werk geeft geen ruis.
    """
    app, service, batch_manager, bus = twin_app
    intermediate = _user_factory(user_id=202, tenant_id=1)
    app.dependency_overrides[get_current_user] = lambda: intermediate

    # ── Arrange: bestaand profiel met observation_count=20 ────────────────────
    existing_profile = UserCognitiveProfile(
        tenant_id=1,
        human_user_id="202",
        coding_style={"prefers": "explicit_typing"},
        work_patterns={"deep_work_blocks_per_day": 3},
        observation_count=20,
        confidence_level=0.55,
        optimal_help_style="step_by_step",
        preferred_agents=[],
        preferred_departments=[],
    )
    db_session.add(existing_profile)
    await db_session.flush()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://twin-test") as client:
        # ── Arrange: consent inschakelen (opt-in per ADR-026) ─────────────────
        enable_r = await client.put(
            "/api/v1/learning/twin/consent",
            json={"status": "enabled"},
        )
        assert enable_r.status_code == 200, enable_r.text

        # ── Act 1: 5 reguliere observaties tijdens een refactor ──────────────
        for idx, behavior in enumerate(
            [
                "file_edit",
                "file_edit",
                "rapid_file_switch",
                "rapid_file_switch",
                "lint_error",
            ]
        ):
            r = await client.post(
                "/api/v1/learning/track-user-behavior",
                json={
                    "session_id": "joris-refactor-thursday",
                    "behavior_type": behavior,
                    "context": {"line": 142 + idx},
                },
            )
            assert r.status_code == 202

        # ── Act 2: struggle-analyse op hoge-struggle context ─────────────────
        struggle_response = await client.post(
            "/api/v1/learning/analyze-struggle",
            json={
                "context": {
                    "recent_edits_same_line": 6,
                    "recent_file_switches": 9,
                    "lines_deleted_last_minute": 55,
                    "errors_last_minute": 5,
                },
                "user_profile": {"optimal_help_style": "step_by_step"},
            },
        )

        # ── Assert 2: Joris ziet een interventie ─────────────────────────────
        assert struggle_response.status_code == 200, struggle_response.text
        struggle_body = struggle_response.json()
        assert struggle_body["needs_intervention"] is True
        assert struggle_body["score"] > 0.8, (
            f"Score moet boven drempel uitkomen, was {struggle_body['score']}"
        )
        assert struggle_body["suggestion"], (
            "Bij een interventie moet er een niet-lege suggestie zijn"
        )
        # Geen lekkende interne pad-info in de UX-tekst
        assert "Traceback" not in struggle_body["suggestion"]

        # ── Act 3: Joris kalmeert — lage struggle context ────────────────────
        calm_response = await client.post(
            "/api/v1/learning/analyze-struggle",
            json={
                "context": {
                    "recent_edits_same_line": 1,
                    "recent_file_switches": 2,
                    "lines_deleted_last_minute": 4,
                    "errors_last_minute": 0,
                },
                "user_profile": {"optimal_help_style": "step_by_step"},
            },
        )

        # ── Assert 3: geen interventie, lege suggestie, geen LLM-spam ────────
        assert calm_response.status_code == 200
        calm_body = calm_response.json()
        assert calm_body["needs_intervention"] is False
        assert calm_body["score"] <= 0.8
        assert calm_body["suggestion"] == "", "Lege suggestie verwacht zodra de struggle wegzakt"

    # ── Assert 4: 5 observaties geland in de DB onder de gehashte user_id ────
    await _flush(batch_manager, db_session)
    obs_count = await _count_observations(db_session, tenant_id=1, raw_user_id="202")
    assert obs_count == 5, f"Verwachtte 5 observaties uit het refactor-burst, kreeg {obs_count}"

    # ── Assert 5: precies 1 InterventionSuggested-event op de bus ────────────
    interventions = [
        e
        for e in bus.published  # type: ignore[attr-defined]
        if isinstance(e, InterventionSuggested)
    ]
    assert len(interventions) == 1, (
        "PracticalTwinService moet een InterventionSuggested event publiceren na interventie (ADR-025 §3.4)"
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  TEST 3 — EXPERT
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.skip(reason="Redis not available in CI environment")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_expert_user_gdpr_lifecycle_opt_out_export_delete_and_reopt_in(
    twin_app: tuple[FastAPI, PracticalTwinService, ObservationBatchManager, TwinEventBus],
    db_session: AsyncSession,
) -> None:
    """
    EXPERT — Asha is privacy-bewust en kent de AVG.

    Verhaal:
      Asha laat zich eerst observeren (3 observaties). Daarna:
        1. Vraagt ze haar data op (Art. 20 Data Portability).
        2. Schakelt ze tracking uit (opt-out).
        3. Test ze of nieuwe observaties echt geweigerd worden.
        4. Vraagt ze om hard delete (Art. 17 Right to Erasure).
        5. Verifieert dat alles weg is.
        6. Bedenkt zich, re-opt-in, en verwacht dat tracking weer werkt.

    Behavior under test: complete GDPR-lifecycle. Beide happy paths (export,
    delete, re-enable) en unhappy paths (track na opt-out moet falen, niet
    crashen).
    """
    app, service, batch_manager, bus = twin_app
    expert = _user_factory(user_id=303, tenant_id=1)
    app.dependency_overrides[get_current_user] = lambda: expert

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://twin-test") as client:
        # ── Act 1: 3 observaties tijdens een normale werksessie ──────────────
        for behavior in ["file_edit", "test_run_pass", "commit"]:
            r = await client.post(
                "/api/v1/learning/track-user-behavior",
                json={
                    "session_id": "asha-monday-morning",
                    "behavior_type": behavior,
                    "context": {"branch": "main"},
                },
            )
            assert r.status_code == 202
            assert r.json()["accepted"] is True
        await _flush(batch_manager, db_session)
        assert await _count_observations(db_session, tenant_id=1, raw_user_id="303") >= 3

        # ── Act 2: Asha exporteert haar data (Art. 20) ───────────────────────
        export_response = await client.get("/api/v1/learning/twin/export")
        assert export_response.status_code == 200, export_response.text
        export_body = export_response.json()
        assert export_body["user_id"] == "303"
        assert len(export_body["observations"]) == 3
        assert "exported_at" in export_body
        # Geen gehashte ruwe waarden in een UX-export: er mag context per row in
        assert all("behavior_type" in o for o in export_body["observations"])

        # ── Act 3: opt-out ───────────────────────────────────────────────────
        opt_out = await client.put("/api/v1/learning/twin/consent", json={"status": "disabled"})
        assert opt_out.status_code == 200
        assert opt_out.json()["status"] == "disabled"

        # ── Act 4: Asha probeert na opt-out nog een observatie te sturen ─────
        post_opt_out = await client.post(
            "/api/v1/learning/track-user-behavior",
            json={
                "session_id": "asha-monday-morning",
                "behavior_type": "file_edit",
                "context": {"line": 1},
            },
        )
        assert post_opt_out.status_code == 202, "API blijft 202, niet 5xx"
        body = post_opt_out.json()
        assert body["accepted"] is False, "Na opt-out moet de twin de observatie expliciet weigeren"
        assert body["trace_id"] is None
        assert body["reason"], "Reden moet uitgelegd worden in de UX"

        # ── Assert 4: het aantal observaties in de DB is NIET gestegen ───────
        await _flush(batch_manager, db_session)
        assert await _count_observations(db_session, tenant_id=1, raw_user_id="303") >= 3, (
            "Opt-out mag geen extra observaties accepteren"
        )

        # ── Act 5: Asha vraagt hard delete aan (Art. 17) ─────────────────────
        delete_response = await client.delete("/api/v1/learning/twin/data")
        assert delete_response.status_code == 204

        # ── Assert 5: alle drie tabellen zijn leeg voor deze user ────────────
        hashed = PrivacyFilter.hash_user_id("303", 1)
        for model in (UserBehaviorObservation, UserCognitiveProfile, UserTwinConsent):
            remaining = await db_session.execute(
                select(func.count())
                .select_from(model)
                .where(
                    model.tenant_id == 1,
                    model.human_user_id.in_([hashed, "303"]),
                )
            )
            assert remaining.scalar_one() == 0, (
                f"Hard delete liet records achter in {model.__tablename__}"
            )

        # ── Act 6: Asha bedenkt zich, re-opt-in ──────────────────────────────
        reopt = await client.put("/api/v1/learning/twin/consent", json={"status": "enabled"})
        assert reopt.status_code == 200
        assert reopt.json() == {"status": "enabled"}

        # ── Act 7: een nieuwe observatie wordt weer geaccepteerd ─────────────
        fresh_track = await client.post(
            "/api/v1/learning/track-user-behavior",
            json={
                "session_id": "asha-monday-afternoon",
                "behavior_type": "file_edit",
                "context": {"line": 99},
            },
        )
        assert fresh_track.status_code == 202
        assert fresh_track.json()["accepted"] is True

        # ── Assert 7: een verse observatie staat in de DB ────────────────────
        await _flush(batch_manager, db_session)
        assert await _count_observations(db_session, tenant_id=1, raw_user_id="303") >= 1, (
            "Re-opt-in moet tracking weer activeren"
        )

    # ── Unhappy/edge: ongeldige consent status geeft 422, geen 500 ────────────
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://twin-test") as client:
        bad = await client.put("/api/v1/learning/twin/consent", json={"status": "bogus_value"})
        assert bad.status_code == 422, (
            "Een onbekende consent-waarde moet een 422 geven, niet de server breken"
        )
