import asyncio
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from typing import Any, cast

import httpx
from fastapi import Depends, HTTPException, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.activepieces.schemas import PieceRead
from src.core.activepieces.stappencontrole import (
    NietToegestaneStap,
    beoordeel_schrijfopdracht,
    controleer_flowdefinitie,
)
from src.core.activepieces.transformer import FlowTransformer
from src.core.activepieces.verbinding import (
    ApProjectIsNietVanDezeKlantError,
    ApRessourceNietGevondenError,
    ApVerbinding,
    ap_verbinding_voor,
)
from src.core.database.database import get_db
from src.core.middleware.tenant_context import safe_get_tenant_id
from src.core.monitoring.prometheus_metrics import (
    record_activepieces_error,
    record_activepieces_latency,
    set_activepieces_status,
)
from src.core.security.egress_control import EgressController
from src.core.shared.tool_broker_resilience import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerState,
    RetryConfig,
    async_retry,
)


#: Wat de klant te zien krijgt als een uitvoering mislukt. Nooit `str(e)`: een httpx-fout noemt het
#: hele interne AP-adres. Het soort fout en de details staan alleen in het log.
UITVOERFOUT = "De workflow kon niet worden uitgevoerd. Probeer het later opnieuw."


def _host(adres: str) -> str:
    """Alleen de host van een adres, voor in het log (geen pad en geen query)."""
    return urlsplit(adres).hostname or "onbekend"


@dataclass
class ActivePiecesClientConfig:
    """Configuration for ActivePieces client behavior."""

    timeout_seconds: float = 30.0
    connect_timeout_seconds: float = 10.0
    max_retries: int = 3
    retry_initial_delay_ms: int = 500
    retry_max_delay_ms: int = 10000
    circuit_failure_threshold: int = 5
    circuit_timeout_seconds: int = 60


