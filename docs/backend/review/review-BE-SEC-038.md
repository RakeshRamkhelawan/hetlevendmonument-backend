# Review -- BE-SEC-038 (Copilot WebSocket hardening)

> Reviewers: Gate-2 code-reviewer + security-reviewer (subagents)
> Datum: 2026-07-10
> Spec: `docs/backend/features/BE-SEC-038-copilot-websocket-hardening.md`
> Diff: commits `3df9424a` + `df59e80c` + `a1c82fb0` op `iter/ws-hardening`

## Eindoordeel

**APPROVED**

Beide reviewers hebben de vijf fixes geverifieerd tegen het HTTP-pad (`turn_endpoint.py`)
en `service.py`. De code-reviewer gaf initieel CHANGES_REQUESTED op MINOR-niveau; die minors
zijn gefixt (commit `a1c82fb0`). De security-reviewer gaf APPROVED. Geen BLOCKERs.

## Geverifieerd

- SEC-AGT-001 PromptGuard: identieke `sanitize`-aanroep als HTTP; injectie geweigerd voor opslag/stream.
- SEC-AGT-002 single-execution: `handle_turn_stream` draait de turn exact 1x; de tweede `handle_turn`
  is weg. Reeel opgeloste dubbele-uitvoering-bug (muterende acties werden dubbel uitgevoerd).
- SEC-AGT-003 rate limit: `check_copilot_turn_limit` gebruikt exact dezelfde key/backends als de
  HTTP-decorator; blokkeert voor executie; key op tenant+user uit JWT, nooit header.
- SEC-AGT-004 token: `?token=` verwijderd; geen token in logs; cookie/subprotocol/header behouden.
  Blast-radius gecheckt: primaire copilot-WS + FlowStatus op cookie-auth; FocusModeBuilder-URL-token
  verwijderd in dezelfde pass.
- TI-112 tenant-cleanup: `clear_tenant_context()` in `finally` en op beide early-return foutpaden.

## Opgeloste review-bevindingen (commit a1c82fb0)

| Severity | Bevinding | Status |
| --- | --- | --- |
| MINOR (code-reviewer) | Tenant-context lekte op de twee early-return foutpaden (db-not-ready, service-build-fail) | Gefixt + test toegevoegd |
| MINOR (beide) | Verouderde module-docstring ("query fallback") | Gefixt |
| MINOR (security) | `FocusModeBuilder.tsx` bouwde nog `?token=` in de WS-URL | Gefixt (cookie-auth) |
| MINOR (security) | Tests bewezen non-executie via `handle_turn` i.p.v. `handle_turn_stream` | Versterkt (spy op `handle_turn_stream`) |
| INFO (code-reviewer) | Rate-limit staat na PromptGuard (HTTP: ervoor) | Bewust; injectie wordt altijd geweigerd, geen LLM-kosten |

## Release-oordeel

- Geschikt voor implementatie: ja (geimplementeerd, tests groen).
- Geschikt voor QA: ja (`tests/unit/copilot/api/test_ws_hardening.py` + auth-tests).
- Gate 3: ruff 0, pyright 0 (expliciet op de gewijzigde bestanden).

Geen CRITICAL of HIGH open.
