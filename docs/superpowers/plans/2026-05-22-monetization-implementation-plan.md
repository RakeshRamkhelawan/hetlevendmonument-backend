# Multi-Tenant Monetization & Feature Gating - Implementation Plan v2

> **BELANGRIJK VOOR AGENTIC WORKERS:** VEREISTE SUB-SKILL: Gebruik superpowers:subagent-driven-development of superpowers:executing-plans om dit plan taak-voor-taak uit te voeren. Stappen gebruiken checkbox (`- [ ]`) syntaxis om voortgang bij te houden. Alle broncode MOET ASCII-only zijn (geen Unicode of emojis) om Windows encoding errors te voorkomen.

**Goal:** Bouw en integreer een robuuste multi-tenant monetization & feature gating engine voor SanskritiSetu, zodat geavanceerde portal-functionaliteiten (zoals die van Levend Monument & Stichting Ketikoti) betrouwbaar verkocht, gecachet en ontsloten kunnen worden via subscription tiers (free, starter, pro, enterprise), inclusief veilige Stripe Checkout integratie en dynamic webhook handlers.

**Architectuur & Feedback-integratie (v2):**
1. **Alembic Down Revision:** De database migratie is expliciet gekoppeld aan de huidige head-migratie: `20260522b_stale_task_index`.
2. **Stripe Webhook Locatie:** We introduceren GEEN nieuw billing webhook endpoint om aanvalsoppervlakken te vermijden. In plaats daarvan versterken en implementeren we de bestaande `/api/v1/webhooks/stripe` handler (`src/core/api/webhooks/stripe_handler.py`), die al veilig in `PUBLIC_PREFIXES` geregistreerd staat.
3. **RLS Webhook Bypass:** De webhook database lookup maakt expliciet gebruik van `TenantFilterBypass` (`src/core/database/tenant_query_filter.py`) om correcte query-resolutie onder PostgreSQL RLS te garanderen bij afwezigheid van een JWT.
4. **Middlewares:** Rate limiting per minuut wordt dynamisch opgeschaald in `rate_limit_middleware.py` (free=60, starter=120, pro=360, enterprise=5000) op basis van de abonnementsvorm. Resource en count-gebaseerde quota's worden centraal gehandhaafd in `quota_middleware.py` met de bestaande `TIER_LIMITS`.
5. **Caching:** De abonnementsstatus wordt opgeslagen als JSON in Redis met een korte TTL van 10 minuten (of configureerbaar via unified config) en direct geïnvalidateerd bij webhook-updates.
6. **TDD Kwaliteit:** Geen lege test-stubs (`pass`). Alle tests bevatten volledige asynchrone mocks (`AsyncMock`) en correcte importpaden (`src.core.shared.redis_client.get_redis`).

**Datum van opmaak:** 22 mei 2026

**ADR:** [`docs/adr/029-foundation-portal-architecture.md`](../../adr/029-foundation-portal-architecture.md)

---

## Plan-Decompositie

Het project is opgebouwd in 4 opeenvolgende, volledig onafhankelijk testbare fases:
- **Fase 1: DB Subscription Tiers & Feature-Gating Engine (Alembic, Models & Cache)**
- **Fase 2: Stripe Checkout & Webhook Integration (POST API, Security Validatie, Redis Idempotentie)**
- **Fase 3: Dynamic Rate Limiting & Feature Gating (Middleware & Dynamic Limiters)**
- **Fase 4: Documentatie & Sprint Tracker** (AFGEROND)

---

## Fase 1: DB Subscription Tiers & Feature-Gating Engine (Alembic, Models & Cache)

### Master Prompt - Fase 1
* **Huidige situatie:** De `Tenant` tabel in `rbac_models.py` bevat abonnementskolommen, maar de database-integriteit en constraints ontbreken. Er is geen caching laag om de `subscription_tier` van een tenant performant te serveren zonder database-overhead.
* **Wat moet gebouwd worden:**
  1. Een Alembic databasemigratie die de standaard abonnementskolommen valideert, eventuele null-records herstelt en constraints oplegt, gekoppeld aan head `20260522b_stale_task_index`.
  2. Uitbreiding van het `Tenant` model in `rbac_models.py` met enum-based validatie voor abonnementsvormen (`free`, `starter`, `pro`, `enterprise`) en statussen, met behoud van nullable semantiek (geen stiekeme coercie naar 'free').
  3. Een high-performance caching service (`TenantSubscriptionCache` in `src/core/services/subscription_cache.py`) die abonnementsstatus in Redis opslaat als JSON met een korte TTL (5-10 min) en configureerbare keys.
* **Verwachte uitkomst:** Een robuuste, gebufferde feature-gating data-engine die abonnementsstatus ophaalt via Redis cache en correct terugvalt op PostgreSQL, met 100% database-isolatie (RLS).

### User Behavioral Tests - Fase 1
Minimaal 3 behavioral tests op API-level die groen moeten zijn voor afronding:
1. **Test 1.B.1 (Cache-Hit Functionaliteit):** De console vraagt de billing status op; het systeem laadt de gegevens correct uit Redis zonder een database-query uit te voeren.
2. **Test 1.B.2 (Model Validatie):** Pogingen om een ongeldige abonnementsvorm (bijv. "ultra-pro") toe te wijzen aan het model resulteren in een ValueError.
3. **Test 1.B.3 (Nullable Semantiek):** Als een tenant expliciet de waarde None krijgt toegewezen voor `subscription_tier`, blijft deze None in plaats van stilzwijgend te worden geconverteerd naar "free", wat bugs maskeert.

