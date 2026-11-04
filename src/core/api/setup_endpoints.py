# orphan:exempt reason: nog niet gemigreerd naar v1/; TODO(SP-VOLGENDE): migreer naar v1/<domein>/
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.core.services.setup_service import SetupService
from src.core.shared.config import is_setup_mode_enabled
from src.core.exceptions import ValidatieFout

logger = logging.getLogger(__name__)

router = APIRouter()


class SetupRequest(BaseModel):
    openai_api_key: str = Field(min_length=10, max_length=512)
    tenant_name: str = Field(min_length=1, max_length=200)
    admin_email: str = Field(min_length=3, max_length=320)
    smtp_host: str | None = Field(default=None, max_length=255)


@router.post("/init")
async def initialize_setup(request: SetupRequest) -> dict[str, str]:
    if not is_setup_mode_enabled():
        raise HTTPException(status_code=404, detail="Not found")

    service = SetupService()

    try:
        if service.setup_artifact_exists():
            raise HTTPException(status_code=409, detail="Setup has already been initialized")
    except ValidatieFout as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Ongeldig verzoek.") from e

    # Validate API Key
    is_valid = await service.validate_openai_key(request.openai_api_key)
    if not is_valid:
        raise HTTPException(status_code=400, detail="Invalid OpenAI API Key")

    try:
        # Write to the reviewed bootstrap artifact only when setup mode is enabled.
        service.write_env_file(
            {
                "OPENAI_API_KEY": request.openai_api_key,
                "INITIAL_TENANT_NAME": request.tenant_name,
                "INITIAL_ADMIN_EMAIL": request.admin_email,
                "SMTP_HOST": request.smtp_host or "",
            }
        )
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail="Setup has already been initialized") from e
    except PermissionError as e:
        if str(e) == "Setup mode is disabled":
            raise HTTPException(status_code=403, detail="Setup mode is disabled") from e
        logger.error("Setup bootstrap artifact write failed", exc_info=True)
        raise HTTPException(status_code=500, detail="Setup initialization failed") from e
    except ValidatieFout as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Ongeldig verzoek.") from e
    except Exception as e:
        logger.error("Setup initialization failed", exc_info=True)
        raise HTTPException(status_code=500, detail="Setup initialization failed") from e

    # In a real app we might trigger os.kill(os.getpid(), signal.SIGTERM) or similar to let supervisor restart it
    # service.restart_server()

    return {
        "status": "ok",
        "message": "Setup successful. Bootstrap artifact updated.",
        "artifact_name": service.artifact_name(),
    }
