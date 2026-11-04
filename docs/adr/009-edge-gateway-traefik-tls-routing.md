# ADR-009: Edge Gateway - Traefik TLS & Routing

## Status
Accepted | Geimplementeerd op 2026-04-10

## Implementatie

**Uitgevoerd door:** Rakesh Ramkhelawan
**Datum:** 2026-04-10

### Wat is gewijzigd

| Bestand | Wijziging |
| :--- | :--- |
| `traefik/traefik.yml` | Nieuw: statische config — TLS 1.3, LetsEncrypt ACME, Docker provider, Prometheus metrics, ping healthcheck |
| `docker-compose.yml` | `traefik` service toegevoegd; `activepieces-proxy` (nginx) verwijderd; Traefik labels op `backend` en `activepieces`; security headers + HSTS middleware |
| `docker-compose.dev.yml` | Traefik dev override: HTTPS-redirect uit, DEBUG logging |
| `docker-compose.prod.yml` | Traefik prod override: `--api.insecure=false`; frontend port-binding verwijderd (conflict met Traefik poort 80) |
| `nginx-activepieces.conf` | Verwijderd |
| `nginx.conf` (root) | Verwijderd |
| `nginx/nginx.conf` | Verwijderd (legacy) |
| `nginx/nginx.prod.conf` | Verwijderd (legacy) |

### Aandachtspunten voor productie

- Traefik YAML interpoleert geen env vars — `LETSENCRYPT_EMAIL` wordt als CLI flag doorgegeven
- `api.insecure=false` is vereist in productie (overschreven via docker-compose.prod.yml)
- HTTP-01 ACME challenge vereist dat poort 80 publiek bereikbaar is vanuit het internet

## Context
De applicatie bestaat uit meerdere services (FastAPI, Next.js, Realtime). We hebben een centrale toegangspoort nodig die TLS-terminatie, path-based routing en security headers afhandelt zonder de applicatiecode te vervuilen.

### Eisen
1. **Dynamic Configuration**: Automatische detectie van nieuwe containers.
2. **Security**: Ondersteuning voor modern TLS (1.2+) en automatische certificaten.
3. **Observability**: Metrics over inkomend verkeer per service.

### Alternatieven
| Ontvanger | Voordeel | Nadeel | Besluit |
| :--- | :--- | :--- | :--- |
| **NGINX** | Zeer performant; bekend | Statische config; lastig met Docker discovery | **Afgewezen** |
| **Envoy** | Cloud-native; krachtig | Zeer complexe configuratie | **Afgewezen** |
| **Traefik** | Docker-native; auto-config; LetsEncrypt | Iets minder raw performance dan NGINX | **Geselecteerd** |

## Decision
We gebruiken **Traefik** als de Edge Gateway.

### 1. TLS & Security Policy
Alle communicatie verloopt via HTTPS.
- **TLS 1.3** is verplicht waar mogelijk.
- **Auto-TLS**: Gebruik van LetsEncrypt via ACME voor automatische certificaat-vernieuwing.
- **Security Headers**: Traefik injecteert standaard:
    - `X-Frame-Options: DENY`
    - `X-Content-Type-Options: nosniff`
    - `Referrer-Policy: same-origin`

### 2. Header Trust & Forwarding
Omdat de backend achter een proxy draait, moet deze de IP-adressen en protocollen van de originele cliënt kunnen vertrouwen.
```yaml
# docker-compose.yml snippet
labels:
  - "traefik.http.middlewares.secure-headers.headers.sslRedirect=true"
  - "traefik.http.middlewares.secure-headers.headers.browserXssFilter=true"
```
**Belangrijk**: De backend vertrouwt alleen `X-Forwarded-For` headers van de Traefik IP-range (Network Isolation).

### 3. Monitoring (SLI/SLO)
| Metriek | Meetmethode | SLO |
| :--- | :--- | :--- |
| **Request Error Rate** | 5xx errors per service | < 0.1% |
| **TLS Negotiation** | Succesvolle handshakes | > 99.9% |
| **Routing Latency** | Gateway overhead | < 10ms |

## Consequences
- **Positive**:
    - Zero-downtime config updates: Nieuwe services worden direct opgepakt.
    - Gecentraliseerd beheer van SSL en security headers.
- **Negative**:
    - Extra vertragingslaag (overhead) van ~5-10ms per request.
    - Bij een gateway-outage is het hele platform onbereikbaar.
- **Notes**:
    - Traefik metrics worden geëxporteerd naar Prometheus (`:8080/metrics`).
鼓
