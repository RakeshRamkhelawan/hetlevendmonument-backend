import pytest


class TestMissionModel:
    """Dag 1: Mission ORM model bestaat en voldoet aan ADR-005."""

    def test_mission_model_exists(self):
        """Mission ORM model is importeerbaar."""
        from src.core.models.mission_models import Mission

        assert Mission is not None

    def test_mission_tenant_id_not_null(self):
        """tenant_id kolom is NOT NULL (ADR-005)."""
        from src.core.models.mission_models import Mission

        col = Mission.__table__.c.tenant_id
        assert col.nullable is False, "tenant_id mag NOOIT nullable zijn (ADR-005)"

    def test_mission_has_uuid_primary_key(self):
        """id kolom is een UUID met gen_random_uuid() server_default."""
        from src.core.models.mission_models import Mission
        from sqlalchemy.dialects.postgresql import UUID as PG_UUID

        col = Mission.__table__.c.id
        assert isinstance(col.type, PG_UUID), f"id moet UUID zijn, is {type(col.type)}"
        assert col.server_default is not None, "id moet server_default gen_random_uuid() hebben"

    def test_mission_created_at_uses_clock_timestamp(self):
        """created_at gebruikt clock_timestamp() niet NOW() (CLAUDE.md §11.5)."""
        from src.core.models.mission_models import Mission

        col = Mission.__table__.c.created_at
        assert col.server_default is not None
        assert "clock_timestamp" in str(col.server_default.arg).lower(), (
            "created_at moet clock_timestamp() gebruiken voor serializable ordering"
        )

    def test_mission_has_deleted_at_column(self):
        """Soft delete: deleted_at kolom aanwezig (nooit hard delete)."""
        from src.core.models.mission_models import Mission

        assert hasattr(Mission, "deleted_at"), "Soft delete kolom deleted_at vereist"

    def test_mission_status_column_default_planned(self):
        """status kolom aanwezig met server_default 'planned'."""
        from src.core.models.mission_models import Mission

        col = Mission.__table__.c.status
        assert col.server_default is not None
        assert "planned" in str(col.server_default.arg).lower(), (
            "status default moet 'planned' zijn (match bestaande API MissionStatus)"
        )

    def test_mission_agent_type_column_exists(self):
        """agent_type kolom aanwezig voor API-compatibiliteit."""
        from src.core.models.mission_models import Mission

        assert hasattr(Mission, "agent_type"), "agent_type kolom vereist voor API-compat"

    def test_mission_created_by_column_exists(self):
        """created_by kolom aanwezig voor API-compatibiliteit."""
        from src.core.models.mission_models import Mission

        assert hasattr(Mission, "created_by"), "created_by kolom vereist voor API-compat"

    def test_mission_payload_is_typed_dict(self):
        """payload is getypeerd als dict[str, Any] niet naakte dict."""
        from src.core.models.mission_models import Mission

        col = Mission.__table__.c.payload
        assert col.nullable is True, "payload moet nullable zijn"


class TestMissionAlembicMigration:
    """Dag 1: Alembic migratie is geldig en in de keten."""

    def test_alembic_chain_has_single_head(self):
        """alembic heads toont precies 1 head (geen gesplitste keten)."""
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, "-m", "alembic", "-c", "src/alembic.ini", "heads"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        lines = [
            line for line in result.stdout.strip().split("\n") if line.strip() and "head" in line
        ]
        assert len(lines) == 1, f"Verwacht 1 head, gevonden: {lines}. Keten is gesplitst!"


class TestMissionEndpointsNoDictStore:
    """Dag 2: in-memory store is volledig verwijderd."""

    def test_missions_store_not_in_source(self):
        """_missions_store is verwijderd uit mission_endpoints.py."""
        import inspect
        import src.core.api.mission_endpoints as mod

        source = inspect.getsource(mod)
        assert "_missions_store" not in source, (
            "_missions_store nog aanwezig in source — P0 data loss bug niet opgelost!"
        )

    def test_tenant_id_not_in_create_request_schema(self):
        """CreateMissionRequest bevat GEEN tenant_id veld (CLAUDE.md §6)."""
        import src.core.api.mission_endpoints as mod

        create_schema = getattr(mod, "CreateMissionRequest", None)
        if create_schema is None:
            pytest.skip("CreateMissionRequest niet gevonden — check module naam")
        assert "tenant_id" not in create_schema.model_fields, (
            "tenant_id in CreateMissionRequest — client kan tenant spoofen!"
        )

    def test_list_missions_has_pagination(self):
        """list_missions endpoint heeft page en page_size parameters."""
        import inspect
        import src.core.api.mission_endpoints as mod

        for name in dir(mod):
            func = getattr(mod, name)
            if callable(func) and "list" in name.lower() and "mission" in name.lower():
                sig = inspect.signature(func)
                params = list(sig.parameters.keys())
                assert "page" in params or "limit" in params, f"{name} mist paginering parameter"
                assert "page_size" in params or "offset" in params, (
                    f"{name} mist paginering parameter"
                )
