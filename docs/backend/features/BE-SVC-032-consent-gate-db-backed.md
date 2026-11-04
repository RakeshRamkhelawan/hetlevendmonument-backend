# BE-SVC-032 -- ConsentGate DB-backed implementatie (SP-WE-03)

**ID:** BE-SVC-032
**Sprint:** SP-WE-03
**Datum:** 2026-05-31
**ADR:** ADR-026

---

## Samenvatting

`_ConsentGateAdapter.has_consent()` retourneerde altijd `True` ongeacht werkelijke consent
(WE-017). Dit was een GDPR-schending: het GDPR opt-in model vereist dat cross-session memory
standaard uitgeschakeld is (SP-C01-B). De adapter is nu async en leest echte consent uit
`TwinConsentManager.get_consent_categories()`.

## Wijzigingen

| Bestand | Wijziging |
| --- | --- |
| `src/core/copilot/council/members/privacy_officer.py` | `ConsentGate.has_consent` protocol: sync -> async; parameter `consent_type: str` -> `tenant_id: int` |
| `src/core/copilot/council/members/privacy_officer.py` | `_deliberate_inner()` lijn 147: `await self._consent_gate.has_consent(proposal.user_id, proposal.tenant_id)` |
| `src/core/copilot/council/factory.py` | `_ConsentGateAdapter`: nieuw `__init__(consent_manager)` + async `has_consent`; fail-secure `return False` bij exception |
| `src/core/copilot/council/factory.py` | `build_council()`: `TwinConsentManager(db=db, cache=redis)` aangemaakt en doorgegeven aan `_ConsentGateAdapter` |

## Veiligheidsgaranties

- `tenant_id is None` + exception beide -> `return False` (fail-secure, geen PII in logs)
- `TwinConsentManager.get_consent_categories().cross_session_memory` is de bron van waarheid
- Standaard `cross_session_memory=False` per SP-C01-B (opt-in model)

## Trainingssamenvatting

### Flow 1: GDPR consent gate blokkeert twin data

- **Actor:** PrivacyOfficer (council lid)
- **Voorwaarde:** DeliberationContext ontvangen met twin_profile aanwezig (niet None)
- **Actie:** `_deliberate_inner()` controleert `context.twin_profile is not None`; roept `await consent_gate.has_consent(user_id, tenant_id)` aan
- **Systeemreactie:** `_ConsentGateAdapter` vraagt `TwinConsentManager.get_consent_categories()`; retourneert `categories.cross_session_memory`
- **Succesrespons:** consent=True -> twin data mag gebruikt worden; PrivacyOfficer APPROVE
- **Foutrespons:** consent=False -> VETO met reason_code MISSING_TWIN_CONSENT
- **Uitzonderingen:** DB exception of tenant_id=None -> fail-secure `False` -> VETO; twin_profile=None -> consent check overgeslagen -> APPROVE
