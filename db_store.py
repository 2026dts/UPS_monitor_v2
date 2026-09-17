"""
PostgreSQL persistence layer.
Replaces mqtt_client.py — all data that previously went to ThingsBoard
now goes directly into the local Postgres database.

Thread-safe: uses a connection pool (psycopg2 ThreadedConnectionPool).
"""

import logging
import threading
from datetime import datetime, timezone

import psycopg2
import psycopg2.pool
import psycopg2.extras

import config

logger = logging.getLogger(__name__)

# =============================================================
# CONNECTION POOL
# =============================================================

_pool: psycopg2.pool.ThreadedConnectionPool | None = None
_pool_lock = threading.Lock()

# Maps ups_id -> DB asset row id (cached after first lookup)
_asset_id_cache: dict[str, int] = {}
_cache_lock = threading.Lock()


def init_pool():
    """Create the connection pool. Call once at startup."""
    global _pool
    with _pool_lock:
        if _pool is not None:
            return
        try:
            _pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=2,
                maxconn=10,
                dsn=config.DB_DSN,
            )
            logger.info("[DB] Connection pool created → %s:%s/%s",
                        config.DB_HOST, config.DB_PORT, config.DB_NAME)
        except Exception as exc:
            logger.error("[DB] Failed to create connection pool: %s", exc)
            raise


def _get_conn():
    if _pool is None:
        raise RuntimeError("DB pool not initialised — call init_pool() first")
    return _pool.getconn()


def _put_conn(conn):
    if _pool is not None:
        _pool.putconn(conn)


# =============================================================
# ASSET LOOKUP
# =============================================================

def get_asset_id(ups_id: str) -> int:
    """Return the DB asset.id for a given ups_id string, with caching."""
    with _cache_lock:
        if ups_id in _asset_id_cache:
            return _asset_id_cache[ups_id]

    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM assets WHERE ups_id = %s", (ups_id,))
            row = cur.fetchone()
            if row is None:
                raise ValueError(
                    f"UPS unit '{ups_id}' not found in DB. "
                    "Run db/schema.sql seed first."
                )
            asset_id = row[0]
        with _cache_lock:
            _asset_id_cache[ups_id] = asset_id
        return asset_id
    finally:
        _put_conn(conn)


# =============================================================
# TELEMETRY INSERT
# =============================================================

def insert_telemetry(ups_id: str, parsed: dict, ts: datetime | None = None):
    """
    Persist one Q1 reading into the telemetry table.
    `parsed` is the dict returned by parsers.parse_q1(), enriched with
    battery_percentage and estimated_backup_minutes by the worker.
    """
    if ts is None:
        ts = datetime.now(timezone.utc)

    asset_id = get_asset_id(ups_id)

    sql = """
        INSERT INTO telemetry (
            asset_id, ts,
            input_voltage, input_fault_voltage, output_voltage,
            output_load_pct, input_frequency, temperature,
            battery_voltage, battery_bank_voltage_est,
            battery_percentage, estimated_backup_minutes,
            utility_fail, battery_low, avr_active, ups_failed,
            standby_type, test_in_progress, shutdown_active,
            beeper_on, beeper_sounding,
            operating_mode, overall_status
        ) VALUES (
            %(asset_id)s, %(ts)s,
            %(input_voltage)s, %(input_fault_voltage)s, %(output_voltage)s,
            %(output_load_pct)s, %(input_frequency)s, %(temperature)s,
            %(battery_voltage)s, %(battery_bank_voltage_est)s,
            %(battery_percentage)s, %(estimated_backup_minutes)s,
            %(utility_fail)s, %(battery_low)s, %(avr_active)s, %(ups_failed)s,
            %(standby_type)s, %(test_in_progress)s, %(shutdown_active)s,
            %(beeper_on)s, %(beeper_sounding)s,
            %(operating_mode)s, %(overall_status)s
        )
    """

    params = {
        "asset_id":                 asset_id,
        "ts":                       ts,
        "input_voltage":            parsed.get("input_voltage"),
        "input_fault_voltage":      parsed.get("input_fault_voltage"),
        "output_voltage":           parsed.get("output_voltage"),
        "output_load_pct":          parsed.get("output_load_pct"),
        "input_frequency":          parsed.get("input_frequency"),
        "temperature":              parsed.get("temperature"),
        "battery_voltage":          parsed.get("battery_voltage"),
        "battery_bank_voltage_est": parsed.get("battery_bank_voltage_est"),
        "battery_percentage":       parsed.get("battery_percentage"),
        "estimated_backup_minutes": parsed.get("estimated_backup_minutes"),
        "utility_fail":             bool(parsed.get("utility_fail", False)),
        "battery_low":              bool(parsed.get("battery_low", False)),
        "avr_active":               bool(parsed.get("avr_active", False)),
        "ups_failed":               bool(parsed.get("ups_failed", False)),
        "standby_type":             bool(parsed.get("standby_type", False)),
        "test_in_progress":         bool(parsed.get("test_in_progress", False)),
        "shutdown_active":          bool(parsed.get("shutdown_active", False)),
        "beeper_on":                bool(parsed.get("beeper_on", False)),
        "beeper_sounding":          bool(parsed.get("beeper_sounding", False)),
        "operating_mode":           parsed.get("operating_mode"),
        "overall_status":           parsed.get("overall_status"),
    }

    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
        conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.error("[DB] telemetry insert failed for %s: %s", ups_id, exc)
    finally:
        _put_conn(conn)


