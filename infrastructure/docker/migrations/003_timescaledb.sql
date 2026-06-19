-- =============================================================================
-- Migration 003: TimescaleDB — Time-Series Hypertables
-- =============================================================================
-- Prerequisites: migration 001 and 002 must be applied first.
-- Run: make migrate-003
--
-- What this does:
--   1. Enables the TimescaleDB extension on the existing PostgreSQL instance
--   2. Converts sensor_readings → hypertable (1-day chunks)
--   3. Adds 90-day data retention policy for raw sensor data
--   4. Creates hourly continuous aggregate (replaces InfluxDB Tasks/Flux)
--   5. Converts anomaly_events → hypertable for fast time-range queries
--   6. Adds composite indexes optimised for typical query patterns
--
-- Safe to re-run: uses IF NOT EXISTS / create_hypertable if_not_exists=TRUE
-- =============================================================================

-- Step 1: Enable TimescaleDB
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- =============================================================================
-- sensor_readings hypertable
-- =============================================================================

-- Ensure the base table exists (created in migration 001)
CREATE TABLE IF NOT EXISTS sensor_readings (
    sensor_id   TEXT             NOT NULL,
    machine_id  TEXT             NOT NULL,
    tenant_id   TEXT             NOT NULL,
    value       DOUBLE PRECISION NOT NULL,
    unit        TEXT             NOT NULL DEFAULT '',
    quality     SMALLINT         NOT NULL DEFAULT 100,
    recorded_at TIMESTAMPTZ      NOT NULL DEFAULT NOW()
);

-- Convert to hypertable with 1-day time chunks
-- 1 day = good balance for industrial telemetry (high write, high read yesterday)
SELECT create_hypertable(
    'sensor_readings', 'recorded_at',
    if_not_exists        => TRUE,
    chunk_time_interval  => INTERVAL '1 day',
    create_default_indexes => FALSE   -- we define our own below
);

-- Composite index: most common query pattern (machine + time range)
CREATE INDEX IF NOT EXISTS idx_sr_machine_time
    ON sensor_readings (machine_id, recorded_at DESC)
    WITH (timescaledb.transaction_per_chunk);

-- Sensor-level index for per-sensor history queries
CREATE INDEX IF NOT EXISTS idx_sr_sensor_time
    ON sensor_readings (sensor_id, recorded_at DESC)
    WITH (timescaledb.transaction_per_chunk);

-- Tenant isolation index
CREATE INDEX IF NOT EXISTS idx_sr_tenant_time
    ON sensor_readings (tenant_id, recorded_at DESC)
    WITH (timescaledb.transaction_per_chunk);

-- Automatic data retention: drop raw data older than 90 days
SELECT add_retention_policy(
    'sensor_readings',
    INTERVAL '90 days',
    if_not_exists => TRUE
);

-- =============================================================================
-- Hourly Continuous Aggregate (replaces InfluxDB Tasks)
-- Computed automatically by TimescaleDB background worker
-- =============================================================================

CREATE MATERIALIZED VIEW IF NOT EXISTS sensor_readings_hourly
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', recorded_at) AS bucket,
    machine_id,
    sensor_id,
    tenant_id,
    avg(value)  AS avg_val,
    max(value)  AS max_val,
    min(value)  AS min_val,
    stddev(value) AS stddev_val,
    count(*)    AS sample_count
FROM sensor_readings
GROUP BY bucket, machine_id, sensor_id, tenant_id
WITH NO DATA;  -- populated asynchronously by the refresh policy below

-- Refresh policy: keep aggregate up-to-date within 3h window
SELECT add_continuous_aggregate_policy(
    'sensor_readings_hourly',
    start_offset      => INTERVAL '3 hours',
    end_offset        => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists     => TRUE
);

-- Retain hourly aggregates for 2 years (much longer than raw data)
SELECT add_retention_policy(
    'sensor_readings_hourly',
    INTERVAL '730 days',
    if_not_exists => TRUE
);

-- =============================================================================
-- anomaly_events hypertable
-- =============================================================================

CREATE TABLE IF NOT EXISTS anomaly_events (
    anomaly_id    TEXT             PRIMARY KEY,
    machine_id    TEXT             NOT NULL,
    sensor_id     TEXT             NOT NULL,
    tenant_id     TEXT             NOT NULL DEFAULT 'default',
    severity      TEXT             NOT NULL,
    value         DOUBLE PRECISION,
    threshold     DOUBLE PRECISION,
    detector_type TEXT             NOT NULL DEFAULT 'rule',
    message       TEXT,
    metadata      JSONB            NOT NULL DEFAULT '{}',
    is_resolved   BOOLEAN          NOT NULL DEFAULT FALSE,
    detected_at   TIMESTAMPTZ      NOT NULL DEFAULT NOW()
);

SELECT create_hypertable(
    'anomaly_events', 'detected_at',
    if_not_exists        => TRUE,
    chunk_time_interval  => INTERVAL '7 days'
);

CREATE INDEX IF NOT EXISTS idx_ae_machine_time
    ON anomaly_events (machine_id, detected_at DESC);

CREATE INDEX IF NOT EXISTS idx_ae_severity_time
    ON anomaly_events (severity, detected_at DESC);

-- Retain anomaly events for 1 year
SELECT add_retention_policy(
    'anomaly_events',
    INTERVAL '365 days',
    if_not_exists => TRUE
);

-- =============================================================================
-- Helpful views for the API layer
-- =============================================================================

CREATE OR REPLACE VIEW latest_sensor_readings AS
SELECT DISTINCT ON (machine_id, sensor_id)
    machine_id, sensor_id, tenant_id, value, unit, recorded_at
FROM sensor_readings
ORDER BY machine_id, sensor_id, recorded_at DESC;

COMMENT ON VIEW latest_sensor_readings IS
    'Latest reading per (machine_id, sensor_id) pair. '
    'Fast for dashboard current-value queries.';
