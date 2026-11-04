"""
Console Output Utility - Unicode-Safe Console Printing
Provides fallback ASCII output for Windows console compatibility
"""

import sys
from typing import Any, Optional

# Unicode to ASCII mapping for common symbols
UNICODE_FALLBACKS = {
    "\u2713": "[OK]",  # Checkmark
    "\u2717": "[FAIL]",  # X mark
    "\u2714": "[OK]",  # Heavy checkmark
    "\u2716": "[FAIL]",  # Heavy X mark
    "\u26a0": "[WARN]",  # Warning sign
    "\u2022": "*",  # Bullet point
    "\u2192": "->",  # Right arrow
    "\u2190": "<-",  # Left arrow
    "\u2194": "<->",  # Left-right arrow
    "\u2026": "...",  # Ellipsis
    "\u00a9": "(C)",  # Copyright
    "\u00ae": "(R)",  # Registered
    "\u2122": "(TM)",  # Trademark
    "\u00b0": "deg",  # Degree symbol
    "\u00b1": "+/-",  # Plus-minus
    "\u00d7": "x",  # Multiplication
    "\u00f7": "/",  # Division
    "\u2665": "<3",  # Heart
    "\u2660": "spade",  # Spade
    "\u2663": "club",  # Club
    "\u2666": "diamond",  # Diamond
    "\ud83d\udd04": "[RELOAD]",  # Reload symbol
}


def safe_print(*args: object, **kwargs: Any) -> None:
    """
    Print with Unicode fallback for Windows console compatibility

    Args:
        *args: Arguments to print
        **kwargs: Keyword arguments for print function
    """
    try:
        # Try normal print first
        print(*args, **kwargs)
    except UnicodeEncodeError:
        # Convert Unicode characters to ASCII fallbacks
        safe_args: list[str] = []
        for arg in args:
            if isinstance(arg, str):
                safe_arg = arg
                for unicode_char, ascii_fallback in UNICODE_FALLBACKS.items():
                    safe_arg = safe_arg.replace(unicode_char, ascii_fallback)
                safe_args.append(safe_arg)
            else:
                safe_args.append(str(arg))

        # Print with ASCII fallbacks
        print(*safe_args, **kwargs)


def safe_format(text: str) -> str:
    """
    Convert Unicode characters to ASCII-safe equivalents

    Args:
        text: Text to convert

    Returns:
        ASCII-safe version of the text
    """
    safe_text = text
    for unicode_char, ascii_fallback in UNICODE_FALLBACKS.items():
        safe_text = safe_text.replace(unicode_char, ascii_fallback)
    return safe_text


def get_console_encoding() -> str:
    """Get current console encoding"""
    return sys.stdout.encoding or "utf-8"


def supports_unicode() -> bool:
    """Check if console supports Unicode output"""
    try:
        # Test printing a Unicode character
        test_char = "\u2713"  # Checkmark
        print(test_char, end="", flush=True)
        # If we get here, Unicode is supported
        print("\b \b", end="", flush=True)  # Erase test character
        return True
    except UnicodeEncodeError:
        return False


def print_status(message: str, status: str = "info", use_unicode: bool | None = None) -> None:
    """
    Print status message with appropriate symbols

    Args:
        message: Message to print
        status: Status type (success, error, warning, info)
        use_unicode: Force Unicode usage (None for auto-detect)
    """
    if use_unicode is None:
        use_unicode = supports_unicode()

    if use_unicode:
        symbols = {
            "success": "\u2713",
            "error": "\u2717",
            "warning": "\u26a0",
            "info": "\u2022",
        }
    else:
        symbols = {
            "success": "[OK]",
            "error": "[FAIL]",
            "warning": "[WARN]",
            "info": "[INFO]",
        }

    symbol = symbols.get(status, symbols["info"])
    safe_print(f"{symbol} {message}")


def print_separator(char: str = "=", length: int = 50) -> None:
    """Print a separator line"""
    safe_print(char * length)


def print_header(title: str, char: str = "=") -> None:
    """Print a formatted header"""
    separator_length = max(50, len(title) + 4)
    safe_print()
    print_separator(char, separator_length)
    safe_print(f"{char} {title.center(separator_length - 4)} {char}")
    print_separator(char, separator_length)
    safe_print()


# Example usage and testing
if __name__ == "__main__":
    print_header("Unicode Console Output Test")

    print_status("Testing Unicode support detection", "info")
    unicode_supported = supports_unicode()
    print_status(
        f"Unicode supported: {unicode_supported}",
        "success" if unicode_supported else "warning",
    )

    print_status("Testing safe print with Unicode", "info")
    safe_print("Unicode test: \u2713 Success \u2717 Error \u26a0 Warning")

    print_status("Testing status printing", "info")
    print_status("This is a success message", "success")
    print_status("This is an error message", "error")
    print_status("This is a warning message", "warning")
    print_status("This is an info message", "info")

    safe_print()
    safe_print(f"Console encoding: {get_console_encoding()}")
