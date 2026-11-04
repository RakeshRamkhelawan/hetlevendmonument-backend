# BE-GOV-009: SP-DLP-002 Dag 2 -- LawfulBasisRegistry API Lifecycle Wiring

**Sprint:** SP-DLP-002 -- DLP Compliance Completeness Sprint  
**Dag:** 2 van 4  
**Datum:** 2026-06-26  
**Status:** DONE  
**ADR:** ADR-003 (JWT tenant identity), GDPR Art. 6

---

## Probleemstelling

GDPR-001 audit bevinding: `LawfulBasisRegistry.validate_endpoint_access()` werd nooit aangeroepen
in API routes. GDPR Art. 6 (rechtmatige grondslag voor verwerking) was daarmee niet gehandhaafd.

---

## Implementatie

### Nieuw bestand: `src/core/governance/dependencies.py`

Pre-geconfigureerde `LawfulBasisRegistry` singleton als FastAPI Depends factory.
Registreert 4 endpoints met hun GDPR Art. 6 grondslag:

| Endpoint | Grondslag | GDPR basis |
|----------|-----------|-----------|
| `/api/v1/privacy/consent-status` | CONSENT | Art. 6(1)(a) |
| `/api/v1/privacy/consent` | CONSENT | Art. 6(1)(a) |
| `/api/gdpr/export` | CONTRACT | Art. 6(1)(b) |
| `/api/gdpr/audit-trail` | LEGAL_OBLIGATION | Art. 6(1)(c) |

### Facade re-exports (ADR-033 compliant)

- `src/core/api/v1/privacy/dependencies.py`: re-exporteert `LawfulBasisRegistry`, `LawfulBasisMissingError`, `get_lawful_basis_registry`
- `src/core/api/v1/gdpr_compliance/dependencies.py`: zelfde re-exports
- `.importlinter`: 4 nieuwe `ignore_imports` entries toegevoegd

### Wiring in routers

Elke handler krijgt `registry: LawfulBasisRegistry = Depends(get_lawful_basis_registry)`.
De call is **non-blocking** (Dag 2 strategie): `LawfulBasisMissingError` wordt gelogd als warning
maar blokkeert niet. Hard blocking volgt in SP-DLP-003 wanneer de registry volledig gecalibreerd is.

Gevangen: alleen `LawfulBasisMissingError` (specifiek), geen breed `except Exception`.
`exc_info=True` aanwezig in alle warning calls conform backend-patterns.md regel 10.

Gewijzigde routers:
- `src/core/api/v1/privacy/consent_router.py` (`get_consent_status`, `update_consent`)
- `src/core/api/v1/gdpr_compliance/portability_router.py` (`export_tenant_data`)
- `src/core/api/v1/gdpr_compliance/access_router.py` (`audit_trail`)

---

## Tests

**Testbestand:** `tests/unit/governance/test_lawful_basis_wiring.py`

| Test | Beschrijving |
|------|-------------|
| `test_consent_router_calls_lawful_basis_validation` | consent_router bevat LawfulBasisRegistry aanroep |
| `test_portability_router_calls_lawful_basis_validation` | portability_router bevat LawfulBasisRegistry aanroep |
| `test_access_router_calls_lawful_basis_validation` | access_router bevat LawfulBasisRegistry aanroep |
| `test_governance_dependencies_module_exists` | governance/dependencies.py bestaat |

Resultaat: 4/4 GREEN (eerst RED, dan GREEN na implementatie).

---

## Kwaliteit

- `python -m pyright`: 0 errors (baseline gehandhaafd)
- `ruff check`: All checks passed
- 579 governance unit tests: 0 failures


## Trainingssamenvatting

- Actor: Backend service of ontwikkelaar
- Voorwaarde: SP-DLP-002 Dag 2: LawfulBasisRegistry API wiring (GDPR-001) -- governance/dependencies.py factory, re-exports in privacy+gdpr\_compliance facades, non-blocking Depends in consent\_router+portability\_router+access\_router. 4 nieuwe importlinter entries. 4 TDD tests GROEN. pyright 0 errors. is beschikbaar en correct geconfigureerd.
- Actie: Backend service of ontwikkelaar start of gebruikt SP-DLP-002 Dag 2: LawfulBasisRegistry API wiring (GDPR-001) -- governance/dependencies.py factory, re-exports in privacy+gdpr\_compliance facades, non-blocking Depends in consent\_router+portability\_router+access\_router. 4 nieuwe importlinter entries. 4 TDD tests GROEN. pyright 0 errors..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
