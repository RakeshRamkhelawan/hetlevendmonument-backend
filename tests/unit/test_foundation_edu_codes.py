"""Unit tests for BE-EP-044 Educational Access Code Generator & Management.

Offline tests: Validates code generation, entropy, schema validation,
hashing conformance, and endpoint logic for /edu/codes.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from src.core.api.v1.foundation.edu import (
    SAFE_EDU_ALPHABET,
    generate_edu_code,
)
from src.core.api.v1.foundation.schemas import (
    CreateEduCodeRequest,
    EduCodeCreateResponse,
    EduCodeItem,
    EduCodeListResponse,
    EduSessionRequest,
)
from src.core.models.foundation_content import (
    EducationalAccess,
    EducationalRole,
    StudyCollection,
)
from src.core.services.edu_session_service import hash_edu_code
from src.core.shared.datetime_utils import utc_now


# ============================================================================
# 1. Cryptographic Code Generator Tests
# ============================================================================


class TestEduCodeGenerator:
    @pytest.mark.unit
    def test_generate_code_format_and_length(self) -> None:
        """Code must be exact 8 characters matching ^[A-Za-z0-9]{8}$."""
        code = generate_edu_code()
        assert len(code) == 8
        assert re.match(r"^[A-Za-z0-9]{8}$", code) is not None

    @pytest.mark.unit
    def test_generate_code_uses_safe_alphabet(self) -> None:
        """Code must only contain safe characters (no 0, O, 1, I, L)."""
        forbidden = set("0O1IL")
        for _ in range(50):
            code = generate_edu_code()
            assert not any(c in forbidden for c in code)
            assert all(c in SAFE_EDU_ALPHABET for c in code)

    @pytest.mark.unit
    def test_generate_code_uniqueness(self) -> None:
        """50 generated codes should all be distinct (sufficient entropy)."""
        codes = {generate_edu_code() for _ in range(50)}
        assert len(codes) == 50

    @pytest.mark.unit
    def test_code_matches_edu_session_request_validator(self) -> None:
        """Generated code must be accepted by EduSessionRequest without error."""
        code = generate_edu_code()
        req = EduSessionRequest(code=code)
        assert req.code == code


# ============================================================================
# 2. Schema Validation Tests
# ============================================================================


class TestEduCodeSchemas:
    @pytest.mark.unit
    def test_create_request_valid(self) -> None:
        req = CreateEduCodeRequest(
            class_name="Groep 8A",
            teacher_email="meester.jan@school.nl",
            role="student",
            valid_hours=4,
        )
        assert req.class_name == "Groep 8A"
        assert req.teacher_email == "meester.jan@school.nl"
        assert req.role == "student"
        assert req.valid_hours == 4

    @pytest.mark.unit
    def test_create_request_invalid_email(self) -> None:
        with pytest.raises(ValidationError):
            CreateEduCodeRequest(
                class_name="Groep 8A",
                teacher_email="not-an-email",
                role="student",
            )

    @pytest.mark.unit
    def test_create_request_empty_class_name(self) -> None:
        with pytest.raises(ValidationError):
            CreateEduCodeRequest(
                class_name="",
                teacher_email="docent@school.nl",
            )

    @pytest.mark.unit
    def test_create_request_valid_hours_range(self) -> None:
        with pytest.raises(ValidationError):
            CreateEduCodeRequest(
                class_name="Klas 1",
                teacher_email="docent@school.nl",
                valid_hours=0,
            )
        with pytest.raises(ValidationError):
            CreateEduCodeRequest(
                class_name="Klas 1",
                teacher_email="docent@school.nl",
                valid_hours=169,  # max 168 (7 days)
            )

    @pytest.mark.unit
    def test_response_models(self) -> None:
        now = utc_now()
        create_res = EduCodeCreateResponse(
            id=1,
            code="K7N2P9Q4",
            class_name="Klas 3 HAVO",
            teacher_email="docent@school.nl",
            role="student",
            expires_at=now + timedelta(hours=4),
            created_at=now,
            is_active=True,
        )
        assert create_res.code == "K7N2P9Q4"

        item = EduCodeItem(
            id=1,
            class_name="Klas 3 HAVO",
            teacher_email="docent@school.nl",
            role="student",
            expires_at=now + timedelta(hours=4),
            created_at=now,
            is_active=True,
        )
        list_res = EduCodeListResponse(items=[item], total=1)
        assert list_res.total == 1
        assert list_res.items[0].id == 1


# ============================================================================
# 3. Code Generation & Hashing Integration
# ============================================================================


class TestCodeGenerationAndHashing:
    @pytest.mark.unit
    def test_generated_code_hashes_to_valid_sha256(self) -> None:
        raw_code = generate_edu_code()
        hashed = hash_edu_code(raw_code)
        assert len(hashed) == 64
        assert re.match(r"^[a-f0-9]{64}$", hashed) is not None
        # Must verify equality when recalculated
        assert hash_edu_code(raw_code) == hashed
