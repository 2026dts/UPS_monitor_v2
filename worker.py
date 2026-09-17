"""
Background worker thread: maintains the TCP connection to the
USR-W630, polls the UPS (Q1) every POLL_INTERVAL seconds, updates
shared in-memory state, writes telemetry to PostgreSQL, and evaluates
alarm rules.

ThingsBoard MQTT publishing removed — replaced by db_store.insert_telemetry()
and alarm_engine.evaluate().
"""

import logging
import socket
import time
from datetime import datetime, timezone

import state
from config import UPS_UNITS, TCP_TIMEOUT, POLL_INTERVAL
from parsers import parse_q1
from serial_link import fetch_static_info, receive_response
from battery_estimator import estimate_battery_percentage, estimate_remaining_minutes
import db_store
import alarm_engine

logger = logging.getLogger(__name__)


def ups_worker(ups_id: str, ip: str, port: int, device_name: str):
    """
    Main polling loop for one UPS unit.
    Runs forever in a daemon thread — restarts the TCP connection
    automatically if it drops.
    """

    while True:
        sock = None

        try:
            logger.info("[TCP][%s] Connecting to %s:%s", ups_id, ip, port)

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(TCP_TIMEOUT)
            sock.connect((ip, port))

            logger.info("[TCP][%s] CONNECTED", ups_id)
            db_store.log_connection_event(ups_id, "connected", f"{ip}:{port}")

            # Fetch UPS identity/rating once per connection and persist it
            try:
                fetch_static_info(sock, ups_id)
            except Exception as info_err:
                logger.warning(
                    "[%s] Static info fetch failed (non-fatal): %s",
                    ups_id, info_err
                )

            # ── Main poll loop ────────────────────────────────────────────
            while True:
                started = time.perf_counter()

                with state.state_lock:
                    state.ups_state[ups_id]["last_attempt"] = (
                        datetime.now().isoformat()
                    )

                sock.sendall(b"Q1\r")
                raw = receive_response(sock, "(")

                latency_ms = round((time.perf_counter() - started) * 1000, 2)

                reply = raw.decode("ascii", errors="replace").rstrip("\r")
                parsed = parse_q1(reply)

                # ── Battery estimation ────────────────────────────────────
                unit_config = next(u for u in UPS_UNITS if u["id"] == ups_id)

                battery_voltage = (
                    parsed["battery_bank_voltage_est"]
                    if parsed["battery_bank_voltage_est"] is not None
                    else parsed["battery_voltage"]
                )

                parsed["battery_percentage"] = estimate_battery_percentage(
                    battery_voltage,
                    unit_config["battery_voltage_empty"],
                    unit_config["battery_voltage_full"],
                )

                parsed["estimated_backup_minutes"] = estimate_remaining_minutes(
                    parsed["battery_percentage"],
                    parsed["output_load_pct"],
                    unit_config["reference_runtime_at_full_load_minutes"],
                )

                ts_now = datetime.now(timezone.utc)

                # ── Update shared in-memory state (for the Flask API) ─────
                with state.state_lock:
                    state.ups_state[ups_id] = {
                        "connected": True,
                        "error": None,
                        "ups": parsed,
                        "latency_ms": latency_ms,
                        "last_update": ts_now.isoformat(),
                        "last_attempt": ts_now.isoformat(),
                    }

                logger.debug(
                    "[%s] %s | In: %s V | Out: %s V | Load: %s%% | Batt: %s%%",
                    ups_id,
                    parsed["overall_status"],
                    parsed["input_voltage"],
                    parsed["output_voltage"],
                    parsed["output_load_pct"],
                    parsed["battery_percentage"],
                )

                # ── Persist to PostgreSQL ─────────────────────────────────
                db_store.insert_telemetry(ups_id, parsed, ts_now)

                # ── Evaluate alarm rules ──────────────────────────────────
                alarm_engine.evaluate(ups_id, device_name, parsed)

                time.sleep(POLL_INTERVAL)

        except Exception as error:
            logger.error(
                "[TCP][%s] Error: %s: %s", ups_id, type(error).__name__, error
            )

            with state.state_lock:
                state.ups_state[ups_id]["connected"] = False
                state.ups_state[ups_id]["error"] = (
                    f"{type(error).__name__}: {error}"
                )
                state.ups_state[ups_id]["last_attempt"] = (
                    datetime.now().isoformat()
                )

            try:
                db_store.log_connection_event(
                    ups_id, "disconnected", str(error)
                )
            except Exception:
                pass  # don't crash the worker if DB is also down

        finally:
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass

        logger.info("[TCP][%s] Reconnecting in 3 seconds...", ups_id)
        time.sleep(3)