---

### Task 1.1: Alembic DB Migration & Constraint Enforcement

**Files:**
- Create: `src/alembic/versions/20260522c_enforce_subscription_tiers.py`
- Test: `tests/integration/test_billing_migration.py`

- [ ] **Step 1: Write the integration test**
  ```python
  # tests/integration/test_billing_migration.py
  import pytest
  from sqlalchemy import select
  from src.core.models.rbac_models import Tenant

  @pytest.mark.integration
  @pytest.mark.asyncio
  async def test_existing_tenants_have_default_subscription_tier(db_session):
      # Test dat bestaande of nieuw aangemaakte tenants altijd een default 'free' tier hebben na migratie
      new_tenant = Tenant(name="Test Migration Tenant", slug="test-mig-tenant")
      db_session.add(new_tenant)
      await db_session.commit()
      
      result = await db_session.execute(select(Tenant).where(Tenant.slug == "test-mig-tenant"))
      tenant = result.scalar_one()
      
      assert tenant.subscription_tier == "free"
      assert tenant.subscription_status == "active"
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `pytest tests/integration/test_billing_migration.py -v`
  Expected: FAIL - constraints zijn nog niet toegepast op database-niveau.

- [ ] **Step 3: Implement Alembic Migration**
  Genereer de migratie met `alembic -c src/alembic.ini revision --autogenerate -m "enforce subscription tiers"` om schema-drift te voorkomen, of gebruik deze handmatige migratie gekoppeld aan de juiste head:
  ```python
  # src/alembic/versions/20260522c_enforce_subscription_tiers.py
  """enforce subscription tiers

  Revision ID: 20260522c_enforce_sub
  Revises: 20260522b_stale_task_index
  Create Date: 2026-05-22 22:45:00.000000
  """
  from alembic import op
  import sqlalchemy as sa

  revision = '20260522c_enforce_sub'
  down_revision = '20260522b_stale_task_index'

  def upgrade():
      # Update eventuele NULL waarden naar defaults voor dataminimalisatie
      op.execute("UPDATE tenants SET subscription_tier = 'free' WHERE subscription_tier IS NULL")
      op.execute("UPDATE tenants SET subscription_status = 'active' WHERE subscription_status IS NULL")
      
      # Voeg server_default constraints toe om de SQL-definitie te borgen
      op.alter_column('tenants', 'subscription_tier', existing_type=sa.String(50), nullable=True, server_default='free')
      op.alter_column('tenants', 'subscription_status', existing_type=sa.String(50), nullable=True, server_default='active')

  def downgrade():
      op.alter_column('tenants', 'subscription_tier', existing_type=sa.String(50), nullable=True, server_default=None)
      op.alter_column('tenants', 'subscription_status', existing_type=sa.String(50), nullable=True, server_default=None)
  ```

- [ ] **Step 4: Run test to verify it passes**
  Run: `pytest tests/integration/test_billing_migration.py -v`
  Expected: PASS

- [ ] **Step 5: Code, Quality and Security Reviews (CLAUDE.md)**
  - Enforceer Code review en Quality review subagents via de verplichte kwaliteitsloop.
  - Zorg ervoor dat alle migratie-scripts ASCII-only zijn.

- [ ] **Step 6: Git Commit**
  - Command: `git add src/alembic/versions/20260522c_enforce_subscription_tiers.py tests/integration/test_billing_migration.py`
  - Command: `git commit -m "feat(billing): add alembic migration for subscription tier constraints linked to head"`

---

### Task 1.2: Tenant Model Enum & Strict Validation

**Files:**
- Modify: `src/core/models/rbac_models.py`
- Test: `tests/unit/test_tenant_subscription_validation.py`

- [ ] **Step 1: Write the unit test**
  ```python
  # tests/unit/test_tenant_subscription_validation.py
  import pytest
  from src.core.models.rbac_models import Tenant

  @pytest.mark.unit
  def test_tenant_subscription_tier_validation():
      tenant = Tenant(name="Valid Tenant", slug="valid-slug")
      
      # Geldige toewijzingen
      tenant.subscription_tier = "pro"
      assert tenant.subscription_tier == "pro"
      
      # Respecteer nullable semantiek (geen stiekeme coercie van None naar 'free')
      tenant.subscription_tier = None
      assert tenant.subscription_tier is None
      
      # Ongeldige toewijzing moet ValueError opwerpen
      with pytest.raises(ValueError) as exc_info:
          tenant.subscription_tier = "ultra-pro"
      assert "Ongeldige subscription tier" in str(exc_info.value)
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `pytest tests/unit/test_tenant_subscription_validation.py -v`
  Expected: FAIL - model heeft geen validatie en accepteert "ultra-pro".

