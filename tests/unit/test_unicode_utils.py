"""
Unit Tests for Unicode Utility Functions
Tests cross-platform unicode handling and status icons

Coverage Target: unicode_utils.py → >90%
"""

import logging
import sys
from io import StringIO
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.core.shared.unicode_utils import (
    StatusIcons,
    icons,
    safe_log_info,
    safe_print,
    strip_unicode,
)

# ============================================================================
# TEST: StatusIcons Class
# ============================================================================


class TestStatusIcons:
    """Test StatusIcons unicode/ascii fallback"""

    def test_unicode_enabled_shows_emoji(self):
        """Test unicode mode shows emoji icons"""
        status = StatusIcons(use_unicode=True)

        assert status.success == "✅"
        assert status.warning == "⚠️"
        assert status.error == "❌"
        assert status.info == "ℹ️"
        assert status.rocket == "🚀"
        assert status.check == "✓"

    def test_unicode_disabled_shows_ascii(self):
        """Test ascii fallback mode shows text tags"""
        status = StatusIcons(use_unicode=False)

        assert status.success == "[OK]"
        assert status.warning == "[WARN]"
        assert status.error == "[ERROR]"
        assert status.info == "[INFO]"
        assert status.rocket == "[LAUNCH]"
        assert status.check == "[PASS]"

    def test_auto_detect_unicode_support_success(self):
        """Test auto-detection when unicode is supported"""
        with patch("sys.stdout") as mock_stdout:
            mock_stdout.encoding = "utf-8"
            status = StatusIcons(use_unicode=None)

            # Should detect unicode support
            assert status.use_unicode is True

    def test_auto_detect_unicode_support_failure_no_encoding(self):
        """Test auto-detection when stdout has no encoding"""
        with patch("sys.stdout") as mock_stdout:
            mock_stdout.encoding = None
            status = StatusIcons(use_unicode=None)

            # Should use utf-8 fallback and succeed
            assert status.use_unicode is True

    def test_auto_detect_unicode_support_failure_encode_error(self):
        """Test auto-detection when encoding fails"""
        with patch("sys.stdout") as mock_stdout:
            mock_stdout.encoding = "ascii"
            # ASCII can't encode emoji
            status = StatusIcons(use_unicode=None)

            # Should detect lack of unicode support
            assert status.use_unicode is False

    def test_auto_detect_unicode_support_failure_lookup_error(self):
        """Test auto-detection handles LookupError"""
        with patch("sys.stdout") as mock_stdout:
            mock_stdout.encoding = "invalid-encoding"
            status = StatusIcons(use_unicode=None)

            # Should fallback to False on error
            assert status.use_unicode is False

    def test_auto_detect_unicode_support_failure_attribute_error(self):
        """Test auto-detection handles missing stdout attributes"""
        with patch("sys.stdout", None):
            status = StatusIcons(use_unicode=None)

            # Should handle AttributeError gracefully
            assert status.use_unicode is False

    def test_status_icons_properties_are_strings(self):
        """Test all icon properties return strings"""
        status_unicode = StatusIcons(use_unicode=True)
        status_ascii = StatusIcons(use_unicode=False)

        for status in [status_unicode, status_ascii]:
            assert isinstance(status.success, str)
            assert isinstance(status.warning, str)
            assert isinstance(status.error, str)
            assert isinstance(status.info, str)
            assert isinstance(status.rocket, str)
            assert isinstance(status.check, str)


# ============================================================================
# TEST: safe_print Function
# ============================================================================


class TestSafePrint:
    """Test safe_print unicode handling"""

    def test_safe_print_normal_string(self, capsys):
        """Test safe_print with normal ASCII string"""
        safe_print("Hello World")
        captured = capsys.readouterr()
        assert "Hello World" in captured.out

    def test_safe_print_unicode_string_success(self, capsys):
        """Test safe_print with unicode when supported"""
        safe_print("✅ Unicode test 🚀")
        captured = capsys.readouterr()
        # If environment supports unicode, should print as-is
        assert "test" in captured.out

    def test_safe_print_unicode_encode_error_fallback(self):
        """Test safe_print falls back when UnicodeEncodeError occurs"""
        with patch("builtins.print") as mock_print:
            # First call raises UnicodeEncodeError, second succeeds
            # UnicodeEncodeError(encoding, object, start, end, reason)
            mock_print.side_effect = [
                UnicodeEncodeError("utf-8", "test", 0, 1, "invalid character"),
                None,
            ]

            safe_print("Test with emoji ✅")

            # Should have called print twice (original + fallback)
            assert mock_print.call_count == 2
            # Second call should have [UNICODE_SAFE] prefix
            assert "[UNICODE_SAFE]" in str(mock_print.call_args_list[1])

    def test_safe_print_uses_fallback_encoding(self):
        """Test safe_print uses specified fallback encoding"""
        with patch("builtins.print") as mock_print:
            mock_print.side_effect = [
                UnicodeEncodeError("utf-8", "text", 0, 1, "error"),
                None,
            ]

            safe_print("Unicode text ñ", fallback_encoding="latin-1")

            # Should have attempted fallback with latin-1
            assert mock_print.call_count == 2


# ============================================================================
# TEST: safe_log_info Function
# ============================================================================


