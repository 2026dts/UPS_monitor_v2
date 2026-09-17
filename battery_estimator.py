"""
Battery estimation helpers — pure functions, no side effects.
Unchanged from v1.
"""


def estimate_battery_percentage(voltage, empty_voltage, full_voltage):
    if voltage is None:
        return None
    if empty_voltage is None or full_voltage is None:
        return None
    if full_voltage == empty_voltage:
        return None

    pct = (voltage - empty_voltage) / (full_voltage - empty_voltage) * 100
    return round(max(0.0, min(100.0, pct)), 1)


def estimate_remaining_minutes(battery_percentage, load_pct,
                               reference_runtime_at_full_load_minutes,
                               min_load_pct=5):
    if battery_percentage is None:
        return None
    if reference_runtime_at_full_load_minutes is None:
        return None

    effective_load_pct = max(
        load_pct if load_pct is not None else min_load_pct,
        min_load_pct,
    )

    remaining = (
        reference_runtime_at_full_load_minutes
        * (100 / effective_load_pct)
        * (battery_percentage / 100)
    )
    return round(remaining, 1)