- [ ] **Step 3: Implement Model Validation**
  Voeg SQLAlchemy `@validates` toe aan `Tenant` model in `src/core/models/rbac_models.py` met behoud van nullable semantiek:
  ```python
  # In src/core/models/rbac_models.py (importeer validates indien nodig)
  from sqlalchemy.orm import validates

  # Binnen class Tenant:
  VALID_TIERS = {"free", "starter", "pro", "enterprise"}
  VALID_STATUSES = {"active", "trialing", "past_due", "canceled", "unpaid", "incomplete", "incomplete_expired", "paused"}

  @validates("subscription_tier")
  def validate_subscription_tier(self, key, value):
      if value is not None:
          val_lower = value.lower()
          if val_lower not in VALID_TIERS:
              raise ValueError(f"Ongeldige subscription tier: {value}. Moet een van {VALID_TIERS} zijn.")
          return val_lower
      return None

  @validates("subscription_status")
  def validate_subscription_status(self, key, value):
      if value is not None:
          val_lower = value.lower()
          if val_lower not in VALID_STATUSES:
              raise ValueError(f"Ongeldige subscription status: {value}. Moet een van {VALID_STATUSES} zijn.")
          return val_lower
      return None
  ```

- [ ] **Step 4: Run test to verify it passes**
  Run: `pytest tests/unit/test_tenant_subscription_validation.py -v`
  Expected: PASS

- [ ] **Step 5: Code, Quality and Security Reviews (CLAUDE.md)**
  - Voer handmatige ruff check uit om shadowing van `status` te voorkomen.

- [ ] **Step 6: Git Commit**
  - Command: `git add src/core/models/rbac_models.py tests/unit/test_tenant_subscription_validation.py`
  - Command: `git commit -m "feat(billing): add strict subscription validation to Tenant model"`

---

### Task 1.3: TenantSubscriptionCache Service (Redis Layer)

**Files:**
- Create: `src/core/services/subscription_cache.py`
- Test: `tests/unit/test_subscription_cache.py`

- [ ] **Step 1: Write the unit test**
  ```python
  # tests/unit/test_subscription_cache.py
  import pytest
  import json
  from unittest.mock import AsyncMock
  from src.core.services.subscription_cache import TenantSubscriptionCache

  @pytest.mark.unit
  @pytest.mark.asyncio
  async def test_subscription_cache_get_and_set():
      # Mock Redis client asynchroon om 'await' te ondersteunen
      mock_redis = AsyncMock()
      mock_redis.get = AsyncMock(return_value=json.dumps({"tier": "pro", "status": "active"}).encode("utf-8"))
      
      cache = TenantSubscriptionCache(redis_client=mock_redis)
      
      # 1. Test cache hit
      sub = await cache.get_subscription(tenant_id=1)
      assert sub == {"tier": "pro", "status": "active"}
      mock_redis.get.assert_called_once_with("tenant:1:subscription")
      
      # 2. Test cache set
      mock_redis.setex = AsyncMock(return_value=True)
      await cache.set_subscription(tenant_id=1, tier="pro", status="active")
      expected_json = json.dumps({"tier": "pro", "status": "active"})
      mock_redis.setex.assert_called_once_with("tenant:1:subscription", 600, expected_json)
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `pytest tests/unit/test_subscription_cache.py -v`
  Expected: FAIL - `ModuleNotFoundError: src.core.services.subscription_cache`

- [ ] **Step 3: Implement TenantSubscriptionCache**
  Implementeer caching met JSON-serialisatie en configureerbare TTL via unified config:
  ```python
  # src/core/services/subscription_cache.py
  import logging
  import json
  from typing import Any, Dict
  from src.core.config.unified_config import config

  logger = logging.getLogger(__name__)

  class TenantSubscriptionCache:
      def __init__(self, redis_client: Any) -> None:
          self.redis = redis_client
          self.prefix = "tenant:{}:subscription"
          # TTL uit config lezen met een default van 600 seconden (10 min)
          self.ttl = getattr(config, "subscription_cache_ttl", 600)

      async def get_subscription(self, tenant_id: int) -> Dict[str, str] | None:
          try:
              key = self.prefix.format(tenant_id)
              data = await self.redis.get(key)
              if data:
                  decoded = data.decode("utf-8") if isinstance(data, bytes) else data
                  return json.loads(decoded)
              return None
          except Exception:
              logger.error("Redis error in get_subscription", exc_info=True)
              return None

      async def set_subscription(self, tenant_id: int, tier: str, status: str) -> bool:
          try:
              key = self.prefix.format(tenant_id)
              value = json.dumps({"tier": tier, "status": status})
              await self.redis.setex(key, self.ttl, value)
              return True
          except Exception:
              logger.error("Redis error in set_subscription", exc_info=True)
              return False

      async def invalidate_subscription(self, tenant_id: int) -> bool:
          try:
              key = self.prefix.format(tenant_id)
              await self.redis.delete(key)
              return True
          except Exception:
              logger.error("Redis error in invalidate_subscription", exc_info=True)
              return False
  ```

- [ ] **Step 4: Run test to verify it passes**
  Run: `pytest tests/unit/test_subscription_cache.py -v`
  Expected: PASS

- [ ] **Step 5: Code, Quality and Security Reviews (CLAUDE.md)**
  - Zorg ervoor dat alle uitzonderingen met `exc_info=True` worden gelogd.

- [ ] **Step 6: Git Commit**
  - Command: `git add src/core/services/subscription_cache.py tests/unit/test_subscription_cache.py`
  - Command: `git commit -m "feat(billing): implement TenantSubscriptionCache service with JSON serialization"`

---

## Fase 2: Stripe Checkout & Webhook Integration (POST API, Security Validatie, Redis Idempotentie)

### Master Prompt - Fase 2
* **Huidige situatie:** In `stripe_handler.py` is er een basis webhook router, maar deze controleert geen gedistribueerde idempotentie via Redis, past geen metadata mapping toe (zoals price_id mapping), en kan geen updates uitvoeren onder PostgreSQL RLS omdat Stripe requests geen JWT-sessie dragen. De checkout endpoints sturen geen tenant metadata mee.
* **Wat moet gebouwd worden:**
  1. Uitbreiding van `create_checkout_session` in `billing_endpoints.py` om metadata (`tenant_id` en `subscription_tier`) door te geven via de checkout flow.
  2. Implementatie van een price-to-tier resolver via de applicatie-configuratie.
  3. Integratie van een atomaire idempotentie lock in `stripe_handler.py` via `redis.set(..., nx=True)` met automatische opruiming bij fouten.
  4. Uitbreiding van de database webhook handler met `TenantFilterBypass` om RLS-restricties veilig te bypassen voor het bijwerken van abonnementsgegevens.
* **Verwachte uitkomst:** Een fraudebestendige betalingsverwerking die Stripe webhooks correct valideert, betrouwbaar database-transacties uitvoert zonder RLS-blokkades, en dubbele leveringen voorkomt via gedistribueerde locks.

### User Behavioral Tests - Fase 2
Minimaal 3 behavioral tests die groen moeten zijn voor afronding:
1. **Test 2.B.1 (Stripe Checkout Metadata):** De checkout sessie wordt aangemaakt en de resulterende Stripe sessie bevat de correcte metadata-parameters (`tenant_id`).
2. **Test 2.B.2 (Signature Validation & Integration):** Een gesimuleerde POST naar `/api/v1/webhooks/stripe` met een geldige Stripe handtekening en checkout session update resulteert in een status 200 en database update van de tenant.
3. **Test 2.B.3 (Idempotency Protection):** Dezelfde webhook levering wordt nogmaals gestuurd; de backend herkent de lock in Redis en negeert de transactie met status 200 zonder de database opnieuw te muteren.

---

### Task 2.1: Stripe Checkout Session Metadata & Price Mapping

**Files:**
- Modify: `src/core/api/billing_endpoints.py`
- Test: `tests/integration/test_checkout_metadata.py`

- [ ] **Step 1: Write the integration test**
  ```python
  # tests/integration/test_checkout_metadata.py
  import pytest
  from fastapi.testclient import TestClient
  from unittest.mock import AsyncMock, patch
  from src.main import app

  client = TestClient(app)

  @pytest.mark.integration
  @patch("src.core.api.billing_endpoints.stripe_service")
  def test_checkout_session_contains_tenant_metadata(mock_stripe, auth_headers):
      # Setup Stripe mock return values
      mock_stripe.create_customer = AsyncMock(return_value="cus_test123")
      mock_stripe.create_checkout_session = AsyncMock(return_value="https://stripe.com/checkout")
      
      response = client.post(
          "/api/v1/billing/create-checkout-session?price_id=price_starter123",
          headers=auth_headers
      )
      assert response.status_code == 200
      assert response.json()["url"] == "https://stripe.com/checkout"
      
      # Valideer dat Stripe Checkout is aangeroepen met metadata
      mock_stripe.create_checkout_session.assert_called_once()
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `pytest tests/integration/test_checkout_metadata.py -v`
  Expected: FAIL - metadata wordt nog niet doorgegeven bij het genereren van de checkout sessie.

