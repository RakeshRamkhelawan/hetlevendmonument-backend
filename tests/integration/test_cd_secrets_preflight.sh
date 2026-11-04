#!/usr/bin/env bash
# Test dat preflight logica correct is
set -eu

echo "=== Preflight: verifying required secrets check ==="

# Check dat cd-production.yml een preflight job heeft
if ! grep -q "preflight:" .github/workflows/cd-production.yml; then
  echo "FAIL: cd-production.yml mist preflight job"
  exit 1
fi

# Check dat alle vereiste secrets worden gecontroleerd
for secret in AZURE_CREDENTIALS PROD_DATABASE_URL SECRET_KEY; do
  if ! grep -q "$secret" .github/workflows/cd-production.yml; then
    echo "FAIL: $secret niet gecontroleerd in preflight"
    exit 1
  fi
done

echo "PASS: Alle vereiste secrets worden gecontroleerd"
