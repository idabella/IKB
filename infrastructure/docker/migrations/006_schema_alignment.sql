-- =============================================================================
-- Migration 006: Schema alignment for v2.3 application code
-- =============================================================================
-- Migration 002 creates anomaly_events without tenant_id / is_resolved.
-- Migration 003 uses CREATE TABLE IF NOT EXISTS and therefore does not alter
-- the 002 table. Application code (stream_processor, migration 004 index)
-- expects tenant_id and is_resolved.
-- Safe to re-run: ADD COLUMN IF NOT EXISTS throughout.
-- =============================================================================

ALTER TABLE anomaly_events
    ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'default';

ALTER TABLE anomaly_events
    ADD COLUMN IF NOT EXISTS is_resolved BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE anomaly_events
    ADD COLUMN IF NOT EXISTS description TEXT;

ALTER TABLE anomaly_events
    ADD COLUMN IF NOT EXISTS message TEXT;

-- Partial index from migration 004 (may have been skipped if is_resolved was missing)
CREATE INDEX IF NOT EXISTS idx_ae_active_critical
    ON anomaly_events (machine_id, detected_at DESC)
    WHERE is_resolved = FALSE AND severity IN ('CRITICAL', 'HIGH');
