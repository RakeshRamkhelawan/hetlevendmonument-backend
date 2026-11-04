"""
seed_agent_registry - Idempotent seeding of RegisteredAgent table from agent_registry.json.

Usage as module:
    from src.core.agents.seed_agent_registry import load_agent_registry_json, seed_agent_registry

Usage as CLI:
    python -m src.core.agents.seed_agent_registry [--tenant-id N] [--clear-existing]
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

# Via de adapter en niet rechtstreeks: ADR-034 verbiedt `src.core.agents` om
# `src.core.database` te importeren. Zie `adapters/tenant_context.py`.
from src.core.agents.adapters.tenant_context import adopt_tenant

logger = logging.getLogger(__name__)

# Absolute path to the JSON file co-located with this module
_REGISTRY_JSON_PATH = Path(__file__).parent / "agent_registry.json"


def load_agent_registry_json() -> list[
    dict[str, Any]  # TODO(TYPE): replace Any with concrete type
]:  # TODO(TYPE): replace Any with concrete type
    """
    Load and parse agent_registry.json from the same directory as this module.

    Returns:
        List of agent dicts from the 'agents' array.

    Raises:
        FileNotFoundError: If agent_registry.json does not exist at the expected path.
        ValueError: If the JSON is malformed or missing the 'agents' key.
    """
    path = _REGISTRY_JSON_PATH
    if not path.exists():
        raise FileNotFoundError("agent_registry.json not found at expected path: %s" % str(path))

    try:
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Failed to parse agent_registry.json at {}: {}".format(str(path), exc)
        ) from exc

    if "agents" not in data:
        raise ValueError(
            "agent_registry.json does not contain an 'agents' key (path: %s)" % str(path)
        )

    agents = data["agents"]
    if not isinstance(agents, list):
        raise ValueError(
            "'agents' in agent_registry.json must be a list, got %s" % type(agents).__name__
        )

    logger.debug("Loaded %s agents from %s", len(agents), str(path))
    return agents


async def seed_agent_registry(
    session: AsyncSession,
    agents: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
    tenant_id: int,
    clear_existing: bool = False,
) -> dict[str, int]:
    """
    Seed the registered_agents table with the provided agent list.

    Idempotent: agents that already exist (by agent_id + tenant_id) are skipped.

    Args:
        session:        SQLAlchemy AsyncSession (caller owns lifecycle).
        agents:         List of agent dicts as returned by load_agent_registry_json().
        tenant_id:      Tenant to seed agents for.
        clear_existing: If True, DELETE all existing agents for this tenant first.

    Returns:
        Dict with keys 'inserted', 'skipped', 'total'.

    Raises:
        Exception: On database error after rollback.
    """
    # Import here to avoid circular imports at module load time
    from src.core.agents.models import RegisteredAgent

    inserted = 0
    skipped = 0

    # De klant wordt AANGENOMEN en niet alleen doorgegeven (ADR-036 OP-153).
    #
    # Dit script draait met de hand (`python -m src.core.agents.seed_agent_registry`),
    # buiten elk verzoek, dus de ContextVar is leeg. `registered_agents` heeft een
    # afschermingsregel en die leest de klant uit `app.current_tenant`.
    #
    # De INSERT verderop zou zich na de omschakeling naar `sanskritisetu_app` met een
    # foutmelding melden, maar de DELETE hieronder NIET: gemeten 2026-09-15 raakt een
    # DELETE zonder klantcontext nul rijen en slaagt ZONDER fout. `--clear-existing`
    # zou dus stil niets opruimen.
    async with adopt_tenant(session, tenant_id):
        try:
            if clear_existing:
                logger.info("Clearing existing registered agents for tenant_id=%s", tenant_id)
                await session.execute(
                    delete(RegisteredAgent).where(RegisteredAgent.tenant_id == tenant_id)
                )
                logger.debug("Deleted existing agents for tenant_id=%s", tenant_id)

            now = datetime.now(timezone.utc)

            for agent_dict in agents:
                agent_id = agent_dict.get("agent_id", "")
                name = agent_dict.get("name", "")
                description = agent_dict.get("description", "")

                if not agent_id:
                    logger.warning("Skipping agent with missing agent_id: %s", agent_dict)
                    skipped += 1
                    continue

                # Build JSONB capabilities from JSON fields
                capabilities: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
                    "department": agent_dict.get("department", "OPERATIONS"),
                    "agent_type": agent_dict.get("agent_type", "SPECIALIST"),
                    "specialization": agent_dict.get("specialization", "general"),
                    "functions": agent_dict.get("functions", []),
                    "is_service": agent_dict.get("is_service", False),
                }

                # Check idempotency: skip if already exists for this tenant
                result = await session.execute(
                    select(RegisteredAgent).where(
                        RegisteredAgent.agent_id == agent_id,
                        RegisteredAgent.tenant_id == tenant_id,
                    )
                )
                existing = result.scalar_one_or_none()

                if existing is not None:
                    logger.debug(
                        "Skipping existing agent agent_id=%s tenant_id=%s",
                        agent_id,
                        tenant_id,
                    )
                    skipped += 1
                    continue

                # Insert new agent row
                new_agent = RegisteredAgent(
                    agent_id=agent_id,
                    name=name,
                    description=description,
                    address="",  # Network address not used in this model
                    capabilities=capabilities,
                    last_heartbeat=now,
                    tenant_id=tenant_id,
                )
                session.add(new_agent)
                logger.debug(
                    "Inserting agent agent_id=%s tenant_id=%s",
                    agent_id,
                    tenant_id,
                )
                inserted += 1

            await session.commit()
            logger.info(
                "Seeding complete for tenant_id=%s: inserted=%s skipped=%s total=%s",
                tenant_id,
                inserted,
                skipped,
                inserted + skipped,
            )

        except Exception as exc:
            logger.error(
                "seed_agent_registry failed for tenant_id=%s: %s: %s",
                tenant_id,
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            await session.rollback()
            raise

        return {"inserted": inserted, "skipped": skipped, "total": inserted + skipped}


if __name__ == "__main__":
    import argparse
    import asyncio

    # NOTE: ADR-034 Cat B Stap 3D -- startup-seeder, lokale import voor CLI-entrypoint.
    # import-linter Contract 7 ignore_imports gedocumenteerd. Backlog: SP-AGT-005.
    from src.core.database.database import initialize_database
    from src.core.database.session import get_db_session

    async def main() -> None:
        parser = argparse.ArgumentParser(description="Seed agent registry")
        parser.add_argument(
            "--tenant-id",
            type=int,
            default=1,
            help="Tenant ID to seed agents for (default: 1)",
        )
        parser.add_argument(
            "--clear-existing",
            action="store_true",
            help="Delete existing agents for the tenant before seeding",
        )
        args = parser.parse_args()

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )

        agents = load_agent_registry_json()
        logger.info("Loaded %s agents from registry JSON", len(agents))

        await initialize_database()

        async with get_db_session() as session:
            result = await seed_agent_registry(session, agents, args.tenant_id, args.clear_existing)

        print("Seeding complete: %s" % result)

    asyncio.run(main())
