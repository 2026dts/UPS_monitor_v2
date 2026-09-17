"""
Low-level serial-over-TCP helpers: reading one CR-terminated
response from the USR-W630, and fetching UPS identity + rating
(commands I and F) once per connection.

ThingsBoard publish_attributes() removed — now calls
db_store.update_asset_info() instead.
"""

import logging
import time

import config
import state
from parsers import parse_info, parse_rating
import db_store

logger = logging.getLogger(__name__)


def receive_response(sock, expected_prefix="("):
    """
    Read one logical UPS response and ignore stray trailing/older lines.

    Some newer UPS models emit mixed firmware/rating/status fragments in a
    single TCP read. We keep reading until we see a line that starts with the
    expected prefix for the current command, then return that frame only.
    """
    deadline = time.monotonic() + 1.0
    data = b""

    while True:
        chunk = sock.recv(1024)

        if not chunk:
            raise ConnectionError("USR-W630 closed TCP connection")

        data += chunk

        if len(data) > 4096:
            raise ValueError("UPS response exceeded maximum length")

        text = data.decode("ascii", errors="replace")
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")

        lines = [
            line.strip()
            for line in normalized.split("\n")[:-1]
            if line.strip()
        ]

        valid_lines = [line for line in lines if line.startswith(expected_prefix)]

        if valid_lines:
            return valid_lines[-1].encode("ascii", errors="replace")

        if time.monotonic() >= deadline:
            all_lines = [
                line.strip()
                for line in normalized.split("\n")
                if line.strip()
            ]
            if all_lines:
                return all_lines[-1].encode("ascii", errors="replace")
            raise ValueError("UPS response did not contain a valid frame")


def receive_response_legacy(sock):
    return receive_response(sock, "(")


def fetch_static_info(sock, ups_id):
    """
    Send I and F commands once per TCP connection to get UPS identity and
    rating data, then persist them to the assets table via db_store.
    """
    unit = next(u for u in config.UPS_UNITS if u["id"] == ups_id)
    protocol = unit.get("protocol", "legacy_megatec")

    info_data = None
    rating_data = None

    if protocol == "microtex_10kva":
        try:
            sock.sendall(b"I\r")
            raw_i = receive_response(sock, "#")
            reply_i = raw_i.decode("ascii", errors="replace").rstrip("\r")
            if reply_i and reply_i != "#":
                info_data = parse_info(reply_i)
                state.ups_info[ups_id] = info_data
                logger.info("[%s] UPS INFO: %s", ups_id, info_data)
        except Exception as exc:
            logger.warning("[%s] Microtex info skipped: %s", ups_id, exc)

        try:
            sock.sendall(b"F\r")
            raw_f = receive_response(sock, "#")
            reply_f = raw_f.decode("ascii", errors="replace").rstrip("\r")
            if reply_f and reply_f != "#":
                rating_data = parse_rating(reply_f)
                state.ups_rating[ups_id] = rating_data
                logger.info("[%s] UPS RATING: %s", ups_id, rating_data)
        except Exception as exc:
            logger.warning("[%s] Microtex rating skipped: %s", ups_id, exc)

    else:
        # --- Command: I (UPS Information) ---
        sock.sendall(b"I\r")
        raw_i = receive_response(sock, "#")
        reply_i = raw_i.decode("ascii", errors="replace").rstrip("\r")
        info_data = parse_info(reply_i)
        state.ups_info[ups_id] = info_data
        logger.info("[%s] UPS INFO: %s", ups_id, info_data)

        time.sleep(0.5)

        # --- Command: F (UPS Rating Information) ---
        sock.sendall(b"F\r")
        raw_f = receive_response(sock, "#")
        reply_f = raw_f.decode("ascii", errors="replace").rstrip("\r")
        rating_data = parse_rating(reply_f)
        state.ups_rating[ups_id] = rating_data
        logger.info("[%s] UPS RATING: %s", ups_id, rating_data)

    # Persist identity + rating to Postgres (replaces ThingsBoard publish_attributes)
    if info_data is not None or rating_data is not None:
        db_store.update_asset_info(
            ups_id,
            info_data or {},
            rating_data or {},
        )
