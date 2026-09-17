-- =============================================================
-- UPS Monitoring Platform — PostgreSQL Schema
-- Migration from ThingsBoard to local Postgres storage
-- =============================================================

-- Enable TimescaleDB extension (if available on server)
-- If TimescaleDB is not installed, comment out the hypertable line below.
-- Plain Postgres will still work — just without automatic time partitioning.
-- CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- =============================================================
-- ASSETS — one row per UPS unit
-- =============================================================
CREATE TABLE IF NOT EXISTS assets (
    id                    SERIAL PRIMARY KEY,
    ups_id                TEXT NOT NULL UNIQUE,          -- matches config.py id e.g. 'ups1'
    device_name           TEXT NOT NULL,                 -- human name e.g. 'Server'
    ip                    TEXT,
    port                  INTEGER,
    installed_on          DATE DEFAULT CURRENT_DATE,
    battery_voltage_empty NUMERIC(8,2),
    battery_voltage_full  NUMERIC(8,2),
    ref_runtime_minutes   INTEGER,                       -- reference_runtime_at_full_load_minutes
    rated_voltage         NUMERIC(8,2),
    rated_current         NUMERIC(8,2),
    rated_battery_voltage NUMERIC(8,2),
    rated_frequency       NUMERIC(6,2),
    model                 TEXT,
    company_name          TEXT,
    firmware_version      TEXT,
    created_at            TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================
-- TELEMETRY — high-frequency time-series readings
-- =============================================================
CREATE TABLE IF NOT EXISTS telemetry (
    id                          BIGSERIAL,
    asset_id                    INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    ts                          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Electrical
    input_voltage               NUMERIC(8,2),
    input_fault_voltage         NUMERIC(8,2),
    output_voltage              NUMERIC(8,2),
    output_load_pct             NUMERIC(6,2),
    input_frequency             NUMERIC(6,2),
    temperature                 NUMERIC(6,2),

    -- Battery
    battery_voltage             NUMERIC(8,2),           -- per-cell value from UPS
    battery_bank_voltage_est    NUMERIC(10,2),          -- derived: cell * 6 * 16
    battery_percentage          NUMERIC(6,2),
    estimated_backup_minutes    NUMERIC(8,2),

    -- Status flags (stored as booleans for easy querying)
    utility_fail                BOOLEAN DEFAULT FALSE,
    battery_low                 BOOLEAN DEFAULT FALSE,
    avr_active                  BOOLEAN DEFAULT FALSE,
    ups_failed                  BOOLEAN DEFAULT FALSE,
    standby_type                BOOLEAN DEFAULT FALSE,
    test_in_progress            BOOLEAN DEFAULT FALSE,
    shutdown_active             BOOLEAN DEFAULT FALSE,
    beeper_on                   BOOLEAN DEFAULT FALSE,
    beeper_sounding             BOOLEAN DEFAULT FALSE,

    -- Derived
    operating_mode              TEXT,                   -- 'Online' | 'Battery'
    overall_status              TEXT,                   -- 'OK' | 'ON BATTERY' | 'FAULT' | ...

    PRIMARY KEY (id, ts)
);

-- Index for fast per-asset, time-ordered queries (charts, history)
CREATE INDEX IF NOT EXISTS idx_telemetry_asset_ts
    ON telemetry (asset_id, ts DESC);

-- Partial index to quickly find utility-fail events for email dedup
CREATE INDEX IF NOT EXISTS idx_telemetry_utility_fail
    ON telemetry (asset_id, ts DESC)
    WHERE utility_fail = TRUE;

-- =============================================================
-- ALARMS — one row per alarm episode (open → clear)
-- =============================================================
CREATE TABLE IF NOT EXISTS alarms (
    id              SERIAL PRIMARY KEY,
    asset_id        INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    alarm_type      TEXT NOT NULL,          -- 'utility_fail' | 'battery_low' | 'ups_failed' etc.
    severity        TEXT NOT NULL DEFAULT 'critical',   -- 'critical' | 'warning' | 'info'
    opened_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    cleared_at      TIMESTAMPTZ,
    notified_at     TIMESTAMPTZ,            -- when the email was sent
    notify_count    INTEGER DEFAULT 0,      -- how many emails sent for this episode
    extra           JSONB                   -- any extra context (voltage value, etc.)
);

CREATE INDEX IF NOT EXISTS idx_alarms_asset_open
    ON alarms (asset_id, opened_at DESC)
    WHERE cleared_at IS NULL;

-- =============================================================
-- CONNECTION LOG — track ups connect/disconnect events
-- =============================================================
CREATE TABLE IF NOT EXISTS connection_events (
    id          BIGSERIAL PRIMARY KEY,
    asset_id    INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    ts          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    event       TEXT NOT NULL,              -- 'connected' | 'disconnected'
    detail      TEXT
);

-- =============================================================
-- SEED ASSETS from config.py values
-- Run this once after creating the schema.
-- Update IPs / runtime values to match your config.py exactly.
-- =============================================================
INSERT INTO assets (ups_id, device_name, ip, port, battery_voltage_empty, battery_voltage_full, ref_runtime_minutes)
VALUES
    ('ups1', 'Server',            '10.10.10.75', 8899, 168.0, 218.0, 8),
    ('ups2', 'Workstation',       '10.10.10.74', 8899, 168.0, 218.0, 12),
    ('ups3', 'UPS-Command Centre','10.10.10.76', 8899, 168.0, 218.0, 12)
ON CONFLICT (ups_id) DO UPDATE
    SET device_name           = EXCLUDED.device_name,
        ip                    = EXCLUDED.ip,
        port                  = EXCLUDED.port,
        battery_voltage_empty = EXCLUDED.battery_voltage_empty,
        battery_voltage_full  = EXCLUDED.battery_voltage_full,
        ref_runtime_minutes   = EXCLUDED.ref_runtime_minutes;

-- =============================================================
-- USEFUL VIEWS
-- =============================================================

-- Latest reading per UPS (used by the live dashboard)
CREATE OR REPLACE VIEW latest_telemetry AS
SELECT DISTINCT ON (asset_id)
    t.*,
    a.ups_id,
    a.device_name,
    a.ip,
    a.port
FROM telemetry t
JOIN assets a ON a.id = t.asset_id
ORDER BY asset_id, ts DESC;

-- Open alarms (used by the alert banner on dashboard)
CREATE OR REPLACE VIEW open_alarms AS
SELECT
    al.*,
    a.ups_id,
    a.device_name
FROM alarms al
JOIN assets a ON a.id = al.asset_id
WHERE al.cleared_at IS NULL
ORDER BY al.opened_at DESC;