# =============================================================
# ASSET ATTRIBUTE UPDATE (identity + rating, fetched once)
# =============================================================

def update_asset_info(ups_id: str, info: dict, rating: dict):
    """
    Update the assets row with UPS identity (model, firmware) and
    rating data (rated voltage, current, etc.) when they become available.
    """
    asset_id = get_asset_id(ups_id)

    sql = """
        UPDATE assets SET
            model             = COALESCE(%(model)s, model),
            company_name      = COALESCE(%(company_name)s, company_name),
            firmware_version  = COALESCE(%(firmware_version)s, firmware_version),
            rated_voltage         = COALESCE(%(rated_voltage)s, rated_voltage),
            rated_current         = COALESCE(%(rated_current)s, rated_current),
            rated_battery_voltage = COALESCE(%(rated_battery_voltage)s, rated_battery_voltage),
            rated_frequency       = COALESCE(%(rated_frequency)s, rated_frequency)
        WHERE id = %(asset_id)s
    """

    params = {
        "asset_id":             asset_id,
        "model":                info.get("model") if info else None,
        "company_name":         info.get("company_name") if info else None,
        "firmware_version":     info.get("firmware_version") if info else None,
        "rated_voltage":        rating.get("rated_voltage") if rating else None,
        "rated_current":        rating.get("rated_current") if rating else None,
        "rated_battery_voltage":rating.get("rated_battery_voltage") if rating else None,
        "rated_frequency":      rating.get("rated_frequency") if rating else None,
    }

    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
        conn.commit()
        logger.info("[DB] Asset info updated for %s", ups_id)
    except Exception as exc:
        conn.rollback()
        logger.error("[DB] asset info update failed for %s: %s", ups_id, exc)
    finally:
        _put_conn(conn)


# =============================================================
# ALARM MANAGEMENT
# =============================================================

