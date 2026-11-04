# BE-GOV-012: LawfulBasisRegistry Hard-Blocking (GDPR-001 fase 2)

**Sprint:** SP-DLP-003 Dag 1
**Status:** APPROVED
**Datum:** 2026-06-26

## Probleem

`LawfulBasisMissingError` werd alleen gelogd (warning, non-blocking). Endpoints verwerkte
persoonsgegevens door ondanks een ontbrekende GDPR Art. 6 lawful basis. GDPR-001 fase 2 vereist
hard-blocking: verwerking gestopt bij onbekende lawful basis.

## Implementatie

4 except-blokken in 3 Laag-1 router-bestanden gewijzigd van warning-only naar blocking 451:

| Bestand | Handler | Endpoint |
|---------|---------|----------|
| `src/core/api/v1/privacy/consent_router.py` | `get_consent_status` | `/api/v1/privacy/consent-status` |
| `src/core/api/v1/privacy/consent_router.py` | `update_consent` | `/api/v1/privacy/consent` |
| `src/core/api/v1/gdpr_compliance/portability_router.py` | `export_tenant_data` | `/api/gdpr/export` |
| `src/core/api/v1/gdpr_compliance/access_router.py` | `audit_trail` | `/api/gdpr/audit-trail` |

Patroon (identiek voor alle 4):
```python
except LawfulBasisMissingError as e:
    logger.error(
        "LawfulBasis hard-blocked (GDPR Art. 6): %s: %s", type(e).__name__, e, exc_info=True
    )
    raise HTTPException(
        status_code=451,
        detail="Data processing is not authorized for this endpoint",
    ) from e
```

HTTP 451 (RFC 7725 Unavailable For Legal Reasons) is het correcte statuscodefor GDPR-blokkering.

## Tests

`tests/unit/governance/test_lawful_basis_hard_blocking.py` -- 3 tests, regex-proximity check:
verifieert dat `raise HTTPException(status_code=451)` aaneengesloten zit aan
`except LawfulBasisMissingError` in elk bestand.

## ADR-compliance

- ADR-033: routers importeren `LawfulBasisMissingError` via `.dependencies` facade (geen directe
  governance-import) -- compliant.
- GDPR Art. 6: verwerking zonder lawful basis nu onmogelijk voor alle 4 endpoints.


## Trainingssamenvatting

- Actor: Backend service of ontwikkelaar
- Voorwaarde: SP-DLP-003 Dag 1: LawfulBasisRegistry hard-blocking (GDPR-001 fase 2) -- 4 except-blokken in 3 routers van logger.warning naar logger.error + HTTPException(451). 3 TDD tests GROEN (regex-proximity). pyright 0 errors. ruff clean. is beschikbaar en correct geconfigureerd.
- Actie: Backend service of ontwikkelaar start of gebruikt SP-DLP-003 Dag 1: LawfulBasisRegistry hard-blocking (GDPR-001 fase 2) -- 4 except-blokken in 3 routers van logger.warning naar logger.error + HTTPException(451). 3 TDD tests GROEN (regex-proximity). pyright 0 errors. ruff clean..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
