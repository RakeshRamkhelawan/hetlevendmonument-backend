import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, cast

import httpx

logger = logging.getLogger("catalog_syncer")


class CatalogSyncer:
    """
    Synchronizes the tool catalog between ActivePieces and our Agentic Core.
    """

    def __init__(self, catalog_path: str = "data/tools_catalog.json") -> None:
        self.catalog_path = Path(catalog_path)
        self.catalog_path.parent.mkdir(parents=True, exist_ok=True)
        # Internal Docker URL usually, or localhost if exposed
        self.api_url = os.getenv("ACTIVEPIECES_API_URL", "http://activepieces:80/api/v1/pieces")

    async def sync_all(self) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """
        Fetches pieces from ActivePieces API and saves locally.
        Tries Live API first -> Falls back to Seed List.
        """
        logger.info("Starting tool catalog synchronization...")
        pieces: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(self.api_url)
                response.raise_for_status()
                data = cast(dict[str, Any] | list[Any], response.json())  # TODO(TYPE): replace Any with concrete type
                # Assuming standard ActivePieces response structure (list of pieces)
                # Adjust parsing logic if their API structure differs
                raw_pieces = data if isinstance(data, list) else data.get("data", [])

                logger.info(
                    f"Successfully connected to ActivePieces API. Found {len(raw_pieces)} pieces."
                )

                for p in raw_pieces:
                    # De lijst-endpoint geeft actions/triggers als AANTAL (int), niet als
                    # dict -- gemeten 2026-10-06 op 0.81.4; alleen een detailcall heeft de namen.
                    triggers = p.get("triggers")
                    actions = p.get("actions")
                    pieces.append(
                        {
                            "name": p.get("name"),
                            "displayName": p.get("displayName", p.get("name")),
                            "description": p.get("description", ""),
                            "category": "Integration",  # ActivePieces might not categorize simply
                            "triggers": list(triggers.keys()) if isinstance(triggers, dict) else [],
                            "actions": list(actions.keys()) if isinstance(actions, dict) else [],
                        }
                    )

        except Exception as e:
            logger.warning(f"Could not reach ActivePieces API ({e}). Using Seed List as fallback.")

            # --- SEED LIST (FALLBACK) ---
            pieces = [
                {
                    "name": "gmail",
                    "displayName": "Gmail",
                    "description": "Send and receive emails from your Google account.",
                    "category": "Communication",
                    "triggers": ["new_email", "new_thread"],
                    "actions": ["send_email", "create_draft"],
                },
                {
                    "name": "slack",
                    "displayName": "Slack",
                    "description": "Send messages to channels or users in your Slack workspace.",
                    "category": "Communication",
                    "triggers": ["new_message"],
                    "actions": ["send_channel_message", "send_direct_message"],
                },
                {
                    "name": "google_sheets",
                    "displayName": "Google Sheets",
                    "description": "Read and write data to your Google Sheets.",
                    "category": "Data",
                    "triggers": ["new_row"],
                    "actions": ["insert_row", "update_row", "get_cell"],
                },
                {
                    "name": "stripe",
                    "displayName": "Stripe",
                    "description": "Listen to payment events and manage customers.",
                    "category": "Finance",
                    "triggers": ["payment_succeeded", "subscription_created"],
                    "actions": ["create_customer", "refund_charge"],
                },
                {
                    "name": "github",
                    "displayName": "GitHub",
                    "description": "Manage repositories, issues and pull requests.",
                    "category": "Development",
                    "triggers": ["new_issue", "new_pr"],
                    "actions": ["create_issue", "add_comment"],
                },
                {
                    "name": "openai",
                    "displayName": "OpenAI",
                    "description": "Powerful AI models for text and image generation.",
                    "category": "AI",
                    "triggers": [],
                    "actions": ["ask_gpt", "generate_image"],
                },
            ]

        # Save to JSON
        with open(self.catalog_path, "w", encoding="utf-8") as f:
            json.dump(pieces, f, indent=2)

        logger.info(f"Sync complete. {len(pieces)} tools saved to catalog.")
        return pieces

    def load_catalog(self) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        if not self.catalog_path.exists():
            return []
        with open(self.catalog_path, encoding="utf-8") as f:
            return cast(list[dict[str, Any]], json.load(f))  # TODO(TYPE): replace Any with concrete type


# Singleton
catalog_syncer = CatalogSyncer()
