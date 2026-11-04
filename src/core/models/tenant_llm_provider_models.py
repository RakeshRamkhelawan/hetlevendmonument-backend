"""De LLM-providers van een tenant -- zijn eindpunt, zijn model, zijn sleutel.

Besluit Rakesh 2026-09-20: geen vendor lock-in; een klant geeft bij de inrichting zijn eigen
provider op. Deze tabel is de opslag daarvoor, en de volgorde erin WORDT de failoverketen die
ADR-026 par. 1.2.1 beschrijft (`tenant.llm_chain`, dat tot nu toe niet bestond). Bewust
"wordt" en niet "is": de keten wordt vandaag OPGESLAGEN maar door niemand gebruikt --
`TenantLLMProviderService.keten()` heeft nul aanroepers, en dat verandert pas in fase 2b. Een
docstring die het tegenwoordige tijd maakt, leest als werkende functionaliteit.

**Over `api_key_encrypted`.** Die kolom bevat NOOIT een leesbare sleutel. De SERVICELAAG
versleutelt bij het schrijven en ontsleutelt bij het lezen via
`src/core/security/tenant_secret_encryption.py`, dat een eigen sleutel per tenant afleidt.
Hier stond eerst "de repository"; dat was onwaar sinds die controles een laag hoger zijn gezet
omdat `infra` niet van `auth` mag afhangen, en het sprak de docstring van de repository zelf
tegen. Twee docstrings die elkaar tegenspreken over waar een geheim wordt versleuteld, is
duurder dan geen docstring. De
kolom mag leeg zijn: een lokaal eindpunt (Ollama, vLLM, LM Studio) heeft geen sleutel nodig, en
een verzonnen placeholder zou als geldige sleutel worden aangeboden.

**Over RLS, en wees hier niet optimistisch.** Deze tabel krijgt policies conform ADR-005, maar
die zijn vandaag INERT: de applicatie verbindt als eigenaar van de tabellen en PostgreSQL past
RLS niet toe op de eigenaar (ADR-036 OP-151, gemeten). Ze werken zodra de rolwissel uit OP-154
landt. Wat vandaag WEL beschermt is het expliciete tenantfilter in de repository -- dat is dus
geen extra laag maar de enige laag, en het hoort op elke methode te staan.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.core.database.database import Base


class TenantLLMProvider(Base):  # type: ignore[misc]
    """Een taalmodel-eindpunt dat een tenant mag gebruiken."""

    __tablename__ = "tenant_llm_providers"
    __table_args__ = (
        # De keten is de sortering van deze rijen, dus twee rijen met dezelfde volgorde zouden
        # een niet-bepaalde failovervolgorde geven -- stil, en per query anders.
        UniqueConstraint("tenant_id", "volgorde", name="uq_tenant_llm_providers_tenant_volgorde"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: De plek in de failoverketen; lager gaat voor.
    volgorde: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Het label dat in de logregel en in het API-veld belandt. Zie
    #: `providers/openai_compatible.py::provider_name` voor de opschoning.
    naam: Mapped[str] = mapped_column(String(64), nullable=False)
    base_url: Mapped[str] = mapped_column(String(512), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    #: Versleuteld met een sleutel PER TENANT. Leeg = lokaal eindpunt zonder sleutel.
    api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    actief: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
