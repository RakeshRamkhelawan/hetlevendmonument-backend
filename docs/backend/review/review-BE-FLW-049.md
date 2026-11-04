# Review: BE-FLW-049 — Council tool-allowlist check per agent-identiteit

| Veld | Waarde |
| --- | --- |
| Spec | `docs/backend/features/BE-SEC-041-council-tool-broker-agent-id.md` (gedeelde spec) |
| Uitkomst | **APPROVED** |
| Datum | 2026-07-31 (doc-gate gesloten; feature zelf gereviewd 2026-07-29) |

BE-FLW-049 is de flow-ID van feature BE-SEC-041 (ADR-036 Fase A dag 2, AUDIT-007) en
heeft geen eigen spec. De volledige review staat in
[`review-BE-SEC-041.md`](review-BE-SEC-041.md).

Dit bestand bestaat omdat `scripts/validate_feature_docs.py` de review-check uitvoert op
het alfabetisch eerste ID per gedeelde spec: `BE-FLW-049` sorteert voor `BE-SEC-041`.

Flow zoals gereviewd:

```text
achtergrondtaak vraagt Council-oordeel
  -> build_council(agent_id=<echte agent>)
  -> _ToolBrokerAdapter(agent_id=<echte agent>)
  -> tool-allowlist getoetst op DIE identiteit, niet hardcoded "copilot"
```

De default blijft `"copilot"` zodat het bestaande HTTP-gedrag ongewijzigd is; alleen
aanroepers die een eigen identiteit meegeven krijgen hun eigen allowlist.
