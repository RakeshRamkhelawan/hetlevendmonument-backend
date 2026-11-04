#!/bin/bash
# Herstel van een back-up (gemaakt met scripts/backup_db.sh) in een PostgreSQL-container.
#
# Twee standen:
#
#   1. NIEUWE database (veilig; voor een hersteloefening of om eerst te kijken):
#        POSTGRES_CONTAINER=<naam> ./scripts/restore_db.sh <bestand> --naar-database <nieuwe_naam>
#      De naam mag nog niet bestaan en mag niet die van de levende database zijn. Er wordt
#      niets overschreven. Mislukt het herstel, dan wordt de halve database weer weggehaald.
#
#   2. OVERSCHRIJVEN van de levende database (POSTGRES_DB, default sanskritisetu):
#        POSTGRES_CONTAINER=<naam> ./scripts/restore_db.sh <bestand> --bevestig <databasenaam>
#      De bevestiging moet de NAAM van de database zijn, niet "y". Zonder --bevestig vraagt
#      het script erom, maar alleen als er een toetsenbord is; in een script of cron weigert
#      het. Voor het overschrijven maakt het script eerst een eigen back-up
#      (voor_herstel_<db>_<tijd>.sql.gz); lukt die niet, dan stopt het.
#
# Omgevingsvariabelen: POSTGRES_CONTAINER, POSTGRES_USER (default postgres), POSTGRES_DB
# (default sanskritisetu), BACKUP_DIR (default backups/postgres).
#
# Gewijzigd 2026-10-12 (meetlat eis 6). Wat er stond en wat het kostte:
#   - De container was "de eerste met postgres in de naam", of een vaste naam van een ander
#     project. Op een machine met meer containers overschreef dat de verkeerde database.
#   - De bevestiging was een enkele "y"; twee deploy-scripts stuurden die automatisch mee.
#   - Een fout halverwege het herstel liet een half herstelde database achter en meldde toch
#     "Restore complete".
#   - Het bestand werd niet gecontroleerd voor het begon.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=pg_container_hulp.sh
source "$SCRIPT_DIR/pg_container_hulp.sh"

DB_USER="${POSTGRES_USER:-postgres}"
DB_NAME="${POSTGRES_DB:-sanskritisetu}"
BACKUP_DIR="${BACKUP_DIR:-backups/postgres}"

gebruik() {
    echo "Gebruik: $0 <back-upbestand> --naar-database <nieuwe_naam>" >&2
    echo "     of: $0 <back-upbestand> --bevestig <databasenaam>" >&2
}

BACKUP_FILE=""
NAAR_DB=""
BEVESTIG=""
while [ $# -gt 0 ]; do
    case "$1" in
        --naar-database) [ $# -ge 2 ] || { gebruik; exit 2; }; NAAR_DB="$2"; shift 2 ;;
        --bevestig)      [ $# -ge 2 ] || { gebruik; exit 2; }; BEVESTIG="$2"; shift 2 ;;
        -*)              echo "FOUT: onbekende optie $1" >&2; gebruik; exit 2 ;;
        *)               [ -z "$BACKUP_FILE" ] || { gebruik; exit 2; }; BACKUP_FILE="$1"; shift ;;
    esac
done

[ -n "$BACKUP_FILE" ] || { gebruik; exit 2; }
[ -f "$BACKUP_FILE" ] || { echo "FOUT: bestand niet gevonden: $BACKUP_FILE" >&2; exit 1; }
[ -z "$NAAR_DB" ] || [ -z "$BEVESTIG" ] || {
    echo "FOUT: --naar-database en --bevestig sluiten elkaar uit." >&2; exit 2; }

controleer_naam "databasenaam" "$DB_NAME"
controleer_naam "gebruikersnaam" "$DB_USER"
[ -z "$NAAR_DB" ] || controleer_naam "doeldatabase" "$NAAR_DB"
if [ -n "$NAAR_DB" ] && [ "$NAAR_DB" = "$DB_NAME" ]; then
    echo "FOUT: --naar-database mag niet de levende database ($DB_NAME) zijn; gebruik --bevestig." >&2
    exit 2
fi

# Het bestand moet heel zijn voordat er iets wordt aangeraakt.
if ! gzip -t "$BACKUP_FILE" 2>/dev/null; then
    echo "FOUT: gzip keurt $BACKUP_FILE af; het bestand is beschadigd." >&2
    exit 1
