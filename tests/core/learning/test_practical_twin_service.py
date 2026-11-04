"""
Unit tests voor PracticalTwinService + WeightedStruggleScore.

Controleert:
- WeightedStruggleScore berekening per factor
- Drempelwaarde voor interventie (> 0.8)
- Maximale score = 1.0
- Nul score bij lege context
- PracticalTwinService.track_behavior() delegeert naar observer
- PracticalTwinService.analyze_struggle() geeft juiste output
- LLM fout → geen crash, lege suggestie
- Geen interventie onder drempel
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.learning.interfaces.llm_provider import MockSuggestionProvider
from src.core.learning.observers.user_behavior_observer import UserBehaviorObserver
from src.core.learning.services.practical_twin_service import (
    PracticalTwinService,
    WeightedStruggleScore,
)


@pytest.fixture(autouse=True)
def _tenant_context_like_production():
    """Zet de tenant-ContextVar die productie altijd heeft.

    `init_tenant_auto_filtering()` (app_lifespan) registreert een globale
    `do_orm_execute`-listener die elke ORM-query filtert op de tenant uit de ContextVar, en
    die is fail-secure: geen tenant betekent NUL rijen. In productie staat die listener dus
    altijd aan en is er altijd een tenant.

    Deze tests slaagden alleen zolang die listener toevallig niet geregistreerd was in hun
    xdist-worker -- dus in een configuratie die in productie nooit voorkomt. Draait
    `tests/unit/test_tenant_query_filter.py` eerder in dezelfde worker, dan vallen ze om.
    Reproduceerbaar door beide bestanden achter elkaar te draaien. Zie OP-20.

    Deze fixture maakt de tests realistischer, niet toleranter.
    """
    from src.core.middleware.tenant_context import set_tenant_id

    set_tenant_id(1)
    yield
    set_tenant_id(None)


class TestWeightedStruggleScore:
    """Tests voor de WeightedStruggleScore berekening."""

    def test_zero_context_returns_zero(self):
        score = WeightedStruggleScore.calculate({})
        assert score == 0.0

    def test_max_regedit_loops_contributes_04(self):
        """10+ edits op dezelfde regel → factor regedit_loops = 0.4"""
        ctx = {"recent_edits_same_line": 10}
        score = WeightedStruggleScore.calculate(ctx)
        assert score == pytest.approx(0.4, abs=0.001)

    def test_max_file_switching_contributes_03(self):
        """8+ bestandswissels → factor rapid_file_switching = 0.3"""
        ctx = {"recent_file_switches": 8}
        score = WeightedStruggleScore.calculate(ctx)
        assert score == pytest.approx(0.3, abs=0.001)

    def test_max_delete_contributes_02(self):
        """50+ verwijderde regels → factor delete_heavy = 0.2"""
        ctx = {"lines_deleted_last_minute": 50}
        score = WeightedStruggleScore.calculate(ctx)
        assert score == pytest.approx(0.2, abs=0.001)

    def test_max_errors_contributes_01(self):
        """5+ fouten → factor error_spike = 0.1"""
        ctx = {"errors_last_minute": 5}
        score = WeightedStruggleScore.calculate(ctx)
        assert score == pytest.approx(0.1, abs=0.001)

    def test_all_max_factors_returns_1_0(self):
        """Alle factoren max → score = 1.0"""
        ctx = {
            "recent_edits_same_line": 10,
            "recent_file_switches": 8,
            "lines_deleted_last_minute": 50,
            "errors_last_minute": 5,
        }
        score = WeightedStruggleScore.calculate(ctx)
        assert score == pytest.approx(1.0, abs=0.001)

    def test_partial_factors(self):
        """5 edits op zelfde regel = 50% van max → 0.4 * 0.5 = 0.2"""
        ctx = {"recent_edits_same_line": 5}
        score = WeightedStruggleScore.calculate(ctx)
        assert score == pytest.approx(0.2, abs=0.001)

    def test_score_capped_at_1_0(self):
        """Waarden boven de norm worden gecapped op 1.0 per factor."""
        ctx = {
            "recent_edits_same_line": 100,  # ver boven de norm van 10
            "recent_file_switches": 100,
            "lines_deleted_last_minute": 100,
            "errors_last_minute": 100,
        }
        score = WeightedStruggleScore.calculate(ctx)
        assert score == pytest.approx(1.0, abs=0.001)

    def test_score_is_rounded_to_3_decimals(self):
        ctx = {"recent_edits_same_line": 3}  # 3/10 = 0.3; 0.4 * 0.3 = 0.12
        score = WeightedStruggleScore.calculate(ctx)
        assert score == round(score, 3)

    def test_needs_intervention_above_threshold(self):
        assert WeightedStruggleScore.needs_intervention(0.81) is True
        assert WeightedStruggleScore.needs_intervention(1.0) is True

    def test_no_intervention_at_or_below_threshold(self):
        assert WeightedStruggleScore.needs_intervention(0.8) is False
        assert WeightedStruggleScore.needs_intervention(0.0) is False
        assert WeightedStruggleScore.needs_intervention(0.5) is False

    def test_threshold_value(self):
        assert WeightedStruggleScore.INTERVENTION_THRESHOLD == 0.8

    def test_weights_sum_to_1_0(self):
        total = sum(WeightedStruggleScore.WEIGHTS.values())
        assert total == pytest.approx(1.0, abs=0.001)


@pytest.mark.asyncio
class TestPracticalTwinServiceTrack:
    """Tests voor PracticalTwinService.track_behavior()."""

    async def test_track_delegates_to_observer(self):
        observer = AsyncMock(spec=UserBehaviorObserver)
        observer.track = AsyncMock(return_value="trace_abc")

        service = PracticalTwinService(observer=observer)
        result = await service.track_behavior(
            user_id="u1",
            tenant_id=1,
            session_id="sess",
            behavior_type="file_edit",
            context={"edit_count": 3},
        )

        observer.track.assert_called_once_with(
            user_id="u1",
            tenant_id=1,
            session_id="sess",
            behavior_type="file_edit",
            context={"edit_count": 3},
            outcome_metrics=None,
            confidence_score=1.0,
        )
        assert result == "trace_abc"

    async def test_track_returns_none_when_observer_rejects(self):
        observer = AsyncMock(spec=UserBehaviorObserver)
        observer.track = AsyncMock(return_value=None)

        service = PracticalTwinService(observer=observer)
        result = await service.track_behavior("u1", 1, "sess", "edit")
        assert result is None


@pytest.mark.asyncio
class TestPracticalTwinServiceAnalyzeStruggle:
    """Tests voor PracticalTwinService.analyze_struggle()."""

    async def test_no_struggle_no_suggestion(self):
        observer = AsyncMock(spec=UserBehaviorObserver)
        service = PracticalTwinService(observer=observer)

        result = await service.analyze_struggle(
            context={"recent_edits_same_line": 0},
            user_profile={},
        )

        assert result["score"] == 0.0
        assert result["needs_intervention"] is False
        assert result["suggestion"] == ""

    async def test_high_struggle_triggers_suggestion(self):
        observer = AsyncMock(spec=UserBehaviorObserver)
        llm = MockSuggestionProvider(response="Probeer dit eens...")
        service = PracticalTwinService(observer=observer, llm_provider=llm)

        high_struggle_context = {
            "recent_edits_same_line": 10,
            "recent_file_switches": 8,
            "lines_deleted_last_minute": 50,
            "errors_last_minute": 5,
        }
        result = await service.analyze_struggle(
            context=high_struggle_context,
            user_profile={"optimal_help_style": "direct_code"},
        )

        assert result["needs_intervention"] is True
        assert result["suggestion"] == "Probeer dit eens..."
        assert llm.call_count == 1

    async def test_llm_failure_returns_empty_suggestion(self):
        observer = AsyncMock(spec=UserBehaviorObserver)
        llm = MockSuggestionProvider(raise_error=True)
        service = PracticalTwinService(observer=observer, llm_provider=llm)

        high_struggle_context = {
            "recent_edits_same_line": 10,
            "recent_file_switches": 8,
            "lines_deleted_last_minute": 50,
            "errors_last_minute": 5,
        }
        result = await service.analyze_struggle(
            context=high_struggle_context,
            user_profile={},
        )

        assert result["needs_intervention"] is True
        assert result["suggestion"] == ""  # LLM fout → lege suggestie, geen crash

    async def test_analyze_struggle_returns_correct_structure(self):
        observer = AsyncMock(spec=UserBehaviorObserver)
        service = PracticalTwinService(observer=observer)

        result = await service.analyze_struggle(context={}, user_profile={})

        assert "score" in result
        assert "needs_intervention" in result
        assert "suggestion" in result

    async def test_struggle_score_in_result(self):
        observer = AsyncMock(spec=UserBehaviorObserver)
        service = PracticalTwinService(observer=observer)

        ctx = {"recent_edits_same_line": 5}
        result = await service.analyze_struggle(context=ctx, user_profile={})

        expected_score = WeightedStruggleScore.calculate(ctx)
        assert result["score"] == pytest.approx(expected_score, abs=0.001)

    async def test_analyze_struggle_blocked_when_ai_interventions_false(self):
        observer = AsyncMock(spec=UserBehaviorObserver)
        consent_mgr = AsyncMock()
        consent_mgr.get_consent_categories = AsyncMock(
            return_value=MagicMock(
                behavior_tracking=True,
                profile_aggregation=True,
                ai_interventions=False,
                cross_session_memory=True,
            )
        )
        service = PracticalTwinService(observer=observer, consent_manager=consent_mgr)

        high_struggle_context = {
            "recent_edits_same_line": 10,
            "recent_file_switches": 8,
        }
        result = await service.analyze_struggle(
            context=high_struggle_context,
            user_profile={},
            user_id="u1",
            tenant_id=1,
        )

        assert result["needs_intervention"] is False
        assert result["suggestion"] == ""

    async def test_analyze_struggle_allows_when_ai_interventions_true(self):
        observer = AsyncMock(spec=UserBehaviorObserver)
        consent_mgr = AsyncMock()
        consent_mgr.get_consent_categories = AsyncMock(
            return_value=MagicMock(
                behavior_tracking=True,
                profile_aggregation=True,
                ai_interventions=True,
                cross_session_memory=True,
            )
        )
        llm = MockSuggestionProvider(response="Probeer dit eens...")
        service = PracticalTwinService(
            observer=observer, llm_provider=llm, consent_manager=consent_mgr
        )

        high_struggle_context = {
            "recent_edits_same_line": 10,
            "recent_file_switches": 8,
            "lines_deleted_last_minute": 50,
            "errors_last_minute": 5,
        }
        result = await service.analyze_struggle(
            context=high_struggle_context,
            user_profile={},
            user_id="u1",
            tenant_id=1,
        )

        assert result["needs_intervention"] is True
        assert result["suggestion"] == "Probeer dit eens..."


@pytest.mark.asyncio
class TestGetProfileConsentGate:
    """Tests voor cross_session_memory consent gate in get_profile()."""

    async def test_get_profile_blocked_when_cross_session_memory_false(self):
        """cross_session_memory=False → get_profile retourneert {} zonder DB-query."""
        observer = AsyncMock(spec=UserBehaviorObserver)
        consent_mgr = AsyncMock()
        consent_mgr.get_consent_categories = AsyncMock(
            return_value=MagicMock(
                behavior_tracking=True,
                profile_aggregation=True,
                ai_interventions=True,
                cross_session_memory=False,
            )
        )
        db = AsyncMock()
        service = PracticalTwinService(observer=observer, consent_manager=consent_mgr)

        result = await service.get_profile(user_id="u1", tenant_id=1, db=db)

        assert result == {}
        db.execute.assert_not_called()

    async def test_get_profile_allows_when_cross_session_memory_true(self):
        """cross_session_memory=True → get_profile voert DB-query uit."""
        observer = AsyncMock(spec=UserBehaviorObserver)
        consent_mgr = AsyncMock()
        consent_mgr.get_consent_categories = AsyncMock(
            return_value=MagicMock(
                behavior_tracking=True,
                profile_aggregation=True,
                ai_interventions=True,
                cross_session_memory=True,
            )
        )
        db = AsyncMock()
        db.execute.return_value.scalar_one_or_none = MagicMock(return_value=None)
        service = PracticalTwinService(observer=observer, consent_manager=consent_mgr)

        result = await service.get_profile(user_id="u1", tenant_id=1, db=db)

        db.execute.assert_called_once()
        assert result == {}

    async def test_get_profile_no_consent_manager_skips_gate(self):
        """Zonder consent_manager wordt de gate overgeslagen (backwards compat)."""
        observer = AsyncMock(spec=UserBehaviorObserver)
        db = AsyncMock()
        db.execute.return_value.scalar_one_or_none = MagicMock(return_value=None)
        service = PracticalTwinService(observer=observer, consent_manager=None)

        result = await service.get_profile(user_id="u1", tenant_id=1, db=db)

        db.execute.assert_called_once()
        assert result == {}

    async def test_user_who_disabled_cross_session_memory_sees_empty_profile(self):
        """Behavioral test: gebruiker die cross-session memory uitschakelt krijgt altijd {} terug."""
        observer = AsyncMock(spec=UserBehaviorObserver)
        consent_mgr = AsyncMock()
        consent_mgr.get_consent_categories = AsyncMock(
            return_value=MagicMock(
                behavior_tracking=True,
                profile_aggregation=True,
                ai_interventions=True,
                cross_session_memory=False,
            )
        )
        db = AsyncMock()
        service = PracticalTwinService(observer=observer, consent_manager=consent_mgr)

        profile = await service.get_profile(user_id="rakesh", tenant_id=42, db=db)

        assert (
            profile == {}
        ), "Gebruiker die cross-session memory uitschakelt ziet nooit profieldata"


@pytest.fixture
def mock_observer():
    return AsyncMock(spec=UserBehaviorObserver)


@pytest.mark.asyncio
async def test_get_profile_returns_empty_when_no_profile(db_session, mock_observer):
    service = PracticalTwinService(observer=mock_observer)
    result = await service.get_profile(user_id="user_unknown", tenant_id=1, db=db_session)
    assert result == {}


@pytest.mark.asyncio
async def test_get_profile_returns_dict_when_profile_exists(db_session, mock_observer):
    from src.core.learning.twin_models import UserCognitiveProfile

    profile = UserCognitiveProfile(
        human_user_id="user_known",
        tenant_id=1,
        optimal_help_style="direct_code",
        confidence_level=0.7,
        observation_count=5,
    )
    db_session.add(profile)
    await db_session.commit()

    service = PracticalTwinService(observer=mock_observer)
    result = await service.get_profile(user_id="user_known", tenant_id=1, db=db_session)
    assert result["confidence_level"] == pytest.approx(0.7, abs=0.01)
    assert result["observation_count"] == 5
    assert result["optimal_help_style"] == "direct_code"
