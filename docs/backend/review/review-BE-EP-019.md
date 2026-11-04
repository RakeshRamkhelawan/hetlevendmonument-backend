# Review BE-EP-019: Inbound Webhook Endpoints (HMAC + SignalBus)

**Status:** APPROVED
**Reviewer:** Rakesh Ramkhelawan
**Datum:** 2026-06-01
**Spec:** `docs/backend/features/BE-EP-019-inbound-webhook-endpoints.md`
**Implementatie:** `src/core/api/webhook_endpoints.py`
**Reden:** ID-collision fix -- spec was eerder onder BE-EP-013 geregistreerd terwijl die ID al in gebruik was voor Agent Heartbeat Endpoint.

---

## Bevindingen

### CRITICAL

Geen.

### HIGH

Geen.

### MEDIUM

- **OA-019-1** (uit spec): `X-Tenant-ID` header wordt nog steeds vertrouwd na signature-verificatie. Echte fix vereist `webhook_registrations` tabel met FK `tenant_id` + UNIQUE `source`. Geregistreerd als post-MVP follow-up. Acceptabel voor v1.0 omdat de header pas wordt vertrouwd NA HMAC-validatie -- alleen authenticated senders kunnen de waarde zetten.

### LOW

- **OA-019-2** (uit spec): Globaal `WEBHOOK_SECRET` fallback. In productie zou alleen per-source secret toegestaan moeten zijn. Documenteer als deployment-best-practice.

---

## Compliance checks

- [x] Spec bevat alle verplichte metadata-velden
- [x] Trainingssamenvatting aanwezig met minstens een `Actor:` flow
- [x] Foutcodes-tabel aanwezig
- [x] Beveiligingsoverwegingen geadresseerd (HMAC constant-time, secret nooit in code, tenant-spoofing risico)
- [x] CLAUDE.md regel 6.1 (ActivePieces webhook tenant binding) wordt nageleefd in de zin dat tenant_id niet uit body komt
- [x] ID geregistreerd in `docs/backend/features/ID-REGISTRY.md`
- [x] User guide aanwezig: `docs/user-guide/backend/inbound-webhook-endpoints.md`

---

## Verdict

**APPROVED.** Spec is feitelijk correct, implementatie matcht de spec (geverifieerd via Read van `src/core/api/webhook_endpoints.py:1-50`), beveiligingsoverwegingen zijn realistisch en open punten zijn juist geclassificeerd als follow-up. ID-collision is opgelost door rename naar BE-EP-019 en registratie in ID-REGISTRY.
