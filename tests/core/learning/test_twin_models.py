"""
Unit tests voor Digital Twin SQLAlchemy models.

Controleert:
- Model-instantiatie en veld-defaults
- __repr__ methodes
- Tabel- en index-namen (schema validatie)
- JSONType keuze (SQLite voor tests, JSONB voor productie)
"""

import os
from datetime import datetime, timezone

import pytest


class TestUserBehaviorObservation:
    """Tests voor UserBehaviorObservation model."""

    def test_import(self):
        """Model is importeerbaar."""
        from src.core.learning.twin_models import UserBehaviorObservation

        assert UserBehaviorObservation is not None

    def test_tablename(self):
        from src.core.learning.twin_models import UserBehaviorObservation

        assert UserBehaviorObservation.__tablename__ == "user_behavior_observations"

    def test_instantiation_with_required_fields(self):
        from src.core.learning.twin_models import UserBehaviorObservation

        obs = UserBehaviorObservation(
            tenant_id=1,
            human_user_id="user_anon_abc123",
            session_id="sess_xyz",
            behavior_type="file_edit",
        )
        assert obs.tenant_id == 1
        assert obs.human_user_id == "user_anon_abc123"
        assert obs.session_id == "sess_xyz"
        assert obs.behavior_type == "file_edit"

    def test_optional_fields_default_to_none(self):
        from src.core.learning.twin_models import UserBehaviorObservation

        obs = UserBehaviorObservation(
            tenant_id=1,
            human_user_id="u",
            session_id="s",
            behavior_type="b",
        )
        assert obs.context is None
        assert obs.outcome_metrics is None
        assert obs.expires_at is None

    def test_repr(self):
        from src.core.learning.twin_models import UserBehaviorObservation

        obs = UserBehaviorObservation(
            tenant_id=1,
            human_user_id="user_abc",
            session_id="s",
            behavior_type="undo_loop",
        )
        obs.id = 42
        r = repr(obs)
        assert "42" in r
        assert "user_abc" in r
        assert "undo_loop" in r

    def test_has_expires_at_column(self):
        """expires_at aanwezig voor 90-dagen retentiebeleid."""
        from src.core.learning.twin_models import UserBehaviorObservation

        cols = {c.name for c in UserBehaviorObservation.__table__.columns}
        assert "expires_at" in cols

    def test_has_required_indexes(self):
        from src.core.learning.twin_models import UserBehaviorObservation

        index_names = {idx.name for idx in UserBehaviorObservation.__table__.indexes}
        assert "idx_twin_obs_user_time" in index_names
        assert "idx_twin_obs_session" in index_names
        assert "idx_twin_obs_tenant_behavior" in index_names
        assert "idx_twin_obs_expires" in index_names

    def test_json_type_falls_back_to_sqlite_json_under_testing(self):
        """De TESTING=1-fallback naar SQLite-JSON moet in de module aanwezig zijn.

        Dit testte eerder de import-tijd WAARDE van `twin_models.JSONType`. Die regel is
        `JSONType = SQLiteJSON if os.getenv("TESTING") == "1" else JSONB` en wordt exact
        een keer geevalueerd: bij de eerste import van de module. Importeert een ander
        bestand twin_models eerder in het proces -- bijvoorbeeld via een conftest of een
        service -- dan staat JSONType al op JSONB en faalt de test, ook al is de fallback
        gewoon aanwezig. Dat maakte de uitkomst afhankelijk van collectievolgorde
        (gevonden OP-11, 2026-07-31).

        Daarom toetst deze test de invariant op broncodeniveau, wat deterministisch is en
        precies de bedoeling vastlegt: er MOET een TESTING-afhankelijke SQLite-fallback
        bestaan, zodat unit-tests niet op een Postgres-specifiek JSONB-type stuklopen.
        """
        import ast
        import inspect

        from src.core.learning import twin_models

        source = inspect.getsource(twin_models)
        tree = ast.parse(source)

        jsontype_assignments = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "JSONType" for t in node.targets)
        ]
        assert jsontype_assignments, "twin_models moet een JSONType-toewijzing hebben"

        rendered = ast.unparse(jsontype_assignments[0].value)
        assert "TESTING" in rendered, (
            f"JSONType moet een TESTING-afhankelijke fallback hebben, gevonden: {rendered}"
        )
        assert "SQLiteJSON" in rendered or "JSON" in rendered, (
            f"JSONType moet naar een SQLite-compatibel JSON-type kunnen vallen: {rendered}"
        )
        assert "JSONB" in rendered, (
            f"JSONType moet buiten tests JSONB gebruiken (productie): {rendered}"
        )


