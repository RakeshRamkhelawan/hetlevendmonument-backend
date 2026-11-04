"""
Unit tests for Foundation Portal exceptions.

Verifies: hierarchy, error codes, status codes, details,
no collision with existing TenantNotFoundError.
"""

import pytest

from src.core.exceptions.exceptions import SanskritiError, TenantNotFoundError
from src.core.exceptions.foundation import (
    CaptchaFailedError,
    ContentNotFoundError,
    FileTooLargeError,
    FoundationError,
    FoundationTenantSlugNotFoundError,
    InvalidFileTypeError,
    InvalidMagicLinkError,
    InvalidSlugError,
    ReservedSlugError,
    RightsNotConfirmedError,
    SlugTakenError,
    TakedownDuplicateError,
)


class TestFoundationExceptionHierarchy:
    @pytest.mark.unit
    def test_all_inherit_from_foundation_error(self) -> None:
        exceptions = [
            FoundationTenantSlugNotFoundError("x"),
            ContentNotFoundError(1),
            InvalidFileTypeError("image/png"),
            FileTooLargeError(10_000_000),
            RightsNotConfirmedError(),
            InvalidMagicLinkError(),
            CaptchaFailedError(),
            TakedownDuplicateError(1),
            ReservedSlugError("api"),
            InvalidSlugError("bad!"),
            SlugTakenError("taken"),
        ]
        for exc in exceptions:
            assert isinstance(exc, FoundationError), f"{type(exc).__name__} is not a FoundationError"

    @pytest.mark.unit
    def test_foundation_error_inherits_sanskriti_error(self) -> None:
        exc = FoundationError("test")
        assert isinstance(exc, SanskritiError)

    @pytest.mark.unit
    def test_no_collision_with_tenant_not_found_error(self) -> None:
        exc = FoundationTenantSlugNotFoundError("ketikoti")
        assert not isinstance(exc, TenantNotFoundError)
        assert exc.error_code == "TENANT_NOT_FOUND"

    @pytest.mark.unit
    def test_error_codes_match_spec(self) -> None:
        assert FoundationTenantSlugNotFoundError("x").error_code == "TENANT_NOT_FOUND"
        assert ContentNotFoundError(1).error_code == "CONTENT_NOT_FOUND"
        assert InvalidFileTypeError("png").error_code == "INVALID_FILE_TYPE"
        assert FileTooLargeError(1).error_code == "FILE_TOO_LARGE"
        assert RightsNotConfirmedError().error_code == "RIGHTS_NOT_CONFIRMED"
        assert InvalidMagicLinkError().error_code == "INVALID_MAGIC_LINK"
        assert CaptchaFailedError().error_code == "CAPTCHA_FAILED"
        assert TakedownDuplicateError(1).error_code == "TAKEDOWN_DUPLICATE"
        assert ReservedSlugError("api").error_code == "RESERVED_SLUG"
        assert InvalidSlugError("bad").error_code == "INVALID_SLUG"
        assert SlugTakenError("taken").error_code == "SLUG_TAKEN"

    @pytest.mark.unit
    def test_status_codes(self) -> None:
        assert FoundationTenantSlugNotFoundError("x").status_code == 404
        assert ContentNotFoundError(1).status_code == 404
        assert InvalidFileTypeError("png").status_code == 400
        assert FileTooLargeError(1).status_code == 413
        assert RightsNotConfirmedError().status_code == 400
        assert InvalidMagicLinkError().status_code == 401
        assert CaptchaFailedError().status_code == 400
        assert TakedownDuplicateError(1).status_code == 409
        assert ReservedSlugError("api").status_code == 400
        assert InvalidSlugError("bad").status_code == 400
        assert SlugTakenError("taken").status_code == 409

    @pytest.mark.unit
    def test_to_dict_format(self) -> None:
        exc = FoundationTenantSlugNotFoundError("ketikoti")
        d = exc.to_dict()
        assert "error" in d
        assert d["error"]["error_code"] == "TENANT_NOT_FOUND"
        assert "message" in d["error"]
        assert "timestamp" in d["error"]
        assert d["error"]["details"]["slug"] == "ketikoti"