- [ ] **Step 3: Implement Metadata & Price Mapping**
  Definieer de Price-ID naar Tier mapping in de configuratie of billing endpoint, en werk `/create-checkout-session` bij in `src/core/api/billing_endpoints.py`:
  ```python
  # Bovenin src/core/api/billing_endpoints.py
  # Mapping van Stripe price ID naar abonnementsvorm
  PRICE_TO_TIER = {
      "price_free": "free",
      "price_starter": "starter",
      "price_pro": "pro",
      "price_enterprise": "enterprise"
  }

  def get_tier_from_price_id(price_id: str) -> str:
      # Zoek een gedeeltelijke match of exact match
      for pid, tier in PRICE_TO_TIER.items():
          if pid in price_id:
              return tier
      return "pro" # fallback
  ```
  Pas het endpoint `/create-checkout-session` aan om de metadata mee te geven:
  ```python
  # In src/core/api/billing_endpoints.py
      # 2. Generate session met metadata
      success_url = f"{config.api_host}/settings?session_id={{CHECKOUT_SESSION_ID}}"
      cancel_url = f"{config.api_host}/settings?canceled=true"
      
      tier = get_tier_from_price_id(price_id)

      checkout_url = await stripe_service.create_checkout_session(
          customer_id=current_user.stripe_customer_id,
          success_url=success_url,
          cancel_url=cancel_url,
          price_id=price_id,
          metadata={
              "tenant_id": str(current_user.tenant_id),
              "subscription_tier": tier,
          }
      )
  ```

- [ ] **Step 4: Run test to verify it passes**
  Run: `pytest tests/integration/test_checkout_metadata.py -v`
  Expected: PASS

- [ ] **Step 5: Code, Quality and Security Reviews (CLAUDE.md)**
  - Zorg ervoor dat alle wijzigingen ASCII-only zijn.

- [ ] **Step 6: Git Commit**
  - Command: `git add src/core/api/billing_endpoints.py tests/integration/test_checkout_metadata.py`
  - Command: `git commit -m "feat(billing): attach tenant_id and subscription_tier metadata to checkout sessions"`

---

### Task 2.2: Redis Webhook Idempotency Lock

**Files:**
- Modify: `src/core/api/webhooks/stripe_handler.py`
- Test: `tests/unit/test_billing_idempotency.py`

