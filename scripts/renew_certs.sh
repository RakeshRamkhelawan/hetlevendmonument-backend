#!/bin/bash
# Certificate renewal is handled automatically by Traefik (ACME).
# This script forces a restart of the proxy to trigger immediate renewal checks if needed.

echo "[RUN] Restarting Traefik to trigger certificate renewal check..."
docker-compose restart traefik
echo "[OK] Traefik restarted."