def open_alarm(ups_id: str, alarm_type: str, severity: str = "critical",
               extra: dict | None = None) -> int | None:
    """
    Open a new alarm episode if one is not already open for this
    ups_id + alarm_type. Returns the alarm id, or None if already open.
    """
    asset_id = get_asset_id(ups_id)
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            # Check for existing open alarm
            cur.execute(
                """
                SELECT id FROM alarms
                WHERE asset_id = %s AND alarm_type = %s AND cleared_at IS NULL
                """,
                (asset_id, alarm_type),
            )
            if cur.fetchone():
                return None     # already open — don't insert duplicate

            cur.execute(
                """
                INSERT INTO alarms (asset_id, alarm_type, severity, extra)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (asset_id, alarm_type, severity,
                 psycopg2.extras.Json(extra) if extra else None),
            )
            alarm_id = cur.fetchone()[0]
        conn.commit()
        logger.info("[DB] Alarm opened: %s / %s (id=%s)", ups_id, alarm_type, alarm_id)
        return alarm_id
    except Exception as exc:
        conn.rollback()
        logger.error("[DB] open_alarm failed: %s", exc)
        return None
    finally:
        _put_conn(conn)


def clear_alarm(ups_id: str, alarm_type: str):
    """Close all open alarms of this type for the given UPS."""
    asset_id = get_asset_id(ups_id)
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE alarms
                SET cleared_at = NOW()
                WHERE asset_id = %s AND alarm_type = %s AND cleared_at IS NULL
                """,
                (asset_id, alarm_type),
            )
            count = cur.rowcount
        conn.commit()
        if count:
            logger.info("[DB] Alarm cleared: %s / %s", ups_id, alarm_type)
    except Exception as exc:
        conn.rollback()
        logger.error("[DB] clear_alarm failed: %s", exc)
    finally:
        _put_conn(conn)


def mark_alarm_notified(alarm_id: int):
    """Record that an email was sent for this alarm."""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE alarms
                SET notified_at = NOW(), notify_count = notify_count + 1
                WHERE id = %s
                """,
                (alarm_id,),
            )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.error("[DB] mark_alarm_notified failed: %s", exc)
    finally:
        _put_conn(conn)


def get_open_alarms() -> list[dict]:
    """Return all currently open alarms (for dashboard alert banner)."""
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT al.id, al.alarm_type, al.severity, al.opened_at,
                       al.notified_at, al.notify_count,
                       a.ups_id, a.device_name
                FROM alarms al
                JOIN assets a ON a.id = al.asset_id
                WHERE al.cleared_at IS NULL
                ORDER BY al.opened_at DESC
                """
            )
            return [dict(r) for r in cur.fetchall()]
    except Exception as exc:
        logger.error("[DB] get_open_alarms failed: %s", exc)
        return []
    finally:
        _put_conn(conn)


# =============================================================
# HISTORY QUERY  (used by the history chart API)
# =============================================================

def get_history(ups_id: str, hours: int = 24) -> list[dict]:
    """
    Return telemetry rows for the last `hours` hours for one UPS unit.
    Downsamples to ~500 points max to keep the JSON payload small.
    """
    asset_id = get_asset_id(ups_id)
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    ts,
                    input_voltage, output_voltage, output_load_pct,
                    input_frequency, battery_percentage,
                    estimated_backup_minutes, battery_voltage,
                    battery_bank_voltage_est, temperature,
                    utility_fail, battery_low, overall_status
                FROM telemetry
                WHERE asset_id = %s
                  AND ts >= NOW() - (%s || ' hours')::INTERVAL
                ORDER BY ts ASC
                """,
                (asset_id, str(hours)),
            )
            rows = cur.fetchall()
            # Convert datetime to ISO string for JSON serialization
            result = []
            for r in rows:
                d = dict(r)
                d["ts"] = d["ts"].isoformat()
                result.append(d)
            return result
    except Exception as exc:
        logger.error("[DB] get_history failed: %s", exc)
        return []
    finally:
        _put_conn(conn)


# =============================================================
# CONNECTION EVENT LOG
# =============================================================

def log_connection_event(ups_id: str, event: str, detail: str = ""):
    """Log a connect / disconnect event to the DB."""
    asset_id = get_asset_id(ups_id)
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO connection_events (asset_id, event, detail)
                VALUES (%s, %s, %s)
                """,
                (asset_id, event, detail),
            )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.error("[DB] log_connection_event failed: %s", exc)
    finally:
        _put_conn(conn)
