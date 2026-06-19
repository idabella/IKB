-- =============================================================================
-- Migration 001: Initial Schema (Baseline)
-- =============================================================================
-- This is the baseline migration that must be applied to a fresh database
-- before migration 002. It creates the foundational tables.
-- Safe to re-run: all statements use IF NOT EXISTS.
-- =============================================================================

-- Enable useful extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";   -- trigram search on text fields

-- =============================================================================
-- Tenants & Users
-- =============================================================================

CREATE TABLE IF NOT EXISTS tenants (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    slug        TEXT        NOT NULL UNIQUE,
    name        TEXT        NOT NULL,
    is_active   BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS users (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID        NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email       TEXT        NOT NULL UNIQUE,
    roles       TEXT[]      NOT NULL DEFAULT '{}',
    factory_ids TEXT[]      NOT NULL DEFAULT '{}',
    is_active   BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_tenant ON users(tenant_id);

-- =============================================================================
-- Factories & Machines
-- =============================================================================

CREATE TABLE IF NOT EXISTS factories (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   TEXT        NOT NULL,
    name        TEXT        NOT NULL,
    location    TEXT,
    metadata    JSONB       NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS machines (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    factory_id  UUID        REFERENCES factories(id) ON DELETE CASCADE,
    tenant_id   TEXT        NOT NULL,
    machine_id  TEXT        NOT NULL,           -- business key e.g. "CNC-07"
    name        TEXT        NOT NULL,
    type        TEXT,
    metadata    JSONB       NOT NULL DEFAULT '{}',
    is_active   BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, machine_id)
);

CREATE TABLE IF NOT EXISTS sensors (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    machine_id  UUID        NOT NULL REFERENCES machines(id) ON DELETE CASCADE,
    tenant_id   TEXT        NOT NULL,
    sensor_id   TEXT        NOT NULL,           -- business key e.g. "temp-01"
    name        TEXT        NOT NULL,
    unit        TEXT        NOT NULL DEFAULT '',
    thresholds  JSONB       NOT NULL DEFAULT '{"warning": null, "critical": null}',
    is_active   BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (machine_id, sensor_id)
);

CREATE INDEX IF NOT EXISTS idx_sensors_machine ON sensors(machine_id);

-- =============================================================================
-- Sensor Readings (time-series — will become a TimescaleDB hypertable in 003)
-- =============================================================================

CREATE TABLE IF NOT EXISTS sensor_readings (
    sensor_id   TEXT        NOT NULL,
    machine_id  TEXT        NOT NULL,
    tenant_id   TEXT        NOT NULL,
    value       DOUBLE PRECISION NOT NULL,
    unit        TEXT        NOT NULL DEFAULT '',
    quality     SMALLINT    NOT NULL DEFAULT 100,  -- 0-100 data quality score
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sensor_readings_machine_time
    ON sensor_readings(machine_id, recorded_at DESC);

CREATE INDEX IF NOT EXISTS idx_sensor_readings_sensor_time
    ON sensor_readings(sensor_id, recorded_at DESC);

-- =============================================================================
-- Audit Log (append-only)
-- =============================================================================

CREATE TABLE IF NOT EXISTS audit_log (
    id          BIGSERIAL   PRIMARY KEY,
    tenant_id   TEXT        NOT NULL,
    user_id     TEXT        NOT NULL,
    action      TEXT        NOT NULL,
    resource    TEXT        NOT NULL,
    resource_id TEXT,
    metadata    JSONB       NOT NULL DEFAULT '{}',
    ip_address  INET,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_tenant_time ON audit_log(tenant_id, created_at DESC);

-- =============================================================================
-- Updated-at trigger function (shared)
-- =============================================================================

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE OR REPLACE TRIGGER trg_tenants_updated_at
    BEFORE UPDATE ON tenants
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE OR REPLACE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE OR REPLACE TRIGGER trg_machines_updated_at
    BEFORE UPDATE ON machines
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
