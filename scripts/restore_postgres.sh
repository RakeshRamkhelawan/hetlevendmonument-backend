#!/bin/bash
# Vervangen op 2026-10-12 door scripts/restore_db.sh. Dit script doet bewust niets meer.
#
# Wat het deed: `dropdb` op de database uit de omgeving, met als standaard
# `sanskritisetu_prod` op host `postgres`, en daarna een herstel zonder transactie. Een
# vergissing met de omgeving betekende dus een weggegooide productiedatabase en bij een fout
# halverwege een half herstelde. De bevestiging was het woord YES, zonder dat de databasenaam
# erin voorkwam.
#
# Gebruik in plaats daarvan:
#   POSTGRES_CONTAINER=<naam> ./scripts/restore_db.sh <bestand> --naar-database <nieuwe_naam>
#   POSTGRES_CONTAINER=<naam> ./scripts/restore_db.sh <bestand> --bevestig <databasenaam>

echo "restore_postgres.sh is vervangen door scripts/restore_db.sh. Er is niets gewijzigd." >&2
echo "Zie de uitleg bovenin dit bestand." >&2
exit 2