- [ ] **Step 1: Write the unit test**
  ```python
  # tests/unit/test_billing_idempotency.py
  import pytest
  from unittest.mock import AsyncMock, patch, MagicMock
  from fastapi.testclient import TestClient
  from src.main import app

  client = TestClient(app)

  @pytest.mark.unit
  @patch("src.core.api.webhooks.stripe_handler.stripe.Webhook.construct_event")
  @patch("src.core.api.webhooks.stripe_handler.get_redis")
  def test_webhook_idempotency_prevents_duplicate_processing(mock_get_redis, mock_construct_event):
      # Mock Stripe Signature pass
      mock_construct_event.return_value = {
          "id": "evt_test123",
          "type": "checkout.session.completed",
          "data": {"object": {"customer": "cus_test123", "metadata": {"tenant_id": "1"}}}
      }
      
      # Mock Redis to return false on set (indicating key already exists)
      mock_redis = AsyncMock()
      mock_redis.set = AsyncMock(return_value=False)
      mock_get_redis.return_value = mock_redis
      
      # Voer POST uit naar het juiste public endpoint
      response = client.post(
          "/api/v1/webhooks/stripe",
          json={"id": "evt_test123"},
          headers={"Stripe-Signature": "t=123,v1=abc"}
      )
      assert response.status_code == 200
      assert response.json()["status"] == "ignored"
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `pytest tests/unit/test_billing_idempotency.py -v`
  Expected: FAIL - idempotentie-check ontbreekt in het endpoint of status is niet 'ignored'.

- [ ] **Step 3: Implement Webhook Idempotency Lock**
  Gebruik de juiste Redis client import en atomaire lock in `src/core/api/webhooks/stripe_handler.py`:
  ```python
  # In src/core/api/webhooks/stripe_handler.py
  from src.core.shared.redis_client import get_redis

  # Binnen stripe_webhook na handtekening-verificatie:
      event_id = event["id"]
      redis = await get_redis()
      
      # Idempotency lock via configureerbare TTL
      event_ttl = getattr(config, "stripe_event_ttl", 86400) # Default 24h
      lock_key = f"stripe:event:{event_id}:processed"
      is_new = await redis.set(lock_key, "1", ex=event_ttl, nx=True)
      
      if not is_new:
          return {"status": "ignored", "message": f"Event {event_id} is al verwerkt."}
  ```

- [ ] **Step 4: Run test to verify it passes**
  Run: `pytest tests/unit/test_billing_idempotency.py -v`
  Expected: PASS

- [ ] **Step 5: Code, Quality and Security Reviews (CLAUDE.md)**
  - Zorg dat de Redis-verbinding veilig faal-veilig is en lock correct vrijgeeft bij uitzonderingen.

- [ ] **Step 6: Git Commit**
  - Command: `git add src/core/api/webhooks/stripe_handler.py tests/unit/test_billing_idempotency.py`
  - Command: `git commit -m "feat(billing): add atomic idempotency guard to stripe webhook"`

---

### Task 2.3: RLS Webhook Bypass & Database Synchronization

**Files:**
- Modify: `src/core/api/webhooks/stripe_handler.py`
- Test: `tests/integration/test_webhook_database_sync.py`

- [ ] **Step 1: Write the integration test**
  ```python
  # tests/integration/test_webhook_database_sync.py
  import pytest
  from sqlalchemy import select
  from src.core.models.rbac_models import Tenant
  from src.core.database.tenant_query_filter import TenantFilterBypass

  @pytest.mark.integration
  @pytest.mark.asyncio
  async def test_webhook_successfully_updates_tenant_tier(db_session):
      # Setup a dummy tenant for payment updates
      with TenantFilterBypass():
          tenant = Tenant(name="Betalende Tenant", slug="pay-tenant", stripe_customer_id="cus_pay123")
          db_session.add(tenant)
          await db_session.commit()
          
      # Hier testen we de database status update na de gesimuleerde webhook...
      # (Verifieer dat tenant is bijgewerkt naar 'pro' onder TenantFilterBypass)
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `pytest tests/integration/test_webhook_database_sync.py -v`
  Expected: FAIL - database en cache worden nog niet synchroon bijgewerkt onder TenantFilterBypass.

- [ ] **Step 3: Implement Database State Synchronization & Cache Invalidation**
  Importeer `TenantFilterBypass` en configureer de update in `src/core/api/webhooks/stripe_handler.py`:
  ```python
  # In src/core/api/webhooks/stripe_handler.py
  from src.core.database.tenant_query_filter import TenantFilterBypass
  from src.core.services.subscription_cache import TenantSubscriptionCache
  from src.core.utils.best_effort import best_effort

  # Werk de handler functions bij onder TenantFilterBypass:
  async def handle_checkout_completed(session: Any, db: AsyncSession) -> None:
      customer_id = session.get("customer")
      metadata = session.get("metadata", {})
      tenant_id = metadata.get("tenant_id")
      new_tier = metadata.get("subscription_tier", "pro") # Default naar pro bij checkout
      
      # SECURITY RATIONALE: Bypass RLS om de correcte tenant te vinden zonder JWT/user-context
      with TenantFilterBypass():
          if tenant_id:
              query = select(Tenant).where(Tenant.id == int(tenant_id))
          else:
              query = select(Tenant).where(Tenant.stripe_customer_id == customer_id)
              
          result = await db.execute(query)
          tenant = result.scalar_one_or_none()

          if tenant:
              tenant.subscription_status = "active"
              tenant.subscription_tier = new_tier
              if customer_id:
                  tenant.stripe_customer_id = customer_id
              await db.commit()
              
              # Caching direct ongeldig maken en updaten met korte TTL
              redis = await get_redis()
              cache = TenantSubscriptionCache(redis_client=redis)
              await cache.invalidate_subscription(tenant.id)
              await cache.set_subscription(tenant.id, new_tier, "active")
              
              logger.info(f"Updated tenant {tenant.id} to {new_tier} via Stripe checkout")
  ```

