"""Een composite foreign key vereist een unique constraint op het DOEL (ADR-036 OP-155).

`20260529b_harden_user_persona_preferences_tenant_integrity.py` maakt twee samengestelde
foreign keys die de tenant-integriteit van `user_persona_preferences` afdwingen:

    fk_user_persona_preferences_user_tenant     -> users(id, tenant_id)      (regel 58-65)
    fk_user_persona_preferences_persona_tenant  -> personas(id, tenant_id)   (regel 66-73)

PostgreSQL staat zo'n FK alleen toe als er op het doel een UNIQUE constraint over precies
die kolommen ligt. De migratie maakt die dan ook aan: `uq_users_id_tenant` (regel 25).

**Het model van `users` heeft hem niet.** `src/core/models/rbac_models.py:335-338` bevat
alleen twee `Index`-regels. Het zusje `personas` heeft de zijne wel
(`src/core/models/persona_models.py:40`), dus dit is aantoonbaar een omissie en geen keuze.

Gevolg: op elke route die het schema met `Base.metadata.create_all` bouwt -- en dat is elke
unittest -- ontbreekt de constraint EN daarmee de FK die erop steunt. Precies de
bescherming die die migratie moest opleveren is in de hele testomgeving afwezig, en geen
enkele test kan dat betrappen omdat de constraint daar niet bestaat.

Deze guard toetst het MODEL, niet de migratie: de migratie is aantoonbaar in orde.

**Mutatiebewijs (2026-08-17), een regel per bewaakt element en in beide richtingen:**
- `uq_users_id_tenant` uit `rbac_models.py` gehaald -> `test_users_carries_the_composite_
  unique_constraint` ROOD. (Dat is de toestand van voor deze fix.)
- `uq_personas_id_tenant` uit `persona_models.py` gehaald -> `test_personas_carries_the_
  composite_unique_constraint` ROOD.
- De kolomvolgorde omgedraaid naar `(tenant_id, id)` -> ROOD. PostgreSQL matcht een FK op
  de kolomVERZAMELING, maar een guard die alleen op de naam let zou dit missen; deze test
  vergelijkt de kolommen.
- Een `Index(..., unique=True)` in plaats van een `UniqueConstraint` -> ROOD. Dat is de
  tegenrichting die er toe doet: een unieke index is voor PostgreSQL WEL een geldig
  FK-doel, maar SQLAlchemy genereert er geen constraint voor bij `create_all`, en dan
  ontbreekt de FK alsnog. Precies de val waar `user_cognitive_profiles` en
  `user_twin_consent` vandaag in zitten.
- Ongewijzigd -> GROEN.
"""

from __future__ import annotations

import pytest

from tests.architecture._unique_constraints import unieke_kolomverzamelingen

# Doel -> de kolommen waarop een samengestelde FK uit de keten verwijst.
# Expliciet benoemd: een guard over een genoemde verzameling is in vijf seconden te
# controleren, en het mutatiebewijs heeft daarmee een regel per element.
_FK_DOELEN: dict[str, tuple[str, ...]] = {
    "users": ("id", "tenant_id"),
    "personas": ("id", "tenant_id"),
}


@pytest.mark.parametrize("tabel,kolommen", sorted(_FK_DOELEN.items()))
def test_the_composite_fk_target_has_a_unique_constraint(
    tabel: str, kolommen: tuple[str, ...]
) -> None:
    """Het doel van een samengestelde FK draagt de bijbehorende UniqueConstraint."""
    gevonden = unieke_kolomverzamelingen(tabel)
    verwacht = frozenset(kolommen)

    assert verwacht in gevonden, (
        f"Het model van `{tabel}` heeft geen UniqueConstraint over {sorted(kolommen)}.\n"
        f"Gevonden constraints: {[sorted(g) for g in gevonden] or 'geen'}\n\n"
        "De migratieketen maakt die constraint wel aan, en er hangt een samengestelde "
        "foreign key aan die zonder dat doel niet kan bestaan. Op elke route die het schema "
        "met `Base.metadata.create_all` bouwt -- dus elke unittest -- ontbreekt daarmee de "
        "tenant-integriteit die de migratie moest opleveren."
    )


def test_the_guard_is_not_vacuous() -> None:
    """Een lege verzameling maakt de test hierboven trivially groen."""
    assert _FK_DOELEN, "geen FK-doelen benoemd"
    for tabel in _FK_DOELEN:
        assert unieke_kolomverzamelingen(tabel) is not None, f"{tabel} niet gevonden"
