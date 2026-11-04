# ADR-003: Tenant Boundary - JWT is de Source of Truth

## Status
Accepted

## Context
Het platform moet bij elk request (API of WebSocket) onmiddellijk en fraudebestendig vaststellen bij welke tenant de actie hoort. We hebben een grens nodig tussen de onbeveiligde buitenwereld en de beveiligde interne data-layer.

### Risico's
- **Header Spoofing**: Een aanvaller zet `X-Tenant-ID: victim-tenant` in een HTTP request.
- **URL Overrides**: Bijv. `GET /api/v1/instelling1/data` terwijl de gebruiker bij instelling 2 hoort.

## Decision
De **JWT (JSON Web Token)** is de enige gezaghebbende bron voor tenant-identiteit.

### Implementatie-details
1. **Token Claims**: De token MOET een `tenant_id` claim bevatten, gezet door de Auth-service na succesvolle login.
2. **Middleware Handhaving**:
```python
# src/core/middleware/tenant_middleware.py
async def __call__(self, scope, receive, send):
    # 1. Extraheer token (Authorization header of Cookie)
    # 2. Decodeer & Verifieer handtekening
    # 3. Extract tenant_id
    tenant_id = payload.get("tenant_id")
    if not tenant_id:
        return self._fail_auth(401, "Missing tenant context")
    # 4. Bind aan ContextVar (Thread/Async safe)
    set_tenant_context(tenant_id)
```
3. **Host Policy**: Subdomains (`instelling.sanskritisetu.org`) zijn slechts routing-hints voor Traefik. De backend verifieert ALTIJD of de `tenant_id` in de token overeenkomt met de bedoelde resources.

### Spoofing Protection (SLI)
| Threat | Mitigatie | Verificatie |
| :--- | :--- | :--- |
| Forbidden Access | JWT signatures (OIDC) | 100% rejection rate voor invalid sigs |
| Token Theft | HTTPS only + HttpOnly cookies | Audit logs per IP/Tenant mismatch |

## Consequences
- **Positive**:
    - Stateless en cryptografisch beveiligd.
    - Voorkomt spoofing op gateway niveau.
- **Negative**:
    - Token-invalidatie bij tenant-wijziging is lastiger (vereist short TTL of blacklist).
- **Neutral/Notes**:
    - Voor WebSockets wordt de `tenant_id` vastgelegd tijdens de handshake; updates tijdens een sessie vereisen reconnect.

## AI Act Governance Mapping (ADR-031)

Dit ADR levert aantoonbaar bewijs voor de volgende AI Act vereisten:

| Vereiste | Artikel | Hoe dit ADR voldoet |
|----------|---------|---------------------|
| Tenant identity as foundation for all AI governance | ADR-031 §1 | JWT claim is step 1 of the canonical governance pipeline; no AI action can proceed without cryptographically verified tenant context |
| Prevention of cross-tenant AI action execution | ADR-031 §4 | `set_tenant_context()` ensures all downstream AI decisions (Council, Gatekeeper, audit) are scoped to the authenticated tenant |

## SOC 2 Mapping

Dit ADR levert aantoonbaar bewijs voor de volgende SOC 2 Security Criteria:

| Criterium | Subcriteria | Hoe dit ADR voldoet |
| --------- | ---------- | ------------------- |
| CC6.1 | Logical access controls | JWT verifieert identiteit vóór toegang wordt verleend; `tenant_id` claim is cryptografisch gebonden aan het token via RS256/HS256 handtekening; middleware weigert 100% van requests zonder geldig JWT |
| CC6.2 | Prior to issuing credentials, entity is registered and authorized | JWT wordt uitsluitend uitgegeven na succesvolle authenticatie tegen de gebruikersopslag; geen token zonder geverifieerde login |
| CC6.3 | Access to data restricted based on authorized individual | `set_tenant_context()` bindt de `tenant_id` uit de JWT aan een ContextVar; alle downstream queries zijn automatisch gescopeerd via de ORM-hook (ADR-004) |
| CC6.6 | Encryption in transit | `access_token` en `refresh_token` worden opgeslagen als `httpOnly; Secure; SameSite=Lax` cookies; HTTPS afgedwongen door Traefik (ADR-009); tokens staan nooit in URL query parameters bij HTTP flows |
| CC6.7 | Restrictions on unauthorized access | Spoofing via `X-Tenant-ID` header expliciet afgewezen; URL-gebaseerde tenant-overrides afgewezen; WebSocket handshake valideert JWT volledig vóór sessie-opbouw |

### Bekende implementatiebug (P0-9) — vastgesteld 2026-05-28

