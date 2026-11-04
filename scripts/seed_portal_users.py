"""Seed demo portal users and generate magic links for local development.

Usage:
    python scripts/seed_portal_users.py
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from src.core.models.foundation_content import (
    MagicLinkToken,
    PortalRole,
    PortalUser,
)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@127.0.0.1:5455/sanskritisetu",
)
PORTAL_URL = os.getenv("PORTAL_URL", "http://localhost:5174")


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def seed() -> None:
    engine = create_async_engine(DATABASE_URL)
    async with AsyncSession(engine) as session:
        # Check default tenant
        res_t = await session.execute(
            text("SELECT id FROM tenants WHERE slug = 'default'")
        )
        tenant_row = res_t.fetchone()
        if not tenant_row:
            await session.execute(
                text("INSERT INTO tenants (name, slug) VALUES ('Het Levend Monument', 'default')")
            )
            await session.commit()
            res_t = await session.execute(
                text("SELECT id FROM tenants WHERE slug = 'default'")
            )
            tenant_id = res_t.fetchone()[0]
        else:
            tenant_id = tenant_row[0]

        users_data = [
            {
                "email": "curator@levendmonument.nl",
                "display_name": "Curator Levend Monument",
                "role": PortalRole.CURATOR,
            },
            {
                "email": "admin@levendmonument.nl",
                "display_name": "Admin Levend Monument",
                "role": PortalRole.ADMIN,
            },
            {
                "email": "bezoeker@levendmonument.nl",
                "display_name": "Bezoeker Levend Monument",
                "role": PortalRole.VISITOR,
            },
        ]

        generated_links = []

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=7)

        for u in users_data:
            stmt = select(PortalUser).where(
                PortalUser.tenant_id == tenant_id,
                PortalUser.email == u["email"],
            )
            existing_user = (await session.execute(stmt)).scalar_one_or_none()

            if not existing_user:
                existing_user = PortalUser(
                    tenant_id=tenant_id,
                    email=u["email"],
                    display_name=u["display_name"],
                    role=u["role"],
                    is_verified=True,
                    email_verified=True,
                    consent_given=True,
                    consent_given_at=now,
                )
                session.add(existing_user)
                await session.flush()
            else:
                existing_user.role = u["role"]
                existing_user.is_verified = True
                existing_user.email_verified = True
                existing_user.is_blocked = False
                await session.flush()

            # Generate new valid magic link token
            raw_token = secrets.token_urlsafe(32)
            token_hash = _hash_token(raw_token)

            magic_token = MagicLinkToken(
                tenant_id=tenant_id,
                portal_user_id=existing_user.id,
                token_hash=token_hash,
                expires_at=expires_at,
                used_at=None,
            )
            session.add(magic_token)
            await session.flush()

            login_url = f"{PORTAL_URL}/inloggen?token={raw_token}&tenant=default"
            generated_links.append((u["role"].value, u["email"], login_url))

        await session.commit()

        print("\n" + "=" * 70)
        print("   HET LEVEND MONUMENT - LOKALE GEBRUIKERS EN INLOGLINKS")
        print("=" * 70)
        for role, email, link in generated_links:
            print(f"\nRol:      {role.upper()}")
            print(f"E-mail:   {email}")
            print(f"Inloglink (7 dagen geldig):")
            print(f"  {link}")
        print("\n" + "=" * 70 + "\n")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
