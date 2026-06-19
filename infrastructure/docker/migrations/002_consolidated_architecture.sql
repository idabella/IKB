-- =============================================================================
-- IKB Consolidated Architecture — Database Migration
-- Version: 002_consolidated_architecture
-- Description: Adds tables required by the Knowledge Engine and Telemetry
--              Aggregator services introduced in the architectural consolidation.
--              Safe to run on an existing database (uses IF NOT EXISTS).
-- =============================================================================

-- Enable TimescaleDB extension (idempotent)
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- =============================================================================
-- KNOWLEDGE ENGINE TABLES
-- =============================================================================

-- Agent task queue and results
CREATE TABLE IF NOT EXISTS agent_tasks (
    task_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      TEXT        NOT NULL,
    tenant_id       TEXT        NOT NULL,
    status          TEXT        NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'cancelled')),
    query           TEXT        NOT NULL,
    metadata        JSONB       NOT NULL DEFAULT '{}',
    result          JSONB,
    error           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_tasks_session  ON agent_tasks (session_id);
CREATE INDEX IF NOT EXISTS idx_agent_tasks_tenant   ON agent_tasks (tenant_id);
CREATE INDEX IF NOT EXISTS idx_agent_tasks_status   ON agent_tasks (status);
CREATE INDEX IF NOT EXISTS idx_agent_tasks_created  ON agent_tasks (created_at DESC);

-- Per-step tool execution trace (for ReAct loop observability)
CREATE TABLE IF NOT EXISTS agent_tool_calls (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id         UUID        NOT NULL REFERENCES agent_tasks(task_id) ON DELETE CASCADE,
    tool_name       TEXT        NOT NULL,
    input_params    JSONB       NOT NULL DEFAULT '{}',
    output_data     JSONB,
    success         BOOLEAN     NOT NULL DEFAULT TRUE,
    error_message   TEXT,
    duration_ms     INTEGER,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tool_calls_task   ON agent_tool_calls (task_id);
CREATE INDEX IF NOT EXISTS idx_tool_calls_tool   ON agent_tool_calls (tool_name);

-- Document ingestion job tracking
CREATE TABLE IF NOT EXISTS ingestion_jobs (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    source_type     TEXT        NOT NULL CHECK (source_type IN ('upload', 'url', 'kafka', 'api')),
    status          TEXT        NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'processing', 'done', 'failed')),
    source_url      TEXT,
    tenant_id       TEXT        NOT NULL,
    factory_id      TEXT        NOT NULL DEFAULT 'default',
    chunk_count     INTEGER,
    error_message   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ingestion_tenant  ON ingestion_jobs (tenant_id);
CREATE INDEX IF NOT EXISTS idx_ingestion_status  ON ingestion_jobs (status);

-- =============================================================================
-- TELEMETRY AGGREGATOR TABLES
-- =============================================================================

-- Anomaly event store (queryable history, replaces Kafka-only pattern)
CREATE TABLE IF NOT EXISTS anomaly_events (
    anomaly_id      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    machine_id      TEXT        NOT NULL,
    sensor_id       TEXT        NOT NULL,
    severity        TEXT        NOT NULL CHECK (severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    value           DOUBLE PRECISION NOT NULL,
    detector_type   TEXT        NOT NULL CHECK (detector_type IN ('rule', 'statistical', 'ml')),
    description     TEXT,
    acknowledged    BOOLEAN     NOT NULL DEFAULT FALSE,
    acknowledged_by TEXT,
    detected_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Convert to a TimescaleDB hypertable for efficient time-range queries
SELECT create_hypertable(
    'anomaly_events', 'detected_at',
    if_not_exists => TRUE,
    migrate_data  => TRUE
);

CREATE INDEX IF NOT EXISTS idx_anomaly_machine   ON anomaly_events (machine_id, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_anomaly_severity  ON anomaly_events (severity, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_anomaly_sensor    ON anomaly_events (sensor_id, detected_at DESC);

-- =============================================================================
-- SHARED / COMMON TABLES
-- =============================================================================

-- Machine registry (shared across services)
CREATE TABLE IF NOT EXISTS machines (
    machine_id      TEXT        PRIMARY KEY,
    factory_id      TEXT        NOT NULL DEFAULT 'default',
    tenant_id       TEXT        NOT NULL,
    name            TEXT        NOT NULL,
    type            TEXT,
    location        TEXT,
    tags            JSONB       NOT NULL DEFAULT '{}',
    active          BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_machines_tenant   ON machines (tenant_id);
CREATE INDEX IF NOT EXISTS idx_machines_factory  ON machines (factory_id);

-- Sensor configuration registry
CREATE TABLE IF NOT EXISTS sensors (
    sensor_id       TEXT        PRIMARY KEY,
    machine_id      TEXT        NOT NULL REFERENCES machines(machine_id) ON DELETE CASCADE,
    name            TEXT        NOT NULL,
    unit            TEXT,
    normal_min      DOUBLE PRECISION,
    normal_max      DOUBLE PRECISION,
    critical_min    DOUBLE PRECISION,
    critical_max    DOUBLE PRECISION,
    active          BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sensors_machine  ON sensors (machine_id);

-- =============================================================================
-- AUTO-UPDATE updated_at TRIGGER
-- =============================================================================

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DO $$
DECLARE
    t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['agent_tasks', 'ingestion_jobs', 'machines'] LOOP
        IF NOT EXISTS (
            SELECT 1 FROM pg_trigger
            WHERE tgname = 'trg_' || t || '_updated_at'
        ) THEN
            EXECUTE format(
                'CREATE TRIGGER trg_%I_updated_at
                 BEFORE UPDATE ON %I
                 FOR EACH ROW EXECUTE FUNCTION set_updated_at()',
                t, t
            );
        END IF;
    END LOOP;
END;
$$;
