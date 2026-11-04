#!/bin/bash
# Herhaalbare proef van scripts/backup_db.sh en scripts/restore_db.sh (meetlat eis 6).
#
# Start een WEGWERP-container (tmpfs, tijdelijk wachtwoord, synthetische rijen), maakt een
# back-up, herstelt die op alle manieren die ertoe doen en probeert ook alles wat NIET mag.
# Raakt geen bestaande container of database. Ruimt zichzelf op, ook bij een fout.
#
# Gebruik:   bash scripts/herstelproef.sh
# Eis:       docker, en het image ankane/pgvector:v0.5.1 (of zet PROEF_IMAGE)
# Uitslag:   een regel PASS of FAIL per controle; exitcode 0 alleen als er geen FAIL is.
# Gebruik ook als maandelijkse hersteltest: een back-upproces dat nooit is teruggezet is een
# aanname, geen back-up.

# Bewust geen `set -e`: een falende controle moet als FAIL worden geteld en de rest laten doorlopen.
set -u
export MSYS_NO_PATHCONV=1

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT" || exit 1

C="ss_herstelproef_$$"
IMAGE="${PROEF_IMAGE:-ankane/pgvector:v0.5.1}"
BACKUP_DIR="$(mktemp -d)" || { echo "STOP: geen tijdelijke map te maken"; exit 1; }
export BACKUP_DIR
export POSTGRES_USER=postgres POSTGRES_DB=sanskritisetu

fouten=0
pass() { echo "PASS  $1"; }
fail() { echo "FAIL  $1"; fouten=$((fouten+1)); }
sql() { docker exec -i "$C" psql -U postgres -d "${2:-sanskritisetu}" -At -c "$1"; }

# check "omschrijving" <verwachte exitcode> commando...
check() {
    local oms="$1" verwacht="$2"
    shift 2
    local uit rc
    uit="$("$@" 2>&1)"
    rc=$?
    LAATSTE_UIT="$uit"
    if [ "$rc" -eq "$verwacht" ]; then pass "$oms (rc=$rc)"
    else fail "$oms (rc=$rc, verwacht $verwacht)"; echo "$uit" | tail -5 | sed 's/^/      /'; fi
}
gelijk() { [ "$2" = "$3" ] && pass "$1" || fail "$1 (kreeg '$2', verwacht '$3')"; }

opruimen() { docker rm -f "$C" > /dev/null 2>&1; rm -rf "$BACKUP_DIR"; }
trap opruimen EXIT

echo "== A. meerdere containers zonder keuze: het script weigert"
unset POSTGRES_CONTAINER
if [ "$(docker ps --format '{{.Names}}' | grep -i postgres | grep -vci exporter)" -ge 2 ]; then
    check "backup weigert bij meerdere PostgreSQL-containers" 1 bash scripts/backup_db.sh
    echo "$LAATSTE_UIT" | grep -q "kiest er geen" && pass "de melding zegt dat er niet gekozen wordt" || fail "melding ontbreekt"
else
    echo "SKIP  er draaien minder dan twee PostgreSQL-containers; dit geval is hier niet te proeven"
fi

echo "== B. wegwerp-container"
docker run -d --name "$C" -e POSTGRES_PASSWORD="$(date +%s%N)" -e POSTGRES_DB=sanskritisetu \
    --tmpfs /var/lib/postgresql/data "$IMAGE" > /dev/null || { echo "STOP  container start niet"; exit 1; }
for _ in $(seq 1 60); do docker exec "$C" pg_isready -U postgres -d sanskritisetu > /dev/null 2>&1 && break; sleep 1; done
sleep 2
sql "CREATE TABLE alembic_version(version_num text); INSERT INTO alembic_version VALUES ('proef_rev_1'); CREATE TABLE klant(id serial primary key, naam text); INSERT INTO klant(naam) SELECT 'klant_'||g FROM generate_series(1,500) g;" > /dev/null
export POSTGRES_CONTAINER="$C"
# Harde grens: alles hierna overschrijft en verwijdert databases. Dat mag ALLEEN in de container die
# dit script zelf zojuist startte. Klopt de naam niet, dan stopt de proef voordat er iets gebeurt.
case "$POSTGRES_CONTAINER" in
    ss_herstelproef_*) ;;
    *) echo "STOP  doelcontainer '$POSTGRES_CONTAINER' is geen eigen wegwerpcontainer"; exit 1 ;;
esac
[ "$POSTGRES_CONTAINER" = "$C" ] || { echo "STOP  doelcontainer wijkt af van de gestarte wegwerpcontainer"; exit 1; }
gelijk "beginstand: 500 klanten" "$(sql 'SELECT count(*) FROM klant')" 500

