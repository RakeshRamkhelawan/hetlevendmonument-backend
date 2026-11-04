#!/bin/bash
# Run an Azure CLI command with exponential-backoff retry (3 attempts).
# Replaces the identical az_retry() bash function that was copy-pasted into
# cd-staging.yml and cd-production.yml 8 times.
#
# Usage:
#   bash .github/scripts/az-retry.sh containerapp update --name foo ...
#
set -euo pipefail

if [ $# -eq 0 ]; then
  echo "Usage: az-retry.sh <az subcommand> [args...]" >&2
  exit 1
fi

attempt=1
delay=5
max=3

while [ $attempt -le $max ]; do
  # ALLEEN de subcommando's, niet de argumenten (ADR-036 OP-98). `$*` bevat onder meer
  # `--set-secrets "tool-payload-pseudonym-key=<waarde>"`, `"redis-url=<waarde>"` en
  # `--registry-password`. GitHub maskeert die waarden, maar maskering is exacte
  # substring-matching en best-effort -- en op een self-hosted runner staan ze bovendien in
  # /proc/<pid>/cmdline. Een logregel die alleen zegt WELK commando draait is genoeg om een
  # herhaalpoging te kunnen volgen.
  echo "[az-retry $attempt/$max] az $1 ${2:-}"
  if az "$@"; then
    exit 0
  fi
  if [ $attempt -lt $max ]; then
    echo "WARN: attempt $attempt failed — retrying in ${delay}s..."
    sleep "$delay"
    delay=$((delay * 2))
  fi
  attempt=$((attempt + 1))
done

echo "ERROR: all $max attempts failed for: az $1 ${2:-}" >&2
exit 1
