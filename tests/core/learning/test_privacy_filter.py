"""
Unit tests voor PrivacyFilter.

Controleert:
- 100% secret redactie (wachtwoorden, API keys, tokens)
- Tokenizer: variabele-assignments met geheimen worden geanonimiseerd
- Path anonimisering (absoluut → relatief)
- URL query-param verwijdering
- Stack trace verwijdering
- Recursieve filtering van nested dicts
- User ID hashing (onomkeerbaar, consistent)
- Fail-secure: filter_context gooit nooit een onverwachte uitzondering
"""

import pytest

from src.core.learning.privacy.privacy_filter import PrivacyFilter


class TestSecretRedaction:
    """Tests voor regex-gebaseerde secret redactie."""

    def test_password_assignment_redacted(self):
        code = 'config = {"password": "super_secret_123"}'
        result, count = PrivacyFilter._tokenize_and_redact(code)
        assert "super_secret_123" not in result
        assert count > 0

    def test_api_key_assignment_redacted(self):
        code = 'api_key = "sk-abc123xyz456"'
        result, count = PrivacyFilter._tokenize_and_redact(code)
        assert "sk-abc123xyz456" not in result
        assert count > 0

    def test_token_assignment_redacted(self):
        code = "token = 'my_bearer_token_abc'"
        result, count = PrivacyFilter._tokenize_and_redact(code)
        assert "my_bearer_token_abc" not in result
        assert count > 0

    def test_secret_assignment_redacted(self):
        code = 'secret = "my_secret_value"'
        result, count = PrivacyFilter._tokenize_and_redact(code)
        assert "my_secret_value" not in result
        assert count > 0

    def test_bearer_jwt_redacted(self):
        code = "Authorization: Bearer eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ1c2VyIn0.signature"
        result, count = PrivacyFilter._tokenize_and_redact(code)
        assert "eyJhbGciOiJSUzI1NiJ9" not in result
        assert count > 0

    def test_non_secret_code_unchanged(self):
        code = "def hello():\n    return 'world'"
        result, count = PrivacyFilter._tokenize_and_redact(code)
        assert result == code
        assert count == 0

    def test_empty_code_unchanged(self):
        result, count = PrivacyFilter._tokenize_and_redact("")
        assert result == ""
        assert count == 0


class TestTokenizer:
    """Tests voor de tokenizer (variabele-naam anonimisering)."""

    def test_db_password_tokenized(self):
        code = "db_password = 'postgres_pass'"
        result, count = PrivacyFilter._tokenize_and_redact(code)
        assert "postgres_pass" not in result
        assert "var_secret_1" in result
        assert count >= 1

    def test_multiple_secrets_get_unique_tokens(self):
        code = "password = 'secret1'\n" "api_key = 'key123'\n"
        result, count = PrivacyFilter._tokenize_and_redact(code)
        assert "secret1" not in result
        assert "key123" not in result
        assert "var_secret_1" in result
        assert "var_secret_2" in result
        assert count >= 2


class TestPathAnonymization:
    """Tests voor path anonimisering."""

    def test_unix_home_path_anonymized(self):
        path = "/home/john/projects/myapp/src/service.py"
        result = PrivacyFilter._anonymize_path(path)
        assert "john" not in result
        assert "/home/" not in result

    def test_windows_home_path_anonymized(self):
        path = "C:\\Users\\Alice\\Documents\\project\\src\\app.py"
        result = PrivacyFilter._anonymize_path(path)
        assert "Alice" not in result

    def test_long_path_truncated(self):
        path = "/very/deep/nested/path/to/some/file.py"
        result = PrivacyFilter._anonymize_path(path)
        # Should keep only last 3 components
        assert result == ".../path/to/some/file.py" or result.startswith("...")

    def test_short_path_unchanged(self):
        path = "src/utils/helper.py"
        result = PrivacyFilter._anonymize_path(path)
        assert result == path

    def test_empty_path_unchanged(self):
        result = PrivacyFilter._anonymize_path("")
        assert result == ""


class TestUrlFilter:
    """Tests voor URL query-parameter verwijdering."""

    def test_query_params_removed(self):
        url = "https://api.example.com/endpoint?token=abc123&user=john"
        result = PrivacyFilter._filter_url(url)
        assert "token=abc123" not in result
        assert "user=john" not in result
        assert "api.example.com" in result

    def test_path_preserved(self):
        url = "https://api.example.com/v1/users"
        result = PrivacyFilter._filter_url(url)
        assert result == "https://api.example.com/v1/users"

    def test_invalid_url_returns_placeholder(self):
        result = PrivacyFilter._filter_url("not-a-url-:::invalid")
        # Should not raise, returns clean version
        assert isinstance(result, str)


class TestErrorFilter:
    """Tests voor stack trace verwijdering."""

    def test_multiline_error_truncated(self):
        error = (
            "ValueError: invalid literal\n"
            "  File /home/user/app.py, line 42\n"
            "    x = int('abc')\n"
        )
        result = PrivacyFilter._filter_error(error)
        assert "File /home/user/app.py" not in result
        assert "[STACK_TRACE_REDACTED]" in result

    def test_single_line_error_preserved(self):
        error = "ValueError: invalid literal"
        result = PrivacyFilter._filter_error(error)
        assert "ValueError" in result
        assert "[STACK_TRACE_REDACTED]" not in result

    def test_empty_error_unchanged(self):
        result = PrivacyFilter._filter_error("")
        assert result == ""


