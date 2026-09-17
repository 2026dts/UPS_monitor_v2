"""
Pure parsing functions for Megatec Q1 protocol responses:
Q1 (real-time status), I (UPS identity), F (UPS rating).
No side effects, no shared state — safe to import anywhere.
Unchanged from v1.
"""

# ============================================================
# Q1 PARSER
# ============================================================

def parse_q1(reply):

    if not reply.startswith("("):
        raise ValueError(f"Invalid UPS response: {reply!r}")

    fields = reply[1:].split()

    if len(fields) != 8:
        raise ValueError(f"Expected 8 Q1 fields, received {len(fields)}")

    status_bits = fields[7]

    if len(status_bits) != 8 or any(bit not in "01" for bit in status_bits):
        raise ValueError(f"Invalid UPS status bits: {status_bits!r}")

    utility_fail      = status_bits[0] == "1"
    battery_low       = status_bits[1] == "1"
    avr_active        = status_bits[2] == "1"
    ups_failed        = status_bits[3] == "1"
    standby_type      = status_bits[4] == "1"
    test_in_progress  = status_bits[5] == "1"
    shutdown_active   = status_bits[6] == "1"
    beeper_on         = status_bits[7] == "1"

    if ups_failed:
        overall_status = "FAULT"
    elif battery_low:
        overall_status = "BATTERY LOW"
    elif utility_fail:
        overall_status = "ON BATTERY"
    elif shutdown_active:
        overall_status = "SHUTDOWN ACTIVE"
    elif test_in_progress:
        overall_status = "TEST IN PROGRESS"
    else:
        overall_status = "OK"

    operating_mode = "Battery" if utility_fail else "Online"

    return {
        "input_voltage":            float(fields[0]),
        "input_fault_voltage":      float(fields[1]),
        "output_voltage":           float(fields[2]),
        "output_load_pct":          int(fields[3]),
        "input_frequency":          float(fields[4]),
        "battery_voltage":          float(fields[5]),
        "battery_voltage_is_per_cell": not standby_type,
        "battery_bank_voltage_est": (
            None if standby_type
            else round(float(fields[5]) * 6 * 16, 2)
        ),
        "temperature":              float(fields[6]),
        "status_bits":              status_bits,
        "utility_fail":             utility_fail,
        "battery_low":              battery_low,
        "avr_active":               avr_active,
        "ups_failed":               ups_failed,
        "standby_type":             standby_type,
        "test_in_progress":         test_in_progress,
        "shutdown_active":          shutdown_active,
        "beeper_on":                beeper_on,
        "operating_mode":           operating_mode,
        "overall_status":           overall_status,
        "beeper_sounding":          beeper_on and (utility_fail or battery_low),
        "raw_q1":                   reply,
    }


def parse_info(reply):
    if not reply.startswith("#"):
        raise ValueError(f"Invalid I response: {reply!r}")
    body = reply[1:]
    return {
        "company_name":    body[0:15].strip() or "Not reported by UPS",
        "model":           body[15:25].strip() or "Not reported by UPS",
        "firmware_version":body[25:35].strip() or "Not reported by UPS",
        "raw_i":           reply,
    }


def parse_rating(reply):
    if not reply.startswith("#"):
        raise ValueError(f"Invalid F response: {reply!r}")
    fields = reply[1:].split()
    if len(fields) != 4:
        raise ValueError(f"Expected 4 F fields, received {len(fields)}")
    return {
        "rated_voltage":         float(fields[0]),
        "rated_current":         float(fields[1]),
        "rated_battery_voltage": float(fields[2]),
        "rated_frequency":       float(fields[3]),
        "raw_f":                 reply,
    }
