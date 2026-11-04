"""Zet Het Levend Monument klaar in een (productie)database en publiceer de demoverhalen.

Draait als Container App Job `levendmonument-publiceer` (infra/main-levendmonument-prod.bicep)
met de EIGENAAR-verbinding, omdat een nieuwe tenant nog geen tenantcontext heeft.
Idempotent: een tweede run maakt niets dubbel aan, alleen een nieuwe inloglink.

Stappen:
1. tenant `hetlevendmonument` met domein `hetlevendmonument.nl` (actief);
2. portalinstellingen (naam, contactadres);
3. een beheerder (PortalUser, rol admin) met een eenmalige inloglink, 48 uur geldig;
4. de items uit `scripts/seed/levend_monument_demo_verhalen.json` (fictieve verhalen) en
   `scripts/seed/levend_monument_lesmateriaal.json` (docentenhandleidingen PUBLIC,
   werkbladen EDU), status APPROVED, op naam van de beheerder. Elk item zegt in
   metadata.fictief expliciet of het fictie is (true/false);
5. optioneel een testklascode (rol leerling, 30 dagen geldig) als KLASCODE_EMAIL gezet is.

Bestaande items (zelfde titel) worden bijgewerkt naar het bestand: tekst, beschrijving,
categorie, zichtbaarheid, doelgroep en metadata. Het bestand is de bron voor deze items;
een wijziging in de beheeromgeving wordt bij een volgende run overschreven.

Omgeving: DATABASE_URL (eigenaar), BEHEER_EMAIL, optioneel VERHALEN_PAD, LES_PAD,
KLASCODE_EMAIL en PORTAL_URL.
De inloglink wordt geprint: het logboek van de job is daarmee gevoelig tot de link is
gebruikt of verlopen (eenmalig, 48 uur).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from src.core.models.foundation_content import (
    ContentStatus,
    ContentType,
    EducationalAccess,
    EducationalRole,
    FoundationContent,
    FoundationPortalSettings,
    MagicLinkToken,
    PortalRole,
    PortalUser,
    Privacy,
    StudyCollection,
    Visibility,
)
from src.core.models.rbac_models import Tenant
from src.core.services.edu_session_service import hash_edu_code

SLUG = "hetlevendmonument"
DOMEIN = "hetlevendmonument.nl"
NAAM = "Het Levend Monument"
CONTACT = "info@hetlevendmonument.nl"
#: In de image staat scripts/ onder /app (Dockerfile: COPY scripts/ ./scripts/). Geen
#: __file__: de job draait dit script met `python3 -c`.
STANDAARD_PAD = Path("/app/scripts/seed/levend_monument_demo_verhalen.json")
LES_STANDAARD_PAD = Path("/app/scripts/seed/levend_monument_lesmateriaal.json")
#: Zelfde alfabet als src/core/api/v1/foundation/edu.py (SAFE_EDU_ALPHABET): geen 0/O, 1/I/L.
#: Niet geimporteerd omdat die module de hele API-laag meetrekt.
_KLASCODE_ALFABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"

#: Sleutels uit het JSON-bestand die geen kolom zijn of apart worden gezet.
_NIET_KOLOM = {"slug", "metadata", "type", "privacy", "visibility", "status"}


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def _tenant(sessie: AsyncSession) -> Tenant:
    for voorwaarde in (Tenant.slug == SLUG, Tenant.domain == DOMEIN):
        bestaand = (await sessie.execute(select(Tenant).where(voorwaarde))).scalar_one_or_none()
        if bestaand is not None:
            bestaand.domain = DOMEIN
            bestaand.is_active = True
            print(f"tenant bestaat: id={bestaand.id} slug={bestaand.slug}")
            return bestaand
    naam = NAAM
    if (await sessie.execute(select(Tenant).where(Tenant.name == naam))).scalar_one_or_none():
        naam = f"Stichting {NAAM}"
    tenant = Tenant(name=naam, slug=SLUG, domain=DOMEIN, is_active=True)
    sessie.add(tenant)
    await sessie.flush()
    print(f"tenant aangemaakt: id={tenant.id} slug={SLUG} domein={DOMEIN}")
    return tenant


async def _instellingen(sessie: AsyncSession, tenant_id: int) -> None:
    bestaand = (
        await sessie.execute(
            select(FoundationPortalSettings).where(FoundationPortalSettings.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()
    if bestaand is None:
        sessie.add(
            FoundationPortalSettings(
                tenant_id=tenant_id,
                platform_name_nl=NAAM,
                platform_name_en="The Living Monument",
                contact_email=CONTACT,
            )
        )
        print("portalinstellingen aangemaakt")
    else:
        bestaand.contact_email = bestaand.contact_email or CONTACT
        print("portalinstellingen bestaan")


async def _beheerder(sessie: AsyncSession, tenant_id: int, email: str) -> PortalUser:
    nu = datetime.now(timezone.utc)
    gebruiker = (
        await sessie.execute(
            select(PortalUser).where(PortalUser.tenant_id == tenant_id, PortalUser.email == email)
        )
    ).scalar_one_or_none()
    if gebruiker is None:
        gebruiker = PortalUser(
            tenant_id=tenant_id,
            email=email,
            display_name="Beheer Het Levend Monument",
            role=PortalRole.ADMIN,
            is_verified=True,
            email_verified=True,
            consent_given=True,
            consent_given_at=nu,
        )
        sessie.add(gebruiker)
        await sessie.flush()
        print(f"beheerder aangemaakt: id={gebruiker.id}")
    else:
        gebruiker.role = PortalRole.ADMIN
        gebruiker.is_blocked = False
        print(f"beheerder bestaat: id={gebruiker.id}")
    return gebruiker


async def _inloglink(sessie: AsyncSession, tenant_id: int, gebruiker: PortalUser) -> str:
    ruw = secrets.token_urlsafe(32)
    sessie.add(
        MagicLinkToken(
            tenant_id=tenant_id,
            portal_user_id=gebruiker.id,
            token_hash=_hash_token(ruw),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=48),
            used_at=None,
        )
    )
    portal = os.getenv("PORTAL_URL", f"https://{DOMEIN}").rstrip("/")
    return f"{portal}/inloggen?token={ruw}&tenant={SLUG}"


async def _verhalen(sessie: AsyncSession, tenant_id: int, uploader_id: int, pad: Path) -> int:
    data: dict[str, Any] = json.loads(pad.read_text(encoding="utf-8"))
    nieuw = 0
    for item in data["items"]:
        if not isinstance(item.get("metadata", {}).get("fictief"), bool):
            raise ValueError(f"item {item.get('slug')} mist metadata.fictief (true of false)")
        bestaand = (
            await sessie.execute(
                select(FoundationContent).where(
                    FoundationContent.tenant_id == tenant_id,
                    FoundationContent.title_nl == item["title_nl"],
                )
            )
        ).scalar_one_or_none()
        if bestaand is not None:
            # Het bestand is de bron (zie de docstring bovenaan).
            for veld in (
                "body_nl",
                "description_nl",
                "description_en",
                "title_en",
                "category",
                "target_age_group",
            ):
                if veld in item:
                    setattr(bestaand, veld, item[veld])
            bestaand.visibility = Visibility(item["visibility"])
            bestaand.metadata_ = item["metadata"]
            print(f"bestaat al, bijgewerkt: {item['slug']} (id={bestaand.id})")
            continue
        kolommen = {k: v for k, v in item.items() if k not in _NIET_KOLOM}
        sessie.add(
            FoundationContent(
                tenant_id=tenant_id,
                uploader_id=uploader_id,
                type=ContentType(item["type"]),
                privacy=Privacy(item["privacy"]),
                visibility=Visibility(item["visibility"]),
                status=ContentStatus(item["status"]),
                metadata_=item["metadata"],
                **kolommen,
            )
        )
        nieuw += 1
        print(f"gepubliceerd: {item['slug']}")
    return nieuw


async def _testklascode(sessie: AsyncSession, tenant_id: int, email: str) -> str:
    """Een klascode voor de leerlingrol, 30 dagen geldig. De code zelf staat alleen in het logboek."""
    for _ in range(5):
        code = "".join(secrets.choice(_KLASCODE_ALFABET) for _ in range(8))
        bezet = (
            await sessie.execute(
                select(EducationalAccess.id).where(
                    EducationalAccess.code_hash == hash_edu_code(code)
                )
            )
        ).scalar_one_or_none()
        if bezet is None:
            break
    else:
        raise RuntimeError("geen unieke klascode gevonden")
    nu = datetime.now(timezone.utc)
    toegang = EducationalAccess(
        tenant_id=tenant_id,
        code_hash=hash_edu_code(code),
        email=email,
        role=EducationalRole.STUDENT,
        is_active=True,
        expires_at=nu + timedelta(days=30),
    )
    sessie.add(toegang)
    await sessie.flush()
    sessie.add(
        StudyCollection(
            tenant_id=tenant_id,
            educational_access_id=toegang.id,
            name="Testklas Het Levend Monument",
            description="Testcode voor het lesmateriaal",
        )
    )
    return code


async def main() -> None:
    email = os.environ["BEHEER_EMAIL"].strip().lower()
    pad = Path(os.getenv("VERHALEN_PAD", str(STANDAARD_PAD)))
    les_pad = Path(os.getenv("LES_PAD", str(LES_STANDAARD_PAD)))
    klascode_email = os.getenv("KLASCODE_EMAIL", "").strip().lower()
    engine = create_async_engine(os.environ["DATABASE_URL"], connect_args={"ssl": "require"})
    try:
        # expire_on_commit=False: na de commit leest de telling tenant.id; met verlopen
        # attributen zou dat een lazy load buiten greenlet_spawn zijn (MissingGreenlet).
        async with AsyncSession(engine, expire_on_commit=False) as sessie:
            tenant = await _tenant(sessie)
            await _instellingen(sessie, tenant.id)
            beheerder = await _beheerder(sessie, tenant.id, email)
            link = await _inloglink(sessie, tenant.id, beheerder)
            nieuw = await _verhalen(sessie, tenant.id, beheerder.id, pad)
            if les_pad.exists():
                nieuw += await _verhalen(sessie, tenant.id, beheerder.id, les_pad)
            else:
                print(f"geen lesmateriaal gevonden op {les_pad}")
            klascode = (
                await _testklascode(sessie, tenant.id, klascode_email) if klascode_email else None
            )
            await sessie.commit()
            totaal = (
                (
                    await sessie.execute(
                        select(FoundationContent).where(
                            FoundationContent.tenant_id == tenant.id,
                            FoundationContent.status == ContentStatus.APPROVED,
                        )
                    )
                )
                .scalars()
                .all()
            )
        print(f"nieuw: {nieuw}, goedgekeurd totaal: {len(totaal)}")
        print(f"INLOGLINK (eenmalig, 48 uur): {link}")
        if klascode:
            print(f"TESTKLASCODE (leerling, 30 dagen): {klascode}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