echo "== C. back-up"
check "backup slaagt" 0 bash scripts/backup_db.sh
BK="$(ls -1 "$BACKUP_DIR"/sanskritisetu_*.sql.gz 2>/dev/null | head -1)"
[ -f "$BK" ] && pass "back-upbestand bestaat" || { fail "geen back-upbestand"; echo "STOP"; exit 1; }
ls "$BACKUP_DIR"/*.partial > /dev/null 2>&1 && fail ".partial bleef liggen" || pass "geen .partial achtergebleven"

echo "== D. een onvolledige of beschadigde back-up wordt geweigerd"
head -c 200 "$BK" > "$BACKUP_DIR/kapot.sql.gz"
check "afgekapt bestand geweigerd" 1 bash scripts/restore_db.sh "$BACKUP_DIR/kapot.sql.gz" --naar-database proef_a
gzip -dc "$BK" | grep -v "PostgreSQL database dump complete" | gzip > "$BACKUP_DIR/zonder_staart.sql.gz"
check "dump zonder afsluitregel geweigerd" 1 bash scripts/restore_db.sh "$BACKUP_DIR/zonder_staart.sql.gz" --naar-database proef_a
gelijk "er is geen database proef_a aangemaakt" "$(sql "SELECT count(*) FROM pg_database WHERE datname='proef_a'" template1)" 0

echo "== E. herstel in een NIEUWE database"
check "herstel naar nieuwe database" 0 bash scripts/restore_db.sh "$BK" --naar-database proef_nieuw
gelijk "500 klanten in de herstelde database" "$(sql 'SELECT count(*) FROM klant' proef_nieuw)" 500
gelijk "migratierevisie hersteld" "$(sql 'SELECT version_num FROM alembic_version' proef_nieuw)" proef_rev_1
check "een naam die al bestaat wordt geweigerd" 1 bash scripts/restore_db.sh "$BK" --naar-database proef_nieuw
check "de levende database als doel van --naar-database wordt geweigerd" 2 bash scripts/restore_db.sh "$BK" --naar-database sanskritisetu
check "een ongeldige naam wordt geweigerd" 1 bash scripts/restore_db.sh "$BK" --naar-database "x; DROP DATABASE sanskritisetu"

echo "== F. overschrijven van de levende database"
sql "DELETE FROM klant WHERE id <= 200" > /dev/null
check "zonder --bevestig en zonder toetsenbord geweigerd" 1 bash scripts/restore_db.sh "$BK" < /dev/null
check "met y als bevestiging geweigerd" 1 bash scripts/restore_db.sh "$BK" --bevestig y
gelijk "levende database na de weigeringen ongewijzigd" "$(sql 'SELECT count(*) FROM klant')" 300
check "met de databasenaam als bevestiging" 0 bash scripts/restore_db.sh "$BK" --bevestig sanskritisetu
gelijk "na het herstel zijn alle 500 klanten terug" "$(sql 'SELECT count(*) FROM klant')" 500
VB="$(ls -1 "$BACKUP_DIR"/voor_herstel_sanskritisetu_*.sql.gz 2>/dev/null | head -1)"
if [ -n "$VB" ] \
    && [ "$(gzip -dc "$VB" | grep -cP '\tklant_150$')" = "0" ] \
    && [ "$(gzip -dc "$VB" | grep -cP '\tklant_300$')" = "1" ]; then
    pass "voor-back-up bevat de toestand van VOOR het herstel"
else
    fail "voor-back-up ontbreekt of klopt niet"
fi

echo "== G. een fout halverwege het herstel"
{ gzip -dc "$BK" | grep -v "PostgreSQL database dump complete"; echo "INSERT INTO bestaat_niet VALUES (1);"; echo "-- PostgreSQL database dump complete"; } | gzip > "$BACKUP_DIR/fout_halverwege.sql.gz"
check "mislukt herstel naar nieuwe database geeft een fout" 1 bash scripts/restore_db.sh "$BACKUP_DIR/fout_halverwege.sql.gz" --naar-database proef_fout
gelijk "de halve database is weggehaald" "$(sql "SELECT count(*) FROM pg_database WHERE datname='proef_fout'" template1)" 0
sql "DELETE FROM klant WHERE id <= 100" > /dev/null
check "mislukt overschrijven geeft een fout" 1 bash scripts/restore_db.sh "$BACKUP_DIR/fout_halverwege.sql.gz" --bevestig sanskritisetu
gelijk "levende database ongewijzigd na mislukt herstel" "$(sql 'SELECT count(*) FROM klant')" 400

echo "== H. het oude, gevaarlijke script"
check "restore_postgres.sh weigert" 2 bash scripts/restore_postgres.sh "$BK"

echo
if [ "$fouten" -eq 0 ]; then echo "UITSLAG: geen FAIL"; exit 0; fi
echo "UITSLAG: $fouten FAIL"
exit 1