**Bestand:** `src/core/shared/config.py:56` en `src/core/shared/interfaces.py:385`

**Probleem:** `database_url` heeft een SQLite default. Als `DATABASE_URL` env var niet gezet
is, start de backend op SQLite. Alle PostgreSQL RLS-policies (ADR-005) bestaan niet in SQLite.
Tenant A kan de data van Tenant B lezen — dit ADR is dan volledig omzeild.

**Vereiste fix:**
```python
# FOUT (huidige code):
database_url: str = Field(default="sqlite:///./sanskriti_setu.db")

# GOED:
database_url: str = Field(default="")

@validator("database_url", pre=True, always=True)
def require_postgres_url(cls, v: str) -> str:
    if not v:
        raise ValueError("DATABASE_URL is required.")
    if v.startswith("sqlite"):
        raise ValueError("SQLite is not supported. Multi-tenant RLS requires PostgreSQL.")
    return v
```

Fix verplicht voor P0. Tijdsinschatting 1-2u. Volledig fix-plan:
`docs/frontend/pages/22-platform-p0-blockers-scope.md` (P0-9).

---

### Bekende implementatiebug (P0-1) — vastgesteld 2026-05-28

**Bestand:** `src/core/api/auth/router.py:165`

**Probleem:** De registratie-flow bevat een hardcoded fallback `tenant_id = 1` (of equivalent).
Gebruikers zonder `tenant_id` in hun JWT worden stilzwijgend aan tenant 1 gekoppeld. Alle
multi-tenant functionaliteit is hierdoor geblokkeerd.

**Vereiste fix:**
```python
# FOUT (huidige code):
tenant_id = payload.get("tenant_id", 1)

# GOED:
tenant = await tenant_service.get_by_slug(db, slug=org_slug)
if not tenant:
    raise HTTPException(status_code=400, detail="Unknown organisation slug")
tenant_id = tenant.id
```

Gebruik `src/core/services/tenant_service.py:get_by_slug()`. Dit is P0 — implementeer
als eerste in het fixplan (zie `docs/frontend/pages/22-platform-p0-blockers-scope.md`).

---

## Implementatie-bevinding -- L3 Wiring Audit 2026-06-01

### CG-007 [HIGH] Drie onafhankelijke JWT-verificatiepaden -- potentieel auth bypass

**Situatie:** ADR-003 stelt dat JWT-verificatie geunificeerd is via `jwt_handler.verify_token()`.
**Werkelijkheid:** Drie onafhankelijke verificatiepaden bestaan naast elkaar:

1. `jwt_handler.verify_token()` -- gebruikt door `TenantMiddleware` en `auth/dependencies.py`
2. `security_manager.verify_token()` -- gebruikt door `SecurityMiddleware` (`src/core/security/security_middleware.py`)
3. Eventuele interne token-checks in specifieke endpoint-dependencies

Deze paden kunnen verschillende algorithm-allowlists, expiry-handling of claim-validatielogica
hebben. Een token die door pad 2 wordt geaccepteerd maar door pad 1 wordt afgewezen (of
omgekeerd) creëert een authentication bypass vector.

**Bewijs:** `src/core/security/security_middleware.py` (eigen `verify_token` implementatie),
`src/core/auth/jwt_handler.py` (centrale implementatie), `src/core/middleware/tenant_middleware.py`
(roept jwt_handler aan).
**Impact:** Aanvaller kan een token craften die SecurityMiddleware accepteert maar TenantMiddleware
afwijst -- of omgekeerd -- waardoor eindpunten zonder tenant-context of met verhoogde privileges
bereikt kunnen worden.
**Fix:** Unificeer alle JWT-verificatie naar uitsluitend `jwt_handler.verify_token()`.
Refactor `SecurityMiddleware` om `jwt_handler.verify_token()` aan te roepen i.p.v. eigen logica.
Documenteer dit als het enige geldige pad per CLAUDE.md §13.
**Sprint:** SP-WE-13 (te plannen, P1 security)

---

### Open gaps richting volledige SOC 2 Type I readiness

- Geen geautomatiseerd kwartaallijks access review proces gedocumenteerd — wie heeft nog een geldig actief account wordt niet periodiek getoetst
- MFA enforcement is niet aantoonbaar gemaakt als bewijs — instelling in GitHub org en Azure AD settings dienen te worden gedocumenteerd als auditeerbaar bewijsartefact
- **CG-007 (nieuw 2026-06-01):** Drie JWT-verificatiepaden -- fix vereist voor SOC 2 CC6.1 (logical access) en CC6.6 (authentication controls)
