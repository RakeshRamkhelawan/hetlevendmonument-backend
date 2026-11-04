"""Gedeelde meting: welke kolomverzamelingen draagt een model als UniqueConstraint?

**Waarom dit een gedeelde module is (ADR-036 OP-155/OP-160).** Twee guards herhaalden dezelfde
functie (`test_composite_fk_targets_exist_in_the_models.py` en
`test_named_unique_constraints_exist_in_the_models.py`): beide meten of een tabel een
`UniqueConstraint` over een genoemde kolomverzameling draagt, en beide sluiten een
`Index(..., unique=True)` bewust uit -- PostgreSQL accepteert die wel als doel, maar
`Base.metadata.create_all()` maakt er geen constraint van, en dan ontbreekt de bescherming in
elke testomgeving. Twee kopieen van dezelfde meting kunnen uit elkaar lopen als de een wordt
aangepast en de ander niet; deze module bestaat om dat te voorkomen.

Bestand begint met een underscore: pytest verzamelt hem dan niet als testmodule.
"""

from __future__ import annotations

from sqlalchemy import UniqueConstraint


def unieke_kolomverzamelingen(tabelnaam: str) -> list[frozenset[str]]:
    """De kolomverzamelingen waarover het MODEL een UniqueConstraint legt.

    Een `Index(..., unique=True)` telt bewust NIET mee: PostgreSQL accepteert die wel als
    doel, maar SQLAlchemy maakt er bij `create_all()` geen constraint van, en dan ontbreekt de
    bescherming in de testomgeving alsnog.
    """
    from src.core.database import import_all_models  # noqa: F401
    from src.core.database.database import Base

    tabel = Base.metadata.tables.get(tabelnaam)
    assert tabel is not None, (
        f"Tabel {tabelnaam!r} staat niet in Base.metadata. Is het model geregistreerd in "
        "`import_all_models.py`? Zonder registratie meet deze functie niets."
    )
    return [
        frozenset(kolom.name for kolom in constraint.columns)
        for constraint in tabel.constraints
        if isinstance(constraint, UniqueConstraint)
    ]