class ActivePiecesClient:
    """
    Async client for interacting with the self-hosted ActivePieces instance.

    Features:
    - Circuit breaker pattern for failure isolation
    - Exponential backoff retry with jitter
    - Configurable timeouts
    - Prometheus metrics integration
    - Graceful degradation
    """

    # Een circuit breaker PER AP-adres, gedeeld tussen de instanties van hetzelfde adres. Elke tenant
    # heeft zijn eigen AP; met een proces-brede breaker zette een kapotte of onbereikbare AP van
    # EEN tenant de toegang van alle tenants op "open" (Gate 2 dag 2, M1).
    _circuit_breakers: dict[str, CircuitBreaker] = {}
    # `_lock` stond hier als `asyncio.Lock()` (ADR-036 OP-16-vondst) maar werd nergens
    # gebruikt -- gemeten met een grep op `ActivePiecesClient._lock`/`self._lock`, nul
    # treffers buiten deze declaratie. Verwijderd i.p.v. lazy gemaakt: er is niets om
    # thread-safe te maken.

    def __init__(
        self,
        verbinding: ApVerbinding,
        config: ActivePiecesClientConfig | None = None,
        egress_controller: EgressController | None = None,
    ) -> None:
        # De verbinding is van EEN tenant en komt uit `ap_verbinding_voor` (ADR-040 B3/B4); de
        # client leest zelf geen algemene URL of wachtwoord meer en kiest nooit een ander project.
        self._verbinding = verbinding
        self.client_config = config or ActivePiecesClientConfig()
        self.internal_url = verbinding.base_url
        self.base_url = self.internal_url

        self.service_email = verbinding.email
        self.service_password = verbinding.wachtwoord

        self.token: str | None = None
        self._token_expiry: datetime | None = None
        self._token_lock = asyncio.Lock()  # Thread-safe token refresh

        # Egress control (feature-flagged)
        self._egress_controller = egress_controller
        self._egress_enabled = os.getenv("FEATURE_FLAG_EGRESS_CONTROL", "").lower() == "true"

        # Configurable timeout
        self.timeout = httpx.Timeout(
            self.client_config.timeout_seconds, connect=self.client_config.connect_timeout_seconds
        )

        # Retry configuration
        self.retry_config = RetryConfig(
            max_attempts=self.client_config.max_retries,
            initial_delay_ms=self.client_config.retry_initial_delay_ms,
            max_delay_ms=self.client_config.retry_max_delay_ms,
            retry_on_exceptions=(httpx.RequestError, httpx.HTTPStatusError),
        )

        # Initialize circuit breaker (singleton pattern)
        self._init_circuit_breaker()

    def _init_circuit_breaker(self) -> None:
        """Maak de breaker van dit AP-adres en project, als die er nog niet is."""
        if self._breaker_sleutel not in ActivePiecesClient._circuit_breakers:
            cb_config = CircuitBreakerConfig(
                failure_threshold=self.client_config.circuit_failure_threshold,
                timeout_seconds=self.client_config.circuit_timeout_seconds,
                success_threshold=2,
                half_open_requests=3,
            )
            ActivePiecesClient._circuit_breakers[self._breaker_sleutel] = CircuitBreaker(
                name=f"activepieces_api:{self._breaker_sleutel}", config=cb_config
            )

    @property
    def _breaker_sleutel(self) -> str:
        """Adres EN project: de breaker telt elke fout, ook een 404, dus een tenant die op een
        gedeeld adres veel vreemde id's vraagt mag alleen zijn eigen project dichtzetten."""
        return f"{self.base_url}|{self.project_id}"

    @property
    def tenant_id(self) -> int:
        """De tenant van wie deze verbinding is."""
        return self._verbinding.tenant_id

    @property
    def project_id(self) -> str:
        """Het ENE project van deze tenant. Er is geen zoekfunctie die er een kiest."""
        return self._verbinding.project_id

    def eigen_project(self, project_id: str | None) -> str:
        """Het project van deze tenant; een ander project is een weigering (403).

        Elke methode die een `project_id` van een aanroeper aanneemt, loopt hierlangs: de client
        logt in met een serviceaccount dat bij ELK project kan, dus alleen deze controle houdt een
        tenant in zijn eigen project. `None` betekent "het eigen project".
        """
        if project_id is not None and project_id != self.project_id:
            logger.warning("ap_vreemd_project_geweigerd", tenant_id=self.tenant_id)
            raise ApProjectIsNietVanDezeKlantError()
        return self.project_id

    @property
    def circuit_breaker(self) -> CircuitBreaker:
        """De breaker van het AP-adres van deze tenant."""
        cb = ActivePiecesClient._circuit_breakers.get(self._breaker_sleutel)
        if cb is None:
            raise RuntimeError("Circuit breaker not initialized")
        return cb

    def is_available(self) -> bool:
        """Check if ActivePieces service is available (circuit not open)."""
        return self.circuit_breaker.state != CircuitBreakerState.OPEN

    async def _get_token(self) -> str:
        """Thread-safe token retrieval with refresh."""
        async with self._token_lock:
            token = self.token
            token_valid = (
                token is not None
                and self._token_expiry is not None
                and datetime.now(timezone.utc) < self._token_expiry
            )
            if token_valid:
                return str(token)
            await self._authenticate()
            new_token = self.token
            if new_token is None:
                raise RuntimeError("Failed to obtain authentication token")
            return str(new_token)

    async def _check_egress(self, url: str) -> None:
        """Validate URL against egress policy if feature flag is enabled."""
        if not self._egress_enabled or self._egress_controller is None:
            return

        from src.core.exceptions.exceptions import EgressBlockedError
        from src.core.security.egress_control import EgressDecision

        result = await self._egress_controller.validate_request(
            url=url,
            tenant_id=0,  # system/service tenant
        )
        if result.decision != EgressDecision.ALLOW:
            raise EgressBlockedError(
                url=url, reason=result.reason or "Egress policy denied", tenant_id=0
            )

    async def _authenticate(self) -> None:
        """Internal authentication with retry logic."""
        url = f"{self.base_url}/authentication/sign-in"
        await self._check_egress(url)
        start_time = datetime.now(timezone.utc)

        async def _do_auth() -> dict[str, object]:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    url,
                    json={
                        "email": self.service_email,
                        "password": self.service_password,
                    },
                )
                response.raise_for_status()
                return cast(dict[str, object], response.json())

        try:
            data = await async_retry(_do_auth, config=self.retry_config)
            self.token = cast(str | None, data.get("token"))
            self._token_expiry = datetime.now(timezone.utc) + timedelta(hours=23)

            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            record_activepieces_latency("authenticate", duration)
            set_activepieces_status(True)
            logger.info("activepieces_authenticated", expiry=self._token_expiry.isoformat())

        except httpx.HTTPStatusError as e:
            record_activepieces_error("authenticate", "http_error")
            set_activepieces_status(False)
            logger.error("activepieces_auth_failed", status_code=e.response.status_code)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not authenticate with Automation Engine",
            )
        except httpx.RequestError as e:
            record_activepieces_error("authenticate", "connection_error")
            set_activepieces_status(False)
            logger.error(
                "activepieces_unreachable",
                tenant_id=self.tenant_id,
                host=_host(self.base_url),
                soort=type(e).__name__,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Automation Engine unreachable",
            )

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        operation_name: str,
        json_data: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
    ) -> dict[str, object]:
        """
        Make an authenticated request through circuit breaker with retry.

        Args:
            method: HTTP method (GET, POST, DELETE, etc.)
            endpoint: API endpoint (without base URL)
            operation_name: Name for metrics/logging
            json_data: Optional JSON body
            params: Optional query parameters

        Returns:
            Response JSON

        Raises:
            HTTPException: If request fails after retries or circuit is open
        """
        if not self.is_available():
            logger.warning("activepieces_circuit_open", operation=operation_name)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Automation Engine temporarily unavailable (circuit open)",
            )

        token = await self._get_token()
        # httpx zet zelf `Content-Type: application/json` zodra er een body is. Zonder body mag
        # het niet: AP antwoordt dan 400 (gemeten 2026-10-25 op DELETE /app-connections/{id}).
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{self.base_url}{endpoint}"
        await self._check_egress(url)
        start_time = datetime.now(timezone.utc)

        async def _do_request() -> dict[str, object]:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=json_data,
                    params=cast(
                        # TODO(TYPE): replace Any with concrete type
                        dict[str, Any] | None,
                        params,
                    ),  # TODO(TYPE): replace Any with concrete type
                )
                response.raise_for_status()
                return cast(dict[str, object], response.json()) if response.content else {}

        try:
            result = await self.circuit_breaker.call(_do_request)

            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            record_activepieces_latency(operation_name, duration)
            logger.debug(
                "activepieces_request_success", operation=operation_name, duration=duration
            )

            return result

        except httpx.HTTPStatusError as e:
            record_activepieces_error(operation_name, "http_error")
            logger.warning(
                "activepieces_request_failed",
                operation=operation_name,
                status_code=e.response.status_code,
            )
            raise
        except httpx.RequestError as e:
            record_activepieces_error(operation_name, "connection_error")
            logger.error(
                "activepieces_request_error",
                operation=operation_name,
                tenant_id=self.tenant_id,
                host=_host(self.base_url),
                soort=type(e).__name__,
            )
            raise

    async def _eigen(
        self, endpoint: str, operation_name: str, soort: str
    ) -> dict[str, object]:
        """Haal een ding op en toets dat het in HET project van deze tenant staat (404 anders).

        Elke methode die een id uit een pad of verzoek aanneemt loopt hier langs. Het
        serviceaccount kan bij elk project; alleen deze controle houdt een tenant bij zijn eigen
        flows, runs en verbindingen. "Staat niet bij AP" en "staat in een ander project" geven
        hetzelfde antwoord, en een antwoord zonder `projectId` telt als niet van deze tenant.
        """
        try:
            data = await self._make_request(
                method="GET", endpoint=endpoint, operation_name=operation_name
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (403, 404):
                raise ApRessourceNietGevondenError(soort) from e
            raise
        # Een verbinding heeft bij AP een LIJST `projectIds`; alleen exact het eigen project telt,
        # een met een ander project gedeelde verbinding is niet van deze tenant (fail-closed).
        van_deze_tenant = data.get("projectId") == self.project_id or data.get("projectIds") == [
            self.project_id
        ]
        if not van_deze_tenant:
            logger.warning("ap_vreemd_id_geweigerd", tenant_id=self.tenant_id, soort=soort)
            raise ApRessourceNietGevondenError(soort)
        return data

    async def get_flow(self, flow_id: str) -> dict[str, object]:
        """Een flow zoals ActivePieces hem nu heeft (met `version.trigger`); alleen de eigen."""
        return await self._eigen(f"/flows/{flow_id}", "get_flow", "Flow")

    async def get_connection(self, connection_id: str) -> dict[str, object]:
        """Een verbinding in het project van deze tenant; een vreemde of onbekende geeft 404."""
        return await self._eigen(
            f"/app-connections/{connection_id}", "get_connection", "Verbinding"
        )

    async def create_flow(
        self,
        project_id: str | None,
        flow_data: dict[str, object],
    ) -> dict[str, object]:
        """Create a new flow in ActivePieces.

        Deze client is de enige uitgang die flows naar AP schrijft of start, dus hier zit de
        stappencontrole (wfb-dag1 stap 1): een stap die iets naar buiten stuurt komt er niet in.
        Een lege flow met alleen een naam mag: zo maakt AP zelf een flow aan.
        """
        project_id = self.eigen_project(project_id)
        opdracht_zelf, huidige = beoordeel_schrijfopdracht(flow_data)
        if huidige:
            raise NietToegestaneStap("Een nieuwe flow kan niet meteen aangezet worden.")
        if opdracht_zelf:
            controleer_flowdefinitie(flow_data)
        return await self._make_request(
            method="POST",
            endpoint="/flows",
            operation_name="create_flow",
            json_data={"projectId": project_id, **flow_data},
        )

    async def update_flow(
        self,
        flow_id: str,
        flow_data: dict[str, object],
    ) -> dict[str, object]:
        """Update an existing flow.

        Een nieuwe definitie wordt gecontroleerd; publiceren of aanzetten controleert de definitie
        die AP nu heeft. Uitzetten en alleen de naam wijzigen mogen altijd; elke andere opdracht
        wordt geweigerd (`beoordeel_schrijfopdracht`).
        """
        huidige_flow = await self.get_flow(flow_id)
        opdracht_zelf, huidige = beoordeel_schrijfopdracht(flow_data)
        if opdracht_zelf:
            controleer_flowdefinitie(flow_data)
        if huidige:
            controleer_flowdefinitie(huidige_flow)
        return await self._make_request(
            method="POST",
            endpoint=f"/flows/{flow_id}",
            operation_name="update_flow",
            json_data=flow_data,
        )

    async def delete_flow(self, flow_id: str) -> bool:
        """Delete a flow -- alleen een eigen flow; een vreemde geeft 404 en wordt niet "false"."""
        await self.get_flow(flow_id)
        try:
            await self._make_request(
                method="DELETE", endpoint=f"/flows/{flow_id}", operation_name="delete_flow"
            )
            return True
        except Exception as e:
            logger.warning(
                "activepieces_delete_failed",
                flow_id=flow_id,
                tenant_id=self.tenant_id,
                host=_host(self.base_url),
                soort=type(e).__name__,
            )
            return False

    async def list_pieces(self) -> list[PieceRead]:
        """List available integration pieces."""
        data = await self._make_request(
            method="GET", endpoint="/pieces", operation_name="list_pieces"
        )
        items = cast(list[object], data if isinstance(data, list) else data.get("data", []))
        return [
            # TODO(TYPE): replace Any with concrete type
            PieceRead(**cast(dict[str, Any], item))
            for item in items
        ]  # TODO(TYPE): replace Any with concrete type

    async def get_server_version(self) -> str:
        """Versie van de ActivePieces-server, uit de vlag CURRENT_VERSION van /flags."""
        flags = await self._make_request(
            method="GET", endpoint="/flags", operation_name="get_flags"
        )
        version = flags.get("CURRENT_VERSION")
        if not isinstance(version, str) or not version:
            raise ValueError("ActivePieces /flags gaf geen CURRENT_VERSION terug")
        return version

    async def build_flow_definition(
        self, react_flow_data: dict[str, object]
    ) -> dict[str, object]:
        """Zet een React Flow-graaf om met de piece-versies en het formaat van DEZE server.

        Vanaf 0.82 pint ActivePieces piece-versies en vanaf 0.85.4 veranderen
        stapverwijzingen; zie ``transformer.py``. Beide hangen dus af van de server.
        """
        server_version = await self.get_server_version()
        piece_versions = {piece.name: piece.version for piece in await self.list_pieces()}
        return FlowTransformer.react_flow_to_activepieces(
            dict(react_flow_data),
            piece_versions=piece_versions,
            server_version=server_version,
        )

    async def trigger_flow(
        self,
        flow_id: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        """Trigger a flow execution -- alleen als de flow in AP de stappencontrole haalt."""
        controleer_flowdefinitie(await self.get_flow(flow_id))
        data = await self._make_request(
            method="POST",
            endpoint=f"/flows/{flow_id}/runs",
            operation_name="trigger_flow",
            json_data={"payload": payload},
        )
        return {
            "execution_id": data.get("id"),
            "status": data.get("status"),
            "start_time": data.get("startTime"),
            "duration": data.get("duration"),
            "project_id": data.get("projectId"),
            "flow_id": data.get("flowId"),
        }

    async def retry_run(self, run_id: str) -> dict[str, object]:
        """Een run opnieuw uitvoeren -- alleen als zijn flow de stappencontrole haalt.

        De flow komt uit de run zelf, niet uit het verzoek: anders kies je een veilige flow
        en herhaal je de run van een andere (Gate 2 HIGH-1).
        """
        run = await self.get_run_logs(run_id)
        flow_id = run.get("flowId")
        if not isinstance(flow_id, str) or not flow_id:
            raise NietToegestaneStap(
                "Deze run is niet te controleren: hij noemt geen flow. Hij wordt niet herhaald."
            )
        controleer_flowdefinitie(await self.get_flow(flow_id))
        return await self._make_request(
            method="POST", endpoint=f"/flow-runs/{run_id}/retry", operation_name="retry_run"
        )

    async def list_project_flows(self, project_id: str) -> list[dict[str, object]]:
        """List flows for a project -- alleen het project van deze tenant."""
        project_id = self.eigen_project(project_id)
        data = await self._make_request(
            method="GET",
            endpoint="/flows",
            operation_name="list_flows",
            params={"projectId": project_id},
        )
        return cast(list[dict[str, object]], data.get("data", []))

    async def list_runs(self, flow_id: str, limit: int = 10) -> list[dict[str, object]]:
        """List runs for a flow -- alleen van een eigen flow."""
        await self.get_flow(flow_id)
        data = await self._make_request(
            method="GET",
            endpoint="/flow-runs",
            operation_name="list_runs",
            params={"flowId": flow_id, "limit": limit},
        )
        return cast(list[dict[str, object]], data.get("data", []))

    async def get_run_logs(self, run_id: str) -> dict[str, object]:
        """Get logs for a specific run -- alleen van een eigen run."""
        return await self._eigen(f"/flow-runs/{run_id}", "get_run_logs", "Run")

    # =========================================================================
    # High Level Abstractions
    # =========================================================================

    async def execute_workflow(
        self,
        workflow_definition: dict[str, object],
        project_id: str | None = None,
    ) -> dict[str, object]:
        """
        Orchestrate workflow execution with resilience.

        De tenant en het project komen uit de verbinding. Een `project_id` van de aanroeper mag
        alleen het project van deze verbinding zijn: wie een ander project noemt krijgt een
        weigering (anders kiest een verzoek het bedrijf waarin de flow terechtkomt).

        Returns success even if ActivePieces is unavailable (graceful degradation).
        """
        project_id = self.eigen_project(project_id)
        tenant_id = self.tenant_id

        if not self.is_available():
            logger.warning(
                "activepieces_circuit_open_execute", tenant_id=tenant_id, fallback="local_only"
            )
            return {
                "success": False,
                "error": "Automation engine temporarily unavailable",
                "fallback": "pending_sync",
            }

        try:
            ap_flow_definition = await self.build_flow_definition(workflow_definition)

            existing_flows = await self.list_project_flows(project_id)
            flow_name = ap_flow_definition.get("displayName", "unnamed")

            existing_flow = next(
                (
                    f
                    for f in existing_flows
                    if cast(dict[str, object], f.get("version", {})).get("displayName") == flow_name
                ),
                None,
            )

            if existing_flow:
                flow = await self.update_flow(cast(str, existing_flow["id"]), ap_flow_definition)
            else:
                flow = await self.create_flow(project_id, ap_flow_definition)

            run = await self.trigger_flow(
                cast(str, flow["id"]), {"source": "sanskritisetu", "tenant_id": tenant_id}
            )

            logger.info(
                "workflow_executed",
                flow_id=flow["id"],
                run_id=run.get("execution_id"),
                tenant_id=tenant_id,
            )

            return {
                "success": True,
                "flow_id": flow["id"],
                "run_id": run.get("execution_id"),
                "status": run.get("status", "RUNNING"),
            }

        except NietToegestaneStap:
            # Geen storing maar een weigering: de aanroeper maakt er een 422 van.
            raise
        except Exception as e:
            logger.error(
                "workflow_execution_failed",
                tenant_id=tenant_id,
                host=_host(self.base_url),
                soort=type(e).__name__,
            )
            return {"success": False, "error": UITVOERFOUT}

    async def list_app_connections(self) -> list[dict[str, object]]:
        """De app-verbindingen in het project van DEZE tenant (ADR-040 B6: een toegangsweg)."""
        data = await self._make_request(
            method="GET",
            endpoint="/app-connections",
            operation_name="list_app_connections",
            params={"projectId": self.project_id},
        )
        return cast(list[dict[str, object]], data.get("data", []))

    async def health_check(self) -> dict[str, object]:
        """Check ActivePieces service health with live connectivity probe."""
        token_valid = False
        api_reachable = False

        try:
            # Attempt authentication if no valid token
            await self._get_token()
            token_valid = bool(
                self.token is not None
                and self._token_expiry is not None
                and datetime.now(timezone.utc) < self._token_expiry
            )
            api_reachable = True
        except Exception:
            token_valid = False
            api_reachable = False

        return {
            "circuit_state": self.circuit_breaker.state.value,
            "is_available": self.is_available(),
            "api_reachable": api_reachable,
            "token_valid": token_valid,
        }


async def ap_client_voor(tenant_id: int, db: AsyncSession | None = None) -> ActivePiecesClient:
    """De client van `tenant_id`, of een `ApVerbindingOntbreektError` (409) als er geen is."""
    return ActivePiecesClient(await ap_verbinding_voor(tenant_id, db))


async def get_activepieces_client(
    tenant_id: int = Depends(safe_get_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> ActivePiecesClient:
    """FastAPI-dependency: de client van de tenant uit het token, nooit een algemene."""
    return await ap_client_voor(tenant_id, db)
