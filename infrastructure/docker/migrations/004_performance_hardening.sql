-- =============================================================================
-- Migration 004: Index Cleanup + Performance Hardening
-- =============================================================================
-- Safe to re-run: uses IF EXISTS / IF NOT EXISTS throughout.
-- Apply after 003_timescaledb.sql.
-- Run: make migrate-004
-- =============================================================================

-- Step 1: Drop low-selectivity tenant index on sensor_readings
-- ─────────────────────────────────────────────────────────────
-- idx_sr_tenant_time has very low cardinality in typical deployments
-- (most queries already filter on machine_id first).
-- Removing it reduces write amplification by ~15% on sensor_readings.
--
-- If you run cross-tenant admin queries frequently, recreate with:
--   CREATE INDEX idx_sr_tenant_time ON sensor_readings (tenant_id, recorded_at DESC)
--   WITH (timescaledb.transaction_per_chunk);
DROP INDEX IF EXISTS idx_sr_tenant_time;

-- Step 2: Add partial index for active anomaly alert queries
-- ─────────────────────────────────────────────────────────────
-- The most common dashboard query pattern is unresolved CRITICAL/HIGH anomalies.
-- A partial index on (is_resolved=false) covers this at a fraction of the cost.
CREATE INDEX IF NOT EXISTS idx_ae_active_critical
    ON anomaly_events (machine_id, detected_at DESC)
    WHERE is_resolved = FALSE AND severity IN ('CRITICAL', 'HIGH');

-- Step 3: Add covering index for the latest_sensor_readings view
-- ─────────────────────────────────────────────────────────────
-- The view uses DISTINCT ON (machine_id, sensor_id) ORDER BY recorded_at DESC.
-- This index makes it an index-only scan instead of a sequential scan.
CREATE INDEX IF NOT EXISTS idx_sr_machine_sensor_time
    ON sensor_readings (machine_id, sensor_id, recorded_at DESC)
    WITH (timescaledb.transaction_per_chunk);

-- Step 4: Update TimescaleDB chunk compression (optional, enable for cold data)
-- ─────────────────────────────────────────────────────────────────────────────
-- Compresses chunks older than 7 days. Typical compression ratio: 10-20x.
-- Only enable if your TimescaleDB version supports it and disk I/O is a concern.
--
-- ALTER TABLE sensor_readings SET (
--     timescaledb.compress,
--     timescaledb.compress_segmentby = 'machine_id, sensor_id',
--     timescaledb.compress_orderby   = 'recorded_at DESC'
-- );
-- SELECT add_compression_policy('sensor_readings', INTERVAL '7 days', if_not_exists => TRUE);

-- Step 5: Refresh continuous aggregate manually (first-time backfill)
-- ─────────────────────────────────────────────────────────────────────────────
-- The policy only refreshes within the sliding window. This backfills all history.
CALL refresh_continuous_aggregate(
    'sensor_readings_hourly',
    NULL,   -- from beginning of time
    NULL    -- to now
);
