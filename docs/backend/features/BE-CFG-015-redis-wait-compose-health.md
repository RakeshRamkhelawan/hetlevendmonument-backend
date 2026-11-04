# BE-CFG-015: Redis Wait + Compose Health Conditions

## Samenvatting

Voegt een Redis-wait toe aan `entrypoint-dev.sh` en configureert `condition: service_healthy` voor de backend `depends_on` in `docker-compose.dev.yml`. Dit elimineert race conditions tussen backend startup en Redis beschikbaarheid.

## Scope

- `scripts/entrypoint-dev.sh` — Redis wait loop (max 30s)
- `docker-compose.dev.yml` — `depends_on` conditions

## Wijzigingen

### entrypoint-dev.sh

```bash
# Wait for Redis
redis_wait=0
redis_max_wait=30
until redis-cli -h redis -p 6379 ping 2>/dev/null | grep -q PONG; do
    if [ $redis_wait -ge $redis_max_wait ]; then
        echo "[WARN] Redis not available after ${redis_max_wait}s, continuing anyway"
        break
    fi
    echo "  Redis wait $redis_wait/$redis_max_wait"
    sleep 1
    redis_wait=$((redis_wait + 1))
done
if [ $redis_wait -lt $redis_max_wait ]; then
    echo "[OK] Redis ready"
fi
```

### docker-compose.dev.yml

```yaml
depends_on:
  postgres:
    condition: service_healthy
  redis:
    condition: service_healthy
```

## Tests

- `tests/unit/test_startup_infra_config.py::TestEntrypointRedisWait`
- `tests/unit/test_startup_infra_config.py::TestDockerComposeDevConfig`

## ADR Impact

- ADR-009 (Traefik/health): stabielere startup volgorde

## Trainingssamenvatting

> Wacht altijd op alle kritieke dependencies (DB + Redis) voordat je de applicatie start. Gebruik `condition: service_healthy` in compose voor expliciete volgorde, en een wait-loop in het entrypoint als fallback.

- Actor: interne component (niet direct gebruikersgericht)
- Voorwaarde: systeem operationeel; afhankelijkheden beschikbaar
- Actie: automatisch bij startup of deployment
- Systeemverwerking: zie technische beschrijving in spec
- Succesrespons: component actief en beschikbaar
- Foutrespons: startup of initialisatie mislukt; zie applicatielogs
- Uitzonderingen: n.v.t.
