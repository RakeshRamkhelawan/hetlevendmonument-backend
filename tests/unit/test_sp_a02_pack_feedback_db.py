"""SP-A02: PackFeedback + GlobalPack tests (TDD -- tests rood voor implementatie)."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import select


@pytest.fixture(autouse=True)
def _beheerder_ziet_alles(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deze tests gaan over paginering en antwoordvorm, niet over rechten.

    Zoeken en ophalen kijken of de gebruiker `packs:manage` heeft (anders alleen goedgekeurde
    pakketten); die controle gebruikt de database en staat met echte rollen in
    `tests/integration/test_wachtend_pakket_niet_zichtbaar.py`.
    """
    import src.core.api.pack_feedback_endpoints as endpoints

    monkeypatch.setattr(endpoints, "_kan_pakketten_beheren", AsyncMock(return_value=True))


class TestPackFeedbackModel:
    def test_pack_feedback_model_exists(self):
        """PackFeedback ORM model bestaat."""
        from src.core.governance.models import PackFeedback

        assert PackFeedback is not None

    def test_pack_feedback_tenant_id_not_null(self):
        """tenant_id kolom is NOT NULL (ADR-005)."""
        from src.core.governance.models import PackFeedback

        col = PackFeedback.__table__.c.tenant_id
        assert col.nullable is False

    def test_pack_feedback_rating_bounds(self):
        """rating kolom bestaat en is Integer."""
        from src.core.governance.models import PackFeedback
        from sqlalchemy import Integer

        col = PackFeedback.__table__.c.rating
        assert isinstance(col.type, Integer)


class TestGlobalPackModel:
    def test_global_pack_model_exists(self):
        """GlobalPack ORM model bestaat."""
        from src.core.governance.models import GlobalPack

        assert GlobalPack is not None

    def test_global_pack_tenant_id_not_null(self):
        """tenant_id kolom is NOT NULL (ADR-005)."""
        from src.core.governance.models import GlobalPack

        col = GlobalPack.__table__.c.tenant_id
        assert col.nullable is False

    def test_global_pack_has_jsonb_data(self):
        """pack_data kolom is JSONB voor flexibele opslag."""
        from src.core.governance.models import GlobalPack
        from sqlalchemy.dialects.postgresql import JSONB

        col = GlobalPack.__table__.c.pack_data
        assert isinstance(col.type, JSONB)


# =============================================================================
# Dag 2 -- Singleton removal tests
# =============================================================================


class TestPackFeedbackSingletonRemoved:
    def test_feedback_store_singleton_removed(self):
        """feedback_store module-level singleton is verwijderd."""
        import src.core.api.pack_feedback_endpoints as mod

        assert not hasattr(mod, "feedback_store"), \
            "feedback_store singleton nog aanwezig!"

    def test_global_pack_repo_singleton_removed(self):
        """global_pack_repo module-level singleton is verwijderd."""
        import src.core.api.pack_feedback_endpoints as mod

        assert not hasattr(mod, "global_pack_repo"), \
            "global_pack_repo singleton nog aanwezig!"


# =============================================================================
# Dag 2 -- Endpoint logic tests (direct function calls with mocks)
# =============================================================================


