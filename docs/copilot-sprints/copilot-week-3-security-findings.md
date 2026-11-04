# Sprint 3 Dag 4 - Security Findings Rapport

**Datum:** 2026-05-23
**Auditor:** code-review-subagent, security-review-subagent, red-team-subagent (parallel)
**Scope:** src/core/copilot/**/*.py

## Samenvatting

| Severity | Count | Closed | Open |
|----------|-------|--------|------|
| CRITICAL | 0    | 0      | 0    |
| HIGH     | 3    | 0      | 3    |
| MEDIUM   | 5    | 0      | 5    |
| LOW      | 3    | 0      | 3    |

**Noot:** De initiele bevinding F-001 (_fail_secure_decision hash="FAILED") is na analyse
afgewezen als false-positive. De fail-secure decision wordt NOOIT naar persist() doorgegeven;
hij wordt direct geretourneerd aan de caller na een exception in deliberate().

## HIGH findings (open)

### F-002: Hash chain integrity check is dead code in normale flow
- **Bestand:** `src/core/copilot/council/audit_writer.py:117-142`
- **Bron:** code-review-subagent
- **Beschrijving:** AuditOfficer creeert CouncilDecision met `previous_decision_hash=None`.
  De integrity check in `persist()` vereist dat `decision.previous_decision_hash is not None`
  om te firen. Daardoor wordt de check NOOIT uitgevoerd in de normale flow. Tampering wordt
  alleen gedetecteerd door de periodieke `verify_chain` scan, niet real-time.
- **Attack-vector:** Een aanvaller die een decision uit de DB verwijdert, wordt niet
  real-time gedetecteerd. De volgende legitimate decision krijgt gewoon een nieuwe
  previous_hash (de nieuwe "laatste" decision) en de chain lijkt intact.
- **Fix:** Laat AuditOfficer de previous_hash opvragen en meegeven aan persist(),
  zodat de integrity check onder de lock altijd firet.
- **Regression test:** `test_f002_hash_chain_integrity_check_fires_on_normal_flow`

### F-003: PromptGuard Unicode normalisatie onvolledig — homoglyph bypass
- **Bestand:** `src/core/copilot/council/members/security_officer.py:124-126`
- **Bron:** security-review-subagent + red-team-subagent
- **Beschrijving:** SecurityOfficer normaliseert met NFKC en vervangt alleen Cyrillic 'а'
  (U+0430). Andere homoglyphs worden NIET vervangen: Greek 'α' (U+03B1), Cyrillic 'е'
  (U+0435), 'о' (U+043E), 'р' (U+0440), 'с' (U+0441), 'х' (U+0445), 'і' (U+0456),
  'ј' (U+0458), etc. Een aanvaller kan prompt injection verbergen door ASCII letters te
  vervangen door lookalikes die door de guard heen glippen.
- **Attack-vector:**
  ```
  reasoning = "ignore previo\u0435s instructions"  # Cyrillic е in plaats van e
  ```
  De string bevat `ignore previous instructions` visueel, maar de pattern-match ziet
  `ignore prеvious instructions` (met Cyrillic е) en mist de injection.
- **Fix:** Breid de homoglyph-map uit naar alle bekende Cyrillisch/Griekse lookalikes,
  of gebruik een dedicated library. Verifieer met regression test.
- **Regression test:** `test_f003_cyrillic_e_homoglyph_detected`

### F-004: OfficerVerdictRow query mist expliciete tenant_id filter
- **Bestand:** `src/core/copilot/api/audit_endpoints.py:250-255`
- **Bron:** security-review-subagent
- **Beschrijving:** `get_decision_explanation` filtert de `decision` wel op tenant_id,
  maar de `OfficerVerdictRow` query heeft geen `.where(tenant_id == ...)`.
  RLS policies beschermen dit waarschijnlijk, maar defense-in-depth vereist een
  expliciete filter. Bij een RLS misconfiguratie of bypass lekt dit verdict-data.
- **Attack-vector:** Als RLS uitgeschakeld is (bv. admin query, migratie, bug),
  returnt het endpoint verdicts van alle tenants bij een gekend decision_id.
- **Fix:** Voeg `.where(OfficerVerdictRow.tenant_id == tenant_id)` toe.
- **Regression test:** `test_f004_officer_verdicts_filtered_by_tenant_id`

## MEDIUM findings (deferred naar SPRINT_TRACKER)

### F-005: RiskOfficer gebruikt f-string in logger call
- **Bestand:** `src/core/copilot/council/members/risk_officer.py:164`
- **Beschrijving:** `logger.error(f"RiskOfficer error [tenant={...}]: {str(e)}", exc_info=True)`
  schendt CLAUDE.md regel 11 (gebruik `%s` formatting).
- **Owner:** @rakesh — target sprint: 5

### F-006: SecurityOfficer `_legacy_deliberate` dupliceert alle logica
- **Bestand:** `src/core/copilot/council/members/security_officer.py:219-321`
- **Beschrijving:** 100+ regels identieke code. Elke security-fix moet op 2 plekken.
- **Owner:** @rakesh — target sprint: 5

### F-007: `verify_chain` laadt ALLE decisions in geheugen — OOM risico
- **Bestand:** `src/core/copilot/api/audit_endpoints.py:82-99`
- **Beschrijving:** Geen LIMIT of pagination. Tenant met 100k+ decisions = OOM.
- **Owner:** @rakesh — target sprint: 5

### F-008: Circuit breaker is uitgecommentarieerd
- **Bestand:** `src/core/copilot/council/coordinator.py:80-101`
- **Beschrijving:** `self._circuit_breakers` is uitgecommentarieerd. Failing Officer
  wordt steeds opnieuw aangeroepen = cascading failure / DoS.
- **Owner:** @rakesh — target sprint: 5

### F-009: `action_params` wordt ruw als JSONB opgeslagen in audit log
- **Bestand:** `src/core/copilot/council/audit_writer.py:166`
- **Beschrijving:** Als action_params wachtwoorden, tokens of PII bevat, worden deze
  plaintext opgeslagen in de audit database. Er is geen redactie/scan.
- **Owner:** @rakesh — target sprint: 6

## LOW findings

### F-010: Hardcoded client_ip '0.0.0.0' in audit log insert
- **Bestand:** `src/core/copilot/api/audit_endpoints.py:265-268`
- **Beschrijving:** `client_ip` is hardcoded in plaats van `request.client.host`.

### F-011: `_build_context` heeft lege dicts
- **Bestand:** `src/core/copilot/council/coordinator.py:194-204`
- **Beschrijving:** `tenant_settings` en `user_preferences` zijn leeg. Officers hebben
  geen toegang tot tenant-specifieke policies.

### F-012: ComplianceOfficer en EthicsOfficer hebben ook `_legacy_deliberate` duplicatie
- **Bestand:** `compliance_officer.py`, `ethics_officer.py`
- **Beschrijving:** Zelfde patroon als F-006.