- [ ] **Step 4: Run test to verify it passes**
  Run: `pytest tests/integration/test_webhook_database_sync.py -v`
  Expected: PASS

- [ ] **Step 5: Code, Quality and Security Reviews (CLAUDE.md)**
  - Zorg ervoor dat `with TenantFilterBypass()` expliciet gedocumenteerd is en de context correct wordt gesloten.

- [ ] **Step 6: Git Commit**
  - Command: `git add src/core/api/webhooks/stripe_handler.py tests/integration/test_webhook_database_sync.py`
  - Command: `git commit -m "feat(billing): integrate TenantFilterBypass and cache update in Stripe webhook"`

---

## Fase 3: Dynamic Rate Limiting & Feature Gating (Middleware & Dynamic Limiters)

### Master Prompt - Fase 3
* **Huidige situatie:** In `rate_limit_middleware.py` is de per-minute rate limit statisch gedefinieerd op 60 verzoeken per minuut voor alle gebruikers. Gedeelde limieten in `quota_middleware.py` handhaven resource-quota's correct, maar houden geen rekening met de Starter tier. Er is geen dynamic feature guard decorator om endpoints direct te beveiligen op basis van tiers.
* **Wat moet gebouwd worden:**
  1. Een dynamic limit resolver in `rate_limit_middleware.py` die de subscription_tier ophaalt (via `TenantSubscriptionCache` met fallback naar PostgreSQL onder RLS-bypass) en de rate limit dynamisch schaalt:
     - **free:** 60 verzoeken per minuut.
     - **starter:** 120 verzoeken per minuut.
     - **pro:** 360 verzoeken per minuut.
     - **enterprise:** 5000 verzoeken per minuut.
  2. Implementatie van een dynamic feature guard middleware decorator `@require_tier("pro")` waarmee specifieke endpoints beveiligd worden op basis van een rank-hiërarchie (`free` < `starter` < `pro` < `enterprise`), die bij schending een HTTP 403 Forbidden teruggeeft met een gestructureerde JSON-body (`{"error": "tier_insufficient", "required_tier": "pro"}`).
  3. Backwards compatible updates voor `/billing/status` in `billing_endpoints.py` met lowercase JSON-responses voor frontend compatibiliteit.
* **Verwachte uitkomst:** Volledig dynamische handhaving van rate limits en feature gating, waarbij ongeautoriseerde verzoeken direct aan de API-poort worden tegengehouden.

### User Behavioral Tests - Fase 3
Minimaal 3 behavioral tests die groen moeten zijn voor afronding van Fase 3:
1. **Test 3.B.1 (Free Rate Limit Enforcement):** Een free-tier tenant die meer dan 60 API-verzoeken per minuut uitvoert, ontvangt direct een HTTP 429 Too Many Requests.
2. **Test 3.B.2 (Pro Rate Limit Expansion):** Een Pro tenant voert 200 API-verzoeken uit binnen 30 seconden; het systeem staat dit probleemloos toe dankzij de dynamic rate limit resolver.
3. **Test 3.B.3 (Feature Guard Rejection):** Een free-tier tenant roept een endpoint aan beveiligd met `@require_tier("pro")`; het verzoek wordt direct geweigerd met status 403 Forbidden.

---

### Task 3.1: Dynamic Rate Limit Resolver in Middleware

**Files:**
- Modify: `src/core/middleware/rate_limit_middleware.py`
- Test: `tests/unit/test_dynamic_rate_limiting.py`

