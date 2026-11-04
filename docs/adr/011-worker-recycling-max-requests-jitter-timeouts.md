# ADR-011: Worker Recycling - Max Requests, Jitter & Timeouts

## Status
Accepted

## Context
Python processen, zeker met zware AI-bibliotheken (PyTorch, TensorFlow, Transformers), kunnen last hebben van "memory fragmentation" of subtiele memory leaks over tijd. In een 24/7 productie-omgeving kan dit leiden tot trage services of Out-Of-Memory (OOM) crashes.

## Decision
We implementeren een proactieve **Worker Recycling** strategie via Gunicorn configuratie.

### 1. Request-based Recycling
Workers worden herstart nadat ze een bepaald aantal requests hebben afgehandeld.
- **`max_requests`**: 1000 (standaard).
- **`max_requests_jitter`**: 50-100.

**Rationale**: De jitter voorkomt het "Thundering Herd" probleem waarbij alle workers tegelijkertijd herstarten en de service tijdelijk onbereikbaar maken.

### 2. Timeout Hardening
AI-workloads kunnen onvoorspelbaar lang duren. We hanteren strikte grenzen om te voorkomen dat een worker oneindig geblokkeerd blijft door een hangende LLM call:
| Parameter | Waarde | Doel |
| :--- | :--- | :--- |
| **`timeout`** | 60s | Max tijd voor een enkel request |
| **`graceful_timeout`** | 30s | Tijd die een worker krijgt bij shutdown |

### 3. Monitoring (SLI)
| Metriek | Meetmethode | SLO |
| :--- | :--- | :--- |
| **Worker Restarts** | Gunicorn logs / Prometheus | Volgens schema (elke 1000 reqs) |
| **Memory Ceiling** | RAM per worker | < 80% van node limiet |
| **Timeout Rate** | 504 errors / Totaal | < 0.05% |

## Consequences
- **Positive**:
    - Verhoogde stabiliteit op lange termijn; voorkomt progressief geheugenverlies.
    - Voorspelbaardere performance door regelmatige verversing van de OS-processen.
- **Negative**:
    - Een korte latency-piek bij elke herstart van een worker.
    - Cold-start delay: De eerste requests na een herstart kunnen trager zijn door JIT-compilatie of cache-warming.
- **Notes**:
    - Recycling moet gecombineerd worden met goede readiness checks (ADR-012) om te voorkomen dat verkeer naar een herstartende worker gaat.
鼓
