# Review: BE-FLW-056 — Websocket-authenticatieflow

| Veld | Waarde |
| --- | --- |
| Spec | `docs/backend/features/BE-SEC-042-websocket-no-query-token.md` (gedeelde spec) |
| Uitkomst | **APPROVED** |
| Datum | 2026-07-31 |

BE-FLW-056 is de flow-ID van feature BE-SEC-042 en heeft geen eigen spec. De volledige
review staat in [`review-BE-SEC-042.md`](review-BE-SEC-042.md).

Dit bestand bestaat omdat `scripts/validate_feature_docs.py` de review-check uitvoert op
het alfabetisch eerste ID per gedeelde spec: `BE-FLW-056` sorteert voor `BE-SEC-042`.

Flow zoals gereviewd:

```text
client opent websocket (geen token in de URL)
  -> WebSocketAuthenticator.extract_token():
       1. access_token-cookie (canoniek)
       2. Sec-WebSocket-Protocol subprotocol
       3. Authorization: Bearer
  -> jwt_handler.verify_token()
  -> tenant-context zetten
  -> connected-frame met user_id + tenant_id
```

Foutpaden: geen token -> sluiten met 4001 of HTTP 401 (per endpoint); ongeldig token ->
4003. Een token in de query string wordt niet gelezen en geeft dus hetzelfde resultaat als
geen token.
