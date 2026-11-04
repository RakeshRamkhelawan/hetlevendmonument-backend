# BE-EP-046: Foundation Stichting Donaties & Erfgoed Adoptie Endpoints

**Status:** APPROVED  
**Auteur:** SanskritiSetu Senior Architect  
**Datum:** 2026-09-12  
**Sprint:** ADR-029 P2-2  
**Component:** `src/core/api/v1/foundation/donations.py`  

---

## 1. Doel & Architectuur

In het Levend Monument platform (ADR-029) is publieke betrokkenheid en ondersteuning van erfgoedbehoud essentieel. `BE-EP-046` introduceert veilige donatie- en erfgoed-adoptie-endpoints gekoppeld aan Stripe Checkout.

### Endpoints
1. `POST /{tenantSlug}/foundation/donations/checkout`
   - Publiek endpoint.
   - Rate limited met `portal_public_write_limit` (30/min).
   - Beveiligd tegen abuse via `@require_hcaptcha`.
   - Valideert bedrag (€1,00 tot €5.000,00 oftewel 100 tot 500.000 cent).
   - Maakt Stripe Checkout Session aan via `stripe_service`.
   - Bevat resilient mock checkout URL in dev/test omgeving wanneer Stripe niet geconfigureerd is.
2. `GET /{tenantSlug}/foundation/donations/stats`
   - Publiek endpoint.
   - Rate limited met `portal_public_read_limit` (120/min).
   - Toont totaal opgehaald bedrag (in centen), aantal donateurs en recente donaties (met respect voor anonimiteit).
3. `GET /{tenantSlug}/foundation/admin/donations`
   - Beveiligd admin/curator endpoint (`require_curator_or_admin`).
   - Volledige auditlijst van alle donaties inclusief e-mailadressen en transactie-IDs.

---

## 2. Datamodellen & Schemas

```python
class DonationFrequency(str, Enum):
    ONE_TIME = "one_time"
    MONTHLY = "monthly"

class DonationCheckoutRequest(BaseModel):
    amount_cents: int = Field(..., ge=100, le=500000)
    frequency: DonationFrequency = DonationFrequency.ONE_TIME
    donor_email: EmailStr
    donor_name: str | None = None
    is_anonymous: bool = False
    monument_id: int | None = None
    message: str | None = Field(None, max_length=500)
    hcaptcha_token: str | None = None

class DonationCheckoutResponse(BaseModel):
    checkout_url: str
    session_id: str
    amount_cents: int
    frequency: str

class DonationHistoryItem(BaseModel):
    id: int
    amount_cents: int
    frequency: str
    donor_name: str | None
    message: str | None
    created_at: str
    is_anonymous: bool

class DonationStatsResponse(BaseModel):
    total_raised_cents: int
    total_donations_count: int
    monthly_supporters_count: int
    recent_donations: list[DonationHistoryItem]
```

---

## 3. Privacy & Anonimiteit

Conform de Levend Monument privacyregels (BE-EP-038):
- Wanneer een donateur kiest voor `is_anonymous = True`, wordt de `donor_name` in publieke endpoints (`GET /donations/stats`) gemaskeerd als `"Anonieme Vriend van het Monument"`.
- Het e-mailadres wordt NOOIT publiek geëxposeerd en is enkel zichtbaar in de afgeschermde beheeromgeving (`/admin/donations`).

---

## 4. Trainingssamenvatting

- **Component**: Foundation Stichting Donaties & Erfgoed Adoptie Endpoints (`BE-EP-046`)
- **Doel**: Veilige betalingsafhandeling en transparantiemetrics voor publieke donaties en erfgoed-adoptie.
- **Architectuurregel**: Bedragen strikt in integer centen (`amount_cents`), bot-protectie via hCaptcha, rate-limiting en veilige dev/test mock fallback.
- **Geverifieerd met**: `tests/unit/test_foundation_donations.py` (8 tests PASS).
- **Actor**: Bezoeker / Erfgoedliefhebber
  - **Flow**: Bezoeker bezoekt `/doneren` -> Kiest bedrag, frequentie en eventuele anonimiteit -> Frontend roept `POST /{tenantSlug}/foundation/donations/checkout` aan met hCaptcha token -> Backend valideert invoer en maakt Stripe Checkout sessie aan -> Bezoeker wordt doorgestuurd naar betaalpagina.
- **Actor**: Curator / Beheerder
  - **Flow**: Curator opent beheer -> Roept `GET /{tenantSlug}/foundation/admin/donations` aan met curator bearer token -> Backend levert ongeanonimiseerde donatielijst inclusief audit e-mailadressen.