class TestFilterContext:
    """Tests voor de hoofd filter_context methode."""

    def test_file_path_anonymized(self):
        ctx = {"file_path": "/home/user/project/src/app.py"}
        result = PrivacyFilter.filter_context(ctx)
        assert "user" not in result["file_path"]

    def test_code_snippet_redacted(self):
        ctx = {"code_snippet": "password = 'my_password'"}
        result = PrivacyFilter.filter_context(ctx)
        assert "my_password" not in result["code_snippet"]

    def test_url_query_params_removed(self):
        ctx = {"url": "https://api.example.com/data?token=secret"}
        result = PrivacyFilter.filter_context(ctx)
        assert "token=secret" not in result["url"]

    def test_error_message_filtered(self):
        ctx = {
            "error_message": ("ImportError: cannot import\n" "  File /home/user/app.py, line 1\n")
        }
        result = PrivacyFilter.filter_context(ctx)
        assert "[STACK_TRACE_REDACTED]" in result["error_message"]

    def test_nested_dict_filtered_recursively(self):
        ctx = {
            "meta": {
                "file_path": "/home/user/deep/nested.py",
                "code": "api_key = 'my_actual_secret_value'",
            }
        }
        result = PrivacyFilter.filter_context(ctx)
        assert "user" not in result["meta"]["file_path"]
        # The original secret VALUE must be removed
        assert "my_actual_secret_value" not in result["meta"]["code"]
        assert "[REDACTED]" in result["meta"]["code"]

    def test_list_of_dicts_filtered(self):
        ctx = {
            "items": [
                {"file_path": "/home/user/a.py"},
                {"code": "password = 'x'"},
            ]
        }
        result = PrivacyFilter.filter_context(ctx)
        assert "user" not in result["items"][0]["file_path"]
        assert "'x'" not in result["items"][1]["code"]

    def test_non_sensitive_fields_pass_through(self):
        ctx = {
            "behavior_type": "file_edit",
            "edit_count": 5,
            "success": True,
        }
        result = PrivacyFilter.filter_context(ctx)
        assert result == ctx

    def test_filter_context_never_raises(self):
        """filter_context moet altijd een dict teruggeven, nooit crashen."""
        # Ongewone waarden
        ctx = {
            "none_val": None,
            "int_val": 42,
            "list_val": [1, 2, 3],
            "bool_val": True,
            "normal": "text",
        }
        result = PrivacyFilter.filter_context(ctx)
        assert isinstance(result, dict)


class TestHashUserId:
    """Tests voor gebruiker-ID hashing."""

    def test_hash_is_16_chars(self):
        result = PrivacyFilter.hash_user_id("user@example.com")
        assert len(result) == 16

    def test_hash_is_consistent(self):
        h1 = PrivacyFilter.hash_user_id("same_user")
        h2 = PrivacyFilter.hash_user_id("same_user")
        assert h1 == h2

    def test_different_users_different_hashes(self):
        h1 = PrivacyFilter.hash_user_id("user_a")
        h2 = PrivacyFilter.hash_user_id("user_b")
        assert h1 != h2

    def test_hash_is_hex_string(self):
        result = PrivacyFilter.hash_user_id("test_user")
        assert all(c in "0123456789abcdef" for c in result)

    def test_empty_user_id(self):
        result = PrivacyFilter.hash_user_id("")
        assert result == "unknown"

    def test_hash_with_tenant_salt_differs(self):
        """Zelfde user, andere tenant -> andere hash (tenant isolation)."""
        h1 = PrivacyFilter.hash_user_id("same_user", tenant_id=1)
        h2 = PrivacyFilter.hash_user_id("same_user", tenant_id=2)
        assert h1 != h2

    def test_hash_without_tenant_matches_default(self):
        """Geen tenant_id is equivalent aan tenant_id=0."""
        h1 = PrivacyFilter.hash_user_id("user_x")
        h2 = PrivacyFilter.hash_user_id("user_x", tenant_id=0)
        assert h1 == h2


class TestPIIRedaction:
    """Tests voor algemene PII redactie op string waarden."""

    def test_email_redacted(self):
        ctx = {"message": "Contact me at john.doe@example.com please"}
        result = PrivacyFilter.filter_context(ctx)
        assert "john.doe@example.com" not in result["message"]
        assert "[EMAIL_REDACTED]" in result["message"]

    def test_phone_redacted(self):
        ctx = {"contact": "Call +31 6 12345678"}
        result = PrivacyFilter.filter_context(ctx)
        assert "12345678" not in result["contact"]
        assert "[PHONE_REDACTED]" in result["contact"]

    def test_ipv4_redacted(self):
        ctx = {"source_ip": "192.168.1.100"}
        result = PrivacyFilter.filter_context(ctx)
        assert "192.168.1.100" not in result["source_ip"]
        assert "[IP_REDACTED]" in result["source_ip"]

    def test_ipv6_redacted(self):
        ctx = {"source_ip": "fe80::1ff:fe23:4567:890a"}
        result = PrivacyFilter.filter_context(ctx)
        assert "fe80::1ff:fe23:4567:890a" not in result["source_ip"]
        assert "[IP_REDACTED]" in result["source_ip"]

    def test_pii_in_nested_dict(self):
        ctx = {"meta": {"note": "Email alice@test.org and ip 10.0.0.1"}}
        result = PrivacyFilter.filter_context(ctx)
        assert "alice@test.org" not in result["meta"]["note"]
        assert "10.0.0.1" not in result["meta"]["note"]
        assert "[EMAIL_REDACTED]" in result["meta"]["note"]
        assert "[IP_REDACTED]" in result["meta"]["note"]

    def test_non_pii_string_unchanged(self):
        ctx = {"status": "all systems operational", "count": 42}
        result = PrivacyFilter.filter_context(ctx)
        assert result["status"] == "all systems operational"
        assert result["count"] == 42
