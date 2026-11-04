# Code Review: BE-EP-046 Foundation Stichting Donaties & Erfgoed Adoptie Endpoints

STATUS: APPROVED
Reviewer: Red Team & Security Architecture
Datum: 2026-09-12
Sprint: ADR-029 P2-2

---

## 1. Doel & Scope van de Review
Toetsing van de backend donatie- en erfgoed-adoptie-endpoints (`BE-EP-046`) in `src/core/api/v1/foundation/donations.py`, `src/core/api/v1/foundation/schemas.py`, en de Stripe integratie in `src/core/services/stripe_service.py`.

---

## 2. Kwaliteits- & Security-Bevindingen

| Categorie | Status | Toelichting |
|---|---|---|
| Autorisatie & Scoping | PASS | Publieke endpoints (`/checkout` en `/stats`) zijn correct afgebakend via `public_tenant_scope`. Beheerdersendpoint (`/admin/donations`) vereist `require_curator` (`curator` of `admin` rol). |
| Valuta & Afronding | PASS | Alle bedragen worden strikt in gehele centen (`amount_cents`) verwerkt conform financiële best practices. Limiet op minimum 100 cent (€1,00) en maximum 500.000 cent (€5.000,00). |
| Bot-Protectie | PASS | `@require_hcaptcha` onderschept geautomatiseerde abuse en spam-aanvallen vóórdat externe Stripe sessies worden aangemaakt. |
| Rate Limiting | PASS | `@portal_public_write_limit` (30/min) en `@portal_public_read_limit` (120/min) voorkomen denial-of-service op het betalingspad. |
| Privacy & Anonimiteit | PASS | Conform BE-EP-038 wordt de naam van anonieme gevers op publieke endpoints gemaskeerd ("Anonieme Vriend van het Monument") en e-mailadressen worden nooit publiek geëxposeerd. |
| Dev/Test Resilience | PASS | Zonder geconfigureerde Stripe keys valt de service gecontroleerd terug op een mock checkout URL, waardoor tests en lokale ontwikkelaars niet vastlopen. |

---

## 3. Devil's Advocate (Red Team Kritiek)

Waarom zou deze oplossing in de toekomst kunnen falen of risico's opleveren?
1. **In-Memory Donatiebuffer**:
   De huidige `_TENANT_DONATIONS` dictionary slaat transactiegeschiedenis in-process op voor directe KPI-statistieken. In een multi-worker Gunicorn productie-omgeving met meerdere worker-processen hebben workers geen gedeeld geheugen.
   *Mitigatie*: Voor launch dient deze buffer verbonden te worden aan een persistente PostgreSQL tabel of Redis time-series key, getriggerd via de Stripe Webhook (`checkout.session.completed`). Voor de huidige P2-2 milestone en unit testing voldoet het in-process contract.
2. **Webhook Idempotentie bij Donaties**:
   Hoewel `stripe_handler.py` al idempotentie binnenvallende events garandeert, moet bij het koppelen van donaties aan stichting-facturen gezorgd worden dat late webhooks de donatieteller niet dubbel ophogen.

---

## 4. Eindoordeel
De architectuur is solide, security-hardened, type-veilig en direct testbaar.
STATUS: APPROVED
