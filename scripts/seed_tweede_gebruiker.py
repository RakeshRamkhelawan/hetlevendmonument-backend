"""Seed een tweede gebruiker ZONDER beheerdersrol, om rolgrenzen mee te testen (Keten B nazorg, G).

Er was alleen een beheerder (`E2E_ADMIN`); zonder tweede gebruiker is "een gewone medewerker
krijgt 403 op /audit-logs en /api/v1/system/*" niet te beproeven. Dit script maakt in de BESTAANDE
dev-tenant (de tenant van de beheerder) een gebruiker met PRECIES de rol `user` en
`is_superuser=False`. De centrale definitie `is_admin` noemt die gebruiker dus geen beheerder.

**Leesrecht.** `require_permission(Permission.READ)` (o.a. `GET /api/v1/receivables`) vraagt
via `RBACService.has_permission(user_id, "*", "read")` om een `role_permissions`-rij met
resource `*` (of `*`) en actie `read` (of `*`). De standaard zaailijst van de rol `user`
(`ensure_default_roles`: `agents:read` en `workflows:read`) heeft die niet; daarom krijgt de rol
`user` in deze tenant hier ook `*:read`. Dat is een LEESrecht en geen schrijfrecht. Gemeten door
`require_permission` zelf aan te roepen, zie de tests.

**Weigert in production en staging.** Er wordt gekeken naar `APP_ENV` EN `ENVIRONMENT` (de
applicatieconfiguratie leest `ENVIRONMENT`, `.env.example` kent `APP_ENV`); een van beide
op production/staging is genoeg om te weigeren. De controle komt VOOR elke databasetoegang.

Inloggegevens komen uit `E2E_MEDEWERKER_EMAIL` / `E2E_MEDEWERKER_PASSWORD`, met dezelfde
dev-standaard als `E2E_MEDEWERKER` in `tests/e2e/helpers/credentials.ts`.

**Rol debiteuren.** Met `--rol debiteuren` krijgt de gebruiker in plaats daarvan PRECIES de rol
`debiteuren` (`receivables:read`, `receivables:write`, `receivables:propose` en `tools:read`, rolmodel optie A): hij mag debiteuren
toevoegen, op betaald zetten en een herinnering voorstellen, maar geen HITL-ticket goedkeuren.
Standaard e-mailadres dan `E2E_DEBITEUREN_EMAIL` of `debiteuren@sanskritisetu.org`.

**Rol goedkeurder.** Met `--rol goedkeurder` PRECIES `receivables:read`, `receivables:approve` en
`tools:read` (ADR-039); standaard e-mailadres `E2E_GOEDKEURDER_EMAIL` of
`goedkeurder@sanskritisetu.org`.

Gebruik (lokaal):  python scripts/seed_tweede_gebruiker.py [--rol debiteuren|crediteuren|goedkeurder|goedkeurder_hr]
Idempotent: een herhaling maakt geen tweede gebruiker.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections.abc import Mapping
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from passlib.context import CryptContext  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from src.core.models.rbac_models import Role, RolePermission, User, user_roles  # noqa: E402

#: Dezelfde dev-standaard als `E2E_MEDEWERKER` in tests/e2e/helpers/credentials.ts. Het
#: wachtwoord van de lokale ontwikkeldatabase, geen productiegeheim.
DEV_EMAIL = "medewerker@sanskritisetu.org"
DEV_PASSWORD = "MedewerkerPass123!"  # noqa: S105 - lokale dev-seed
ROL_NAAM = "user"
DEBITEUREN_EMAIL = "debiteuren@sanskritisetu.org"
GOEDKEURDER_EMAIL = "goedkeurder@sanskritisetu.org"
GOEDKEURDER_HR_EMAIL = "goedkeurder-hr@sanskritisetu.org"
CREDITEUREN_EMAIL = "crediteuren@sanskritisetu.org"
#: Per seedbare rol: beschrijving en PRECIES deze rechten. `debiteuren` is gelijk aan de rij in
#: `RBACService.ensure_default_roles`; `user` krijgt hier extra `*:read` (zie de moduledocstring).
ROLLEN: dict[str, tuple[str, tuple[tuple[str, str], ...]]] = {
    "user": ("Default user", (("*", "read"),)),
    "debiteuren": (
        "Debiteurenadministrateur",
        (
            ("receivables", "read"),
            ("receivables", "write"),
            ("receivables", "propose"),
            # Leestools via een agent (OP-143): gelijk aan de zaailijst in `ensure_default_roles`.
            ("tools", "read"),
        ),
    ),
    # Crediteuren dag 1 (2026-10-24): gelijk aan de rij in `RBACService.ensure_default_roles`; geen `tools:read`.
    "crediteuren": (
        "Crediteurenadministrateur",
        (
            ("payables", "read"),
            ("payables", "write"),
        ),
    ),
    # ADR-039 (2026-10-09): goedkeuren is een procesbevoegdheid. Gelijk aan de rij in
    # `RBACService.ensure_default_roles`; de beheerder heeft dit recht NIET vanzelf.
    "goedkeurder": (
        "Goedkeurder debiteuren en crediteuren",
        (
            ("receivables", "read"),
            ("receivables", "approve"),
            ("payables", "read"),
            ("payables", "approve"),
            ("governance", "approve"),
            ("tools", "read"),
        ),
    ),
    "goedkeurder_hr": (
        "Goedkeurder personeel",
        (
            ("hr", "approve"),
            ("tools", "read"),
        ),
    ),
}
GEWEIGERDE_OMGEVINGEN = frozenset({"production", "staging"})

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class OmgevingGeweigerd(RuntimeError):
    """Het script draait niet in production of staging."""


def controleer_omgeving(env: Mapping[str, str]) -> None:
    """Gooit OmgevingGeweigerd als APP_ENV of ENVIRONMENT production/staging is."""
    for variabele in ("APP_ENV", "ENVIRONMENT"):
        waarde = env.get(variabele, "").strip().lower()
        if waarde in GEWEIGERDE_OMGEVINGEN:
            raise OmgevingGeweigerd(
                f"{variabele}={waarde}: dit script maakt een testgebruiker en draait alleen lokaal"
            )


async def _zorg_voor_rol(session: AsyncSession, tenant_id: int, rol_naam: str) -> Role:
    beschrijving, rechten = ROLLEN[rol_naam]
    rol = (
        await session.execute(select(Role).where(Role.name == rol_naam, Role.tenant_id == tenant_id))
    ).scalar_one_or_none()
    if rol is None:
        rol = Role(tenant_id=tenant_id, name=rol_naam, description=beschrijving, is_active=True)
        session.add(rol)
        await session.flush()
    for resource, action in rechten:
        aanwezig = (
            await session.execute(
                select(RolePermission.id).where(
                    RolePermission.role_id == rol.id,
                    RolePermission.resource == resource,
                    RolePermission.action == action,
                )
            )
        ).first()
        if aanwezig is None:
            session.add(
                RolePermission(
                    role_id=rol.id, tenant_id=tenant_id, resource=resource, action=action
                )
            )
            await session.flush()
    return rol


async def maak_tweede_gebruiker(
    session: AsyncSession,
    *,
    tenant_id: int,
    email: str,
    password: str,
    rol_naam: str = ROL_NAAM,
) -> int:
    """Maakt (of hergebruikt) de gebruiker met alleen de rol `rol_naam`; geeft het user-id terug."""
    if rol_naam not in ROLLEN:
        raise ValueError(f"Onbekende rol {rol_naam!r}; kies uit {sorted(ROLLEN)}")
    rol = await _zorg_voor_rol(session, tenant_id, rol_naam)
    hash_ = _pwd_context.hash(password[:72])

    gebruiker = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if gebruiker is None:
        gebruiker = User(
            email=email,
            hashed_password=hash_,
            tenant_id=tenant_id,
            is_active=True,
            is_superuser=False,
        )
        session.add(gebruiker)
        await session.flush()
    elif gebruiker.tenant_id != tenant_id:
        raise RuntimeError(f"{email} bestaat al in een andere tenant ({gebruiker.tenant_id})")
    else:
        gebruiker.hashed_password = hash_
        gebruiker.is_superuser = False

    gekoppeld = (
        await session.execute(
            select(user_roles.c.role_id).where(
                user_roles.c.user_id == gebruiker.id, user_roles.c.role_id == rol.id
            )
        )
    ).first()
    if gekoppeld is None:
        await session.execute(user_roles.insert().values(user_id=gebruiker.id, role_id=rol.id))
    await session.commit()
    return int(gebruiker.id)


def _async_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    return url


async def _seed(env: Mapping[str, str], rol_naam: str = ROL_NAAM) -> int:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from src.core.database.bypass_session import adopt_tenant

    url = env.get("DATABASE_URL", "")
    if not url:
        print("DATABASE_URL ontbreekt.", file=sys.stderr)
        return 1
    beheerder = env.get("E2E_ADMIN_EMAIL") or env.get("DEFAULT_ADMIN_EMAIL") or "admin@sanskritisetu.org"
    if rol_naam == "debiteuren":
        email = env.get("E2E_DEBITEUREN_EMAIL") or DEBITEUREN_EMAIL
    elif rol_naam == "crediteuren":
        email = env.get("E2E_CREDITEUREN_EMAIL") or CREDITEUREN_EMAIL
    elif rol_naam == "goedkeurder":
        email = env.get("E2E_GOEDKEURDER_EMAIL") or GOEDKEURDER_EMAIL
    elif rol_naam == "goedkeurder_hr":
        email = env.get("E2E_GOEDKEURDER_HR_EMAIL") or GOEDKEURDER_HR_EMAIL
    else:
        email = env.get("E2E_MEDEWERKER_EMAIL") or DEV_EMAIL
    password = env.get("E2E_MEDEWERKER_PASSWORD") or DEV_PASSWORD

    engine = create_async_engine(_async_url(url))
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            # De dev-tenant is de tenant van de beheerder; het tenant-id komt uit de database.
            tenant_id = (
                await session.execute(select(User.tenant_id).where(User.email == beheerder))
            ).scalar_one_or_none()
            if tenant_id is None:
                print(f"Beheerder {beheerder} niet gevonden: draai eerst de seed.", file=sys.stderr)
                return 1
            async with adopt_tenant(session, int(tenant_id)):
                user_id = await maak_tweede_gebruiker(
                    session,
                    tenant_id=int(tenant_id),
                    email=email,
                    password=password,
                    rol_naam=rol_naam,
                )
        print(f"Gebruiker {email} (id {user_id}) met rol {rol_naam} in tenant {tenant_id}.")
        return 0
    finally:
        await engine.dispose()


def main(env: Mapping[str, str] | None = None, argv: list[str] | None = None) -> int:
    omgeving: Mapping[str, str] = os.environ if env is None else env
    try:
        controleer_omgeving(omgeving)
    except OmgevingGeweigerd as exc:
        print(f"Geweigerd: {exc}", file=sys.stderr)
        return 1
    parser = argparse.ArgumentParser(description="Seed een tweede gebruiker zonder beheerdersrol.")
    parser.add_argument("--rol", choices=sorted(ROLLEN), default=ROL_NAAM)
    args = parser.parse_args([] if argv is None else argv)
    return asyncio.run(_seed(omgeving, args.rol))


if __name__ == "__main__":
    sys.exit(main(argv=sys.argv[1:]))
