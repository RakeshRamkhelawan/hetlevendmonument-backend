#!/bin/bash
# Meet de bonlezer van begin tot eind: een upload via de API, gelezen door de worker (bonlezer dag 3).
#
# Met wegwerpcontainers op een INTERN Docker-netwerk (niets wordt gedeployed, niets blijft staan):
#   1. een eigen Redis met een wegwerpwachtwoord (zoals `bonlezer-redis` in docker-compose.yml);
#   2. de worker (het gebouwde image), uploadmap ALLEEN-LEZEN;
#   3. een API-container (zelfde image) die het meetharnas draait (`scripts/bonlezer_upload_api.py`:
#      de echte bonnen-route), uploadmap SCHRIJFBAAR;
#   4. in die API-container de client (`scripts/bonlezer_upload_meting.py`): 24 uploads via HTTP, daarna de randen;
#   5. het worker-log wordt bewaard en gecontroleerd op bontekst.
#
# Gebruik:
#   UIT=<map voor de uitvoer> bash scripts/bonlezer/meet_upload.sh [image]
# Het image is standaard `sanskritisetu-bonlezer-worker:dag3`
# (`docker build --target bonlezer-worker -t sanskritisetu-bonlezer-worker:dag3 .`).

set -euo pipefail
export MSYS_NO_PATHCONV=1

IMAGE="${1:-sanskritisetu-bonlezer-worker:dag3}"
UIT="${UIT:?zet UIT=<map voor de uitvoer>}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && (pwd -W 2>/dev/null || pwd))"
NET=bl3_meting_intern
NET2=bl3_meting_koppel
REDIS=bl3_meting_redis
WORKER=bl3_meting_worker
API=bl3_meting_api
WACHTWOORD=wegwerp-meting
BROKER_URL="redis://:${WACHTWOORD}@${REDIS}:6379/0"

opruimen() {
    docker logs "$API" > "$UIT/api-dag3.log" 2>&1 || true
    docker rm -f "$API" "$WORKER" "$REDIS" >/dev/null 2>&1 || true
    docker network rm "$NET" "$NET2" >/dev/null 2>&1 || true
}
trap opruimen EXIT
opruimen

rm -rf "$UIT/uploads"
mkdir -p "$UIT/uploads"
chmod 777 "$UIT/uploads" 2>/dev/null || true

docker network create --internal "$NET" >/dev/null
docker network create --internal "$NET2" >/dev/null
docker run -d --name "$REDIS" --network "$NET" redis:7-alpine \
    redis-server --requirepass "$WACHTWOORD" --appendonly no --save "" \
    --maxmemory 256mb --maxmemory-policy noeviction >/dev/null
docker network connect "$NET2" "$REDIS"
docker run -d --name "$WORKER" --network "$NET" \
    -e BONLEZER_BROKER_URL="$BROKER_URL" \
    -v "$UIT/uploads:/data/bonnen:ro" \
    "$IMAGE" >/dev/null
docker run -d --name "$API" --network "$NET2" --entrypoint python \
    -e BONLEZER_BROKER_URL="$BROKER_URL" -e BONLEZER_UPLOAD_ROOT=/data/bonnen \
    -e BONLEZER_SOCKET_TIMEOUT=5 \
    -e TESTING=1 -e PYTHONPATH=/app:/repo/scripts \
    -v "$REPO:/repo:ro" -v "$UIT/uploads:/data/bonnen" -v "$UIT:/uit" \
    "$IMAGE" -m uvicorn bonlezer_upload_api:app --host 127.0.0.1 --port 8000 >/dev/null

echo "wachten tot de worker en de API klaar zijn ..."
for _ in $(seq 1 120); do
    if docker logs "$WORKER" 2>&1 | grep -qi "worker process is ready" && \
       docker logs "$API" 2>&1 | grep -qi "application startup complete"; then break; fi
    sleep 2
done
docker logs "$WORKER" 2>&1 | tail -3
docker logs "$API" 2>&1 | tail -3

echo "== controle van het netwerk van de worker (verwacht: Redis bereikbaar, de API en het internet niet)"
docker exec "$WORKER" python -c "
import socket
for naam, adres in (('redis', ('$REDIS', 6379)), ('api', ('$API', 8000)), ('internet', ('1.1.1.1', 53))):
    try:
        socket.create_connection(adres, timeout=4).close()
        print(naam, 'BEREIKBAAR')
    except Exception as fout:
        print(naam, 'niet bereikbaar:', type(fout).__name__)
" | tee "$UIT/netwerkcontrole-dag3.txt"

docker exec -e PYTHONPATH=/app:/repo/scripts "$API" python /repo/scripts/bonlezer_upload_meting.py \
    --uit /uit/upload-verslag.md | tee "$UIT/upload-meting.log"

docker logs "$WORKER" > "$UIT/worker-dag3.log" 2>&1
echo "worker-log bewaard in $UIT/worker-dag3.log"
