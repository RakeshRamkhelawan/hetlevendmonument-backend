# Backend Feature Specification

## Metadata

- Feature ID: BE-EP-019
- Feature naam: Inbound Webhook Endpoints (HMAC + SignalBus)
- Status: ACTIEF
- Auteur: Rakesh Ramkhelawan
- Reviewer: --
- Datum: 2026-06-01
- Gerelateerde user story / ticket: ID-collision fix (was BE-EP-013, conflict met Agent Heartbeat Endpoint)
- Gerelateerde router / module: `src/core/api/webhook_endpoints.py`
- Gerelateerde frontend endpoints: geen (server-to-server)
- Gerelateerde database tabellen: geen (publiceert naar SignalBus / Redis)
- Versie: 1.0

---

## Doel en scope

`POST /webhooks/inbound/{source}` ontvangt externe webhook-events, verifieert de HMAC-SHA256-signature en publiceert een genormaliseerd `Signal` op de SignalBus (Redis pub/sub) voor downstream verwerking door agents en monitors.

In scope: HMAC-validatie via `X-Webhook-Signature` header, per-source secret-lookup uit env vars, signature-first dan tenant-id-extractie, SignalBus publish, 202 Accepted bij succes.

Out of scope: webhook-registratietabel (`webhook_registrations` voor per-source tenant_id binding) -- post-MVP follow-up.

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging |
|---|---|---|---|---|
| BE-EP-019 | `POST /webhooks/inbound/{source}` | BE-EP | `src/core/api/webhook_endpoints.py` | Bestaand (ID-collision fix) |

---

## API-flow

### BE-FLW-019: Inbound webhook signature-verify + SignalBus publish

- **Trigger:** Externe service POSTt naar `/webhooks/inbound/{source}` met JSON body en `X-Webhook-Signature` header.
- **Beschrijving:** Backend zoekt het HMAC-secret op via env var `WEBHOOK_SECRET_{SOURCE}` (uppercased, koppeltekens -> underscores) met fallback `WEBHOOK_SECRET`. Bij ontbrekende config retourneer 503. Vergelijk signature constant-time. Bij mismatch 401. Bij geldig: extraheer `event_type` + `data` uit body, leid `tenant_id` af uit `X-Tenant-ID` header (alleen vertrouwd NA signature-verificatie), maak `Signal(tier, source, event_type, data, tenant_id)` en publish naar SignalBus. Respons 202 met `{"accepted": true}`.

---

## Foutcodes

| Situatie | HTTP-status | Body |
|---|---|---|
| Geen secret geconfigureerd voor source | 503 | `{"detail": "Webhook source not configured"}` |
| Signature ontbreekt of klopt niet | 401 | `{"detail": "Invalid webhook signature"}` |
| Body geen geldige JSON of mist verplichte velden | 422 | Pydantic validation error |
| Succes | 202 | `{"accepted": true}` |

---

## Trainingssamenvatting

### Flow: Inbound webhook met geldige signature

- **Actor:** Externe service (bijv. payment provider, CRM, automation platform)
- **Voorwaarde:** Env var `WEBHOOK_SECRET_{SOURCE}` (of `WEBHOOK_SECRET`) is geconfigureerd op backend; sender heeft hetzelfde secret en heeft de juiste body al gesigneerd.
- **Actie:** Sender doet `POST /webhooks/inbound/payment-stripe` met JSON body `{"event_type": "invoice.paid", "data": {...}}` en header `X-Webhook-Signature: <hex hmac-sha256>`.
- **Systeemreactie:** Backend leest body, berekent verwachte HMAC met `webhook_secret`, vergelijkt constant-time. Bij match: leidt `tenant_id` af, maakt `Signal` en publish naar Redis pub/sub kanaal. Logt audit-entry met source + event_type (geen body).
- **Succesrespons:** HTTP 202 Accepted met body `{"accepted": true}`. Downstream agents/monitors ontvangen het Signal asynchroon.
- **Foutrespons:**
  - 503 als `WEBHOOK_SECRET_{SOURCE}` niet bestaat (config-fout).
  - 401 als signature ontbreekt of niet matcht (auth-fout, geen retry zinvol).
  - 422 als body niet voldoet aan `InboundWebhookPayload` schema (sender bug).
- **Uitzonderingen:** Bij Redis-publish failure: backend retourneert 202 (event is geverifieerd) maar logt `signal_publish_failed`. Sender mag NIET opnieuw versturen -- anders dubbele verwerking bij latere Redis-recovery.

---

## Beveiligingsoverwegingen

- **HMAC-SHA256 constant-time vergelijk** via `hmac.compare_digest()` -- geen timing oracle.
- **Secret NOOIT in code** -- uitsluitend env vars; logregels mogen het secret of de body niet bevatten.
- **`X-Tenant-ID` alleen vertrouwd NA signature-verificatie** -- anders cross-tenant spoofing. Echte fix (per-source tenant binding via `webhook_registrations` tabel) is post-MVP.
- **Geen tenant_id uit JWT** want webhooks zijn server-to-server, niet user-driven.

---

## Open punten

| ID | Type | Beschrijving | Prioriteit |
|---|---|---|---|
| OA-019-1 | Risico | `X-Tenant-ID` header wordt nog steeds als bron gebruikt na signature-verify. Migreer naar `webhook_registrations` tabel met FK `tenant_id` en `source` UNIQUE. | Middel |
| OA-019-2 | Aanname | Een globaal `WEBHOOK_SECRET` fallback bestaat. In productie zou alleen per-source secrets toegelaten moeten zijn. | Laag |
