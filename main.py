"""
Entry point — UPS Monitoring Platform v2.
ThingsBoard removed. Data flows: USR-W630 → Postgres + local dashboard.

Run: python3 main.py
"""

import logging
import socket
import sys
import threading

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)

from config import UPS_UNITS, WEB_HOST, WEB_PORT, DB_HOST, DB_PORT, DB_NAME
import db_store
import audio_alert
from worker import ups_worker
from web_app import app


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect((UPS_UNITS[0]["ip"], 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


if __name__ == "__main__":

    lan_ip = get_local_ip()

    print()
    print("=" * 70)
    print("  UPS MONITORING SYSTEM  v2")
    print("=" * 70)
    devices_str = ", ".join(f"{u['ip']}:{u['port']}" for u in UPS_UNITS)
    print(f"  USR devices : {devices_str}")
    print(f"  Protocol    : Megatec Q1")
    print(f"  Database    : {DB_HOST}:{DB_PORT}/{DB_NAME}  (PostgreSQL)")
    print(f"  Web (local) : http://127.0.0.1:{WEB_PORT}")
    print(f"  Web (LAN)   : http://{lan_ip}:{WEB_PORT}")
    print("  ThingsBoard : [REMOVED — using local Postgres]")
    print("=" * 70)
    print()

    # ── Initialise database connection pool ───────────────────────────────
    try:
        db_store.init_pool()
    except Exception as exc:
        logger.critical("Cannot connect to PostgreSQL: %s", exc)
        logger.critical(
            "Ensure Postgres is running and DB_HOST/DB_NAME/DB_USER/DB_PASSWORD "
            "are set correctly in config.py or environment variables."
        )
        sys.exit(1)

    # ── Start one polling worker thread per UPS ───────────────────────────
    for unit in UPS_UNITS:
        t = threading.Thread(
            target=ups_worker,
            args=(unit["id"], unit["ip"], unit["port"], unit["device_name"]),
            daemon=True,
            name=f"worker-{unit['id']}",
        )
        t.start()
        logger.info("Started worker thread for %s (%s)", unit["device_name"], unit["id"])

    # ── Start PC speaker audio alert engine ──────────────────────────────
    audio_alert.start_audio_thread()

    # ── Run Flask web server (blocking) ───────────────────────────────────
    app.run(
        host=WEB_HOST,
        port=WEB_PORT,
        debug=False,
        threaded=True,
    )
