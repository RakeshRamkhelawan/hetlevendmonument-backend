"""De escalatietermijn van debiteuren, per klant (debiteuren vanzelf afronden, 2026-10-20).

Besluit Rakesh 2026-10-20: "laat klant zijn eigen escalatietermijn kiezen". Na zoveel dagen zonder betaling (gerekend
vanaf `herinnerd_op`, de dag van de verzonden brief) escaleert de dagelijkse opvolging een dossier.

**Waarom `tenants.settings` en geen kolom.** Zoals de vier-ogen-keuze (`governance/four_eyes.py`): de JSON-kolom bestaat
al en een kolom vraagt een migratie. De sleutel is `escalatie_na_dagen`, een geheel getal van 1 tot en met 120;
standaard 14. Een ontbrekende of onmogelijke waarde (tekst, 0, 121, een float, een bool) is geen fout bij het LEZEN:
dan geldt de standaard, zodat de dagelijkse opvolging nooit stilvalt op een kapotte instelling. Bij het SCHRIJVEN
wordt een onmogelijke waarde juist geweigerd.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

#: De sleutel in `tenants.settings`.
ESCALATIE_SETTINGS_KEY = "escalatie_na_dagen"

STANDAARD_ESCALATIE_NA_DAGEN = 14
MIN_ESCALATIE_NA_DAGEN = 1
MAX_ESCALATIE_NA_DAGEN = 120


def _is_toegestaan(waarde: object) -> bool:
    """Een geheel getal van 1 tot en met 120; een bool is geen getal in dit verband."""
    return (
        isinstance(waarde, int)
        and not isinstance(waarde, bool)
        and MIN_ESCALATIE_NA_DAGEN <= waarde <= MAX_ESCALATIE_NA_DAGEN
    )


def escalatie_na_dagen_uit_settings(settings: object) -> int:
    """De termijn uit `tenants.settings`; de standaard als hij ontbreekt of niet klopt."""
    if not isinstance(settings, dict):
        return STANDAARD_ESCALATIE_NA_DAGEN
    waarde = settings.get(ESCALATIE_SETTINGS_KEY)
    if isinstance(waarde, int) and _is_toegestaan(waarde):
        return waarde
    return STANDAARD_ESCALATIE_NA_DAGEN


async def lees_escalatie_na_dagen(db: AsyncSession, *, tenant_id: int) -> int:
    """De termijn van DEZE tenant (de standaard voor een onbekende tenant)."""
    from src.core.models.rbac_models import Tenant

    settings = (
        await db.execute(select(Tenant.settings).where(Tenant.id == tenant_id))
    ).scalar_one_or_none()
    return escalatie_na_dagen_uit_settings(settings)


async def schrijf_escalatie_na_dagen(
    db: AsyncSession, *, tenant_id: int, dagen: int
) -> tuple[int, int]:
    """Zet de termijn van DEZE tenant. Geeft (oud, nieuw).

    `ValueError` bij een onmogelijke waarde, `LookupError` bij een onbekende tenant. De rest van `settings` blijft
    staan. Commit zelf. Een nieuw dict toewijzen en niet in-place wijzigen: een JSON-kolom ziet een mutatie binnen het
    object niet als wijziging.
    """
    from src.core.models.rbac_models import Tenant

    if not _is_toegestaan(dagen):
        raise ValueError(
            f"de termijn moet een geheel getal van {MIN_ESCALATIE_NA_DAGEN} tot en met "
            f"{MAX_ESCALATIE_NA_DAGEN} dagen zijn"
        )
    # Met rijslot: een gelijktijdige wijziging van een andere sleutel in `settings` (bijvoorbeeld vier ogen door een
    # andere beheerder) gaat anders verloren, want de hele JSON wordt teruggeschreven (Gate 2).
    tenant = (
        await db.execute(
            select(Tenant)
            .where(Tenant.id == tenant_id)
            .with_for_update()
            # Ververs een rij die de sessie al kent, anders overschrijf je de wijziging van een ander met een oude kopie.
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if tenant is None:
        raise LookupError("tenant bestaat niet")
    huidig = tenant.settings if isinstance(tenant.settings, dict) else {}
    oud = escalatie_na_dagen_uit_settings(huidig)
    tenant.settings = {**huidig, ESCALATIE_SETTINGS_KEY: dagen}
    await db.commit()
    return oud, dagen