class TestUserCognitiveProfile:
    """Tests voor UserCognitiveProfile model."""

    def test_import(self):
        from src.core.learning.twin_models import UserCognitiveProfile

        assert UserCognitiveProfile is not None

    def test_tablename(self):
        from src.core.learning.twin_models import UserCognitiveProfile

        assert UserCognitiveProfile.__tablename__ == "user_cognitive_profiles"

    def test_instantiation(self):
        from src.core.learning.twin_models import UserCognitiveProfile

        profile = UserCognitiveProfile(
            tenant_id=1,
            human_user_id="user_abc",
        )
        assert profile.tenant_id == 1
        assert profile.human_user_id == "user_abc"
        # SQLAlchemy column defaults are DB-level; they apply at INSERT time.
        # Check that the column definition carries the correct default.
        col = UserCognitiveProfile.__table__.c["confidence_level"]
        assert col.default.arg == 0.0
        col_count = UserCognitiveProfile.__table__.c["observation_count"]
        assert col_count.default.arg == 0

    def test_optional_json_fields_default_to_none(self):
        from src.core.learning.twin_models import UserCognitiveProfile

        profile = UserCognitiveProfile(tenant_id=1, human_user_id="u")
        assert profile.coding_style is None
        assert profile.work_patterns is None
        assert profile.blind_spots is None
        assert profile.strengths is None

    def test_repr(self):
        from src.core.learning.twin_models import UserCognitiveProfile

        profile = UserCognitiveProfile(
            tenant_id=1,
            human_user_id="user_xyz",
            confidence_level=0.75,
        )
        profile.id = 7
        r = repr(profile)
        assert "7" in r
        assert "user_xyz" in r
        assert "0.75" in r

    def test_unique_constraint_on_tenant_user(self):
        """OP-228: de keten legt een UNIQUE-constraint, geen unieke index; het model ook."""
        from sqlalchemy import UniqueConstraint

        from src.core.learning.twin_models import UserCognitiveProfile

        constraints = {
            c.name: tuple(col.name for col in c.columns)
            for c in UserCognitiveProfile.__table__.constraints
            if isinstance(c, UniqueConstraint)
        }
        assert constraints == {"uq_twin_profile_tenant_user": ("tenant_id", "human_user_id")}
        assert "idx_twin_profile_tenant_user" not in {
            idx.name for idx in UserCognitiveProfile.__table__.indexes
        }


class TestUserTwinConsent:
    """Tests voor UserTwinConsent model (GDPR)."""

    def test_import(self):
        from src.core.learning.twin_models import UserTwinConsent

        assert UserTwinConsent is not None

    def test_tablename(self):
        from src.core.learning.twin_models import UserTwinConsent

        assert UserTwinConsent.__tablename__ == "user_twin_consent"

    def test_instantiation_defaults(self):
        """Default: GEEN consent (opt-in model) -- column defaults gedefinieerd.

        Deze test eiste tot 2026-07-31 `consent_given.default.arg is True` met de
        toelichting "opt-out model". Dat is onder de AVG niet toegestaan voor
        twin-verwerking; het model documenteert de correcte keuze op de kolom zelf
        ("GDPR opt-in: default False") met `default=False` en `server_default="FALSE"`.
        De test liep achter op die correctie (gevonden OP-11).
        """
        from src.core.learning.twin_models import UserTwinConsent

        # SQLAlchemy column defaults are DB-level (applied at INSERT).
        # Verify the column definitions carry correct defaults.
        tbl = UserTwinConsent.__table__.c
        assert tbl["consent_given"].default.arg is False
        assert tbl["hard_delete_requested"].default.arg is False
        assert tbl["consent_version"].default.arg == "1.0"

        consent = UserTwinConsent(
            tenant_id=1,
            human_user_id="user_abc",
        )
        assert consent.hard_delete_requested_at is None

    def test_opt_out(self):
        from src.core.learning.twin_models import UserTwinConsent

        consent = UserTwinConsent(
            tenant_id=1,
            human_user_id="user_abc",
            consent_given=False,
        )
        assert consent.consent_given is False

    def test_hard_delete_request(self):
        """GDPR Artikel 17: Right to Erasure vlag."""
        from src.core.learning.twin_models import UserTwinConsent

        now = datetime.now(timezone.utc)
        consent = UserTwinConsent(
            tenant_id=1,
            human_user_id="user_abc",
            hard_delete_requested=True,
            hard_delete_requested_at=now,
        )
        assert consent.hard_delete_requested is True
        assert consent.hard_delete_requested_at == now

    def test_repr(self):
        from src.core.learning.twin_models import UserTwinConsent

        consent = UserTwinConsent(
            tenant_id=1,
            human_user_id="user_xyz",
            consent_given=True,
        )
        consent.id = 3
        r = repr(consent)
        assert "3" in r
        assert "user_xyz" in r
        assert "True" in r

    def test_unique_constraint_on_tenant_user(self):
        """OP-228: de keten legt een UNIQUE-constraint, geen unieke index; het model ook."""
        from sqlalchemy import UniqueConstraint

        from src.core.learning.twin_models import UserTwinConsent

        constraints = {
            c.name: tuple(col.name for col in c.columns)
            for c in UserTwinConsent.__table__.constraints
            if isinstance(c, UniqueConstraint)
        }
        assert constraints == {"uq_twin_consent_tenant_user": ("tenant_id", "human_user_id")}
        assert "idx_twin_consent_tenant_user" not in {
            idx.name for idx in UserTwinConsent.__table__.indexes
        }
