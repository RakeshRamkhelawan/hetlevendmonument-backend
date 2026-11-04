# core/tool_broker/main.py

from fastapi import FastAPI

from src.core.shared.environment import is_development as _is_development

from .router import router


# Dit is een module-level app-object voor een aparte service. Er is vandaag geen entrypoint
# die hem serveert, maar hij publiceerde zijn volledige schema onvoorwaardelijk -- zodra
# iemand hem wel mount is dat hetzelfde gat als OP-124.
app = FastAPI(
    title="Tool Broker Service",
    description="A centralized service for executing powerful tools.",
    version="1.0.0",
    docs_url="/docs" if _is_development() else None,
    redoc_url="/redoc" if _is_development() else None,
    openapi_url="/openapi.json" if _is_development() else None,
)

app.include_router(router)


@app.get("/", tags=["Health Check"])
async def read_root() -> dict[str, str]:
    return {"status": "ok", "message": "Tool Broker Service is running."}