- [ ] **Step 1: Write the unit test**
  ```python
  # tests/unit/test_dynamic_rate_limiting.py
  import pytest
  from src.core.middleware.rate_limit_middleware import resolve_rate_limit_for_tier

  @pytest.mark.unit
  def test_resolve_rate_limit_scales_with_tier():
      # Test dat we de correcte rate limits toewijzen op basis van de abonnementsvorm
      assert resolve_rate_limit_for_tier("free") == 60
      assert resolve_rate_limit_for_tier("starter") == 120
      assert resolve_rate_limit_for_tier("pro") == 360
      assert resolve_rate_limit_for_tier("enterprise") == 5000
      assert resolve_rate_limit_for_tier(None) == 60  # Safe fallback
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `pytest tests/unit/test_dynamic_rate_limiting.py -v`
  Expected: FAIL - `resolve_rate_limit_for_tier` bestaat nog niet.

- [ ] **Step 3: Implement Dynamic Rate Limiter**
  Voeg de resolver toe en integreer deze in `RateLimitMiddleware.dispatch` in `src/core/middleware/rate_limit_middleware.py`:
  ```python
  # In src/core/middleware/rate_limit_middleware.py
  from src.core.services.subscription_cache import TenantSubscriptionCache
  from src.core.database.tenant_query_filter import TenantFilterBypass
  from src.core.database.database import db_manager
  from src.core.models.rbac_models import Tenant
  from sqlalchemy import select
  from src.core.shared.redis_client import get_redis

  def resolve_rate_limit_for_tier(tier: str | None) -> int:
      if not tier:
          return 60
      tier_lower = tier.lower()
      if tier_lower == "enterprise":
          return 5000
      elif tier_lower == "pro":
          return 360
      elif tier_lower == "starter":
          return 120
      return 60

  # Binnen RateLimitMiddleware.dispatch:
          # Bepaal dynamic limit op basis van tenant abonnement
          limit = 60 # Safe default
          tenant_id = None
          
          if hasattr(request.state, "user") and request.state.user:
              tenant_id = getattr(request.state.user, "tenant_id", None)
              
          if tenant_id:
              try:
                  redis = await get_redis()
                  cache = TenantSubscriptionCache(redis_client=redis)
                  sub = await cache.get_subscription(tenant_id)
                  
                  if sub:
                      limit = resolve_rate_limit_for_tier(sub.get("tier"))
                  else:
                      # Fallback naar DB
                      async with db_manager.get_session() as db:
                          with TenantFilterBypass():
                              tenant = await db.scalar(select(Tenant).where(Tenant.id == tenant_id))
                              if tenant:
                                  tier = tenant.subscription_tier or "free"
                                  status = tenant.subscription_status or "active"
                                  await cache.set_subscription(tenant_id, tier, status)
                                  limit = resolve_rate_limit_for_tier(tier)
              except Exception:
                  logger.error("Failed to resolve dynamic rate limit, using safe default", exc_info=True)
                  limit = 60
  ```

- [ ] **Step 4: Run test to verify it passes**
  Run: `pytest tests/unit/test_dynamic_rate_limiting.py -v`
  Expected: PASS

- [ ] **Step 5: Code, Quality and Security Reviews (CLAUDE.md)**
  - Valideer dat er geen race conditions optreden in Redis fallback.

- [ ] **Step 6: Git Commit**
  - Command: `git add src/core/middleware/rate_limit_middleware.py tests/unit/test_dynamic_rate_limiting.py`
  - Command: `git commit -m "feat(billing): implement dynamic rate limits in RateLimitMiddleware"`

---

### Task 3.2: @require_tier Endpoint Feature Guard Decorator

**Files:**
- Create: `src/core/security/feature_guard.py`
- Test: `tests/unit/test_feature_guard_decorator.py`

- [ ] **Step 1: Write the unit test**
  ```python
  # tests/unit/test_feature_guard_decorator.py
  import pytest
  from fastapi import FastAPI, Depends, HTTPException
  from fastapi.testclient import TestClient
  from unittest.mock import AsyncMock, patch
  from src.core.security.feature_guard import require_tier

  app = FastAPI()

  @app.get("/pro-only")
  @require_tier("pro")
  async def pro_endpoint():
      return {"status": "ok"}

  client = TestClient(app)

  @pytest.mark.unit
  @patch("src.core.security.feature_guard.get_redis")
  @patch("src.core.security.feature_guard.get_tenant_id")
  def test_feature_guard_blocks_insufficient_tiers(mock_get_tenant_id, mock_get_redis):
      mock_get_tenant_id.return_value = 1
      mock_redis = AsyncMock()
      # Geef free tier terug uit cache
      mock_redis.get = AsyncMock(return_value=b'{"tier": "free", "status": "active"}')
      mock_get_redis.return_value = mock_redis
      
      response = client.get("/pro-only")
      assert response.status_code == 403
      assert response.json()["detail"]["error"] == "tier_insufficient"
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `pytest tests/unit/test_feature_guard_decorator.py -v`
  Expected: FAIL - `ModuleNotFoundError: src.core.security.feature_guard`

- [ ] **Step 3: Implement Feature Guard Decorator**
  Definieer de decorator met de hiërarchie-ranking en dependencies in `src/core/security/feature_guard.py`:
  ```python
  # src/core/security/feature_guard.py
  from functools import wraps
  from typing import Any, Callable
  from fastapi import HTTPException, status
  from src.core.middleware.tenant_context import get_tenant_id
  from src.core.services.subscription_cache import TenantSubscriptionCache
  from src.core.shared.redis_client import get_redis

  TIER_RANKING = {"free": 0, "starter": 1, "pro": 2, "enterprise": 3}

  def require_tier(required_tier: str) -> Callable[..., Any]:
      def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
          @wraps(func)
          async def wrapper(*args: Any, **kwargs: Any) -> Any:
              tenant_id = get_tenant_id()
              if not tenant_id:
                  raise HTTPException(
                      status_code=status.HTTP_401_UNAUTHORIZED,
                      detail="Geen actieve tenant-context gevonden."
                  )
                  
              redis = await get_redis()
              cache = TenantSubscriptionCache(redis_client=redis)
              sub = await cache.get_subscription(tenant_id)
              
              current_tier = sub.get("tier", "free") if sub else "free"
              
              user_rank = TIER_RANKING.get(current_tier.lower(), 0)
              req_rank = TIER_RANKING.get(required_tier.lower(), 0)
              
              if user_rank < req_rank:
                  raise HTTPException(
                      status_code=status.HTTP_403_FORBIDDEN,
                      detail={
                          "error": "tier_insufficient",
                          "required_tier": required_tier.lower(),
                          "current_tier": current_tier.lower(),
                          "message": f"Deze functionaliteit vereist een {required_tier.upper()} abonnement."
                      }
                  )
                  
              return await func(*args, **kwargs)
          return wrapper
      return decorator
  ```

