# BE-SVC-039: CVA GDPR/AI Act Compliance Bundle (SP-CVA-COMP)

## Metadata

| Veld | Waarde |
|------|--------|
| ID | BE-SVC-039 |
| Sprint | SP-CVA-COMP Dag 1 |
| Datum | 2026-06-20 |
| Status | APPROVED |

## Scope

7 compliance-items (GDPR Art. 6/17, AI Act Art. 13, ADR-019, ADR-033) gerealiseerd in 1 sprintdag.

## Gewijzigde bestanden

### Backend

| Bestand | Wijziging |
|---------|-----------|
| `src/core/services/cva_service.py` | Fix A+B+D+pre-existing bug |
| `src/core/governance/retention_cleanup.py` | Fix C |

### Frontend

| Bestand | Wijziging |
|---------|-----------|
| `frontend/src/lib/hooks/useExplainability.ts` | Fix E |
| `frontend/src/components/copilot/PersonalizationConsentBanner.tsx` | Fix F (nieuw) |
| `frontend/src/components/layout/CopilotSidebar.tsx` | Fix F |

### Tests

| Bestand | Dekt |
|---------|------|
| `tests/unit/test_sp_cva_comp_metadata.py` | Fix A: personalization_consent_status |
| `tests/unit/test_sp_cva_comp_memory_consent.py` | Fix B: memory write consent-skip |
| `tests/unit/governance/test_sp_cva_comp_retention.py` | Fix C: retention tables+categories |
| `tests/unit/test_sp_cva_comp_audit.py` | Fix D: audit trail |
| `frontend/src/components/copilot/__tests__/PersonalizationConsentBanner.test.tsx` | Fix F: banner |

## Fix-details

### Fix A -- COMP-001: personalization_consent_status in metadata (GDPR Art. 6)

`CVAService.chat()` retourneert nu `metadata.personalization_consent_status = "granted" | "required"`.
Frontend kan hierop een consent-banner tonen. Chat zelf werkt altijd (Art. 6(1)(b) contract).

### Fix B -- COMP-002/007: consent-skip in _write_memory_candidate() (GDPR Art. 6)

`_write_memory_candidate()` checkt nu `CookieConsentManager.is_consent_given(..., PERSONALIZATION)`
VOOR het schrijven. Geen consent: early return met INFO log. Consent: schrijft door.
Grondslag: Art. 6(1)(a) toestemming vereist voor episodisch geheugen.

### Fix C -- COMP-003: CVA conversations in retention_cleanup (GDPR Art. 17)

`DataCategory` uitgebreid met `CVA_CONVERSATION`, `CVA_MESSAGE`, `CVA_SESSION`.
`_RETENTION_ALLOWED_TABLES` uitgebreid met `conversations`, `conversation_messages`, `cva_conversations`.
`_get_table_info()` bevat nu 3 nieuwe mappings voor CVA-tabellen.

### Fix D -- COMP-006: CVA audit trail + pre-existing bug (ADR-019)

Pre-existing bug gefixed: `hard_delete_conversation()` gebruikte `resource_type`/`resource_id` (niet-bestaande
AuditLog-velden) en `user_id=str(user_id)` (type-fout). Gecorrigeerd naar `resource=f"conversation:{id}"` en
`user_id=user_id` (int).

`CVAService.chat()` maakt nu een `AuditLog` aan via `best_effort` (ADR-019 hash chain).
Audit-fout blokkeert nooit de chat response.

### Fix E -- COMP-004: generateMockExplainability verwijderd (AI Act Art. 13)

`generateMockExplainability()` export verwijderd uit `useExplainability.ts`.
Geen callers. TSC exit 0 bevestigt.

### Fix F -- Frontend consent banner (COMP-001 completering)

Nieuwe component `PersonalizationConsentBanner` toont niet-blokkerend boven het inputveld wanneer
PERSONALIZATION consent ontbreekt. "Enable" roept `updateConsent({preferences:{personalization:true}, policy_version})` aan.
"Skip" dismisst voor de sessie. Netwerk-fouten zijn stil (chat blijft werken).
`CopilotSidebar` checkt consent via `useEffect` bij openen.

## Test-resultaten

| Suite | Resultaat |
|-------|-----------|
| Backend COMP-tests (14) | 14/14 PASS |
| Backend governance-suite (573) | 573/573 PASS |
| Frontend banner-tests (5) | 5/5 PASS |
| `python -m pyright` | 0 errors |
| `npx tsc --noEmit` | exit 0 |
| `alembic heads` | 1 head (geen migraties) |


## Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker of agent
- Voorwaarde: SP-CVA-COMP Dag 1: GDPR Art.6/17 + AI Act Art.13 compliance bundle. Fix A+B: personalization_consent_status + memory write consent-skip. Fix C: CVA tables in retention_cleanup. Fix D: audit trail + pre-existing resource bug. Fix E: generateMockExplainability verwijderd. Fix F: PersonalizationConsentBanner + CopilotSidebar integratie. 14/14 BE + 5/5 FE tests PASS. is beschikbaar en correct geconfigureerd.
- Actie: Geauthenticeerde gebruiker of agent start of gebruikt SP-CVA-COMP Dag 1: GDPR Art.6/17 + AI Act Art.13 compliance bundle. Fix A+B: personalization_consent_status + memory write consent-skip. Fix C: CVA tables in retention_cleanup. Fix D: audit trail + pre-existing resource bug. Fix E: generateMockExplainability verwijderd. Fix F: PersonalizationConsentBanner + CopilotSidebar integratie. 14/14 BE + 5/5 FE tests PASS..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
