#!/bin/bash
# Script to replace pg_hba.conf with trust authentication
# This runs after database initialization completes

cat > /var/lib/postgresql/data/pg_hba.conf <<'EOF'
# PostgreSQL Client Authentication Configuration
# TYPE  DATABASE        USER            ADDRESS                 METHOD
local   all             all                                     trust
host    all             all             127.0.0.1/32            trust
host    all             all             ::1/128                 trust
host    all             all             0.0.0.0/0               trust
host    replication     all             127.0.0.1/32            trust
host    replication     all             ::1/128                 trust
EOF

# Reload PostgreSQL configuration
psql -U test -d test -c "SELECT pg_reload_conf();" || true