fi
if [ "$(gzip -dc "$BACKUP_FILE" | tail -n 3 | grep -c 'PostgreSQL database dump complete' || true)" -lt 1 ]; then
    echo "FOUT: de dump eindigt niet met 'PostgreSQL database dump complete'; onvolledig." >&2
    exit 1
fi

kies_postgres_container || exit 1

psql_in() {
    # psql in de container, tegen een gegeven database, zonder terminal.
    local db="$1"
    shift
    docker exec -i "$CONTAINER_NAME" psql -U "$DB_USER" -d "$db" -v ON_ERROR_STOP=1 -q "$@"
}

database_bestaat() {
    [ "$(psql_in template1 -At -c "SELECT 1 FROM pg_database WHERE datname = '$1'")" = "1" ]
}

if [ -n "$NAAR_DB" ]; then
    DOEL="$NAAR_DB"
    if database_bestaat "$DOEL"; then
        echo "FOUT: database $DOEL bestaat al in $CONTAINER_NAME; kies een nieuwe naam." >&2
        exit 1
    fi
    echo "Herstellen in NIEUWE database $DOEL (container $CONTAINER_NAME); er wordt niets overschreven."
    psql_in template1 -c "CREATE DATABASE $DOEL"
    HALVE_DB_OPRUIMEN="ja"
else
    DOEL="$DB_NAME"
    database_bestaat "$DOEL" || { echo "FOUT: database $DOEL bestaat niet in $CONTAINER_NAME." >&2; exit 1; }
    echo "=============================================="
    echo "LET OP: dit OVERSCHRIJFT database '$DOEL'"
    echo "Container: $CONTAINER_NAME"
    echo "Bron:      $BACKUP_FILE"
    echo "=============================================="
    if [ -z "$BEVESTIG" ]; then
        if [ -t 0 ]; then
            read -r -p "Typ de naam van de database om door te gaan: " BEVESTIG
        else
            echo "FOUT: geen --bevestig en geen toetsenbord; het script overschrijft niets ongevraagd." >&2
            exit 1
        fi
    fi
    if [ "$BEVESTIG" != "$DOEL" ]; then
        echo "FOUT: bevestiging '$BEVESTIG' is niet de databasenaam '$DOEL'. Niets gewijzigd." >&2
        exit 1
    fi

    mkdir -p "$BACKUP_DIR"
    VOOR="$BACKUP_DIR/voor_herstel_${DOEL}_$(date +%Y%m%d_%H%M%S).sql.gz"
    echo "Eerst een back-up van de huidige database: $VOOR"
    docker exec "$CONTAINER_NAME" pg_dump -U "$DB_USER" --clean --if-exists "$DOEL" | gzip > "$VOOR"
    if ! gzip -t "$VOOR" 2>/dev/null \
        || [ "$(gzip -dc "$VOOR" | tail -n 3 | grep -c 'PostgreSQL database dump complete' || true)" -lt 1 ]; then
        rm -f "$VOOR"
        echo "FOUT: de voor-back-up is mislukt. Niets gewijzigd." >&2
        exit 1
    fi
    chmod 600 "$VOOR"

    psql_in template1 -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DOEL' AND pid <> pg_backend_pid()" > /dev/null
    HALVE_DB_OPRUIMEN=""
fi

echo "Herstellen uit $BACKUP_FILE ..."
if ! gzip -dc "$BACKUP_FILE" | psql_in "$DOEL" --single-transaction > /dev/null; then
    echo "FOUT: het herstel is mislukt." >&2
    if [ -n "$HALVE_DB_OPRUIMEN" ]; then
        psql_in template1 -c "DROP DATABASE IF EXISTS $DOEL" > /dev/null || true
        echo "De halve database $DOEL is weer weggehaald." >&2
    else
        echo "Alles stond in een transactie, dus de levende database is ongewijzigd." >&2
        echo "De voor-back-up staat in $VOOR." >&2
    fi
    exit 1
fi

TABELLEN="$(psql_in "$DOEL" -At -c "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")"
REVISIE="$(psql_in "$DOEL" -At -c "SELECT version_num FROM alembic_version LIMIT 1" 2>/dev/null || echo "onbekend")"
echo "Herstel gelukt: database $DOEL, $TABELLEN tabellen, migratierevisie $REVISIE."
echo "Controleer de inhoud voordat iemand ermee werkt."
