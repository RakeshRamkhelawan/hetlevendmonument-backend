"""Een constraint die de migratie aanmaakt moet ook in het MODEL staan (ADR-036 OP-160).

`user_consents` en `contact_opt_outs` zijn twee van de drie oorspronkelijk gemelde gevallen
van OP-160: de migratie maakte de UNIQUE constraint bij tabelcreatie
(`20260404_gdpr_tables.py:58`, `b2c3d4e5f6a7_add_notifications_inbound_tables_tenant_hardening.py:107-108`),
maar het model kende hem niet. Verschil met het `users`/`personas`-paar in
`test_composite_fk_targets_exist_in_the_models.py`: hier hangt er geen samengestelde
foreign key aan (geverifieerd: geen enkele migratie bevat een `ForeignKeyConstraint` die naar
deze twee tabellen wijst) -- de schade is dat de testomgeving, die het schema met
`Base.metadata.create_all()` bouwt, dubbele rijen toestond die productie al sinds de migratie
weigerde (bij een opt-out of een toestemmingsrij is dat een AVG-relevant verschil, niet
cosmetisch).

Beide constraints staan inmiddels AL in de modellen (`src/core/governance/models.py:162`,
`src/core/notifications/inbound/models.py:172-176`), met een comment die naar deze OP
verwijst. Er bestond alleen nog geen test die dat bewaakt -- deze guard is die test.

**Mutatiebewijs (2026-09-10), een regel per bewaakt element en in beide richtingen:**
- `uq_user_tenant_consent` uit `governance/models.py` gehaald -> ROOD.
- `uq_contact_opt_outs_tenant_contact_channel` uit `notifications/inbound/models.py`
  gehaald -> ROOD.
- Beide vervangen door een `Index(..., unique=True)` in plaats van een `UniqueConstraint`
  -> ROOD op dezelfde assertie. Dat is de tegenrichting die ertoe doet: PostgreSQL accepteert
  een unieke index voor eigen gebruik, maar `Base.metadata.create_all()` maakt er geen
  constraint van, en dan bestaat de bescherming in de testomgeving alsnog niet.
- Ongewijzigd -> GROEN.
"""

from __future__ import annotations

import pytest

from tests.architecture._unique_constraints import unieke_kolomverzamelingen

# Doel -> de kolommen waarop het model een UniqueConstraint hoort te leggen, met de naam
# die de migratie gebruikt (zodat `alembic check` beide kanten als dezelfde constraint ziet).
# Expliciet benoemd: een guard over een genoemde verzameling is in vijf seconden te
# controleren, en het mutatiebewijs heeft daarmee een regel per element.
_MODEL_CONSTRAINTS: dict[str, tuple[str, ...]] = {
    "user_consents": ("user_id", "tenant_id"),
    "contact_opt_outs": ("tenant_id", "contact", "channel"),
}


@pytest.mark.parametrize("tabel,kolommen", sorted(_MODEL_CONSTRAINTS.items()))
def test_the_migration_constraint_exists_in_the_model(
    tabel: str, kolommen: tuple[str, ...]
) -> None:
    """Het model draagt dezelfde UniqueConstraint die de migratie bij tabelcreatie maakt."""
    gevonden = unieke_kolomverzamelingen(tabel)
    verwacht = frozenset(kolommen)

    assert verwacht in gevonden, (
        f"Het model van `{tabel}` heeft geen UniqueConstraint over {sorted(kolommen)}.\n"
        f"Gevonden constraints: {[sorted(g) for g in gevonden] or 'geen'}\n\n"
        "De migratie maakt deze constraint wel aan. Zonder hem in het model bouwt elke "
        "testomgeving (Base.metadata.create_all()) een schema dat duplicaten toestaat die "
        "productie al weigert (ADR-036 OP-160)."
    )


def test_the_guard_is_not_vacuous() -> None:
    """Een lege verzameling maakt de test hierboven trivially groen."""
    assert _MODEL_CONSTRAINTS, "geen constraints benoemd"
    for tabel in _MODEL_CONSTRAINTS:
        assert unieke_kolomverzamelingen(tabel) is not None, f"{tabel} niet gevonden"
