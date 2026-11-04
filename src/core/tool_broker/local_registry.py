from __future__ import annotations

import asyncio
import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import TYPE_CHECKING, Any, NotRequired, TypedDict, cast

import yaml

# Environment vars are loaded by the application entrypoint (src.main)
# to avoid overriding existing environment variables.

logger = logging.getLogger("local_tool_registry")


class ToolWhitelist(TypedDict):
    """Vorm van `tool_whitelist.yaml`. `allowed_commands` bestaat niet meer sinds
    `local__run_shell` is verwijderd (ADR-036 OP-126) -- er is geen shell-uitvoering
    meer om een commandolijst voor te hebben."""

    allowed_paths: list[str]
    max_read_size: NotRequired[int]


class LocalToolRegistry:
    """Registry for local tools: whitelisted file reads (ADR-036 OP-126: no shell/
    subprocess execution surface), outbound email, and LLM generation.

    ADR-036 OP-216: this registry does not sandbox anything and does not need to --
    `local__run_shell` (the only code-execution tool) was removed in OP-126. Security
    for the remaining tools comes from `_is_path_allowed`'s whitelist check, not from
    process isolation.
    """

    def __init__(self, config_path: str = "src/core/config/tool_whitelist.yaml") -> None:
        self.config_path = config_path
        self.whitelist = self._load_whitelist()

    def _load_whitelist(self) -> ToolWhitelist:
        try:
            with open(self.config_path, encoding="utf-8") as f:
                loaded = yaml.safe_load(f)
                if isinstance(loaded, dict):
                    return cast(ToolWhitelist, loaded)
                return {"allowed_paths": []}
        except Exception as e:
            logger.error(f"Failed to load tool whitelist: {e}")
            return {"allowed_paths": []}

    #: De uitvoerbare lokale en test-tools, expliciet -- zoals `BusinessToolRegistry._TOOL_NAMES`
    #: en `HRToolRegistry._TOOL_NAMES`. Expliciet en niet afgeleid uit de methodenaamruimte, want
    #: `execute_local_tool` hieronder mangelt de naam en dat is niet eenduidig terug te rekenen:
    #: `_tool_read_file` kan uit `local__read_file` of uit `read__file` komen.
    #:
    #: Deze verzameling bestond niet, en dat had gevolgen: de architectuur-guard van ADR-036
    #: OP-27 uniet `BusinessToolRegistry.known_tool_names() | HRToolRegistry.known_tool_names()`,
    #: dus deze zeven tools hadden NUL dekking. Drie van de zes afwijkingen in
    #: `redaction.PAYLOAD_POLICY` zaten precies hier (`seconds` i.p.v. `delay_seconds`, en
    #: fantoomnamen voor `test__echo` en `local__llm_generate`).
    #:
    #: `tests/architecture/test_tool_policy_matches_the_tools.py` toetst deze verzameling in
    #: BEIDE richtingen tegen de `_tool_*`-methodes: elke naam moet dispatchen, en elke methode
    #: moet door een naam gedekt zijn.
    _TOOL_NAMES: frozenset[str] = frozenset(
        {
            "local__read_file",
            "local__send_email",
            "local__llm_generate",
            "test__echo",
            "test__fail",
            "test__slow",
        }
    )

    @classmethod
    def known_tool_names(cls) -> set[str]:
        """De toolnamen die deze registry afhandelt."""
        return set(cls._TOOL_NAMES)

    async def execute_local_tool(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Routes the tool call to the correct local implementation.
        """
        name = tool_name
        if name.startswith("local__"):
            name = name.replace("local__", "", 1)
        name = name.replace("__", "_")
        method_name = f"_tool_{name}"
        if hasattr(self, method_name):
            method = cast(Any, getattr(self, method_name))  # TODO(TYPE): replace Any with concrete type
            result = await method(params)
            return cast(dict[str, Any], result)  # TODO(TYPE): replace Any with concrete type
        else:
            raise ValueError(f"Local tool '{tool_name}' not implemented.")

    async def _tool_test_echo(self, params: dict[str, Any]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        from src.core.tool_broker.test_tools import test_echo

        return await test_echo(params)

    async def _tool_test_fail(self, params: dict[str, Any]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        from src.core.tool_broker.test_tools import test_fail

        return await test_fail(params)

    async def _tool_test_slow(self, params: dict[str, Any]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        from src.core.tool_broker.test_tools import test_slow

        return await test_slow(params)

    async def _tool_read_file(self, params: dict[str, Any]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        file_path = params.get("path")
        if not file_path:
            raise ValueError("Parameter 'path' is required for read_file.")

        if not self._is_path_allowed(file_path):
            logger.warning(f"Blocked attempt to read unauthorized path: {file_path}")
            return {"success": False, "error": "Access Denied: Path not whitelisted."}

        try:
            full_path = Path(file_path)
            if not full_path.exists():
                return {"success": False, "error": "File not found."}

            if full_path.stat().st_size > self.whitelist.get("max_read_size", 1048576):
                return {"success": False, "error": "File too large."}

            content = full_path.read_text(encoding="utf-8")
            return {"success": True, "content": content}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # --- REAL WORLD CONNECTORS ---

    async def _tool_send_email(self, params: dict[str, Any]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Sends an email via SMTP (Gmail/Outlook).
        Requires SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD in .env
        """
        to_email: str | None = params.get("to")
        subject: str | None = params.get("subject")
        body: str | None = params.get("body")

        if not all([to_email, subject, body]):
            return {
                "success": False,
                "error": "Missing parameters: 'to', 'subject', or 'body'.",
            }

        # Type narrowing after validation
        if to_email is None or subject is None or body is None:
            return {
                "success": False,
                "error": "Missing parameters: 'to', 'subject', or 'body'.",
            }

        # Security: Basic check to prevent spamming entire world if needed
        # (Could add domain whitelist here)

        try:
            smtp_host = os.getenv("SMTP_HOST")
            smtp_port_str = os.getenv("SMTP_PORT", "587")
            smtp_user = os.getenv("SMTP_USER")
            smtp_password = os.getenv("SMTP_PASSWORD")

            if not all([smtp_host, smtp_user, smtp_password]):
                return {"success": False, "error": "SMTP configuration missing in .env"}

            # Type narrowing after validation
            if smtp_host is None or smtp_user is None or smtp_password is None:
                return {"success": False, "error": "SMTP configuration missing in .env"}

            smtp_port: int = int(smtp_port_str)

            # Create Message
            msg = MIMEMultipart()
            msg["From"] = smtp_user
            msg["To"] = to_email
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain"))

            # Send Async (wrapped in thread)
            def send_sync() -> None:
                with smtplib.SMTP(smtp_host, smtp_port) as server:
                    server.starttls()
                    server.login(smtp_user, smtp_password)
                    server.send_message(msg)

            await asyncio.to_thread(send_sync)

            logger.info(f"Email sent successfully to {to_email}")
            return {"success": True, "message": "Email sent."}

        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return {"success": False, "error": str(e)}

    async def _tool_llm_generate(self, params: dict[str, Any]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Genereert tekst met het taalmodel van de TENANT van dit verzoek (brief 2026-10-20, ADR-041 B14).

        Hier stond het platformmodel uit `LLM_PROVIDER` (met `ollama` als standaard) voor elke klant. De tenant
        komt uit de verzoekcontext, nooit uit `params`. Zonder tenantcontext is het een fout.
        """
        prompt = params.get("prompt")
        if not prompt:
            return {"success": False, "error": "Missing 'prompt' parameter."}

        import importlib

        from src.core.middleware.tenant_context import require_tenant_id

        # Dynamisch (zoals `service.py`): `tool_broker` is een LAGERE laag dan `services` (agent_runtime); een
        # statische import telt als backward import in `test_dsm014_agt_rt_no_laag_circulars`.
        tenant_deur = importlib.import_module("src.core.services.llm.tenant_deur")

        try:
            tenant_id = require_tenant_id()
        except Exception as exc:
            logger.error("LLM generate zonder tenantcontext: %s", type(exc).__name__, exc_info=True)
            return {"success": False, "error": "no tenant context"}

        antwoord = await tenant_deur.TenantTaalmodel(tenant_id).generate_response(str(prompt))
        if not antwoord.get("success"):
            return {"success": False, "error": str(antwoord.get("error", "LLM generation failed"))}
        return {"success": True, "content": antwoord.get("content", "")}

    # --- HELPERS ---
    def _is_path_allowed(self, path: str) -> bool:
        """Valt dit pad ONDER een toegestane map? (ADR-036 OP-126)

        Hier stond `abs_path.startswith(abs_allowed)`. Dat is een stringvergelijking en kent geen
        mapgrenzen: met de allowlist-regel `src/core` passeerde ook `src/core_secrets`, want die
        naam begint er nu eenmaal mee. `Path.is_relative_to` toetst de grens wel.
        """
        kandidaat = Path(path).resolve()
        for allowed in self.whitelist.get("allowed_paths", []):
            try:
                if kandidaat.is_relative_to(Path(allowed).resolve()):
                    return True
            except (OSError, ValueError):
                # Een onleesbaar of ongeldig allowlist-pad mag nooit als treffer tellen.
                continue
        return False
