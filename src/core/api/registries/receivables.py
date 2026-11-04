"""Receivables domain registry (ADR-033 Laag 3, max 80 regels). Debiteurenagent dag 2."""

from fastapi import FastAPI


def register(app: FastAPI) -> int:
    """Register the receivables domain router and the four-eyes setting. Returns count.

    De vier-ogen-instelling (dag 3) staat hier en niet in `optional.py`: dat bestand zit op de
    grens van 80 regels, en de instelling is er gekomen voor de debiteurenagent.
    """
    from src.core.api.v1.receivables import router as receivables_router
    from src.core.api.v1.tool_broker.four_eyes_router import router as four_eyes_router

    app.include_router(receivables_router)
    app.include_router(four_eyes_router)
    return 2
