#!/bin/bash
set -euo pipefail

echo "▶ IKB: applying SQL migrations (001 → 006)..."

MIGRATION_DIR="/docker-migrations"
DB_USER="${POSTGRES_USER:-ikb_admin}"
DB_NAME="${POSTGRES_DB:-ikb_main}"

for migration in \
    001_initial_schema.sql \
    002_consolidated_architecture.sql \
    003_timescaledb.sql \
    004_performance_hardening.sql \
    005_missing_tables.sql \
    006_schema_alignment.sql
do
    path="${MIGRATION_DIR}/${migration}"
    if [ -f "$path" ]; then
        echo "  → ${migration}"
        psql -v ON_ERROR_STOP=0 -U "$DB_USER" -d "$DB_NAME" -f "$path" || true
    else
        echo "  ⚠ missing: ${migration}"
    fi
done

echo "✅ IKB migrations complete."