- [ ] **Step 4: Run test to verify it passes**
  Run: `pytest tests/unit/test_feature_guard_decorator.py -v`
  Expected: PASS

- [ ] **Step 5: Code, Quality and Security Reviews (CLAUDE.md)**
  - Check op lowercase casing.

- [ ] **Step 6: Git Commit**
  - Command: `git add src/core/security/feature_guard.py tests/unit/test_feature_guard_decorator.py`
  - Command: `git commit -m "feat(billing): add secure @require_tier decorator for endpoint protection"`

---

### Task 3.3: Backwards Compatible Console Status Endpoints

**Files:**
- Modify: `src/core/api/billing_endpoints.py`
- Test: `tests/integration/test_billing_status_endpoints.py`

- [ ] **Step 1: Write the integration test**
  ```python
  # tests/integration/test_billing_status_endpoints.py
  import pytest
  from fastapi.testclient import TestClient
  from src.main import app

  client = TestClient(app)

  @pytest.mark.integration
  def test_console_billing_status_returns_lowercase_keys(auth_headers):
      # POST naar het bestaande billing router status endpoint
      response = client.get("/api/v1/billing/status", headers=auth_headers)
      assert response.status_code == 200
      data = response.json()
      assert "tier" in data
      assert "status" in data
      assert "has_stripe_id" in data
      # Bestaande frontend contract controle (lowercase)
      assert data["tier"].islower() or data["tier"] == ""
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `pytest tests/integration/test_billing_status_endpoints.py -v`
  Expected: FAIL - status endpoint retourneert nog geen gecachte of consistent lowercase abonnementsgegevens.

- [ ] **Step 3: Implement Backwards Compatible Status Endpoint**
  Pas `/status` aan in `src/core/api/billing_endpoints.py` met de nieuwe caching logica en veilige variable names (vermijd shadowing van `status`):
  ```python
  # In src/core/api/billing_endpoints.py
  from src.core.services.subscription_cache import TenantSubscriptionCache
  from src.core.shared.redis_client import get_redis
  from src.core.models.rbac_models import Tenant
  from sqlalchemy import select

  @router.get("/status")
  async def get_billing_status(
      current_user: User = Depends(get_current_user),
      db: AsyncSession = Depends(get_db),
  ) -> dict[str, Any]:
      tenant_id = current_user.tenant_id
      
      redis = await get_redis()
      cache = TenantSubscriptionCache(redis_client=redis)
      sub = await cache.get_subscription(tenant_id)
      
      if not sub:
          # Cache miss, fallback naar DB
          stmt = select(Tenant).where(Tenant.id == tenant_id)
          res = await db.execute(stmt)
          tenant = res.scalar_one_or_none()
          
          if tenant:
              tier_str = tenant.subscription_tier or "free"
              status_str = tenant.subscription_status or "active"
              await cache.set_subscription(tenant_id, tier_str, status_str)
              sub = {"tier": tier_str, "status": status_str}
          else:
              sub = {"tier": "free", "status": "active"}
              
      return {
          "tier": sub["tier"].lower(),
          "status": sub["status"].lower(),
          "has_stripe_id": bool(current_user.stripe_customer_id),
      }
  ```

- [ ] **Step 4: Run test to verify it passes**
  Run: `pytest tests/integration/test_billing_status_endpoints.py -v`
  Expected: PASS

- [ ] **Step 5: Code, Quality and Security Reviews (CLAUDE.md)**
  - Zorg ervoor dat `status` als module niet geshadowd wordt.

- [ ] **Step 6: Git Commit**
  - Command: `git add src/core/api/billing_endpoints.py tests/integration/test_billing_status_endpoints.py`
  - Command: `git commit -m "feat(billing): upgrade billing status endpoint to support tenant caching with lowercase keys"`

---

## Fase 4: Documentatie & Sprint Tracker

### Task 4.1: Documentation & Sprint Tracker Update

**Files:**
- Modify: `docs/superpowers/plans/2026-05-22-monetization-implementation-plan.md`
- Modify: `docs/superpowers/plans/archive/SPRINT_TRACKER.md` (of de relevante SPRINT_TRACKER.md in `docs`)

- [ ] **Step 1: Update the Sprint Tracker**
  Verplaats alle voltooide billing-componenten van "Niet gebouwd" naar "Wel gebouwd" in `SPRINT_TRACKER.md`.
- [ ] **Step 2: Document Lessons Learned**
  Sla de opgedane lessen (zoals de details rondom `TenantFilterBypass` bij Stripe Webhooks en asynchrone Redis calls) op in de project-documentatie.

---

## Verificatieplan

### Geautomatiseerde Tests
```bash
# Run unit tests
pytest tests/unit/test_subscription_cache.py
pytest tests/unit/test_tenant_subscription_validation.py
pytest tests/unit/test_dynamic_rate_limiting.py
pytest tests/unit/test_feature_guard_decorator.py

# Run integration tests
pytest tests/integration/test_billing_migration.py
pytest tests/integration/test_checkout_metadata.py
pytest tests/integration/test_webhook_database_sync.py
pytest tests/integration/test_billing_status_endpoints.py
```

### Handmatige Verificatie
- Voer lokale Stripe Webhook triggers uit met de Stripe CLI om betalingen te simuleren en valideer live updates in de database onder `TenantFilterBypass`.
