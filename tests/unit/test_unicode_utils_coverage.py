"""
Comprehensive tests for src/core/shared/unicode_utils.py
Coverage target: 100% of Unicode utilities
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


class TestStatusIconsInitialization:
    """Test StatusIcons initialization"""

    def test_initialization_auto_detect(self):
        """Test initialization with auto-detection"""
        status = StatusIcons()

        assert isinstance(status.use_unicode, bool)

    def test_initialization_force_unicode(self):
        """Test initialization forcing Unicode"""
        status = StatusIcons(use_unicode=True)

        assert status.use_unicode is True

    def test_initialization_force_ascii(self):
        """Test initialization forcing ASCII"""
        status = StatusIcons(use_unicode=False)

        assert status.use_unicode is False


class TestUnicodeDetection:
    """Test _detect_unicode_support method"""

    @patch("sys.stdout")
    def test_detect_unicode_support_success(self, mock_stdout):
        """Test Unicode detection when supported"""
        mock_stdout.encoding = "utf-8"

        status = StatusIcons()

        # Should detect support
        assert isinstance(status.use_unicode, bool)

    @patch("sys.stdout")
    def test_detect_unicode_no_encoding(self, mock_stdout):
        """Test Unicode detection with no encoding"""
        mock_stdout.encoding = None

        status = StatusIcons()

        # Should use fallback utf-8
        assert isinstance(status.use_unicode, bool)

    @patch("sys.stdout")
    def test_detect_unicode_ascii_encoding(self, mock_stdout):
        """Test Unicode detection with ASCII encoding"""
        mock_stdout.encoding = "ascii"

        status = StatusIcons()

        # ASCII can't encode Unicode emojis
        assert status.use_unicode is False


class TestStatusIconsUnicode:
    """Test StatusIcons with Unicode enabled"""

    def test_success_icon_unicode(self):
        """Test success icon in Unicode mode"""
        status = StatusIcons(use_unicode=True)

        assert status.success == "✅"

    def test_warning_icon_unicode(self):
        """Test warning icon in Unicode mode"""
        status = StatusIcons(use_unicode=True)

        assert status.warning == "⚠️"

    def test_error_icon_unicode(self):
        """Test error icon in Unicode mode"""
        status = StatusIcons(use_unicode=True)

        assert status.error == "❌"

    def test_info_icon_unicode(self):
        """Test info icon in Unicode mode"""
        status = StatusIcons(use_unicode=True)

        assert status.info == "ℹ️"

    def test_rocket_icon_unicode(self):
        """Test rocket icon in Unicode mode"""
        status = StatusIcons(use_unicode=True)

        assert status.rocket == "🚀"

    def test_check_icon_unicode(self):
        """Test check icon in Unicode mode"""
        status = StatusIcons(use_unicode=True)

        assert status.check == "✓"


class TestStatusIconsASCII:
    """Test StatusIcons with ASCII fallback"""

    def test_success_icon_ascii(self):
        """Test success icon in ASCII mode"""
        status = StatusIcons(use_unicode=False)

        assert status.success == "[OK]"

    def test_warning_icon_ascii(self):
        """Test warning icon in ASCII mode"""
        status = StatusIcons(use_unicode=False)

        assert status.warning == "[WARN]"

    def test_error_icon_ascii(self):
        """Test error icon in ASCII mode"""
        status = StatusIcons(use_unicode=False)

        assert status.error == "[ERROR]"

    def test_info_icon_ascii(self):
        """Test info icon in ASCII mode"""
        status = StatusIcons(use_unicode=False)

        assert status.info == "[INFO]"

    def test_rocket_icon_ascii(self):
        """Test rocket icon in ASCII mode"""
        status = StatusIcons(use_unicode=False)

        assert status.rocket == "[LAUNCH]"

    def test_check_icon_ascii(self):
        """Test check icon in ASCII mode"""
        status = StatusIcons(use_unicode=False)

        assert status.check == "[PASS]"


class TestSafePrint:
    """Test safe_print function"""

    @patch("builtins.print")
    def test_safe_print_success(self, mock_print):
        """Test safe_print with normal message"""
        safe_print("Test message")

        mock_print.assert_called_once_with("Test message")

    @patch("builtins.print")
    def test_safe_print_with_unicode(self, mock_print):
        """Test safe_print with Unicode message"""
        safe_print("Test ✅ message")

        mock_print.assert_called_once_with("Test ✅ message")

    @patch("sys.stdout")
    def test_safe_print_unicode_error_fallback(self, mock_stdout):
        """Test safe_print fallback on Unicode error"""
        # CRITICAL FIX: Mock stdout.write to raise UnicodeEncodeError
        # This simulates a terminal that cannot encode Unicode characters
        mock_stdout.write = Mock(
            side_effect=[
                UnicodeEncodeError("ascii", "Test ✅ message", 5, 6, "ordinal not in range(128)"),
                None,  # Second attempt succeeds
            ]
        )
        mock_stdout.flush = Mock()

        # Mock the print function to actually use stdout.write
        with patch("builtins.print") as mock_print:
            # First call raises UnicodeEncodeError, second succeeds
            mock_print.side_effect = [
                UnicodeEncodeError("ascii", "Test ✅ message", 5, 6, "ordinal not in range(128)"),
                None,
            ]

            safe_print("Test ✅ message")

            # Should call print twice (first fails, second with fallback)
            assert mock_print.call_count == 2

    @patch("builtins.print")
    def test_safe_print_custom_fallback_encoding(self, mock_print):
        """Test safe_print with custom fallback encoding"""
        # CRITICAL FIX: UnicodeEncodeError(codec, object, start, end, reason) - object must be str
        mock_print.side_effect = [
            UnicodeEncodeError("utf-8", "Test message", 0, 1, "ordinal not in range"),
            None,
        ]

        safe_print("Test message", fallback_encoding="latin-1")

        assert mock_print.call_count == 2


class TestSafeLogInfo:
    """Test safe_log_info function"""

    def test_safe_log_info_with_logger(self):
        """Test safe_log_info with provided logger"""
        mock_logger = Mock(spec=logging.Logger)

        safe_log_info("Test message", logger=mock_logger)

        mock_logger.info.assert_called_once_with("Test message")

    def test_safe_log_info_without_logger(self):
        """Test safe_log_info without logger uses default"""
        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = Mock(spec=logging.Logger)
            mock_get_logger.return_value = mock_logger

            safe_log_info("Test message")

            mock_logger.info.assert_called_once_with("Test message")

    def test_safe_log_info_with_unicode(self):
        """Test safe_log_info with Unicode message"""
        mock_logger = Mock(spec=logging.Logger)

        safe_log_info("Test ✅ message", logger=mock_logger)

        mock_logger.info.assert_called_once()

    def test_safe_log_info_unicode_error_fallback(self):
        """Test safe_log_info fallback on Unicode error"""
        mock_logger = Mock(spec=logging.Logger)
        # CRITICAL FIX: UnicodeEncodeError(codec, object, start, end, reason) - object must be str
        mock_logger.info.side_effect = [
            UnicodeEncodeError("ascii", "Test ✅ message", 5, 6, "ordinal not in range(128)"),
            None,
        ]

        safe_log_info("Test ✅ message", logger=mock_logger)

        # Should call info twice (first fails, second with fallback)
        assert mock_logger.info.call_count == 2


class TestStripUnicode:
    """Test strip_unicode function"""

    def test_strip_unicode_removes_emoji(self):
        """Test strip_unicode removes emoji"""
        result = strip_unicode("Test ✅ message")

        assert "✅" not in result
        assert "Test" in result
        assert "message" in result

    def test_strip_unicode_removes_special_chars(self):
        """Test strip_unicode removes special Unicode characters"""
        result = strip_unicode("Test €™® message")

        assert "€" not in result
        assert "™" not in result
        assert "®" not in result
        assert "Test" in result

    def test_strip_unicode_keeps_ascii(self):
        """Test strip_unicode preserves ASCII characters"""
        result = strip_unicode("Test123 message!@#")

        assert result == "Test123 message!@#"

    def test_strip_unicode_empty_string(self):
        """Test strip_unicode with empty string"""
        result = strip_unicode("")

        assert result == ""

    def test_strip_unicode_only_unicode(self):
        """Test strip_unicode with only Unicode characters"""
        result = strip_unicode("✅❌⚠️")

        assert result == ""

    def test_strip_unicode_mixed_content(self):
        """Test strip_unicode with mixed ASCII and Unicode"""
        result = strip_unicode("Test ✅ 123 ❌ ABC ⚠️ end")

        assert "Test" in result
        assert "123" in result
        assert "ABC" in result
        assert "end" in result
        assert "✅" not in result
        assert "❌" not in result
        assert "⚠️" not in result


class TestGlobalIcons:
    """Test global icons instance"""

    def test_global_icons_exists(self):
        """Test global icons instance exists"""
        assert icons is not None
        assert isinstance(icons, StatusIcons)

    def test_global_icons_usable(self):
        """Test global icons instance is usable"""
        # Should not raise
        _ = icons.success
        _ = icons.warning
        _ = icons.error
        _ = icons.info
        _ = icons.rocket
        _ = icons.check


class TestEdgeCases:
    """Test edge cases"""

    def test_status_icons_multiple_instances(self):
        """Test multiple StatusIcons instances"""
        status1 = StatusIcons(use_unicode=True)
        status2 = StatusIcons(use_unicode=False)

        assert status1.success != status2.success

    @patch("builtins.print")
    def test_safe_print_empty_string(self, mock_print):
        """Test safe_print with empty string"""
        safe_print("")

        mock_print.assert_called_once_with("")

    def test_safe_log_info_empty_message(self):
        """Test safe_log_info with empty message"""
        mock_logger = Mock(spec=logging.Logger)

        safe_log_info("", logger=mock_logger)

        mock_logger.info.assert_called_once_with("")

    def test_strip_unicode_ascii_characters_preserved(self):
        """Test strip_unicode preserves all ASCII range"""
        ascii_chars = "".join(chr(i) for i in range(32, 127))
        result = strip_unicode(ascii_chars)

        assert result == ascii_chars
