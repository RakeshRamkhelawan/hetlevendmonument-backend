"""AIACT-002: ChatResponse schema MOET decision_id bevatten.

Test is ROOD totdat cva_schemas.py is bijgewerkt.
"""


def test_chat_response_schema_has_decision_id():
    """ChatResponse schema bevat decision_id veld (AIACT-002)."""
    from src.core.schemas.cva_schemas import ChatResponse

    fields = ChatResponse.model_fields
    assert "decision_id" in fields, (
        "ChatResponse mist decision_id veld. "
        "Voeg toe: decision_id: str | None = None "
        "voor Right-to-Explanation (EU AI Act Art. 13)."
    )


def test_chat_response_decision_id_is_optional():
    """decision_id is optioneel (None als council niet beschikbaar)."""
    from src.core.schemas.cva_schemas import ChatResponse

    fields = ChatResponse.model_fields
    assert "decision_id" in fields, "decision_id ontbreekt in ChatResponse"
    field = fields["decision_id"]
    assert field.default is None or field.is_required() is False, (
        "decision_id moet optioneel zijn (default=None). "
        "Council kan niet beschikbaar zijn bij degraded mode."
    )
