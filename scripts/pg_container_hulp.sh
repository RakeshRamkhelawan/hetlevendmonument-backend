#!/bin/bash
# Gedeelde hulp voor backup_db.sh en restore_db.sh: kies de PostgreSQL-container.
#
# Waarom dit bestaat. De oude scripts namen de EERSTE draaiende container met "postgres" in de
# naam. Op een machine met meer dan een zo'n container (gemeten 2026-10-12: vijf, waaronder
# een testserver en een ander project) maakt of overschrijft dat de verkeerde database zonder
# dat iemand het merkt. Hier geldt: of de container is expliciet opgegeven, of er is er
# PRECIES een. Bij twijfel stopt het script en noemt de kandidaten.
#
# Gebruik: source dit bestand en roep `kies_postgres_container` aan; het antwoord staat in
# de variabele CONTAINER_NAME. Het bestand zelf voert niets uit.

# Geef de namen van draaiende containers waarvan de naam "postgres" bevat, zonder de
# metrics-exporter (die praat met de database maar IS de database niet).
_pg_kandidaten() {
    docker ps --format '{{.Names}}' | grep -i postgres | grep -vi exporter || true
}

# Zet CONTAINER_NAME. Geeft een niet-nul status en een melding op stderr als de keuze niet
# eenduidig is.
# shellcheck disable=SC2034  # CONTAINER_NAME is het antwoord voor het script dat dit bestand source't
kies_postgres_container() {
    local opgegeven="${POSTGRES_CONTAINER:-}"

    if [ -n "$opgegeven" ]; then
        if ! docker ps --format '{{.Names}}' | grep -Fxq -- "$opgegeven"; then
            echo "FOUT: container '$opgegeven' (POSTGRES_CONTAINER) draait niet." >&2
            return 1
        fi
        CONTAINER_NAME="$opgegeven"
        return 0
    fi

    local kandidaten aantal
    kandidaten="$(_pg_kandidaten)"
    if [ -z "$kandidaten" ]; then
        echo "FOUT: geen draaiende PostgreSQL-container gevonden." >&2
        return 1
    fi
    aantal="$(printf '%s\n' "$kandidaten" | wc -l | tr -d ' ')"
    if [ "$aantal" -ne 1 ]; then
        echo "FOUT: $aantal PostgreSQL-containers draaien; het script kiest er geen." >&2
        printf '  - %s\n' $kandidaten >&2
        echo "Zet POSTGRES_CONTAINER=<naam> en probeer opnieuw." >&2
        return 1
    fi
    CONTAINER_NAME="$kandidaten"
    return 0
}

# Een database- of gebruikersnaam mag alleen letters, cijfers en underscores bevatten. Ze
# komen in SQL terecht, dus alles anders weigeren we.
controleer_naam() {
    local soort="$1" waarde="$2"
    # Een bash-regex toetst de HELE tekenreeks. `grep` toetst per regel: een naam met een regeleinde
    # en daarna SQL kwam er door omdat de eerste regel klopte (Gate 2, 2026-10-14).
    if ! [[ "$waarde" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
        echo "FOUT: ongeldige $soort '$waarde' (alleen letters, cijfers en _)." >&2
        return 1
    fi
}
