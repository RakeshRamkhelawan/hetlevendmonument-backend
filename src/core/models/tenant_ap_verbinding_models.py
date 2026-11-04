"""De ActivePieces-verbinding van een tenant: adres, inlog en project.

Een klant heeft precies een eigen ActivePieces-project; deze tabel legt vast hoe de applicatie
daar namens die klant bij komt. Daarom is `tenant_id` UNIQUE: een tweede rij voor dezelfde klant
zou een niet-bepaalde keuze van verbinding geven.

**Over `wachtwoord_encrypted`.** Die kolom bevat NOOIT een leesbaar wachtwoord. De SERVICELAAG
versleutelt bij het schrijven en ontsleutelt bij het lezen via
`src/core/security/tenant_secret_encryption.py`; de repository doet dat niet, omdat `infra` niet
van `auth` mag afhangen.

**Over RLS.** De tabel heeft een policy conform ADR-005, maar die is vandaag INERT zolang de
applicatie als eigenaar van de tabellen verbindt (ADR-036 OP-151). Het expliciete
`tenant_id`-filter in de repository is dus de enige werkende laag.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.core.database.database import Base


class TenantAPVerbinding(Base):  # type: ignore[misc]
    """Hoe de applicatie bij het ActivePieces-project van een tenant komt."""

    __tablename__ = "tenant_ap_verbindingen"
    # Als constraint met naam, niet als `unique=True` op de kolom: samen met `index=True` maakt
    # SQLAlchemy daar een UNIQUE INDEX van, en dat wijkt af van de migratie (alembic check).
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_tenant_ap_verbindingen_tenant"),
        # Een AP-project hoort bij EEN tenant (zie de migratie).
        UniqueConstraint(
            "base_url", "project_id", name="uq_tenant_ap_verbindingen_adres_project"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    base_url: Mapped[str] = mapped_column(String(512), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    #: Versleuteld met een sleutel PER TENANT, door de servicelaag.
    wachtwoord_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    project_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