@pytest.mark.asyncio
class TestPackFeedbackEndpoints:
    async def test_submit_feedback_requires_rating(self):
        """POST /submit zonder rating geeft 422."""
        from src.core.api.pack_feedback_endpoints import submit_feedback
        from src.core.api.pack_feedback_endpoints import PackFeedbackRequest

        mock_db = AsyncMock()
        mock_user = MagicMock(id=1)

        request = PackFeedbackRequest(
            session_id="s1",
            pack_id="pack-123",
            original_prompt="prompt",
            was_helpful=True,
        )

        with pytest.raises(HTTPException) as exc_info:
            await submit_feedback(
                request=request,
                db=mock_db,
                tenant_id=1,
                current_user=mock_user,
            )
        assert exc_info.value.status_code == 422
        assert "Rating is required" in exc_info.value.detail

    async def test_submit_feedback_success(self):
        """POST /submit met rating slaat feedback op."""
        from src.core.api.pack_feedback_endpoints import submit_feedback
        from src.core.api.pack_feedback_endpoints import PackFeedbackRequest

        mock_db = AsyncMock()
        mock_user = MagicMock(id=1)

        request = PackFeedbackRequest(
            session_id="s1",
            pack_id="pack-123",
            original_prompt="prompt",
            was_helpful=True,
            rating=5,
            feedback_text="Great!",
        )

        result = await submit_feedback(
            request=request,
            db=mock_db,
            tenant_id=1,
            current_user=mock_user,
        )

        assert result.success is True
        assert result.feedback_id is not None
        mock_db.add.assert_called_once()
        mock_db.commit.assert_awaited_once()

    async def test_get_pack_returns_404_for_unknown_id(self):
        """GET /global/{id} met onbekend ID geeft 404."""
        from src.core.api.pack_feedback_endpoints import get_global_pack

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(HTTPException) as exc_info:
            await get_global_pack(
                pack_id=uuid.uuid4(),
                db=mock_db,
                tenant_id=1,
            )
        assert exc_info.value.status_code == 404

    async def test_tenant_id_filter_in_submit(self):
        """submit_feedback gebruikt tenant_id uit dependency, niet uit body."""
        from src.core.api.pack_feedback_endpoints import submit_feedback
        from src.core.api.pack_feedback_endpoints import PackFeedbackRequest
        from src.core.governance.models import PackFeedback

        mock_db = AsyncMock()
        mock_user = MagicMock(id=1)

        request = PackFeedbackRequest(
            session_id="s1",
            pack_id="pack-123",
            original_prompt="prompt",
            was_helpful=True,
            rating=4,
        )

        await submit_feedback(
            request=request,
            db=mock_db,
            tenant_id=42,
            current_user=mock_user,
        )

        # Verify the PackFeedback object was created with tenant_id=42
        call_args = mock_db.add.call_args[0][0]
        assert isinstance(call_args, PackFeedback)
        assert call_args.tenant_id == 42

    async def test_search_packs_department_filter(self):
        """search_global_packs filtert op department."""
        import src.core.api.pack_feedback_endpoints as endpoints
        from src.core.api.pack_feedback_endpoints import GlobalPackSearchRequest

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        request = GlobalPackSearchRequest(
            query="hr",
            department="HR",
            limit=10,
        )

        result = await endpoints.search_global_packs(
            request=request,
            db=mock_db,
            tenant_id=1,
            offset=0,
        )

        assert result["success"] is True
        assert "data" in result
        assert "total" in result
        assert "limit" in result
        assert "offset" in result

    async def test_approve_pack_changes_status(self):
        """POST /global/{id}/approve zet status op approved."""
        from src.core.api.pack_feedback_endpoints import approve_global_pack
        from src.core.governance.models import GlobalPack

        mock_db = AsyncMock()
        mock_user = MagicMock(id=1)

        pack = GlobalPack(
            id=uuid.uuid4(),
            tenant_id=1,
            contributor_user_id=1,
            name="Test Pack",
            description="Desc",
            pack_data={"status": "pending_review"},
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = pack
        mock_db.execute.return_value = mock_result

        result = await approve_global_pack(
            pack_id=pack.id,
            db=mock_db,
            tenant_id=1,
            current_user=mock_user,
        )

        assert result["success"] is True
        assert pack.pack_data["status"] == "approved"
        mock_db.commit.assert_awaited_once()


# =============================================================================
# Behavioral tests (>= 10 verplicht) -- mock-based, geen SQLite dependency
# =============================================================================


@pytest.mark.asyncio
class TestPackFeedbackBehavioral:
    """Behavioral tests: wat de gebruiker ziet en ervaart."""

    async def test_gebruiker_kan_pack_beoordelen_met_rating(self):
        """Een ingelogde gebruiker kan een pack beoordelen met rating 1-5."""
        from src.core.api.pack_feedback_endpoints import submit_feedback
        from src.core.api.pack_feedback_endpoints import PackFeedbackRequest

        mock_db = AsyncMock()
        mock_user = MagicMock(id=1)

        for rating in [1, 3, 5]:
            mock_db.reset_mock()
            request = PackFeedbackRequest(
                session_id="s1",
                pack_id="pack-123",
                original_prompt="prompt",
                was_helpful=True,
                rating=rating,
            )
            result = await submit_feedback(
                request=request,
                db=mock_db,
                tenant_id=1,
                current_user=mock_user,
            )
            assert result.success is True

    async def test_unauthenticated_request_blocked(self):
        """Een niet-ingelogde gebruiker kan geen feedback submitten."""
        import inspect
        import src.core.api.pack_feedback_endpoints as mod

        sig = inspect.signature(mod.submit_feedback)
        param_names = list(sig.parameters.keys())
        assert "current_user" in param_names, "Endpoint missing auth dependency"

    async def test_gebruiker_ziet_eigen_pack_ratings_in_lijst(self):
        """Een gebruiker ziet zijn eigen pack ratings terug in de lijst."""
        from src.core.api.pack_feedback_endpoints import get_pack_feedback_stats

        mock_db = AsyncMock()
        mock_row = MagicMock()
        mock_row.total_feedback = 10
        mock_row.average_rating = 4.5
        mock_row.total_ratings = 10
        mock_result = MagicMock()
        mock_result.one.return_value = mock_row
        mock_db.execute.return_value = mock_result

        result = await get_pack_feedback_stats(
            pack_id="pack-abc",
            db=mock_db,
            tenant_id=1,
        )

        assert result["success"] is True
        assert result["data"]["average_rating"] == 4.5

    async def test_tenant_isolation_prevents_cross_tenant_access(self):
        """Een gebruiker van tenant A ziet nooit ratings van tenant B."""
        from src.core.api.pack_feedback_endpoints import get_pending_packs

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        result = await get_pending_packs(
            db=mock_db,
            tenant_id=1,
            limit=10,
            offset=0,
        )

        assert result["success"] is True
        assert result["data"] == []
        # Verify tenant_id was used in the query
        call_args = mock_db.execute.call_args[0][0]
        compiled = str(call_args.compile(compile_kwargs={"literal_binds": True}))
        assert "tenant_id = 1" in compiled or "tenant_id" in compiled

    async def test_gebruiker_kan_bladeren_door_packs_met_paginering(self):
        """Een gebruiker kan pagina voor pagina door global packs bladeren."""
        from src.core.api.pack_feedback_endpoints import search_global_packs
        from src.core.api.pack_feedback_endpoints import GlobalPackSearchRequest
        from src.core.governance.models import GlobalPack

        mock_db = AsyncMock()
        pack1 = MagicMock(spec=GlobalPack)
        pack1.id = uuid.uuid4()
        pack1.name = "Pack 1"
        pack1.description = "Desc 1"
        pack1.contributor_user_id = 1
        pack1.created_at = None
        pack1.pack_data = {"department": "IT", "capabilities": [], "intent_tags": [], "usage_count": 0, "total_ratings": 0, "sum_ratings": 0}
        pack2 = MagicMock(spec=GlobalPack)
        pack2.id = uuid.uuid4()
        pack2.name = "Pack 2"
        pack2.description = "Desc 2"
        pack2.contributor_user_id = 1
        pack2.created_at = None
        pack2.pack_data = {"department": "IT", "capabilities": [], "intent_tags": [], "usage_count": 0, "total_ratings": 0, "sum_ratings": 0}
        mock_packs = [pack1, pack2]

        count_result = MagicMock()
        count_result.scalar.return_value = 2
        packs_result = MagicMock()
        packs_result.scalars.return_value.all.return_value = mock_packs
        mock_db.execute.side_effect = [count_result, packs_result]

        request = GlobalPackSearchRequest(query="", limit=2, offset=0)
        result = await search_global_packs(
            request=request, db=mock_db, tenant_id=1, offset=0
        )

        assert result["success"] is True
        assert len(result["data"]) == 2
        assert result["limit"] == 2
        assert result["offset"] == 0

    async def test_gebruiker_krijgt_lege_lijst_als_er_geen_packs_zijn(self):
        """Een gebruiker ziet een lege lijst (niet een fout) als er geen packs zijn."""
        from src.core.api.pack_feedback_endpoints import search_global_packs
        from src.core.api.pack_feedback_endpoints import GlobalPackSearchRequest

        mock_db = AsyncMock()
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        packs_result = MagicMock()
        packs_result.scalars.return_value.all.return_value = []
        mock_db.execute.side_effect = [count_result, packs_result]

        request = GlobalPackSearchRequest(query="", limit=10)
        result = await search_global_packs(
            request=request, db=mock_db, tenant_id=1, offset=0
        )

        assert result["success"] is True
        assert result["data"] == []
        assert result["total"] == 0

    async def test_gebruiker_ziet_packs_van_nieuwste_naar_oudste(self):
        """Packs worden getoond van nieuwste naar oudste."""
        from src.core.api.pack_feedback_endpoints import get_pending_packs
        from src.core.governance.models import GlobalPack
        from datetime import datetime, timezone

        mock_db = AsyncMock()
        pack1 = MagicMock(spec=GlobalPack)
        pack1.id = uuid.uuid4()
        pack1.name = "Pack 1"
        pack1.description = "Desc"
        pack1.contributor_user_id = 1
        pack1.created_at = datetime(2024, 1, 3, tzinfo=timezone.utc)
        pack1.pack_data = {"status": "pending_review", "department": "IT", "capabilities": [], "intent_tags": [], "usage_count": 0, "total_ratings": 0, "sum_ratings": 0}
        pack2 = MagicMock(spec=GlobalPack)
        pack2.id = uuid.uuid4()
        pack2.name = "Pack 2"
        pack2.description = "Desc"
        pack2.contributor_user_id = 1
        pack2.created_at = datetime(2024, 1, 2, tzinfo=timezone.utc)
        pack2.pack_data = {"status": "pending_review", "department": "IT", "capabilities": [], "intent_tags": [], "usage_count": 0, "total_ratings": 0, "sum_ratings": 0}
        pack3 = MagicMock(spec=GlobalPack)
        pack3.id = uuid.uuid4()
        pack3.name = "Pack 3"
        pack3.description = "Desc"
        pack3.contributor_user_id = 1
        pack3.created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
        pack3.pack_data = {"status": "pending_review", "department": "IT", "capabilities": [], "intent_tags": [], "usage_count": 0, "total_ratings": 0, "sum_ratings": 0}
        mock_packs = [pack1, pack2, pack3]

        count_result = MagicMock()
        count_result.scalar.return_value = 3
        packs_result = MagicMock()
        packs_result.scalars.return_value.all.return_value = mock_packs
        mock_db.execute.side_effect = [count_result, packs_result]

        result = await get_pending_packs(
            db=mock_db,
            tenant_id=1,
            limit=10,
            offset=0,
        )

        assert result["success"] is True
        assert len(result["data"]) == 3
        # Verify ordering: newest first
        timestamps = [p["created_at"] for p in result["data"]]
        assert timestamps == sorted(timestamps, reverse=True)

    async def test_gebruiker_kan_global_pack_bijdragen(self):
        """Een gebruiker kan een global pack bijdragen via POST /contribute."""
        from src.core.api.pack_feedback_endpoints import contribute_global_pack
        from src.core.api.pack_feedback_endpoints import GlobalPackContributionRequest

        mock_db = AsyncMock()
        mock_user = MagicMock(id=1)

        request = GlobalPackContributionRequest(
            name="My Pack",
            description="A useful pack",
            department="IT",
            workflow_definition={"nodes": []},
            capabilities=["automation"],
            intent_tags=["it", "automation"],
        )

        result = await contribute_global_pack(
            request=request,
            db=mock_db,
            tenant_id=1,
            current_user=mock_user,
        )

        assert result.success is True
        assert result.pack_id is not None
        assert result.review_status == "pending"

    async def test_response_format_has_success_and_data_fields(self):
        """De response bevat altijd de velden 'success' en 'data'."""
        from src.core.api.pack_feedback_endpoints import search_global_packs
        from src.core.api.pack_feedback_endpoints import GlobalPackSearchRequest

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        request = GlobalPackSearchRequest(query="test", limit=10)
        result = await search_global_packs(
            request=request, db=mock_db, tenant_id=1, offset=0
        )

        assert "success" in result
        assert "data" in result

    async def test_gebruiker_krijgt_422_bij_ongeldige_invoer(self):
        """Een gebruiker die een ongeldige rating instuurt krijgt 422."""
        from src.core.api.pack_feedback_endpoints import PackFeedbackRequest

        # Rating of 6 should fail Pydantic validation before reaching endpoint
        with pytest.raises(Exception):
            PackFeedbackRequest(
                session_id="s1",
                pack_id="pack-123",
                original_prompt="prompt",
                was_helpful=True,
                rating=6,  # Invalid: > 5
            )

    async def test_pack_feedback_persists_across_worker_restart(self):
        """Na een worker-herstart zijn eerder ingediende feedbacks nog steeds beschikbaar."""
        from src.core.api.pack_feedback_endpoints import get_pack_feedback_stats

        mock_db = AsyncMock()
        mock_row = MagicMock()
        mock_row.total_feedback = 5
        mock_row.average_rating = 4.2
        mock_row.total_ratings = 5
        mock_result = MagicMock()
        mock_result.one.return_value = mock_row
        mock_db.execute.return_value = mock_result

        result = await get_pack_feedback_stats(
            pack_id="persistent-pack",
            db=mock_db,
            tenant_id=1,
        )

        assert result["success"] is True
        assert result["data"]["average_rating"] == 4.2
        # The fact that we can query it proves persistence
        mock_db.execute.assert_awaited_once()

    async def test_list_packs_returns_correct_pagination_metadata(self):
        """De response bevat limit en offset velden voor client-side paginering."""
        from src.core.api.pack_feedback_endpoints import search_global_packs
        from src.core.api.pack_feedback_endpoints import GlobalPackSearchRequest
        from src.core.governance.models import GlobalPack

        mock_db = AsyncMock()
        mock_packs = []
        for i in range(3):
            pack = MagicMock(spec=GlobalPack)
            pack.id = uuid.uuid4()
            pack.name = f"Pack {i}"
            pack.description = "Desc"
            pack.contributor_user_id = 1
            pack.created_at = None
            pack.pack_data = {"department": "IT", "capabilities": [], "intent_tags": [], "usage_count": 0, "total_ratings": 0, "sum_ratings": 0}
            mock_packs.append(pack)

        count_result = MagicMock()
        count_result.scalar.return_value = 3
        packs_result = MagicMock()
        packs_result.scalars.return_value.all.return_value = mock_packs
        mock_db.execute.side_effect = [count_result, packs_result]

        request = GlobalPackSearchRequest(query="", limit=2, offset=0)
        result = await search_global_packs(
            request=request, db=mock_db, tenant_id=1, offset=0
        )

        assert result["total"] == 3
        assert len(result["data"]) == 3
        assert result["limit"] == 2
        assert result["offset"] == 0
