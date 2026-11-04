# Single-Tenant Deployment Guide

SanskritiSetu kan worden uitgerold als zelfgehoste single-tenant installatie
via Docker Compose. Dit gids beschrijft de minimale stappen.

## Vereisten

- Docker 24+ met Docker Compose v2
- Minimaal 4 GB RAM, 2 CPU-cores
- Toegang tot het Azure Container Registry (of een lokale image build)

## Stap 1 — Repository en configuratie

```bash
git clone https://github.com/sanskritisetu/sanskritisetu.org
cd sanskritisetu.org
cp .env.single-tenant.example .env
```

## Stap 2 — Verplichte omgevingsvariabelen instellen

Open `.env` en vul alle VERPLICHTE waarden in:

| Variabele | Vereist | Uitleg |
|-----------|---------|--------|
| `SECRET_KEY` | Ja | `openssl rand -hex 32` |
| `DB_PASSWORD` | Ja | Sterk wachtwoord voor PostgreSQL (wordt ook hergebruikt als Redis-wachtwoord, zie hieronder) |
| `DEFAULT_ADMIN_EMAIL` | Ja | E-mailadres van de eerste beheerder |
| `DEFAULT_ADMIN_PASSWORD` | Ja | Minimaal 16 tekens |
| `CORS_ALLOWED_ORIGINS` | Ja | Jouw frontend-domein, bijv. `https://app.mijn-org.nl` |
| `TOOL_PAYLOAD_PSEUDONYM_KEY` | Ja | `python -c "import secrets; print(secrets.token_urlsafe(32))"` -- zie de waarschuwing hieronder |

Laat `CORS_ALLOWED_ORIGINS` nooit leeg of op `*` staan -- dit is een beveiligingsvereiste (SEC-001).

### `TOOL_PAYLOAD_PSEUDONYM_KEY` -- genereren, en daarna nooit meer aanraken

Deze sleutel pseudonimiseert tool-payloads in de auditketen (ADR-036 OP-27). Zonder hem
**start de backend niet** in `production` of `staging`: hij staat in
`PRODUCTION_REQUIRED_VARS`, dus je krijgt een harde bootfout in plaats van een stille
storing bij de eerste tool-aanroep. In `development`, `test` en `local` krijgt elk proces
een willekeurige sleutel en hoef je niets in te stellen.

Genereren, niet verzinnen:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

De code weigert een sleutel die korter is dan 32 tekens, minder dan 8 verschillende tekens
heeft, of een herhaald blok is. Die controle is nadrukkelijk **geen raadbaarheidstoets** --
iets als `sanskritisetu-key-2026` haalt hem gewoon. De bescherming zit in het genereren.

Drie dingen die hierbij anders werken dan bij een gewoon wachtwoord:

1. **Wijzig hem nooit meer.** Verander je de sleutel, dan zijn alle eerder vastgelegde
   auditkenmerken onvergelijkbaar met de nieuwe. Dat spoor is precies wat AI Act art. 12(2)
   van je vraagt -- het is dus bewijsverlies, geen ongemak.
2. **Bewaar hem buiten de server.** Raak je hem kwijt, dan kun je hem niet terughalen; je
   kunt alleen een nieuwe zetten, met gevolg 1.
3. **Een andere waarde per omgeving.** Dezelfde sleutel in staging en productie betekent
   dat wie staging kan lezen de productielogs kan terugrekenen.

## Stap 3 — Containers starten

```bash
docker compose -f docker-compose.single-tenant.yml up -d
```

## Stap 4 — Database migraties uitvoeren

```bash
docker compose -f docker-compose.single-tenant.yml exec backend \
  alembic -c src/alembic.ini upgrade head
```

## Stap 5 — Verificatie

Controleer of de service gezond is:

```bash
curl http://localhost:8110/health/ready
# Verwacht: {"status": "ready"}
```

De applicatie is bereikbaar op `http://localhost:8110`.

## Troubleshooting

**Backend is `unhealthy`**
```bash
docker inspect --format='{{json .State.Health}}' $(docker compose ps -q backend)
```

**Database verbinding mislukt**
Controleer of `DB_PASSWORD` overeenkomt met wat is ingesteld in de PostgreSQL container.

**Redis verbinding mislukt / container start niet**
Redis vereist sinds AUDIT-ARCH-2026-07-02 (SEC-ARCH-002) hetzelfde `DB_PASSWORD` als
wachtwoord (`--requirepass`). Zonder `DB_PASSWORD` in `.env` start de Redis-container
niet. Beide poorten (5432, 6379) zijn bovendien gebonden op `127.0.0.1` -- alleen
bereikbaar vanaf de host zelf, niet van buitenaf.

**CORS-fout in browser**
Zorg dat `CORS_ALLOWED_ORIGINS` exact overeenkomt met het origin van de frontend,
inclusief protocol en poort (bijv. `https://app.mijn-org.nl`).
