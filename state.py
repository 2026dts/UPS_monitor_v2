"""
Shared in-memory UPS state, updated by the polling worker and read
by the Flask API/dashboard. state_lock guards concurrent access.
Unchanged from v1 — ThingsBoard removal doesn't affect in-memory state.
"""

import threading
import config

state_lock = threading.Lock()

ups_state = {}
ups_info  = {}
ups_rating = {}

for unit in config.UPS_UNITS:
    ups_state[unit["id"]] = {
        "connected":    False,
        "error":        "Waiting for first UPS poll",
        "ups":          None,
        "latency_ms":   None,
        "last_update":  None,
        "last_attempt": None,
    }
    ups_info[unit["id"]] = {
        "company_name":     None,
        "model":            None,
        "firmware_version": None,
    }
    ups_rating[unit["id"]] = {
        "rated_voltage":         None,
        "rated_current":         None,
        "rated_battery_voltage": None,
        "rated_frequency":       None,
    }
