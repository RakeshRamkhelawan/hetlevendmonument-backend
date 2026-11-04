"""SEC-003+013: streaming ValueError mag geen intern foutdetail lekken naar client.

Architecture test: controleert dat chat_router.py een generiek foutbericht gebruikt
voor ValueError in de generate() streaming handler, NIET str(e).
"""

from pathlib import Path


class TestStreamingErrorDisclosure:
    """ValueError in streaming moet een generiek foutbericht retourneren (SEC-003+013)."""

    def test_streaming_value_error_uses_generic_message_not_str_e(self):
        """generate() in chat_router.py MOET een generiek bericht gebruiken bij ValueError.

        FOUT (huidig): yield f"data: {json.dumps({'error': str(e)})}"
        GOED (fix):    yield f"data: {json.dumps({'error': 'Chat processing error. Please retry.'})}"
        """
        source = (
            Path(__file__).resolve().parents[5] / "src/core/api/v1/cva/chat_router.py"
        ).read_text(encoding="utf-8")

        # Find the ValueError handler in the generate() streaming function
        # The fix must NOT use str(e) for ValueError -- it should use a generic message
        # Search for the pattern after the except ValueError block
        lines = source.splitlines()
        value_error_handler_uses_str_e = False
        in_value_error_block = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("except ValueError as e:"):
                in_value_error_block = True
            elif in_value_error_block:
                if stripped.startswith("except ") or stripped.startswith("finally"):
                    in_value_error_block = False
                elif "str(e)" in stripped and "error" in stripped and "yield" in stripped:
                    value_error_handler_uses_str_e = True
                    break

        assert not value_error_handler_uses_str_e, (
            "chat_router.py streaming ValueError handler gebruikt str(e) in de SSE payload. "
            "SEC-003+013: dit lekt intern foutdetail naar de client. "
            "Fix: vervang door een generiek foutbericht zoals 'Chat processing error. Please retry.'"
        )

    def test_streaming_value_error_handler_logs_with_exc_info(self):
        """ValueError in generate() MOET worden gelogd met exc_info=True (SEC-003 + BE-003)."""
        source = (
            Path(__file__).resolve().parents[5] / "src/core/api/v1/cva/chat_router.py"
        ).read_text(encoding="utf-8")

        lines = source.splitlines()
        value_error_has_exc_info_log = False
        in_value_error_block = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("except ValueError as e:"):
                in_value_error_block = True
            elif in_value_error_block:
                if stripped.startswith("except ") or stripped.startswith("finally"):
                    in_value_error_block = False
                elif (
                    "logger." in stripped and "exc_info" in stripped
                ) or stripped == "exc_info=True,":
                    # Handles both inline: logger.error(..., exc_info=True)
                    # and multi-line continuation: exc_info=True, on its own line.
                    value_error_has_exc_info_log = True
                    break

        assert value_error_has_exc_info_log, (
            "chat_router.py streaming ValueError handler logt NIET met exc_info=True. "
            "BE-003: add logger.error(..., exc_info=True) in de ValueError-branch van generate()."
        )
