"""
Sprint B: Pydantic request schemas must not expose tenant_id as a client-settable field.

tenant_id must always come from JWT/middleware (CLAUDE.md rule 6, ADR-003).
Exposing it as a request body field lets any caller forge cross-tenant requests.

Tests are parameterized over known NEEDS_FIX violations.

RED phase: all tests fail — tenant_id is still present in each schema.
GREEN phase: all tests pass after tenant_id is removed from each schema.
"""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).parents[3] / "src"


def _field_names(src_rel: str, class_name: str) -> list[str]:
    """
    Return annotated field names defined directly in the class body.
    Uses AST so it works for both Pydantic BaseModel subclasses and dataclasses.
    """
    source = (SRC / src_rel).read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            fields: list[str] = []
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    fields.append(item.target.id)
            return fields
    return []


# ---------------------------------------------------------------------------
# Parameterized NEEDS_FIX test cases
# Each tuple: (path relative to src/, class_name, human-readable reason)
# ---------------------------------------------------------------------------

NEEDS_FIX = [
    pytest.param(
        "core/api/feature_flags_endpoints.py",
        "ToggleFeatureRequest",
        "Admin endpoint /admin/features/{feature}/toggle receives tenant_id from client instead of JWT",
        id="ToggleFeatureRequest",
    ),
    pytest.param(
        "core/api/schemas/evaluation_schemas.py",
        "EvaluationBatchRequest",
        "trigger_batch_evaluation endpoint already has Depends(get_current_tenant_id) — field is redundant and dangerous",
        id="EvaluationBatchRequest",
    ),
    pytest.param(
        "core/api/user_management_endpoints.py",
        "UserCreate",
        "User creation endpoint receives tenant_id from client instead of JWT",
        id="UserCreate@user_management_endpoints",
    ),
    pytest.param(
        "core/api/v1/users/schemas.py",
        "UserCreate",
        "v1 user creation schema exposes tenant_id as input field",
        id="UserCreate@v1_users_schemas",
    ),
    pytest.param(
        "core/learning/gdpr_models.py",
        "GDPRRetentionRequest",
        "GDPR retention request schema exposes tenant_id as optional input",
        id="GDPRRetentionRequest",
    ),
    pytest.param(
        "core/scheduling/schemas.py",
        "PartnerCreateRequest",
        "Partner creation endpoint receives tenant_id from client instead of JWT",
        id="PartnerCreateRequest",
    ),
]


@pytest.mark.security
@pytest.mark.parametrize("src_rel,class_name,reason", NEEDS_FIX)
def test_request_schema_has_no_tenant_id(src_rel: str, class_name: str, reason: str) -> None:
    """
    Request schemas must not include tenant_id as a field.

    Client-controlled tenant_id fields enable cross-tenant data access.
    tenant_id must be sourced from the JWT claim via middleware (ADR-003).
    """
    fields = _field_names(src_rel, class_name)
    assert "tenant_id" not in fields, (
        f"{src_rel}: {class_name}.tenant_id must be removed.\n"
        f"Reason: {reason}\n"
        "Fix: remove tenant_id from the schema and get it from JWT/middleware in the endpoint."
    )