class TestSafeLogInfo:
    """Test safe_log_info unicode handling"""

    def test_safe_log_info_with_logger(self):
        """Test safe_log_info with provided logger"""
        mock_logger = Mock(spec=logging.Logger)
        safe_log_info("Test message", logger=mock_logger)

        mock_logger.info.assert_called_once_with("Test message")

    def test_safe_log_info_without_logger(self):
        """Test safe_log_info creates default logger"""
        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = Mock(spec=logging.Logger)
            mock_get_logger.return_value = mock_logger

            safe_log_info("Default logger message")

            mock_get_logger.assert_called_once()
            mock_logger.info.assert_called_once()

    def test_safe_log_info_unicode_encode_error_fallback(self):
        """Test safe_log_info handles UnicodeEncodeError"""
        mock_logger = Mock(spec=logging.Logger)
        # First call raises error, second succeeds
        mock_logger.info.side_effect = [
            UnicodeEncodeError("utf-8", "message", 0, 1, "invalid"),
            None,
        ]

        safe_log_info("Unicode message ✅", logger=mock_logger)

        # Should have called info twice (original + fallback)
        assert mock_logger.info.call_count == 2
        # Second call should have [UNICODE_SAFE] prefix
        fallback_call = mock_logger.info.call_args_list[1][0][0]
        assert "[UNICODE_SAFE]" in fallback_call

    def test_safe_log_info_preserves_ascii_in_fallback(self):
        """Test safe_log_info preserves ASCII characters in fallback"""
        mock_logger = Mock(spec=logging.Logger)
        mock_logger.info.side_effect = [
            UnicodeEncodeError("utf-8", "status", 0, 1, "invalid"),
            None,
        ]

        safe_log_info("Status: PASSED ✅", logger=mock_logger)

        # Check fallback message contains ASCII parts
        fallback_call = mock_logger.info.call_args_list[1][0][0]
        assert "Status" in fallback_call
        assert "PASSED" in fallback_call


# ============================================================================
# TEST: strip_unicode Function
# ============================================================================


class TestStripUnicode:
    """Test strip_unicode character removal"""

    def test_strip_unicode_ascii_only(self):
        """Test strip_unicode preserves ASCII text"""
        result = strip_unicode("Hello World 123")
        assert result == "Hello World 123"

    def test_strip_unicode_removes_emoji(self):
        """Test strip_unicode removes emoji"""
        result = strip_unicode("Status: ✅ Success 🚀")
        assert result == "Status:  Success "
        assert "✅" not in result
        assert "🚀" not in result

    def test_strip_unicode_removes_symbols(self):
        """Test strip_unicode removes unicode symbols"""
        result = strip_unicode("Warning ⚠️ Error ❌")
        assert result == "Warning  Error "
        assert "⚠️" not in result
        assert "❌" not in result

    def test_strip_unicode_removes_accented_characters(self):
        """Test strip_unicode removes accented characters"""
        result = strip_unicode("Café naïve résumé")
        assert result == "Caf nave rsum"

    def test_strip_unicode_empty_string(self):
        """Test strip_unicode handles empty string"""
        result = strip_unicode("")
        assert result == ""

    def test_strip_unicode_only_unicode(self):
        """Test strip_unicode with only unicode characters"""
        result = strip_unicode("✅⚠️❌")
        assert result == ""

    def test_strip_unicode_mixed_content(self):
        """Test strip_unicode with mixed ASCII and unicode"""
        result = strip_unicode("Test 123 ✓ Done ñ End")
        assert result == "Test 123  Done  End"


# ============================================================================
# TEST: Global Icons Instance
# ============================================================================


class TestGlobalIconsInstance:
    """Test global icons singleton"""

    def test_global_icons_exists(self):
        """Test global icons instance is created"""
        assert icons is not None
        assert isinstance(icons, StatusIcons)

    def test_global_icons_has_all_properties(self):
        """Test global icons has all expected properties"""
        assert hasattr(icons, "success")
        assert hasattr(icons, "warning")
        assert hasattr(icons, "error")
        assert hasattr(icons, "info")
        assert hasattr(icons, "rocket")
        assert hasattr(icons, "check")

    def test_global_icons_returns_strings(self):
        """Test global icons properties return strings"""
        assert isinstance(icons.success, str)
        assert isinstance(icons.warning, str)
        assert isinstance(icons.error, str)
        assert isinstance(icons.info, str)
        assert isinstance(icons.rocket, str)
        assert isinstance(icons.check, str)

    def test_global_icons_detects_environment(self):
        """Test global icons auto-detects unicode support"""
        # Should have auto-detected based on environment
        assert isinstance(icons.use_unicode, bool)


# ============================================================================
# TEST: Edge Cases
# ============================================================================


class TestEdgeCases:
    """Test edge cases and error handling"""

    def test_status_icons_explicit_false(self):
        """Test StatusIcons with explicit False"""
        status = StatusIcons(use_unicode=False)
        assert status.use_unicode is False
        assert status.success == "[OK]"

    def test_status_icons_explicit_true(self):
        """Test StatusIcons with explicit True"""
        status = StatusIcons(use_unicode=True)
        assert status.use_unicode is True
        assert status.success == "✅"

    def test_safe_print_with_newlines(self, capsys):
        """Test safe_print preserves newlines"""
        safe_print("Line 1\nLine 2\nLine 3")
        captured = capsys.readouterr()
        assert "Line 1" in captured.out
        assert "Line 2" in captured.out
        assert "Line 3" in captured.out

    def test_safe_log_info_with_multiline(self):
        """Test safe_log_info handles multiline messages"""
        mock_logger = Mock(spec=logging.Logger)
        message = "Line 1\nLine 2\nLine 3"
        safe_log_info(message, logger=mock_logger)

        mock_logger.info.assert_called_once_with(message)

    def test_strip_unicode_preserves_numbers(self):
        """Test strip_unicode preserves numbers"""
        result = strip_unicode("Test 123 ✅ 456")
        assert "123" in result
        assert "456" in result

    def test_strip_unicode_preserves_punctuation(self):
        """Test strip_unicode preserves ASCII punctuation"""
        result = strip_unicode("Hello, World! (Test)")
        assert result == "Hello, World! (Test)"
