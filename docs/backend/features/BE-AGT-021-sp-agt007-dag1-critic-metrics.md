# BE-AGT-021 -- CriticAgent Prometheus Metrics

## Metadata

- **Sprint**: SP-AGT-007, Dag 1 van 1
- **Status**: IMPLEMENTED
- **Datum**: 2026-06-27
- **Auteur**: Claude (SP-AGT-007 implementatie-agent)

---

## Samenvatting

Drie nieuwe Prometheus-metrics toegevoegd aan CriticAgent via `src/core/observability/metrics.py`.
Metrics worden geemitteerd direct na `store()` in het happy-path van `critique_task()`.

---

## Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `src/core/observability/metrics.py` | 3 nieuwe metrics: `critique_score_histogram`, `critique_latency_seconds`, `critique_panel_invocations_total` |
| `src/core/agents/critic_agent.py` | `import time` + metrics-import + emissie in `critique_task()` |
| `tests/unit/agents/test_critique_metrics.py` | NIEUW -- 4 unit tests (rood voor, groen na) |

---

## Metrics

| Naam (Prometheus) | Type | Labels | Beschrijving |
|---|---|---|---|
| `sanskritisetu_critique_score` | Histogram | `tenant_id`, `mode` | Score-distributie per run |
| `sanskritisetu_critique_latency_seconds` | Histogram | `mode` | Wall-clock van `critique_task()` |
| `sanskritisetu_critique_panel_invocations_total` | Counter | `tenant_id` | Teller judge-panel activaties |

---

## Ontwerpbeslissingen

- Metrics worden NIET geemitteerd op schema-fail pad (score=0.0, geen valid run).
- Panel-counter wordt geincrementeerd zodra de ambiguous-zone-conditie True is, ook als het panel None teruggeeft.
- `import time` is module-level (niet lazy) want het is stdlib.
- Prometheus-variabelnamen zijn lowercase; metric-strings hebben `sanskritisetu_` prefix (consistent met SLICE 3).

---

## Testbewijs

```
tests/unit/agents/test_critique_metrics.py::test_critique_score_histogram_observed PASSED
tests/unit/agents/test_critique_metrics.py::test_critique_latency_histogram_observed PASSED
tests/unit/agents/test_critique_metrics.py::test_panel_counter_incremented_when_panel_activated PASSED
tests/unit/agents/test_critique_metrics.py::test_panel_counter_not_incremented_outside_ambiguous_zone PASSED
```


## Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker of agent
- Voorwaarde: SP-AGT-007 Dag 1: CriticAgent Prometheus metrics (critique_score_histogram, critique_latency_seconds, critique_panel_invocations_total) is beschikbaar en correct geconfigureerd.
- Actie: Geauthenticeerde gebruiker of agent start of gebruikt SP-AGT-007 Dag 1: CriticAgent Prometheus metrics (critique_score_histogram, critique_latency_seconds, critique_panel_invocations_total).
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
